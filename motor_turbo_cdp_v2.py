#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
motor_turbo_cdp_v2.py — Versão 3.0 UltraBatch (27 Workers/Conta + Pool Multi-Contas + Anti-Unusual Activity)
=============================================================================================================
Preserva 100% a compatibilidade com `motor_turbo_cdp.py` (v1.0) e `motor_turbo_cdp_v2.py` (v2.0),
integrando diretamente o motor de alta concorrência `forja/flow_rpc_direto.py` (v3.0 UltraBatch):

1. Concorrência de 27 Workers por Conta (`BoundedSemaphore(27)`):
   - Até 27 chamadas WebSocket CDP simultâneas por conta (`:9225..:9236`), escalando linearmente
     para +100 workers quando múltiplas contas estão abertas via `gerenciar_contas_flow.py`.

2. UltraBatch 1-Token (`gerar_imagens_lote_rpc_v2` / `gerar_videos_lote_rpc_v2`):
   - Empacota múltiplas imagens (`c.imagemLote` via `ogiZ0b`) ou 3 a 9 cenas de vídeo (`c.videoLote` via `eb1hJf`)
     em 1 única requisição Protobuf assinada por 1 único token `reCAPTCHA Enterprise` (reduzindo o consumo
     de tokens em 70–85% e evitando `UNUSUAL_ACTIVITY`).

3. Poller Central Coalescido (`_consultar_status_video_coalescido` via `jwpduf`):
   - Agrupa o polling de todas as 27 threads em 1 única chamada `jwpduf` a cada 2.4s por conta
     (zero spam no endpoint `as29s`).

4. Blindagem Anti-Atividade Incomum (`Storage.clearDataForOrigin` + Failover Multi-Contas):
   - Se uma conta receber `INCOMUM` (`UNUSUAL_ACTIVITY` / `TOO_MUCH_TRAFFIC`), ela entra em cooldown de 30s,
     a requisição migra instantaneamente para outra conta saudável do pool (re-subindo referências
     automaticamente com `_garantir_ref_na_conta`), e a conta afetada limpa `local_storage, session_storage,
     indexeddb, cache_storage, service_workers` em background via CDP sem deslogar do Google.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from forja.flow_rpc_direto import (
    CDP_URL_PADRAO,
    _consultar_status_video_coalescido,
    _eval_flow_js_paralelo as eval_flow_js_paralelo,
    _garantir_ref_na_conta,
    _obter_ws_url_flow_cached,
    aguardar_midia_rpc as aguardar_midia_rpc_v2,
    escolher_conta_flow,
    gerar_imagem_rpc as gerar_imagem_rpc_v2,
    gerar_imagens_lote_rpc as gerar_imagens_lote_rpc_v2,
    gerar_video_rpc as gerar_video_rpc_v2,
    gerar_videos_lote_rpc as gerar_videos_lote_rpc_v2,
    ler_status_e_creditos_flow,
    ler_status_todas_contas_flow,
    listar_contas_flow_ativas,
    recarregar_aba_flow_anti_traffic,
    subir_midia_rpc as subir_midia_rpc_v2,
    usar_conta_flow,
)


class FlowTurboCDP:
    """Wrapper OO compatível com `motor_turbo_cdp.py` sobre o motor v3.0 UltraBatch & Multi-Contas."""

    def __init__(self, cdp_port: int = 9225):
        self.cdp_port = cdp_port
        self.cdp_url = f"http://127.0.0.1:{cdp_port}"
        try:
            self.ws_url = _obter_ws_url_flow_cached(self.cdp_url, force_refresh=True)
        except Exception:
            self.ws_url = ""

    def eval_js(self, expression: str, timeout: int = 180) -> Any:
        return eval_flow_js_paralelo(
            f"async () => ({expression})",
            None,
            cdp_url=self.cdp_url,
            timeout_s=float(timeout),
        )

    def _eval_js(self, expression: str, timeout: int = 180) -> Any:
        return self.eval_js(expression, timeout=timeout)

    def subir_imagem(self, caminho_arquivo: str | Path) -> Optional[str]:
        r = subir_midia_rpc_v2(caminho_arquivo, cdp_url=self.cdp_url)
        if isinstance(r, dict) and r.get("ok"):
            return str(r.get("mediaId") or "")
        return None

    def gerar_start_frame(
        self,
        prompt: str,
        destino_jpg: Optional[str | Path] = None,
        modelo_img: str = "BELUGA",
        refs: Optional[List[str]] = None,
    ) -> Optional[str]:
        r = gerar_imagem_rpc_v2(
            prompt=prompt,
            refs=refs,
            modelo=modelo_img,
            aspecto=2,
            cdp_url=self.cdp_url,
        )
        if isinstance(r, dict) and r.get("ok"):
            dl = aguardar_midia_rpc_v2(
                r,
                tipo="image",
                destino_arquivo=destino_jpg,
                cdp_url=r.get("cdp_url") or self.cdp_url,
            )
            return str(dl.get("mediaId") or r.get("mediaId") or "")
        return None

    def gerar_imagens_lote(
        self,
        itens: List[Dict[str, Any]],
        modelo_img: str = "BELUGA",
        aspecto: int = 2,
    ) -> Dict[str, Any]:
        """Dispara N imagens em 1 único RPC `ogiZ0b` com 1 único token reCAPTCHA Enterprise."""
        return gerar_imagens_lote_rpc_v2(
            itens=itens,
            modelo=modelo_img,
            aspecto=aspecto,
            cdp_url=self.cdp_url,
        )

    def disparar_video_veo31(
        self,
        prompt: str,
        start_frame_id: Optional[str] = None,
        modelo_video: str = "veo_3_1_i2v_lite_low_priority",
        refs: Optional[List[str]] = None,
    ) -> List[str]:
        r = gerar_video_rpc_v2(
            prompt=prompt,
            first_frame_id=start_frame_id,
            refs=refs,
            modelo=modelo_video,
            tipo="i2v",
            aspecto=1,
            cdp_url=self.cdp_url,
        )
        if isinstance(r, dict) and r.get("ok"):
            return list(r.get("cands") or [])
        return []

    def disparar_videos_lote_veo31(
        self,
        itens: List[Dict[str, Any]],
        modelo_video: str = "veo_3_1_i2v_lite_low_priority",
        aspecto: int = 1,
    ) -> Dict[str, Any]:
        """Dispara N takes de vídeo (ex.: as 3 cenas de um vídeo) em 1 único RPC `eb1hJf` com 1 único token reCAPTCHA."""
        return gerar_videos_lote_rpc_v2(
            itens=itens,
            modelo=modelo_video,
            aspecto=aspecto,
            cdp_url=self.cdp_url,
        )


__all__ = [
    "CDP_URL_PADRAO",
    "FlowTurboCDP",
    "_consultar_status_video_coalescido",
    "_garantir_ref_na_conta",
    "aguardar_midia_rpc_v2",
    "escolher_conta_flow",
    "eval_flow_js_paralelo",
    "gerar_imagem_rpc_v2",
    "gerar_imagens_lote_rpc_v2",
    "gerar_video_rpc_v2",
    "gerar_videos_lote_rpc_v2",
    "ler_status_e_creditos_flow",
    "ler_status_todas_contas_flow",
    "listar_contas_flow_ativas",
    "recarregar_aba_flow_anti_traffic",
    "subir_midia_rpc_v2",
    "usar_conta_flow",
]
