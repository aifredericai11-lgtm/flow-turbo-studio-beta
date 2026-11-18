# -*- coding: utf-8 -*-
"""
forja/diretor_realismo_pastel_euojeff.py
========================================
REGRA FIXA GERAL — PLAYBOOK DE REALISMO PASTEL (@euojeff) + SKILL `ugc-raw-footage` + DIRETOR DE ANIMAÇÃO IA (`AD06`)

Integra 100% as 3 fontes oficiais do usuário:
1. `ugc-raw-footage/SKILL.md` + `references/beginner-workflow.md` + `references/calibration-protocol.md`:
   - `MODE: GENERATE_FROM_ZERO` (`refs=[]` na Cena 1; referências visuais de estilo são `STYLE_ANALYSIS_ONLY` e jamais vão como âncora de identidade).
   - `COLOR PIPELINE`: Raw ungraded smartphone footage, straight-out-of-camera color, neutral white balance and faithful natural skin tone. No LUT, no cinematic grade, no warm filter, no orange/yellow skin, no beauty filter. Keep neutral surfaces neutral.
   - `BRIGHT-SOURCE RESPONSE`: Let the in-frame practical ceiling light or window clip naturally under phone autoexposure into a larger white shape with source-shaped bloom and a faint localized lens veil/reflection, while the far cheek and room recesses fall off naturally (ZERO HDR falso onde luz, rosto e sombra ficam todos perfeitamente detalhados).
   - `LOW-AMPLITUDE SKIN SIGNAL`: Variação tonal fina, rubor localizado, olheira suave e acutância local alta apenas em íris/cílios/linha do cabelo, SEM poros desenhados em relevo duro na cara inteira e SEM rugas esculpidas artificialmente.
   - `DEFAULT DEPTH BEHAVIOR`: Profundidade de campo ampla de smartphone (23–26mm frontal sem modo Retrato) onde armários, rejunte, eletrodomésticos e objetos a 0,5–3m permanecem 100% legíveis, com leve desequilíbrio natural de enquadramento e momento capturado entre fonemas (nunca pose centralizada de estúdio).
2. `#01 PLAYBOOK -> Realismo em suas Gerações @euojeff.md` + Regra Fixa "Só Enfermeiras":
   - Exclusivamente enfermeiras mulheres em scrubs foscos dessaturados/pastéis (`dusty plum`, `faded slate-blue`, `muted eucalyptus-sage`, `washed charcoal`, ou jaleco fosco sobre scrub) + estetoscópio + crachá hospitalar, em cozinhas domésticas vividas com objetos mostrando sinais reais de uso.
3. `AD06 - Diretor de Animação IA — Versão Beta @euojeff` (`Documento sem título.md`):
   - Prompt JSON de animação para Veo 3.1 com física biomecânica causal (`ombro -> cotovelo -> punho -> mão`), compressão elástica real da pele, viscosidade real da mistura e acústica de celular apoiado na bancada.
"""

from __future__ import annotations

import json
import re
from typing import Any

# ══════════════════════════════════════════════════════════════════════════════
# 1. CONTRATOS INVARIANTES DA SKILL `ugc-raw-footage`
# ══════════════════════════════════════════════════════════════════════════════

COLOR_PIPELINE_UGC_RAW = (
    "COLOR PIPELINE: Raw ungraded smartphone footage, straight-out-of-camera color, "
    "neutral white balance and faithful natural skin tone. No LUT, no cinematic grade, "
    "no warm filter, no golden-hour cast, no orange/yellow skin, no teal-and-orange look "
    "and no beauty filter. Keep neutral walls, cabinets, whites and greys strictly neutral."
)

BRIGHT_SOURCE_RESPONSE_UGC_RAW = (
    "BRIGHT-SOURCE RESPONSE: Let the in-frame overhead ceiling light or window clip naturally "
    "under phone autoexposure into a larger pure-white shape with soft source-shaped bloom and "
    "a faint, localized lens veil extending slightly across the nearby ceiling/hair edge. "
    "Do not preserve clean bulb detail inside the lamp, and do not recover face, shadows and "
    "bright light with synthetic HDR perfection simultaneously; preserve the source-side highlight "
    "on the face and let the far cheek and room corners fall off naturally without invisible fill light."
)

