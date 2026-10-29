"""
Forja — Motor Turbo de Lote em Ondas Paralelas (forja/turbo_lote.py).
Meta de Alta Escala (100 variações em ~91 min em 1 conta ULTRA / ~45 min em 2 contas ULTRA):
- Macro-Ondas de 5 vídeos (5 Frames Base Nano Banana 2.1 + 15 Takes Veo 3.1 - Lite = 20 cards exatos por projeto).
- Recicla o projeto ('Novo projeto' em https://labs.google/fx/pt/tools/flow) ao fim de cada Macro-Onda para evitar virtualização do DOM (>20 cards).
- Reutiliza 1 único Frame Base por personagem na galeria interna do projeto para os 3 takes, variando o ângulo via prompt.
- Baixa todos os 15 vídeos da onda em paralelo (ThreadPoolExecutor max_workers=16) via URL direta =mm,22,15 com cookies da sessão.
- Executa QA por clipe em paralelo (16 threads) e Edição Vigia GPU em background enquanto a próxima Macro-Onda já inicia no Flow.
"""

from __future__ import annotations

import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any

from forja.compilador_realismo_zerum import enriquecer_item_video_zerum
from forja.estrutura import ROOT_DIR, BatchLogger, FlowSafetyGuard
from forja.fila_runner import entregar_video_aprovado
from forja.geracao_flow import CacheVideoForja, ControladorFlowPlaywright
from forja.qa_clipe import avaliar_qa_clipe, mover_para_reprovados, tesoura_cirurgica_3_passes
from forja.seletores_flow import SELETORES_FLOW

from contextlib import contextmanager
import msvcrt
import os

MAX_FRAMES_SIMULTANEOS = 5
MAX_VIDEOS_SIMULTANEOS = 15


@contextmanager
def _lock_ui_flow(ctrl: ControladorFlowPlaywright):
    """
    Cada Conta Ultra roda em sua própria janela/perfil independente do Chrome (Default e Profile 3).
    Zero troca de aba (sem bring_to_front) e zero bloqueio entre os 2 Chromes!
    """
    yield


def _converter_para_url_mp4_direta(url_card: str) -> str:
    """Converte a URL da mídia/thumbnail do card do Flow no stream binário MP4 direto (=mm,22,15)."""
    if "=mm," in url_card:
        return url_card
    if "aisandbox-pa.googleapis.com" in url_card:
        return re.sub(r"=[a-zA-Z0-9_,-]+$", "", url_card) + "=mm,22,15"
    return f"{url_card}=mm,22,15"


def obter_lista_ordenada_urls_imagens(ctrl: ControladorFlowPlaywright) -> list[str]:
    """Retorna a lista de URLs de imagens da grade na ordem exata do DOM (mais recente no índice 0)."""
    urls: list[str] = []
    vistos: set[str] = set()
    for sel in SELETORES_FLOW["imagens_geradas"]:
        try:
            encontradas = ctrl.page.locator(sel).evaluate_all("els => els.map(e => e.currentSrc || e.src || '')")
            for u in encontradas:
                if (
                    u
                    and (
                        "/asb/" in u
                        or "flow-content.google" in u
                        or "aisandbox-pa.googleapis.com" in u
                        or "signature=" in u
                    )
                    and u not in vistos
                ):
                    vistos.add(u)
                    urls.append(u)
        except Exception:
            pass
    return urls


def obter_lista_ordenada_urls_videos(ctrl: ControladorFlowPlaywright) -> list[str]:
    """Retorna a lista de URLs de vídeos/miniaturas da grade na ordem exata do DOM (mais recente no índice 0)."""
    urls: list[str] = []
    vistos: set[str] = set()
    for sel in SELETORES_FLOW["miniaturas_video_gerado"]:
        try:
            encontradas = ctrl.page.locator(sel).evaluate_all("els => els.map(e => e.currentSrc || e.src || '')")
            for u in encontradas:
                if (
                    u
                    and ("/asb/" in u or "aisandbox-pa.googleapis.com" in u or "signature=" in u)
                    and u not in vistos
                ):
                    vistos.add(u)
                    urls.append(u)
        except Exception:
            pass

    # Fallback complementar lendo div[data-tile-id] para cards com <video> ou thumbnail aisandbox-pa
    try:
        urls_tiles = ctrl.page.evaluate(
            """() => {
                const tiles = Array.from(document.querySelectorAll('div[data-tile-id]'));
                const out = [];
                for (const tile of tiles) {
                    const text = (tile.innerText || '').trim();
                    const isRendering = /(?:^|\\n|\\s)\\d{1,3}%(?:\\s|\\n|$)/.test(text);
                    const hasFailed = /falha|failed|erro|error|não foi possível/i.test(text);
                    if (isRendering || hasFailed) continue;
                    const videoEl = tile.querySelector('video');
                    if (videoEl && (videoEl.currentSrc || videoEl.src)) {
                        out.push(videoEl.currentSrc || videoEl.src);
                    }
                }
                return out;
            }"""
        )
        for u in urls_tiles or []:
            if u and u not in vistos:
                vistos.add(u)
                urls.append(u)
    except Exception:
        pass

    return urls


def anexar_ingrediente_por_url_asb(ctrl: ControladorFlowPlaywright, url_asb_ref: str | None) -> None:
    """
    No modo Imagem (Takes 2..N), anexa especificamente o Frame 1 daquele vídeo (pelo ID /asb/ da imagem)
    como ingrediente de referência, garantindo que 5 takes disparados em lote não misturem os avatares.
    """
    ctrl.page.mouse.move(10, 10)
    ctrl.limpar_ingredientes_prompt()
    if not url_asb_ref:
        return

    asb_token = url_asb_ref.split("/asb/")[-1][:28] if "/asb/" in url_asb_ref else url_asb_ref[-28:]
    btn_add = ctrl.localizar("botao_adicionar_ingrediente", timeout_ms=5000)
    btn_add.click(force=True)
    time.sleep(0.55)

    opcoes_especificas = ctrl.page.locator(f'button[role="option"]:has(img[src*="{asb_token}"])')
    if opcoes_especificas.count() > 0:
        try:
            opcoes_especificas.first.scroll_into_view_if_needed(timeout=2000)
        except Exception:
            pass
        opcoes_especificas.first.click(force=True)
    else:
        opcoes_img = ctrl.page.locator(
            'button[role="option"]:has(img[alt*="imagem" i]), button[role="option"]:has(img[alt*="image" i])'
        )
        if opcoes_img.count() > 0 and opcoes_img.first.is_visible():
            opcoes_img.first.click(force=True)
        else:
            ctrl.page.keyboard.press("Escape")
            return

    time.sleep(0.4)
    try:
        btn_incluir = ctrl.localizar("botao_adicionar_ao_prompt", timeout_ms=2500)
        btn_incluir.click(force=True)
        time.sleep(0.45)
    except Exception:
        ctrl.page.keyboard.press("Escape")


