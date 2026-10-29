"""
Compilador Determinístico de Realismo, Física, Voz (Hz), Animação, Juízes e Tesoura (Padrão Flow Turbo Studio).

Extraído e portado 1:1 da interceptação AO VIVO do ciclo completo de geração no Zerum
(`zerum-build:20261024T1400-estagios24-783315d`, lotes reais `L-PENSANTE-dde74994-6645959D` e `L-PENSANTE-2192d1a5-6645959D`):

1. `QUADRO_PROMPT_18 + DUAL_REF_LOCK (quadroRefs18)`:
   - Cena 1 (`quadro1`): Usa `[avatarRefId]` + `IDENTITY LOCK` + `APPROVED OUTFIT (portrait photo 1)` + `LOCATION LOCK` + `HOOK OBJECT (... END HOOK OBJECT)`.
   - Cena 2+ (`quadro-novo`): Usa **2 referências** `[avatarRefId, scene1ApprovedMediaId]`!
     - Foto 1 = Identidade facial/cabelo/idade (`0 em 406 quadros de troca de cabelo`).
     - Foto 2 = Cena 1 aprovada para `APPROVED OUTFIT: P1 wears the garments P1 wears in the approved scene-1 frame, not those of reference photo 1` (`0 vazamento de roupa em 209 vídeos`) + `SCENE CONTINUITY (... END CONTINUITY)`.
   - Cena Final (`cta=True`): Injeta `CTA LAW: in this closing shot the speaker talks to the camera with both hands resting still and low by the body.`

2. `ESTAGIOS_24 (Antes/Depois em 3 Estágios: DAY 1 / DAY 15 / DAY 30 + Trava de Gênero Corporal)`:
   - Homem transformado NUNCA recebe corpo feminino (`strict male/female anatomical torso lock`).
   - Progressão explícita em 3 estágios (`DAY 1` inicial -> `DAY 15` intermediário -> `DAY 30` definido).

3. `MONTADOR_C2_VIDEO_PROMPT (Fala Literal na Frase #1)`:
   - A Frase #1 do prompt do Veo 3.1 (`generate.video`) é SEMPRE a fala literal entre aspas:
     `The man/woman in the reference image says in English: "<FALA_LITERAL>"`
   - Garante início imediato da fala (`0.06s..0.56s`) e preservação literal de `"Save this video, comment yes, and follow me so I can send you the recipe."` sem truncar `"save this video"`.

4. `JUIZES_VISAO_KIE (3 Camadas + Reparo Cirúrgico por Prepend)`:
   - Juiz 1 (`Compare identity and worn accessories` entre `[Avatar, Cena 1, Cena N]`): se `same_accessories == False`, faz prepend cirúrgico `"The person wears the same accessories visible in the reference."` e regenera SÓ o quadro daquela cena.
   - Juiz 2 (`Judge ONE native-resolution generated frame only` - schema fechado de 23 campos com regra `LIMBS AT THE EDGE`).
   - Juiz 3 (`Review ONLY this DELIVERED clip` - 5 imagens: `0.00s, 3.00s, 6.00s, last_frame, scene1_ref`).

5. `TESOURA_3_PASSES (Whisper + wav2vec2-ctc-onnx-en hop_ms=20) + LEGENDA_ASS_11_ESTILOS`:
   - Pass 1: Alinha o clipe bruto de 8s e corta alucinações finais do Veo 3.1 (ex.: `"okay thank you"` em `6.82s..7.84s` -> `trimEnd = 6.4s`).
   - Pass 2: Earcheck no clipe aparado (`casadas == total`).
   - Pass 3: Micro-slice dos últimos `2.0s` para provar que a última palavra não foi decepada.
   - Montagem com os 11 estilos `.ass` oficiais (`Leg`, `Uma`, `Kar`, `Cmd`, `Board`, `Top`, `DayTag`, `Word`, `Cta`, `Seta`, `Angel`).
"""

from __future__ import annotations

import re
from typing import Any