LOW_AMPLITUDE_SKIN_AND_OPTICS_UGC_RAW = (
    "MATERIALS & LOW-AMPLITUDE SKIN: Preserve subtle, irregular low-amplitude skin variation "
    "(fine tonal shifts, mild localized redness around nose/cheeks, soft natural under-eye shadow, "
    "and small expression creases caused only by the current speech movement). High local acutance "
    "on the closer eye iris, eyelashes, hairline, facial hair/stubble and scrub fabric weave, WITHOUT embossed drawn-on "
    "pores across the whole face, WITHOUT hard-etched AI wrinkles, and WITHOUT porcelain smoothing. "
    "DEFAULT DEPTH BEHAVIOR: Ordinary front-facing iPhone camera (24mm equivalent, no Portrait mode) "
    "with broad depth of field — background walls, medical equipment, exam tables, cabinets "
    "and foreground props at 0.5m to 3m remain legible with recognizable edges and zero synthetic bokeh."
)

ACTIVE_PROP_HARMONY_RULE_UGC_RAW = (
    "ACTIVE PROP HARMONY (STRICTLY NO PASSIVE FINGER-POINTING): Whenever ingredients, containers, bowls, glasses, "
    "spoons, lemons, salt shakers, pitchers or anatomical models are present on the table/counter/tray, the nurse MUST "
    "physically hold, scoop, pour, squeeze, mix or apply them with both hands in natural harmony with the spoken action — "
    "NEVER stand passively pointing an index finger at the props on the table."
)

# ══════════════════════════════════════════════════════════════════════════════
# 2. POOLS DE ENFERMEIRAS E COZINHAS DOMÉSTICAS (`@euojeff` + `ugc-raw-footage`)
# ══════════════════════════════════════════════════════════════════════════════

ROUPAS_PASTEL_DESSATURADAS_EUOJEFF: list[str] = [
    "a washed dusty-plum matte cotton V-neck medical scrub top with soft lived-in fabric creases, a black clinical stethoscope draped slightly asymmetrically around her neck, and a clip-on hospital RN ID badge on her neckline",
    "an off-white matte cotton lab coat worn open over a muted sage-olive matte scrub top, with a clinical stethoscope around her neck and a hospital nurse practitioner ID badge clipped to the lapel",
    "a faded slate-blue matte cotton V-neck medical scrub top with natural fabric weave, a stethoscope around her neck, and a clip-on registered nurse ID badge",
    "a muted heather-charcoal matte cotton V-neck medical scrub top with zero gloss, a clinical stethoscope around her neck, and a clip-on hospital RN badge",
    "a washed eucalyptus-sage matte cotton medical scrub top with subtle lived-in folds, a stethoscope around her neck, and a clip-on nurse ID badge",
]

CENARIOS_DOMESTICOS_PASTEL_EUOJEFF: list[str] = [
    (
        "an ordinary lived-in American home kitchen with neutral off-white shaker cabinets, a muted slate-blue island base, "
        "an in-frame overhead ceiling light fixture near the top edge that clips naturally into a bright white bloom, "
        "a stainless refrigerator in the back with paper notes and magnets, a fruit bowl on the back counter, "
        "and a neutral white-and-grey marble countertop angled from the bottom-left foreground"
    ),
    (
        "an unpolished everyday American kitchen with neutral matte cream cabinets, a side window on the left whose bright daylight "
        "partially clips on the window trim while casting directional neutral light across the counter, "
        "an overhead flush-mount ceiling lamp, a black drip coffee maker and two matte ceramic mugs in the background, "
        "and a neutral stone countertop angled from the bottom-left foreground"
    ),
    (
        "a lived-in home kitchen at night under evening practical lighting only — an overhead ceiling fixture near the top frame edge "
        "clips into a bright white shape with localized bloom, while the lower wooden cabinets, back corners and dark window collect "
        "subtle localized phone shadow noise and mild codec softness, with a neutral marble counter in the bottom-left foreground"
    ),
]


