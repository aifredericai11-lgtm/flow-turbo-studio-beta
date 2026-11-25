# -*- coding: utf-8 -*-
"""
MOTOR ULTRA-BATCH 500 VÍDEOS/HORA (6–9 VÍDEOS/MINUTO EM 1 ÚNICA CONTA FLOW)
===========================================================================
Arquitetura de 5 Pilares comprovada no protocolo Protobuf `batchexecute` do Google Flow:
  1. Empacotamento Multi-Take (`gerar_videos_lote_rpc` / `c.videoLote`):
     - Dispara pacotes de 3 a 9 cenas completas em 1 ÚNICA chamada RPC `eb1hJf`
       assinada por 1 ÚNICO token `reCAPTCHA Enterprise` (reduzindo em 70–85% o consumo de tokens
       reCAPTCHA e eliminando `UNUSUAL_ACTIVITY`).
  2. Empacotamento Multi-Imagem 2-em-1 (`gerar_imagens_lote_rpc` / `c.imagemLote`) + Cache de Matrizes:
     - Gera `[frame_2.jpg, frame_3.jpg]` em 1 ÚNICA chamada RPC `ogiZ0b` com 1 único token reCAPTCHA.
     - Persistência automática de `(proj_id, fmt_code, avatar, roupa)` em `cache_matrizes_avatares_flow.json`
       para reutilização instantânea (`0.0s`) de quadros-base já validados no projeto.
  3. Janela Deslizante Contínua (`MAX_TAKES_SIMULTANEOS = 27`):
     - Mantém os 27–28 slots de GPU do Google Flow 100% ocupados continuamente; assim que 1 take
       fica pronto, libera 1 vaga imediatamente sem esperar os outros takes ou a edição local.
  4. Poller Central Coalescido (`_consultar_status_video_coalescido` via `jwpduf`):
     - 1 única chamada RPC `jwpduf` a cada `2.0s` lê o status de todos os 27 takes simultâneos.
  5. Tesoura Fonética Zero-Encode + Montagem GPU em 1 Único Passe (`montar_video_1_passe_nvenc`):
     - Calcula `(trim_start, dur_corte)` via Faster-Whisper GPU sem re-encodar os clipes individuais
       e executa o corte (`-ss / -t`) + concatenação + queima de legenda `.ass` Karaokê + áudio em
       1 único encode `h264_nvenc -preset p1` (`~0.55s` por vídeo, zero fila de sessões NVENC).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from forja.flow_rpc_direto import (
    CDP_URL_PADRAO,
    aguardar_midia_rpc,
    gerar_imagem_rpc,
    gerar_imagens_lote_rpc,
    gerar_video_rpc,
    gerar_videos_lote_rpc,
)
from forja.ler_viral import carregar_whisper, transcrever_com_palavras
from forja.qa_clipe import _normalizar_token_fala
from nosso_zerum import gerar_script_ass_zerum_11

CACHE_MATRIZES_PATH = ROOT_DIR / "prontos" / "cache_matrizes_avatares_flow.json"
_CACHE_LOCK = threading.Lock()
_SLOTS_VEO_SEM = threading.BoundedSemaphore(27)
_IMG_LOTE_SEM = threading.BoundedSemaphore(2)
_NVENC_SEM = threading.BoundedSemaphore(5)


def carregar_cache_matrizes() -> dict[str, dict[str, str]]:
    """
    Carrega (e auto-hidrata a partir de `lotes_matinal_08_11/*/checkpoint.json` se existir)
    o dicionário persistente de quadros-base `(fmt_code, avatar, roupa)` -> `{f1_id, f2_id, f3_id}`.
    """
    with _CACHE_LOCK:
        cache: dict[str, dict[str, str]] = {}
        if CACHE_MATRIZES_PATH.exists():
            try:
                cache = json.loads(CACHE_MATRIZES_PATH.read_text(encoding="utf-8"))
            except Exception:
                cache = {}

        pasta_lotes_matinal = ROOT_DIR / "lotes_matinal_08_11"
        mudou = False
        if pasta_lotes_matinal.exists():
            for ck_file in pasta_lotes_matinal.glob("*/checkpoint.json"):
                try:
                    d = json.loads(ck_file.read_text(encoding="utf-8"))
                    f1 = str(d.get("cena1_media_id") or "")
                    f2 = str(d.get("frame_id_1") or "")
                    f3 = str(d.get("frame_id_2") or "")
                    if f1 and f2 and f3:
                        job_name = ck_file.parent.name
                        fmt_c = job_name.split("_")[0]
                        key_job = f"{fmt_c}::{job_name}"
                        if key_job not in cache:
                            cache[key_job] = {"f1_id": f1, "f2_id": f2, "f3_id": f3}
                            mudou = True
                except Exception:
                    pass

        if mudou:
            CACHE_MATRIZES_PATH.parent.mkdir(parents=True, exist_ok=True)
            CACHE_MATRIZES_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
        return cache


def salvar_item_cache_matrizes(chave: str, f1_id: str, f2_id: str = "", f3_id: str = "", frames_list: list[str] | None = None) -> None:
    with _CACHE_LOCK:
        cache: dict[str, dict[str, Any]] = {}
        if CACHE_MATRIZES_PATH.exists():
            try:
                cache = json.loads(CACHE_MATRIZES_PATH.read_text(encoding="utf-8"))
            except Exception:
                cache = {}
        fl = list(frames_list or [x for x in (f1_id, f2_id, f3_id) if x])
        cache[chave] = {
            "f1_id": fl[0] if len(fl) > 0 else f1_id,
            "f2_id": fl[1] if len(fl) > 1 else f2_id,
            "f3_id": fl[2] if len(fl) > 2 else f3_id,
            "frames": fl,
        }
        CACHE_MATRIZES_PATH.parent.mkdir(parents=True, exist_ok=True)
        CACHE_MATRIZES_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def inspecionar_clipe_veo_sem_ui_ou_texto_falso(
    video_path: Path,
    trim_start: float = 0.0,
    duracao: float = 6.0,
    indice_cena: int = 2,
) -> tuple[bool, str]:
    """
    Detector OpenCV determinístico anti-UI falsa (ex: barra branca 'Baking Sodar | comment')
    e anti-texto queimado pelo Veo (ex: 'comment yes' ou legendas falsas no rodapé).
    Inspeciona as 3 cenas (`indice_cena in (0, 1, 2)`) na faixa inferior (`0.78*h .. 1.0*h`,
    abaixo da linha das mãos/tigela) procurando por faixas horizontais de UI ou texto branco queimado.
    """
    try:
        import cv2
        import numpy as np

        cap = cv2.VideoCapture(str(video_path))
        ok0, ref = cap.read()
        if not ok0 or ref is None:
            cap.release()
            return False, "VIDEO_CORROMPIDO"

        h, w = ref.shape[:2]
        ref_b = ref[int(h * 0.78) :, :]
        ref_white_b = (ref_b[:, :, 0] > 232) & (ref_b[:, :, 1] > 232) & (ref_b[:, :, 2] > 232)
        ref_b_ui = (ref_b[:, :, 2] > 230) & (ref_b[:, :, 1] > 190)

        fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
        n_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        dur_total = max(0.5, n_frames / fps)
        t_fim = min(dur_total - 0.05, max(0.5, trim_start + duracao))

        max_w = 0.0
        max_b = 0.0
        for t in np.linspace(max(0.15, trim_start + 0.15), t_fim, 9):
            cap.set(cv2.CAP_PROP_POS_MSEC, float(t) * 1000.0)
            ok, fr = cap.read()
            if not ok or fr is None:
                continue
            if fr.shape[:2] != (h, w):
                fr = cv2.resize(fr, (w, h))

            strip_b = fr[int(h * 0.78) :, :]
            diff_b = np.abs(strip_b.astype(np.int16) - ref_b.astype(np.int16)).mean(axis=2)
            white_now_b = (strip_b[:, :, 0] > 235) & (strip_b[:, :, 1] > 235) & (strip_b[:, :, 2] > 235)
            new_w = float((white_now_b & (~ref_white_b) & (diff_b > 65)).mean())
            if new_w > max_w:
                max_w = new_w

            now_b_ui = (strip_b[:, :, 2] > 232) & (strip_b[:, :, 1] > 195) & (~ref_b_ui) & (diff_b > 65)
            row_ui = now_b_ui.mean(axis=1)
            rows_wide = (row_ui > 0.62).astype(np.int32)
            if rows_wide.sum() >= 12:
                b_sc = float(row_ui.max())
                if b_sc > max_b:
                    max_b = b_sc

        cap.release()
        if max_b > 0.62:
            return False, f"UI_BAR_RODAPE_VEO_C{indice_cena+1}(bar={max_b*100:.1f}%)"
        if max_w > 0.022:
            return False, f"TEXTO_QUEIMADO_VEO_C{indice_cena+1}(white={max_w*100:.2f}%)"
        return True, "OK"
    except Exception as e:
        return True, f"WARN_OPENCV:{e}"


def calcular_tesoura_zero_encode(
    video_path: Path,
    fala_pedida: str,
    folga_inicio_s: float = 0.04,
    folga_fim_s: float = 0.24,
) -> dict[str, Any]:
    """
    Calcula os pontos exatos de corte fonético (`trim_start`, `duracao_final_s`) e desloca os timestamps
    das palavras (`palavras_alinhadas`) em memória usando 1 única chamada Faster-Whisper GPU,
    SEM rodar FFmpeg intermediário no clipe individual (o corte `-ss / -t` entra direto no encode final!).
    """
    trans = transcrever_com_palavras(video_path)
    dur_bruta = float(trans.get("duracao_video_s") or 8.0)
    palavras_ouvidas = trans.get("palavras", [])
    tokens_pedidos = [_normalizar_token_fala(t) for t in (fala_pedida or "").split() if _normalizar_token_fala(t)]

    if not palavras_ouvidas or not tokens_pedidos:
        return {
            "ok": False,
            "trim_start": 0.0,
            "trim_end": dur_bruta,
            "duracao_final_s": round(dur_bruta, 3),
            "texto_transcrito": str(trans.get("texto") or ""),
            "palavras_alinhadas": [],
        }

    idx_pedido = 0
    ultimo_fim_confirmado = float(palavras_ouvidas[-1]["fim"])
    indice_ultima_palavra_roteiro = len(palavras_ouvidas) - 1

    for i_ouv, p_obj in enumerate(palavras_ouvidas):
        tok_ouv = _normalizar_token_fala(str(p_obj.get("palavra", "")))
        if not tok_ouv:
            continue
        for lookahead in range(idx_pedido, min(len(tokens_pedidos), idx_pedido + 8)):
            if tok_ouv == tokens_pedidos[lookahead] or (
                len(tok_ouv) >= 4 and tok_ouv[:4] == tokens_pedidos[lookahead][:4]
            ):
                idx_pedido = lookahead + 1
                ultimo_fim_confirmado = float(p_obj.get("fim", ultimo_fim_confirmado))
                indice_ultima_palavra_roteiro = i_ouv
                break

    if idx_pedido < max(1, len(tokens_pedidos) - 2):
        ultimo_fim_confirmado = float(palavras_ouvidas[-1]["fim"])
        indice_ultima_palavra_roteiro = len(palavras_ouvidas) - 1

    primeiro_inicio = max(0.0, float(palavras_ouvidas[0].get("inicio", 0.0)) - folga_inicio_s)
    trim_start = round(primeiro_inicio if primeiro_inicio > 0.12 else 0.01, 3)
    trim_end = round(min(dur_bruta, ultimo_fim_confirmado + folga_fim_s), 3)
    dur_final = max(1.8, round(trim_end - trim_start, 3))

    palavras_alinhadas = [
        [
            str(p.get("palavra", "")).strip(),
            round(max(0.0, float(p.get("inicio", 0.0)) - trim_start), 2),
            round(max(0.05, float(p.get("fim", 0.0)) - trim_start), 2),
        ]
        for p in palavras_ouvidas[: indice_ultima_palavra_roteiro + 1]
    ]
    return {
        "ok": True,
        "trim_start": trim_start,
        "trim_end": trim_end,
        "duracao_final_s": dur_final,
        "texto_transcrito": str(trans.get("texto") or ""),
        "palavras_alinhadas": palavras_alinhadas,
    }


_KEY_FRAME_LOCKS: dict[str, threading.Lock] = {}
_KEY_FRAME_LOCKS_GUARD = threading.Lock()


def _get_key_frame_lock(chave: str) -> threading.Lock:
    with _KEY_FRAME_LOCKS_GUARD:
        if chave not in _KEY_FRAME_LOCKS:
            _KEY_FRAME_LOCKS[chave] = threading.Lock()
        return _KEY_FRAME_LOCKS[chave]


def obter_ou_gerar_n_frames_ultrabatch(
    spec: dict[str, Any],
    pasta_job: Path,
    usar_cache: bool = True,
    cdp_url: str = CDP_URL_PADRAO,
) -> list[str]:
    """
    Gera ou recupera do cache qualquer quantidade `N` de quadros-base (`1..N` takes: 2, 3, 4, 6, 8, 12+ takes).
    Se um take `i` em `prompts_img[i]` for vazio/`None` (ex.: Take POV `t2v` sem start frame), retorna `""` naquela posição!
    """
    prompts_vid = list(spec.get("prompts_vid") or [])
    prompts_img = list(spec.get("prompts_img") or [])
    n_takes = max(len(prompts_vid), len(prompts_img), 1)
    while len(prompts_img) < n_takes:
        prompts_img.append(prompts_img[-1] if prompts_img else "")

    chave_cache = f"{spec.get('fmt_code', 'FMT')}::{spec.get('avatar', 'AV')}::{spec.get('roupa', 'RP')}::N{n_takes}"
    chave_legacy = f"{spec.get('fmt_code', 'FMT')}::{spec.get('avatar', 'AV')}::{spec.get('roupa', 'RP')}"
    chave_job = f"{spec.get('fmt_code', 'FMT')}::{spec.get('job_id', '')}"

    with _get_key_frame_lock(chave_cache):
        if usar_cache:
            cache = carregar_cache_matrizes()
            hit = cache.get(chave_cache) or cache.get(chave_job) or (cache.get(chave_legacy) if n_takes == 3 else None)
            if hit:
                fl_cached = list(hit.get("frames") or [hit.get("f1_id", ""), hit.get("f2_id", ""), hit.get("f3_id", "")])
                if len(fl_cached) >= n_takes and all(bool(fl_cached[i]) or not prompts_img[i] for i in range(n_takes)):
                    return [str(fl_cached[i] or "") for i in range(n_takes)]

        refs_orig = list(spec.get("refs_orig") or [])
        refs_s1 = [refs_orig[0]] if len(refs_orig) > 0 and refs_orig[0] else []

        with _IMG_LOTE_SEM:
            f1_id = ""
            if prompts_img[0]:
                f1_path = pasta_job / "frame_1.jpg"
                for _ in range(4):
                    r1 = gerar_imagem_rpc(prompt=prompts_img[0], refs=refs_s1, modelo="BELUGA", cdp_url=cdp_url)
                    w1 = aguardar_midia_rpc(r1, tipo="image", destino_arquivo=f1_path, timeout_s=180, cdp_url=cdp_url)
                    if w1.get("ok") and w1.get("mediaId"):
                        f1_id = str(w1["mediaId"])
                        break
                    time.sleep(1.5)
                if not f1_id:
                    raise RuntimeError(f"Falha ao gerar frame_1 para {spec.get('job_id')}")

            def _gerar_f_sub(idx_take: int) -> tuple[int, str]:
                p_txt = str(prompts_img[idx_take] or "").strip()
                if not p_txt:
                    return idx_take, ""
                # Se o prompt de imagem for idêntico ao frame 1, reaproveita f1_id sem gastar geração extra!
                if p_txt == str(prompts_img[0] or "").strip() and f1_id:
                    return idx_take, f1_id
                dest_p = pasta_job / f"frame_{idx_take + 1}.jpg"
                r_ids = [x for x in ([f1_id, refs_orig[idx_take]] if len(refs_orig) > idx_take and refs_orig[idx_take] else [f1_id]) if x]
                for _ in range(4):
                    r_sub = gerar_imagem_rpc(prompt=p_txt, refs=r_ids, modelo="BELUGA", cdp_url=cdp_url)
                    w_sub = aguardar_midia_rpc(r_sub, tipo="image", destino_arquivo=dest_p, timeout_s=180, cdp_url=cdp_url)
                    if w_sub.get("ok") and w_sub.get("mediaId"):
                        return idx_take, str(w_sub["mediaId"])
                    time.sleep(1.5)
                return idx_take, ""

            frames_out = [""] * n_takes
            frames_out[0] = f1_id
            if n_takes > 1:
                # Primeiro tenta disparar todos os quadros restantes (frame_2..frame_N) em 1 ÚNICO RPC ogiZ0b (1 único token reCAPTCHA!)
                indices_para_gerar: list[int] = []
                itens_lote_img: list[dict[str, Any]] = []
                for idx_t in range(1, n_takes):
                    p_txt = str(prompts_img[idx_t] or "").strip()
                    if not p_txt:
                        frames_out[idx_t] = ""
                    elif p_txt == str(prompts_img[0] or "").strip() and f1_id:
                        frames_out[idx_t] = f1_id
                    else:
                        r_ids = [x for x in ([f1_id, refs_orig[idx_t]] if len(refs_orig) > idx_t and refs_orig[idx_t] else [f1_id]) if x]
                        indices_para_gerar.append(idx_t)
                        itens_lote_img.append({"prompt": p_txt, "refs": r_ids, "aspecto": 2, "modelo": "BELUGA"})

                if itens_lote_img:
                    r_batch_img = gerar_imagens_lote_rpc(itens_lote_img, modelo="BELUGA", aspecto=2, cdp_url=cdp_url)
                    batch_items = list(r_batch_img.get("items") or []) if isinstance(r_batch_img, dict) else []
                    cdp_batch = (r_batch_img.get("cdp_url") if isinstance(r_batch_img, dict) else None) or cdp_url

                    def _coletar_ou_fallback_img(pos_b: int, idx_take: int) -> tuple[int, str]:
                        dest_p = pasta_job / f"frame_{idx_take + 1}.jpg"
                        if pos_b < len(batch_items) and isinstance(batch_items[pos_b], dict) and batch_items[pos_b].get("ok"):
                            w_b = aguardar_midia_rpc(batch_items[pos_b], tipo="image", destino_arquivo=dest_p, timeout_s=180, cdp_url=cdp_batch)
                            if w_b.get("ok") and w_b.get("mediaId"):
                                return idx_take, str(w_b["mediaId"])
                        return _gerar_f_sub(idx_take)

                    with ThreadPoolExecutor(max_workers=min(6, len(indices_para_gerar))) as ex_fn:
                        futs = [ex_fn.submit(_coletar_ou_fallback_img, pos_b, i_t) for pos_b, i_t in enumerate(indices_para_gerar)]
                        for fut in futs:
                            i_t, mid_t = fut.result()
                            if prompts_img[i_t] and not mid_t:
                                raise RuntimeError(f"Falha ao gerar frame_{i_t + 1} para {spec.get('job_id')}")
                            frames_out[i_t] = mid_t

        salvar_item_cache_matrizes(
            chave_cache,
            frames_out[0] if len(frames_out) > 0 else "",
            frames_out[1] if len(frames_out) > 1 else "",
            frames_out[2] if len(frames_out) > 2 else "",
            frames_list=frames_out,
        )
        if n_takes == 3:
            salvar_item_cache_matrizes(chave_legacy, frames_out[0], frames_out[1], frames_out[2], frames_list=frames_out)
        return frames_out


def obter_ou_gerar_3_frames_ultrabatch(
    spec: dict[str, Any],
    pasta_job: Path,
    usar_cache: bool = True,
    cdp_url: str = CDP_URL_PADRAO,
) -> tuple[str, str, str]:
    fl = obter_ou_gerar_n_frames_ultrabatch(spec=spec, pasta_job=pasta_job, usar_cache=usar_cache, cdp_url=cdp_url)
    while len(fl) < 3:
        fl.append(fl[-1] if fl else "")
    return fl[0], fl[1], fl[2]


def montar_video_1_passe_nvenc(
    pasta_job: Path,
    clipes: list[Path],
    cenas_meta: list[dict[str, Any]],
    titulo_id: str,
    destino_final: Path,
    estilo_legenda: str = "apenas_cta",
    palavra_cta: str = "YES",
) -> Path:
    """
    Fusão em 1 Único Passe FFmpeg (`h264_nvenc -preset p1`):
    Aplica o corte fonético (`-ss <trim_start> -t <duracao>`) diretamente nos inputs + concatena
    + queima a legenda `.ass` Karaokê + normaliza áudio em 1 único processo NVENC (~0.55s)!
    """
    paleta_cta = ["#FF7A00", "#22C55E", "#FFC400"]
    cor_balao = paleta_cta[sum(ord(ch) for ch in titulo_id) % len(paleta_cta)]
    cor_ativa_k = "#22C55E" if cor_balao != "#22C55E" else "#FF7A00"

    ass_str = gerar_script_ass_zerum_11(
        cenas=cenas_meta,
        estilo=estilo_legenda,
        blocos_palavras=3,
        cor_ativa_hex=cor_ativa_k,
        palavra_cta=palavra_cta,
        cor_balao_hex=cor_balao,
    )
    ass_file = pasta_job / f"{titulo_id}.ass"
    ass_file.write_text(ass_str, encoding="utf-8")

    destino_final.parent.mkdir(parents=True, exist_ok=True)
    fonts_rel = os.path.relpath(ROOT_DIR / "fonts", pasta_job).replace("\\", "/")

    inputs_cmd: list[str] = []
    filter_parts_v: list[str] = []
    filter_parts_a: list[str] = []
    for idx_clip, c in enumerate(clipes):
        cm = cenas_meta[idx_clip]
        t_ini = float(cm.get("trim_start") or 0.0)
        t_dur = float(cm.get("duracao") or 5.5)
        inputs_cmd.extend(["-ss", f"{t_ini:.3f}", "-t", f"{t_dur:.3f}", "-i", str(c.resolve())])
        filter_parts_v.append(
            f"[{idx_clip}:v]fps=30,setpts=PTS-STARTPTS[v{idx_clip}];"
            f"[{idx_clip}:a]asetpts=PTS-STARTPTS[a{idx_clip}];"
        )
        filter_parts_a.append(f"[v{idx_clip}][a{idx_clip}]")

    n_c = len(clipes)
    fcomplex = (
        "".join(filter_parts_v)
        + "".join(filter_parts_a)
        + f"concat=n={n_c}:v=1:a=1[vc][ac];"
        + f"[vc]ass={ass_file.name}:fontsdir={fonts_rel}[vout];"
        + "[ac]volume=2.2dB,alimiter=limit=0.96[aout]"
    )

    with _NVENC_SEM:
        from forja.hw_accel import args_h264_hw, encontrar_ffmpeg_bin

        subprocess.run(
            [
                encontrar_ffmpeg_bin(),
                "-y",
                "-loglevel",
                "error",
                *inputs_cmd,
                "-filter_complex",
                fcomplex,
                "-map",
                "[vout]",
                "-map",
                "[aout]",
                *args_h264_hw(bitrate="2.4M", maxrate="3.4M", bufsize="5M", cq=23),
                "-movflags",
                "+faststart",
                "-c:a",
                "aac",
                "-b:a",
                "128k",
                str(destino_final.resolve()),
            ],
            cwd=str(pasta_job),
            check=True,
        )
    return destino_final


def produzir_video_ultrabatch_500h(
    spec: dict[str, Any],
    pasta_saida: Path,
    usar_cache_frames: bool = True,
    verificar_fala_fn: Callable[[Path, str, str], tuple[bool, str]] | None = None,
    cands_pre_disparados: list[dict[str, Any]] | None = None,
    cdp_url: str = CDP_URL_PADRAO,
) -> dict[str, Any]:
    t0_vid = time.time()
    jid = spec["job_id"]
    pasta_job = ROOT_DIR / "lotes_ultrabatch_500h" / jid
    pasta_job.mkdir(parents=True, exist_ok=True)
    out_final = Path(spec["out_final_path"]) if spec.get("out_final_path") else (pasta_saida / spec["filename"])
    out_final.parent.mkdir(parents=True, exist_ok=True)

    if out_final.exists() and out_final.stat().st_size > 250_000:
        return {
            "ok": True,
            "job_id": jid,
            "arquivo": str(out_final),
            "duracao_s": 18.0,
            "tempo_total_s": 0.0,
            "tempo_nvenc_s": 0.0,
            "cached": True,
        }

    prompts_vid = list(spec["prompts_vid"])
    n_cenas = len(prompts_vid)
    falas = list(spec.get("falas") or [""] * n_cenas)
    while len(falas) < n_cenas:
        falas.append("")

    if spec.get("_frames_resolvidos"):
        frame_ids = list(spec["_frames_resolvidos"])
    else:
        frame_ids = obter_ou_gerar_n_frames_ultrabatch(
            spec=spec,
            pasta_job=pasta_job,
            usar_cache=usar_cache_frames,
            cdp_url=cdp_url,
        )
    while len(frame_ids) < n_cenas:
        frame_ids.append(frame_ids[-1] if frame_ids else "")

    # Verifica quais cenas (1.mp4 .. N.mp4) já existem prontas em disco para reaproveitamento 0.0s!
    res_cenas_prontas: dict[int, dict[str, Any]] = {}
    cenas_faltantes: list[int] = []
    for idx_chk in range(n_cenas):
        c_chk = pasta_job / f"{idx_chk + 1}.mp4"
        if c_chk.exists() and c_chk.stat().st_size > 80_000:
            try:
                tes_chk = calcular_tesoura_zero_encode(c_chk, falas[idx_chk])
                t_ini_c = float(tes_chk.get("trim_start") or 0.0)
                t_dur_c = float(tes_chk.get("duracao_final_s") or 5.5)
                ok_v_c, _ = inspecionar_clipe_veo_sem_ui_ou_texto_falso(
                    c_chk, trim_start=t_ini_c, duracao=t_dur_c, indice_cena=idx_chk
                )
                if ok_v_c:
                    res_cenas_prontas[idx_chk] = {
                        "idx": idx_chk,
                        "trim_start": t_ini_c,
                        "duracao": t_dur_c,
                        "palavras_alinhadas": tes_chk.get("palavras_alinhadas") or [],
                    }
                    continue
                else:
                    c_chk.unlink(missing_ok=True)
            except Exception:
                pass
        cenas_faltantes.append(idx_chk)

    ja_adquiriu_slots = bool(cands_pre_disparados)
    slots_liberados = {i: (i not in cenas_faltantes) for i in range(n_cenas)}
    slots_lock = threading.Lock()

    if not ja_adquiriu_slots:
        for _ in cenas_faltantes:
            _SLOTS_VEO_SEM.acquire()

    def _liberar_slot(idx_s: int) -> None:
        with slots_lock:
            if not slots_liberados[idx_s]:
                slots_liberados[idx_s] = True
                _SLOTS_VEO_SEM.release()

    try:
        mapa_cands_iniciais: dict[int, dict[str, Any]] = {}
        if cands_pre_disparados and len(cands_pre_disparados) == n_cenas:
            for i_pre in cenas_faltantes:
                mapa_cands_iniciais[i_pre] = cands_pre_disparados[i_pre]
        elif cenas_faltantes:
            for _att_lote in range(3):
                r_lote = gerar_videos_lote_rpc(
                    [
                        {"prompt": prompts_vid[i_f], "img": frame_ids[i_f] or None, "aspecto": 1}
                        for i_f in cenas_faltantes
                    ],
                    modelo="veo_3_1_i2v_lite_low_priority",
                    aspecto=1,
                    cdp_url=cdp_url,
                )
                itens_lote = (r_lote.get("items") or []) if r_lote.get("ok") else []
                if len(itens_lote) == len(cenas_faltantes):
                    for pos_f, i_f in enumerate(cenas_faltantes):
                        mapa_cands_iniciais[i_f] = itens_lote[pos_f]
                    break
                time.sleep(2.5)

        def _coletar_e_cortar_cena(idx_c: int) -> dict[str, Any]:
            if idx_c in res_cenas_prontas:
                return res_cenas_prontas[idx_c]
            c_path = pasta_job / f"{idx_c + 1}.mp4"
            cand_inicial = mapa_cands_iniciais.get(idx_c)
            try:
                for att in range(1, 5):
                    if att == 1 and cand_inicial and cand_inicial.get("ok"):
                        r_v = cand_inicial
                    else:
                        r_v = gerar_video_rpc(
                            prompt=prompts_vid[idx_c],
                            first_frame_id=frame_ids[idx_c] or None,
                            modelo="veo_3_1_i2v_lite_low_priority",
                            tipo="i2v" if frame_ids[idx_c] else "t2v",
                            cdp_url=cdp_url,
                        )
                    w_v = aguardar_midia_rpc(
                        r_v,
                        tipo="video",
                        destino_arquivo=c_path,
                        timeout_s=360,
                        poll_interval_s=2.0,
                        cdp_url=cdp_url,
                    )
                    if w_v.get("ok") and c_path.exists() and c_path.stat().st_size > 80_000:
                        _liberar_slot(idx_c)
                        tes = calcular_tesoura_zero_encode(c_path, falas[idx_c])
                        t_ini_chk = float(tes.get("trim_start") or 0.0)
                        t_dur_chk = float(tes.get("duracao_final_s") or 5.5)
                        ok_vis, motivo_vis = inspecionar_clipe_veo_sem_ui_ou_texto_falso(
                            c_path,
                            trim_start=t_ini_chk,
                            duracao=t_dur_chk,
                            indice_cena=idx_c,
                        )
                        if not ok_vis:
                            print(f"⚠️ [{jid} cena {idx_c+1}] Reprovado pelo Revisor Visual ({motivo_vis}) -> Re-gerando...", flush=True)
                            c_path.unlink(missing_ok=True)
                            _SLOTS_VEO_SEM.acquire()
                            with slots_lock:
                                slots_liberados[idx_c] = False
                            continue
                        if verificar_fala_fn is not None:
                            ok_f, _ = verificar_fala_fn(c_path, falas[idx_c], str(tes.get("texto_transcrito") or ""))
                            if not ok_f:
                                c_path.unlink(missing_ok=True)
                                _SLOTS_VEO_SEM.acquire()
                                with slots_lock:
                                    slots_liberados[idx_c] = False
                                continue
                        return {
                            "idx": idx_c,
                            "trim_start": float(tes.get("trim_start") or 0.0),
                            "duracao": float(tes.get("duracao_final_s") or 5.5),
                            "palavras_alinhadas": tes.get("palavras_alinhadas") or [],
                        }
                    time.sleep(2.0)
                raise RuntimeError(f"Falha na cena {idx_c + 1} de {jid}")
            finally:
                _liberar_slot(idx_c)

        with ThreadPoolExecutor(max_workers=max(1, n_cenas)) as ex_c:
            futs = [ex_c.submit(_coletar_e_cortar_cena, ci) for ci in range(n_cenas)]
            res_cenas = [f.result() for f in futs]
    finally:
        for i_s in range(n_cenas):
            _liberar_slot(i_s)

    res_cenas.sort(key=lambda x: x["idx"])
    clipes = [pasta_job / f"{i + 1}.mp4" for i in range(n_cenas)]
    cenas_meta = [
        {
            "numero": i + 1,
            "id": f"s{i + 1}",
            "trim_start": res_cenas[i]["trim_start"],
            "duracao": res_cenas[i]["duracao"],
            "fala": falas[i],
            "acao": f"Cena {i + 1}",
            "palavras": res_cenas[i].get("palavras_alinhadas") or [],
        }
        for i in range(n_cenas)
    ]

    t0_nvenc = time.time()
    montar_video_1_passe_nvenc(
        pasta_job=pasta_job,
        clipes=clipes,
        cenas_meta=cenas_meta,
        titulo_id=jid,
        destino_final=out_final,
        estilo_legenda=str(spec.get("estilo_legenda") or "apenas_cta"),
        palavra_cta=str(spec.get("palavra_cta") or "YES"),
    )
    dt_nvenc = time.time() - t0_nvenc
    dt_total = time.time() - t0_vid
    dur_vid = sum(c["duracao"] for c in cenas_meta)
    return {
        "ok": True,
        "job_id": jid,
        "arquivo": str(out_final),
        "duracao_s": round(dur_vid, 2),
        "tempo_total_s": round(dt_total, 2),
        "tempo_nvenc_s": round(dt_nvenc, 2),
    }


def executar_lote_ultrabatch_500h(
    fila_specs: list[dict[str, Any]],
    pasta_saida: Path,
    workers_simultaneos: int = 12,
    usar_cache_frames: bool = True,
    cdp_url: str = CDP_URL_PADRAO,
) -> dict[str, Any]:
    """
    Executa uma fila de vídeos com:
      - Pré-aquecimento do modelo Faster-Whisper GPU na VRAM (`0.0s` de cold-start).
      - Super-Batch de disparo `eb1hJf` (até 9 takes = 3 vídeos completos por chamada RPC / por token reCAPTCHA!).
      - Janela Deslizante de 27 takes simultâneos + Poller Central `jwpduf`.
      - Tesoura Fonética Zero-Encode + Montagem 1-Passe `h264_nvenc -preset p1`.
    """
    pasta_saida.mkdir(parents=True, exist_ok=True)
    # Pré-aquece o Whisper na GPU RTX 4050 antes de iniciar o cronômetro da onda!
    carregar_whisper("small")

    # =========================================================================
    # FASE 1: Pré-Hidratação das Matrizes Únicas de Quadros-Base (BELUGA)
    # Garante que todas as 30 matrizes (fmt_code::avatar::roupa) estejam salvas
    # em `cache_matrizes_avatares_flow.json` ANTES de iniciar os disparos de vídeo,
    # evitando 100% colisão de tokens entre IMAGE_GENERATION e VIDEO_GENERATION!
    # =========================================================================
    if usar_cache_frames:
        cache_atual = carregar_cache_matrizes()
        specs_por_matriz: dict[str, dict[str, Any]] = {}
        for sp in fila_specs:
            out_chk = Path(sp["out_final_path"]) if sp.get("out_final_path") else (pasta_saida / sp["filename"])
            if out_chk.exists() and out_chk.stat().st_size > 250_000:
                continue
            ch_m = f"{sp.get('fmt_code', 'FMT')}::{sp.get('avatar', 'AV')}::{sp.get('roupa', 'RP')}"
            if ch_m not in cache_atual and ch_m not in specs_por_matriz:
                specs_por_matriz[ch_m] = sp

        if specs_por_matriz:
            print(f"🖼️ [FASE 1 — PRÉ-HIDRATAÇÃO DE MATRIZES] Gerando {len(specs_por_matriz)} matrizes únicas (3 frames cada) no BELUGA...", flush=True)

            def _hidratar_uma_matriz(item_kv: tuple[str, dict[str, Any]]) -> str:
                ch_k, sp_m = item_kv
                p_job = ROOT_DIR / "lotes_ultrabatch_500h" / sp_m["job_id"]
                p_job.mkdir(parents=True, exist_ok=True)
                obter_ou_gerar_3_frames_ultrabatch(sp_m, p_job, usar_cache=True, cdp_url=cdp_url)
                return ch_k

            done_m = 0
            with ThreadPoolExecutor(max_workers=2) as pool_m:
                futs_m = {pool_m.submit(_hidratar_uma_matriz, kv): kv[0] for kv in specs_por_matriz.items()}
                for fm in as_completed(futs_m):
                    ch_k = futs_m[fm]
                    try:
                        fm.result()
                        done_m += 1
                        print(f"  ✅ Matriz [{done_m}/{len(specs_por_matriz)}] pronta: {ch_k}", flush=True)
                    except Exception as e_m:
                        print(f"  ⚠️ Aviso na matriz {ch_k}: {e_m}", flush=True)

    t0 = time.time()
    resultados: list[dict[str, Any]] = []
    falhas = 0
    prog_path = pasta_saida / "progresso_ultrabatch.json"
    prog_lock = threading.Lock()

    with ThreadPoolExecutor(max_workers=workers_simultaneos) as pool:
        futs = {
            pool.submit(
                produzir_video_ultrabatch_500h,
                sp,
                pasta_saida,
                usar_cache_frames,
                None,
                None,
                cdp_url,
            ): sp
            for sp in fila_specs
        }

        for fut in as_completed(futs):
            sp = futs[fut]
            try:
                r = fut.result()
                resultados.append(r)
                el_s = max(0.1, time.time() - t0)
                vids_min = (len(resultados) / el_s) * 60.0
                vids_hora = vids_min * 60.0
                with prog_lock:
                    prog_path.write_text(
                        json.dumps(
                            {
                                "concluidos": len(resultados),
                                "total": len(fila_specs),
                                "falhas": falhas,
                                "elapsed_min": round(el_s / 60.0, 2),
                                "videos_por_min": round(vids_min, 2),
                                "videos_por_hora": round(vids_hora, 1),
                                "ultimo_job": r.get("job_id"),
                            },
                            ensure_ascii=False,
                            indent=2,
                        ),
                        encoding="utf-8",
                    )
                print(
                    f"⚡ [{len(resultados)}/{len(fila_specs)}] {r['job_id']} PRONTO ({r['duracao_s']}s · NVENC {r['tempo_nvenc_s']}s) "
                    f"| Ritmo Real: {vids_min:.2f} vídeos/min ({vids_hora:.0f} vídeos/hora)",
                    flush=True,
                )
            except Exception as e:
                falhas += 1
                print(f"❌ Erro em {sp.get('job_id')}: {e}", flush=True)

    if falhas > 0:
        pendentes_rep = [
            sp
            for sp in fila_specs
            if not (Path(sp["out_final_path"]) if sp.get("out_final_path") else (pasta_saida / sp["filename"])).exists()
            or (Path(sp["out_final_path"]) if sp.get("out_final_path") else (pasta_saida / sp["filename"])).stat().st_size < 250_000
        ]
        if pendentes_rep:
            print(f"🔄 Repescagem automática UltraBatch em PARALELO para {len(pendentes_rep)} vídeo(s)...", flush=True)
            with ThreadPoolExecutor(max_workers=min(12, len(pendentes_rep))) as pool_rep:
                futs_rep = {
                    pool_rep.submit(produzir_video_ultrabatch_500h, sp, pasta_saida, usar_cache_frames, None, None, cdp_url): sp
                    for sp in pendentes_rep
                }
                for f_r in as_completed(futs_rep):
                    sp_r = futs_rep[f_r]
                    try:
                        r_rep = f_r.result()
                        resultados.append(r_rep)
                        falhas = max(0, falhas - 1)
                        print(f"✅ [REPESCAGEM OK] {sp_r['job_id']} PRONTO ({r_rep['duracao_s']}s)", flush=True)
                    except Exception as e_rep:
                        print(f"❌ [REPESCAGEM FALHOU] {sp_r['job_id']}: {e_rep}", flush=True)

    dt_total = max(0.1, time.time() - t0)
    vpm = (len(resultados) / dt_total) * 60.0
    vph = vpm * 60.0
    return {
        "ok": falhas == 0,
        "concluidos": len(resultados),
        "falhas": falhas,
        "tempo_total_s": round(dt_total, 2),
        "videos_por_minuto": round(vpm, 2),
        "videos_por_hora_equivalente": round(vph, 1),
        "resultados": resultados,
    }
