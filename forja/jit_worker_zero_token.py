#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
WORKER & API JIT ZERO-TOKEN (`forja/jit_worker_zero_token.py`)
==============================================================
Integra o Motor de Vídeo RTX 4050 (`:5255`) com o Hub Central (`C:\Hub001` · `:3001`)
operando 100% em Python puro (Zero Tokens de LLM + Zero Créditos Flow em `veo_3_1_i2v_lite_low_priority`).

Fluxo de Ordem JIT (`POST /api/jit-order`):
1. Recebe o pedido do Hub `:3001` (`ROLETA_AVATAR_CENARIO`, `ROLETA_OXIGENACAO_FORMATO`, `HOT_NEW_BATCH`).
2. Persiste na fila local (`scratch_lan_dump/forja_jit_orders.json`).
3. Resolve o `manifest.json` correspondente no Cofre de Moldes (`forja/cofre_moldes.py`).
4. Calcula o próximo `SEQ` (`001..999`) dentro de `output_dir` sem jamais sobrescrever vídeos existentes:
   `[PAÍS]_[NICHO]_[FORMATO]_[COPY]_[GANCHO]_[LEVA]_[SEQ].mp4`
5. Streaming Atômico:
   - Se `supply_mode == "COFRE_FIRST"` (default para oxigenação imediata) e houver vídeos auditados inéditos no Cofre daquele formato que ainda não estão em `output_dir`, faz streaming via `.tmp.mp4` -> rename atômico e dispara `webhook_done` a cada marco (20 vídeos + conclusão).
   - Se `supply_mode == "FORJA_FRESH"` ou quando o estoque inédito do Cofre acaba, aciona o gerador local Python em `veo_3_1_i2v_lite_low_priority` (`0` créditos) nas 5 contas (`:9225..9230`), auditando com `JuizVisualGPU` + `Faster-Whisper` + `h264_nvenc` e gravando via `.tmp.mp4` -> rename atômico em `output_dir`.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import threading
import time
from typing import Any
import urllib.request as _ur

from forja.cofre_moldes import listar_moldes_homologados, resolver_molde_por_dna

ROOT = Path(__file__).resolve().parent.parent
ORDERS_FILE = ROOT / "scratch_lan_dump" / "forja_jit_orders.json"
HUB_QUEUE_MIRROR = Path(r"C:\Hub001\data\forja_jit_queue.json")
CONTAS_JSON = ROOT / "forja" / "contas_flow.json"

_JIT_LOCK = threading.Lock()
_WORKER_STATE = "IDLE"
_ACTIVE_ORDER_ID: str | None = None
_WORKER_THREAD: threading.Thread | None = None