LEI_REALISMO_PESSOA = (
    "UNPROCESSED RAW SMARTPHONE FOOTAGE (counter-propped iPhone 15 Pro 24mm f/1.78 camera, natural Rec.709 color science, zero beauty filter, zero AI plastic smoothing): "
    "Vertical 9:16 candid phone framing, natural directional window daylight combined with slightly blown-out overhead recessed ceiling LED highlights, deep optical phone depth of field. "
    "PHYSICALLY ACCURATE SURFACE & SPECULAR REFLECTIONS: the foreground polished stone/quartz/granite countertop surface displays real mirror-like specular light reflections of the overhead light and window daylight, "
    "subtle inverted surface reflections of the tabletop containers, boxes and the speaker's forearms, plus realistic contact shadows and light caustics refracted onto the polished stone surface. "
    "Authentic human skin subsurface scattering, visible pores, subtle natural T-zone sheen/oiliness on forehead, nose and skin, and a lived-in everyday American background (not overly sterile or artificial). "
    "ONE single photograph filling the whole frame — never a grid, collage, split screen, panels or multiple moments."
)

LEI_CONSISTENCIA_OBJETOS_CENA = (
    "STRICT SCENE-TO-SCENE PROP & TABLETOP CONTINUITY (ZERO DUPLICATE CONTAINERS): "
    "Keep the exact same polished countertop surface, specular light reflections, and lived-in background architecture across all 3 scenes. "
    "Do not invent extra containers or duplicate glasses on the countertop when the speaker is already holding the glass in their hand."
)

LEI_REALISMO_MAOS = (
    "real hands with visible skin texture, pores, fine lines and natural slight asymmetry; "
    "the ingredients and containers look like real everyday products with real specular reflections and light caustics on the polished stone countertop; "
    "shot on a regular phone camera from directly above, slightly imperfect candid framing, "
    "NOT airbrushed, NOT editorial"
)

LEI_ANATOMIA_MAOS = (
    "Exactly ONE pair of adult hands in the frame — two hands, five fingers each, "
    "both belonging to the same person; no second pair of hands, no other person, "
    "nothing above the forearms is shown"
)

CRITICAL_SHOT_RULE_PESSOA = (
    "Locked shot, no camera move, no cut. Unprocessed raw phone camera footage with natural specular reflections on the polished countertop stone and real light caustics. "
    "For the whole clip: the same person (face, hair, body build, skin), the same clothes/accessories, the same place, the same light, and the EXACT SAME containers and props on the countertop as in the reference image; "
    "never morph, duplicate or swap containers during the clip; nobody else in the frame. "
    "Clean picture for the whole clip: strictly NO on-screen text, NO subtitles, NO captions, NO social media UI, NO comment box overlay, and NO icons appear at any point; only the filmed scene with existing package labels unchanged."
)

CRITICAL_SHOT_RULE_MAOS = (
    "CRITICAL SHOT RULE: this is ONE single continuous locked overhead take. "
    "The framing and the background stay EXACTLY the same from the very first frame to the very last frame. "
    "Absolutely NO fade-in, NO fade-out, NO dissolve, NO zoom, NO camera movement, NO cut, NO transition. "
    "Hold the exact same clear image through the entire clip and end abruptly on a sharp, fully visible frame. "
    "FRAME RULE: the footage fills the ENTIRE frame edge to edge — NO phone frame, NO bezel, NO letterboxing."
)

CTA_LAW_QUADRO = (
    "CTA LAW: in this closing shot the speaker stands behind the exact same polished countertop looking directly at the camera lens while delivering the call to action; "
    "keep the exact same background, lighting, and tabletop props from Scene 2 without duplicating any glass or container."
)
CTA_LAW_VIDEO = "The speaker gestures naturally toward the camera lens while speaking; all tabletop props stay consistent with the reference frame, with zero on-screen text or UI overlays generated in the video."

PREPEND_REPARO_ACESSORIOS = (
    "CRITICAL OUTFIT & ACCESSORY REPAIR: The person MUST wear 100% the EXACT same shirt/scrub color, cap/headwear, and neck accessories (stethoscope) visible in Reference Image 1 (OVERRIDE Reference Image 2's clothing color and accessories)."
)
PREPEND_REPARO_OCULOS_ADD = "The person wears the exact same eyeglasses visible in Reference Image 1."
PREPEND_REPARO_OCULOS_REM = "The person does not wear eyeglasses, matching Reference Image 1."
PREPEND_REPARO_ROSTO = "CRITICAL IDENTITY REPAIR: The person has 100% the exact same face, facial structure, skin tone, hair, and age as Reference Image 1."
PREPEND_REPARO_OBJETOS = (
    "CRITICAL BACKGROUND & PROP CONTINUITY REPAIR: Keep 100% the exact same background walls, windows with blinds, cabinets, countertop stone, and lighting as Reference Image 1 (OVERRIDE Reference Image 2's background walls), and do NOT duplicate any box, bowl, or glass on the table."
)