def anexar_frame_inicio_por_url_ou_disco(
    ctrl: ControladorFlowPlaywright,
    imagem_path: Path,
    url_asb_frame: str | None = None,
) -> None:
    """
    No modo Vídeo -> Frames, anexa exatamente o frame daquele take:
    - se tivermos o token /asb/ da imagem gerada na galeria interna do projeto, seleciona instantaneamente (< 0.8s);
    - caso contrário, faz upload direto do disco.
    """
    ctrl.page.mouse.move(10, 10)
    btn_inicio = ctrl.localizar("botao_frame_inicio", timeout_ms=6000)
    btn_inicio.click(force=True)
    time.sleep(0.45)

    if url_asb_frame == "__RECENTE_PROJETO__":
        op_rec = ctrl.page.locator('button[role="option"]:has(img)')
        if op_rec.count() > 0 and op_rec.first.is_visible():
            op_rec.first.click(force=True)
            time.sleep(0.55)
            try:
                for sel_inc in SELETORES_FLOW["botao_adicionar_ao_prompt"]:
                    b_inc = ctrl.page.locator(sel_inc).first
                    if b_inc.count() > 0 and b_inc.is_visible(timeout=200):
                        b_inc.click(force=True)
                        time.sleep(0.35)
                        break
            except Exception:
                pass
            return

    if url_asb_frame:
        asb_token = url_asb_frame.split("/asb/")[-1][:28] if "/asb/" in url_asb_frame else url_asb_frame[-28:]
        op_exata = ctrl.page.locator(f'button[role="option"]:has(img[src*="{asb_token}"])')
        if op_exata.count() > 0:
            try:
                op_exata.first.scroll_into_view_if_needed(timeout=1500)
            except Exception:
                pass
            op_exata.first.click(force=True)
            time.sleep(0.55)
            try:
                for sel_inc in SELETORES_FLOW["botao_adicionar_ao_prompt"]:
                    b_inc = ctrl.page.locator(sel_inc).first
                    if b_inc.count() > 0 and b_inc.is_visible(timeout=200):
                        b_inc.click(force=True)
                        time.sleep(0.35)
                        break
            except Exception:
                pass
            return

    btn_upload = ctrl.localizar("botao_upload_arquivo", timeout_ms=8000)
    with ctrl.page.expect_file_chooser(timeout=10000) as fc_info:
        btn_upload.click(force=True)
    fc_info.value.set_files(str(imagem_path.resolve()))
    time.sleep(4.5)
    try:
        btn_incluir = ctrl.localizar("botao_adicionar_ao_prompt", timeout_ms=2500)
        btn_incluir.click(force=True)
        time.sleep(1.0)
    except Exception:
        pass

    # Garante que o frame recém-upado está selecionado como Início (mesmo caminho que dá 0.975 de similaridade)
    op_rec_pos = ctrl.page.locator('button[role="option"]:has(img)')
    if op_rec_pos.count() == 0 or not op_rec_pos.first.is_visible():
        try:
            btn_inicio_re = ctrl.localizar("botao_frame_inicio", timeout_ms=3000)
            btn_inicio_re.click(force=True)
            time.sleep(0.6)
        except Exception:
            pass
    op_rec_pos = ctrl.page.locator('button[role="option"]:has(img)')
    if op_rec_pos.count() > 0 and op_rec_pos.first.is_visible():
        op_rec_pos.first.click(force=True)
        time.sleep(0.6)
        try:
            for sel_inc in SELETORES_FLOW["botao_adicionar_ao_prompt"]:
                b_inc = ctrl.page.locator(sel_inc).first
                if b_inc.count() > 0 and b_inc.is_visible(timeout=200):
                    b_inc.click(force=True)
                    time.sleep(0.35)
                    break
        except Exception:
            pass


def detectar_toast_limite_fila(ctrl: ControladorFlowPlaywright) -> str | None:
    """
    Verifica se o Google Flow exibiu algum toast/alerta de limite de fila simultânea
    (ex: 'muitas gerações', 'too many', 'falha', 'limite', 'rate limit', 'try again').
    """
    marcadores_fila = (
        "muitas gerações",
        "too many",
        "limite",
        "limit",
        "queue",
        "fila",
        "aguarde",
        "wait",
        "try again",
        "tente novamente",
        "falha",
        "failed",
        "não foi possível",
        "couldn't generate",
    )
    for sel in SELETORES_FLOW["alertas_sistema"] + ["mat-snack-bar-container", "simple-snack-bar"]:
        try:
            for el in ctrl.page.locator(sel).all():
                if el.is_visible(timeout=100):
                    txt = (el.inner_text(timeout=150) or "").strip()
                    low = txt.lower()
                    if any(m in low for m in marcadores_fila):
                        return txt
        except Exception:
            pass
    return None


def detectar_card_atividade_incomum_na_grade(ctrl: ControladorFlowPlaywright) -> bool:
    """Detecta se algum card (div[data-tile-id]) na grade exibiu 'Notamos uma atividade incomum' ou 'extensões do navegador'."""
    js_check = """
    () => {
        const txt = (document.body ? document.body.innerText : '').toLowerCase();
        return txt.includes('atividade incomum') || txt.includes('unusual activity') || txt.includes('extensões do navegador');
    }
    """
    try:
        return bool(ctrl.page.evaluate(js_check))
    except Exception:
        return False


def contar_cards_renderizando_na_grade(ctrl: ControladorFlowPlaywright) -> int:
    """Conta quantos cards estão com porcentagem ativa (1%..99%) na grade neste exato instante."""
    js_count = """
    () => {
        const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
        let n, count = 0;
        while ((n = walker.nextNode())) {
            const t = (n.nodeValue || '').trim();
            if (/^\\d{1,3}%$/.test(t)) {
                const el = n.parentElement;
                if (el && el.offsetParent !== null) count++;
            }
        }
        return count;
    }
    """
    try:
        return int(ctrl.page.evaluate(js_count))
    except Exception:
        return 0


