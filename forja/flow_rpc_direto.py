# -*- coding: utf-8 -*-
"""
Motor RPC Direto Multi-Contas do Google Flow via Zerum Core V1 (`forja/flow_rpc_direto.py`)
==========================================================================================
Suporta 1 ou N contas Google Flow simultâneas (`CDP :9225`, `:9226`, `:9227`, `:9228`, ...), com:
- Isolamento total de estado por conta (`_FlowEndpointState`: reload lock, semáforo WS 28 slots/conta,
  cadenciamento de disparo independente, cota diária de imagem por conta e poller coalescido por conta).
- Ponte automática de `mediaId` entre contas (`_garantir_ref_na_conta`): se um `ref_id` de matriz foi
  subido na Conta 1 (`:9225`) e o worker cair na Conta 2 (`:9226`), o arquivo original é subido e cacheado
  automaticamente na Conta 2 sem quebrar nenhum script existente!
- Roteador inteligente `escolher_conta_flow(exige_omni=...)` + contexto `usar_conta_flow(cdp_url)`:
  distribui lotes em Round-Robin entre todas as contas logadas e direciona pilotos Omni Flash para contas com créditos!
"""

from __future__ import annotations

import base64
from contextlib import contextmanager
import itertools
import json
import mimetypes
import os
from pathlib import Path
import re
import threading
import time
from typing import Any
import urllib.request as _ur

from playwright.sync_api import sync_playwright

CDP_URL_PADRAO = "http://127.0.0.1:9225"
PORTAS_SCAN_FLOW = tuple(range(9225, 9237)) + (9333, 9334, 9335, 9336, 9222, 9223)  # Suporta :9225..:9236 e workers :9333/:9334
CONTAS_JSON_PATH = Path(__file__).resolve().parent / "contas_flow.json"
EXT_DIR = Path(__file__).resolve().parent.parent / "extensao_flow_rpc"

_CDP_RPC_LOCK = threading.Lock()
_THREAD_LOCAL = threading.local()
_RR_COUNTER = itertools.count(0)


class _FlowEndpointState:
    def __init__(self, cdp_url: str) -> None:
        self.cdp_url = cdp_url.rstrip("/")
        self.reload_lock = threading.RLock()
        self.reload_event = threading.Event()
        self.reload_event.set()
        self.ultimo_reload_ts = 0.0
        self.dispatch_lock = threading.Lock()
        self.ultimo_dispatch_ts = 0.0
        self.ws_sem = threading.BoundedSemaphore(27)
        self.active_ws_count = 0
        self.img_ok_count = 0
        self.vid_ok_count = 0
        self.cooldown_until = 0.0
        self.last_event = "Pronta (27 workers)"
        self.ws_cache_lock = threading.Lock()
        self.ws_url_cached: tuple[float, str] | None = None
        self.quota_imagem_esgotada: set[str] = set()
        self.poll_cond = threading.Condition()
        self.active_video_poll_ids: set[str] = set()
        self.last_video_poll_status: dict[str, dict[str, Any]] = {}
        self.last_video_poll_ts = 0.0
        self.video_poller_busy = False
        self.ultima_limpeza_omnibox = 0.0
        self.project_url: str = ""
        self.email: str = ""
        self.creditos_cache: int | None = None
        self.consecutive_incomum: int = 0


_ENDPOINTS_LOCK = threading.Lock()
_ENDPOINTS: dict[str, _FlowEndpointState] = {}

# Rastreamento automático de qual conta gerou/subiu cada mediaId/workflowId e qual arquivo de disco deu origem a ele!
_MEDIA_LOCK = threading.Lock()
_MEDIA_OWNER_CDP: dict[str, str] = {}
_MEDIA_SOURCE_FILE: dict[str, Path] = {}
_FILE_UPLOAD_CACHE: dict[tuple[str, int, str], str] = {}

_ACTIVE_POOL_LOCK = threading.Lock()
_ACTIVE_POOL_CACHE: tuple[float, list[str]] = (0.0, [])
_LAST_TELEMETRY_DUMP_TS = 0.0
_TELEMETRY_PATH = Path(r"C:\Hub001\forja_live_telemetry.json") if Path(r"C:\Hub001").exists() else (Path(__file__).resolve().parent.parent / "lotes" / "forja_live_telemetry.json")