ESTAGIOS_ANTES_DEPOIS_24: dict[str, dict[str, str]] = {
    "DAY 1": {
        "m": (
            "BEFORE/AFTER STAGE 1 (DAY 1 - INITIAL FULLER MALE BODY): male anatomical build with a visibly fuller "
            "male midsection, broader waist, fuller cheeks and neck while strictly preserving a masculine chest, "
            "masculine shoulders and male torso proportions (never a female body)."
        ),
        "f": (
            "BEFORE/AFTER STAGE 1 (DAY 1 - INITIAL FULLER FEMALE BODY): female anatomical build with a visibly fuller "
            "midsection, softer waist, fuller cheeks and neck while preserving natural feminine proportions."
        ),
    },
    "DAY 15": {
        "m": (
            "BEFORE/AFTER STAGE 2 (DAY 15 - MIDPOINT MALE PROGRESSION): noticeably slimmer male waist and flatter "
            "stomach than Day 1, leaner jawline and neck, intermediate progress while strictly keeping a masculine "
            "chest, shoulders and male torso."
        ),
        "f": (
            "BEFORE/AFTER STAGE 2 (DAY 15 - MIDPOINT FEMALE PROGRESSION): noticeably slimmer waist and flatter "
            "midsection than Day 1, leaner face and neck, clear intermediate transformation."
        ),
    },
    "DAY 30": {
        "m": (
            "BEFORE/AFTER STAGE 3 (DAY 30 - FINAL LEAN MALE RESULT): visibly lean, flat male abdomen, defined jawline "
            "and healthy masculine posture, strictly preserving male chest and shoulder anatomy."
        ),
        "f": (
            "BEFORE/AFTER STAGE 3 (DAY 30 - FINAL LEAN FEMALE RESULT): visibly lean, flat stomach, defined waistline "
            "and healthy confident posture."
        ),
    },
}

ASS_STYLESHEET_ZERUM_11 = """[Script Info]
ScriptType: v4.00+
PlayResX: 720
PlayResY: 1280
ScaledBorderAndShadow: yes
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Leg,Poppins Bold,56,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,5,1,2,40,40,320,1
Style: Uma,Poppins Black,110,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,9,0,2,30,30,320,1
Style: Kar,Poppins Bold,64,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,5,0,2,40,40,320,1
Style: Cmd,Anton,86,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,1,0,1,7,0,2,50,50,340,1
Style: Board,Poppins Bold,44,&H00FFFFFF,&H00FFFFFF,&H00000000,&H78000000,-1,0,0,0,100,100,0,0,3,14,0,8,50,50,150,1
Style: Top,Poppins Bold,36,&H00FFFFFF,&H00FFFFFF,&H00000000,&H78000000,-1,0,0,0,100,100,0,0,3,10,0,8,60,60,120,1
Style: DayTag,Anton,64,&H0000FFFF,&H0000FFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,1.5,0,8,0,0,12,1
Style: Word,Anton,70,&H00FFFFFF,&H00FFFFFF,&H00B45CF6,&H00000000,-1,0,0,0,100,100,1,0,1,6,0,2,40,40,560,1
Style: Cta,Montserrat Black,56,&H00141414,&H00141414,&H0000C4FF,&H00000000,-1,0,0,0,100,100,1,0,3,14,0,2,60,60,440,1
Style: CtaPillBg,Poppins Black,20,&H1214100E,&H1214100E,&H0000D9FF,&H80000000,-1,0,0,0,100,100,0,0,1,4.5,6,7,0,0,0,1
Style: CtaWordBadge,Poppins Black,20,&H0000D9FF,&H0000D9FF,&H00FFFFFF,&H00000000,-1,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1
Style: CtaTextLeft,Montserrat Black,56,&H00FFFFFF,&H00FFFFFF,&H00000000,&H90000000,-1,0,0,0,100,100,1.5,0,1,4,2,5,0,0,0,1
Style: CtaTextRight,Montserrat Black,62,&H000E0E0E,&H000E0E0E,&H00FFFFFF,&H00000000,-1,0,0,0,100,100,2,0,1,2.5,0,5,0,0,0,1
Style: Seta,Poppins Black,20,&H0000E5FF,&H0000E5FF,&H00000000,&H70000000,-1,0,0,0,100,100,0,0,1,4,2,7,0,0,0,1
Style: Angel,Poppins Bold,34,&H40FFFFFF,&H40FFFFFF,&H80000000,&H00000000,0,0,0,0,100,100,0,0,1,2,0,7,0,0,0,1
"""


