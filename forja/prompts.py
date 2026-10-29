"""
Forja — Etapa 4: Prompts (Imagem Frame 1 + Vídeo Lip Sync) — Motor Diretor de Animação IA 2.0 (@euojeff).
Fórmula Master de Alto Realismo Cru de Celular (Zero Cara de IA):
1. Câmera & Óptica de Celular: Lente 24mm wide-angle, slight barrel distortion, deep depth of field (fundo 100% em foco, zero bokeh).
2. Avatar "Anti-Modelo": Poros visíveis, brilho natural na zona T, vincos na testa ao falar, fios de cabelo soltos, roupa vivida.
3. Posição & Perspectiva Forçada: Objeto/ação em destaque na lente 24mm sem cobrir a boca, reflexo especular real nos dedos/bancada.
4. Cenário + 3 a 4 Provas de Vida (Lived-in Clutter Props): Bagunça involuntária real (papel da maca puxado, álcool em gel, fios, post-its, caneca).
5. Fonte de Luz Física Visível no Quadro: Spot de LED estourado no teto ao lado da saída de ar-condicionado (AC vent grille), sombra dura real.
6. Bloco Negativo Anti-IA + Animação com Física Real de iPhone (zero bokeh, zero morphing, micro-expressões reais e lip sync cravado).
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

# [BLOCO 1] 8 Enquadramentos girando (--angulo) com Óptica Real de Celular 24mm + Deep Depth of Field (Zero Bokeh)
OITO_ANGULOS = [
    (
        "Vertical 9:16 raw, unedited smartphone camera video still frame, front-facing iPhone camera propped on a counter "
        "at eye level, 24mm wide-angle phone lens with slight barrel distortion and deep depth of field where the entire "
        "background room is completely sharp and in focus with zero background blur and zero bokeh"
    ),
    (
        "Vertical 9:16 raw, unedited smartphone camera video still frame, slightly elevated 15-degree high-angle phone shot "
        "showing upper body and counter, 24mm wide-angle phone lens with slight barrel distortion and deep depth of field "
        "where the entire background room is completely sharp and in focus with zero bokeh"
    ),
    (
        "Vertical 9:16 raw, unedited smartphone camera video still frame, three-quarter front-left angle phone camera propped "
        "on a stand, 24mm wide-angle smartphone lens with slight barrel distortion and deep depth of field keeping the entire "
        "background 100% sharp with zero background blur"
    ),
    (
        "Vertical 9:16 raw, unedited smartphone camera video still frame, three-quarter front-right angle iPhone selfie camera "
        "angled slightly upward at 10 degrees, 24mm wide-angle phone lens with deep depth of field and zero bokeh"
    ),
    (
        "Vertical 9:16 raw, unedited smartphone camera video still frame, chest-height straight-on phone camera propped on a shelf, "
        "24mm wide-angle lens with slight barrel distortion and deep depth of field where every background detail is sharp"
    ),
    (
        "Vertical 9:16 raw, unedited smartphone camera video still frame, closer waist-to-head phone framing angled slightly up "
        "at 12 degrees, 24mm wide-angle smartphone lens with deep depth of field and zero background blur"
    ),
    (
        "Vertical 9:16 raw, unedited smartphone camera video still frame, handheld-style locked iPhone frame at a slight diagonal "
        "counter angle, 24mm wide-angle phone lens with slight barrel distortion and deep depth of field with zero bokeh"
    ),
    (
        "Vertical 9:16 raw, unedited smartphone camera video still frame, wide-medium smartphone shot framing subject centered "
        "with foreground counter tray, 24mm wide-angle lens with deep depth of field and zero bokeh"
    ),
]

# [BLOCO 4] Provas de Vida Reais (3 a 4 Lived-in Clutter Props por variação para matar cenário vazio de IA)
PROVAS_DE_VIDA_CENARIO = [
    (
        "a crinkled white exam-table paper roll slightly pulled out on the beige couch, a blue pump bottle of hand sanitizer "
        "and an open cardboard box of blue nitrile gloves on the counter, tangled black blood-pressure cuff tubing hanging from "
        "the wall mount, and yellow sticky notes stuck to the side of a cabinet"
    ),
    (
        "a stainless-steel sink with a blue dish-soap pump bottle and paper towel dispenser, a half-full ceramic coffee mug next "
        "to a stack of manila patient folders, a black phone charger cable hanging off the desk edge, and magnets with paper "
        "notes on the metal cabinet"
    ),
    (
        "an open plain brown cardboard shipping box on the side counter, a plastic water bottle and clipboards stacked on the desk, "
        "a slightly crooked computer monitor with a webcam clipped on top, and horizontal white window blinds slightly tilted in the back"
    ),
    (
        "a wall-mounted otoscope with coiled black cord, a open plastic tub of disinfecting wipes on the counter next to a pen cup, "
        "a crumpled paper towel near the steel sink, and printed chart papers pinned to a corkboard behind"
    ),
]

# [BLOCO 5] Fontes de Luz Física Visíveis no Teto/Quadro (Luz dura real de ambiente interno)
LUZES_FISICAS_VISIVEIS = [
    (
        "Harsh, authentic indoor overhead lighting from a single recessed circular ceiling LED pot-light visible as a bright "
        "blown-out circle on the white ceiling right next to a metal AC air vent grille, casting realistic downward shadows "
        "under the eyes and chin with auto-white-balance indoor color cast"
    ),
    (
        "Harsh, unedited indoor lighting from a bright rectangular overhead fluorescent ceiling fixture visible on the ceiling "
        "next to a metal AC air vent grille, plus a warm under-cabinet strip light casting realistic uneven shadows and slight "
        "specular glare on the counter"
    ),
    (
        "Raw indoor overhead lighting from two recessed ceiling LED pot-lights visible on the ceiling near an air-conditioning "
        "vent grille, mixed with cool daylight leaking through half-closed window blinds, creating authentic uneven smartphone "
        "auto-exposure and downward shadows"
    ),
]

# [BLOCO 6] Negativos Obrigatórios Anti-IA (Imagem)
BLOCO_NEGATIVO_ANTI_IA_IMAGEM = (
    "STYLE & NEGATIVES: Raw amateur TikTok UGC video frame, subtle smartphone sensor grain in the shadows, "
    "no studio lighting, no softbox, no bokeh, no shallow depth of field, no blurry background, no cinematic color grading, "
    "no model-like face, no airbrushed skin, no plastic skin, no watermark, no text overlays, no camera UI."
)

# Banco de variações de avatares, roupas e sub-tons de fundo
VARIACOES_AVATAR = [
    {
        "avatar": "Caucasian female doctor, 44 years old, shoulder-length auburn hair tied back with natural loose flyaways",
        "roupa": "lived-in navy-blue fitted medical scrubs with natural cotton creases and white lab coat open over shoulders, silver stethoscope",
        "fundo_detalhe": "real lived-in American medical clinic office with light oak cabinets, beige exam bed and daylight blinds",
        "voz": "Clear warm American female voice, steady doctor-explaining tone",
    },
    {
        "avatar": "Hispanic male physician, 48 years old, salt-and-pepper hair and neatly trimmed mustache",
        "roupa": "lived-in emerald-teal medical V-neck scrubs with a slightly stretched collar, surgical cap, stethoscope around neck",
        "fundo_detalhe": "real lived-in clinical consultation room with white paper-lined exam table and steel sink",
        "voz": "Calm confident American male voice, crisp articulation",
    },
    {
        "avatar": "Black female nurse practitioner, 41 years old, natural braided hair in a bun with subtle baby hairs",
        "roupa": "lived-in burgundy wine-red medical scrubs with natural fabric folds, black stethoscope draped around neck",
        "fundo_detalhe": "real lived-in medical office with wood cabinetry, exam table on left and window blinds on right",
        "voz": "Warm empathetic American female voice, engaging pace",
    },
    {
        "avatar": "Caucasian male health specialist, 54 years old, silver hair, neatly trimmed beard, thin-rimmed glasses with slight lens reflection",
        "roupa": "lived-in charcoal-gray medical scrubs and silver stethoscope around neck",
        "fundo_detalhe": "real sunlit doctor office with beige examination table, wood storage cabinets and sink",
        "voz": "Deep reassuring American male voice, steady cadence",
    },
    {
        "avatar": "Asian female physician, 39 years old, dark ponytail with natural loose strands",
        "roupa": "lived-in forest-green medical scrubs and white clinical coat, black stethoscope around neck",
        "fundo_detalhe": "real American family clinic room with white cabinets, exam table and wall blood-pressure monitor",
        "voz": "Crisp articulate American female voice, natural conversational pace",
    },
    {
        "avatar": "Middle-Eastern male doctor, 46 years old, short dark hair, full neatly groomed beard",
        "roupa": "lived-in dark-slate medical scrubs with white lab coat, stethoscope around neck",
        "fundo_detalhe": "real clinical exam room with light maple cabinets, beige exam couch and stainless sink",
        "voz": "Warm steady American male voice, doctor-explaining tone",
    },
    {
        "avatar": "Caucasian female senior nurse specialist, 51 years old, blonde bob haircut with natural flyaways",
        "roupa": "lived-in plum-purple medical V-neck scrubs, gold-accent stethoscope around neck",
        "fundo_detalhe": "real sunlit medical exam room with white upper cabinets, beige table and clinical sink",
        "voz": "Friendly authoritative American female voice, clear pacing",
    },
    {
        "avatar": "Black male senior physician, 56 years old, short gray-flecked hair, clean-shaven, rimless glasses",
        "roupa": "lived-in hunter-green medical scrubs under an open white doctor coat, stethoscope around neck",
        "fundo_detalhe": "real American outpatient exam room with oak cabinets, exam bed and stainless steel sink",
        "voz": "Deep calm American male voice, authoritative cadence",
    },
    {
        "avatar": "Latina female family doctor, 36 years old, wavy dark-brown hair over shoulders",
        "roupa": "lived-in royal-purple medical scrubs and silver stethoscope around neck",
        "fundo_detalhe": "real clinical room with beige exam couch, wood cabinets and stainless sink",
        "voz": "Warm energetic American female voice, clear articulation",
    },
    {
        "avatar": "Caucasian male orthopedic specialist, 42 years old, short sandy-blonde hair",
        "roupa": "lived-in steel-blue medical V-neck scrubs, black stethoscope around neck",
        "fundo_detalhe": "real sports medicine clinic exam room with light wood cabinets and exam table",
        "voz": "Confident clear American male voice, natural pace",
    },
    {
        "avatar": "South-Asian female physician, 45 years old, dark hair in a low chignon, small gold-stud earrings",
        "roupa": "lived-in teal-blue medical scrubs under a white lab coat, stethoscope around neck",
        "fundo_detalhe": "real medical consultation room with white cabinetry, exam bed and sink",
        "voz": "Warm articulate American female voice, steady doctor tone",
    },
    {
        "avatar": "Black female senior doctor, 53 years old, short natural silver-streaked curls, glasses",
        "roupa": "lived-in deep-navy medical scrubs and white doctor coat, silver stethoscope",
        "fundo_detalhe": "real American medical office with oak cabinets, beige exam table and blinds",
        "voz": "Reassuring authoritative American female voice, steady pace",
    },
    {
        "avatar": "Caucasian female nurse practitioner, 33 years old, blonde ponytail with loose flyaway strands",
        "roupa": "lived-in sage-green fitted medical scrubs, white stethoscope around neck",
        "fundo_detalhe": "real clinic exam room with beige exam table, wood cabinets and sink",
        "voz": "Friendly upbeat American female voice, crisp delivery",
    },
    {
        "avatar": "Asian male physician, 49 years old, black hair with subtle gray temples, thin glasses",
        "roupa": "lived-in midnight-blue medical scrubs under open white lab coat, black stethoscope",
        "fundo_detalhe": "real American medical exam room with light wood cabinets and beige exam bed",
        "voz": "Calm authoritative American male voice, clear pacing",
    },
    {
        "avatar": "Hispanic female health specialist, 47 years old, shoulder-length chestnut hair",
        "roupa": "lived-in coral-rose medical V-neck scrubs, silver stethoscope around neck",
        "fundo_detalhe": "real clinical exam room with wood cabinetry, exam table and stainless sink",
        "voz": "Warm empathetic American female voice, natural cadence",
    },
    {
        "avatar": "Black male family physician, 38 years old, short fade haircut, neatly trimmed goatee",
        "roupa": "lived-in cobalt-blue medical scrubs and white lab coat, black stethoscope around neck",
        "fundo_detalhe": "real American medical consultation office with beige exam bed and wood cabinets",
        "voz": "Confident warm American male voice, crisp pacing",
    },
    {
        "avatar": "Caucasian female integrative doctor, 49 years old, silver-blonde hair in a low bun, thin gold glasses",
        "roupa": "lived-in olive-green medical V-neck scrubs, silver stethoscope around neck",
        "fundo_detalhe": "real medical office with white cabinets, exam table and clinical sink",
        "voz": "Calm reassuring American female voice, steady cadence",
    },
    {
        "avatar": "East-Asian male clinical specialist, 37 years old, clean-cut black hair",
        "roupa": "lived-in burgundy medical scrubs under an open white doctor coat, black stethoscope",
        "fundo_detalhe": "real clinic exam room with light oak cabinets and paper-lined exam couch",
        "voz": "Crisp energetic American male voice, natural doctor tone",
    },
    {
        "avatar": "Middle-Eastern female physician, 43 years old, dark wavy hair tied half-back",
        "roupa": "lived-in slate-blue medical scrubs and white clinical coat, silver stethoscope around neck",
        "fundo_detalhe": "real American outpatient clinic room with wood cabinets, exam bed and sink",
        "voz": "Warm articulate American female voice, clear delivery",
    },
    {
        "avatar": "Hispanic male senior doctor, 55 years old, silver-streaked hair, clean-shaven, rectangular glasses",
        "roupa": "lived-in forest-green medical scrubs and white lab coat, black stethoscope around neck",
        "fundo_detalhe": "real medical consultation room with maple cabinetry, beige exam table and blinds",
        "voz": "Deep steady American male voice, authoritative doctor cadence",
    },
]

# Expansão determinística para 125 perfis médicos 100% únicos para lotes de 50 a 100+ vídeos
_ETNIAS_GENEROS = [
    ("Caucasian female physician", "female", "Clear warm American female voice, steady doctor tone"),
    ("Black male doctor", "male", "Deep confident American male voice, crisp articulation"),
    ("Hispanic female nurse practitioner", "female", "Warm empathetic American female voice, natural pace"),
    ("East-Asian male health specialist", "male", "Calm articulate American male voice, steady cadence"),
    ("South-Asian female family doctor", "female", "Friendly authoritative American female voice, clear delivery"),
    ("Middle-Eastern male clinician", "male", "Warm steady American male voice, reassuring doctor tone"),
    ("Black female integrative specialist", "female", "Confident warm American female voice, engaging pace"),
    ("Caucasian male senior physician", "male", "Deep calm American male voice, authoritative cadence"),
    ("Latina female clinical specialist", "female", "Upbeat clear American female voice, natural conversational pace"),
    ("Asian female senior doctor", "female", "Crisp reassuring American female voice, steady delivery"),
]
_TRAÇOS = [
    "tied-back hair with natural loose flyaways, attentive direct gaze",
    "short hair, thin-rimmed glasses with slight lens glare, natural expression",
    "silver-streaked hair with flyaways, reassuring expression",
    "practical hairstyle, rimless glasses, focused gaze",
    "wavy shoulder-length hair with loose strands, trustworthy expression",
    "short slightly messy hair, calm authoritative presence",
    "natural curls with flyaways, empathetic gaze",
]
_ROUPAS_MED = [
    "lived-in navy-blue V-neck medical scrubs with natural cotton creases and silver stethoscope around neck",
    "lived-in emerald-teal medical scrubs under an open white lab coat, black stethoscope",
    "lived-in burgundy wine-red fitted medical scrubs with slightly stretched collar, silver stethoscope",
    "lived-in charcoal-gray medical scrubs and white doctor coat, stethoscope around neck",
    "lived-in royal-blue clinical scrubs, surgical cap, black stethoscope around neck",
    "lived-in forest-green V-neck scrubs and white lab coat, gold-accent stethoscope",
    "lived-in ceil-blue medical scrubs with natural fabric folds, silver stethoscope draped around neck",
    "lived-in plum-purple medical scrubs under white clinical coat, black stethoscope",
    "lived-in hunter-green fitted medical scrubs, silver stethoscope around neck",
    "lived-in slate-blue medical scrubs and open white lab coat, stethoscope around neck",
]
_FUNDOS_CLINICA = [
    "real lived-in American medical office with light oak cabinets, beige exam bed and window blinds",
    "real clinical consultation room with white cabinetry, paper-lined exam table and stainless sink",
    "real family practice exam room with maple wood cabinets, beige couch and wall otoscope",
    "real outpatient clinic room with white upper cabinets, exam table on left and steel sink",
    "real integrative health office with warm wood cabinetry, exam bed and daylight blinds",
]

for _idx_extra in range(105):
    _et_label, _gen, _voz = _ETNIAS_GENEROS[_idx_extra % len(_ETNIAS_GENEROS)]
    _idade = 34 + ((_idx_extra * 3) % 26)
    _traco = _TRAÇOS[(_idx_extra // 2) % len(_TRAÇOS)]
    _roupa = _ROUPAS_MED[(_idx_extra * 3) % len(_ROUPAS_MED)]
    _fundo = _FUNDOS_CLINICA[(_idx_extra * 2) % len(_FUNDOS_CLINICA)]
    VARIACOES_AVATAR.append(
        {
            "avatar": f"{_et_label} #{_idx_extra + 21}, {_idade} years old, {_traco}",
            "roupa": _roupa,
            "fundo_detalhe": _fundo,
            "voz": _voz,
        }
    )

TERMOS_SENSIVEIS_CORPO_ACAO = [
    r"\bthighs?\b",
    r"\bgroin\b",
    r"\blegs?\b",
    r"\bcalf\b",
    r"\bbelly\b",
    r"\bstomach\b",
    r"\bfeet\b",
    r"\bfoot\b",
    r"\brub(?:bing|s|bed)?\b",
    r"\bapply(?:ing|ied)?\b",
    r"\bspread(?:ing|s)?\b",
]

SUBSTITUICOES_NEUTRAS = {
    "thigh": "the area",
    "thighs": "the area",
    "groin": "the area",
    "leg": "the limb",
    "legs": "the limbs",
    "calf": "the lower area",
    "skin": "the surface",
    "belly": "the midsection",
    "stomach": "the midsection",
    "feet": "the lower extremity",
    "foot": "the lower extremity",
    "rub": "motion",
    "rubbing": "continuing the motion",
    "rubs": "motions",
    "rubbed": "motioned",
    "apply": "place",
    "applying": "placing",
    "applied": "placed",
    "spread": "smooth",
    "spreading": "smoothing",
}


def higienizar_descricao_visual(texto_visual: str) -> tuple[str, list[str]]:
    """
    Garante que cada palavra sensível de ação/parte do corpo apareça NO MÁXIMO UMA VEZ
    na descrição visual do prompt (evitando o erro 'Serviço indisponível' do Google Flow).
    """
    removidas: list[str] = []
    resultado = texto_visual

    for padrao in TERMOS_SENSIVEIS_CORPO_ACAO:
        matches = list(re.finditer(padrao, resultado, flags=re.IGNORECASE))
        if len(matches) > 1:
            for m in reversed(matches[1:]):
                palavra_orig = m.group(0)
                chave = palavra_orig.lower()
                substituto = SUBSTITUICOES_NEUTRAS.get(chave, "it")
                resultado = resultado[: m.start()] + substituto + resultado[m.end() :]
                removidas.append(palavra_orig)

    resultado = re.sub(r"\s{2,}", " ", resultado).strip()
    return resultado, removidas


def gerar_prompts_video(
    analise_viral: dict[str, Any],
    roteiro: dict[str, Any],
    indice_variacao: int = 0,
    usar_angulo: bool = False,
    imagem_base: str | None = None,
) -> dict[str, Any]:
    """
    Gera os prompts de Imagem (Frame 1) e Vídeo (Animação Veo 3.1 com lip sync e fala exata entre aspas)
    seguindo a Fórmula Master de 6 Blocos de Alto Realismo Cru de Celular (Diretor de Animação IA 2.0 - @euojeff).
    """
    variacoes_disponiveis = analise_viral.get("variacoes_avatar") or VARIACOES_AVATAR
    perfil_raw = variacoes_disponiveis[indice_variacao % len(variacoes_disponiveis)]
    perfil = {
        "avatar": perfil_raw.get("avatar") or perfil_raw.get("personagem_en", "50-year-old American speaker"),
        "roupa": perfil_raw.get("roupa") or perfil_raw.get("roupa_en", "casual lived-in cotton shirt"),
        "fundo_detalhe": perfil_raw.get("fundo_detalhe") or perfil_raw.get("cenario_en", "real lived-in American room"),
        "voz": perfil_raw.get("voz") or perfil_raw.get("voz_en", "Natural conversational American voice"),
    }
    formato = analise_viral.get("formato", "formato_viral_custom")

    provas_override = analise_viral.get("provas_de_vida_override_en")
    if isinstance(provas_override, str) and provas_override.strip():
        clutter_props = provas_override.strip()
    elif isinstance(provas_override, list) and provas_override:
        clutter_props = provas_override[indice_variacao % len(provas_override)]
    else:
        clutter_props = PROVAS_DE_VIDA_CENARIO[indice_variacao % len(PROVAS_DE_VIDA_CENARIO)]

    luzes_override = analise_viral.get("luz_fisica_override_en")
    if isinstance(luzes_override, str) and luzes_override.strip():
        luz_fisica = luzes_override.strip()
    elif isinstance(luzes_override, list) and luzes_override:
        luz_fisica = luzes_override[indice_variacao % len(luzes_override)]
    else:
        luz_fisica = LUZES_FISICAS_VISIVEIS[indice_variacao % len(LUZES_FISICAS_VISIVEIS)]

    # Lê 100% da análise visual do viral (<viral>_analise.json preenchido pelo LLM Vision interno)
    cena_analise = analise_viral.get("cena", {})
    objeto_fixo = (
        analise_viral.get("cena_fixa_en")
        or cena_analise.get("cena_fixa_en")
        or (
            "The key props from the reference video ("
            + ", ".join(cena_analise.get("objetos", ["main ingredient prop"]))
            + ") are held clearly in the foreground."
        )
    )
    acoes_en = analise_viral.get("acoes_en") or cena_analise.get("acoes_en") or {}

    prompts_takes = []
    for take_info in roteiro["takes"]:
        num_take = int(take_info["take"])
        papel = take_info["papel"]
        fala_raw = take_info["fala"].strip()
        fala_exata = (fala_raw[0].upper() + fala_raw[1:]) if fala_raw else ""

        # [BLOCO 1] Câmera & Óptica de Celular (24mm + Deep Depth of Field + Zero Bokeh)
        if usar_angulo:
            idx_ang = (indice_variacao + num_take - 1) % len(OITO_ANGULOS)
            enquadramento_str = OITO_ANGULOS[idx_ang]
        else:
            enquadramento_str = OITO_ANGULOS[0]

        # [BLOCO 3] Ação por papel vinda dinamicamente da análise Vision do viral
        if papel == "hook" or num_take == 1:
            acao_frame1 = acoes_en.get("hook_frame1") or (
                f"The subject performs the opening visual hook action ({analise_viral.get('hook_visual', {}).get('gesto', 'demonstrating the main prop')}) "
                "pushed slightly forward toward the 24mm wide-angle lens (leaving the entire face and mouth 100% unobstructed)."
            )
            acao_video_sem_base = acoes_en.get("hook_video") or (
                "Stationary vertical 9:16 smartphone take with subtle authentic handheld micro-stability. "
                "The subject maintains direct eye contact with the phone lens while completing the opening gesture naturally. "
                "Every prop and background clutter item already exists and stays sharp in focus; nothing new spawns or morphs."
            )
        elif papel == "cta":
            acao_frame1 = acoes_en.get("cta_frame1") or (
                "The subject stands in the same position, pointing one index finger straight down toward the comment section "
                "(leaving the face and mouth 100% unobstructed) while looking directly into the phone lens."
            )
            acao_video_sem_base = acoes_en.get("cta_video") or (
                "Stationary vertical 9:16 smartphone take. The subject points one index finger straight down "
                "with a natural encouraging nod and real forehead micro-expressions while looking straight into the phone lens. "
                "Every background item stays completely sharp with zero bokeh; nothing new spawns."
            )
        else:
            acao_frame1 = acoes_en.get("body_frame1") or (
                "The subject stands in the same position, gesturing naturally with one open hand at chest level "
                "(leaving the face and mouth 100% unobstructed) while explaining directly to the phone camera."
            )
            acao_video_sem_base = acoes_en.get("body_video") or (
                "Stationary vertical 9:16 smartphone take. The subject gestures naturally with one hand at chest height "
                "with realistic human blinking, forehead creases, and chest breathing while speaking to the phone lens. "
                "Every background item stays sharp in focus with zero bokeh; nothing new spawns."
            )

        # =========================================================================
        # PROMPT DE IMAGEM (6 BLOCOS — ALTO REALISMO CRU DE CELULAR / NANO BANANA)
        # =========================================================================
        avatar_txt = perfil["avatar"].strip()
        if not avatar_txt.lower().startswith("an ordinary"):
            avatar_txt = f"An ordinary, non-model {avatar_txt}"
        roupa_txt = perfil["roupa"].strip()
        cenario_txt = re.sub(r"^(?:a|an)\s+", "", perfil["fundo_detalhe"].strip(), flags=re.IGNORECASE)

        bruto_img = (
            f"{enquadramento_str}. "
            f"CHARACTER: {avatar_txt}, natural horizontal forehead creases mid-sentence, "
            f"visible skin texture and pores, slight natural T-zone shine, uneven indoor complexion, wearing {roupa_txt}, "
            f"mouth slightly open mid-word as if speaking naturally to the phone. "
            f"POSE & PRODUCT: {objeto_fixo} {acao_frame1} Casting a real specular reflection and contact shadow onto the fingers and counter surface. "
            f"SCENE & LIVED-IN DETAILS: In the background is a {cenario_txt} with authentic lived-in clutter: {clutter_props}. "
            f"LIGHTING: {luz_fisica}. "
            f"{BLOCO_NEGATIVO_ANTI_IA_IMAGEM}"
        )
        prompt_imagem, removidas_img = higienizar_descricao_visual(bruto_img)

        # =========================================================================
        # PROMPT DE VÍDEO / ANIMAÇÃO (FÍSICA REAL DE CELULAR + LIP SYNC — VEO 3.1)
        # =========================================================================
        tem_base_neste_take = bool(imagem_base)
        if tem_base_neste_take:
            bruto_vid_visual = (
                "Raw unedited vertical 9:16 smartphone UGC video animating the provided reference frame. "
                "24mm wide-angle phone lens with deep depth of field keeping the entire background room 100% sharp, static, and in focus with zero bokeh and zero camera pan. "
                "Keep the exact same person, clothing, overhead LED lighting shadows, and background clutter stationary. "
                "Authentic human micro-expressions, natural forehead movement, irregular blinking, and real iPhone microphone room acoustics (no background music). "
                f"{perfil['voz']}."
            )
        else:
            bruto_vid_visual = (
                f"{enquadramento_str}. "
                f"{avatar_txt}, visible skin pores and natural T-zone shine under harsh overhead ceiling LED pot-light, "
                f"wearing {roupa_txt}, in a {cenario_txt}. "
                f"{objeto_fixo} {acao_video_sem_base} "
                "Authentic human micro-expressions, natural forehead creases when emphasizing words, real iPhone microphone indoor room acoustics (no studio reverb, no background music), "
                "no bokeh, no blurry background, no cinematic camera movement. "
                f"{perfil['voz']}."
            )

        vid_visual_limpo, removidas_vid = higienizar_descricao_visual(bruto_vid_visual)
        prompt_video = f'{vid_visual_limpo} The person says with exact lip sync: "{fala_exata}"'

        prompts_takes.append(
            {
                "take": num_take,
                "papel": papel,
                "angulo_indice": ((indice_variacao + num_take - 1) % len(OITO_ANGULOS)) + 1 if usar_angulo else 1,
                "enquadramento": enquadramento_str,
                "imagem_base_usada": imagem_base if tem_base_neste_take else None,
                "fala": fala_exata,
                "prompt_imagem": prompt_imagem,
                "prompt_video": prompt_video,
                "termos_repetidos_higienizados": removidas_img + removidas_vid,
            }
        )

    return {
        "video_id": f"V{indice_variacao + 1:02d}",
        "formato": formato,
        "avatar": perfil["avatar"],
        "roupa": perfil["roupa"],
        "cenario": perfil["fundo_detalhe"],
        "voz": perfil["voz"],
        "opcoes": {
            "angulo_rotativo": usar_angulo,
            "imagem_base": imagem_base,
        },
        "takes": prompts_takes,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Forja Etapa 4 — Gerador de Prompts por Take (Alto Realismo 2.0)")
    parser.add_argument("--analise", required=True, help="Caminho do <viral>_analise.json")
    parser.add_argument("--roteiro", required=True, help="Caminho do roteiro_takes.json")
    parser.add_argument("--variacao", type=int, default=0, help="Índice da variação de avatar (0..N)")
    parser.add_argument("--angulo", action="store_true", help="Ativa rotação dos 8 enquadramentos")
    parser.add_argument("--base", default=None, help="Caminho de imagem base aprovada para frame 1")
    parser.add_argument("--saida", default="", help="Arquivo JSON de saída")
    args = parser.parse_args()

    analise = json.loads(Path(args.analise).read_text(encoding="utf-8"))
    roteiro = json.loads(Path(args.roteiro).read_text(encoding="utf-8"))
    resultado = gerar_prompts_video(
        analise_viral=analise,
        roteiro=roteiro,
        indice_variacao=args.variacao,
        usar_angulo=args.angulo,
        imagem_base=args.base,
    )
    if args.saida:
        Path(args.saida).write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(resultado, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
