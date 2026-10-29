"""
Forja — Seletores centralizados do Google Flow.
REGRA ESTRITA: Localizar botões APENAS pelo texto ou aria-label/role, NUNCA por posição (x,y) ou classe CSS (.class).
Todos os seletores ficam neste único arquivo para manutenção imediata quando a interface mudar.
"""

from __future__ import annotations

FLOW_PROJECT_URL_PATTERN = r"^https://flow\.google\.com/project/[0-9a-f-]{36}/?$"
FLOW_BASE_URL = "https://flow.google.com/"

MODELO_IMAGEM_PADRAO = "Nano Banana 2.1"
MODELO_VIDEO_PADRAO = "Veo 3.1 - Lite [Lower Priority]"

SELETORES_FLOW: dict[str, list[str]] = {
    "botao_novo_projeto": [
        'button:has-text("Novo projeto")',
        'button:has-text("New project")',
        'button[aria-label*="Novo projeto" i]',
        'button[aria-label*="New project" i]',
    ],
    "link_abrir_projeto": [
        'a[aria-label="Abrir projeto"]',
        'a[aria-label="Open project"]',
        'a[href^="/project/"]',
        'a[href*="/project/"]',
    ],
    "botao_configuracoes": [
        'button[aria-label="Gatilho de configurações"]',
        'button[aria-label="Settings trigger"]',
        'button[aria-label*="configurações" i]',
        'button[aria-label*="Settings" i]',
    ],
    "seletor_modelo": [
        'button[aria-label="Selecionar família de modelos"]',
        'button[aria-label="Select model family"]',
        'button[aria-label*="família de modelos" i]',
        'button[aria-label*="model family" i]',
    ],
    "item_menu_modelo": [
        '[role="menuitem"]',
        '[role="option"]',
        '[role="menuitemradio"]',
    ],
    "modo_imagem": [
        'button[role="radio"]:has-text("Imagem")',
        'button[role="radio"]:has-text("Image")',
        '[role="radio"]:has-text("Imagem")',
        '[role="radio"]:has-text("Image")',
    ],
    "modo_video": [
        'button[role="radio"]:has-text("Vídeo")',
        'button[role="radio"]:has-text("Video")',
        '[role="radio"]:has-text("Vídeo")',
        '[role="radio"]:has-text("Video")',
    ],
    "submodo_frames": [
        'button[role="radio"]:has-text("Frames")',
        '[role="radio"]:has-text("Frames")',
    ],
    "submodo_elementos": [
        'button[role="radio"]:has-text("Elementos")',
        'button[role="radio"]:has-text("Elements")',
        'button[role="radio"]:has-text("Ingredients")',
    ],
    "proporcao_9_16": [
        'button[role="radio"]:has-text("9:16")',
        '[role="radio"]:has-text("9:16")',
        'button[aria-label*="9:16" i]',
    ],
    "resolucao_720p": [
        'button[role="radio"]:has-text("720p")',
        '[role="radio"]:has-text("720p")',
    ],
    "duracao_8s": [
        'button[role="radio"]:has-text("8s")',
        '[role="radio"]:has-text("8s")',
    ],
    "quantidade_x1": [
        'button[role="radio"]:has-text("x1")',
        '[role="radio"]:has-text("x1")',
    ],
    "quantidade_x4": [
        'button[role="radio"]:has-text("x4")',
        '[role="radio"]:has-text("x4")',
    ],
    "caixa_prompt": [
        'div[role="textbox"][aria-label="O que você quer criar?"]',
        'div[role="textbox"][aria-label="What do you want to create?"]',
        'div[role="textbox"]',
        'textarea[aria-label*="criar" i]',
        'textarea[aria-label*="create" i]',
    ],
    "botao_frame_inicio": [
        'button:has-text("Início")',
        'button:has-text("Start")',
    ],
    "botao_adicionar_ingrediente": [
        'button[aria-label="Adicionar elementos à caixa de comando"]',
        'button[aria-label="Adicionar ingredientes à caixa de comando"]',
        'button[aria-label="Add ingredients to the prompt box"]',
        'button[aria-label*="caixa de comando" i]',
        'button[aria-label*="prompt box" i]',
    ],
    "botao_upload_arquivo": [
        'button:has-text("Enviar mídia")',
        'button:has-text("Upload media")',
        'button:has-text("Upload")',
        'button:has-text("Enviar")',
    ],
    "botao_adicionar_ao_prompt": [
        'button:has-text("Incluir no comando")',
        'button:has-text("Add to prompt")',
        'button:has-text("Adicionar ao comando")',
        'button[aria-label*="Incluir no comando" i]',
        'button[aria-label*="Add to prompt" i]',
    ],
    "botao_remover_ingrediente": [
        'button[aria-label*="Remove" i]',
        'button[aria-label*="Remover" i]',
        'button[aria-label*="Excluir" i]',
        'button[aria-label*="Limpar" i]',
        'button:has-text("close")',
    ],
    "botao_iniciar_geracao": [
        'button[aria-label="Iniciar geração"]',
        'button[aria-label="Start generation"]',
        'button:has-text("arrow_forward")',
    ],
    "botao_baixar_midia": [
        'button[aria-label="Baixar mídia"]',
        'button[aria-label="Download media"]',
        'button[aria-label*="Baixar" i]',
        'button[aria-label*="Download" i]',
    ],
    "opcao_download_720p": [
        '[role="menuitem"]:has-text("720p")',
        'button:has-text("720p")',
        '[role="menuitem"]:has-text("Original")',
    ],
    "botao_concluido_detalhe": [
        'button:has-text("Concluído")',
        'button:has-text("Done")',
    ],
    "indicador_progresso": [
        '[role="progressbar"]',
        '[aria-busy="true"]',
        '[aria-label*="Gerando" i]',
        '[aria-label*="Generating" i]',
    ],
    "alertas_sistema": [
        '[role="alert"]',
        '[role="dialog"]',
        '[aria-live="assertive"]',
        '[aria-live="polite"]',
    ],
    "imagens_geradas": [
        'img[alt*="Bloco mostrando a imagem" i]',
        'img[alt*="Tile showing user image" i]',
        'img[src*="flow-content.google/image/"]',
    ],
    "miniaturas_video_gerado": [
        'img[src*="signature="]',
        'img[alt*="Miniatura do vídeo" i]',
        'img[alt*="video thumbnail" i]',
        'img[alt*="Generated video" i]',
    ],
}

MARCADORES_ATIVIDADE_INCOMUM = (
    "atividade incomum",
    "unusual activity",
    "notamos uma atividade incomum",
    "verifique se você é humano",
    "verify you are human",
    "captcha",
    "recaptcha",
)

MARCADORES_SERVICO_INDISPONIVEL = (
    "serviço de geração de imagens está indisponível",
    "image generation service unavailable",
    "service unavailable",
    "serviço indisponível",
    "too much traffic",
    "rate limit",
)