def disparar_onda_frames_simultaneos(
    ctrl: ControladorFlowPlaywright,
    tarefas_frames: list[dict[str, Any]],
    timeout_s: int = 300,
) -> dict[str, str]:
    """
    Dispara N frames simultâneos no Google Flow sem esperar um terminar para enviar o próximo!
    Se atingir o limite de concorrência do servidor do Flow no meio da onda, detecta o aviso,
    registra o teto exato de frames simultâneos suportados e aguarda abrir vaga automaticamente.
    """
    if not tarefas_frames:
        return {}

    with _lock_ui_flow(ctrl):
        ctrl.configurar_modo_flow(modo="imagem", quantidade="x1")
        urls_antes = set(obter_lista_ordenada_urls_imagens(ctrl))

        ctrl.logger.log(f"[ONDA TURBO FRAMES] Disparando {len(tarefas_frames)} frames simultâneos no Flow...")
        pico_simultaneo_frames = 0
        limite_detectado_frames: int | None = None

        for idx, tf in enumerate(tarefas_frames, start=1):
            while True:
                ctrl.verificar_alertas_flow()
                if tf.get("url_ref_frame1"):
                    anexar_ingrediente_por_url_asb(ctrl, tf["url_ref_frame1"])
                else:
                    ctrl.limpar_ingredientes_prompt()
                ctrl.digitar_prompt_e_disparar(tf["prompt_imagem"])
                time.sleep(2.0)

                toast_erro = detectar_toast_limite_fila(ctrl)
                ativos_agora = contar_cards_renderizando_na_grade(ctrl)
                pico_simultaneo_frames = max(pico_simultaneo_frames, ativos_agora, idx)

                if toast_erro:
                    if limite_detectado_frames is None:
                        limite_detectado_frames = max(1, idx - 1)
                    ctrl.logger.log(
                        f"  [TETO DE FRAMES DETECTADO NO DISPARO #{idx}] Toast Flow: '{toast_erro}' "
                        f"(Limite simultâneo real = {limite_detectado_frames} frames). Aguardando 10s por vaga...",
                        nivel="WARN",
                    )
                    time.sleep(10.0)
                    continue

                ctrl.logger.log(
                    f"  -> Frame [{idx}/{len(tarefas_frames)}] disparado ({tf['chave']} -> {tf['destino_jpg'].name}) | Renderizando na grade: {ativos_agora}"
                )
                break

    qtd_alvo = len(tarefas_frames)
    prazo = time.monotonic() + timeout_s
    time.sleep(4.0)

    novas_ordenadas: list[str] = []
    ciclos_ociosos_img = 0
    ciclos_renderizando_img = 0
    while time.monotonic() < prazo:
        ctrl.verificar_alertas_flow()
        lista_atual = obter_lista_ordenada_urls_imagens(ctrl)
        novas_ordenadas = [u for u in lista_atual if u not in urls_antes]
        if len(novas_ordenadas) >= qtd_alvo:
            break
        if not ctrl.geracao_em_andamento_na_grade():
            ciclos_renderizando_img = 0
            ciclos_ociosos_img += 1
            if ciclos_ociosos_img == 2:
                try:
                    ctrl.page.reload(wait_until="domcontentloaded", timeout=30000)
                    time.sleep(3.5)
                    lista_atual = obter_lista_ordenada_urls_imagens(ctrl)
                    novas_ordenadas = [u for u in lista_atual if u not in urls_antes]
                    if len(novas_ordenadas) >= qtd_alvo:
                        break
                except Exception:
                    pass
            elif ciclos_ociosos_img >= 3 and len(novas_ordenadas) < qtd_alvo:
                faltam_img = qtd_alvo - len(novas_ordenadas)
                tem_incomum = detectar_card_atividade_incomum_na_grade(ctrl)
                if tem_incomum:
                    ctrl.logger.log(
                        "  [ANTI-BOTGUARD COOLING] Detectado card 'Atividade incomum / extensoes do navegador'! "
                        "Aguardando 45s (sem bloquear a outra aba) e recriando projeto limpo...",
                        nivel="WARN",
                    )
                    time.sleep(45.0)
                with _lock_ui_flow(ctrl):
                    if tem_incomum:
                        ctrl.criar_novo_projeto_limpo()
                        urls_antes = set(obter_lista_ordenada_urls_imagens(ctrl))
                    ctrl.logger.log(
                        f"  [AUTO-RECOVERY FRAMES] {len(novas_ordenadas)}/{qtd_alvo} prontos e grade ociosa; re-disparando {faltam_img} frame(s) com cadencia segura (2.5s)...",
                        nivel="WARN",
                    )
                    ctrl.configurar_modo_flow(modo="imagem", quantidade="x1")
                    for tf_rep in tarefas_frames[-faltam_img:]:
                        if tf_rep.get("url_ref_frame1"):
                            anexar_ingrediente_por_url_asb(ctrl, tf_rep["url_ref_frame1"])
                        else:
                            ctrl.limpar_ingredientes_prompt()
                        ctrl.digitar_prompt_e_disparar(tf_rep["prompt_imagem"])
                        time.sleep(2.5)
                prazo = max(prazo, time.monotonic() + 180)
                ciclos_ociosos_img = 0
        else:
            ciclos_ociosos_img = 0
            ciclos_renderizando_img += 1
            if ciclos_renderizando_img >= 30:
                ctrl.logger.log("  [ANTI-ZOMBIE 99% FRAMES] Recarregando grade após 60s de renderização contínua...", nivel="INFO")
                try:
                    ctrl.page.reload(wait_until="domcontentloaded", timeout=30000)
                    time.sleep(3.0)
                except Exception:
                    pass
                ciclos_renderizando_img = 0
        time.sleep(2.0)

    if len(novas_ordenadas) < qtd_alvo:
        try:
            with _lock_ui_flow(ctrl):
                ctrl.page.reload(wait_until="domcontentloaded", timeout=30000)
                time.sleep(4.0)
                lista_atual = obter_lista_ordenada_urls_imagens(ctrl)
                novas_ordenadas = [u for u in lista_atual if u not in urls_antes]
        except Exception:
            pass

    if len(novas_ordenadas) < qtd_alvo:
        raise TimeoutError(
            f"[ONDA TURBO FRAMES] Esperava {qtd_alvo} novas imagens, mas apenas {len(novas_ordenadas)} apareceram em {timeout_s}s."
        )

    selecionadas_ordem_disparo = list(reversed(novas_ordenadas[:qtd_alvo]))
    mapa_urls: dict[str, str] = {}
    for tf, url_img in zip(tarefas_frames, selecionadas_ordem_disparo):
        ctrl.baixar_imagem_por_url(url_img, tf["destino_jpg"])
        mapa_urls[tf["chave"]] = url_img
        ctrl.logger.log(f"  [OK FRAME] {tf['chave']} salvo em {tf['destino_jpg'].name} ({tf['destino_jpg'].stat().st_size} bytes)")

    ctrl.logger.log(
        f"[TELEMETRIA FRAMES] Onda de {len(tarefas_frames)} frames concluída | "
        f"Pico simultâneo na grade: {pico_simultaneo_frames} | "
        f"Teto/Toast detectado: {limite_detectado_frames if limite_detectado_frames is not None else 'NENHUM (100% aceito)'}"
    )
    ctrl.safety_guard.resetar()
    return mapa_urls


