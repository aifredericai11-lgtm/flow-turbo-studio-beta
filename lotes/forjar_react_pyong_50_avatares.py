#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
MOTOR REACT TELA DIVIDIDA ESTILO PYONG LEE V2 — REALISMO FUSÃO SUPREMA V2 + AD06 JSON
=====================================================================================
Corrigido 100% conforme feedback do operador:
1. REALISMO MÁXIMO (`realismo-e-animacao-universal` / `Fusão Suprema V2` em 3 parágrafos + `avatar-realista` + `Diretor Biomecânico Causal AD06` JSON de 11 blocos):
   - `F1_talking.jpg` (`720x1280`): Gerado DO ZERO (`refs=[]`) com os 3 parágrafos de realismo iPhone (`IMPORTANT: THIS IS IPHONE FOOTAGE!!`, estrutura óssea, pele de baixa amplitude sem filtro plástico, luz de janela/teto com autoexposure bloom real, óptica 24mm sem bokeh falso e cor neutra crua).
   - `F2_watching_phone.jpg` (`720x1280`): Gerado com `refs=[f1_id]` mantendo 100% a mesma pessoa, roupa fosca e ambiente, olhando para a tela do celular na mão com **expressão calma, séria, focada e natural igual ao Pyong** (lábios fechados relaxados, ZERO olhos esbugalhados, ZERO sorriso forçado de IA).
2. ESTRUTURA E FLUXO IDÊNTICOS AO PYONG (`Video by pyonglee.mp4`):
   - PARTE 1 — HOOK DE INÍCIO (`0.0s .. ~2.0s`, Tela Dividida):
     * Topo (`y=0..764`): Quadro inicial da receita com a Caixa de Citação Estilo Pyong (ícone verde `“` + faixas brancas uppercase).
     * Base (`y=716..1280`, CROP 1:1 `720x564` cortado de `y=140..704` do `720x1280`, ZERO achatamento!): Avatar olha para a câmera, levanta brevemente o indicador apontando para o vídeo de cima e fala apenas o Hook curto do Pyong em inglês:
       "Have you seen this video that just went viral?" (~2.0s).
   - PARTE 2 — VÍDEO DE RECEITA 100% COMPLETO + REACT SILENCIOSO SEM REVERSO (`~2.0s .. fim total da receita`):
     * Topo (`y=0..764`): O vídeo de receita original de `07_REACT_RCLONE` toca **100% INTEIRO do segundo `0.00s` até o último segundo (`dur_viral` completo, sem jamais cortar no meio!)** com seu áudio original.
     * Base (`y=716..1280`, CROP 1:1 `720x564` sem achatar): O avatar **NÃO FALA NADA** durante o vídeo — apenas assiste ao celular com reações humanas sutis e calmas igual ao Pyong (olhar atento acompanhando a tela, leve arquear de sobrancelha, micro-aceno sutil de cabeça com boca fechada). Os cortes de reação (1 a 3 cortes diretos) repetem em **ordem normal para frente (ZERO reverso / ZERO ping-pong!)**.
   - PARTE 3 — FINAL TELA CHEIA COM CTA (`últimos ~3.5s` APÓS a receita terminar 100%, `720x1280` Tela Cheia):
     * Corta para o avatar em **TELA CHEIA (`720x1280`)** com o botão **`FOLLOW FOR MORE ↓`** centralizado na base (igual ao `SIGA PARA MAIS ↓` do Pyong), falando:
       "Try this natural recipe at home, and follow for more daily health tips."