def _hash_deterministico_voz(chave: str) -> int:
    h = 7
    for ch in chave:
        h = (h * 31 + ord(ch)) & 0xFFFFFFFF
    return h


def extrair_idade_avatar(descricao: str, padrao: int = 50) -> int:
    padroes = [
        r"(?:about\s+|aged?\s+|~)(\d{2})\b",
        r"\b(\d{2})\s*(?:-year-old|years?\s*old)\b",
        r"\bin\s+(?:her|his|their)\s+(?:late\s+|early\s+|mid\s+)?(\d{2})s\b",
    ]
    for p in padroes:
        m = re.search(p, descricao or "", re.IGNORECASE)
        if m and 18 <= int(m.group(1)) <= 99:
            return int(m.group(1))
    return padrao


def calcular_hz_avatar(avatar_id: str, descricao: str = "", sexo: str = "f") -> int:
    m = re.search(r"\b(\d{2,3})\s*Hz\b", descricao or "", re.IGNORECASE)
    if m and 75 <= int(m.group(1)) <= 350:
        return int(m.group(1))
    h = _hash_deterministico_voz(avatar_id or descricao or "voice")
    if sexo.lower().startswith("m"):
        return 115 + (h % 18)  # Ex: 125 Hz no hard test ao vivo
    return 176 + (h % 31)  # 176..206 Hz


def gerar_bloco_voz_fixa(
    avatar_id: str,
    descricao_avatar: str = "",
    sexo: str = "f",
    palavras_por_segundo: float = 2.6,
) -> str:
    """
    Gera o bloco `[VOICE]` exato interceptado no `montador c2` ao vivo:
    `[VOICE] Male, 50 years old, speaks American English, pitch around 125 Hz, resonant conversational texture, brisk engaging pace, confident energy, sentences end falling.`
    """
    genero = "Male" if sexo.lower().startswith("m") else "Female"
    idade = extrair_idade_avatar(descricao_avatar)
    hz = calcular_hz_avatar(avatar_id, descricao_avatar, sexo=sexo)
    ritmo = "brisk engaging pace" if palavras_por_segundo >= 2.7 else "steady conversational pace"
    return (
        f"[VOICE] {genero}, {idade} years old, speaks American English, pitch around {hz} Hz, "
        f"resonant conversational texture, {ritmo}, confident energy, sentences end falling."
    )


def limpar_texto_tela_do_prompt(prompt: str) -> tuple[str, list[str]]:
    """
    Remove instruções de texto na tela dos prompts visuais para que o modelo de imagem/vídeo
    nunca tente desenhar legendas tortas (as legendas entram via `.ass` na montagem).
    """
    extraidos: list[str] = []

    def _capturar(m: re.Match[str]) -> str:
        txt = (m.group(1) or "").strip()
        if txt:
            extraidos.append(txt)
        return ""

    limpo = re.sub(
        r'(?:\bon[- ]screen\s+(?:text|caption|label)|\btext\s+overlay|\btexto\s+na\s+tela|\blegenda\s+na\s+tela)'
        r'\s*(?::|reads?|says?|saying|reading)?\s*["\'“”]([^"\'“”]+)["\'“”]'
        r'(?:\s+(?:appears?|is displayed|is shown|at|on|near|in|aparece|no|na)\b[^.;\n]*)?',
        _capturar,
        prompt or "",
        flags=re.IGNORECASE,
    )
    limpo = re.sub(r"\s{2,}", " ", limpo).strip()
    return limpo, list(dict.fromkeys(extraidos))