def _gravar_telemetria_live(force: bool = False) -> None:
    global _LAST_TELEMETRY_DUMP_TS
    agora = time.time()
    if not force and (agora - _LAST_TELEMETRY_DUMP_TS) < 0.8:
        return
    _LAST_TELEMETRY_DUMP_TS = agora
    try:
        with _ENDPOINTS_LOCK:
            eps = {
                k: {
                    "active_ws": v.active_ws_count,
                    "img_ok": v.img_ok_count,
                    "vid_ok": v.vid_ok_count,
                    "last_event": v.last_event,
                }
                for k, v in _ENDPOINTS.items()
            }
        _TELEMETRY_PATH.parent.mkdir(parents=True, exist_ok=True)
        _TELEMETRY_PATH.write_text(json.dumps({"ts": agora, "endpoints": eps}, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def _norm_cdp(cdp_url: str | None) -> str:
    return (cdp_url or CDP_URL_PADRAO).strip().rstrip("/")


def _get_ep(cdp_url: str) -> _FlowEndpointState:
    u = _norm_cdp(cdp_url)
    with _ENDPOINTS_LOCK:
        ep = _ENDPOINTS.get(u)
        if ep is None:
            ep = _FlowEndpointState(u)
            # Pré-carrega project_url salvo em contas_flow.json se existir
            for c_cfg in carregar_registro_contas_flow():
                if _norm_cdp(str(c_cfg.get("cdp_url") or "")) == u:
                    ep.project_url = str(c_cfg.get("project_url") or "")
                    ep.email = str(c_cfg.get("email") or "")
                    if c_cfg.get("ultimo_saldo_creditos") is not None:
                        try:
                            ep.creditos_cache = int(c_cfg["ultimo_saldo_creditos"])
                        except Exception:
                            pass
            if not ep.project_url and u.endswith(":9225"):
                ep.project_url = "https://flow.google.com/project/cff15a39-bcef-4bdb-bc36-c927668414c5"
            _ENDPOINTS[u] = ep
        return ep


def carregar_registro_contas_flow() -> list[dict[str, Any]]:
    if not CONTAS_JSON_PATH.exists():
        return []
    try:
        data = json.loads(CONTAS_JSON_PATH.read_text(encoding="utf-8"))
        return list(data.get("contas") or [])
    except Exception:
        return []


def salvar_registro_contas_flow(contas: list[dict[str, Any]]) -> None:
    from datetime import datetime

    CONTAS_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "atualizado_em": datetime.now().isoformat(timespec="seconds"),
        "contas": sorted(contas, key=lambda x: int(x.get("slot") or x.get("porta") or 9999)),
    }
    CONTAS_JSON_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def listar_contas_flow_ativas(forcar_scan: bool = False) -> list[str]:
    """
    Descobre em ~100ms todas as instâncias Chrome CDP ativas (`:9225..:9236` + `contas_flow.json`)
    que possuem uma aba autenticada do Google Flow (`/project/`).
    """
    global _ACTIVE_POOL_CACHE
    agora = time.time()
    with _ACTIVE_POOL_LOCK:
        if not forcar_scan and _ACTIVE_POOL_CACHE[1] and (agora - _ACTIVE_POOL_CACHE[0]) < 20.0:
            return list(_ACTIVE_POOL_CACHE[1])

    portas_cand = list(PORTAS_SCAN_FLOW)
    for c_cfg in carregar_registro_contas_flow():
        p_cfg = int(c_cfg.get("porta") or 0)
        if p_cfg and p_cfg not in portas_cand:
            portas_cand.append(p_cfg)

    ativas: list[str] = []
    seen_emails: set[str] = set()
    email_by_port = {
        int(c.get("porta") or 0): str(c.get("email") or "").strip().lower()
        for c in carregar_registro_contas_flow()
        if c.get("porta")
    }
    for porta in portas_cand:
        cdp = f"http://127.0.0.1:{porta}"
        try:
            raw = _ur.urlopen(f"{cdp}/json/list", timeout=1.2).read()
            tabs = json.loads(raw)
            flow_proj_tabs = [
                t for t in tabs
                if t.get("type") == "page" and (
                    "flow.google.com/project/" in str(t.get("url") or "")
                    or ("labs.google" in str(t.get("url") or "") and "/project/" in str(t.get("url") or ""))
                )
            ]
            if flow_proj_tabs:
                ep = _get_ep(cdp)
                em = (ep.email or email_by_port.get(porta) or "").strip().lower()
                # Evita mandar carga dobrada se a mesma conta Gmail estiver aberta em 2 portas diferentes!
                if em and em in seen_emails:
                    continue
                if em:
                    seen_emails.add(em)
                u_tab = str(flow_proj_tabs[0].get("url") or "")
                m_p = re.search(r"/project/([0-9a-fA-F-]{36})", u_tab)
                if m_p:
                    ep.project_url = f"https://flow.google.com/project/{m_p.group(1)}"
                ativas.append(cdp)
        except Exception:
            continue

    if not ativas:
        ativas = [CDP_URL_PADRAO]

    with _ACTIVE_POOL_LOCK:
        _ACTIVE_POOL_CACHE = (agora, list(ativas))
    return ativas


def escolher_conta_flow(exige_omni: bool = False, min_creditos: int = 72) -> str:
    """
    Seleciona a melhor conta ativa do pool:
    - `exige_omni=True` (Pilotos Omni Flash): prioriza conta ativa com saldo `>= min_creditos`!
    - `exige_omni=False` (Escala Low Priority 0 créditos): faz Round-Robin uniforme entre todas as contas ativas!
    """
    ativas = listar_contas_flow_ativas()
    if len(ativas) == 1:
        return ativas[0]

    if exige_omni:
        # Ordena pelas contas com maior saldo conhecido >= min_creditos
        com_saldo = []
        sem_info = []
        for u in ativas:
            ep = _get_ep(u)
            if ep.creditos_cache is None:
                sem_info.append(u)
            elif ep.creditos_cache >= min_creditos:
                com_saldo.append((ep.creditos_cache, u))
        if com_saldo:
            com_saldo.sort(reverse=True)
            idx = next(_RR_COUNTER) % len(com_saldo)
            return com_saldo[idx][1]
        if sem_info:
            return sem_info[next(_RR_COUNTER) % len(sem_info)]

    # Em modo imagem/escala, prefere contas fora de cooldown (igual broker.mjs linha 173) e com cota BELUGA+HARBOR_SEAL
    agora = time.time()
    saudaveis = [
        u for u in ativas
        if _get_ep(u).cooldown_until <= agora
        and not ({"BELUGA", "HARBOR_SEAL"}.issubset(_get_ep(u).quota_imagem_esgotada))
    ]
    if not saudaveis:
        saudaveis = [u for u in ativas if _get_ep(u).cooldown_until <= agora]
    pool = saudaveis or ativas
    return pool[next(_RR_COUNTER) % len(pool)]


@contextmanager
def usar_conta_flow(cdp_url: str | None):
    """Fixa todas as chamadas RPC da thread atual em uma conta específica durante o bloco `with`."""
    prev = getattr(_THREAD_LOCAL, "pinned_cdp_url", None)
    _THREAD_LOCAL.pinned_cdp_url = _norm_cdp(cdp_url) if cdp_url else None
    try:
        yield _THREAD_LOCAL.pinned_cdp_url
    finally:
        _THREAD_LOCAL.pinned_cdp_url = prev


def obter_conta_atual_thread() -> str | None:
    return getattr(_THREAD_LOCAL, "pinned_cdp_url", None)


def _resolver_cdp_efetivo(cdp_url: str | None, owner_hint_ids: list[str] | None = None) -> str:
    """
    Resolve para qual conta CDP enviar a chamada:
    1) Se `cdp_url` explícito != `CDP_URL_PADRAO` foi passado, respeita `cdp_url`.
    2) Se há `workflowId`s de polling em `owner_hint_ids`, usa a conta dona daquele job!
    3) Se a thread está dentro de `with usar_conta_flow(...)`, usa a conta fixada (ou faz failover se entrou em cooldown!).
    4) Caso contrário, usa `escolher_conta_flow()`.
    """
    if cdp_url and _norm_cdp(cdp_url) != CDP_URL_PADRAO:
        return _norm_cdp(cdp_url)
    if owner_hint_ids:
        with _MEDIA_LOCK:
            for hid in owner_hint_ids:
                if hid and hid in _MEDIA_OWNER_CDP:
                    return _MEDIA_OWNER_CDP[hid]
    pinned = getattr(_THREAD_LOCAL, "pinned_cdp_url", None)
    if pinned:
        if _get_ep(pinned).cooldown_until > time.time():
            nova = escolher_conta_flow(exige_omni=False)
            _THREAD_LOCAL.pinned_cdp_url = nova
            return nova
        return pinned
    return escolher_conta_flow(exige_omni=False)


def _registrar_midia_na_conta(media_ids: list[str], cdp_url: str, source_file: Path | None = None) -> None:
    u = _norm_cdp(cdp_url)
    ep = _get_ep(u)
    rp = source_file.resolve() if (source_file and source_file.exists()) else None
    with _MEDIA_LOCK:
        for mid in media_ids:
            if not mid:
                continue
            _MEDIA_OWNER_CDP[mid] = u
            _MEDIA_OWNER_CDP[f"{mid}::proj"] = ep.project_url
            if rp is not None:
                _MEDIA_SOURCE_FILE[mid] = rp


def _garantir_ref_na_conta(ref_id: str | None, target_cdp: str) -> str | None:
    """
    Mágica Multi-Conta & Multi-Projeto:
    Se `ref_id` foi gerado/subido em outra conta OU em um projeto anterior que foi rotacionado por contaminação
    (`PUBLIC_ERROR_UNUSUAL_ACTIVITY_TOO_MUCH_TRAFFIC`), re-sobe automaticamente o arquivo original de disco
    para a conta/projeto atual (com cache por `(arquivo, mtime, cdp_url, project_url)`)!
    Assim o Worker preserva o `1.mp4` já salvo em disco e continua os takes 2, 3 e 4 num projeto novo limpo!
    """
    if not ref_id:
        return ref_id
    u = _norm_cdp(target_cdp)
    ep = _get_ep(u)
    with _MEDIA_LOCK:
        owner = _MEDIA_OWNER_CDP.get(ref_id)
        owner_proj = _MEDIA_OWNER_CDP.get(f"{ref_id}::proj") or ""
        src_path = _MEDIA_SOURCE_FILE.get(ref_id)
    mesmo_proj = (not ep.project_url) or (not owner_proj) or (ep.project_url == owner_proj)
    if (owner == u and mesmo_proj) or src_path is None or not src_path.exists():
        return ref_id

    st_mtime = src_path.stat().st_mtime_ns
    cache_key = (str(src_path), st_mtime, f"{u}::{ep.project_url}")
    with _MEDIA_LOCK:
        cached_mid = _FILE_UPLOAD_CACHE.get(cache_key)
    if cached_mid:
        return cached_mid

    up = _subir_midia_direto_na_conta(src_path, u)
    if isinstance(up, dict) and up.get("ok") and up.get("mediaId"):
        new_mid = str(up["mediaId"])
        with _MEDIA_LOCK:
            _FILE_UPLOAD_CACHE[cache_key] = new_mid
            _MEDIA_OWNER_CDP[new_mid] = u
            _MEDIA_OWNER_CDP[f"{new_mid}::proj"] = ep.project_url
            _MEDIA_SOURCE_FILE[new_mid] = src_path
        return new_mid
    return ref_id


def _garantir_core_injetado(pg: Any) -> None:
    core_js = EXT_DIR / "flow-core.js"
    try:
        estado = pg.evaluate(
            """() => {
                const c = window.__zerumCandidateCoreV1;
                if (!c) return { ok: false };
                const info = c.info();
                return { ok: !!(info && info.armadilha && info.wiz), v: c.v || '', info };
            }"""
        )
        if estado and estado.get("ok"):
            if estado.get("v") != "0.5.1-ultrabatch" and core_js.exists():
                pg.evaluate(core_js.read_text(encoding="utf-8"))
            return
    except Exception:
        pass

    core_code = core_js.read_text(encoding="utf-8") if core_js.exists() else ""
    try:
        if core_code:
            pg.evaluate(core_code)
    except Exception:
        pass


def _cadenciar_disparo_nao_bloqueante(intervalo_s: float = 0.35, cdp_url: str = CDP_URL_PADRAO) -> None:
    """Espaça disparos APENAS dentro da mesma conta CDP — contas diferentes disparam 100% em paralelo!"""
    ep = _get_ep(cdp_url)
    with ep.dispatch_lock:
        agora = time.time()
        espera = (ep.ultimo_dispatch_ts + intervalo_s) - agora
        if espera > 0:
            time.sleep(espera)
        ep.ultimo_dispatch_ts = time.time()


def recarregar_aba_flow_anti_traffic(cdp_url: str = CDP_URL_PADRAO, forcar_novo_projeto: bool = False) -> bool:
    """
    Recarrega de forma limpa APENAS a conta `cdp_url` afetada por tráfego incomum, sem pausar as demais contas!
    Se `forcar_novo_projeto=True` ou se o projeto atual já acumulou >= 2 falhas `INCOMUM` seguidas ("Projeto Contaminado"),
    abre a home do Flow e cria automaticamente um Novo Projeto limpo (`/project/<NOVO_UUID>`), permitindo que
    `_garantir_ref_na_conta` re-suba o `frame_1.jpg` salvo em disco para continuar os takes 2, 3 e 4 sem perder o `1.mp4`!
    """
    import asyncio
    import websockets

    u = _norm_cdp(cdp_url)
    ep = _get_ep(u)
    ep.consecutive_incomum += 1
    criar_novo_proj = forcar_novo_projeto or (ep.consecutive_incomum >= 2)
    with ep.reload_lock:
        agora = time.time()
        if (agora - ep.ultimo_reload_ts) < 20.0:
            return False
        ep.ultimo_reload_ts = agora
        ep.reload_event.clear()
        with ep.dispatch_lock:
            ep.ultimo_dispatch_ts = max(ep.ultimo_dispatch_ts, agora + 10.5)
        try:
            time.sleep(1.5)
            tabs = json.loads(_ur.urlopen(f"{u}/json/list", timeout=3.0).read())
            flow_tabs = [
                t for t in tabs
                if t.get("type") == "page" and (
                    "flow.google.com/project/" in str(t.get("url") or "")
                    or ("labs.google" in str(t.get("url") or "") and "/project/" in str(t.get("url") or ""))
                )
            ]
            old_proj_url = (
                str(flow_tabs[0].get("url"))
                if flow_tabs
                else (ep.project_url or "https://flow.google.com/")
            )
            m_p = re.search(r"/project/([0-9a-fA-F-]{36})", old_proj_url)
            if m_p:
                old_proj_url = f"https://flow.google.com/project/{m_p.group(1)}"
                if not criar_novo_proj:
                    ep.project_url = old_proj_url

            proj_url = "https://flow.google.com/" if criar_novo_proj else old_proj_url

            req_new = _ur.Request(f"{u}/json/new?about:blank", method="PUT")
            new_t = json.loads(_ur.urlopen(req_new, timeout=5.0).read())
            ws_new = str(new_t.get("webSocketDebuggerUrl") or "")

            for old_t in flow_tabs:
                try:
                    _ur.urlopen(f"{u}/json/close/{old_t['id']}", timeout=2.0).read()
                except Exception:
                    pass
            time.sleep(0.5)

            if ws_new:
                async def _clean_and_navigate() -> None:
                    async with websockets.connect(ws_new, open_timeout=8, close_timeout=3) as ws:
                        await ws.send(json.dumps({"id": 1, "method": "Page.enable", "params": {}}))
                        for idx_o, orig in enumerate(["https://flow.google.com", "https://labs.google"]):
                            await ws.send(
                                json.dumps(
                                    {
                                        "id": 900 + idx_o,
                                        "method": "Storage.clearDataForOrigin",
                                        "params": {
                                            "origin": orig,
                                            # Preserva local_storage e indexeddb (onde vive a âncora de confiança _grecaptcha do Google!)
                                            "storageTypes": "session_storage,cache_storage,service_workers",
                                        },
                                    }
                                )
                            )
                        await asyncio.sleep(0.8)
                        trap_js = EXT_DIR / "trap-main.js"
                        if trap_js.exists():
                            await ws.send(
                                json.dumps(
                                    {
                                        "id": 2,
                                        "method": "Page.addScriptToEvaluateOnNewDocument",
                                        "params": {"source": trap_js.read_text(encoding="utf-8")},
                                    }
                                )
                            )
                        core_js = EXT_DIR / "flow-core.js"
                        if core_js.exists():
                            await ws.send(
                                json.dumps(
                                    {
                                        "id": 22,
                                        "method": "Page.addScriptToEvaluateOnNewDocument",
                                        "params": {"source": core_js.read_text(encoding="utf-8")},
                                    }
                                )
                            )
                        await ws.send(json.dumps({"id": 3, "method": "Page.navigate", "params": {"url": proj_url}}))
                        await asyncio.sleep(5.5 if criar_novo_proj else 0.6)
                        if criar_novo_proj:
                            # Clica automaticamente em "+ New Project" na home do Flow para criar um projeto 100% limpo
                            js_click_new = """(() => {
                                const btns = [...document.querySelectorAll('button, a')];
                                const b = btns.find(el => /new project|novo projeto/i.test((el.innerText || el.getAttribute('aria-label') || '')));
                                if (b) { b.click(); return 'CLICKED_NEW'; }
                                return 'NO_BTN';
                            })()"""
                            await ws.send(json.dumps({"id": 44, "method": "Runtime.evaluate", "params": {"expression": js_click_new, "returnByValue": True}}))
                            await asyncio.sleep(4.0)

                try:
                    asyncio.run(_clean_and_navigate())
                except Exception:
                    pass

            time.sleep(2.5 if criar_novo_proj else 6.5)
            try:
                tabs_after = json.loads(_ur.urlopen(f"{u}/json/list", timeout=3.0).read())
                for t_a in tabs_after:
                    u_a = str(t_a.get("url") or "")
                    m_na = re.search(r"/project/([0-9a-fA-F-]{36})", u_a)
                    if m_na:
                        ep.project_url = f"https://flow.google.com/project/{m_na.group(1)}"
                        ep.consecutive_incomum = 0
                        break
            except Exception:
                pass
            with ep.ws_cache_lock:
                ep.ws_url_cached = (time.time(), ws_new) if ws_new else None
            return True
        except Exception:
            time.sleep(3.0)
            return False
        finally:
            ep.reload_event.set()


def rotacionar_projeto_limpo_flow(cdp_url: str = CDP_URL_PADRAO) -> bool:
    """Força a criação imediata de um Novo Projeto limpo na conta `cdp_url`, preservando os `.mp4` já baixados."""
    return recarregar_aba_flow_anti_traffic(cdp_url=cdp_url, forcar_novo_projeto=True)


def _obter_ws_url_flow_cached(cdp_url: str = CDP_URL_PADRAO, force_refresh: bool = False) -> str:
    u = _norm_cdp(cdp_url)
    ep = _get_ep(u)
    agora = time.time()
    with ep.ws_cache_lock:
        if not force_refresh and ep.ws_url_cached and (agora - ep.ws_url_cached[0]) < 15.0:
            return ep.ws_url_cached[1]
        tabs = json.loads(_ur.urlopen(f"{u}/json/list", timeout=3.0).read())
        cand_ws = []
        for t in tabs:
            tu = str(t.get("url") or "")
            if t.get("type") == "page" and ("flow.google.com/project/" in tu or ("labs.google" in tu and "/project/" in tu)) and t.get("webSocketDebuggerUrl"):
                m_p = re.search(r"/project/([0-9a-fA-F-]{36})", tu)
                if m_p:
                    ep.project_url = f"https://flow.google.com/project/{m_p.group(1)}"
                cand_ws.append(str(t["webSocketDebuggerUrl"]))
        if cand_ws:
            ws_u = cand_ws[0]
            ep.ws_url_cached = (agora, ws_u)
            return ws_u
        proj_url = ep.project_url or "https://flow.google.com/"
        req_new = _ur.Request(f"{u}/json/new?{proj_url}", method="PUT")
        new_t = json.loads(_ur.urlopen(req_new, timeout=5.0).read())
        time.sleep(5.5)
        ws_u = str(new_t.get("webSocketDebuggerUrl") or "")
        if ws_u:
            ep.ws_url_cached = (time.time(), ws_u)
            return ws_u
    raise RuntimeError(f"Nenhuma aba /project/ encontrada em {u}.")


def _eval_flow_js_paralelo(js_arrow_fn: str, arg_obj: Any = None, cdp_url: str = CDP_URL_PADRAO, timeout_s: float = 180.0) -> Any:
    import asyncio
    import websockets

    u = _norm_cdp(cdp_url)
    ep = _get_ep(u)
    arg_json = json.dumps(arg_obj, ensure_ascii=False)
    core_js = EXT_DIR / "flow-core.js"
    core_code = core_js.read_text(encoding="utf-8") if core_js.exists() else ""
    expr = f"""(() => {{
        if (!window.__zerumCandidateCoreV1 && {json.dumps(bool(core_code))}) {{
            try {{ {core_code} }} catch (e) {{}}
        }}
        return ({js_arrow_fn})({arg_json});
    }})()"""

    for att in range(3):
        try:
            ep.reload_event.wait(timeout=35.0)
            ws_url = _obter_ws_url_flow_cached(u, force_refresh=(att > 0))
            with ep.ws_sem:
                ep.active_ws_count += 1
                _gravar_telemetria_live()
                try:
                    if not ep.reload_event.is_set():
                        ep.reload_event.wait(timeout=35.0)
                        ws_url = _obter_ws_url_flow_cached(u, force_refresh=True)

                    async def _run_ws(inject_first: bool = False) -> Any:
                        async with websockets.connect(
                            ws_url,
                            max_size=64 * 1024 * 1024,
                            open_timeout=15,
                            close_timeout=5,
                            ping_interval=None,
                        ) as ws:
                            if inject_first and core_js.exists():
                                inj_id = int((time.time() * 1000) % 100000000) + 1
                                await ws.send(
                                    json.dumps(
                                        {
                                            "id": inj_id,
                                            "method": "Runtime.evaluate",
                                            "params": {
                                                "expression": core_js.read_text(encoding="utf-8"),
                                                "awaitPromise": False,
                                                "returnByValue": False,
                                            },
                                        }
                                    )
                                )
                                while True:
                                    r_inj = json.loads(await asyncio.wait_for(ws.recv(), timeout=15.0))
                                    if r_inj.get("id") == inj_id:
                                        break
                            req_id = int((time.time() * 1000) % 100000000) + threading.get_ident() % 10000
                            await ws.send(
                                json.dumps(
                                    {
                                        "id": req_id,
                                        "method": "Runtime.evaluate",
                                        "params": {
                                            "expression": expr,
                                            "awaitPromise": True,
                                            "returnByValue": True,
                                        },
                                    }
                                )
                            )
                            while True:
                                raw_msg = await asyncio.wait_for(ws.recv(), timeout=timeout_s)
                                msg = json.loads(raw_msg)
                                if msg.get("id") == req_id:
                                    res_obj = (msg.get("result") or {}).get("result") or {}
                                    return res_obj.get("value")

                    val = asyncio.run(_run_ws(inject_first=False))
                    if isinstance(val, dict) and val.get("erro") == "CORE_NAO_INJETADO":
                        val = asyncio.run(_run_ws(inject_first=True))
                    if val is not None:
                        return val
                finally:
                    ep.active_ws_count = max(0, ep.active_ws_count - 1)
                    _gravar_telemetria_live()
        except Exception:
            time.sleep(0.8)
            continue
    return {"ok": False, "erro": "FALHA_WS_EVAL", "cdp_url": u}


def _obter_aba_flow(playwright_instance: Any, cdp_url: str = CDP_URL_PADRAO):
    u = _norm_cdp(cdp_url)
    ep = _get_ep(u)
    agora = time.time()
    if agora - ep.ultima_limpeza_omnibox > 120.0:
        ep.ultima_limpeza_omnibox = agora
        try:
            _tabs = json.loads(_ur.urlopen(f"{u}/json/list", timeout=1.5).read())
            for _t in _tabs:
                _u = str(_t.get("url") or "")
                if "omnibox-popup" in _u or ":8505" in _u:
                    try:
                        _ur.urlopen(f"{u}/json/close/{_t['id']}", timeout=1).read()
                    except Exception:
                        pass
        except Exception:
            pass
    browser = playwright_instance.chromium.connect_over_cdp(u, timeout=25000)
    ctx = browser.contexts[0]
    for pg in ctx.pages:
        if "flow.google.com/project/" in pg.url:
            m_p = re.search(r"/project/([0-9a-fA-F-]{36})", pg.url)
            if m_p:
                ep.project_url = f"https://flow.google.com/project/{m_p.group(1)}"
            _garantir_core_injetado(pg)
            return browser, pg
    for pg in ctx.pages:
        if "labs.google" in pg.url and "/project/" in pg.url:
            m_p = re.search(r"/project/([0-9a-fA-F-]{36})", pg.url)
            if m_p:
                ep.project_url = f"https://flow.google.com/project/{m_p.group(1)}"
                pg.goto(ep.project_url, wait_until="domcontentloaded")
                time.sleep(4.5)
            _garantir_core_injetado(pg)
            return browser, pg
    fallback_proj_url = ep.project_url or os.getenv("FLOW_PROJECT_URL", "")
    for pg in ctx.pages:
        if "flow.google.com" in pg.url or "labs.google" in pg.url:
            try:
                href_proj = pg.evaluate(
                    """() => {
                        const a = document.querySelector('a[href*="/project/"]');
                        return a ? a.href : '';
                    }"""
                )
                if href_proj and "/project/" in str(href_proj):
                    m_p = re.search(r"/project/([0-9a-fA-F-]{36})", str(href_proj))
                    target_u = f"https://flow.google.com/project/{m_p.group(1)}" if m_p else str(href_proj)
                    ep.project_url = target_u
                    pg.goto(target_u, wait_until="domcontentloaded")
                    time.sleep(4.5)
                elif fallback_proj_url:
                    pg.goto(fallback_proj_url, wait_until="domcontentloaded")
                    time.sleep(4.5)
            except Exception:
                if fallback_proj_url:
                    pg.goto(fallback_proj_url, wait_until="domcontentloaded")
                    time.sleep(4.5)
            _garantir_core_injetado(pg)
            return browser, pg
    pg0 = None
    for pg in ctx.pages:
        if pg.url in ("about:blank", "chrome://newtab/", ""):
            pg0 = pg
            break
    if pg0 is None:
        pg0 = ctx.new_page()
    pg0.goto(fallback_proj_url or "https://flow.google.com/", wait_until="domcontentloaded")
    time.sleep(4.5)
    _garantir_core_injetado(pg0)
    return browser, pg0


def ler_status_e_creditos_flow(cdp_url: str = CDP_URL_PADRAO) -> dict[str, Any]:
    u = _resolver_cdp_efetivo(cdp_url)
    ep = _get_ep(u)
    with sync_playwright() as p:
        _, pg = _obter_aba_flow(p, u)
        res = pg.evaluate(
            """async () => {
                const c = window.__zerumCandidateCoreV1;
                if (!c) return { ok: false, erro: 'CORE_NAO_INJETADO' };
                const info = c.info();
                const cred = await c.credito(info.projeto);
                const cat = await c.catalogo(info.projeto);
                const catImg = await c.catalogoImagem(info.projeto);
                return {
                    ok: true,
                    info,
                    creditos: cred.creditos,
                    modelosVideo: (cat.models || []).map(m => ({ key: m.key, displayName: m.displayName, costs: m.costs, duration: m.duration })),
                    modelosImagem: (catImg.models || []).map(m => ({ key: m.key, displayName: m.displayName }))
                };
            }"""
        )
        if isinstance(res, dict) and res.get("ok"):
            res["cdp_url"] = u
            info_d = res.get("info") or {}
            if info_d.get("email"):
                ep.email = str(info_d["email"])
            if info_d.get("projeto"):
                ep.project_url = f"https://flow.google.com/project/{info_d['projeto']}"
            if res.get("creditos") is not None:
                try:
                    ep.creditos_cache = int(res["creditos"])
                except Exception:
                    pass
        return res


def ler_status_todas_contas_flow() -> list[dict[str, Any]]:
    """Retorna o status completo e saldo de créditos de TODAS as contas Flow ativas no pool."""
    ativas = listar_contas_flow_ativas(forcar_scan=True)
    rel: list[dict[str, Any]] = []
    for u in ativas:
        try:
            with usar_conta_flow(u):
                st = ler_status_e_creditos_flow(u)
            rel.append({
                "cdp_url": u,
                "ok": bool(st.get("ok")),
                "email": (st.get("info") or {}).get("email", ""),
                "projeto": (st.get("info") or {}).get("projeto", ""),
                "creditos": st.get("creditos"),
                "armadilha": (st.get("info") or {}).get("armadilha"),
            })
        except Exception as exc:
            rel.append({"cdp_url": u, "ok": False, "erro": str(exc)})
    return rel


def _normalizar_imagem_9x16_sem_bordas(fpath: Path) -> None:
    """
    Garante que qualquer imagem (.jpg/.png) gerada pelo BELUGA (768x1376 = 24:43) ou subida como matriz
    tenha 0px de borda preta/escura nas 4 laterais e proporção exata 9:16 (720x1280), impedindo que o
    Veo 3.1 Lite adicione barras pretas verticais de 3px na esquerda e na direita!
    """
    if fpath.suffix.lower() not in (".jpg", ".jpeg", ".png") or not fpath.exists():
        return
    try:
        import cv2
        import numpy as np

        im = cv2.imread(str(fpath))
        if im is None:
            return
        h, w = im.shape[:2]
        gray = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
        t = 0
        while t < int(h * 0.18) and np.percentile(gray[t, :], 92) < 32:
            t += 1
        b = 0
        while b < int(h * 0.18) and np.percentile(gray[h - 1 - b, :], 92) < 32:
            b += 1
        l = 0
        while l < int(w * 0.18) and np.percentile(gray[:, l], 92) < 32:
            l += 1
        r = 0
        while r < int(w * 0.18) and np.percentile(gray[:, w - 1 - r], 92) < 32:
            r += 1
        if max(t, b, l, r) > 0:
            pad_x = min(l + 2, int(w * 0.20)) if l > 0 else 0
            pad_r = min(r + 2, int(w * 0.20)) if r > 0 else 0
            pad_t = min(t + 2, int(h * 0.20)) if t > 0 else 0
            pad_b = min(b + 2, int(h * 0.20)) if b > 0 else 0
            im = im[pad_t : h - pad_b, pad_x : w - pad_r]
            h, w = im.shape[:2]

        # Center-crop para proporção exata 9:16 (0.5625) caso seja 768x1376 (0.5581) ou diferente de 720x1280
        target_ratio = 9.0 / 16.0
        cur_ratio = w / float(max(1, h))
        if abs(cur_ratio - target_ratio) > 0.001 or max(t, b, l, r) > 0:
            if cur_ratio < target_ratio:
                new_h = int(round(w / target_ratio))
                y0 = max(0, (h - new_h) // 2)
                im = im[y0 : y0 + new_h, :]
            elif cur_ratio > target_ratio:
                new_w = int(round(h * target_ratio))
                x0 = max(0, (w - new_w) // 2)
                im = im[:, x0 : x0 + new_w]
            im = cv2.resize(im, (720, 1280), interpolation=cv2.INTER_LANCZOS4)
            cv2.imwrite(str(fpath), im, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
    except Exception:
        pass


def _subir_midia_direto_na_conta(fpath: Path, u: str) -> dict[str, Any]:
    _normalizar_imagem_9x16_sem_bordas(fpath)
    mime, _ = mimetypes.guess_type(str(fpath))
    mime = mime or "image/png"
    b64 = base64.b64encode(fpath.read_bytes()).decode("ascii")
    res = _eval_flow_js_paralelo(
        """async ({ b64, mime, nome }) => {
            const c = window.__zerumCandidateCoreV1;
            if (!c) return { ok: false, erro: 'CORE_NAO_INJETADO' };
            const info = c.info();
            return await c.subir(b64, mime, nome, info.projeto);
        }""",
        {"b64": b64, "mime": mime, "nome": fpath.name},
        cdp_url=u,
        timeout_s=90.0,
    )
    if isinstance(res, dict):
        res["cdp_url"] = u
        if res.get("mediaId"):
            _registrar_midia_na_conta([str(res["mediaId"])], u, source_file=fpath)
    return res


def subir_midia_rpc(caminho_arquivo: str | Path, cdp_url: str = CDP_URL_PADRAO) -> dict[str, Any]:
    fpath = Path(caminho_arquivo)
    if not fpath.exists():
        return {"ok": False, "erro": f"Arquivo não existe: {fpath}"}
    u = _resolver_cdp_efetivo(cdp_url)
    rp = fpath.resolve()
    cache_key = (str(rp), rp.stat().st_mtime_ns, u)
    with _MEDIA_LOCK:
        cached_mid = _FILE_UPLOAD_CACHE.get(cache_key)
    if cached_mid:
        return {"ok": True, "mediaId": cached_mid, "cdp_url": u, "cached": True}

    res = _subir_midia_direto_na_conta(rp, u)
    if isinstance(res, dict) and res.get("ok") and res.get("mediaId"):
        with _MEDIA_LOCK:
            _FILE_UPLOAD_CACHE[cache_key] = str(res["mediaId"])
    return res


def chamar_gemini_flow_gratis_rpc(
    prompt: str,
    sistema: str = "",
    arquivos_anexos: list[str | Path] | None = None,
    modelo: str = "gemini-3-flash-preview",
    cdp_url: str = CDP_URL_PADRAO,
) -> dict[str, Any]:
    u = _resolver_cdp_efetivo(cdp_url)
    partes = []
    for arq in arquivos_anexos or []:
        fp = Path(arq)
        if fp.exists():
            raw_bytes = fp.read_bytes()
            mime, _ = mimetypes.guess_type(str(fp))
            mime = mime or "image/jpeg"
            if mime.startswith("image/") and len(raw_bytes) > 120000:
                try:
                    import cv2
                    import numpy as np

                    arr = np.frombuffer(raw_bytes, dtype=np.uint8)
                    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                    if img is not None:
                        h, w = img.shape[:2]
                        max_dim = 1080 if len(arquivos_anexos or []) == 1 else 640
                        if max(h, w) > max_dim:
                            scale = max_dim / float(max(h, w))
                            img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
                        ok_enc, buf = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
                        if ok_enc:
                            raw_bytes = buf.tobytes()
                            mime = "image/jpeg"
                except Exception:
                    pass
            partes.append({"mime": mime, "b64": base64.b64encode(raw_bytes).decode("ascii")})
    prompt_clean = " ".join((prompt or "").splitlines()).strip()
    sistema_clean = " ".join((sistema or "").splitlines()).strip()
    return _eval_flow_js_paralelo(
        """async ({ prompt, sistema, partes, modelo }) => {
            const c = window.__zerumCandidateCoreV1;
            if (!c) return { ok: false, erro: 'CORE_NAO_INJETADO' };
            const info = c.info();
            return await c.texto({ prompt, sistema, partes, modelo, proj: info.projeto });
        }""",
        {"prompt": prompt_clean, "sistema": sistema_clean, "partes": partes, "modelo": modelo},
        cdp_url=u,
        timeout_s=90.0,
    )


def gerar_imagem_rpc(
    prompt: str,
    refs: list[str] | None = None,
    modelo: str = "BELUGA",
    aspecto: int = 2,
    cdp_url: str = CDP_URL_PADRAO,
) -> dict[str, Any]:
    u = _resolver_cdp_efetivo(cdp_url)
    ep = _get_ep(u)
    # Se esta conta já esgotou BELUGA e HARBOR_SEAL hoje, tenta migrar para outra conta saudável do pool!
    if {"BELUGA", "HARBOR_SEAL"}.issubset(ep.quota_imagem_esgotada) and cdp_url == CDP_URL_PADRAO:
        alt_u = escolher_conta_flow(exige_omni=False)
        if alt_u != u:
            u = alt_u
            ep = _get_ep(u)

    refs_local = [_garantir_ref_na_conta(r_id, u) for r_id in (refs or []) if r_id]
    ordem_candidatos = []
    for m_cand in (modelo or "BELUGA", "BELUGA", "HARBOR_SEAL", "GEM_PIX_2"):
        if m_cand not in ordem_candidatos and m_cand not in ep.quota_imagem_esgotada:
            ordem_candidatos.append(m_cand)
    if not ordem_candidatos:
        ordem_candidatos = ["BELUGA", "HARBOR_SEAL", "GEM_PIX_2"]

    res = None
    for _att_img_traffic in range(4):
        _cadenciar_disparo_nao_bloqueante(1.35, cdp_url=u)
        res = _eval_flow_js_paralelo(
            """async ({ prompt, refs, aspecto, modelos }) => {
                const c = window.__zerumCandidateCoreV1;
                if (!c) return { ok: false, erro: 'CORE_NAO_INJETADO' };
                const info = c.info();
                let ultimo = null;
                const esgotados = [];
                for (const mod of modelos) {
                    const r = await c.imagem({
                        prompt,
                        refs: refs || [],
                        aspecto: aspecto || 2,
                        modelo: mod,
                        proj: info.projeto
                    });
                    ultimo = { ...r, modeloUsado: mod, esgotados };
                    if (r && r.ok && (r.mediaId || (Array.isArray(r.cands) && r.cands.length > 0))) {
                        return ultimo;
                    }
                    if (r && (r.erro === 'INCOMUM' || r.erro === 'TRAFEGO')) {
                        break;
                    }
                    if (r && String(r.erro || '').includes('DAILY_QUOTA_REACHED')) {
                        esgotados.push(mod);
                    }
                }
                return ultimo || { ok: false, erro: 'NENHUM_MODELO_IMAGEM_ACEITO', esgotados };
            }""",
            {"prompt": prompt, "refs": refs_local, "aspecto": aspecto, "modelos": ordem_candidatos},
            cdp_url=u,
            timeout_s=180.0,
        )
        if isinstance(res, dict) and not res.get("ok") and (
            res.get("erro") == "INCOMUM"
            or "TOO_MUCH_TRAFFIC" in str(res.get("raw") or "")
            or "UNUSUAL_ACTIVITY" in str(res.get("raw") or "")
        ):
            ep.cooldown_until = time.time() + 30.0
            ep.last_event = "Cooldown anti-tráfego -> failover p/ outra conta!"
            threading.Thread(target=recarregar_aba_flow_anti_traffic, args=(u,), daemon=True).start()
            # Failover imediato para outra conta saudável do pool sem perder tempo!
            outras = [
                c_u for c_u in listar_contas_flow_ativas()
                if c_u != u and _get_ep(c_u).cooldown_until < time.time()
            ]
            if outras:
                u = outras[next(_RR_COUNTER) % len(outras)]
                ep = _get_ep(u)
                refs_local = [_garantir_ref_na_conta(r_id, u) for r_id in (refs or []) if r_id]
                time.sleep(0.5)
                continue
            time.sleep(3.0)
            continue
        break

    if isinstance(res, dict):
        res["cdp_url"] = u
        if res.get("ok"):
            ep.img_ok_count += 1
            ep.consecutive_incomum = 0
            ep.last_event = f"Imagem {res.get('modeloUsado', modelo)} OK"
        for m_esg in res.get("esgotados") or []:
            ep.quota_imagem_esgotada.add(str(m_esg))
        cands = list(res.get("cands") or res.get("candidatos") or [])
        if res.get("mediaId") and res["mediaId"] not in cands:
            cands.insert(0, res["mediaId"])
        res["cands"] = cands
        res["candidatos"] = cands
        _registrar_midia_na_conta(cands, u)
    return res


def gerar_video_rpc(
    prompt: str,
    first_frame_id: str | None = None,
    last_frame_id: str | None = None,
    refs: list[str] | None = None,
    modelo: str = "abra_i2v_8s",
    tipo: str = "i2v",
    aspecto: int = 1,
    cdp_url: str = CDP_URL_PADRAO,
) -> dict[str, Any]:
    exige_omni = bool(modelo and (modelo.startswith("macaron_cookie_") or modelo.startswith("abra_") or modelo.startswith("omni_")))
    if cdp_url == CDP_URL_PADRAO and not obter_conta_atual_thread() and exige_omni:
        u = escolher_conta_flow(exige_omni=True, min_creditos=24)
    else:
        u = _resolver_cdp_efetivo(cdp_url, owner_hint_ids=[first_frame_id or "", *((refs or [])[:1])])
    ep = _get_ep(u)

    ff_local = _garantir_ref_na_conta(first_frame_id, u) if first_frame_id else None
    lf_local = _garantir_ref_na_conta(last_frame_id, u) if last_frame_id else None
    refs_local = [_garantir_ref_na_conta(r_id, u) for r_id in (refs or []) if r_id]

    # Auto-heal tipo & modelo se o take não tiver imagem inicial (ex.: Take 4 POV Text-to-Video t2v)
    if tipo == "i2v" and not ff_local:
        tipo = "r2v" if refs_local else "t2v"

    if tipo == "i2v":
        if modelo == "veo_3_1_i2v_lite_low_priority":
            modelos_tentativa = ["veo_3_1_i2v_lite_low_priority", "veo_3_1_i2v_lite"]
        elif modelo and modelo.startswith("macaron_cookie_"):
            modelos_tentativa = [modelo]
        elif modelo and (modelo.startswith("abra_") or modelo.startswith("omni_")):
            modelos_tentativa = [modelo, "abra_i2v_8s"]
            modelos_tentativa = list(dict.fromkeys(modelos_tentativa))
        else:
            modelos_tentativa = [modelo or "veo_3_1_i2v_lite_low_priority", "veo_3_1_i2v_lite_low_priority", "veo_3_1_i2v_lite"]
            modelos_tentativa = list(dict.fromkeys(modelos_tentativa))
    elif tipo == "t2v":
        mod_t2v = (modelo or "veo_3_1_t2v_lite_low_priority").replace("_i2v_", "_t2v_")
        modelos_tentativa = list(dict.fromkeys([mod_t2v, "veo_3_1_t2v_lite_low_priority", "veo_3_1_t2v_lite"]))
    elif tipo == "r2v":
        mod_r2v = (modelo or "veo_3_1_r2v_lite_low_priority").replace("_i2v_", "_r2v_")
        modelos_tentativa = list(dict.fromkeys([mod_r2v, "veo_3_1_r2v_lite_low_priority", "veo_3_1_r2v_lite"]))
    else:
        modelos_tentativa = [modelo]

    core_js = EXT_DIR / "flow-core.js"
    core_code = core_js.read_text(encoding="utf-8") if core_js.exists() else ""

    res = None
    for _att_traffic in range(4):
        _cadenciar_disparo_nao_bloqueante(0.45, cdp_url=u)
        res = _eval_flow_js_paralelo(
            """async ({ tipo, prompt, refs, img, imgFim, modelos, aspecto, coreCode }) => {
                let c = window.__zerumCandidateCoreV1;
                if ((!c || c.v !== '0.5.1-ultrabatch') && coreCode) {
                    try { eval(coreCode); c = window.__zerumCandidateCoreV1; } catch (e) {}
                }
                if (!c) return { ok: false, erro: 'CORE_NAO_INJETADO' };
                const info = c.info();
                let ultimo = null;
                for (const mod of modelos) {
                    const r = await c.video({
                        tipo,
                        prompt,
                        refs: refs || [],
                        img: img || undefined,
                        imgFim: imgFim || undefined,
                        modelo: mod,
                        aspecto: aspecto || 1,
                        proj: info.projeto
                    });
                    ultimo = { ...r, modeloUsado: mod };
                    if (r && r.ok && Array.isArray(r.cands) && r.cands.length > 0) {
                        return ultimo;
                    }
                    if (r && (r.erro === 'INCOMUM' || r.erro === 'TRAFEGO')) {
                        break;
                    }
                }
                return ultimo || { ok: false, erro: 'NENHUM_MODELO_VIDEO_ACEITO' };
            }""",
            {
                "tipo": tipo,
                "prompt": prompt,
                "refs": refs_local,
                "img": ff_local,
                "imgFim": lf_local,
                "modelos": modelos_tentativa,
                "aspecto": aspecto,
                "coreCode": core_code,
            },
            cdp_url=u,
            timeout_s=120.0,
        )

        tem_cands = isinstance(res, dict) and res.get("ok") and bool(res.get("cands") or res.get("videoId"))
        if tem_cands:
            break

        eh_incomum = isinstance(res, dict) and (
            res.get("erro") in ("INCOMUM", "TRAFEGO")
            or "TOO_MUCH_TRAFFIC" in str(res.get("raw") or "")
            or "UNUSUAL_ACTIVITY" in str(res.get("raw") or "")
        )
        if eh_incomum:
            ep.cooldown_until = time.time() + 30.0
            ep.last_event = "Cooldown anti-tráfego -> failover p/ outra conta!"
            threading.Thread(target=recarregar_aba_flow_anti_traffic, args=(u,), daemon=True).start()
        elif _att_traffic >= 2:
            # Se falhou 2x sem candidatos na mesma conta (ex.: fila Lower Priority cheia com 3 takes ativos ou projeto travado), rotaciona!
            threading.Thread(target=recarregar_aba_flow_anti_traffic, args=(u, True), daemon=True).start()

        # Failover para outra conta saudável do pool (ou aguarda vaga na fila Lower Priority se só houver 1 conta)
        outras = [
            c_u for c_u in listar_contas_flow_ativas()
            if c_u != u and _get_ep(c_u).cooldown_until < time.time() and (not exige_omni or not c_u.endswith(":9225"))
        ]
        if outras:
            u = outras[next(_RR_COUNTER) % len(outras)]
            ep = _get_ep(u)
            ff_local = _garantir_ref_na_conta(first_frame_id, u) if first_frame_id else None
            lf_local = _garantir_ref_na_conta(last_frame_id, u) if last_frame_id else None
            refs_local = [_garantir_ref_na_conta(r_id, u) for r_id in (refs or []) if r_id]
            time.sleep(0.8)
            continue
        time.sleep(3.5)
        ff_local = _garantir_ref_na_conta(first_frame_id, u) if first_frame_id else None
        lf_local = _garantir_ref_na_conta(last_frame_id, u) if last_frame_id else None
        refs_local = [_garantir_ref_na_conta(r_id, u) for r_id in (refs or []) if r_id]

    if isinstance(res, dict):
        res["cdp_url"] = u
        if res.get("ok"):
            ep.vid_ok_count += 1
            ep.consecutive_incomum = 0
            ep.last_event = f"Vídeo {res.get('modeloUsado', modelo)} disparado OK"
        cands = list(res.get("cands") or res.get("candidatos") or [])
        if res.get("videoId") and res["videoId"] not in cands:
            cands.insert(0, res["videoId"])
        res["cands"] = cands
        res["candidatos"] = cands
        _registrar_midia_na_conta(cands, u)
    return res


def gerar_imagens_lote_rpc(
    itens: list[dict[str, Any]],
    modelo: str = "BELUGA",
    aspecto: int = 2,
    cdp_url: str = CDP_URL_PADRAO,
) -> dict[str, Any]:
    u = _resolver_cdp_efetivo(cdp_url)
    ep = _get_ep(u)
    ordem_candidatos = []
    for m_cand in (modelo or "BELUGA", "BELUGA", "HARBOR_SEAL", "GEM_PIX_2"):
        if m_cand not in ordem_candidatos and m_cand not in ep.quota_imagem_esgotada:
            ordem_candidatos.append(m_cand)
    if not ordem_candidatos:
        ordem_candidatos = ["BELUGA", "HARBOR_SEAL", "GEM_PIX_2"]

    itens_local = []
    for it in itens:
        it_c = dict(it)
        if it_c.get("refs"):
            it_c["refs"] = [_garantir_ref_na_conta(r_id, u) for r_id in it_c["refs"] if r_id]
        itens_local.append(it_c)

    core_js = EXT_DIR / "flow-core.js"
    core_code = core_js.read_text(encoding="utf-8") if core_js.exists() else ""

    res = None
    for _ in range(4):
        _cadenciar_disparo_nao_bloqueante(1.35, cdp_url=u)
        res = _eval_flow_js_paralelo(
            """async ({ itens, aspecto, modelos, coreCode }) => {
                let c = window.__zerumCandidateCoreV1;
                if (c && typeof c.imagemLote !== 'function' && coreCode) {
                    try { eval(coreCode); c = window.__zerumCandidateCoreV1; } catch (e) {}
                }
                if (!c || typeof c.imagemLote !== 'function') return { ok: false, erro: 'CORE_NAO_INJETADO' };
                const info = c.info();
                let ultimo = null;
                for (const mod of modelos) {
                    const batchIn = itens.map(it => ({
                        prompt: it.prompt,
                        refs: it.refs || [],
                        aspecto: it.aspecto || aspecto || 2,
                        modelo: it.modelo || mod
                    }));
                    const r = await c.imagemLote(batchIn, info.projeto);
                    ultimo = { ...r, modeloUsado: mod };
                    if (r && r.ok && Array.isArray(r.items) && r.items.length === itens.length) {
                        return ultimo;
                    }
                    if (r && (r.erro === 'INCOMUM' || r.erro === 'TRAFEGO')) {
                        break;
                    }
                }
                return ultimo || { ok: false, erro: 'FALHA_IMAGEM_LOTE' };
            }""",
            {"itens": itens_local, "aspecto": aspecto, "modelos": ordem_candidatos, "coreCode": core_code},
            cdp_url=u,
            timeout_s=180.0,
        )
        if isinstance(res, dict) and not res.get("ok") and (
            res.get("erro") in ("INCOMUM", "TRAFEGO")
            or "TOO_MUCH_TRAFFIC" in str(res.get("raw") or "")
            or "UNUSUAL_ACTIVITY" in str(res.get("raw") or "")
        ):
            recarregar_aba_flow_anti_traffic(u)
            time.sleep(2.0)
            continue
        break
    if isinstance(res, dict):
        res["cdp_url"] = u
        for it_r in res.get("items") or []:
            if isinstance(it_r, dict):
                it_r["cdp_url"] = u
                c_ids = list(it_r.get("cands") or ([it_r["mediaId"]] if it_r.get("mediaId") else []))
                _registrar_midia_na_conta([str(x) for x in c_ids if x], u)
    return res or {"ok": False, "erro": "FALHA_IMAGEM_LOTE", "cdp_url": u}


def _disparar_sublote_video_rpc(
    itens_sub: list[dict[str, Any]],
    modelo: str,
    aspecto: int,
    cdp_url: str,
) -> dict[str, Any]:
    hint_ids = [str(it.get("img") or it.get("first_frame_id") or "") for it in itens_sub if (it.get("img") or it.get("first_frame_id"))]
    u = _resolver_cdp_efetivo(cdp_url, owner_hint_ids=hint_ids)

    itens_local = []
    for it in itens_sub:
        it_c = dict(it)
        raw_img = it_c.get("img") or it_c.get("first_frame_id")
        if raw_img:
            it_c["img"] = _garantir_ref_na_conta(str(raw_img), u)
        itens_local.append(it_c)

    exige_omni = bool(modelo and (modelo.startswith("macaron_cookie_") or modelo.startswith("abra_") or modelo.startswith("omni_")))
    if modelo == "veo_3_1_i2v_lite_low_priority":
        modelos_tentativa = ["veo_3_1_i2v_lite_low_priority", "veo_3_1_i2v_lite"]
    elif exige_omni:
        modelos_tentativa = [modelo]
    else:
        modelos_tentativa = [modelo or "veo_3_1_i2v_lite_low_priority", "veo_3_1_i2v_lite_low_priority", "veo_3_1_i2v_lite"]
        modelos_tentativa = list(dict.fromkeys(modelos_tentativa))

    core_js = EXT_DIR / "flow-core.js"
    core_code = core_js.read_text(encoding="utf-8") if core_js.exists() else ""

    res = None
    for _ in range(4):
        _cadenciar_disparo_nao_bloqueante(1.45, cdp_url=u)
        res = _eval_flow_js_paralelo(
            """async ({ itens, aspecto, modelos, coreCode }) => {
                let c = window.__zerumCandidateCoreV1;
                if ((!c || c.v !== '0.5.1-ultrabatch' || typeof c.videoLote !== 'function') && coreCode) {
                    try { eval(coreCode); c = window.__zerumCandidateCoreV1; } catch (e) {}
                }
                if (!c || typeof c.videoLote !== 'function') return { ok: false, erro: 'CORE_NAO_INJETADO' };
                const info = c.info();
                let ultimo = null;
                for (const mod of modelos) {
                    const batchIn = itens.map(it => ({
                        prompt: it.prompt,
                        img: it.img || it.first_frame_id,
                        refs: it.refs || [],
                        modelo: it.modelo || mod,
                        aspecto: it.aspecto || aspecto || 1
                    }));
                    const r = await c.videoLote(batchIn, info.projeto);
                    ultimo = { ...r, modeloUsado: mod };
                    if (r && r.ok && Array.isArray(r.items) && r.items.length === itens.length) {
                        return ultimo;
                    }
                    if (r && (r.erro === 'INCOMUM' || r.erro === 'TRAFEGO')) break;
                }
                return ultimo || { ok: false, erro: 'FALHA_VIDEO_LOTE' };
            }""",
            {"itens": itens_local, "aspecto": aspecto, "modelos": modelos_tentativa, "coreCode": core_code},
            cdp_url=u,
            timeout_s=120.0,
        )
        if isinstance(res, dict) and not res.get("ok") and (
            res.get("erro") in ("INCOMUM", "TRAFEGO")
            or "TOO_MUCH_TRAFFIC" in str(res.get("raw") or "")
            or "UNUSUAL_ACTIVITY" in str(res.get("raw") or "")
        ):
            ep = _get_ep(u)
            ep.cooldown_until = time.time() + 30.0
            ep.last_event = "videoLote INCOMUM -> reload + failover p/ outra conta!"
            threading.Thread(target=recarregar_aba_flow_anti_traffic, args=(u,), daemon=True).start()
            outras = [
                c_u for c_u in listar_contas_flow_ativas()
                if c_u != u and _get_ep(c_u).cooldown_until < time.time() and (not exige_omni or not c_u.endswith(":9225"))
            ]
            if outras:
                u = outras[next(_RR_COUNTER) % len(outras)]
                itens_local = []
                for it in itens_sub:
                    it_c = dict(it)
                    raw_img = it_c.get("img") or it_c.get("first_frame_id")
                    if raw_img:
                        it_c["img"] = _garantir_ref_na_conta(str(raw_img), u)
                    itens_local.append(it_c)
            time.sleep(1.5)
            continue
        break

    if not isinstance(res, dict):
        res = {"ok": False, "items": [], "cdp_url": u}
    res["cdp_url"] = u
    itens_ret = list(res.get("items") or [])
    while len(itens_ret) < len(itens_sub):
        itens_ret.append({"ok": False, "cands": []})

    for idx_it, it_orig in enumerate(itens_sub):
        it_r = itens_ret[idx_it] if isinstance(itens_ret[idx_it], dict) else {"ok": False, "cands": []}
        c_ids = list(it_r.get("cands") or ([it_r["mediaId"]] if it_r.get("mediaId") else []))
        if not c_ids:
            raw_img_i = it_orig.get("img") or it_orig.get("first_frame_id")
            r_single = gerar_video_rpc(
                prompt=str(it_orig.get("prompt") or ""),
                first_frame_id=str(raw_img_i) if raw_img_i else None,
                refs=it_orig.get("refs"),
                modelo=str(it_orig.get("modelo") or modelo),
                tipo="i2v" if raw_img_i else "t2v",
                aspecto=int(it_orig.get("aspecto") or aspecto or 1),
                cdp_url=cdp_url,
            )
            c_single = list(r_single.get("cands") or [])
            it_r = {
                "ok": bool(r_single.get("ok") and c_single),
                "mediaId": c_single[0] if c_single else "",
                "cands": c_single,
                "cdp_url": r_single.get("cdp_url") or u,
            }
            itens_ret[idx_it] = it_r
        else:
            it_r["cdp_url"] = u
            _registrar_midia_na_conta([str(x) for x in c_ids if x], u)
    res["items"] = itens_ret
    res["ok"] = len(itens_ret) == len(itens_sub) and all(bool(x.get("cands")) for x in itens_ret)
    return res


def gerar_videos_lote_rpc(
    itens: list[dict[str, Any]],
    modelo: str = "veo_3_1_i2v_lite_low_priority",
    aspecto: int = 1,
    cdp_url: str = CDP_URL_PADRAO,
    max_por_pacote_rpc: int = 4,
) -> dict[str, Any]:
    """
    Suporta QUALQUER número de takes por vídeo (1, 2, 3, 4, 6, 8, 12, N takes)!
    Envia até 4 takes JUNTOS em 1 único RPC `eb1hJf` com 1 único token reCAPTCHA (`max_por_pacote_rpc=4`),
    e se o vídeo tiver mais de 4 takes (ex.: 6 ou 8 takes), fatia o excedente em blocos de até 4 takes,
    distribuindo entre as contas ativas e respeitando a janela de <= 4 tokens / 15.5s por conta!
    """
    if not itens:
        return {"ok": False, "items": [], "erro": "LOTE_VAZIO", "cdp_url": cdp_url}

    chunk_sz = max(1, int(max_por_pacote_rpc or 4))
    if len(itens) <= chunk_sz:
        return _disparar_sublote_video_rpc(itens, modelo=modelo, aspecto=aspecto, cdp_url=cdp_url)

    from concurrent.futures import ThreadPoolExecutor

    chunks: list[tuple[int, list[dict[str, Any]]]] = [
        (i, itens[i : i + chunk_sz]) for i in range(0, len(itens), chunk_sz)
    ]
    ativas = listar_contas_flow_ativas()
    resultados_por_offset: dict[int, list[dict[str, Any]]] = {}

    def _rodar_chunk(idx_chunk: int, offset: int, sub_lista: list[dict[str, Any]]) -> tuple[int, list[dict[str, Any]]]:
        # Se cdp_url é o padrão e há múltiplas contas ativas, distribui cada par de takes em Round-Robin entre as contas!
        target_u = cdp_url
        if cdp_url == CDP_URL_PADRAO and len(ativas) > 1 and not obter_conta_atual_thread():
            target_u = escolher_conta_flow(exige_omni=False)
        elif idx_chunk > 0:
            time.sleep(0.9 * idx_chunk)
        r_sub = _disparar_sublote_video_rpc(sub_lista, modelo=modelo, aspecto=aspecto, cdp_url=target_u)
        return offset, list(r_sub.get("items") or [])

    with ThreadPoolExecutor(max_workers=min(8, len(chunks))) as ex_chunks:
        futs = [
            ex_chunks.submit(_rodar_chunk, idx_c, off, sub)
            for idx_c, (off, sub) in enumerate(chunks)
        ]
        for f in futs:
            off, sub_items = f.result()
            resultados_por_offset[off] = sub_items

    todos_itens: list[dict[str, Any]] = []
    for off, _ in chunks:
        todos_itens.extend(resultados_por_offset.get(off, []))

    ok_all = len(todos_itens) == len(itens) and all(bool(x.get("cands")) for x in todos_itens)
    cdp_usado = (todos_itens[0].get("cdp_url") if todos_itens else None) or cdp_url
    return {
        "ok": ok_all,
        "items": todos_itens,
        "cdp_url": cdp_usado,
        "total_takes": len(todos_itens),
    }


def _consultar_status_video_coalescido(ids: list[str], cdp_url: str = CDP_URL_PADRAO, min_interval_s: float = 2.4) -> dict[str, Any]:
    """Coalesce isolado POR CONTA `cdp_url` — cada conta agrupa apenas os seus próprios `workflowId`s!"""
    u = _norm_cdp(cdp_url)
    ep = _get_ep(u)
    with ep.poll_cond:
        for cid in ids:
            ep.active_video_poll_ids.add(cid)

        for cid in ids:
            st_c = ep.last_video_poll_status.get(cid)
            if st_c and (st_c.get("pronto") or st_c.get("falhou")):
                return {k: ep.last_video_poll_status.get(k, {}) for k in ids}

        if ep.video_poller_busy:
            ep.poll_cond.wait(timeout=4.0)
            return {k: ep.last_video_poll_status.get(k, {}) for k in ids}

        agora = time.time()
        espera = (ep.last_video_poll_ts + min_interval_s) - agora
        if espera > 0:
            ep.poll_cond.wait(timeout=espera)
            if (time.time() - ep.last_video_poll_ts) < (min_interval_s * 0.8):
                return {k: ep.last_video_poll_status.get(k, {}) for k in ids}

        ep.video_poller_busy = True
        todos_ids = list(ep.active_video_poll_ids)

    try:
        statuses = _eval_flow_js_paralelo(
            """async ({ ids }) => {
                const c = window.__zerumCandidateCoreV1;
                if (!c) return { erro: 'CORE_NAO_INJETADO' };
                const info = c.info();
                return await c.status(ids.map(id => ({ id, tipo: 'video' })), info.projeto);
            }""",
            {"ids": todos_ids},
            cdp_url=u,
            timeout_s=45.0,
        )
    except Exception:
        statuses = {}

    with ep.poll_cond:
        ep.last_video_poll_ts = time.time()
        ep.video_poller_busy = False
        if isinstance(statuses, dict):
            for k, v in statuses.items():
                if isinstance(v, dict):
                    ep.last_video_poll_status[k] = v
                    if v.get("pronto") or v.get("falhou") or v.get("sumiu"):
                        ep.active_video_poll_ids.discard(k)
        ep.poll_cond.notify_all()
        return {k: ep.last_video_poll_status.get(k, {}) for k in ids}


def aguardar_midia_rpc(
    candidatos_ids: list[str] | dict[str, Any],
    tipo: str = "video",
    destino_arquivo: str | Path | None = None,
    timeout_s: int = 600,
    poll_interval_s: float = 4.0,
    cdp_url: str = CDP_URL_PADRAO,
) -> dict[str, Any]:
    direct_url = ""
    direct_mid = ""
    dict_cdp = ""
    if isinstance(candidatos_ids, dict):
        direct_url = str(candidatos_ids.get("url") or "")
        direct_mid = str(candidatos_ids.get("mediaId") or "")
        dict_cdp = str(candidatos_ids.get("cdp_url") or "")
        ids = [
            cid
            for cid in (candidatos_ids.get("candidatos") or candidatos_ids.get("cands") or ([direct_mid] if direct_mid else []))
            if cid
        ]
    else:
        ids = [cid for cid in (candidatos_ids or []) if cid]

    if not ids and not direct_url:
        return {"ok": False, "erro": "SEM_CANDIDATOS_UUID"}

    u = _norm_cdp(dict_cdp) if dict_cdp else _resolver_cdp_efetivo(cdp_url, owner_hint_ids=ids)
    ep = _get_ep(u)

    def _baixar_url_fora_do_lock(url_dl: str, dest: Path) -> bool:
        dest.parent.mkdir(parents=True, exist_ok=True)
        for _att_dl in range(3):
            try:
                import ssl as _ssl

                ctx_ssl = _ssl._create_unverified_context()
                req = _ur.Request(url_dl, headers={"User-Agent": "Mozilla/5.0"})
                with _ur.urlopen(req, timeout=45, context=ctx_ssl) as r_dl:
                    if r_dl.status == 200:
                        dest.write_bytes(r_dl.read())
                        if dest.exists() and dest.stat().st_size > 1000:
                            if tipo == "imagem":
                                _normalizar_imagem_9x16_sem_bordas(dest)
                            return True
            except Exception:
                pass
            try:
                dl_b64 = _eval_flow_js_paralelo(
                    """async ({ u }) => {
                        const c = window.__zerumCandidateCoreV1;
                        if (c && typeof c.baixarBase64 === 'function') return await c.baixarBase64(u);
                        return { ok: false };
                    }""",
                    {"u": url_dl},
                    cdp_url=u,
                    timeout_s=60.0,
                )
                if isinstance(dl_b64, dict) and dl_b64.get("ok") and (dl_b64.get("b64") or dl_b64.get("base64")):
                    raw_b64 = dl_b64.get("b64") or dl_b64.get("base64")
                    dest.write_bytes(base64.b64decode(raw_b64))
                    if dest.exists() and dest.stat().st_size > 1000:
                        if tipo == "imagem":
                            _normalizar_imagem_9x16_sem_bordas(dest)
                        return True
            except Exception:
                pass
        return False

    deadline = time.time() + timeout_s

    if direct_url and direct_mid:
        out: dict[str, Any] = {"ok": True, "mediaId": direct_mid, "url": direct_url, "cdp_url": u, "status": {"pronto": True}}
        if destino_arquivo:
            dest = Path(destino_arquivo)
            if _baixar_url_fora_do_lock(direct_url, dest):
                out["arquivo"] = str(dest)
                out["tamanho_bytes"] = dest.stat().st_size
                _registrar_midia_na_conta([direct_mid], u, source_file=dest)
                return out
        else:
            _registrar_midia_na_conta([direct_mid], u)
            return out

    while time.time() < deadline:
        if tipo == "video":
            statuses = _consultar_status_video_coalescido(ids, cdp_url=u, min_interval_s=min(2.5, poll_interval_s))
        else:
            statuses = _eval_flow_js_paralelo(
                """async ({ ids, tipo }) => {
                    const c = window.__zerumCandidateCoreV1;
                    if (!c) return { erro: 'CORE_NAO_INJETADO' };
                    const info = c.info();
                    return await c.status(ids.map(id => ({ id, tipo })), info.projeto);
                }""",
                {"ids": ids, "tipo": tipo},
                cdp_url=u,
                timeout_s=45.0,
            )

        for cid in ids:
            st = (statuses or {}).get(cid) or {}
            if st.get("pronto") and st.get("url"):
                with ep.poll_cond:
                    for _id_clean in ids:
                        ep.active_video_poll_ids.discard(_id_clean)
                url = st["url"]
                m_uid = re.search(r"/(?:image|video)/([0-9a-fA-F-]{36})", str(url))
                real_mid = m_uid.group(1) if m_uid else cid
                out = {"ok": True, "mediaId": real_mid, "workflowId": cid, "url": url, "cdp_url": u, "status": st}
                if destino_arquivo:
                    dest = Path(destino_arquivo)
                    if _baixar_url_fora_do_lock(url, dest):
                        out["arquivo"] = str(dest)
                        out["tamanho_bytes"] = dest.stat().st_size
                        _registrar_midia_na_conta([real_mid, cid], u, source_file=dest)
                    else:
                        return {"ok": False, "erro": "DOWNLOAD_FAILED", "url": url, "cdp_url": u}
                else:
                    _registrar_midia_na_conta([real_mid, cid], u)
                return out

        algum_falhou = ""
        algum_pendente = False
        for cid in ids:
            st = (statuses or {}).get(cid) or {}
            if st.get("falhou"):
                algum_falhou = st.get("erro") or "MIDIA_FALHOU"
            elif not st.get("sumiu"):
                algum_pendente = True
        if algum_falhou and not algum_pendente:
            with ep.poll_cond:
                for _id_clean in ids:
                    ep.active_video_poll_ids.discard(_id_clean)
            return {"ok": False, "erro": algum_falhou, "status": statuses, "cdp_url": u}
        if tipo != "video":
            time.sleep(poll_interval_s)

    return {"ok": False, "erro": "TIMEOUT_POLLING_FLOW", "candidatos": ids, "cdp_url": u}