def baixar_video_por_url_card(ctrl: ControladorFlowPlaywright, url_card: str, destino_mp4: Path) -> bool:
    """
    Baixa o MP4 720p diretamente via HTTP autenticado (_converter_para_url_mp4_direta) em ~0.3s sem abrir modal!
    Mantém fallback de clique no card caso necessário.
    """
    destino_mp4.parent.mkdir(parents=True, exist_ok=True)
    url_mp4_direta = _converter_para_url_mp4_direta(url_card)
    for _ in range(2):
        try:
            resp = ctrl.page.context.request.get(url_mp4_direta, timeout=30000)
            if resp.status == 200:
                dados = resp.body()
                if len(dados) > 50_000:
                    destino_mp4.write_bytes(dados)
                    if ctrl.validar_video_mp4_baixado(destino_mp4):
                        return True
        except Exception:
            time.sleep(0.5)

    token = url_card.split("/asb/")[-1][:28] if "/asb/" in url_card else url_card[-28:]

    for tentativa in range(1, 4):
        ctrl.page.mouse.move(10, 10)
        ctrl.page.keyboard.press("Escape")
        time.sleep(0.5)

        card = ctrl.page.locator(f'img[src*="{token}"]').first
        if card.count() == 0:
            ctrl.page.mouse.move(600, 500)
            ctrl.page.mouse.wheel(0, 700 * tentativa)
            time.sleep(0.8)
            card = ctrl.page.locator(f'img[src*="{token}"]').first
            if card.count() == 0:
                continue

        try:
            card.scroll_into_view_if_needed(timeout=3000)
        except Exception:
            pass
        card.click(force=True)
        time.sleep(2.4)

        for sel_dl in SELETORES_FLOW["botao_baixar_midia"]:
            btn = ctrl.page.locator(sel_dl).first
            try:
                if btn.count() > 0 and btn.is_visible(timeout=800):
                    btn.click(force=True)
                    time.sleep(0.8)
                    with ctrl.page.expect_download(timeout=60000) as dl_info:
                        op_clicada = False
                        for sel_op in SELETORES_FLOW["opcao_download_720p"]:
                            op = ctrl.page.locator(sel_op).first
                            if op.count() > 0 and op.is_visible(timeout=600):
                                op.click(force=True)
                                op_clicada = True
                                break
                        if not op_clicada:
                            btn.click(force=True)
                    dl = dl_info.value
                    destino_mp4.parent.mkdir(parents=True, exist_ok=True)
                    dl.save_as(str(destino_mp4))
                    break
            except Exception as e:
                ctrl.logger.log(f"Aviso ao baixar vídeo {destino_mp4.name} (tentativa {tentativa}/3): {e}", nivel="WARN")

        try:
            btn_done = ctrl.localizar("botao_concluido_detalhe", timeout_ms=2500)
            btn_done.click(force=True)
            time.sleep(0.8)
        except Exception:
            ctrl.page.keyboard.press("Escape")
            time.sleep(0.6)

        if ctrl.validar_video_mp4_baixado(destino_mp4):
            return True

    return ctrl.validar_video_mp4_baixado(destino_mp4)