def compilar_quadro_refs_18(
    indice_cena: int,
    avatar_media_id: str,
    cena1_aprovada_media_id: str | None = None,
) -> list[str]:
    """
    Implementa `quadroRefs18` capturado ao vivo no Zerum:
    - Cena 1 (`indice_cena == 0`): `[avatar_media_id]` (1 referência)
    - Cena 2+ (`indice_cena >= 1`): `[avatar_media_id, cena1_aprovada_media_id]` (Dupla referência:
      Foto 1 trava rosto/cabelo/idade; Foto 2 trava roupa/acessórios/cenário/luz da Cena 1 aprovada).
    """
    refs = [avatar_media_id] if avatar_media_id else []
    if indice_cena > 0 and cena1_aprovada_media_id and cena1_aprovada_media_id not in refs:
        refs.append(cena1_aprovada_media_id)
    return refs


def compilar_prompt_quadro_cena(
    *,
    indice_cena: int,
    descricao_visual: str,
    sexo: str = "f",
    enquadramento: str = "framed chest-up in vertical 9:16 format",
    cenario_lock: str = "",
    roupa_lock: str = "",
    hook_object: str = "",
    cta: bool = False,
    camera_modo: str = "fixo",
    painel: str | None = None,
    estagio_corporal: str | None = None,
    reparo_prepend: str = "",
) -> str:
    """
    Implementa `quadroPrompt18` exato interceptado ao vivo em `/ia/receita` (`quadro1` e `quadro-novo`) + `montador c2`:
    - `No text in the image.`
    - `[reparo_prepend]` (se o Juiz de Visão detectou `accessories_changed` ou `face_changed`)
    - `IDENTITY LOCK: the speaker is the man/woman in reference photo 1, with his/her own face, skin, age and hair from that photo; the same person in every shot.`
    - `APPROVED OUTFIT`:
      - Na Cena 1: `P1 wears exactly the same garments and accessories seen on the person in approved portrait photo 1...`
      - Nas Cenas 2+: `P1 wears the garments P1 wears in the approved scene-1 frame, not those of reference photo 1; the same garments, colors and accessories in every shot. Ignore any other clothing mentioned for P1 in this scene. END OUTFIT.`
    - `LOCATION LOCK: ...`
    - `HOOK OBJECT (... END HOOK OBJECT)` na Cena 1
    - `CTA LAW` na última cena (`cta=True`)
    - `SCENE CONTINUITY (... END CONTINUITY)` nas Cenas 2+.
    """
    visual_limpo, _ = limpar_texto_tela_do_prompt(descricao_visual)
    ator = "man" if sexo.lower().startswith("m") else "woman"
    possessivo = "his" if sexo.lower().startswith("m") else "her"

    if painel == "B" or camera_modo == "maos":
        enq_maos = enquadramento or "top-down close-up of the hands only, locked overhead camera, light countertop"
        ref_prefix = (
            ""
            if indice_cena == 0
            else "Same overhead camera position, height, angle and framing as the approved first hands image. "
        )
        return (
            f"No text in the image. Vertical 9:16 photorealistic frame. {ref_prefix}Camera/framing: {enq_maos}; "
            f"hands-only framing; no face is introduced. {visual_limpo}. "
            f"{LEI_ANATOMIA_MAOS}. {LEI_REALISMO_MAOS}."
        )

    pre = f"{reparo_prepend.strip()} " if reparo_prepend.strip() else ""
    identity_lock = (
        f"IDENTITY LOCK: the speaker is the {ator} in reference photo 1, with {possessivo} own face, skin, age and hair "
        f"from that photo; the same person in every shot."
    )

    if indice_cena == 0:
        outfit_block = (
            "APPROVED OUTFIT: P1 wears exactly the same garments and accessories seen on the person in approved portrait photo 1; "
            "the same garments, colors and accessories in every shot. END OUTFIT."
        )
    else:
        outfit_block = (
            "APPROVED OUTFIT: P1 wears the garments P1 wears in the approved scene-1 frame, not those of reference photo 1; "
            "the same garments, colors and accessories in every shot. Ignore any other clothing mentioned for P1 in this scene. END OUTFIT."
        )

    location_block = (
        f"LOCATION LOCK: {cenario_lock.rstrip('.')}; this same place, background, furniture and light in every shot of this video. "
        if cenario_lock.strip()
        else ""
    )

    estagio_block = ""
    if estagio_corporal:
        chave_est = estagio_corporal.upper().strip()
        sexo_key = "m" if sexo.lower().startswith("m") else "f"
        estagio_block = (
            ESTAGIOS_ANTES_DEPOIS_24.get(chave_est, {}).get(sexo_key, f"BEFORE/AFTER STAGE ({estagio_corporal}).")
            + " "
        )

    roupa_desc = f"{roupa_lock.rstrip('.')}. " if roupa_lock.strip() else ""
    hook_block = (
        f"HOOK OBJECT (copy it from the viral exactly, with the same size, body build, proportions, shape, colours, materials and substances): "
        f"{hook_object.rstrip('. ')}. END HOOK OBJECT. "
        if (indice_cena == 0 and hook_object.strip())
        else ""
    )
    cta_block = f"{CTA_LAW_QUADRO} " if cta else ""
    if indice_cena == 0:
        continuity_block = f"{LEI_CONSISTENCIA_OBJETOS_CENA} "
    else:
        continuity_block = (
            f"SCENE CONTINUITY: the exact same room, background architecture, cabinets, appliances, lighting, camera angle and polished stone countertop surface as the reference image, "
            f"with the exact same person (same face, body build, outfit, hat and glasses). {LEI_CONSISTENCIA_OBJETOS_CENA} END CONTINUITY. "
        )

    return (
        f"No text in the image. {pre}{identity_lock} {outfit_block} {location_block}{estagio_block}"
        f"The same person from the reference photo, {enquadramento}. {roupa_desc}{visual_limpo.rstrip('. ')}. "
        f"{hook_block}{cta_block}{LEI_REALISMO_PESSOA} {continuity_block}"
    ).strip()