3. 50 Avatares Fixos Únicos (Homens e Mulheres Brancos e Asiático-Americanos estilo Pyong — zero negros conforme instrução).
"""
from __future__ import annotations

import argparse
import concurrent.futures
from datetime import datetime
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import time
from typing import Any
import urllib.request as _ur

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

cv2.setNumThreads(1)
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = pathlib.Path(r"c:\Users\JeffP\OneDrive\Área de Trabalho\Nova pasta")
SCRATCH = ROOT / "scratch"
for p_s in (str(ROOT), str(SCRATCH)):
    if p_s not in sys.path:
        sys.path.insert(0, p_s)

from forja.flow_rpc_direto import (
    aguardar_midia_rpc,
    gerar_imagem_rpc,
    gerar_video_rpc,
    gerar_videos_lote_rpc,
    listar_contas_flow_ativas,
    recarregar_aba_flow_anti_traffic,
    subir_midia_rpc,
    usar_conta_flow,
)
from forja.qa_clipe import obter_metadados_midia, transcrever_com_palavras
from motor_turbo_lote20_core import (
    ARTIFACTS_DIR,
    DRIVE_COFRE_IMUTAVEL,
    DRIVE_ROOT_BASE,
    FFMPEG_BIN,
    HUB_OUT_BASE,
    IMG_SEM,
    MODELO_VIDEO_LP,
    NVENC_SEM,
    WHISPER_LOCK,
)

RCLONE_DIR = pathlib.Path(r"H:\Meu Drive\HUB CENTRAL OP ORGÂNICO\07_REACT_RCLONE")
MAT_DIR = pathlib.Path(r"C:\Hub001\MATRIZES_VIRAIS_1611\react_pyong_50")
MAT_DIR.mkdir(parents=True, exist_ok=True)

AVATARS_BANK_DIR = pathlib.Path(r"C:\Hub001\AVATARES_FIXOS_REACT_50_V2")
AVATARS_BANK_DIR.mkdir(parents=True, exist_ok=True)

ESTEIRA_REACT_BASE = pathlib.Path(r"C:\Hub001\VIDEOS_ESTEIRA_TREE\US\WL\REACT\C01\G00")
ESTEIRA_REACT_BASE.mkdir(parents=True, exist_ok=True)

TODAY_STR = f"{datetime.now():%Y-%m-%d}"
FOLDER_LABEL = "LOTE_105__REACT_PYONG_50_AVATARES__07_REACT_RCLONE"
COFRE_FOLDER_NAME = "REACT_PYONG_50_AVATARES_RCLONE_105"

# Hooks curtos idênticos ao Pyong ("Você já viu esse vídeo que viralizou?" ~2.0s–2.5s)
# TRAVA ESTRITA DO REVISOR WHISPER: `must_end_any` exige OBRIGATORIAMENTE a última palavra real da frase ("viral" / "recipe")!
PYONG_HOOKS_EN = [
    {"fala": "Have you seen this video that just went viral?", "must_end_any": ["viral"]},
    {"fala": "Did you see this recipe video that just went viral?", "must_end_any": ["viral"]},
    {"fala": "Have you seen this natural trick that went viral?", "must_end_any": ["viral"]},
    {"fala": "Wait, have you seen this video that just went viral?", "must_end_any": ["viral"]},
    {"fala": "Have you seen why this home recipe just went viral?", "must_end_any": ["viral"]},
]

OUTRO_CTA_SPECS = [
    {"fala": "Try this natural recipe at home, and follow for more daily health tips.", "must_end_any": ["tips"]},
    {"fala": "Save this natural recipe to try at home, and follow for more daily health tips.", "must_end_any": ["tips"]},
]

# 50 Avatares Fixos Únicos com Estrutura Óssea Completa (Fusão Suprema V2 — Homens e Mulheres Brancos + Asiático-Americanos estilo Pyong)
AVATARES_50_SPECS: list[dict[str, str]] = [
    # 1: Homem Asiático-Americano estilo Pyong Lee (Piloto #1!)
    {
        "gender": "male",
        "age": "36",
        "person": "East-Asian American man with straight dark-black medium-short hair parted naturally on the left with a few loose strands across his forehead, dark-brown eyes, broad forehead, defined cheekbones, straight nose, smooth clean-shaven jawline, and natural unstyled eyebrows",
        "role": "everyday American wellness and health creator",
        "shirt": "a matte washed-black cotton crew-neck t-shirt with natural lived-in fabric folds",
        "room": "an ordinary lived-in American apartment living room with vertical off-white curtain blinds behind him and soft directional daylight from a side window on the right",
    },
    # 2: Mulher Branca 41 anos
    {
        "gender": "female",
        "age": "41",
        "person": "Caucasian American woman with dark chestnut-brown shoulder-length hair pulled back casually with a matte claw clip leaving loose flyaway strands at the temples, warm hazel-brown eyes, oval face, defined cheekbones, straight nose, and natural unstyled eyebrows",
        "role": "everyday middle-class American mom and home wellness enthusiast",
        "shirt": "a matte heather-grey ribbed cotton henley t-shirt with subtle fabric weave",
        "room": "an ordinary lived-in American home kitchen with neutral off-white shaker cabinets, a stainless faucet, and a bright side window clipping naturally into soft white daylight bloom",
    },
    # 3: Homem Branco 47 anos
    {
        "gender": "male",
        "age": "47",
        "person": "Caucasian American man with short brushed-back salt-and-pepper brown hair, blue-grey eyes, broad forehead with subtle horizontal expression lines, square jawline with light natural 5-o'clock stubble, and straight nose",
        "role": "everyday American physical therapist and dad",
        "shirt": "a matte slate-blue washed cotton crew-neck t-shirt",
        "room": "a lived-in American home dining room with off-white walls, a wooden bookshelf at 2m depth, and a bright side window casting natural directional daylight",
    },
    # 4: Mulher Branca 46 anos
    {
        "gender": "female",
        "age": "46",
        "person": "Caucasian American woman with honey-blonde chin-length bob hair with a natural side part and fine flyaway strands, soft green-blue eyes, high cheekbones, soft jawline, and honest crow's feet around the eyes",
        "role": "everyday American registered nurse and nutrition reader",
        "shirt": "a matte sage-olive washed cotton V-neck top",
        "room": "an everyday American kitchen with matte cream cabinets, a black drip coffee maker on the back counter, and an overhead ceiling fixture clipping into soft white bloom",
    },
    # 5: Homem Branco 52 anos
    {
        "gender": "male",
        "age": "52",
        "person": "Caucasian American man with short sandy-brown hair with silver temples, thin rectangular eyeglasses, warm brown eyes, defined cheekbones, and a neatly trimmed short salt-and-pepper beard",
        "role": "ordinary middle-class American health researcher",
        "shirt": "a matte charcoal-grey cotton polo shirt with zero gloss",
        "room": "a lived-in American home office with neutral beige walls, framed certificates at 2m depth, and directional window daylight from the left",
    },
    # 6..50: Mais 45 avatares brancos (mulheres e homens 34..60 anos) com estrutura óssea detalhada
]

_EXTRA_PEOPLE = [
    ("female", "38", "Caucasian American woman with medium auburn-brown straight hair tucked behind her ears with wispy flyaway strands, hazel eyes, heart-shaped face, defined cheekbones, and straight nose", "a matte oatmeal-beige fine knit short-sleeve top", "a bright American living room with sheer white window curtains and a potted green plant in the background"),
    ("female", "51", "Caucasian American woman with ash-blonde shoulder-length bob hair with subtle silver highlights, thin wire-frame glasses, soft blue eyes, oval face, and natural laugh lines", "a matte dusty-plum washed cotton crew-neck t-shirt", "a lived-in American kitchen with oak wood cabinets and natural window daylight"),
    ("male", "44", "Caucasian American man with short dark-brown hair, clean-shaven angular jawline, green-hazel eyes, broad forehead, and natural eyebrows", "a matte navy-blue washed cotton crew-neck t-shirt", "an ordinary American living room with vertical off-white blinds and directional daylight"),
    ("female", "49", "Caucasian American woman with chestnut-brown hair in a casual low ponytail with temple flyaways, warm dark-brown eyes, defined cheekbones, and soft jawline", "a matte dusty-rose washed cotton t-shirt", "a sunlit American kitchen with white tile backsplash and matte ceramic mugs on the counter"),
    ("male", "55", "Caucasian American man with closely cropped silver-grey hair, warm hazel eyes, broad forehead, and a neatly trimmed short grey-brown beard", "a matte sage-green cotton henley shirt", "a lived-in American home kitchen with neutral off-white cabinets and an overhead ceiling lamp"),
    ("female", "35", "Caucasian American woman with golden-blonde hair in a casual half-up clip, blue eyes, fair skin with subtle natural freckles on the nose bridge, and defined cheekbones", "a matte washed-charcoal cotton crew-neck t-shirt", "a bright American apartment living room with white bookshelves and side window light"),
    ("female", "54", "Caucasian American woman with silver-streaked light-brown bob hair, tortoiseshell reading glasses, blue-grey eyes, and honest expression lines", "a matte slate-blue cotton blouse", "a classic American kitchen with cream shaker cabinets and stainless refrigerator in the back"),
    ("male", "42", "Caucasian American man with wavy medium-brown hair, light facial stubble, blue eyes, straight nose, and square jawline", "a matte heather-taupe crew-neck cotton t-shirt", "a bright American dining area with a large daylight window on the side"),
    ("female", "43", "Caucasian American woman with light caramel-brown shoulder-length hair with center part, green eyes, oval face, and high cheekbones", "a matte cream-white ribbed cotton t-shirt", "a contemporary American kitchen with light grey cabinets and marble counter in the back"),
    ("male", "50", "Caucasian American man with receding salt-and-pepper hair, rimless glasses, clean-shaven jaw, brown eyes, and natural forehead lines", "a matte dark steel-blue polo shirt", "a lived-in American home office with books and soft window daylight"),
    ("female", "48", "Caucasian American woman with strawberry-blonde medium bob hair, thin round metal glasses, green-blue eyes, and light natural freckles", "a matte forest-green washed cotton t-shirt", "a cozy American living room with off-white walls and a table lamp in the background"),
    ("female", "57", "Caucasian American woman with short silver-blonde bob hair, warm brown eyes, defined cheekbones, and friendly natural crow's feet", "a matte soft-teal washed cotton top", "a bright American sunroom/kitchen with white window frames"),
    ("male", "39", "East-Asian American man with short textured black hair, warm dark-brown eyes, clean-shaven face, defined cheekbones, and straight nose", "a matte charcoal-slate crew-neck t-shirt", "a minimalist American apartment living room with sheer white curtains and daylight"),
    ("female", "45", "Caucasian American woman with dark espresso-brown shoulder-length hair in a claw clip, blue eyes, fair skin, and soft square jawline", "a matte burgundy-wine casual henley top", "a lived-in American home kitchen with warm wood cabinets and ceiling light bloom"),
    ("male", "58", "Caucasian American man with full silver-grey short hair, clean-shaven jawline, blue eyes, and natural mature skin creases", "a matte oatmeal-grey cotton crew-neck t-shirt", "a bright American farmhouse kitchen with white beadboard cabinets"),
]

while len(AVATARES_50_SPECS) < 50:
    idx_e = (len(AVATARES_50_SPECS) - 5) % len(_EXTRA_PEOPLE)
    g, a_base, p_desc, sh, rm = _EXTRA_PEOPLE[idx_e]
    age_mod = int(a_base) + ((len(AVATARES_50_SPECS) // len(_EXTRA_PEOPLE)) % 3) - 1
    AVATARES_50_SPECS.append(
        {
            "gender": g,
            "age": str(age_mod),
            "person": p_desc,
            "role": "everyday American home wellness enthusiast",
            "shirt": sh,
            "room": rm,
        }
    )


def _prompt_f1_fusao_suprema_v2(av_num: int, spec_av: dict[str, str]) -> str:
    """
    Compila o Prompt de Imagem da Pose 1 (Talking-Head olhando para a câmera)
    seguindo 100% os 3 parágrafos da skill `realismo-e-animacao-universal` (`Fusão Suprema V2`) + `avatar-realista`.
    """
    pron = "He" if spec_av["gender"] == "male" else "She"
    poss = "his" if spec_av["gender"] == "male" else "her"
    p1 = (
        f"A straight-on medium close-up smartphone frame captures a {spec_av['age']}-year-old {spec_av['person']} (unique seed #PYONG_AV{av_num:03d}), "
        f"with realistic low-amplitude skin variation (subtle tonal shifts, mild natural redness around the nose and cheeks, soft natural under-eye shadow, "
        f"and honest expression lines caused by speech), high local acutance on the closer iris, eyelashes and hairline, no makeup, no beauty filter, "
        f"no porcelain smoothing, and no cosmetic enhancements, captured mid-sentence with lips naturally parted between phonemes and a calm, earnest, "
        f"curious everyday expression. {pron} resembles an ordinary, anonymous everyday middle-class {spec_av['role']}, not resembling anyone famous or any celebrity."
    )
    p2 = (
        f"{pron} is wearing {spec_av['shirt']}. The framing is a vertical 9:16 front-facing smartphone portrait from mid-chest to slightly above the head "
        f"(with the top of {poss} hair positioned naturally ~15% below the top frame edge so {poss} head and shoulders fill the upper-middle frame cleanly). "
        f"Both hands are naturally lowered and resting out of frame in a relaxed neutral posture, not waving or pointing. "
        f"{pron} looks directly into the smartphone camera lens, talking straight to the viewer."
    )
    p3 = (
        f"The background is {spec_av['room']}. Captured at eye level with an ordinary front-facing smartphone camera (24mm equivalent, no Portrait mode) "
        f"with slight natural framing imbalance and broad depth of field — walls, curtains, cabinets, and background objects at 0.5m to 3m remain naturally "
        f"legible with recognizable edges and zero synthetic bokeh. Let the in-frame window or overhead ceiling light clip naturally under phone autoexposure "
        f"into a soft white bloom while the far cheek and room corners fall off naturally into shadow without studio fill light. "
        f"COLOR PIPELINE: Raw ungraded smartphone footage, straight-out-of-camera neutral white balance and faithful natural skin tone. "
        f"No LUT, no cinematic grade, no warm orange/yellow filter, no teal-and-orange look, and no beauty filter. Keep neutral walls, whites, and greys strictly neutral."
    )
    return f"IMPORTANT: THIS IS IPHONE FOOTAGE!! KEEP THE SAME LIGHTING AND QUALITY. No text or UI in the image.\n\n{p1}\n\n{p2}\n\n{p3}"


def _prompt_f2_watching_phone_fusao_suprema_v2(av_num: int, spec_av: dict[str, str]) -> str:
    """
    Compila o Prompt de Imagem da Pose 2 (Assistindo vídeo no celular igual ao Pyong em `pyong_exact_structure_12frames.jpg` t=2.2s..38.6s)
    usando `refs=[f1_id]` (`EDIT_TARGET`) com expressão 100% CALMA, SÉRIA, FOCADA E NATURAL (zero olhos arregalados, zero sorriso forçado).
    """
    pron = "He" if spec_av["gender"] == "male" else "She"
    poss = "his" if spec_av["gender"] == "male" else "her"
    return (
        "IMPORTANT: THIS IS IPHONE FOOTAGE!! KEEP THE SAME LIGHTING AND QUALITY. No text or UI in the image.\n\n"
        f"Continuous frame from the exact same front-facing smartphone video recording as Reference Image 1. "
        f"Preserve 100% the exact same {spec_av['age']}-year-old {spec_av['person']} (same facial bone structure, low-amplitude natural skin texture, "
        f"hair strands, {spec_av['shirt']}, and the exact same {spec_av['room']} background, lighting, neutral white balance, and head size/position).\n\n"
        f"Update ONLY {poss} gaze and add the top back corner of a modern smartphone in the bottom-right corner of the frame: "
        f"{pron} is silently watching a video on a smartphone held low near the bottom-right corner of the frame (only the upper back edge and camera lens of the matte smartphone case is visible at the bottom-right corner, with {poss} fingers resting below the frame edge). "
        f"{poss.capitalize()} head is turned very slightly (~10 degrees) toward the bottom-right, eyes looking calmly downward at the smartphone screen. "
        f"CRITICAL EXPRESSION LOCK (PYONG LEE STYLE): {poss.capitalize()} facial expression is completely calm, serious, focused, and naturally attentive while reading/watching the phone screen — "
        f"relaxed neutral eyebrows, normal relaxed eyelids (STRICTLY NO wide bug-eyes, NO exaggerated shock), and lips gently closed in a calm neutral resting position (STRICTLY NO toothy grin, NO open-mouth smile).\n\n"
        "COLOR PIPELINE: Raw ungraded smartphone footage, straight-out-of-camera neutral white balance and faithful natural skin tone, 24mm deep focus with zero synthetic bokeh."
    )


def _prompt_veo_ad06_falado(spec_av: dict[str, str], fala_en: str, is_hook: bool) -> str:
    """Compila o JSON de 11 blocos do Diretor Biomecânico Causal AD06 (`realismo-e-animacao-universal`) para C1 (Hook) ou C3 (Outro)."""
    gender_word = "man" if spec_av["gender"] == "male" else "woman"
    pitch_str = "natural male baritone/tenor mid-register (~115–135 Hz)" if spec_av["gender"] == "male" else "natural female mid-register (~185–210 Hz)"
    fala_limpa = re.sub(r'["“”]', "", fala_en.strip())

    if is_hook:
        gesture_str = (
            "As speech begins on frame 1, one hand briefly raises an index finger into the lower frame pointing slightly upward toward the top of the screen "
            "following causal shoulder -> elbow -> wrist -> finger biomechanics, then lowers naturally."
        )
        expr_str = "Curious, earnest, spontaneous everyday expression with a subtle eyebrow raise on the question, maintaining natural human skin elasticity."
        energy_str = "Spontaneous, curious conversational UGC hook."
    else:
        gesture_str = (
            "Looking directly at the camera lens, the speaker makes a brief, natural causal hand gesture pointing slightly downward toward the bottom of the frame "
            "following shoulder -> elbow -> wrist -> hand biomechanics."
        )
        expr_str = "Warm, sincere, down-to-earth expression with a subtle friendly nod at the end, zero exaggerated commercial grin."
        energy_str = "Warm, friendly everyday closing recommendation."

    payload = {
        "visual_reference": (
            f"Animate the exact {spec_av['age']}-year-old {gender_word} from the input image. Preserve exact facial identity, bone structure, "
            f"low-amplitude natural skin, hair strands, {spec_av['shirt']}, {spec_av['room']}, clipped light bloom, and framing."
        ),
        "visual_style": {
            "format": "vertical 9:16",
            "look": "raw ungraded smartphone footage, straight-out-of-camera neutral color, authentic live-action UGC",
            "energy": "Spontaneous, natural, human conversational presence — never polished commercial acting.",
        },
        "camera": {
            "mode": "DIRECT FRONT-FACING SMARTPHONE POV",
            "critical_pov_rule": "The viewer looks through the recording smartphone; never render extra recording rigs.",
            "framing": "Preserve the exact medium close-up framing, slight natural imbalance, and broad 24mm smartphone depth of field from the input image.",
            "restriction": "Zero camera zoom, zero cuts, zero transitions, zero artificial push-in.",
        },
        "physical_camera_behavior": {
            "core_rule": "All gestures and body emphasis follow causal shoulder -> elbow -> wrist -> fingers biomechanics, creating proportional shoulder movement, subtle fabric fold response, tiny natural inertia, and a smooth settle.",
            "forbidden": "No robotic head bobbing, no extra hands, no morphing, no random shake.",
        },
        "performance": {
            "opening": "Begin speaking immediately on frame 1 mid-breath with natural direct eye contact.",
            "energy": energy_str,
            "eye_contact": "Steady, natural eye contact with the camera lens.",
            "expression": expr_str,
            "gesture": gesture_str,
            "skin_physics": "Natural cheek, jaw, and nasolabial skin elasticity matching lip movements and micro-expressions.",
            "pace_rule": "Facial transitions and hand mechanics tightly synchronized with speech syllables.",
        },
        "voice_identity": {
            "critical_rule": "MAINTAIN A SINGLE CONSISTENT HUMAN VOICE IDENTITY FROM START TO END.",
            "profile": f"Native American {gender_word}, {spec_av['age']} years old, {pitch_str}, natural everyday timbre and conversational UGC personality.",
            "identity_lock": "Preserve consistent vocal age, timbre, resonance, and accent across the entire clip.",
        },
        "speech_direction": {
            "language": "Native American English (en-US)",
            "lip_sync": "Accurate syllable-by-syllable lip-sync.",
            "delivery": "FAST, punchy, energetic, upbeat conversational UGC pace (~215–230 words per minute, like Pyong Lee's energetic vocal rhythm), while keeping the face calm and natural without exaggerated facial expressions.",
            "rhythm": "Zero dead air at the start, zero mid-sentence pauses, crisp rapid-fire articulation of the entire sentence through the very last word.",
            "critical_rule": "Begin speaking immediately on frame 1 at a brisk, energetic clip and finish the final word ('viral' or 'tips') completely with room to spare.",
            "forbidden": "No slow drawl, no dragging vowels, no dramatic pauses, no robotic cadence, no overacted bug-eyes.",
        },
        "audio_perspective": {
            "core_rule": "Natural front-facing smartphone microphone perspective (~50cm indoor distance) matching visible camera distance."
        },
        "audio": {
            "quality": "Clean, clear vocal track in the foreground with crisp consonants and natural vowels.",
            "only_audible_element": "SPOKEN HUMAN VOICE IS THE ONLY AUDIBLE ELEMENT.",
            "forbidden": "No background music, no sound effects, no crowd noise, no metallic reverb.",
        },
        "spoken_audio_lock": (
            "IMPORTANT — SPOKEN AUDIO ONLY:\n"
            "Generate the dialogue exclusively as spoken audio. ABSOLUTELY NO visible text at any moment: "
            "no subtitles, no captions, no burned-in words, no speech bubbles, no UI icons, no watermarks, and no overlays."
        ),
        "dialogue": fala_limpa,
        "final_visual_restriction": "FINAL VISUAL RESTRICTION: Zero visible text or social media UI from the first frame to the last frame.",
    }
    header = (
        f"RAW UNEDITED SMARTPHONE CAMERA FOOTAGE (STRICTLY ZERO ON-SCREEN TEXT, ZERO SUBTITLES, ZERO CAPTIONS, ZERO SOCIAL MEDIA UI). "
        f"The {gender_word} in the reference image speaks aloud in English (spoken audio only, never written on screen): {fala_limpa}\n"
    )
    return header + json.dumps(payload, ensure_ascii=False)


def _prompt_veo_ad06_watch_silent(spec_av: dict[str, str]) -> str:
    """
    Compila o JSON AD06 para o Clipe 2 (Assistindo vídeo no celular igual ao Pyong):
    - Expressão 100% CALMA, SÉRIA, FOCADA, BOCA FECHADA, OLHOS RELAXADOS OLHANDO PARA O CELULAR NO CANTO INFERIOR DIREITO.
    - ZERO olhos arregalados ("bug-eyes"), ZERO sorriso aberto bizarro, ZERO fala.
    """
    gender_word = "man" if spec_av["gender"] == "male" else "woman"
    payload = {
        "visual_reference": (
            f"Animate the exact {spec_av['age']}-year-old {gender_word} from the input image silently watching the smartphone in the bottom-right corner. "
            f"Preserve exact facial identity, bone structure, low-amplitude natural skin, hair strands, {spec_av['shirt']}, {spec_av['room']}, and smartphone corner."
        ),
        "visual_style": {
            "format": "vertical 9:16",
            "look": "raw ungraded smartphone footage, straight-out-of-camera neutral color, authentic live-action UGC reaction",
            "energy": "Calm, focused, understated, realistic human attention while watching a video on a phone — zero theatrical overacting.",
        },
        "camera": {
            "mode": "DIRECT FRONT-FACING SMARTPHONE POV",
            "framing": "Preserve the exact close-medium framing and broad 24mm depth of field from the input image.",
            "restriction": "Zero camera zoom, zero cuts, zero transitions, zero artificial push-in.",
        },
        "physical_camera_behavior": {
            "core_rule": "Subtle, realistic human posture micro-shifts and natural breathing inertia only.",
            "forbidden": "No exaggerated head bobbing, no extra hands, no waving, no pointing.",
        },
        "performance": {
            "opening": "From frame 1, the person is calmly and silently watching the screen of the smartphone in the lower-right corner.",
            "eye_contact": "Eyes remain focused downward toward the smartphone screen in the lower-right corner (never staring wide-eyed at the camera).",
            "expression": (
                "CALM, NATURAL, UNDERSTATED HUMAN FOCUS (PYONG LEE REACTION STYLE): "
                "Lips remain gently closed in a relaxed neutral position the entire time. "
                "Eyelids remain at a normal, relaxed human aperture with natural blinking every 2–3 seconds. "
                "As they watch the phone screen, show only subtle, believable micro-expressions: a slight thoughtful furrow of the eyebrows, "
                "subtle horizontal eye-tracking across the phone screen, and a tiny, calm 2mm nod of silent comprehension. "
                "STRICTLY FORBIDDEN: NO wide bug-eyes, NO open-mouth shock, NO toothy grin, NO creepy smiling, NO speaking."
            ),
            "gesture": "The smartphone in the bottom-right corner stays steady; no hands wave or enter the upper frame.",
            "skin_physics": "Natural subtle forehead and cheek micro-tension matching quiet attentive reading/watching.",
        },
        "final_visual_restriction": "FINAL VISUAL RESTRICTION: Zero visible text, zero speech, zero subtitles, zero UI from the first frame to the last frame.",
    }
    header = (
        "RAW UNEDITED SMARTPHONE CAMERA FOOTAGE (STRICTLY ZERO ON-SCREEN TEXT, ZERO SUBTITLES, ZERO UI). "
        f"The {gender_word} in the reference image silently watches the smartphone screen in the lower-right corner with a calm, focused, neutral expression and closed lips:\n"
    )
    return header + json.dumps(payload, ensure_ascii=False)


def _gerar_blind_hook_dr_agressivo(first_sent: str, full_text: str, idx_num: int) -> tuple[str, str, str]:
    """
    Aplica as 5 Regras de Direct Response Agressivo do Copywriter:
    1. ZERO aspas e ZERO rótulo de jornal ('TEMA: EXPLICAÇÃO').
    2. Blind Hook (Cegueira Deliberada): Esconde o ingrediente/culpado e entrega o sintoma visceral + Âncora de Vigia ('WAIT FOR THE 3RD INGREDIENT').
    3. Retorna (line1, line2, highlight_phrase) onde APENAS as 2–3 palavras de dor/choque recebem grifo Vermelho Sangue ou Amarelo Alerta!
    """
    t = (first_sent + " " + full_text).lower()
    if "surgeon" in t or ("green apple" in t and "turmeric" in t):
        return ("BOIL THESE 3 KITCHEN SCRAPS AT NIGHT", "THE 3RD ONE MELTS BELLY FAT AS YOU SLEEP", "3RD ONE MELTS")
    if "armpit" in t or "smell bad" in t or "odor" in t:
        return ("IF DEODORANT FAILS YOU BY NOON,", "RUB THIS 3RD KITCHEN POWDER ON YOUR SKIN", "3RD KITCHEN POWDER")
    if "child" in t or "smarter" in t or "focused at school" in t:
        return ("GIVE THIS TO YOUR KID BEFORE SCHOOL", "WATCH WHAT THE 2ND SPOON DOES IN 14 DAYS", "2ND SPOON DOES")
    if "avocado seed" in t or "type 2 diabetes" in t:
        return ("STOP THROWING THIS SEED IN THE TRASH", "IT HITS BLOOD SUGAR HARDER THAN ANY PILL", "HITS BLOOD SUGAR")
    if "clogged arteries" in t or "heart attack" in t or "cholesterol" in t:
        return ("IF YOUR CHEST FEELS HEAVY AT NIGHT,", "BOIL THESE 3 INGREDIENTS (WATCH THE LAST ONE)", "WATCH THE LAST ONE")
    if "fungus" in t or "swollen feet" in t or "yellow nails" in t:
        return ("SOAK YOUR FEET IN THIS BEFORE BED", "WATCH WHAT COMES OUT OF YOUR NAILS IN 10 MIN", "COMES OUT")
    if "mucus" in t or "lungs" in t or "cough" in t or "throat" in t:
        return ("IF YOU WAKE UP COUGHING UP PHLEGM,", "THIS HOT SYRUP CLEARS YOUR LUNGS IN 1 NIGHT", "IN 1 NIGHT")
    if "prostate" in t or "urinate at night" in t:
        return ("WAKING UP 3 TIMES A NIGHT TO PEE?", "NEVER GO TO BED WITHOUT THIS 3RD SPOONFUL", "3RD SPOONFUL")
    if "blurry vision" in t or "nearsighted" in t or "tired eyes" in t or "improve vision" in t:
        return ("IF YOUR VISION GETS BLURRY AFTER 6 PM,", "MIX THESE 3 THINGS (DON'T SKIP THE LAST ONE)", "THE LAST ONE")
    if "hair grow" in t or "bald" in t or "scalp" in t:
        return ("RUB THIS 12-HOUR OIL ON THINNING SPOTS", "DOCTORS HATE WHAT HAPPENS ON DAY 14", "ON DAY 14")
    if "constipation" in t or "stool" in t or "intestine" in t or "bloated" in t:
        return ("IF YOUR STOMACH FEELS LIKE LEAD AFTER MEALS,", "THIS 3-INGREDIENT BLEND FLUSHES IT OVERNIGHT", "FLUSHES IT OVERNIGHT")
    if "joint pain" in t or "knee" in t or "collagen" in t or "arthritis" in t:
        return ("IF YOUR KNEES CRACK WHEN YOU STAND UP,", "EAT 1 SPOON OF THIS BEFORE BED (WATCH AT 10S)", "WATCH AT 10S")
    if "lime peel" in t or "lemon peel" in t or "peels" in t:
        return ("NEVER THROW THESE PEELS IN THE TRASH", "BOIL THEM FOR 10 MIN (LOOK AT THE 3RD HERB)", "THE 3RD HERB")

    # Fallback DR agressivo com Blind Hook + Âncora de Vigia rotativa
    fallbacks = [
        ("PHARMACIES PRAY YOU NEVER BOIL THIS", "WATCH WHAT THE 3RD INGREDIENT DOES AT 12S", "3RD INGREDIENT"),
        ("NEVER MIX THESE 3 THINGS AT NIGHT...", "UNLESS YOU WANT TO DROP 2 SIZES THIS WEEK", "DROP 2 SIZES"),
        ("DOCTORS NEVER MENTION THIS $1 TRICK", "WAIT UNTIL THEY ADD THE LAST SPOONFUL", "LAST SPOONFUL"),
        ("STOP BUYING EXPENSIVE PHARMACY PILLS", "THIS 3RD KITCHEN INGREDIENT WORKS IN 1 NIGHT", "WORKS IN 1 NIGHT"),
    ]
    return fallbacks[idx_num % len(fallbacks)]

def _carregar_ou_gerar_catalogo_105() -> dict[str, dict[str, Any]]:
    cat_path = MAT_DIR / "rclone_105_catalogo_dr_v2.json"
    if cat_path.exists():
        try:
            d = json.loads(cat_path.read_text(encoding="utf-8"))
            if len(d) >= 100:
                return d
        except Exception:
            pass

    txt_path = pathlib.Path(
        r"C:\Users\JeffP\.gemini\antigravity\brain\8ae8cf2b-5a24-4020-9cf1-2816b2435e39\.system_generated\steps\16831\output.txt"
    )
    catalogo: dict[str, dict[str, Any]] = {}
    if txt_path.exists():
        raw = txt_path.read_text(encoding="utf-8", errors="replace")
        blocks = re.split(
            r"=== RCLONE_[^\n]+ \(([^|]+) \| (\d+x\d+) \| ([\d.]+)s \| [\d.]+fps \| lang=(\w+)\) ===",
            raw,
        )
        idx_c = 0
        for i in range(1, len(blocks), 5):
            idx_c += 1
            fname = blocks[i].strip()
            dur = float(blocks[i + 2].strip())
            lang = blocks[i + 3].strip()
            body = blocks[i + 4].strip()
            lines = []
            for ln in body.splitlines():
                m = re.match(r"\s*\[\d+\.\d+s \.\. \d+\.\d+s\]\s*(.+)", ln)
                if m:
                    lines.append(m.group(1).strip())
            first_sent = lines[0] if lines else "NATURAL HOME RECIPE TRICK"
            full_txt = " ".join(lines)
            l1, l2, hl = _gerar_blind_hook_dr_agressivo(first_sent, full_txt, idx_c)
            catalogo[fname] = {
                "fileName": fname,
                "duration_s": dur,
                "lang": lang,
                "first_sentence": first_sent,
                "quote_line1": l1,
                "quote_line2": l2,
                "highlight_phrase": hl,
                "style_idx": idx_c,
            }

    for idx_p, p in enumerate(sorted(RCLONE_DIR.glob("*.mp4")), start=1):
        if p.name not in catalogo:
            l1, l2, hl = _gerar_blind_hook_dr_agressivo("", "", idx_p)
            catalogo[p.name] = {
                "fileName": p.name,
                "duration_s": 20.0,
                "lang": "en",
                "first_sentence": "Natural recipe everyone is trying at home",
                "quote_line1": l1,
                "quote_line2": l2,
                "highlight_phrase": hl,
                "style_idx": idx_p,
            }

    cat_path.write_text(json.dumps(catalogo, indent=2, ensure_ascii=False), encoding="utf-8")
    return catalogo


def _subir_seguro(path: pathlib.Path, cdp_url: str | None = None) -> str:
    ep = cdp_url or "http://127.0.0.1:9225"
    for att in range(1, 7):
        try:
            with IMG_SEM:
                up = subir_midia_rpc(path, cdp_url=ep)
            if isinstance(up, dict) and up.get("ok") and up.get("mediaId"):
                return str(up["mediaId"])
        except Exception:
            pass
        if att in (2, 4):
            try:
                recarregar_aba_flow_anti_traffic(ep)
            except Exception:
                pass
        time.sleep(1.5 * att)
    raise RuntimeError(f"Falha upload {path.name}")


def auditar_whisper_react(mp4_path: pathlib.Path, spec_s: dict[str, Any], min_dur: float = 1.5) -> tuple[bool, str, dict[str, Any]]:
    meta = obter_metadados_midia(mp4_path)
    if not meta.get("valido") or not meta.get("tem_audio"):
        return False, "SEM_AUDIO", {}
    dur = float(meta.get("duracao_s") or 0.0)
    if dur < min_dur:
        return False, f"CURTO({dur:.2f}s)", {}

    with WHISPER_LOCK:
        tr = transcrever_com_palavras(mp4_path)
    pals = tr.get("palavras") or []
    if len(pals) < 4:
        return False, f"POUCAS_PALAVRAS({len(pals)})", {}

    texto = str(tr.get("texto") or "").strip()
    norm = lambda s: re.sub(r"[^a-zA-Z0-9]", "", s.lower())
    esp = [norm(t) for t in spec_s["fala"].split() if norm(t)]
    trn_norm = [norm(str(p.get("palavra") or "")) for p in pals if norm(str(p.get("palavra") or ""))]

    for k_bi in range(len(trn_norm) - 3):
        if trn_norm[k_bi : k_bi + 2] == trn_norm[k_bi + 2 : k_bi + 4]:
            return False, f"REPETICAO_BIGRAMA({' '.join(trn_norm[k_bi:k_bi+4])})", {}

    cov = sum(1 for t in esp if t in set(trn_norm)) / max(1, len(esp))
    if cov < 0.72:
        return False, f"COV_BAIXA({cov:.2f}:'{texto}')", {}

    must_end = [norm(m) for m in spec_s["must_end_any"]]
    # A última ou penúltima palavra transcrita DEVE ser a palavra final obrigatória ('viral' ou 'tips')!
    if not any(u in must_end for u in trn_norm[-2:]):
        return False, f"NAO_TERMINOU_PALAVRA_FINAL({trn_norm[-3:]}:'{texto}')", {}

    idx_fim = len(pals) - 1
    for i in range(len(pals) - 1, max(-1, len(pals) - 4), -1):
        if norm(str(pals[i].get("palavra") or "")) in must_end:
            idx_fim = i
            break

    return True, "OK", {
        "dur_bruta": dur,
        "ini_fala": max(0.0, float(pals[0].get("inicio") or 0.0)),
        "fim_fala": float(pals[idx_fim].get("fim") or dur),
        "texto": texto,
        "palavras": pals[: idx_fim + 1],
    }


def _gerar_ou_carregar_avatar_fixo(
    av_num: int,
    conta_cdp: str = "http://127.0.0.1:9225",
    apenas_frames: bool = False,
) -> dict[str, Any]:
    """
    Gera (ou carrega de `C:\\Hub001\\AVATARES_FIXOS_REACT_50_V2\\AVxxx`) o Avatar Fixo com Realismo Fusão Suprema V2 + AD06 JSON:
    - `frame_1_talking.jpg` (`refs=[]` — gerado do zero com estrutura óssea, pele de baixa amplitude e óptica 24mm iPhone)
    - `frame_2_watching_phone.jpg` (`refs=[f1_id]` — mesma pessoa e ambiente assistindo ao celular com expressão calma/focada igual ao Pyong)
    - `clip_1_hook_trim.mp4` (~2.0s–2.4s falando "Have you seen this video that just went viral?")
    - `clip_2_watch_trim.mp4` (8.0s reação silenciosa calma e focada assistindo celular — para repetir em loop normal para frente, SEM reverso!)
    - `clip_3_outro_trim.mp4` (~4.0s falando "Try this natural recipe at home, and follow for more daily health tips.")
    """
    with usar_conta_flow(conta_cdp):
        av_dir = AVATARS_BANK_DIR / f"AV{av_num:03d}"
        av_dir.mkdir(parents=True, exist_ok=True)
        spec_av = AVATARES_50_SPECS[(av_num - 1) % len(AVATARES_50_SPECS)]
        hook_spec = PYONG_HOOKS_EN[(av_num - 1) % len(PYONG_HOOKS_EN)]
        outro_spec = OUTRO_CTA_SPECS[(av_num - 1) % len(OUTRO_CTA_SPECS)]
        porta_lbl = conta_cdp.split(":")[-1]
        tag = f"AV{av_num:03d}@{porta_lbl}"

        f1_jpg = av_dir / "frame_1_talking.jpg"
        f2_jpg = av_dir / "frame_2_watching_phone.jpg"
        c1_trim = av_dir / "clip_1_hook_trim.mp4"
        c2_trim = av_dir / "clip_2_watch_trim.mp4"
        c3_trim = av_dir / "clip_3_outro_trim.mp4"

        if c1_trim.exists() and c1_trim.stat().st_size > 30_000:
            ok1, _, _ = auditar_whisper_react(c1_trim, hook_spec, min_dur=1.2)
            if not ok1:
                c1_trim.unlink(missing_ok=True)
        if c3_trim.exists() and c3_trim.stat().st_size > 30_000:
            ok3, _, _ = auditar_whisper_react(c3_trim, outro_spec, min_dur=1.2)
            if not ok3:
                c3_trim.unlink(missing_ok=True)

        if (
            not apenas_frames
            and c1_trim.exists() and c1_trim.stat().st_size > 30_000
            and c2_trim.exists() and c2_trim.stat().st_size > 30_000
            and c3_trim.exists() and c3_trim.stat().st_size > 30_000
        ):
            return {
                "av_num": av_num,
                "av_dir": av_dir,
                "f1": str(f1_jpg),
                "f2": str(f2_jpg),
                "c1": str(c1_trim),
                "c2": str(c2_trim),
                "c3": str(c3_trim),
                "hook_fala": hook_spec["fala"],
                "outro_fala": outro_spec["fala"],
            }

        # 1. FRAME 1 (TALKING PORTRAIT — GERADO DO ZERO `refs=[]` COM SKILL `realismo-e-animacao-universal` FUSÃO SUPREMA V2)
        p_f1 = _prompt_f1_fusao_suprema_v2(av_num, spec_av)
        precisa_f1_id = (
            not (f2_jpg.exists() and f2_jpg.stat().st_size > 20_000)
            or not (c1_trim.exists() and c1_trim.stat().st_size > 30_000)
            or not (c3_trim.exists() and c3_trim.stat().st_size > 30_000)
        )
        f1_id = ""
        if f1_jpg.exists() and f1_jpg.stat().st_size > 20_000:
            if precisa_f1_id:
                f1_id = _subir_seguro(f1_jpg, conta_cdp)
        else:
            for att in range(1, 6):
                gi1 = gerar_imagem_rpc(prompt=p_f1, refs=[], modelo="BELUGA", aspecto=2, cdp_url=conta_cdp)
                if gi1.get("ok"):
                    dl1 = aguardar_midia_rpc(gi1, tipo="imagem", destino_arquivo=f1_jpg, timeout_s=150, cdp_url=conta_cdp)
                    if dl1.get("ok") and f1_jpg.exists() and f1_jpg.stat().st_size > 20_000:
                        f1_id = str(dl1.get("mediaId") or gi1.get("mediaId") or "") or _subir_seguro(f1_jpg, conta_cdp)
                        print(f"  [{tag} F1 REALISMO FUSAO SUPREMA V2 OK att={att}]", flush=True)
                        break
                else:
                    print(f"  [{tag} F1 att={att} ERRO] {gi1}", flush=True)
                    if att in (2, 4):
                        recarregar_aba_flow_anti_traffic(conta_cdp)
                    time.sleep(2.5)
                f1_jpg.unlink(missing_ok=True)
        if precisa_f1_id and not f1_id:
            raise RuntimeError(f"{tag} falhou F1")

        # 2. FRAME 2 (WATCHING SMARTPHONE — `refs=[f1_id]` COM EXPRESSÃO CALMA/SÉRIA/FOCADA IGUAL AO PYONG)
        p_f2 = _prompt_f2_watching_phone_fusao_suprema_v2(av_num, spec_av)
        f2_id = ""
        if f2_jpg.exists() and f2_jpg.stat().st_size > 20_000:
            if not (c2_trim.exists() and c2_trim.stat().st_size > 30_000):
                f2_id = _subir_seguro(f2_jpg, conta_cdp)
        else:
            for att in range(1, 6):
                gi2 = gerar_imagem_rpc(prompt=p_f2, refs=[f1_id], modelo="BELUGA", aspecto=2, cdp_url=conta_cdp)
                if gi2.get("ok"):
                    dl2 = aguardar_midia_rpc(gi2, tipo="imagem", destino_arquivo=f2_jpg, timeout_s=150, cdp_url=conta_cdp)
                    if dl2.get("ok") and f2_jpg.exists() and f2_jpg.stat().st_size > 20_000:
                        f2_id = str(dl2.get("mediaId") or gi2.get("mediaId") or "") or _subir_seguro(f2_jpg, conta_cdp)
                        print(f"  [{tag} F2 WATCHING PHONE CALMO/FOCADO OK att={att}]", flush=True)
                        break
                f2_jpg.unlink(missing_ok=True)
        if not (c2_trim.exists() and c2_trim.stat().st_size > 30_000) and not f2_id:
            raise RuntimeError(f"{tag} falhou F2")

        if apenas_frames:
            return {"av_num": av_num, "f1": str(f1_jpg), "f2": str(f2_jpg)}

        # 3. PROMPTS DE ANIMAÇÃO AD06 JSON (11 BLOCOS)
        pr_c1 = _prompt_veo_ad06_falado(spec_av, hook_spec["fala"], is_hook=True)
        pr_c2 = _prompt_veo_ad06_watch_silent(spec_av)
        pr_c3 = _prompt_veo_ad06_falado(spec_av, outro_spec["fala"], is_hook=False)

        lote_items: dict[int, dict[str, Any] | None] = {1: None, 3: None}
        pend_f1 = []
        if not (c1_trim.exists() and c1_trim.stat().st_size > 30_000):
            pend_f1.append((1, pr_c1, f1_id))
        if not (c3_trim.exists() and c3_trim.stat().st_size > 30_000):
            pend_f1.append((3, pr_c3, f1_id))

        if len(pend_f1) == 2:
            lote_res = gerar_videos_lote_rpc(
                [{"prompt": p_txt, "img": r_id, "modelo": MODELO_VIDEO_LP, "aspecto": 1} for (_, p_txt, r_id) in pend_f1],
                modelo=MODELO_VIDEO_LP,
                aspecto=1,
                cdp_url=conta_cdp,
            )
            items_ret = lote_res.get("items") or []
            if lote_res.get("ok") and len(items_ret) == 2:
                lote_items[1] = items_ret[0]
                lote_items[3] = items_ret[1]

        def _cortar_clipe_falado(raw: pathlib.Path, inf_w: dict[str, Any], out_trim: pathlib.Path, target_dur: float, sp_dict: dict[str, Any]) -> bool:
            # JAMAIS truncar o fim da fala! Pega do início da 1ª palavra até +0.42s após o fim da última palavra ('viral' ou 'tips')
            t0 = max(0.0, float(inf_w["ini_fala"]) - 0.08)
            t1 = min(float(inf_w["dur_bruta"]), float(inf_w["fim_fala"]) + 0.42)
            raw_span = max(1.2, t1 - t0)
            # Ritmo energético estilo Pyong Lee: se o locutor falou devagar, acelera suavemente (1.16x..1.26x) sem distorcer timbre nem cortar palavra!
            speed = round(min(1.26, max(1.14, raw_span / target_dur)), 4)
            vf = f"trim=start={t0:.3f}:end={t1:.3f},setpts=(PTS-STARTPTS)/{speed:.4f},fps=30,crop=iw-16:ih-28:8:14,scale=720:1280:flags=lanczos,format=yuv420p"
            af = f"atrim=start={t0:.3f}:end={t1:.3f},asetpts=PTS-STARTPTS,atempo={speed:.4f},aresample=44100,volume=2.5dB,alimiter=limit=0.95"
            with NVENC_SEM:
                subprocess.run(
                    [
                        FFMPEG_BIN, "-y", "-loglevel", "error", "-i", str(raw),
                        "-vf", vf, "-af", af,
                        "-c:v", "h264_nvenc", "-preset", "p4", "-cq", "20",
                        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2",
                        str(out_trim),
                    ],
                    check=True,
                )
            # REVISOR PÓS-CORTE OBRIGATÓRIO: Audita o arquivo `out_trim` já cortado para garantir 100% que a frase inteira até a última palavra ('viral' / 'tips') está dentro do clipe!
            ok_post, msg_post, inf_post = auditar_whisper_react(out_trim, sp_dict, min_dur=1.2)
            if not ok_post:
                print(f"  [REVISOR POS-CORTE REPROVOU {out_trim.name}] {msg_post}", flush=True)
                out_trim.unlink(missing_ok=True)
                return False
            print(f"  [REVISOR POS-CORTE APROVOU {out_trim.name}] speed={speed}x | texto='{inf_post['texto']}'", flush=True)
            return True

        def _resolver_clipe_falado(c_idx: int, prompt_v: str, ref_img_id: str, sp_dict: dict[str, Any], out_trim: pathlib.Path, target_dur: float) -> None:
            with usar_conta_flow(conta_cdp):
                if out_trim.exists() and out_trim.stat().st_size > 30_000:
                    ok_existing, _, _ = auditar_whisper_react(out_trim, sp_dict, min_dur=1.2)
                    if ok_existing:
                        return
                    out_trim.unlink(missing_ok=True)
                c_tag = f"{tag}_C{c_idx}"
                it0 = lote_items.get(c_idx)
                if it0 and it0.get("ok"):
                    raw0 = av_dir / f"raw_c{c_idx}_lote.mp4"
                    p0 = aguardar_midia_rpc(it0, tipo="video", destino_arquivo=raw0, timeout_s=175, cdp_url=conta_cdp)
                    if p0.get("ok") and raw0.exists() and raw0.stat().st_size >= 40_000:
                        ok_w, msg_w, inf_w = auditar_whisper_react(raw0, sp_dict, min_dur=1.4)
                        if ok_w and _cortar_clipe_falado(raw0, inf_w, out_trim, target_dur, sp_dict):
                            raw0.unlink(missing_ok=True)
                            print(f"  [{c_tag} OK lote ({MODELO_VIDEO_LP})] {inf_w['ini_fala']:.2f}..{inf_w['fim_fala']:.2f}s", flush=True)
                            return
                    raw0.unlink(missing_ok=True)

                for att in range(1, 8):
                    raw = av_dir / f"raw_c{c_idx}_att{att}.mp4"
                    gen = gerar_video_rpc(
                        prompt=prompt_v,
                        first_frame_id=ref_img_id,
                        modelo=MODELO_VIDEO_LP,
                        tipo="i2v",
                        aspecto=1,
                        cdp_url=conta_cdp,
                    )
                    if not gen.get("ok"):
                        time.sleep(2.0)
                        continue
                    p = aguardar_midia_rpc(gen, tipo="video", destino_arquivo=raw, timeout_s=175, cdp_url=conta_cdp)
                    if not p.get("ok") or not raw.exists() or raw.stat().st_size < 40_000:
                        raw.unlink(missing_ok=True)
                        continue
                    ok_w, msg_w, inf_w = auditar_whisper_react(raw, sp_dict, min_dur=1.4)
                    if not ok_w:
                        print(f"  [{c_tag} RE-ROLL att={att}] {msg_w}", flush=True)
                        raw.unlink(missing_ok=True)
                        continue
                    if _cortar_clipe_falado(raw, inf_w, out_trim, target_dur, sp_dict):
                        raw.unlink(missing_ok=True)
                        print(f"  [{c_tag} OK ({MODELO_VIDEO_LP}) att={att}] {inf_w['ini_fala']:.2f}..{inf_w['fim_fala']:.2f}s", flush=True)
                        return
                    raw.unlink(missing_ok=True)
                raise RuntimeError(f"{c_tag} falhou após tentativas")

        def _resolver_clipe_watch() -> None:
            with usar_conta_flow(conta_cdp):
                if c2_trim.exists() and c2_trim.stat().st_size > 30_000:
                    return
                c_tag = f"{tag}_C2_WATCH"
                for att in range(1, 8):
                    raw = av_dir / f"raw_c2_att{att}.mp4"
                    gen = gerar_video_rpc(
                        prompt=pr_c2,
                        first_frame_id=f2_id,
                        modelo=MODELO_VIDEO_LP,
                        tipo="i2v",
                        aspecto=1,
                        cdp_url=conta_cdp,
                    )
                    if not gen.get("ok"):
                        time.sleep(2.0)
                        continue
                    p = aguardar_midia_rpc(gen, tipo="video", destino_arquivo=raw, timeout_s=175, cdp_url=conta_cdp)
                    if not p.get("ok") or not raw.exists() or raw.stat().st_size < 40_000:
                        raw.unlink(missing_ok=True)
                        continue
                    vf = "fps=30,crop=iw-16:ih-28:8:14,scale=720:1280:flags=lanczos,format=yuv420p"
                    with NVENC_SEM:
                        subprocess.run(
                            [
                                FFMPEG_BIN, "-y", "-loglevel", "error", "-i", str(raw),
                                "-vf", vf, "-an",
                                "-c:v", "h264_nvenc", "-preset", "p4", "-cq", "20",
                                "-pix_fmt", "yuv420p",
                                str(c2_trim),
                            ],
                            check=True,
                        )
                    raw.unlink(missing_ok=True)
                    print(f"  [{c_tag} OK ({MODELO_VIDEO_LP}) att={att}]", flush=True)
                    return
                raise RuntimeError(f"{c_tag} falhou após tentativas")

        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
            f_c1 = ex.submit(_resolver_clipe_falado, 1, pr_c1, f1_id, hook_spec, c1_trim, 2.35)
            f_c2 = ex.submit(_resolver_clipe_watch)
            f_c3 = ex.submit(_resolver_clipe_falado, 3, pr_c3, f1_id, outro_spec, c3_trim, 3.85)
            f_c1.result()
            f_c2.result()
            f_c3.result()

        return {
            "av_num": av_num,
            "av_dir": av_dir,
            "f1": str(f1_jpg),
            "f2": str(f2_jpg),
            "c1": str(c1_trim),
            "c2": str(c2_trim),
            "c3": str(c3_trim),
            "hook_fala": hook_spec["fala"],
            "outro_fala": outro_spec["fala"],
        }


def _detectar_y_crop_avatar_sem_achatar(img_path: pathlib.Path, crop_h: int = 564, is_phone_watch: bool = False) -> int:
    """
    Detecta automaticamente a testa/rosto via máscara de pele YCrCb no frame 720x1280 para cortar exatamente `720x564`
    com `1:1` de proporção (ZERO achatamento!), eliminando o teto/luminária e enquadrando cabeça + ombros + topo do celular
    exatamente como o Pyong Lee!
    """
    try:
        im = cv2.imread(str(img_path))
        if im is None:
            return 285
        ycrcb = cv2.cvtColor(im[180:850, 160:560], cv2.COLOR_BGR2YCrCb)
        _, Cr, Cb = cv2.split(ycrcb)
        skin = (Cr >= 135) & (Cr <= 176) & (Cb >= 76) & (Cb <= 126)
        ys = np.where(skin)[0] + 180
        if len(ys) > 120:
            y_forehead = int(np.percentile(ys, 5))
            # Em F2 (assistindo celular), desce ~35px a mais para mostrar o topo do smartphone no canto inferior direito igual ao Pyong
            offset_top = 55 if is_phone_watch else 85
            y0 = max(0, min(1280 - crop_h, y_forehead - offset_top))
            return int(y0)
    except Exception:
        pass
    return 310 if is_phone_watch else 280


def _criar_overlay_quote_pyong_png(
    line1: str,
    line2: str,
    out_png: pathlib.Path,
    highlight_phrase: str = "",
    style_idx: int = 0,
) -> pathlib.Path:
    """
    Gera o Banner Direct Response Agressivo (conforme autópsia do Copywriter):
    - ZERO aspas ('“' removido!) e ZERO formato jornalzinho.
    - Faixas brancas com texto preto bold uppercase e grifo EXCLUSIVO nas 2–3 palavras de dor/choque
      alternando entre Vermelho Sangue (#D91414 c/ texto branco) e Amarelo Alerta (#FFE014 c/ texto preto) para quebrar cegueira de banner!
    """
    img = Image.new("RGBA", (720, 1280), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    try:
        font_txt = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 24)
    except Exception:
        font_txt = ImageFont.load_default()

    use_blood_red = (style_idx % 2) == 1
    hl_bg = (217, 20, 20, 255) if use_blood_red else (255, 224, 20, 255)
    hl_fg = (255, 255, 255, 255) if use_blood_red else (10, 10, 10, 255)

    y_cur = 505
    hl_clean = highlight_phrase.strip().upper()
    for ln in (line1.strip().upper(), line2.strip().upper()):
        if not ln:
            continue
        bbox = draw.textbbox((0, 0), ln, font=font_txt)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        pad_x, pad_y = 14, 10
        rx0, ry0 = 36, y_cur
        rx1, ry1 = min(696, rx0 + tw + pad_x * 2), ry0 + th + pad_y * 2
        # Sombra dura para contraste no feed
        draw.rectangle([rx0 + 3, ry0 + 4, rx1 + 3, ry1 + 4], fill=(0, 0, 0, 140))
        draw.rectangle([rx0, ry0, rx1, ry1], fill=(255, 255, 255, 250))

        # Verifica se a frase de destaque (2-3 palavras de dor/choque) está nesta linha
        if hl_clean and hl_clean in ln:
            idx_pos = ln.find(hl_clean)
            prefix = ln[:idx_pos]
            w_pre = draw.textbbox((0, 0), prefix, font=font_txt)[2] if prefix else 0
            w_hl = draw.textbbox((0, 0), hl_clean, font=font_txt)[2]
            hx0 = rx0 + pad_x + w_pre - 4
            hx1 = hx0 + w_hl + 8
            draw.rectangle([hx0, ry0 + 3, min(rx1 - 2, hx1), ry1 - 3], fill=hl_bg)
            # Desenha prefixo, grifo e sufixo
            draw.text((rx0 + pad_x, ry0 + pad_y - 3), prefix, font=font_txt, fill=(10, 10, 10, 255))
            draw.text((rx0 + pad_x + w_pre, ry0 + pad_y - 3), hl_clean, font=font_txt, fill=hl_fg)
            suffix = ln[idx_pos + len(hl_clean) :]
            if suffix:
                w_pre_hl = draw.textbbox((0, 0), ln[: idx_pos + len(hl_clean)], font=font_txt)[2]
                draw.text((rx0 + pad_x + w_pre_hl, ry0 + pad_y - 3), suffix, font=font_txt, fill=(10, 10, 10, 255))
        else:
            draw.text((rx0 + pad_x, ry0 + pad_y - 3), ln, font=font_txt, fill=(10, 10, 10, 255))
        y_cur = ry1 + 8

    img.save(str(out_png), "PNG")
    return out_png


def _criar_overlay_follow_pill_png(out_png: pathlib.Path) -> pathlib.Path:
    """Gera PNG transparente 720x1280 com o pill branco 'FOLLOW FOR MORE ↓' centralizado na base (igual ao 'SIGA PARA MAIS ↓' do Pyong)."""
    img = Image.new("RGBA", (720, 1280), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    try:
        font_pill = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 25)
    except Exception:
        font_pill = ImageFont.load_default()

    # Centralizado na parte inferior igual ao Pyong (x=175..545, y=1095..1158)
    x0, y0, x1, y1 = 175, 1095, 545, 1158
    draw.rounded_rectangle([x0 + 2, y0 + 4, x1 + 2, y1 + 4], radius=14, fill=(0, 0, 0, 95))
    draw.rounded_rectangle([x0, y0, x1, y1], radius=14, fill=(255, 255, 255, 252))
    draw.text((x0 + 34, y0 + 17), "FOLLOW FOR MORE", font=font_pill, fill=(15, 15, 15, 255))
    # Seta vetorial para baixo '↓' nítida
    ax = x1 - 36
    draw.line([(ax, y0 + 18), (ax, y0 + 41)], fill=(15, 15, 15, 255), width=4)
    draw.polygon([(ax - 8, y0 + 35), (ax + 8, y0 + 35), (ax, y0 + 46)], fill=(15, 15, 15, 255))
    img.save(str(out_png), "PNG")
    return out_png


def montar_video_react_pyong_nvenc(
    vid_idx: int,
    rclone_mp4: pathlib.Path,
    cat_entry: dict[str, Any],
    av_info: dict[str, Any],
    forcar_remontar: bool = False,
) -> dict[str, Any]:
    """
    Monta o vídeo final de React em Tela Dividida Estilo Pyong (`720x1280` 30fps, 0 bordas pretas, crop 1:1 sem achatamento):
    - PARTE 1 (Hook de Início ~2.0s):
      * Topo: Quadro inicial do vídeo de receita + Caixa de Citação Verde do Pyong (`“`).
      * Base: Crop 1:1 (`720x564`) do `clip_1_hook_trim.mp4` falando "Have you seen this video that just went viral?"
    - PARTE 2 (Vídeo de Receita 100% Completo do início ao fim + React Silencioso SEM reverso):
      * Topo: O vídeo original de `07_REACT_RCLONE` toca **100% INTEIRO (`0.00s` até `dur_viral` completo, sem jamais cortar no meio!)** com seu áudio original!
      * Base: Crop 1:1 (`720x564`) do `clip_2_watch_trim.mp4` repetindo em **ordem normal para frente (`-stream_loop -1` direto no clipe forward, ZERO reverso!)**, assistindo ao celular em silêncio igual ao Pyong!
    - PARTE 3 (Final Tela Cheia `720x1280` após a receita terminar 100%):
      * `clip_3_outro_trim.mp4` em `720x1280` Tela Cheia com o botão **`FOLLOW FOR MORE ↓`**!
    """
    av_num = int(av_info["av_num"])
    mp4_esteira_name = f"US_WL_REACT_C01_G00_L01_{vid_idx:03d}.mp4"
    mp4_desc_name = f"REACT_{vid_idx:03d}__AV{av_num:03d}__{rclone_mp4.name}"

    esteira_dst = ESTEIRA_REACT_BASE / mp4_esteira_name
    hub_dst = HUB_OUT_BASE / FOLDER_LABEL / mp4_desc_name
    drv_diario = DRIVE_ROOT_BASE / "01_PRODUCAO_DIARIA" / TODAY_STR / FOLDER_LABEL / mp4_desc_name
    drv_cofre = DRIVE_COFRE_IMUTAVEL / COFRE_FOLDER_NAME / mp4_desc_name

    if not forcar_remontar and esteira_dst.exists() and esteira_dst.stat().st_size > 200_000:
        for dst in (hub_dst, drv_diario, drv_cofre):
            dst.parent.mkdir(parents=True, exist_ok=True)
            if not dst.exists():
                shutil.copy2(str(esteira_dst), str(dst))
        return {"ok": True, "idx": vid_idx, "path": str(esteira_dst), "cached": True}

    wdir = pathlib.Path(r"C:\Hub001\WORK_REACT_PYONG_105_V2") / f"R{vid_idx:03d}_AV{av_num:03d}"
    wdir.mkdir(parents=True, exist_ok=True)

    c1_hook = pathlib.Path(av_info["c1"])
    c2_watch = pathlib.Path(av_info["c2"])
    c3_outro = pathlib.Path(av_info["c3"])

    dur_hook = max(1.6, float(obter_metadados_midia(c1_hook).get("duracao_s") or 2.2))
    dur_viral = max(8.0, float(obter_metadados_midia(rclone_mp4).get("duracao_s") or 18.0))

    y_crop_f1 = _detectar_y_crop_avatar_sem_achatar(pathlib.Path(av_info["f1"]), crop_h=564, is_phone_watch=False)
    y_crop_f2 = _detectar_y_crop_avatar_sem_achatar(pathlib.Path(av_info["f2"]), crop_h=564, is_phone_watch=True)

    quote_png = _criar_overlay_quote_pyong_png(
        cat_entry.get("quote_line1", "BOIL THESE 3 KITCHEN SCRAPS AT NIGHT"),
        cat_entry.get("quote_line2", "THE 3RD ONE MELTS BELLY FAT AS YOU SLEEP"),
        wdir / "pyong_quote.png",
        highlight_phrase=cat_entry.get("highlight_phrase", "3RD ONE MELTS"),
        style_idx=int(cat_entry.get("style_idx", vid_idx)),
    )
    pill_png = _criar_overlay_follow_pill_png(MAT_DIR / "follow_for_more_pill_v2.png")

    # 1. SEG 1 (HOOK DE INÍCIO ~2.5s):
    # - Segundo 0 a 2 (Confirmação Visual do Risco): Começa direto no momento mais tenso/visual da receita (`-ss 5.5` onde os ingredientes estão fervendo/sendo despejados na panela!) com o Banner DR Agressivo sem aspas e com grifo Vermelho Sangue / Amarelo Alerta!
    # - Base mostra o avatar em CROP 1:1 (720x564 cortado em y_crop_f1, ZERO achatamento!) falando em ritmo energético (~220 WPM): "Have you seen this video that just went viral?"
    seg1_mp4 = wdir / "seg1_hook_split.mp4"
    tense_offset_s = min(5.5, max(0.0, dur_viral * 0.35))
    fc_seg1 = (
        f"[0:v]fps=30,scale=720:1280:flags=lanczos,crop=720:764:0:258,pad=720:1280:0:0:black[top];"
        f"[1:v]fps=30,scale=720:1280:flags=lanczos,crop=720:564:0:{y_crop_f1},format=rgba,"
        f"geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='if(lt(Y,44),255*Y/44,255)'[bot];"
        f"[top][bot]overlay=0:716:format=auto[split];"
        f"[split][2:v]overlay=0:0:format=auto,format=yuv420p[vout]"
    )
    with NVENC_SEM:
        subprocess.run(
            [
                FFMPEG_BIN, "-y", "-loglevel", "error",
                "-stream_loop", "-1", "-ss", f"{tense_offset_s:.2f}", "-i", str(rclone_mp4),
                "-i", str(c1_hook),
                "-i", str(quote_png),
                "-filter_complex", fc_seg1,
                "-map", "[vout]", "-map", "1:a",
                "-t", f"{dur_hook:.3f}",
                "-c:v", "h264_nvenc", "-preset", "p4", "-cq", "20",
                "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2",
                str(seg1_mp4),
            ],
            check=True,
        )

    # 2. SEG 2 (VÍDEO DE RECEITA 100% COMPLETO DO SEGUNDO 0.00s ATÉ O FIM + REACT SILENCIOSO EM LOOP FORWARD SEM REVERSO!):
    # - Topo toca `rclone_mp4` INTEIRO (`0.00s .. dur_viral`) com seu áudio original completo!
    # - Base repete `c2_watch` em loop normal para frente (`-stream_loop -1` direto em `c2_watch`, ZERO reverso!) em CROP 1:1 (`crop=720:564:0:{y_crop_f2}`)!
    seg2_mp4 = wdir / "seg2_watch_split.mp4"
    fc_seg2 = (
        f"[0:v]fps=30,scale=720:1280:flags=lanczos,crop=720:764:0:258,pad=720:1280:0:0:black[top];"
        f"[1:v]fps=30,scale=720:1280:flags=lanczos,crop=720:564:0:{y_crop_f2},format=rgba,"
        f"geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='if(lt(Y,44),255*Y/44,255)'[bot];"
        f"[top][bot]overlay=0:716:format=auto,format=yuv420p[vout]"
    )
    with NVENC_SEM:
        subprocess.run(
            [
                FFMPEG_BIN, "-y", "-loglevel", "error",
                "-i", str(rclone_mp4),
                "-stream_loop", "-1", "-i", str(c2_watch),
                "-filter_complex", fc_seg2,
                "-map", "[vout]", "-map", "0:a",
                "-t", f"{dur_viral:.3f}",
                "-af", "aresample=44100,volume=2.0dB,alimiter=limit=0.95",
                "-c:v", "h264_nvenc", "-preset", "p4", "-cq", "20",
                "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2",
                str(seg2_mp4),
            ],
            check=True,
        )

    # 3. SEG 3 (OUTRO TELA CHEIA 720x1280 APÓS O FIM COMPLETO DA RECEITA, COM BOTÃO 'FOLLOW FOR MORE ↓')
    seg3_mp4 = wdir / "seg3_outro_full.mp4"
    fc_seg3 = "[0:v]fps=30,scale=720:1280:flags=lanczos[base];[base][1:v]overlay=0:0:format=auto,format=yuv420p[vout]"
    with NVENC_SEM:
        subprocess.run(
            [
                FFMPEG_BIN, "-y", "-loglevel", "error",
                "-i", str(c3_outro),
                "-i", str(pill_png),
                "-filter_complex", fc_seg3,
                "-map", "[vout]", "-map", "0:a",
                "-c:v", "h264_nvenc", "-preset", "p4", "-cq", "20",
                "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2",
                str(seg3_mp4),
            ],
            check=True,
        )

    # 4. Concatena SEG 1 (Hook ~2.0s) + SEG 2 (Receita 100% Completa) + SEG 3 (Outro Tela Cheia ~4.0s)
    concat_txt = wdir / "concat.txt"
    concat_txt.write_text(
        f"file '{seg1_mp4.resolve().as_posix()}'\n"
        f"file '{seg2_mp4.resolve().as_posix()}'\n"
        f"file '{seg3_mp4.resolve().as_posix()}'\n",
        encoding="utf-8",
    )
    esteira_dst.parent.mkdir(parents=True, exist_ok=True)
    tmp_dst = esteira_dst.with_suffix(".tmp.mp4")
    with NVENC_SEM:
        subprocess.run(
            [
                FFMPEG_BIN, "-y", "-loglevel", "error",
                "-f", "concat", "-safe", "0", "-i", str(concat_txt.resolve()),
                "-c:v", "h264_nvenc", "-preset", "p6", "-tune", "hq", "-multipass", "fullres",
                "-rc", "vbr", "-rc-lookahead", "20", "-cq", "25",
                "-b:v", "1100k", "-maxrate", "1600k", "-bufsize", "3000k",
                "-spatial_aq", "1", "-temporal_aq", "1", "-aq-strength", "8",
                "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "96k", "-ar", "44100", "-movflags", "+faststart",
                str(tmp_dst.resolve()),
            ],
            check=True,
        )
    tmp_dst.replace(esteira_dst)

    for dst in (hub_dst, drv_diario, drv_cofre):
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(esteira_dst), str(dst))
        except Exception:
            pass

    dur_f = float(obter_metadados_midia(esteira_dst).get("duracao_s") or (dur_hook + dur_viral + 4.0))
    sz_mb = round(esteira_dst.stat().st_size / 1048576, 2)
    print(
        f"=== [REACT V2 CONCLUIDO #{vid_idx:03d} | AV{av_num:03d} + {rclone_mp4.name[:22]}] Hook={dur_hook:.1f}s + Receita={dur_viral:.1f}s -> Total={dur_f:.2f}s | {sz_mb} MB ===",
        flush=True,
    )
    return {"ok": True, "idx": vid_idx, "av_num": av_num, "path": str(esteira_dst), "dur": round(dur_f, 2), "mb": sz_mb}


def gerar_tira_react_auditoria(mp4_path: pathlib.Path, out_jpg: pathlib.Path) -> None:
    cap = cv2.VideoCapture(str(mp4_path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    n_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    dur = max(1.0, n_frames / fps)
    thumbs = []
    for i in range(15):
        t = (i + 0.5) * dur / 15.0
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
        ok, fr = cap.read()
        if not ok:
            fr = np.zeros((1280, 720, 3), dtype=np.uint8)
        th = cv2.resize(fr, (240, 426))
        cv2.rectangle(th, (0, 0), (240, 26), (0, 0, 0), -1)
        cv2.putText(th, f"REACT V2 t={t:.1f}s", (6, 19), cv2.FONT_HERSHEY_SIMPLEX, 0.46, (0, 255, 180), 1, cv2.LINE_AA)
        thumbs.append(th)
    cap.release()
    rows = [np.hstack(thumbs[r * 5 : (r + 1) * 5]) for r in range(3)]
    cv2.imwrite(str(out_jpg), np.vstack(rows), [int(cv2.IMWRITE_JPEG_QUALITY), 92])


def main() -> None:
    t0 = time.time()
    ap = argparse.ArgumentParser()
    ap.add_argument("--avatars", type=int, default=50)
    ap.add_argument("--videos", type=int, default=105)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--test-pilot1", action="store_true", help="Gera o Piloto #1 (AV001 c/ Realismo Fusão Suprema V2 + AD06 JSON em Low Priority)")
    args = ap.parse_args()

    contas = listar_contas_flow_ativas(forcar_scan=True) or ["http://127.0.0.1:9225"]
    catalogo = _carregar_ou_gerar_catalogo_105()
    rclone_files = sorted(RCLONE_DIR.glob("*.mp4"))

    print(
        f"=== MOTOR REACT PYONG LEE V2 (FUSAO SUPREMA V2 + AD06 JSON) | {args.avatars} AVATARES + {min(args.videos, len(rclone_files))} VIDEOS | CONTAS: {contas} ===",
        flush=True,
    )

    if args.test_pilot1:
        av1 = _gerar_ou_carregar_avatar_fixo(1, contas[0], apenas_frames=False)
        rc0 = rclone_files[1] if len(rclone_files) > 1 else rclone_files[0]
        res = montar_video_react_pyong_nvenc(1, rc0, catalogo.get(rc0.name, {}), av1, forcar_remontar=True)
        out_strip = ARTIFACTS_DIR / "inspect_pilot1_v2_realismo_pyong_15frames.jpg"
        gerar_tira_react_auditoria(pathlib.Path(res["path"]), out_strip)
        # Salva também o par F1 + F2 do AV001 em alta resolução para inspeção de pele/realismo
        im1 = cv2.resize(cv2.imread(av1["f1"]), (360, 640))
        im2 = cv2.resize(cv2.imread(av1["f2"]), (360, 640))
        out_av_preview = ARTIFACTS_DIR / "inspect_av001_v2_realismo_frames.jpg"
        cv2.imwrite(str(out_av_preview), np.hstack([im1, im2]), [int(cv2.IMWRITE_JPEG_QUALITY), 94])
        print(json.dumps({"ok": True, "video": res, "strip": str(out_strip), "avatar_frames": str(out_av_preview)}, indent=2))
        return

    n_av = max(1, min(50, int(args.avatars)))
    target_rclone = rclone_files[: max(1, int(args.videos))]
    avatars_prontos: dict[int, dict[str, Any]] = {}
    vids_prontos: list[pathlib.Path] = []

    nvenc_pool = concurrent.futures.ThreadPoolExecutor(max_workers=6)
    futs_v: dict[concurrent.futures.Future, int] = {}

    def _enfileirar_montagem_do_avatar(av_i: int, r_av: dict[str, Any]) -> None:
        for idx_v, rc_mp4 in enumerate(target_rclone, start=1):
            if ((idx_v - 1) % n_av) + 1 == av_i:
                fut_m = nvenc_pool.submit(
                    montar_video_react_pyong_nvenc,
                    idx_v,
                    rc_mp4,
                    catalogo.get(rc_mp4.name, {}),
                    r_av,
                    False,
                )
                futs_v[fut_m] = idx_v

    for av_i in range(1, n_av + 1):
        av_dir = AVATARS_BANK_DIR / f"AV{av_i:03d}"
        c1_t = av_dir / "clip_1_hook_trim.mp4"
        c2_t = av_dir / "clip_2_watch_trim.mp4"
        c3_t = av_dir / "clip_3_outro_trim.mp4"
        if (
            c1_t.exists() and c1_t.stat().st_size > 30_000
            and c2_t.exists() and c2_t.stat().st_size > 30_000
            and c3_t.exists() and c3_t.stat().st_size > 30_000
        ):
            hook_spec = PYONG_HOOKS_EN[(av_i - 1) % len(PYONG_HOOKS_EN)]
            outro_spec = OUTRO_CTA_SPECS[(av_i - 1) % len(OUTRO_CTA_SPECS)]
            r_av_cached = {
                "av_num": av_i,
                "av_dir": av_dir,
                "f1": str(av_dir / "frame_1_talking.jpg"),
                "f2": str(av_dir / "frame_2_watching_phone.jpg"),
                "c1": str(c1_t),
                "c2": str(c2_t),
                "c3": str(c3_t),
                "hook_fala": hook_spec["fala"],
                "outro_fala": outro_spec["fala"],
            }
            avatars_prontos[av_i] = r_av_cached
            _enfileirar_montagem_do_avatar(av_i, r_av_cached)

    pend_iniciais = [av_i for av_i in range(1, n_av + 1) if av_i not in avatars_prontos]
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(args.workers, max(1, len(pend_iniciais)))) as ex:
        futs = {
            ex.submit(
                _gerar_ou_carregar_avatar_fixo,
                av_i,
                contas[(av_i - 1) % len(contas)],
                False,
            ): av_i
            for av_i in pend_iniciais
        }
        for f in concurrent.futures.as_completed(futs):
            av_i = futs[f]
            try:
                r_av = f.result()
                avatars_prontos[av_i] = r_av
                _enfileirar_montagem_do_avatar(av_i, r_av)
                print(
                    f"  >>> AVATAR V2 AV{av_i:03d} PRONTO ({len(avatars_prontos)}/{n_av}) -> MONTANDO REACTS NA GPU! ({(time.time()-t0)/60.0:.1f} min) <<<",
                    flush=True,
                )
            except Exception as exc:
                print(f"!! [FALHA AV{av_i:03d}] {exc}", flush=True)

    for retry_r in range(1, 4):
        pend_av = [i for i in range(1, n_av + 1) if i not in avatars_prontos]
        if not pend_av:
            break
        print(f"=== [RETRY AVATARES V2 RODADA {retry_r}: {len(pend_av)} PENDENTES] ===", flush=True)
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(6, len(pend_av))) as ex:
            futs2 = {
                ex.submit(
                    _gerar_ou_carregar_avatar_fixo,
                    av_i,
                    contas[(av_i - 1) % len(contas)],
                    False,
                ): av_i
                for av_i in pend_av
            }
            for f in concurrent.futures.as_completed(futs2):
                av_i = futs2[f]
                try:
                    r_av = f.result()
                    avatars_prontos[av_i] = r_av
                    _enfileirar_montagem_do_avatar(av_i, r_av)
                except Exception as exc:
                    print(f"!! [FALHA RETRY AV{av_i:03d}] {exc}", flush=True)

    for fut_m in concurrent.futures.as_completed(list(futs_v.keys())):
        idx_v = futs_v[fut_m]
        try:
            rv = fut_m.result()
            vids_prontos.append(pathlib.Path(rv["path"]))
        except Exception as exc:
            print(f"!! [FALHA MONTAGEM REACT #{idx_v:03d}] {exc}", flush=True)
    nvenc_pool.shutdown(wait=True)

    if vids_prontos:
        gerar_tira_react_auditoria(sorted(vids_prontos)[0], ARTIFACTS_DIR / "tira_lote_105_react_pyong_v2.jpg")

    print(
        json.dumps(
            {
                "avatares_gerados": len(avatars_prontos),
                "videos_react_montados": len(vids_prontos),
                "esperados": len(target_rclone),
                "tempo_s": round(time.time() - t0, 1),
            },
            ensure_ascii=False,
            indent=2,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