def disparar_onda_videos_simultaneos(
    ctrl: ControladorFlowPlaywright,
    tarefas_videos: list[dict[str, Any]],
    timeout_s: int = 720,
) -> list[Path]:
    """
    Dispara até 15 VÍDEOS SIMULTÂNEOS no Google Flow (Veo 3.1 - Lite [Lower Priority]):
    - Seleciona na galeria interna do projeto o Frame 1 correspondente a cada vídeo;
    - Injeta o prompt com document.execCommand('insertText') e clica em 'Iniciar geração';
    - Faz polling ativo a cada 2s monitorando a renderização na grade;
    - Baixa os 15 MP4s simultaneamente em 16 threads via URL direta (=mm,22,15).
    """
    if not tarefas_videos:
        return []

    with _lock_ui_flow(ctrl):
        ctrl.configurar_modo_flow(modo="video", quantidade="x1")
        urls_videos_antes = set(obter_lista_ordenada_urls_videos(ctrl))

        ctrl.logger.log(f"[ONDA TURBO VÍDEOS] Disparando {len(tarefas_videos)} vídeos simultâneos no Flow...")
        pico_simultaneo_videos = 0
        limite_detectado_videos: int | None = None

        for idx, tv in enumerate(tarefas_videos, start=1):
            while True:
                ctrl.verificar_alertas_flow()
                anexar_frame_inicio_por_url_ou_disco(
                    ctrl,
                    imagem_path=tv["imagem_path"],
                    url_asb_frame=tv.get("url_asb_frame"),
                )
                ctrl.digitar_prompt_e_disparar(tv["prompt_video"])
                time.sleep(2.0)

                toast_erro = detectar_toast_limite_fila(ctrl)
                ativos_agora = contar_cards_renderizando_na_grade(ctrl)
                pico_simultaneo_videos = max(pico_simultaneo_videos, ativos_agora, idx)

                if toast_erro:
                    if limite_detectado_videos is None:
                        limite_detectado_videos = max(1, idx - 1)
                    ctrl.logger.log(
                        f"  [TETO DE VÍDEOS DETECTADO NO DISPARO #{idx}] Toast Flow: '{toast_erro}' "
                        f"(Limite simultâneo real = {limite_detectado_videos} vídeos). Aguardando 15s por vaga...",
                        nivel="WARN",
                    )
                    time.sleep(15.0)
                    continue

                ctrl.logger.log(
                    f"  -> Vídeo [{idx}/{len(tarefas_videos)}] disparado ({tv['chave']} -> {tv['destino_mp4'].name}) | Renderizando na grade: {ativos_agora}"
                )
                break

    qtd_alvo = len(tarefas_videos)
    prazo = time.monotonic() + timeout_s
    time.sleep(8.0)

    urls_acumuladas_na_ordem_disparo: list[str] = []
    ja_recarregou = False
    ciclos_ociosos_vid = 0
    ciclos_renderizando_vid = 0
    while time.monotonic() < prazo:
        ctrl.verificar_alertas_flow()
        atuais_chk = obter_lista_ordenada_urls_videos(ctrl)
        novos_chk = list(reversed([u for u in atuais_chk if u not in urls_videos_antes and u not in urls_acumuladas_na_ordem_disparo]))
        if len(urls_acumuladas_na_ordem_disparo) + len(novos_chk) >= qtd_alvo:
            urls_acumuladas_na_ordem_disparo.extend(novos_chk)
            break

        if ctrl.geracao_em_andamento_na_grade():
            ciclos_ociosos_vid = 0
            ciclos_renderizando_vid += 1
            if ciclos_renderizando_vid >= 35:
                ctrl.logger.log(
                    f"  [ANTI-ZOMBIE 99% VÍDEOS] Recarregando grade após ~88s de renderização contínua ({len(urls_acumuladas_na_ordem_disparo) + len(novos_chk)}/{qtd_alvo} prontos)...",
                    nivel="INFO",
                )
                try:
                    ctrl.page.reload(wait_until="domcontentloaded", timeout=30000)
                    time.sleep(3.5)
                except Exception:
                    pass
                ciclos_renderizando_vid = 0
            else:
                time.sleep(2.5)
            continue

        ciclos_renderizando_vid = 0
        if not ja_recarregou:
            try:
                ctrl.page.reload(wait_until="domcontentloaded", timeout=30000)
                time.sleep(3.0)
                ja_recarregou = True
            except Exception:
                pass

        if ctrl.geracao_em_andamento_na_grade():
            ja_recarregou = False
            ciclos_ociosos_vid = 0
            time.sleep(2.5)
            continue

        atuais = obter_lista_ordenada_urls_videos(ctrl)
        novos_deste_proj = list(reversed([u for u in atuais if u not in urls_videos_antes and u not in urls_acumuladas_na_ordem_disparo]))
        total_prontos_agora = len(urls_acumuladas_na_ordem_disparo) + len(novos_deste_proj)
        if total_prontos_agora >= qtd_alvo:
            urls_acumuladas_na_ordem_disparo.extend(novos_deste_proj)
            break

        ciclos_ociosos_vid += 1
        if ciclos_ociosos_vid >= 2 and total_prontos_agora < qtd_alvo:
            # Salva imediatamente os vídeos que já ficaram prontos neste projeto antes de reciclar!
            if novos_deste_proj:
                urls_acumuladas_na_ordem_disparo.extend(novos_deste_proj)
            faltam_vid = qtd_alvo - len(urls_acumuladas_na_ordem_disparo)
            tem_alerta_incomum = detectar_card_atividade_incomum_na_grade(ctrl)
            if tem_alerta_incomum:
                ctrl.logger.log(
                    "  [SENIOR SELF-HEALING] Detectado card 'Atividade incomum'! Resfriando 20s e abrindo NOVO PROJETO LIMPO para não estourar 20 cards nem repetir no projeto marcado...",
                    nivel="WARN",
                )
                time.sleep(20.0)
            with _lock_ui_flow(ctrl):
                ctrl.logger.log(
                    f"  [SENIOR SELF-HEALING VÍDEOS] {len(urls_acumuladas_na_ordem_disparo)}/{qtd_alvo} vídeos salvos; criando NOVO PROJETO LIMPO para gerar os {faltam_vid} take(s) restantes sem virtualização DOM...",
                    nivel="WARN",
                )
                ctrl.criar_novo_projeto_limpo()
                urls_videos_antes = set()
                ctrl.configurar_modo_flow(modo="video", quantidade="x1")
                for tv_rep in tarefas_videos[-faltam_vid:]:
                    # Em novo projeto limpo, faz upload do frame_1.jpg do disco (url_asb_frame=None)
                    anexar_frame_inicio_por_url_ou_disco(
                        ctrl,
                        imagem_path=tv_rep["imagem_path"],
                        url_asb_frame=None,
                    )
                    ctrl.digitar_prompt_e_disparar(tv_rep["prompt_video"])
                    time.sleep(2.8)
            prazo = max(prazo, time.monotonic() + 300)
            ciclos_ociosos_vid = 0
            ciclos_renderizando_vid = 0
            ja_recarregou = False
            time.sleep(8.0)
            continue

        ja_recarregou = False
        time.sleep(2.5)

    if len(urls_acumuladas_na_ordem_disparo) < qtd_alvo:
        raise TimeoutError(
            f"[ONDA TURBO VÍDEOS] Esperava {qtd_alvo} vídeos prontos, mas {len(urls_acumuladas_na_ordem_disparo)} concluíram em {timeout_s}s."
        )

    urls_na_ordem_disparo = urls_acumuladas_na_ordem_disparo[:qtd_alvo]
    baixados: list[Path] = []

    import urllib.request

    cookies = []
    try:
        s_ck = ctrl.page.context.new_cdp_session(ctrl.page)
        cookies = s_ck.send(
            "Network.getCookies",
            {
                "urls": [
                    "https://flow.google.com",
                    "https://labs.google",
                    "https://aisandbox-pa.googleapis.com",
                    "https://google.com",
                    "https://googleusercontent.com",
                ]
            },
        ).get("cookies", [])
        s_ck.detach()
    except Exception:
        cookies = ctrl.page.context.cookies(
            [
                "https://flow.google.com",
                "https://labs.google",
                "https://aisandbox-pa.googleapis.com",
                "https://google.com",
                "https://googleusercontent.com",
            ]
        )
    cookie_header = "; ".join(f"{ck['name']}={ck['value']}" for ck in cookies)
    ua = ctrl.page.evaluate("() => navigator.userAgent")

    def _baixar_http_direto(par: tuple[dict[str, Any], str]) -> tuple[dict[str, Any], str, bool]:
        tv_item, u_card = par
        dest = tv_item["destino_mp4"]
        dest.parent.mkdir(parents=True, exist_ok=True)
        u_mp4 = _converter_para_url_mp4_direta(u_card)
        for _ in range(2):
            try:
                req = urllib.request.Request(
                    u_mp4,
                    headers={
                        "Cookie": cookie_header,
                        "User-Agent": ua,
                        "Referer": "https://labs.google/",
                    },
                )
                with urllib.request.urlopen(req, timeout=45) as resp:
                    dados = resp.read()
                if len(dados) > 50_000 and b"ftyp" in dados[:64]:
                    dest.write_bytes(dados)
                    return tv_item, u_card, True
            except Exception:
                time.sleep(0.4)
        return tv_item, u_card, False

    pares_download = list(zip(tarefas_videos, urls_na_ordem_disparo))
    with ThreadPoolExecutor(max_workers=min(16, max(1, len(pares_download)))) as pool_dl:
        resultados_dl = list(pool_dl.map(_baixar_http_direto, pares_download))

    for tv, u_vid, ok_http in resultados_dl:
        ok = ok_http or baixar_video_por_url_card(ctrl, u_vid, tv["destino_mp4"])
        if ok:
            baixados.append(tv["destino_mp4"])
            ctrl.logger.log(
                f"  [OK VÍDEO] {tv['chave']} salvo em {tv['destino_mp4'].name} ({tv['destino_mp4'].stat().st_size} bytes)"
            )
        else:
            ctrl.logger.log(f"  [FALHA DOWNLOAD VÍDEO] {tv['chave']}", nivel="ERROR")

    ctrl.logger.log(
        f"[TELEMETRIA VÍDEOS] Onda de {len(tarefas_videos)} vídeos concluída | "
        f"Pico simultâneo na grade: {pico_simultaneo_videos} | "
        f"Teto/Toast detectado: {limite_detectado_videos if limite_detectado_videos is not None else 'NENHUM (100% aceito)'}"
    )
    ctrl.safety_guard.resetar()
    return baixados