def compilar_prompt_animacao_cena(
    *,
    indice_cena: int,
    acao_visual: str,
    fala_ingles: str,
    avatar_id: str = "avatar_default",
    descricao_avatar: str = "",
    sexo: str = "f",
    roupa_lock: str = "",
    regiao_corpo_fala: str = "",
    cta: bool = False,
    enquadramento: str = "medium shot, waist up",
    camera_modo: str = "fixo",
    painel: str | None = None,
    mudo: bool = False,
    palavras_por_segundo: float = 2.6,
) -> str:
    """
    Implementa o `montador c2` exato de vídeo capturado ao vivo no hard test (`generate.video` para Veo 3.1):
    - Frase #1 SEMPRE é a fala literal:
      `The man/woman in the reference image says in English: "<fala_ingles>"`
    - Seguida pela ação física, roupa, `Locked shot, no camera move, no cut...`, `CTA_LAW_VIDEO` (se CTA) e `[VOICE]`.
    """
    acao_limpa, _ = limpar_texto_tela_do_prompt(acao_visual)
    fala_literal = re.sub(r'["“”]', "", (fala_ingles or "").strip())

    if painel == "B" or camera_modo == "maos" or mudo:
        enq_maos = enquadramento or "top-down close-up of the hands only, locked overhead camera, light countertop"
        return (
            f"{CRITICAL_SHOT_RULE_MAOS} Camera/framing: {enq_maos}; hands-only framing; no face is introduced.\n"
            f"{acao_limpa}. The hands perform this one action for real, start to finish, during the 8 seconds. "
            f"SILENT CLIP: nobody speaks, no voice, no narration, no music — only the natural sound of the action. "
            f"{LEI_ANATOMIA_MAOS}. Continuous single shot, no camera cut, sharp ending, no on-screen text."
        )

    ator = "man" if sexo.lower().startswith("m") else "woman"
    bloco_voz = gerar_bloco_voz_fixa(
        avatar_id=avatar_id,
        descricao_avatar=descricao_avatar,
        sexo=sexo,
        palavras_por_segundo=palavras_por_segundo,
    )
    roupa_str = f" {roupa_lock.rstrip('.')}." if roupa_lock.strip() else ""
    cta_str = f" {CTA_LAW_VIDEO}" if cta else ""
    regiao_str = (
        f" The body area shown and touched in this shot is the one named in the speech: {regiao_corpo_fala.strip()}."
        if regiao_corpo_fala.strip()
        else ""
    )

    return (
        f'The {ator} in the reference image says in English: "{fala_literal}" '
        f"{acao_limpa.rstrip('.')}.{roupa_str} {CRITICAL_SHOT_RULE_PESSOA}{cta_str} {bloco_voz}{regiao_str}"
    ).strip()


