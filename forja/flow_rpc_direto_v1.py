# -*- coding: utf-8 -*-
"""
Motor RPC Direto do Google Flow via Zerum Core V1 (`forja/flow_rpc_direto.py`)
=============================================================================
Conecta na aba autenticada do Google Flow (`CDP :9225`) onde `trap-main.js` e
`flow-core.js` (`window.__zerumCandidateCoreV1`) já estão carregados no `MAIN` world,
permitindo executar via RPC `batchexecute` nativo (com token reCAPTCHA Enterprise
original):
- `ler_creditos_e_catalogo()` -> `nzlxg` e `HTrJv`
- `subir_midia_rpc(caminho_arquivo)` -> `maseQ` (imagem) ou `subirVideo` (MP4), retornando `mediaId` UUID em ~1s sem clicar no DOM!
- `gerar_imagem_rpc(prompt, refs, modelo)` -> `ogiZ0b` (`GEM_PIX_2`, `BELUGA`, `HARBOR_SEAL`)
- `gerar_video_rpc(prompt, first_frame_id, modelo, tipo)` -> `eb1hJf` (`i2v`), `MZZa6b` (`r2v`), `nprQif` (`interpolation`), `YhhmEf` (`t2v`)
- `aguardar_midia_rpc(candidatos_ids, tipo)` -> polling `jwpduf` + `as29s` até `pronto: true` e download da URL assinada `https://flow-content.google/...`
- `juiz_gemini_flow_rpc(prompt, sistema, partes_b64)` -> `agJzFb` (`gemini-3-flash-preview` GRÁTIS dentro do Flow!)
"""

from __future__ import annotations

import base64
import json
import mimetypes
import threading
import time
from pathlib import Path
from typing import Any
from playwright.sync_api import sync_playwright

CDP_URL_PADRAO = "http://127.0.0.1:9225"
_CDP_RPC_LOCK = threading.Lock()


EXT_DIR = Path(__file__).resolve().parent.parent / "zerum_re" / "dump_autenticado" / "extensao_zerum_instalada"


def _garantir_core_injetado(pg: Any) -> None:
    estado = pg.evaluate(
        """() => {
            const c = window.__zerumCandidateCoreV1;
            if (!c) return { ok: false };
            const info = c.info();
            return { ok: !!(info && info.armadilha && info.wiz), info };
        }"""
    )
    if estado and estado.get("ok"):
        return

    trap_js = EXT_DIR / "trap-main.js"
    core_js = EXT_DIR / "flow-core.js"
    trap_code = trap_js.read_text(encoding="utf-8") if trap_js.exists() else ""
    core_code = core_js.read_text(encoding="utf-8") if core_js.exists() else ""
    try:
        cdp = pg.context.new_cdp_session(pg)
        cdp.send("Page.enable")
        cdp.send("Page.addScriptToEvaluateOnNewDocument", {"source": trap_code + "\n;\n" + core_code})
        pg.reload(wait_until="domcontentloaded")
        pg.wait_for_timeout(3500)
    except Exception:
        if trap_code:
            pg.evaluate(trap_code)
        if core_code:
            pg.evaluate(core_code)


_ULTIMA_LIMPEZA_OMNIBOX = 0.0
_WS_CONCURRENCY_SEM = threading.BoundedSemaphore(14)
_WS_URL_CACHE: dict[str, tuple[float, str]] = {}
_WS_CACHE_LOCK = threading.Lock()


def _obter_ws_url_flow_cached(cdp_url: str = CDP_URL_PADRAO, force_refresh: bool = False) -> str:
    import urllib.request as _ur

    agora = time.time()
    with _WS_CACHE_LOCK:
        cached = _WS_URL_CACHE.get(cdp_url)
        if not force_refresh and cached and (agora - cached[0]) < 15.0:
            return cached[1]
        tabs = json.loads(_ur.urlopen(f"{cdp_url.rstrip('/')}/json/list", timeout=3.0).read())
        for t in tabs:
            u = str(t.get("url") or "")
            if ("flow.google.com/project/" in u or "/project/" in u) and t.get("webSocketDebuggerUrl"):
                ws_u = str(t["webSocketDebuggerUrl"])
                _WS_URL_CACHE[cdp_url] = (agora, ws_u)
                return ws_u
    # Se não achou aba /project/, abre via Playwright fallback
    with _CDP_RPC_LOCK:
        with sync_playwright() as p:
            _obter_aba_flow(p, cdp_url)
    with _WS_CACHE_LOCK:
        tabs = json.loads(_ur.urlopen(f"{cdp_url.rstrip('/')}/json/list", timeout=3.0).read())
        for t in tabs:
            u = str(t.get("url") or "")
            if ("flow.google.com/project/" in u or "/project/" in u) and t.get("webSocketDebuggerUrl"):
                ws_u = str(t["webSocketDebuggerUrl"])
                _WS_URL_CACHE[cdp_url] = (time.time(), ws_u)
                return ws_u
    raise RuntimeError("Nenhuma aba /project/ encontrada no Chrome CDP.")