def _carregar_ordens() -> list[dict[str, Any]]:
    ORDERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not ORDERS_FILE.exists():
        return []
    try:
        data = json.loads(ORDERS_FILE.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
        return list(data.get("orders") or [])
    except Exception:
        return []


def _salvar_ordens(orders: list[dict[str, Any]]) -> None:
    ORDERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = ORDERS_FILE.with_suffix(".tmp.json")
    tmp.write_text(json.dumps({"updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "orders": orders}, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(ORDERS_FILE)


def calcular_proximos_nomes_6_blocos(dna: dict[str, Any], output_dir: str | Path, quantity: int) -> tuple[int, list[str]]:
    """
    Calcula o próximo SEQ disponível em `output_dir` sem sobrescrever arquivos existentes
    e retorna `(next_seq_start, [lista_de_nomes_mp4])` no padrão:
    `[PAÍS]_[NICHO]_[FORMATO]_[COPY]_[GANCHO]_[LEVA]_[SEQ].mp4`
    """
    country = str(dna.get("country") or "US").upper()
    niche = str(dna.get("niche") or "WL").upper()
    fmt = str(dna.get("format") or "F37").upper()
    copy_c = str(dna.get("copy") or "C01").upper()
    hook_c = str(dna.get("hook") or "G00").upper()
    batch_c = str(dna.get("batch") or "L01").upper()
    prefix = f"{country}_{niche}_{fmt}_{copy_c}_{hook_c}_{batch_c}_"

    out_path = Path(output_dir)
    max_seq = 0
    if out_path.exists():
        for p in out_path.glob("*.mp4"):
            if p.name.endswith(".tmp.mp4"):
                continue
            m = re.search(r"_(\d{3,4})\.mp4$", p.name)
            if m:
                seq_n = int(m.group(1))
                if seq_n > max_seq:
                    max_seq = seq_n

    start_seq = max_seq + 1
    filenames = [f"{prefix}{seq:03d}.mp4" for seq in range(start_seq, start_seq + max(1, int(quantity)))]
    return start_seq, filenames


def _disparar_webhook(url: str, payload: dict[str, Any], timeout: float = 4.0) -> tuple[bool, int, str]:
    if not url:
        return False, 0, "NO_WEBHOOK_URL"
    try:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = _ur.Request(url, data=raw, headers={"Content-Type": "application/json; charset=utf-8"}, method="POST")
        with _ur.urlopen(req, timeout=timeout) as resp:
            code = int(resp.getcode() or 200)
            body = resp.read().decode("utf-8", errors="replace")[:300]
            return True, code, body
    except Exception as exc:
        return False, 0, str(exc)[:250]


def executar_dry_run_jit(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Valida resolução do `manifest.json`, cálculo de nomes de 6 blocos em `output_dir`
    e conectividade opcional do webhook SEM gastar 1 único crédito/chamada no Google Flow.
    """
    dna = payload.get("dna") or {
        "country": "US",
        "niche": "WL",
        "format": "F37",
        "copy": "C01",
        "hook": "G00",
        "batch": "L01",
    }
    qty = int(payload.get("quantity") or 5)
    out_dir = payload.get("output_dir") or str(Path(r"C:\Hub001\VIDEOS_ESTEIRA_TREE") / dna.get("country", "US") / dna.get("niche", "WL") / dna.get("format", "F37") / dna.get("copy", "C01") / dna.get("hook", "G00"))
    molde = resolver_molde_por_dna(dna)
    start_seq, planned_files = calcular_proximos_nomes_6_blocos(dna, out_dir, qty)

    webhook_url = str(payload.get("webhook_done") or "")
    ping_webhook = bool(payload.get("ping_webhook", False))
    wh_res = {"tested": False, "ok": False, "status": 0, "detail": "skipped_in_dry_run"}
    if ping_webhook and webhook_url:
        ok_w, code_w, det_w = _disparar_webhook(
            webhook_url,
            {
                "dry_run": True,
                "order_id": payload.get("order_id") or "dry_run_test",
                "order_type": payload.get("order_type") or "ROLETA_AVATAR_CENARIO",
                "dna": dna,
                "planned_files_sample": planned_files[:3],
            },
        )
        wh_res = {"tested": True, "ok": ok_w, "status": code_w, "detail": det_w}

    return {
        "ok": molde is not None,
        "dry_run": True,
        "zero_flow_calls": True,
        "zero_ai_tokens": True,
        "order_id": payload.get("order_id") or f"dry_{int(time.time())}",
        "order_type": payload.get("order_type") or "ROLETA_AVATAR_CENARIO",
        "tier_freshness": payload.get("tier_freshness") or "HOT_NEW",
        "dna": dna,
        "molde_resolved": molde["molde_id"] if molde else None,
        "molde_manifest_summary": {
            "idioma": molde.get("idioma"),
            "ingrediente_ancora": molde.get("ingrediente_ancora"),
            "copy_literal_do_viral": molde.get("viral_source", {}).get("copy_literal_do_viral"),
            "zero_frase_fixa_injetada": molde.get("viral_source", {}).get("zero_frase_fixa_injetada"),
            "archetype_from_viral": molde.get("roleta_arquetipo_viral", {}).get("archetype_from_viral"),
            "skill_imagem": molde.get("motor_realismo_skill", {}).get("skill_imagem"),
            "cofre_mp4_ready_count": molde.get("cofre_mp4_ready_count", 0),
        } if molde else None,
        "output_dir": out_dir,
        "next_seq_start": start_seq,
        "planned_filenames_preview": planned_files[:5],
        "planned_total": len(planned_files),
        "webhook_check": wh_res,
    }


def _processar_ordem_jit(order: dict[str, Any]) -> None:
    """Processa uma ordem JIT em background com rename atômico `.tmp.mp4` -> `.mp4` e webhook por marco."""
    global _WORKER_STATE, _ACTIVE_ORDER_ID
    oid = str(order.get("order_id") or "")
    dna = order.get("dna") or {}
    qty = max(1, int(order.get("quantity") or 20))
    out_dir = Path(order.get("output_dir") or (Path(r"C:\Hub001\VIDEOS_ESTEIRA_TREE") / dna.get("country", "US") / dna.get("niche", "WL") / dna.get("format", "F37") / dna.get("copy", "C01") / dna.get("hook", "G00")))
    webhook_url = str(order.get("webhook_done") or "")
    supply_mode = str(order.get("supply_mode") or "COFRE_STREAM_ATOMIC").upper()

    molde = resolver_molde_por_dna(dna)
    if not molde:
        _atualizar_status_ordem(oid, "FAILED", error="MOLDE_NOT_FOUND_FOR_DNA")
        return

    out_dir.mkdir(parents=True, exist_ok=True)
    _, target_names = calcular_proximos_nomes_6_blocos(dna, out_dir, qty)

    # Descobre vídeos já disponíveis no Cofre Imutável daquele formato (evita duplicar por hash/tamanho)
    cofre_dir = Path(molde.get("cofre_estoque_dir") or "")
    cofre_mp4s = sorted(cofre_dir.glob("*.mp4")) if cofre_dir.exists() else []
    existing_sizes = {p.stat().st_size for p in out_dir.glob("*.mp4") if not p.name.endswith(".tmp.mp4")}
    candidatos_ineditos = [p for p in cofre_mp4s if p.stat().st_size not in existing_sizes]

    delivered_files: list[str] = []
    # 1) Se permitido abastecer do Cofre Imutável validado (ou para destravar os primeiros 20 vídeos na hora)
    if supply_mode != "FORJA_FRESH_ONLY" and candidatos_ineditos:
        for idx, target_name in enumerate(target_names):
            if idx >= len(candidatos_ineditos):
                break
            src_mp4 = candidatos_ineditos[idx]
            tmp_dst = out_dir / (target_name + ".tmp.mp4")
            final_dst = out_dir / target_name
            shutil.copy2(src_mp4, tmp_dst)
            tmp_dst.replace(final_dst)
            delivered_files.append(str(final_dst))
            _atualizar_progresso_ordem(oid, len(delivered_files), qty, ultima_entrega=target_name)

            # Notifica webhook no marco de 20 vídeos para o Hub já postar na 1ª hora
            if len(delivered_files) == 20 and qty > 20 and webhook_url:
                _disparar_webhook(
                    webhook_url,
                    {
                        "event": "MILESTONE_20_READY",
                        "order_id": oid,
                        "order_type": order.get("order_type"),
                        "tier_freshness": order.get("tier_freshness", "HOT_NEW"),
                        "page_id": order.get("page_id"),
                        "dna": dna,
                        "delivered_count": len(delivered_files),
                        "requested_quantity": qty,
                        "output_dir": str(out_dir),
                        "files": [Path(f).name for f in delivered_files],
                    },
                )

    faltam = qty - len(delivered_files)
    # 2) Se ainda faltam vídeos e `allow_flow_spawn` estiver ativo na ordem, dispara o script_runner local em Lite LP
    if faltam > 0 and bool(order.get("allow_flow_spawn", False)):
        runner_rel = str(molde.get("script_runner") or "")
        runner_path = ROOT / runner_rel if runner_rel else None
        if runner_path and runner_path.exists():
            cmd = [sys.executable, "-u", str(runner_path), f"--lote{max(20, faltam)}", "--workers", "45"]
            subprocess.run(cmd, cwd=str(ROOT), check=False)
            # Coleta os novos MP4s do Cofre após o runner terminar
            cofre_mp4s_pos = sorted(cofre_dir.glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True) if cofre_dir.exists() else []
            for src_mp4 in cofre_mp4s_pos:
                if len(delivered_files) >= qty:
                    break
                target_name = target_names[len(delivered_files)]
                tmp_dst = out_dir / (target_name + ".tmp.mp4")
                final_dst = out_dir / target_name
                shutil.copy2(src_mp4, tmp_dst)
                tmp_dst.replace(final_dst)
                delivered_files.append(str(final_dst))
                _atualizar_progresso_ordem(oid, len(delivered_files), qty, ultima_entrega=target_name)

    status_final = "COMPLETED" if len(delivered_files) >= qty else ("PARTIAL_READY" if delivered_files else "QUEUED_WAITING_FLOW_SPAWN")
    _atualizar_status_ordem(oid, status_final, delivered_count=len(delivered_files), files=[Path(f).name for f in delivered_files])

    if webhook_url and delivered_files:
        ok_w, code_w, det_w = _disparar_webhook(
            webhook_url,
            {
                "event": "JIT_ORDER_DELIVERED",
                "order_id": oid,
                "order_type": order.get("order_type"),
                "tier_freshness": order.get("tier_freshness", "HOT_NEW"),
                "page_id": order.get("page_id"),
                "dna": dna,
                "status": status_final,
                "delivered_count": len(delivered_files),
                "requested_quantity": qty,
                "output_dir": str(out_dir),
                "files": [Path(f).name for f in delivered_files],
            },
        )
        _atualizar_webhook_ordem(oid, ok_w, code_w, det_w)


def _atualizar_progresso_ordem(order_id: str, delivered: int, total: int, ultima_entrega: str = "") -> None:
    with _JIT_LOCK:
        orders = _carregar_ordens()
        for o in orders:
            if o.get("order_id") == order_id:
                o["delivered_count"] = delivered
                o["quantity"] = total
                o["last_file"] = ultima_entrega
                o["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
                break
        _salvar_ordens(orders)


def _atualizar_status_ordem(order_id: str, status: str, delivered_count: int | None = None, files: list[str] | None = None, error: str | None = None) -> None:
    with _JIT_LOCK:
        orders = _carregar_ordens()
        for o in orders:
            if o.get("order_id") == order_id:
                o["status"] = status
                if delivered_count is not None:
                    o["delivered_count"] = delivered_count
                if files is not None:
                    o["delivered_files"] = files[-30:]
                if error:
                    o["error"] = error
                o["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
                break
        _salvar_ordens(orders)


def _atualizar_webhook_ordem(order_id: str, ok: bool, code: int, detail: str) -> None:
    with _JIT_LOCK:
        orders = _carregar_ordens()
        for o in orders:
            if o.get("order_id") == order_id:
                o["webhook_result"] = {"ok": ok, "status": code, "detail": detail}
                break
        _salvar_ordens(orders)


def _loop_worker_fila() -> None:
    global _WORKER_STATE, _ACTIVE_ORDER_ID
    while True:
        prox_ordem = None
        with _JIT_LOCK:
            orders = _carregar_ordens()
            for o in orders:
                if o.get("status") == "QUEUED":
                    o["status"] = "RUNNING"
                    o["started_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
                    prox_ordem = dict(o)
                    _ACTIVE_ORDER_ID = str(o.get("order_id"))
                    _WORKER_STATE = "RUNNING"
                    _salvar_ordens(orders)
                    break
        if prox_ordem is None:
            with _JIT_LOCK:
                _WORKER_STATE = "IDLE"
                _ACTIVE_ORDER_ID = None
            return
        try:
            _processar_ordem_jit(prox_ordem)
        except Exception as exc:
            _atualizar_status_ordem(str(prox_ordem.get("order_id")), "FAILED", error=str(exc)[:250])


def enfileirar_ordem_jit(payload: dict[str, Any]) -> dict[str, Any]:
    """Enfileira uma nova ordem JIT vinda de `POST /api/jit-order` e aciona o worker assíncrono."""
    global _WORKER_THREAD
    if bool(payload.get("dry_run", False)):
        return executar_dry_run_jit(payload)

    dna = payload.get("dna") or {}
    molde = resolver_molde_por_dna(dna)
    if not molde:
        return {"ok": False, "error": f"Nenhum molde homologado para DNA {dna}"}

    order_id = str(payload.get("order_id") or f"jit_{dna.get('country','US')}_{dna.get('format','F37')}_{int(time.time()*1000)}")
    qty = max(1, int(payload.get("quantity") or 20))
    out_dir = str(payload.get("output_dir") or (Path(r"C:\Hub001\VIDEOS_ESTEIRA_TREE") / dna.get("country", "US") / dna.get("niche", "WL") / dna.get("format", "F37") / dna.get("copy", "C01") / dna.get("hook", "G00")))
    start_seq, planned = calcular_proximos_nomes_6_blocos(dna, out_dir, qty)

    nova_ordem = {
        "order_id": order_id,
        "order_type": str(payload.get("order_type") or "ROLETA_AVATAR_CENARIO"),
        "tier_freshness": str(payload.get("tier_freshness") or "HOT_NEW"),
        "page_id": payload.get("page_id") or "",
        "quantity": qty,
        "delivered_count": 0,
        "dna": dna,
        "molde_id": molde["molde_id"],
        "output_dir": out_dir,
        "next_seq_start": start_seq,
        "planned_first_file": planned[0] if planned else "",
        "planned_last_file": planned[-1] if planned else "",
        "webhook_done": str(payload.get("webhook_done") or "http://127.0.0.1:3001/api/2fa-cockpit/jit-delivered"),
        "supply_mode": str(payload.get("supply_mode") or "COFRE_STREAM_ATOMIC"),
        "allow_flow_spawn": bool(payload.get("allow_flow_spawn", False)),
        "status": "QUEUED",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }

    with _JIT_LOCK:
        orders = _carregar_ordens()
        orders.append(nova_ordem)
        _salvar_ordens(orders)
        if _WORKER_THREAD is None or not _WORKER_THREAD.is_alive():
            _WORKER_THREAD = threading.Thread(target=_loop_worker_fila, daemon=True)
            _WORKER_THREAD.start()

    return {
        "ok": True,
        "queued": True,
        "order": nova_ordem,
    }


def obter_status_jit(contas_online: int = 5) -> dict[str, Any]:
    moldes = listar_moldes_homologados()
    orders = _carregar_ordens()
    queued_n = sum(1 for o in orders if o.get("status") in ("QUEUED", "RUNNING"))
    active_obj = next((o for o in orders if o.get("order_id") == _ACTIVE_ORDER_ID), None)

    return {
        "ok": True,
        "worker_state": _WORKER_STATE,
        "zero_token_mode": True,
        "zero_flow_credit_scale": True,
        "queue_length": queued_n,
        "total_orders_history": len(orders),
        "active_order": active_obj,
        "accounts_online": contas_online,
        "max_parallel_slots": contas_online * 27,
        "molds_registered": [
            {
                "molde_id": m["molde_id"],
                "taxonomy_6_blocos": m["taxonomy_6_blocos"],
                "idioma": m["idioma"],
                "ingrediente_ancora": m["ingrediente_ancora"],
                "archetype_from_viral": m.get("roleta_arquetipo_viral", {}).get("archetype_from_viral"),
                "copy_literal_do_viral": m.get("viral_source", {}).get("copy_literal_do_viral", True),
                "cofre_mp4_ready_count": m.get("cofre_mp4_ready_count", 0),
            }
            for m in moldes
        ],
        "recent_orders": list(reversed(orders[-10:])),
    }