def enriquecer_prompt_imagem_se_necessario(
    prompt_imagem: str,
    indice_cena: int = 0,
    sexo: str = "f",
    cta: bool = False,
    painel: str | None = None,
    reparo_prepend: str = "",
) -> str:
    """
    Injeta automaticamente `No text in the image.`, `IDENTITY LOCK`, `APPROVED OUTFIT`,
    `SCENE CONTINUITY` (Cena 2+) e `CTA LAW` (se `cta=True`) em qualquer prompt de quadro.
    """
    p, _ = limpar_texto_tela_do_prompt(prompt_imagem or "")
    if painel == "B" or "hands-only" in p.lower():
        if "no text in the image" not in p.lower():
            p = f"No text in the image. {p}"
        return p

    ator = "man" if sexo.lower().startswith("m") else "woman"
    poss = "his" if sexo.lower().startswith("m") else "her"
    partes: list[str] = ["No text in the image."]
    if reparo_prepend.strip():
        partes.append(reparo_prepend.strip())
    if "IDENTITY LOCK:" not in p:
        partes.append(
            f"IDENTITY LOCK: the speaker is the {ator} in reference photo 1, with {poss} own face, skin, age and hair from that photo; the same person in every shot."
        )
    if "APPROVED OUTFIT:" not in p:
        if indice_cena == 0:
            partes.append(
                "APPROVED OUTFIT: P1 wears exactly the same garments and accessories seen on the person in approved portrait photo 1; the same garments, colors and accessories in every shot. END OUTFIT."
            )
        else:
            partes.append(
                "APPROVED OUTFIT: P1 wears the garments P1 wears in the approved scene-1 frame, not those of reference photo 1; the same garments, colors and accessories in every shot. Ignore any other clothing mentioned for P1 in this scene. END OUTFIT."
            )

    p_sem_no_text = re.sub(r"^No text in the image\.\s*", "", p, flags=re.I)
    partes.append(p_sem_no_text.rstrip(". ") + ".")

    if cta and "CTA LAW:" not in p:
        partes.append(CTA_LAW_QUADRO)
    if indice_cena > 0 and "SCENE CONTINUITY:" not in p:
        partes.append(
            "SCENE CONTINUITY: the same take as the scene reference image: the same background, furniture, props, light, camera and framing and people on the same spots; only pose, hands and expression change. END CONTINUITY."
        )
    if "ONE single photograph filling the whole frame" not in p:
        partes.append(LEI_REALISMO_PESSOA)
    return " ".join(partes)


def enriquecer_prompt_video_se_necessario(
    prompt_video: str,
    fala: str = "",
    avatar_id: str = "avatar_default",
    descricao_avatar: str = "",
    sexo: str = "f",
    indice_cena: int = 0,
    cta: bool = False,
    painel: str | None = None,
    mudo: bool = False,
) -> str:
    """
    Garante a Regra da Frase #1 do `montador c2` (`The man/woman in the reference image says in English: "..."`)
    + `Locked shot, no camera move, no cut...` + `[VOICE]` com Hz fixo.
    """
    p, _ = limpar_texto_tela_do_prompt(prompt_video or "")
    if painel == "B" or mudo or "silent clip" in p.lower():
        if "CRITICAL SHOT RULE" not in p:
            p = (
                f"{CRITICAL_SHOT_RULE_MAOS}\n{p.rstrip('.')}. "
                f"SILENT CLIP: nobody speaks, no voice, no narration, no music — only the natural sound of the action. "
                f"{LEI_ANATOMIA_MAOS}. Continuous single shot, no camera cut, sharp ending, no on-screen text."
            )
        return p

    ator = "man" if sexo.lower().startswith("m") else "woman"
    fala_limpa = re.sub(r'["“”]', "", (fala or "").strip())
    prefixo_fala = f'The {ator} in the reference image says in English: "{fala_limpa}"' if fala_limpa else ""

    # Se o prompt ainda não começa com a fala na Frase #1, coloca na frente (padrão montador c2)
    if prefixo_fala and not p.lower().startswith(f"the {ator} in the reference image says in english:"):
        p = f"{prefixo_fala} {p.lstrip()}"

    if "Locked shot, no camera move, no cut" not in p:
        p = f"{p.rstrip('. ')}. {CRITICAL_SHOT_RULE_PESSOA}"
    if cta and CTA_LAW_VIDEO not in p:
        p = f"{p.rstrip('. ')}. {CTA_LAW_VIDEO}"
    if "[VOICE]" not in p:
        p = f"{p.rstrip('. ')}. {gerar_bloco_voz_fixa(avatar_id=avatar_id, descricao_avatar=descricao_avatar, sexo=sexo)}"
    return p