def compilar_prompt_ugc_raw_footage(
    *,
    indice_cena: int,
    subject_enfermeira: str,
    moment_em_andamento: str,
    capture_profile: str = "INDOOR_DAYLIGHT_SELFIE",
    capture_details: str = (
        "Front-facing smartphone camera (24mm equivalent) propped on the kitchen counter at chest-to-eye distance; "
        "slight natural framing imbalance with the speaker slightly off-center and one shoulder closer to the frame edge; "
        "broad smartphone depth of field with legible domestic background and zero portrait bokeh"
    ),
    light_behavior: str = (
        "Directional daylight from a side kitchen window combined with an in-frame overhead ceiling light fixture; "
        "the overhead fixture clips into a bright white shape with soft localized bloom and a faint contrast veil right below it, "
        "while the far cheek and kitchen recesses fall off into natural shadow without studio fill"
    ),
    product_and_props: str = (
        "In the bottom-left foreground on the marble counter sits an everyday orange cardboard baking soda box, "
        "a clear water glass, and a metal spoon with spilled white baking soda powder; she holds a small white ceramic bowl "
        "with creamy white baking soda paste smeared on the inner rim"
    ),
    cta: bool = False,
) -> str:
    """
    Monta o prompt de geração de imagem seguindo o Baseline Prompt Assembly de 10 blocos da skill `ugc-raw-footage`
    (`MODE`, `SUBJECT`, `MOMENT`, `CAPTURE`, `LIGHT`, `BRIGHT-SOURCE RESPONSE`, `MATERIALS`, `PRODUCT`, `COLOR PIPELINE`, `COMPOSITION`).
    - Na Cena 1 (`indice_cena == 0`): `MODE: GENERATE_FROM_ZERO` (`refs=[]`).
    - Nas Cenas 2 e 3 (`indice_cena >= 1`): `MODE: EDIT_TARGET` sobre o `frame_1.jpg` aprovado (`refs=[f1_id]`),
      preservando 100% a enfermeira, o ambiente, a exposição e os objetos, mudando apenas o gesto e os lábios.
    """
    if indice_cena == 0:
        header_mode = (
            "No text or UI in the image. MODE: GENERATE_FROM_ZERO (single unretouched smartphone video frame captured mid-recording). "
        )
        preserve_block = ""
    else:
        header_mode = (
            "No text or UI in the image. MODE: EDIT_TARGET (continuous frame from the exact same smartphone video recording as reference photo 1). "
        )
        preserve_block = (
            "PRESERVE: Keep the exact same handsome male registered nurse (same face, jawline, hair, beard/stubble, skin tone, matte pastel V-neck nursing scrub top, stethoscope, RN badge — strictly NO doctor lab coat), "
            "the exact same room/hospital/clinic/kitchen background, clipped ceiling light bloom, shadow falloff and camera angle "
            "from reference photo 1; update his speaking mouth aperture, hand action and foreground props exactly as specified in MOMENT and PRODUCT & PROPS. "
        )

    cta_moment = ""

    return (
        f"{header_mode}"
        f"{preserve_block}"
        f"SUBJECT: {subject_enfermeira.rstrip('. ')}. "
        f"MOMENT: {moment_em_andamento.rstrip('. ')}.{cta_moment} "
        f"CAPTURE ({capture_profile}): {capture_details.rstrip('. ')}. "
        f"LIGHT: {light_behavior.rstrip('. ')}. "
        f"{BRIGHT_SOURCE_RESPONSE_UGC_RAW} "
        f"{LOW_AMPLITUDE_SKIN_AND_OPTICS_UGC_RAW} "
        f"{ACTIVE_PROP_HARMONY_RULE_UGC_RAW} "
        f"PRODUCT & PROPS: {product_and_props.rstrip('. ')}. "
        f"{COLOR_PIPELINE_UGC_RAW} "
        f"COMPOSITION: Vertical 9:16 raw smartphone frame, imperfect candid crop, no centered stock-photo symmetry, "
        f"strictly no camera app UI, no grids, no text overlays, no watermarks."
    ).strip()


# Compatibilidade direta com chamadas existentes
def compilar_prompt_imagem_5_partes_euojeff(
    *,
    indice_cena: int,
    personagem: str,
    cenario: str,
    objetos_com_uso: str,
    acao_fisica: str,
    enquadramento_celular: str = (
        "Front-facing smartphone camera (24mm equivalent) propped on the kitchen counter with slight natural framing imbalance "
        "and broad depth of field where the domestic background remains completely legible"
    ),
    sexo: str = "f",
    cta: bool = False,
    trocar_identidade_em_massa: bool = True,
) -> str:
    return compilar_prompt_ugc_raw_footage(
        indice_cena=indice_cena,
        subject_enfermeira=personagem,
        moment_em_andamento=acao_fisica,
        capture_profile="INDOOR_DAYLIGHT_SELFIE",
        capture_details=enquadramento_celular,
        light_behavior=cenario,
        product_and_props=objetos_com_uso,
        cta=cta,
    )