def executar_lote_turbo_paralelo(
    lote_id: str,
    lista_prompts_videos: list[dict[str, Any]],
    max_frames_simultaneos: int = MAX_FRAMES_SIMULTANEOS,
    max_videos_simultaneos: int = MAX_VIDEOS_SIMULTANEOS,
    usar_frame1_unico: bool = True,
    project_url: str | None = None,
    porta_cdp: int = 9222,
    profile_dir: str | Path | None = None,
    rodar_vigia: bool = True,
    auto_abrir: bool = False,
    root: Path = ROOT_DIR,
) -> dict[str, Any]:
    """
    Executa um lote de N vídeos em modo TURBO (Macro-Ondas de 5 vídeos = 5 Frames + 15 Takes = 20 cards):
    1) Agrupa os vídeos em Macro-Ondas de 5 vídeos (15 takes de vídeo).
    2) Ao iniciar cada nova Macro-Onda (idx_macro >= 2), cria um Novo Projeto limpo em https://labs.google/fx/pt/tools/flow.
    3) Dentro de cada Macro-Onda:
       - Passo A: Gera apenas os 5 Frames 1 base (1 por personagem).
       - Passo B: Propaga a referência do Frame 1 na galeria interna do projeto para os Takes 2 e 3.
       - Passo C: Dispara os 15 takes de vídeo no Veo 3.1 - Lite [Lower Priority] e baixa em paralelo (16 threads, =mm,22,15).
       - Passo D: Roda o QA (Whisper GPU) e a Edição (h264_nvenc) em uma thread separada enquanto a próxima onda começa.
    """
    t0_lote = time.monotonic()
    logger = BatchLogger(lote_id, root=root)
    safety = FlowSafetyGuard(logger)

    caches: dict[str, tuple[CacheVideoForja, dict[str, Any], Path]] = {}
    urls_asb_conhecidas: dict[str, str] = {}

    for pv in lista_prompts_videos:
        enriquecer_item_video_zerum(pv)
        vid_id = pv["video_id"]
        pasta_v = root / "lotes" / lote_id / vid_id
        cm = CacheVideoForja(pasta_v)
        est = cm.sincronizar_arquivos_existentes(cm.carregar(pv))
        caches[vid_id] = (cm, est, pasta_v)

    ctrl = ControladorFlowPlaywright(
        logger=logger,
        safety_guard=safety,
        porta_cdp=porta_cdp,
        profile_dir=profile_dir,
        project_url=project_url,
    )
    ctrl.conectar(auto_abrir=auto_abrir)

    entregues_lista: list[dict[str, Any]] = []
    reprovados_lista: list[dict[str, Any]] = []
    resultados_qa_por_video: dict[str, dict[str, dict[str, Any]]] = {}

    def _validar_take(args_tuple: tuple[str, str, Path, str, Path]) -> tuple[str, str, dict[str, Any]]:
        vid_id, num_s, c_path, fala_esp, i_path = args_tuple
        tes = tesoura_cirurgica_3_passes(video_path=c_path, fala_pedida=fala_esp)
        qa = avaliar_qa_clipe(video_path=c_path, fala_pedida=fala_esp, imagem_gerada_path=i_path)
        qa["tesoura_3_passes"] = tes
        return vid_id, num_s, qa

    def _processar_pos_onda_bg(idx_macro: int, total_macros: int, grupo_pvs: list[dict[str, Any]]) -> None:
        """Roda QA paralelo + Entrega + Edição Vigia GPU em background enquanto a próxima onda gera no Flow!"""
        from edicao.estoque import gerar_painel_estoque
        from edicao.vigia import VigiaEdicao

        grupo_pvs = [
            pv_item
            for pv_item in grupo_pvs
            if not (root / "entregues" / f"{lote_id}_{pv_item['video_id']}" / "falas.json").exists()
            and not (root / "estoque" / "prontos" / f"{lote_id}_{pv_item['video_id']}" / "video_final.mp4").exists()
        ]
        if not grupo_pvs:
            return
        tarefas_qa_onda = []
        for pv_item in grupo_pvs:
            v_id = pv_item["video_id"]
            _, est_v, pasta_v = caches[v_id]
            for num_str, t_info in est_v["takes"].items():
                tarefas_qa_onda.append(
                    (
                        v_id,
                        num_str,
                        pasta_v / t_info["arquivo_clipe"],
                        t_info["fala"],
                        pasta_v / t_info["arquivo_imagem"],
                    )
                )

        if rodar_vigia:
            with ThreadPoolExecutor(max_workers=min(16, max(1, len(tarefas_qa_onda)))) as pool_qa:
                for v_id, num_s, qa_res in pool_qa.map(_validar_take, tarefas_qa_onda):
                    resultados_qa_por_video.setdefault(v_id, {})[num_s] = qa_res
        else:
            for v_id, num_s, c_path, _, _ in tarefas_qa_onda:
                ok_mp4 = c_path.is_file() and c_path.stat().st_size > 20_000
                resultados_qa_por_video.setdefault(v_id, {})[num_s] = dict(aprovado=ok_mp4)

        for pv_item in grupo_pvs:
            v_id = pv_item["video_id"]
            _, est_v, pasta_v = caches[v_id]
            falas_payload = {
                "video_id": v_id,
                "lote_id": lote_id,
                "formato": est_v["formato"],
                "avatar": est_v["avatar"],
                "cta_texto": "COMMENT YES",
                "takes": [
                    {
                        "take": info["take"],
                        "arquivo": info["arquivo_clipe"],
                        "papel": info["papel"],
                        "fala": info["fala"],
                    }
                    for info in est_v["takes"].values()
                ],
            }
            (pasta_v / "falas.json").write_text(json.dumps(falas_payload, ensure_ascii=False, indent=2), encoding="utf-8")

            qas_vid = resultados_qa_por_video.get(v_id, {})
            aprovado_v = all(q.get("aprovado", False) for q in qas_vid.values())
            if aprovado_v:
                pasta_ent = entregar_video_aprovado(
                    lote_id=lote_id,
                    video_id=v_id,
                    pasta_video_lote=pasta_v,
                    entregues_root=root / "entregues",
                    logger=logger,
                )
                entregues_lista.append({"video_id": v_id, "pasta_entregue": str(pasta_ent)})
            else:
                reprovados_lista.append({"video_id": v_id, "qas": qas_vid})

        if rodar_vigia:
            try:
                vigia_bg = VigiaEdicao(root=root)
                vigia_bg.varrer_uma_vez(mover_ao_finalizar=True, max_workers=4)
                painel_bg = gerar_painel_estoque(root=root)
                logger.log(
                    f"[MACRO-ONDA {idx_macro}/{total_macros} NO ESTOQUE] "
                    f"Total prontos no estoque.json agora: {painel_bg.get('disponiveis')} vídeos!"
                )
            except Exception as e_bg:
                logger.log(f"Aviso no Vigia background da macro-onda {idx_macro}: {e_bg}", nivel="WARN")

        ids_aprovados_onda = [e_item["video_id"] for e_item in entregues_lista if any(p["video_id"] == e_item["video_id"] for p in grupo_pvs)]
        if os.environ.get("FORJA_OFFLOAD_PEACHCLUB", "1") != "0" and ids_aprovados_onda:
            try:
                from forja.rclone_offload import descarregar_onda_para_peachclub
                descarregar_onda_para_peachclub(
                    lote_id=lote_id,
                    video_ids=ids_aprovados_onda,
                    root=root,
                    remover_mp4_local_lote=True,
                    mover_entregues_para_nuvem=not rodar_vigia,
                    logger=logger,
                )
            except Exception as e_off:
                logger.log(f"Aviso no offload rclone da macro-onda {idx_macro}: {e_off}", nivel="WARN")

    import shutil

    videos_por_macro_onda = max(1, max_videos_simultaneos // 3)
    grupos_macro = [
        lista_prompts_videos[i : i + videos_por_macro_onda]
        for i in range(0, len(lista_prompts_videos), videos_por_macro_onda)
    ]
    total_macros = len(grupos_macro)
    bg_executor = ThreadPoolExecutor(max_workers=1)
    futures_bg = []

    try:
        for idx_macro, grupo_pvs in enumerate(grupos_macro, start=1):
            ids_onda = [p["video_id"] for p in grupo_pvs]
            logger.log(
                f"=== [MACRO-ONDA {idx_macro}/{total_macros}] Processando {len(grupo_pvs)} vídeos ({ids_onda[0]}..{ids_onda[-1]}) na porta CDP {porta_cdp} ==="
            )

            # Recicla o projeto (Novo projeto) no início de cada Macro-Onda se idx_macro >= 2 ou se o projeto atual já tiver cards antigos
            precisa_gerar_onda = any(
                not (
                    caches[pv["video_id"]][1]["takes"][num_str]["clipe_pronto"]
                    and (caches[pv["video_id"]][2] / caches[pv["video_id"]][1]["takes"][num_str]["arquivo_clipe"]).exists()
                )
                for pv in grupo_pvs
                for num_str in caches[pv["video_id"]][1]["takes"]
            )
            eh_retentativa_parcial = any(
                any(
                    caches[pv["video_id"]][1]["takes"][num_str]["clipe_pronto"]
                    and (caches[pv["video_id"]][2] / caches[pv["video_id"]][1]["takes"][num_str]["arquivo_clipe"]).exists()
                    for num_str in caches[pv["video_id"]][1]["takes"]
                )
                or pv.get("usar_frame1_existente")
                for pv in grupo_pvs
            )
            if precisa_gerar_onda and not eh_retentativa_parcial:
                with _lock_ui_flow(ctrl):
                    tem_cards_antigos = (
                        len(obter_lista_ordenada_urls_imagens(ctrl)) > 0
                        or len(obter_lista_ordenada_urls_videos(ctrl)) > 0
                    )
                    if tem_cards_antigos:
                        ctrl.criar_novo_projeto_limpo()
                        urls_asb_conhecidas.clear()

            # Passo A da Macro-Onda: Gera apenas os 5 Frames 1 base desta macro-onda
            tarefas_f1: list[dict[str, Any]] = []
            for pv in grupo_pvs:
                vid_id = pv["video_id"]
                cm, est, pasta_v = caches[vid_id]
                t1 = est["takes"]["1"]
                f1_path = pasta_v / t1["arquivo_imagem"]
                if pv.get("usar_frame1_existente") and f1_path.is_file():
                    t1["imagem_pronta"] = True
                    t1["imagem_aprovada"] = True
                    t1["url_asb"] = "__RECENTE_PROJETO__"
                    urls_asb_conhecidas[f"{vid_id}_1"] = "__RECENTE_PROJETO__"
                    cm.salvar(est)
                    continue
                if precisa_gerar_onda or not (t1["imagem_aprovada"] and f1_path.exists()):
                    tarefas_f1.append(
                        {
                            "chave": f"{vid_id}_1",
                            "video_id": vid_id,
                            "take_str": "1",
                            "prompt_imagem": t1["prompt_imagem"],
                            "destino_jpg": f1_path,
                            "url_ref_frame1": None,
                        }
                    )

            for i in range(0, len(tarefas_f1), max_frames_simultaneos):
                sub_onda = tarefas_f1[i : i + max_frames_simultaneos]
                mapa_f1 = disparar_onda_frames_simultaneos(ctrl, sub_onda)
                urls_asb_conhecidas.update(mapa_f1)
                for tf in sub_onda:
                    cm, est, _ = caches[tf["video_id"]]
                    est["takes"]["1"]["imagem_pronta"] = True
                    est["takes"]["1"]["imagem_aprovada"] = True
                    est["takes"]["1"]["url_asb"] = mapa_f1.get(tf["chave"], "")
                    cm.salvar(est)

            # Passo B da Macro-Onda: Propaga Frame 1 para Takes 2..N (consistência 100% + seleção interna na galeria)
            if usar_frame1_unico:
                for pv in grupo_pvs:
                    vid_id = pv["video_id"]
                    cm, est, pasta_v = caches[vid_id]
                    f1_path = pasta_v / est["takes"]["1"]["arquivo_imagem"]
                    url_f1 = urls_asb_conhecidas.get(f"{vid_id}_1") or est["takes"]["1"].get("url_asb", "")
                    for num_str, t_info in est["takes"].items():
                        if num_str == "1":
                            continue
                        fn_path = pasta_v / t_info["arquivo_imagem"]
                        if f1_path.is_file() and not fn_path.is_file():
                            shutil.copy2(f1_path, fn_path)
                        t_info["imagem_pronta"] = True
                        t_info["imagem_aprovada"] = True
                        url_ref_take = url_f1 or ("__RECENTE_PROJETO__" if pv.get("usar_frame1_existente") else "")
                        t_info["url_asb"] = url_ref_take
                        urls_asb_conhecidas[f"{vid_id}_{num_str}"] = url_ref_take
                    cm.salvar(est)
            else:
                tarefas_fn: list[dict[str, Any]] = []
                for pv in grupo_pvs:
                    vid_id = pv["video_id"]
                    cm, est, pasta_v = caches[vid_id]
                    url_ref = urls_asb_conhecidas.get(f"{vid_id}_1") or est["takes"]["1"].get("url_asb")
                    for num_str, t_info in est["takes"].items():
                        if num_str == "1":
                            continue
                        fn_path = pasta_v / t_info["arquivo_imagem"]
                        if not (t_info["imagem_aprovada"] and fn_path.exists()):
                            tarefas_fn.append(
                                {
                                    "chave": f"{vid_id}_{num_str}",
                                    "video_id": vid_id,
                                    "take_str": num_str,
                                    "prompt_imagem": t_info["prompt_imagem"],
                                    "destino_jpg": fn_path,
                                    "url_ref_frame1": url_ref,
                                }
                            )
                for i in range(0, len(tarefas_fn), max_frames_simultaneos):
                    sub_onda = tarefas_fn[i : i + max_frames_simultaneos]
                    mapa_fn = disparar_onda_frames_simultaneos(ctrl, sub_onda)
                    urls_asb_conhecidas.update(mapa_fn)
                    for tf in sub_onda:
                        cm, est, _ = caches[tf["video_id"]]
                        t_obj = est["takes"][tf["take_str"]]
                        t_obj["imagem_pronta"] = True
                        t_obj["imagem_aprovada"] = True
                        t_obj["url_asb"] = mapa_fn.get(tf["chave"], "")
                        cm.salvar(est)

            # Passo C da Macro-Onda: Dispara os 15 vídeos desta macro-onda e baixa via HTTP paralelo (=mm,22,15)!
            tarefas_vid: list[dict[str, Any]] = []
            for pv in grupo_pvs:
                vid_id = pv["video_id"]
                cm, est, pasta_v = caches[vid_id]
                for num_str, t_info in est["takes"].items():
                    clip_path = pasta_v / t_info["arquivo_clipe"]
                    img_path = pasta_v / t_info["arquivo_imagem"]
                    if not (t_info["clipe_pronto"] and clip_path.exists()):
                        tarefas_vid.append(
                            {
                                "chave": f"{vid_id}_take{num_str}",
                                "video_id": vid_id,
                                "take_str": num_str,
                                "imagem_path": img_path,
                                "url_asb_frame": urls_asb_conhecidas.get(f"{vid_id}_{num_str}") or t_info.get("url_asb"),
                                "prompt_video": t_info["prompt_video"],
                                "destino_mp4": clip_path,
                            }
                        )

            for i in range(0, len(tarefas_vid), max_videos_simultaneos):
                sub_onda_v = tarefas_vid[i : i + max_videos_simultaneos]
                disparar_onda_videos_simultaneos(ctrl, sub_onda_v)
                for tv in sub_onda_v:
                    cm, est, _ = caches[tv["video_id"]]
                    t_obj = est["takes"][tv["take_str"]]
                    t_obj["clipe_pronto"] = tv["destino_mp4"].exists()
                    cm.salvar(est)

            # Passo D da Macro-Onda: Envia QA + Entrega + Vigia GPU para rodar em BACKGROUND imediato!
            futures_bg.append(bg_executor.submit(_processar_pos_onda_bg, idx_macro, total_macros, list(grupo_pvs)))

    finally:
        ctrl.desconectar()

    for fut in futures_bg:
        try:
            fut.result()
        except Exception as e_f:
            logger.log(f"Erro ao finalizar tarefa background: {e_f}", nivel="ERROR")
    bg_executor.shutdown(wait=True)

    tempo_total_s = round(time.monotonic() - t0_lote, 2)
    return {
        "lote_id": lote_id,
        "modo": "turbo_macro_ondas_pipelined",
        "tempo_total_s": tempo_total_s,
        "tempo_medio_por_video_s": round(tempo_total_s / max(1, len(lista_prompts_videos)), 2),
        "entregues": entregues_lista,
        "reprovados": reprovados_lista,
    }