def construir_reparo_cirurgico_juiz_visao(veredito_juiz: dict[str, Any], prompt_original: str) -> str:
    """
    Aplica a correção cirúrgica exata interceptada no hard test (`idx 347` / `idx 352`):
    Quando `/ia/kie/visao` retorna `same_accessories: false` ou `same_identity: false`,
    injeta a instrução corretiva logo após `No text in the image.` sem descartar as outras cenas!
    """
    prepend_list: list[str] = []
    for ch in veredito_juiz.get("changes", []) or []:
        kind = str(ch.get("kind") or "")
        if kind == "accessories_changed":
            prepend_list.append(PREPEND_REPARO_ACESSORIOS)
        elif kind == "glasses_added":
            prepend_list.append(PREPEND_REPARO_OCULOS_REM)
        elif kind == "glasses_removed":
            prepend_list.append(PREPEND_REPARO_OCULOS_ADD)
        elif kind == "face_changed":
            prepend_list.append(PREPEND_REPARO_ROSTO)
        elif kind in ("props_changed", "container_changed", "duplicate_container"):
            prepend_list.append(PREPEND_REPARO_OBJETOS)

    if not prepend_list and not veredito_juiz.get("same_accessories", True):
        prepend_list.append(PREPEND_REPARO_ACESSORIOS)
    if not prepend_list and not veredito_juiz.get("same_identity", True):
        prepend_list.append(PREPEND_REPARO_ROSTO)
    if not veredito_juiz.get("same_props", True) and PREPEND_REPARO_OBJETOS not in prepend_list:
        prepend_list.append(PREPEND_REPARO_OBJETOS)

    if not prepend_list:
        return prompt_original

    pre_str = " ".join(dict.fromkeys(prepend_list))
    if prompt_original.startswith("No text in the image."):
        return prompt_original.replace("No text in the image.", f"No text in the image. {pre_str}", 1)
    return f"No text in the image. {pre_str} {prompt_original}"


def enriquecer_item_video_zerum(pv: dict[str, Any]) -> dict[str, Any]:
    """
    Enriquece in-place (e retorna) um item de vídeo do lote (`video_id`, `avatar`, `takes`)
    com as leis do `montador c2` (`quadroPrompt18`, `quadroRefs18`, Frase #1 de fala no Veo 3.1, `CTA LAW` e `[VOICE] Hz`).
    """
    avatar_id = str(pv.get("video_id") or pv.get("avatar") or "avatar_default")
    desc_avatar = str(pv.get("avatar") or "")
    sexo = "m" if re.search(r"\b(man|male|homem|masculino|dr\.|mr\.)\b", desc_avatar, re.I) else "f"
    takes = pv.get("takes", [])
    total_takes = len(takes)
    for idx, t in enumerate(takes):
        painel = t.get("painel")
        mudo = bool(t.get("mudo", False))
        is_cta = (idx == total_takes - 1) and total_takes > 1 and not mudo
        t["quadroRefs18"] = compilar_quadro_refs_18(
            indice_cena=idx,
            avatar_media_id=str(pv.get("avatar_media_id") or f"ref_{avatar_id}"),
            cena1_aprovada_media_id=str(pv.get("cena1_media_id") or f"scene1_{avatar_id}") if idx > 0 else None,
        )
        t["prompt_imagem"] = enriquecer_prompt_imagem_se_necessario(
            t.get("prompt_imagem", ""),
            indice_cena=idx,
            sexo=sexo,
            cta=is_cta,
            painel=painel,
        )
        t["prompt_video"] = enriquecer_prompt_video_se_necessario(
            t.get("prompt_video", ""),
            fala=t.get("fala", ""),
            avatar_id=avatar_id,
            descricao_avatar=desc_avatar,
            sexo=sexo,
            indice_cena=idx,
            cta=is_cta,
            painel=painel,
            mudo=mudo,
        )
    return pv