def compilar_json_animacao_fisica_euojeff(
    *,
    indice_cena: int,
    fala_ingles: str,
    abertura_instantanea: str,
    gesto_biomecanico: str,
    fisica_pele_ou_objeto: str,
    enquadramento_camera: str = (
        "Close-medium conversational kitchen counter smartphone framing. Preserve the exact slight framing imbalance, "
        "broad depth of field and clipped ceiling light bloom from the input image."
    ),
    descricao_voz_acustica: str = (
        "Native American female registered nurse approximately 42–55 years old, natural mid-register (~186 Hz), "
        "slightly textured everyday voice, warm clinical resonance and spontaneous UGC personality."
    ),
    sexo: str = "f",
    cta: bool = False,
    idioma: str = "EN",
) -> str:
    """
    Replica 100% a estrutura JSON exata do `AD06 - Diretor de Animação IA — Versão Beta @euojeff`
    (`H:\\Meu Drive\\HUB CENTRAL OP ORGÂNICO\\Realismo _ MDs\\Documento sem título.md`)
    adaptada para as enfermeiras em inglês americano nativo (`EN`) ou espanhol neutro (`ES`)
    no Veo 3.1 (`veo_3_1_i2v_lite_low_priority`).
    """
    ator = "male" if sexo.lower().startswith("m") else "female"
    pron = "He" if sexo.lower().startswith("m") else "She"
    poss = "his" if sexo.lower().startswith("m") else "her"
    eh_es = str(idioma or "EN").upper().startswith("ES")
    fala_limpa = re.sub(r'["“”]', "", (fala_ingles or "").strip())
    fala_limpa = re.sub(r"\bcomment\s+['\"]?YES['\"]?\b", "comment yes", fala_limpa, flags=re.I)
    fala_limpa = re.sub(r"\bcomenta\s+['\"]?S[ÍI]['\"]?\b", "comenta sí", fala_limpa, flags=re.I)

    performance_block: dict[str, Any] = {
        "opening": abertura_instantanea,
        "energy": (
            "Very fast direct closing instruction."
            if cta
            else (
                "Fast mechanism and clinical proof explanation."
                if indice_cena == 1
                else "Urgent, spontaneous clinical hook captured mid-action."
            )
        ),
        "eye_contact": "Unbroken direct lens contact." if cta else "Strong direct lens contact.",
        "expression": (
            "Confident, casual and action-oriented."
            if cta
            else (
                "Concerned, authoritative and animated."
                if indice_cena == 1
                else "Alert eyes, raised brows and genuine clinical urgency."
            )
        ),
        "gesture": (
            f"{gesto_biomecanico.rstrip('. ')}. "
            "CRITICAL PROP HARMONY RULE: Physically use, hold, scoop, squeeze, pour or apply the objects and ingredients with both hands in natural coordination with the speech — NEVER passively point a finger at the props on the table."
        ),
        "skin_physics": fisica_pele_ou_objeto,
        "body": (
            "Physically lean slightly closer during the instruction, then finish with an expectant direct look."
            if cta
            else "Brief forward torso emphasis on the key phrase, then a tiny natural settle before continuing."
        ),
        "pace_rule": "Facial reactions and gesture timing are quick and tightly synchronized with the rapid speech.",
    }
    if cta:
        performance_block["ending"] = "Finish close with a confident, expectant direct look into the camera lens."

    payload_diretor: dict[str, Any] = {
        "visual_reference": (
            f"Animate the exact {ator} registered nurse avatar from the input image. Preserve exact identity, apparent age, face, "
            f"jawline, facial hair/stubble, low-amplitude natural skin, hair strands, matte pastel nursing scrub top, stethoscope, RN badge, body proportions, "
            f"exact room environment (hospital operating room, clinical exam room, or home kitchen), recognizable background elements, foreground props, "
            f"clipped ceiling light bloom, framing and live-action realism exactly."
        ),
        "visual_style": {
            "format": "vertical 9:16",
            "look": "hyper-realistic American UGC talking-head, raw ungraded smartphone footage, straight-out-of-camera neutral color",
            "energy": "Fast, raw, urgent and spontaneous, never polished commercial acting.",
        },
        "camera": {
            "mode": "DIRECT FRONT-FACING SMARTPHONE CAMERA POV",
            "critical_pov_rule": (
                "The viewer is looking through the invisible recording smartphone itself. "
                "Never render a visible phone or recording equipment."
            ),
            "framing": enquadramento_camera,
            "restriction": "No zoom, cuts, transitions or artificial push-in.",
        },
        "physical_camera_behavior": {
            "core_rule": (
                "Fast body emphasis and pointing/touching movements follow shoulder -> elbow -> wrist -> fingers mechanics "
                "and create proportional real shoulder, arm and wrist response, brief framing displacement, tiny inertia "
                "and one natural settling correction."
            ),
            "forbidden": "No random shake, repetitive vibration or gimbal motion.",
        },
        "performance": performance_block,
        "voice_identity": {
            "critical_rule": f"USE THE EXACT SAME {ator.upper()} VOICE IDENTITY THROUGHOUT THE ENTIRE AD.",
            "profile": descricao_voz_acustica,
            "identity_lock": (
                "Preserve the exact same vocal age, baseline pitch, pitch range, timbre, resonance, texture, "
                "accent and speaking personality in every clip."
            ),
            "no_voice_drift": "Energy changes prosody only, never speaker identity.",
        },
        "speech_direction": {
            "language": (
                "Native neutral Latin American / Mexican-American Spanish speech (es-MX / es-US)."
                if eh_es
                else "Native American English speech."
            ),
            "lip_sync": "Accurate Spanish lip sync." if eh_es else "Accurate English lip sync.",
            "pronunciation": (
                "Natural contemporary Latin American Spanish pronunciation (pronouncing 'sí' naturally as a single word)."
                if eh_es
                else "Natural contemporary American English pronunciation."
            ),
            "delivery": (
                "FAST, high-energy conversational Spanish UGC delivery around 190–210 words per minute, while remaining completely intelligible and fully articulated."
                if eh_es
                else "FAST, high-energy conversational American UGC delivery around 190–210 words per minute, while remaining completely intelligible and fully articulated."
            ),
            "rhythm": "Minimal dead air, very short natural breaths, tiny punctuation pauses only.",
            "tone": (
                "Direct and casual, not commercial."
                if cta
                else "Urgent, authoritative yet warm practical explanation from a real nurse."
            ),
            "critical_rule": (
                "Begin speaking immediately on the first frame. Never drag vowels, over-pause or slow down for dramatic effect. "
                + ("Never spell out the word sí letter-by-letter." if eh_es else "Never spell out the word yes letter-by-letter.")
            ),
            "forbidden": "No announcer voice, no commercial voice, no whisper, no slurring.",
        },
        "audio_perspective": {
            "core_rule": f"Natural smartphone-distance vocal perspective continuously matching {poss} visible physical distance."
        },
        "audio": {
            "quality": (
                "Premium professional studio microphone; treated acoustic environment; crystal-clear and clean vocal track; "
                "high-fidelity speech; voice centered and in the foreground; stable volume; clean consonants and full vowels."
            ),
            "only_audible_element": "SPOKEN VOICE IS THE ONLY AUDIBLE ELEMENT.",
            "forbidden": (
                "No music, background noise, room tone, Foley, movement sounds, pops, clicks, echo or reverberation; "
                "no perceptible compression, clipping, metallic voice or gain pumping."
            ),
        },
        "spoken_audio_lock": (
            "IMPORTANT — SPOKEN AUDIO ONLY:\n"
            "The dialogue must be generated exclusively as spoken audio. Never display, transcribe, caption, quote or "
            "visualize any part of the spoken sentence inside the video.\n"
            "ABSOLUTELY NO visible text at any moment: no subtitles, no captions, no closed captions, no automatic transcription, "
            "no burned-in dialogue, no kinetic typography, no speech bubbles, no words, no letters, no quote marks, no labels, "
            "no interface elements, no overlays, no watermarks and no added logos.\n"
            + (
                "The following sentence is spoken aloud in native Spanish (es-MX / es-US). It is audio dialogue only and must never appear visually:"
                if eh_es
                else "The following sentence is spoken aloud in native American English. It is audio dialogue only and must never appear visually:"
            )
        ),
        "dialogue": fala_limpa,
        "final_visual_restriction": (
            "FINAL VISUAL RESTRICTION: The spoken dialogue is audio only. The entire video must contain zero visible text "
            "from the first frame to the last frame. Do not render any transcription or written representation of the dialogue."
        ),
    }

    lang_word = "Spanish" if eh_es else "English"
    prefixo_veo = (
        "RAW UNEDITED SMARTPHONE CAMERA FOOTAGE (STRICTLY ZERO ON-SCREEN TEXT, ZERO SUBTITLES, "
        "ZERO CAPTIONS, ZERO SOCIAL MEDIA UI OR COMMENT BARS AT THE BOTTOM). "
        f"The {ator} nurse in the reference image speaks aloud in {lang_word} (spoken audio only, never written on screen): {fala_limpa}\n"
    )
    return prefixo_veo + json.dumps(payload_diretor, ensure_ascii=False)