def _eval_flow_js_paralelo(js_arrow_fn: str, arg_obj: Any = None, cdp_url: str = CDP_URL_PADRAO, timeout_s: float = 180.0) -> Any:
    """
    Executa uma função JS assíncrona no MAIN world da aba do Google Flow via WebSocket CDP direto,
    permitindo até 14 chamadas RPC 100% simultâneas sem spawnar `node.exe` e sem serializar threads!
    """
    import asyncio
    import websockets

    arg_json = json.dumps(arg_obj, ensure_ascii=False)
    expr = f"({js_arrow_fn})({arg_json})"

    for att in range(2):
        try:
            ws_url = _obter_ws_url_flow_cached(cdp_url, force_refresh=(att > 0))
            with _WS_CONCURRENCY_SEM:
                async def _run_ws() -> Any:
                    async with websockets.connect(
                        ws_url,
                        max_size=64 * 1024 * 1024,
                        open_timeout=15,
                        close_timeout=5,
                        ping_interval=None,
                    ) as ws:
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

                val = asyncio.run(_run_ws())
                if isinstance(val, dict) and val.get("erro") == "CORE_NAO_INJETADO":
                    with _CDP_RPC_LOCK:
                        with sync_playwright() as p:
                            _obter_aba_flow(p, cdp_url)
                    continue
                if val is not None:
                    return val
        except Exception:
            if att == 0:
                time.sleep(0.5)
                continue
    # Fallback final via Playwright
    with _CDP_RPC_LOCK:
        with sync_playwright() as p:
            _, pg = _obter_aba_flow(p, cdp_url)
            return pg.evaluate(js_arrow_fn, arg_obj)


def _obter_aba_flow(playwright_instance: Any, cdp_url: str = CDP_URL_PADRAO):
    global _ULTIMA_LIMPEZA_OMNIBOX
    agora = time.time()
    if agora - _ULTIMA_LIMPEZA_OMNIBOX > 120.0:
        _ULTIMA_LIMPEZA_OMNIBOX = agora
        try:
            import urllib.request as _ur
            _tabs = json.loads(_ur.urlopen(f"{cdp_url.rstrip('/')}/json/list", timeout=1.5).read())
            for _t in _tabs:
                _u = str(_t.get("url") or "")
                if "omnibox-popup" in _u or ":8505" in _u:
                    try:
                        _ur.urlopen(f"{cdp_url.rstrip('/')}/json/close/{_t['id']}", timeout=1).read()
                    except Exception:
                        pass
        except Exception:
            pass
    browser = playwright_instance.chromium.connect_over_cdp(cdp_url, timeout=25000)
    ctx = browser.contexts[0]
    for pg in ctx.pages:
        if "flow.google.com/project/" in pg.url or "/project/" in pg.url:
            _garantir_core_injetado(pg)
            return browser, pg
    for pg in ctx.pages:
        if "flow.google.com" in pg.url:
            pg.goto("https://flow.google.com/project/2d5e1b0f-1b4d-4b4a-ade7-18752f39e239", wait_until="domcontentloaded")
            time.sleep(2.5)
            _garantir_core_injetado(pg)
            return browser, pg
    raise RuntimeError("Nenhuma aba do Google Flow aberta no Chrome CDP.")


def ler_status_e_creditos_flow(cdp_url: str = CDP_URL_PADRAO) -> dict[str, Any]:
    with sync_playwright() as p:
        _, pg = _obter_aba_flow(p, cdp_url)
        return pg.evaluate(
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


def subir_midia_rpc(caminho_arquivo: str | Path, cdp_url: str = CDP_URL_PADRAO) -> dict[str, Any]:
    fpath = Path(caminho_arquivo)
    if not fpath.exists():
        return {"ok": False, "erro": f"Arquivo não existe: {fpath}"}
    mime, _ = mimetypes.guess_type(str(fpath))
    mime = mime or "image/png"
    b64 = base64.b64encode(fpath.read_bytes()).decode("ascii")

    return _eval_flow_js_paralelo(
        """async ({ b64, mime, nome }) => {
            const c = window.__zerumCandidateCoreV1;
            if (!c) return { ok: false, erro: 'CORE_NAO_INJETADO' };
            const info = c.info();
            return await c.subir(b64, mime, nome, info.projeto);
        }""",
        {"b64": b64, "mime": mime, "nome": fpath.name},
        cdp_url=cdp_url,
        timeout_s=90.0,
    )


def chamar_gemini_flow_gratis_rpc(
    prompt: str,
    sistema: str = "",
    arquivos_anexos: list[str | Path] | None = None,
    modelo: str = "gemini-3-flash-preview",
    cdp_url: str = CDP_URL_PADRAO,
) -> dict[str, Any]:
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
            partes.append(
                {
                    "mime": mime,
                    "b64": base64.b64encode(raw_bytes).decode("ascii"),
                }
            )
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
        cdp_url=cdp_url,
        timeout_s=90.0,
    )


_QUOTA_DIARIA_IMAGEM_ESGOTADA: set[str] = set()


def gerar_imagem_rpc(
    prompt: str,
    refs: list[str] | None = None,
    modelo: str = "BELUGA",
    aspecto: int = 2,
    cdp_url: str = CDP_URL_PADRAO,
) -> dict[str, Any]:
    """
    Dispara geração de imagem no Google Flow via RPC `ogiZ0b`:
    - `modelo`: 'BELUGA' (Nano Banana 2 - 0 créditos ilimitado), 'HARBOR_SEAL' (Nano Banana 2 Lite), 'GEM_PIX_2' (Nano Banana Pro)
    - `aspecto`: 2 (9:16 vertical) ou 3 (16:9 horizontal)
    """
    ordem_candidatos = []
    for m_cand in (modelo or "BELUGA", "BELUGA", "HARBOR_SEAL", "GEM_PIX_2"):
        if m_cand not in ordem_candidatos and m_cand not in _QUOTA_DIARIA_IMAGEM_ESGOTADA:
            ordem_candidatos.append(m_cand)
    if not ordem_candidatos:
        ordem_candidatos = ["BELUGA", "HARBOR_SEAL", "GEM_PIX_2"]

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
                if (r && String(r.erro || '').includes('DAILY_QUOTA_REACHED')) {
                    esgotados.push(mod);
                }
            }
            return ultimo || { ok: false, erro: 'NENHUM_MODELO_IMAGEM_ACEITO', esgotados };
        }""",
        {"prompt": prompt, "refs": refs or [], "aspecto": aspecto, "modelos": ordem_candidatos},
        cdp_url=cdp_url,
        timeout_s=180.0,
    )
    if isinstance(res, dict):
        for m_esg in res.get("esgotados") or []:
            _QUOTA_DIARIA_IMAGEM_ESGOTADA.add(str(m_esg))
        cands = list(res.get("cands") or res.get("candidatos") or [])
        if res.get("mediaId") and res["mediaId"] not in cands:
            cands.insert(0, res["mediaId"])
        res["cands"] = cands
        res["candidatos"] = cands
    return res


def gerar_video_rpc(
    prompt: str,
    first_frame_id: str | None = None,
    last_frame_id: str | None = None,
    refs: list[str] | None = None,
    modelo: str = "veo_3_1_i2v_lite_low_priority",
    tipo: str = "i2v",
    aspecto: int = 1,
    cdp_url: str = CDP_URL_PADRAO,
) -> dict[str, Any]:
    """
    Dispara geração de vídeo no Google Flow via RPC (`eb1hJf` i2v, `MZZa6b` r2v, `nprQif` interpolation, `YhhmEf` t2v).
    - `aspecto`: 1 (9:16 vertical) ou 2 (16:9 horizontal)
    - Faz resolução automática de modelo compatível com a conta (Ultra vs Pro: `veo_3_1_i2v_lite_low_priority` 0 créditos -> `veo_3_1_i2v_lite` -> `veo_3_1_i2v_s_fast_portrait_ultra` -> `veo_3_1_i2v_s_fast`).
    """
    # TRAVA ESTRITA 0 CRÉDITOS (Low Priority Only): nunca faz fallback para modelos pagos
    modelos_tentativa = ["veo_3_1_i2v_lite_low_priority"] if tipo == "i2v" else [modelo]

    res = _eval_flow_js_paralelo(
        """async ({ tipo, prompt, refs, img, imgFim, modelos, aspecto }) => {
            const c = window.__zerumCandidateCoreV1;
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
            }
            return ultimo || { ok: false, erro: 'NENHUM_MODELO_VIDEO_ACEITO' };
        }""",
        {
            "tipo": tipo,
            "prompt": prompt,
            "refs": refs or [],
            "img": first_frame_id,
            "imgFim": last_frame_id,
            "modelos": modelos_tentativa,
            "aspecto": aspecto,
        },
        cdp_url=cdp_url,
        timeout_s=120.0,
    )
    if isinstance(res, dict):
        cands = list(res.get("cands") or res.get("candidatos") or [])
        if res.get("videoId") and res["videoId"] not in cands:
            cands.insert(0, res["videoId"])
        res["cands"] = cands
        res["candidatos"] = cands
    return res


def aguardar_midia_rpc(
    candidatos_ids: list[str] | dict[str, Any],
    tipo: str = "video",
    destino_arquivo: str | Path | None = None,
    timeout_s: int = 600,
    poll_interval_s: float = 4.0,
    cdp_url: str = CDP_URL_PADRAO,
) -> dict[str, Any]:
    """
    Faz polling via `core.status` (`jwpduf` + `as29s`) dos UUIDs candidatos até `pronto == True`
    e baixa os bytes reais da URL assinada `https://flow-content.google/<tipo>/<id>` FORA do lock CDP!
    """
    direct_url = ""
    direct_mid = ""
    if isinstance(candidatos_ids, dict):
        direct_url = str(candidatos_ids.get("url") or "")
        direct_mid = str(candidatos_ids.get("mediaId") or "")
        ids = [
            cid
            for cid in (candidatos_ids.get("candidatos") or candidatos_ids.get("cands") or ([direct_mid] if direct_mid else []))
            if cid
        ]
    else:
        ids = [cid for cid in (candidatos_ids or []) if cid]

    if not ids and not direct_url:
        return {"ok": False, "erro": "SEM_CANDIDATOS_UUID"}

    def _baixar_url_fora_do_lock(url_dl: str, dest: Path) -> bool:
        dest.parent.mkdir(parents=True, exist_ok=True)
        for _att_dl in range(3):
            try:
                import urllib.request as _ureq
                req = _ureq.Request(url_dl, headers={"User-Agent": "Mozilla/5.0"})
                with _ureq.urlopen(req, timeout=45) as r_dl:
                    if r_dl.status == 200:
                        dest.write_bytes(r_dl.read())
                        if dest.exists() and dest.stat().st_size > 1000:
                            return True
            except Exception:
                pass
            try:
                with _CDP_RPC_LOCK:
                    with sync_playwright() as p:
                        _, pg = _obter_aba_flow(p, cdp_url)
                        resp = pg.context.request.get(url_dl, timeout=60000)
                        if resp.status == 200:
                            dest.write_bytes(resp.body())
                            if dest.exists() and dest.stat().st_size > 1000:
                                return True
            except Exception:
                pass
        return False

    deadline = time.time() + timeout_s

    # Atalho síncrono: se `ogiZ0b` já devolveu `url` assinada na hora, baixa direto fora do lock!
    if direct_url and direct_mid:
        out: dict[str, Any] = {"ok": True, "mediaId": direct_mid, "url": direct_url, "status": {"pronto": True}}
        if destino_arquivo:
            dest = Path(destino_arquivo)
            if _baixar_url_fora_do_lock(direct_url, dest):
                out["arquivo"] = str(dest)
                out["tamanho_bytes"] = dest.stat().st_size
                return out
        else:
            return out

    while time.time() < deadline:
        statuses = _eval_flow_js_paralelo(
            """async ({ ids, tipo }) => {
                const c = window.__zerumCandidateCoreV1;
                if (!c) return { erro: 'CORE_NAO_INJETADO' };
                const info = c.info();
                return await c.status(ids.map(id => ({ id, tipo })), info.projeto);
            }""",
            {"ids": ids, "tipo": tipo},
            cdp_url=cdp_url,
            timeout_s=45.0,
        )

        # Processa resultado e faz download HTTP 100% FORA do _CDP_RPC_LOCK!
        for cid in ids:
            st = (statuses or {}).get(cid) or {}
            if st.get("pronto") and st.get("url"):
                import re as _re
                url = st["url"]
                m_uid = _re.search(r"/(?:image|video)/([0-9a-fA-F-]{36})", str(url))
                real_mid = m_uid.group(1) if m_uid else cid
                out = {"ok": True, "mediaId": real_mid, "workflowId": cid, "url": url, "status": st}
                if destino_arquivo:
                    dest = Path(destino_arquivo)
                    if _baixar_url_fora_do_lock(url, dest):
                        out["arquivo"] = str(dest)
                        out["tamanho_bytes"] = dest.stat().st_size
                    else:
                        return {"ok": False, "erro": "DOWNLOAD_FAILED", "url": url}
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
            return {"ok": False, "erro": algum_falhou, "status": statuses}
        time.sleep(poll_interval_s)

    return {"ok": False, "erro": "TIMEOUT_POLLING_FLOW", "candidatos": ids}

