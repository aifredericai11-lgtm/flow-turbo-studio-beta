"""
Forja — Motor de Inteligência de Virais & Transplante de Formato Visual (forja/motor_virais.py).

Funcionalidades:
1. ASSISTIR VIRAL NOVO (100% Local / Zero Custo de API Externa):
   - Detecta cortes reais de cena via FFmpeg (scene cut detection) + extrai frames do Hook (0.5s, 1.5s, 2.5s) e de cada take.
   - Transcreve palavra por palavra via Whisper GPU (CUDA float16) medindo ritmo (palavras/s) no Hook, Body e CTA.
   - Analisa os frames com OpenCV (enquadramento, escala de rosto, temperatura de cor e brilho) e extrai o DNA do viral
     separado em Camada Verbal (Esqueleto de Copy + Variáveis) e Camada Visual (Cena, Gesto do Hook, Objetos, Arquétipo).
2. MEMÓRIA DUPLA SINCRONIZADA (JSON + Cofre do Obsidian):
   - Salva em `memoria_virais.json` na raiz da Forja e gera/atualiza automaticamente uma nota Markdown editável
     em `G:\\Meu Drive\\obsidian\\Cérebro\\_Memória Claude\\Catálogo de Virais\\<viral_id>.md`.
   - Sincronização bidirecional: se o usuário editar a Copy, o Objeto ou a Ação lá no Obsidian, o motor lê a alteração da nota!
3. TRANSPLANTE DE FORMATO VISUAL (1 Vídeo -> Outro Formato Visual com Alto Realismo 24mm):
   - Permite pegar qualquer viral assistido (ex.: Médico em Consultório aplicando pasta na coxa) e transplantar a mesma
     copy/produto para outro formato visual da biblioteca (ex.: `ugc_cozinha_selfie_24mm` — Pessoa Comum na Cozinha de Casa
     em Selfie 24mm, `ugc_banheiro_espelho_24mm`, `ugc_quarto_noturno_tv`, `ugc_sala_sofa_24mm`, `especialista_mesa_pc_24mm`).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from forja.estrutura import ROOT_DIR
from forja.ler_viral import analisar_viral, extrair_frame, obter_duracao_video
from forja.roteiro_takes import gerar_roteiro_takes

MEMORIA_VIRAIS_PATH = ROOT_DIR / "memoria_virais.json"
OBSIDIAN_CATALOGO_DIR = Path(r"G:\Meu Drive\obsidian\Cérebro\_Memória Claude\Catálogo de Virais")


# ==============================================================================
# CATÁLOGO DE FORMATOS VISUAIS DE DESTINO (PARA TRANSPLANTE DE FORMATO 2.0)
# Todos construídos sobre o Master Template de Alto Realismo Cru de Celular (24mm, Zero Bokeh)
# ==============================================================================
FORMATOS_VISUAIS_CATALOGO: dict[str, dict[str, Any]] = {
    "ugc_cozinha_selfie_24mm": {
        "id": "ugc_cozinha_selfie_24mm",
        "titulo": "Pessoa Comum na Cozinha de Casa (Selfie 24mm Apoiada no Balcão)",
        "arquetipo_grupo": "pessoa_comum_casa",
        "cenario_base_en": (
            "a real, lived-in middle-class American apartment kitchen with a granite or laminate countertop, "
            "wood cabinets, and a sink in the background"
        ),
        "provas_de_vida_en": (
            "a stainless-steel fridge with colorful magnets and paper notes stuck to the side, "
            "a blue Dawn dish soap bottle and coffee maker by the sink, a crinkly snack bag on top of the upper wood cabinet, "
            "and an open plain brown cardboard shipping box on the counter edge"
        ),
        "luz_fisica_en": (
            "Harsh, authentic indoor lighting from a single recessed circular ceiling LED pot-light visible as a bright "
            "blown-out circle on the white ceiling right next to a metal AC air vent grille, plus a warm under-cabinet "
            "kitchen strip light casting realistic downward shadows and auto-white-balance indoor color cast"
        ),
        "cena_fixa_template_en": (
            "On the kitchen counter in the foreground sits {OBJETO_PRINCIPAL_EN}, casting a real specular reflection "
            "and contact shadow onto the countertop surface."
        ),
        "acoes_template_en": {
            "hook_frame1": (
                "The subject leans slightly forward over the kitchen counter, holding {OBJETO_PRINCIPAL_EN} pushed "
                "slightly forward toward the 24mm wide-angle phone lens at collarbone/chest level (leaving the entire "
                "face and mouth 100% unobstructed) so the item looks large, clear, and dominant in the foreground while "
                "speaking directly to the phone camera."
            ),
            "hook_video": (
                "Stationary front-facing iPhone propped on the kitchen counter. The subject maintains natural eye contact "
                "with the phone lens while holding {OBJETO_PRINCIPAL_EN} at chest level (never blocking the mouth) and "
                "giving it a subtle tap or tilt toward the lens."
            ),
            "body_frame1": (
                "The subject stands naturally by the kitchen counter with {OBJETO_PRINCIPAL_EN} resting clearly in the "
                "foreground, gesturing with one open hand at chest height while explaining directly to the phone camera."
            ),
            "body_video": (
                "Stationary front-facing iPhone propped on the kitchen counter. The subject gestures naturally with one "
                "hand at chest level while explaining conversationally to the phone camera."
            ),
            "cta_frame1": (
                "The subject leans slightly toward the phone on the kitchen counter next to {OBJETO_PRINCIPAL_EN}, "
                "pointing one index finger straight down toward the comment section at chest level while looking into the lens."
            ),
            "cta_video": (
                "Stationary front-facing iPhone propped on the kitchen counter. The subject points one index finger "
                "straight down toward the comments with an encouraging nod while speaking directly into the lens."
            ),
        },
        "avatares": [
            {
                "id_avatar": "ugc_kitchen_01_man_54_grey_tee",
                "genero": "male",
                "voz_en": "Natural mid-50s American male voice, warm, conversational, and slightly gravelly, brisk casual pace",
                "personagem_en": (
                    "An ordinary, non-model 54-year-old American man with slightly messy short salt-and-pepper hair, "
                    "natural horizontal forehead creases mid-sentence, visible skin pores, slight oily T-zone shine"
                ),
                "roupa_en": "a casual lived-in plain heather-grey crew-neck cotton t-shirt with a slightly stretched collar",
                "cenario_en": "a real, lived-in middle-class American apartment kitchen with granite countertop and wood cabinets",
            },
            {
                "id_avatar": "ugc_kitchen_02_woman_48_navy_hoodie",
                "genero": "female",
                "voz_en": "Natural late-40s American female voice, clear, friendly, and conversational, brisk casual pace",
                "personagem_en": (
                    "An ordinary, non-model 48-year-old American woman with shoulder-length brown hair tied back in a loose "
                    "clip with natural flyaways, subtle crow's feet, visible skin pores, zero heavy makeup"
                ),
                "roupa_en": "a casual lived-in faded navy-blue zip-up cotton hoodie over a white scoop-neck tee",
                "cenario_en": "a real, lived-in suburban American home kitchen with white tile backsplash and laminate counter",
            },
            {
                "id_avatar": "ugc_kitchen_03_man_61_flannel",
                "genero": "male",
                "voz_en": "Natural early-60s American male voice, grounded, direct, and authentic, brisk conversational pace",
                "personagem_en": (
                    "An ordinary, non-model 61-year-old American man with thinning silver hair, short trimmed beard, "
                    "natural forehead lines, visible skin pores, and reading glasses resting on his shirt collar"
                ),
                "roupa_en": "a casual lived-in plaid cotton flannel shirt with sleeves rolled up to the elbows",
                "cenario_en": "a real, lived-in American house kitchen with oak cabinets and a stainless-steel refrigerator behind",
            },
            {
                "id_avatar": "ugc_kitchen_04_black_man_49_olive_tee",
                "genero": "male",
                "voz_en": "Natural late-40s American male voice, deep, warm, and conversational, brisk casual pace",
                "personagem_en": (
                    "An ordinary, non-model 49-year-old Black American man with a short fade haircut, closely trimmed goatee, "
                    "natural forehead creases mid-word, visible skin pores and authentic indoor skin texture"
                ),
                "roupa_en": "a casual lived-in olive-green crew-neck cotton t-shirt with soft fabric wrinkles",
                "cenario_en": "a real, lived-in modern American apartment kitchen with dark stone counters and dish rack by the sink",
            },
            {
                "id_avatar": "ugc_kitchen_05_woman_56_cardigan",
                "genero": "female",
                "voz_en": "Natural mid-50s American female voice, warm, earnest, and conversational, brisk casual pace",
                "personagem_en": (
                    "An ordinary, non-model 56-year-old American woman with short blonde-streaked hair with flyaways, "
                    "natural expression lines around the eyes and forehead, visible skin pores"
                ),
                "roupa_en": "a casual lived-in beige knit cardigan over a plain burgundy cotton t-shirt",
                "cenario_en": "a real, lived-in middle-class American kitchen with a coffee maker and paper towel holder on the counter",
            },
        ],
    },
    "ugc_banheiro_espelho_24mm": {
        "id": "ugc_banheiro_espelho_24mm",
        "titulo": "Pessoa Comum no Banheiro de Casa (Bancada da Pia em Lente 24mm)",
        "arquetipo_grupo": "pessoa_comum_casa",
        "cenario_base_en": (
            "a real, lived-in middle-class American home bathroom with a vanity counter, sink faucet, and towel rack behind"
        ),
        "provas_de_vida_en": (
            "a toothbrush holder with two toothbrushes and a half-squeezed toothpaste tube on the sink edge, "
            "a pump bottle of liquid hand soap, a slightly rumpled white hand towel hanging on the wall ring, "
            "and a hairbrush resting on the counter"
        ),
        "luz_fisica_en": (
            "Harsh, authentic indoor lighting from a bright overhead bathroom vanity LED fixture visible near the top edge "
            "next to a ceiling exhaust vent grille, casting realistic downward shadows on the face and vanity counter"
        ),
        "cena_fixa_template_en": (
            "On the bathroom vanity counter in the foreground sits {OBJETO_PRINCIPAL_EN}, casting a real reflection "
            "onto the porcelain sink edge."
        ),
        "acoes_template_en": {
            "hook_frame1": (
                "The subject stands in front of the bathroom vanity counter, holding {OBJETO_PRINCIPAL_EN} pushed "
                "slightly forward toward the 24mm wide-angle phone lens at collarbone/chest level (leaving the face and "
                "mouth 100% unobstructed) while speaking directly to the phone camera."
            ),
            "hook_video": (
                "Stationary front-facing iPhone propped on the bathroom shelf. The subject holds {OBJETO_PRINCIPAL_EN} "
                "at chest level (never covering the mouth) and tilts it slightly toward the lens while speaking naturally."
            ),
            "body_frame1": (
                "The subject stands by the bathroom vanity with {OBJETO_PRINCIPAL_EN} visible in the foreground, "
                "gesturing naturally with one hand at chest height while explaining directly to the phone."
            ),
            "body_video": (
                "Stationary front-facing iPhone propped on the bathroom shelf. The subject gestures calmly with one hand "
                "while speaking directly into the camera lens."
            ),
            "cta_frame1": (
                "The subject stands by the bathroom vanity next to {OBJETO_PRINCIPAL_EN}, pointing one index finger "
                "straight down at chest level toward the comment section while looking into the lens."
            ),
            "cta_video": (
                "Stationary front-facing iPhone propped on the bathroom shelf. The subject points one index finger "
                "straight down with a natural nod while looking into the lens."
            ),
        },
        "avatares": [
            {
                "id_avatar": "ugc_bath_01_man_52_white_tee",
                "genero": "male",
                "voz_en": "Natural early-50s American male voice, direct and conversational, brisk casual pace",
                "personagem_en": (
                    "An ordinary, non-model 52-year-old American man with short tousled brown hair with grey temples, "
                    "natural horizontal forehead creases, visible skin pores, slight morning stubble"
                ),
                "roupa_en": "a casual lived-in plain white crew-neck cotton undershirt with a relaxed collar",
                "cenario_en": "a real, lived-in American home bathroom with a white vanity counter and shower curtain visible behind",
            },
            {
                "id_avatar": "ugc_bath_02_woman_46_grey_sweatshirt",
                "genero": "female",
                "voz_en": "Natural mid-40s American female voice, clear and authentic, brisk conversational pace",
                "personagem_en": (
                    "An ordinary, non-model 46-year-old American woman with messy bun hair and natural flyaways, "
                    "visible skin pores, authentic bare-skin indoor complexion"
                ),
                "roupa_en": "a casual lived-in light-grey crewneck cotton sweatshirt",
                "cenario_en": "a real, lived-in American apartment bathroom with beige wall tiles and a towel hook on the door",
            },
        ],
    },
    "ugc_quarto_noturno_tv": {
        "id": "ugc_quarto_noturno_tv",
        "titulo": "Pessoa Comum no Quarto à Noite (Rotina Antes de Dormir / TV Ligada ao Fundo)",
        "arquetipo_grupo": "pessoa_comum_casa",
        "cenario_base_en": (
            "a real, lived-in middle-class American bedroom in the evening with an unmade bed, wooden dresser, and nightstand"
        ),
        "provas_de_vida_en": (
            "a wall-mounted TV displaying a purple Roku home screen in the background, a white phone charger cable hanging "
            "off the nightstand edge, a messy stack of mail papers and a dark gym backpack on the wooden dresser, "
            "and a half-empty water glass on the nightstand"
        ),
        "luz_fisica_en": (
            "Harsh, authentic indoor evening lighting from a single recessed circular ceiling LED pot-light visible on the "
            "ceiling next to a metal AC air vent grille plus a warm bedside lamp glow, casting realistic indoor shadows"
        ),
        "cena_fixa_template_en": (
            "In the foreground at chest level is {OBJETO_PRINCIPAL_EN}, catching a real specular highlight from the overhead light."
        ),
        "acoes_template_en": {
            "hook_frame1": (
                "The subject sits/stands in the bedroom holding {OBJETO_PRINCIPAL_EN} pushed slightly forward toward "
                "the 24mm wide-angle phone lens at collarbone/chest level (leaving the entire face and mouth 100% unobstructed) "
                "while speaking directly to the camera."
            ),
            "hook_video": (
                "Stationary front-facing iPhone propped on the dresser. The subject holds {OBJETO_PRINCIPAL_EN} at chest "
                "level (never covering the mouth) and makes a subtle gesture toward it while speaking naturally."
            ),
            "body_frame1": (
                "The subject is in the same bedroom spot holding {OBJETO_PRINCIPAL_EN} low at chest level and gesturing "
                "with one open hand while explaining directly to the phone camera."
            ),
            "body_video": (
                "Stationary front-facing iPhone propped on the dresser. The subject gestures naturally with one hand "
                "while speaking conversationally to the camera."
            ),
            "cta_frame1": (
                "The subject leans slightly toward the phone in the bedroom, pointing one index finger straight down "
                "at chest level toward the comments while looking directly into the lens."
            ),
            "cta_video": (
                "Stationary front-facing iPhone propped on the dresser. The subject points straight down toward the "
                "comment section with an encouraging nod while speaking into the lens."
            ),
        },
        "avatares": [
            {
                "id_avatar": "ugc_bed_01_man_55_charcoal_tee",
                "genero": "male",
                "voz_en": "Natural mid-50s American male voice, calm, direct, and authentic, brisk conversational pace",
                "personagem_en": (
                    "An ordinary, non-model 55-year-old American man with short silver-streaked hair, natural horizontal "
                    "forehead creases, visible skin pores, slight oily T-zone shine under indoor light"
                ),
                "roupa_en": "a casual lived-in charcoal-grey cotton t-shirt with a slightly worn neckline",
                "cenario_en": "a real, lived-in American bedroom with a wooden headboard, nightstand, and dresser behind",
            },
        ],
    },
    "especialista_mesa_pc_24mm": {
        "id": "especialista_mesa_pc_24mm",
        "titulo": "Especialista / Criador no Home Office (Mesa com Monitor e Persiana)",
        "arquetipo_grupo": "especialista_home_office",
        "cenario_base_en": (
            "a real, lived-in American home office desk with a computer monitor, bookshelf, and window blinds behind"
        ),
        "provas_de_vida_en": (
            "a black Logitech webcam clipped on top of a slightly crooked Acer monitor in the background, "
            "a dusty mechanical keyboard and coffee mug on the desk mat, a stack of sticky notes, "
            "and horizontal white vinyl window blinds behind"
        ),
        "luz_fisica_en": (
            "Harsh, authentic indoor lighting from a single recessed circular ceiling LED pot-light visible on the ceiling "
            "next to a metal AC air vent grille, combined with cool blue-white monitor screen glow on the desk surface"
        ),
        "cena_fixa_template_en": (
            "On the desk in the foreground sits {OBJETO_PRINCIPAL_EN}, casting a real contact shadow onto the desk surface."
        ),
        "acoes_template_en": {
            "hook_frame1": (
                "The subject leans forward at the home office desk, holding {OBJETO_PRINCIPAL_EN} pushed slightly forward "
                "toward the 24mm wide-angle phone lens at collarbone/chest level (leaving the face and mouth 100% unobstructed) "
                "while speaking directly to the camera."
            ),
            "hook_video": (
                "Stationary front-facing iPhone propped on the desk. The subject holds {OBJETO_PRINCIPAL_EN} at chest level "
                "(never blocking the mouth) and taps it once while speaking directly to the lens."
            ),
            "body_frame1": (
                "The subject sits at the home office desk with {OBJETO_PRINCIPAL_EN} visible in the foreground, gesturing "
                "naturally with one open hand while explaining directly to the phone camera."
            ),
            "body_video": (
                "Stationary front-facing iPhone propped on the desk. The subject gestures naturally with one hand while "
                "speaking conversationally to the camera."
            ),
            "cta_frame1": (
                "The subject sits at the home office desk next to {OBJETO_PRINCIPAL_EN}, pointing one index finger "
                "straight down toward the comment section while looking directly into the lens."
            ),
            "cta_video": (
                "Stationary front-facing iPhone propped on the desk. The subject points straight down toward the comments "
                "with a natural encouraging nod."
            ),
        },
        "avatares": [
            {
                "id_avatar": "ugc_desk_01_man_47_polo",
                "genero": "male",
                "voz_en": "Natural late-40s American male voice, clear, authoritative yet casual, brisk pace",
                "personagem_en": (
                    "An ordinary, non-model 47-year-old American man with short dark-brown hair with grey at the temples, "
                    "natural forehead creases mid-sentence, visible skin pores, rectangular glasses"
                ),
                "roupa_en": "a casual lived-in navy-blue cotton polo shirt with collar slightly unbuttoned",
                "cenario_en": "a real, lived-in American home office with a wooden desk, monitor, and bookshelf behind",
            },
        ],
    },
    "cozinha_clara_enfermeira_24mm": {
        "id": "cozinha_clara_enfermeira_24mm",
        "titulo": "Enfermeira(o) de Scrubs na Cozinha Clara de Casa (Top #1 Conversão EUA — Aula 21/10)",
        "arquetipo_grupo": "enfermeira_cozinha_casa",
        "cenario_base_en": (
            "a bright, real lived-in middle-class American home kitchen with white wood cabinets, light granite countertop, "
            "and a stainless-steel refrigerator in the background"
        ),
        "provas_de_vida_en": (
            "a stainless-steel fridge with family magnets and paper notes stuck to the side, "
            "a blue Dawn dish soap bottle and coffee maker by the sink, a crinkly snack bag on top of the upper white cabinet, "
            "and a ceramic mug on the counter"
        ),
        "luz_fisica_en": (
            "Harsh, authentic indoor lighting from a single recessed circular ceiling LED pot-light visible as a bright "
            "blown-out circle on the white ceiling right next to a metal AC air vent grille, plus bright natural kitchen "
            "daylight casting realistic downward shadows"
        ),
        "cena_fixa_template_en": (
            "On the bright kitchen counter in the foreground sits {OBJETO_PRINCIPAL_EN}, casting a real specular reflection "
            "and contact shadow onto the granite countertop surface."
        ),
        "acoes_template_en": {
            "hook_frame1": (
                "The nurse leans slightly forward over the home kitchen counter, holding {OBJETO_PRINCIPAL_EN} pushed "
                "slightly forward toward the 24mm wide-angle phone lens at collarbone/chest level (leaving the entire "
                "face and mouth 100% unobstructed) while speaking directly to the phone camera."
            ),
            "hook_video": (
                "Stationary front-facing iPhone propped on the kitchen counter. The nurse maintains natural eye contact "
                "with the phone lens while holding {OBJETO_PRINCIPAL_EN} at chest level (never blocking the mouth) and "
                "demonstrating it naturally."
            ),
            "body_frame1": (
                "The nurse stands by the home kitchen counter with {OBJETO_PRINCIPAL_EN} clearly visible in the foreground, "
                "gesturing with one open hand at chest height while explaining directly to the phone camera."
            ),
            "body_video": (
                "Stationary front-facing iPhone propped on the kitchen counter. The nurse gestures naturally with one "
                "hand at chest level while explaining conversationally to the phone camera."
            ),
            "cta_frame1": (
                "The nurse stands at the kitchen counter next to {OBJETO_PRINCIPAL_EN}, pointing one index finger straight "
                "down toward the comment section at chest level while looking directly into the lens."
            ),
            "cta_video": (
                "Stationary front-facing iPhone propped on the kitchen counter. The nurse points one index finger straight "
                "down toward the comments with a warm, encouraging nod while speaking into the lens."
            ),
        },
        "avatares": [
            {
                "id_avatar": "nurse_kitchen_01_female_46_navy_scrubs",
                "genero": "female",
                "voz_en": "Warm empathetic mid-40s American female nurse voice, reassuring and conversational, brisk pace",
                "personagem_en": (
                    "An ordinary, non-model 46-year-old Caucasian American female nurse practitioner with shoulder-length "
                    "brown hair tied back with natural loose flyaways, visible skin pores, slight natural T-zone shine"
                ),
                "roupa_en": "lived-in navy-blue V-neck nursing scrubs with natural cotton creases and a stethoscope draped around her neck",
                "cenario_en": "a bright, real lived-in middle-class American home kitchen with white cabinets and granite countertop",
            },
            {
                "id_avatar": "nurse_kitchen_02_black_female_49_burgundy_scrubs",
                "genero": "female",
                "voz_en": "Confident warm late-40s Black American female nurse voice, clear and trustworthy, brisk pace",
                "personagem_en": (
                    "An ordinary, non-model 49-year-old Black American female senior nurse with natural curls in a practical "
                    "bun, subtle forehead lines, visible skin pores, authentic bare-skin indoor complexion"
                ),
                "roupa_en": "lived-in burgundy wine-red nursing scrubs with soft fabric folds and a black stethoscope around her neck",
                "cenario_en": "a bright, real lived-in American home kitchen with white subway tile backsplash and stainless fridge",
            },
            {
                "id_avatar": "nurse_kitchen_03_latina_female_42_teal_scrubs",
                "genero": "female",
                "voz_en": "Friendly energetic early-40s American female nurse voice, clear and direct, brisk pace",
                "personagem_en": (
                    "An ordinary, non-model 42-year-old Hispanic American female nurse with dark wavy ponytail and natural "
                    "loose strands, visible skin pores and natural indoor lighting"
                ),
                "roupa_en": "lived-in emerald-teal fitted nursing scrubs with a silver stethoscope around her neck",
                "cenario_en": "a bright, real lived-in American apartment kitchen with light oak cabinets and granite counter",
            },
        ],
    },
    "cozinha_clara_homem_forte_50_24mm": {
        "id": "cozinha_clara_homem_forte_50_24mm",
        "titulo": "Homem Forte/Maduro 50–60 Anos na Cozinha Clara (Ímã de Retenção Mulheres 45+ — Aula 21/10)",
        "arquetipo_grupo": "homem_forte_cozinha",
        "cenario_base_en": (
            "a bright, real lived-in American kitchen with marble or granite countertop, wood cabinets, and stainless steel appliances"
        ),
        "provas_de_vida_en": (
            "a stainless-steel refrigerator with magnets and paper notes stuck to the side, a blue dish soap bottle by the sink, "
            "a coffee maker on the counter, and a folded kitchen towel"
        ),
        "luz_fisica_en": (
            "Harsh, authentic indoor overhead lighting from a single recessed circular ceiling LED pot-light visible on the "
            "white ceiling right next to a metal AC air vent grille, casting realistic downward shadows"
        ),
        "cena_fixa_template_en": (
            "On the kitchen counter in the foreground sits {OBJETO_PRINCIPAL_EN}, casting a real specular reflection and contact shadow."
        ),
        "acoes_template_en": {
            "hook_frame1": (
                "The fit older man leans slightly forward over the kitchen counter, holding {OBJETO_PRINCIPAL_EN} pushed "
                "slightly forward toward the 24mm wide-angle phone lens at chest level (leaving his face and mouth 100% unobstructed) "
                "while speaking with confident authority to the camera."
            ),
            "hook_video": (
                "Stationary front-facing iPhone propped on the kitchen counter. The man maintains strong direct eye contact "
                "with the lens while holding {OBJETO_PRINCIPAL_EN} at chest level."
            ),
            "body_frame1": (
                "The man stands behind the kitchen counter with {OBJETO_PRINCIPAL_EN} in the foreground, gesturing naturally "
                "with one hand at chest height while explaining directly to the phone."
            ),
            "body_video": (
                "Stationary front-facing iPhone propped on the kitchen counter. The man gestures naturally with one hand "
                "while speaking directly to the camera."
            ),
            "cta_frame1": (
                "The man stands at the kitchen counter next to {OBJETO_PRINCIPAL_EN}, pointing one index finger straight down "
                "toward the comment section while looking directly into the lens."
            ),
            "cta_video": (
                "Stationary front-facing iPhone propped on the kitchen counter. The man points one index finger straight down "
                "toward the comments with a confident nod."
            ),
        },
        "avatares": [
            {
                "id_avatar": "fit_man_kitchen_01_black_52_fitted_tee",
                "genero": "male",
                "voz_en": "Deep confident early-50s Black American male voice, warm and authoritative, brisk conversational pace",
                "personagem_en": (
                    "An ordinary, non-model athletic 52-year-old Black American man with a salt-and-pepper goatee, short fade haircut, "
                    "muscular build, natural forehead creases, visible skin pores and slight T-zone shine"
                ),
                "roupa_en": "a casual lived-in fitted black crew-neck cotton t-shirt",
                "cenario_en": "a real, lived-in American kitchen with wood cabinets, stainless refrigerator, and granite counter",
            },
            {
                "id_avatar": "fit_man_kitchen_02_caucasian_55_henley",
                "genero": "male",
                "voz_en": "Deep grounded mid-50s American male voice, direct and charismatic, brisk conversational pace",
                "personagem_en": (
                    "An ordinary, non-model fit 55-year-old Caucasian American man with thick silver-streaked hair and neatly trimmed "
                    "silver beard, strong jawline, natural crow's feet and visible skin pores"
                ),
                "roupa_en": "a casual lived-in fitted charcoal-grey short-sleeve cotton Henley shirt",
                "cenario_en": "a bright, real lived-in American home kitchen with white cabinets and marble island counter",
            },
        ],
    },
    "medico_consultorio_original": {
        "id": "medico_consultorio_original",
        "titulo": "Profissional de Saúde em Consultório Americano (Formato Clínico Realista 24mm)",
        "arquetipo_grupo": "medico_consultorio",
        "cenario_base_en": (
            "a real, lived-in American medical exam room with a beige exam table covered in white crinkly paper roll, "
            "wood cabinets, and a stainless steel sink in the background"
        ),
        "provas_de_vida_en": (
            "a wall-mounted blood pressure cuff and otoscope cord on the wall, a box of blue nitrile gloves on the counter, "
            "a stainless steel medical tray in the foreground, and paper charts on the cabinet"
        ),
        "luz_fisica_en": (
            "Harsh, authentic indoor overhead lighting from a recessed ceiling LED fixture visible on the white ceiling "
            "right next to a metal AC air vent grille, casting realistic downward shadows"
        ),
        "cena_fixa_template_en": (
            "On the stainless steel medical tray in the foreground sits {OBJETO_PRINCIPAL_EN}, casting a real reflection "
            "onto the metal tray."
        ),
        "acoes_template_en": {},
        "avatares": [],
    },
}


# ==============================================================================
# 1. DETECÇÃO AUTOMÁTICA DE CORTES DE CENA & MÉTRICAS VISUAIS (FFMPEG + OPENCV)
# ==============================================================================
def detectar_cortes_cena_ffmpeg(video_path: Path, threshold: float = 0.28) -> list[float]:
    """
    Detecta timestamps exatos de cortes de cena reais no vídeo viral usando o filtro `select='gt(scene,T)'` do FFmpeg.
    Retorna lista ordenada de segundos onde ocorrem mudanças de cena/take.
    """
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-i",
        str(video_path),
        "-vf",
        f"select='gt(scene,{threshold})',showinfo",
        "-f",
        "null",
        "-",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    stderr = proc.stderr or ""
    cortes: list[float] = []
    for m in re.finditer(r"pts_time:([0-9]+(?:\.[0-9]+)?)", stderr):
        t = round(float(m.group(1)), 2)
        if not cortes or (t - cortes[-1]) >= 1.2:
            cortes.append(t)
    return cortes


def analisar_metricas_visuais_opencv(frames_paths: list[Path]) -> dict[str, Any]:
    """
    Analisa os frames extraídos do viral via OpenCV (100% local, zero custo de API):
    - Detecta presença e escala do rosto (Close-up / Selfie vs Plano Médio / Corpo Inteiro);
    - Mede brilho médio, contraste e temperatura de cor (Quente Residencial vs Fria Consultório).
    """
    try:
        import cv2
        import numpy as np
    except Exception:
        return {"metodo": "fallback_sem_cv2"}

    face_cascade = None
    try:
        haar_dir = getattr(getattr(cv2, "data", None), "haarcascades", "")
        if isinstance(haar_dir, str) and haar_dir:
            xml_file = Path(haar_dir) / "haarcascade_frontalface_default.xml"
            if xml_file.is_file():
                fc = cv2.CascadeClassifier(str(xml_file))
                if not fc.empty():
                    face_cascade = fc
    except Exception:
        face_cascade = None

    brilhos: list[float] = []
    temp_ratios: list[float] = []
    areas_rosto: list[float] = []

    for fp in frames_paths:
        if not fp.is_file():
            continue
        data = np.fromfile(str(fp), dtype=np.uint8)
        img = cv2.imdecode(data, cv2.IMREAD_COLOR)
        if img is None:
            continue
        h, w = img.shape[:2]
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        brilhos.append(float(np.mean(gray)))

        # Temperatura aproximada: razão canal Vermelho (R) / Azul (B)
        b_mean = float(np.mean(img[:, :, 0])) + 1.0
        r_mean = float(np.mean(img[:, :, 2])) + 1.0
        temp_ratios.append(r_mean / b_mean)

        if face_cascade is not None:
            faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=4, minSize=(40, 40))
            if len(faces) > 0:
                maior = max(faces, key=lambda r: r[2] * r[3])
                area_rel = (maior[2] * maior[3]) / float(max(1, w * h))
                areas_rosto.append(area_rel)
        else:
            # Fallback YCrCb skin-region estimation no terço superior/central da imagem vertical
            ycrcb = cv2.cvtColor(img[: int(h * 0.65), int(w * 0.15) : int(w * 0.85)], cv2.COLOR_BGR2YCrCb)
            mask_skin = cv2.inRange(ycrcb, (0, 133, 77), (255, 173, 127))
            skin_pixels = float(np.count_nonzero(mask_skin))
            area_rel = min(0.25, skin_pixels / float(max(1, w * h)))
            if area_rel > 0.005:
                areas_rosto.append(area_rel)

    area_media = round(sum(areas_rosto) / len(areas_rosto), 4) if areas_rosto else 0.0
    if area_media >= 0.08:
        plano_detectado = "close_up_selfie_frontal"
    elif area_media >= 0.025:
        plano_detectado = "plano_medio_peito_ cintura"
    elif area_media > 0:
        plano_detectado = "plano_aberto_corpo_inteiro"
    else:
        plano_detectado = "plano_detalhe_ou_perfil"

    temp_media = round(sum(temp_ratios) / len(temp_ratios), 3) if temp_ratios else 1.0
    iluminacao_tipo = "quente_residencial_indoor" if temp_media >= 1.06 else "fria_neutra_comercial_ou_consultorio"

    return {
        "metodo": "opencv_local",
        "plano_camera_detectado": plano_detectado,
        "area_relativa_rosto": area_media,
        "brilho_medio_0_255": round(sum(brilhos) / max(1, len(brilhos)), 1) if brilhos else 128.0,
        "razao_temperatura_r_b": temp_media,
        "iluminacao_detectada": iluminacao_tipo,
    }


def extrair_dna_verbal_e_esqueleto(texto_transcrito: str, roteiro: dict[str, Any]) -> dict[str, Any]:
    """
    Extrai automaticamente da transcrição do viral:
    - O ingrediente/produto principal mencionado;
    - A parte do corpo / local de aplicação;
    - O benefício / dor principal;
    - O esqueleto parametrizado da copy com variáveis {INGREDIENTE}, {LOCAL_CORPO}, {FREQUENCIA}, {CTA}.
    """
    t_low = texto_transcrito.lower()

    # Banco expansível de detecção de ingredientes/mecanismos comuns em virais DTC
    ingredientes_map = {
        "baking soda": ("Arm & Hammer orange box of baking soda and a small white ceramic bowl with white paste", "baking soda"),
        "apple cider vinegar": ("a glass bottle of raw unfiltered apple cider vinegar with mother", "apple cider vinegar"),
        "castor oil": ("an amber glass dropper bottle of organic cold-pressed castor oil", "castor oil"),
        "pink salt": ("a clear glass jar of coarse Himalayan pink salt and a metal spoon with warm water", "pink salt"),
        "turmeric": ("a small bowl of bright yellow turmeric powder and a glass of warm water", "turmeric"),
        "olive oil": ("a dark green glass bottle of extra virgin olive oil and a tablespoon", "olive oil"),
        "garlic": ("peeled raw garlic cloves on a small cutting board with a glass of warm water", "garlic"),
        "cloves": ("a small jar of whole dried cloves and a mug of steeped clove tea", "cloves"),
    }
    objeto_visual_en = "a household wellness ingredient container and a small ceramic bowl"
    ingrediente_detectado = "natural ingredient"
    for chave, (desc_en, nome_curto) in ingredientes_map.items():
        if chave in t_low:
            objeto_visual_en = desc_en
            ingrediente_detectado = nome_curto
            break

    partes_corpo = [
        "armpits",
        "armpit",
        "sides of your neck",
        "behind your ears",
        "groin creases",
        "groin",
        "soles of your feet",
        "thighs",
        "thigh",
        "feet",
        "foot",
        "belly button",
        "navel",
        "under your tongue",
        "knees",
        "neck",
        "belly",
        "gut",
        "stomach",
    ]
    local_detectado = next((p for p in partes_corpo if p in t_low), "body")

    frequencias = ["every night", "before bed", "every morning", "on an empty stomach", "tonight", "in just seven days"]
    freq_detectada = next((f for f in frequencias if f in t_low), "every night")

    # Classificação Determinística 001 (Padrão Spies L10–L15 + Raphael Paiva + Aula 21/10)
    if any(k in t_low for k in ("glp-1", "glp1", "mounjaro", "ozempic")):
        familia_roteiro = "GLP1-MOUNJARO (Homemade GLP-1 / Mounjaro Killer — Dever de Casa 21/10)"
        objeto_visual_en = "an Arm & Hammer orange box of baking soda, a metal spoon, fresh cut lemon halves, and a clear glass of ice-cold fizzing water"
    elif any(k in t_low for k in ("pulls out of your gut", "does to your")):
        familia_roteiro = "GUT-PULL / DOES-TO-FAT (This is what baking soda pulls out of / does to... [34% Top 30])"
    elif any(k in t_low for k in ("do not drink", "don't drink")):
        familia_roteiro = "DO-NOT-DRINK (Quebra de Padrão: Do not drink baking soda)"
    elif any(k in t_low for k in ("one spoon", "one tablespoon", "empty stomach")):
        familia_roteiro = "DOSE-MATINAL (1 Spoon Every Morning Empty Stomach)"
    elif any(k in t_low for k in ("every night", "watch your", "rub baking soda", "put baking soda")):
        familia_roteiro = "CORPO-A-NOITE (Instrução + Local do Corpo à Noite [48% dos Virais])"
    else:
        familia_roteiro = "OUTRA-ABERTURA"

    alertas_veo = []
    if "groin" in t_low:
        alertas_veo.append(
            "BLOQUEIO VEO (Groin/Virilha): Use uma das 3 saídas da Aula 21/10 -> (1) Manequim anatômico, (2) Pasta branca já aplicada na pele e enfermeira só apontando, ou (3) Apontar por cima da roupa."
        )
    if any(k in t_low for k in ("belly", "stomach", "gut")):
        alertas_veo.append("PELE EXPOSTA: Prefira mostrar pote/colher/limão em 1º plano ou manequim para evitar filtro de segurança.")

    esqueleto = texto_transcrito
    if ingrediente_detectado in esqueleto.lower():
        esqueleto = re.sub(re.escape(ingrediente_detectado), "{INGREDIENTE}", esqueleto, flags=re.IGNORECASE)
    if local_detectado in esqueleto.lower():
        esqueleto = re.sub(re.escape(local_detectado), "{LOCAL_CORPO}", esqueleto, flags=re.IGNORECASE)
    if freq_detectada in esqueleto.lower():
        esqueleto = re.sub(re.escape(freq_detectada), "{FREQUENCIA}", esqueleto, flags=re.IGNORECASE)

    edicoes_baratas_21_10 = [
        {
            "tipo": "antes_e_depois_hook",
            "janela_s": "0.2s - 5.2s",
            "posicao": "Acima da legenda, canto direito (sem tampar rosto/mão)",
            "descricao": "2 fotos de Antes e Depois (0.2-2.7s Foto 1 | 2.7-5.2s Foto 2) para provar o hook e acionar a IA visual do Facebook.",
        },
        {
            "tipo": "imagem_de_apoio_mecanismo",
            "janela_s": "5.2s - 9.0s",
            "posicao": "Acima da legenda, canto direito",
            "descricao": f"Imagem anatômica/apoio ilustrando '{local_detectado}' ou 'lymph nodes / GLP-1' no segundo exato da fala.",
        },
    ]

    return {
        "familia_roteiro_001": familia_roteiro,
        "ingrediente_detectado": ingrediente_detectado,
        "objeto_principal_visual_en": objeto_visual_en,
        "local_corpo_detectado": local_detectado,
        "frequencia_detectada": freq_detectada,
        "cta_palavra": roteiro.get("cta_palavra", "COMMENT YES"),
        "alertas_veo": alertas_veo,
        "edicoes_baratas_21_10": edicoes_baratas_21_10,
        "esqueleto_copy_parametrizado": esqueleto,
        "takes_originais": roteiro.get("takes", []),
    }


BANCO_COPIES_E_FORMATOS_001: list[dict[str, Any]] = [
    {
        "id": "DEVER_21_10_COPY_1_GLP1_DM",
        "categoria": "Dever de Casa 21/10 (Oficial)",
        "titulo": "🔥 Copy 1 — Homemade GLP-1 + Mulheres Agradecendo na DM",
        "familia": "GLP1-MOUNJARO",
        "formato_visual_recomendado": "cozinha_clara_enfermeira_24mm",
        "objeto_principal_en": "an Arm & Hammer orange box of baking soda, a metal spoon, fresh cut lemon halves, and a clear glass of ice-cold fizzing water",
        "fala_completa": (
            "Did you know that if you mix lemon juice with baking soda, you create a homemade GLP-1?! "
            "I mix these 3 ingredients with ice-cold water every morning, and drink them on a empty stomach, "
            "some women doubted me, but once they decided to try it, they started thanking me on my direct messages. "
            "Comment yes, and I will send you the full recipe now."
        ),
        "takes_falas": (
            "Did you know that if you mix lemon juice with baking soda, you create a homemade GLP-1?! || "
            "I mix these 3 ingredients with ice-cold water every morning, and drink them on a empty stomach, || "
            "some women doubted me, but once they decided to try it, they started thanking me on my direct messages. Comment yes, and I will send you the full recipe now."
        ),
    },
    {
        "id": "DEVER_21_10_COPY_2_GLP1_FLAT_STOMACH",
        "categoria": "Dever de Casa 21/10 (Oficial)",
        "titulo": "⚡ Copy 2 — 1 Spoon GLP-1 + Flat Stomach (Not The Gym)",
        "familia": "GLP1-MOUNJARO",
        "formato_visual_recomendado": "ugc_cozinha_selfie_24mm",
        "objeto_principal_en": "an Arm & Hammer orange box of baking soda, a metal tablespoon with white powder, cut lemon halves, and a glass of ice water",
        "fala_completa": (
            "If you mix one spoon of baking soda and lemon juice you create a homemade GLP1?! "
            "I mix these 3 ingredients with ice-cold water every morning, and drink them on a empty stomach. "
            "This is the real reason my stomach finally went flat, not the gym. "
            "Comment yes, and I will send you the full recipe now."
        ),
        "takes_falas": (
            "If you mix one spoon of baking soda and lemon juice you create a homemade GLP1?! || "
            "I mix these 3 ingredients with ice-cold water every morning, and drink them on a empty stomach. || "
            "This is the real reason my stomach finally went flat, not the gym. Comment yes, and I will send you the full recipe now."
        ),
    },
    {
        "id": "DEVER_21_10_COPY_3_MOUNJARO_HELL",
        "categoria": "Dever de Casa 21/10 (Oficial)",
        "titulo": "💣 Copy 3 — Mounjaro Can Go Straight To Hell (5 lbs/week)",
        "familia": "GLP1-MOUNJARO",
        "formato_visual_recomendado": "cozinha_clara_homem_forte_50_24mm",
        "objeto_principal_en": "an Arm & Hammer orange box of baking soda, a metal spoon, fresh lemon halves, and a glass of ice-cold water",
        "fala_completa": (
            "Mounjaro can go straight to hell, one spoon of baking soda with lemon juice is all you need to burn 5 pounds of fat every week. "
            "I mix these 3 ingredients with ice-cold water every morning, and drink them on a empty stomach. "
            "This is the real reason my stomach finally went flat, not the gym. "
            "Comment yes, and I will send you the full recipe now."
        ),
        "takes_falas": (
            "Mounjaro can go straight to hell, one spoon of baking soda with lemon juice is all you need to burn 5 pounds of fat every week. || "
            "I mix these 3 ingredients with ice-cold water every morning, and drink them on a empty stomach. || "
            "This is the real reason my stomach finally went flat, not the gym. Comment yes, and I will send you the full recipe now."
        ),
    },
    {
        "id": "SPY_F01_BELLY_BUTTON_1_2M",
        "categoria": "Top 15 Spies L10–L15 (1.2M views)",
        "titulo": "🏆 F01 — Belly Button Every Night (1.2M views — Mina Cho / Sophie)",
        "familia": "CORPO-A-NOITE",
        "formato_visual_recomendado": "cozinha_clara_enfermeira_24mm",
        "objeto_principal_en": "an Arm & Hammer orange box of baking soda and a small white bowl with white paste",
        "fala_completa": (
            "Put baking soda in your belly button every night and watch your body start dropping weight while you sleep. "
            "Add one more ingredient and it works three times faster. Comment yes and I send you the full trick."
        ),
        "takes_falas": (
            "Put baking soda in your belly button every night and watch your body start dropping weight while you sleep. || "
            "Add one more ingredient and it works three times faster. || "
            "Comment yes and I send you the full trick."
        ),
    },
    {
        "id": "SPY_F02_SIDES_OF_NECK_706K",
        "categoria": "Top 15 Spies L10–L15 (706k views)",
        "titulo": "🏆 F02 — Sides of Your Neck + Lymph Nodes (706k views — Linda Harper)",
        "familia": "CORPO-A-NOITE",
        "formato_visual_recomendado": "cozinha_clara_enfermeira_24mm",
        "objeto_principal_en": "an Arm & Hammer orange box of baking soda and a small ceramic bowl with white paste",
        "fala_completa": (
            "Rub baking soda on the sides of your neck every night and watch your belly fat melt away. "
            "Your neck holds the lymph nodes that drain fat from your whole body. "
            "My clients swear by this now. Save this video, comment yes, and follow me so I can send you the recipe."
        ),
        "takes_falas": (
            "Rub baking soda on the sides of your neck every night and watch your belly fat melt away. || "
            "Your neck holds the lymph nodes that drain fat from your whole body. || "
            "My clients swear by this now. Save this video, comment yes, and follow me so I can send you the recipe."
        ),
    },
    {
        "id": "SPY_F03_BEHIND_YOUR_EARS_LYMPH",
        "categoria": "Variação Linfonodos Aula 21/10 (Destrava Página)",
        "titulo": "🔥 F03 — Behind Your Ears + Lymph Nodes (Tasha Monroe L14-029)",
        "familia": "CORPO-A-NOITE",
        "formato_visual_recomendado": "cozinha_clara_enfermeira_24mm",
        "objeto_principal_en": "an Arm & Hammer orange box of baking soda and a small white ceramic bowl with white paste",
        "fala_completa": (
            "Rub baking soda behind your ears every night and watch your body start dropping weight while you sleep. "
            "Behind your ears sit the cervical lymph nodes that drain stubborn fluid and fat from your body. "
            "Every woman I treat does this now. Save this video, comment yes, and follow me so I can send you the recipe."
        ),
        "takes_falas": (
            "Rub baking soda behind your ears every night and watch your body start dropping weight while you sleep. || "
            "Behind your ears sit the cervical lymph nodes that drain stubborn fluid and fat from your body. || "
            "Every woman I treat does this now. Save this video, comment yes, and follow me so I can send you the recipe."
        ),
    },
    {
        "id": "SPY_F04_ARMPITS_LYMPH_NODES",
        "categoria": "Exemplo Oficial Aula 21/10 (CapsuLean 199k views)",
        "titulo": "🔥 F04 — Under Your Armpits + Lymph Nodes (Com Imagens de Apoio)",
        "familia": "CORPO-A-NOITE",
        "formato_visual_recomendado": "cozinha_clara_enfermeira_24mm",
        "objeto_principal_en": "an Arm & Hammer orange box of baking soda and a small ceramic bowl with white paste",
        "fala_completa": (
            "Rub baking soda under your armpits every night and watch your body start dropping weight while you sleep. "
            "Your armpits sit right on top of your largest fat burning lymph nodes. "
            "My clients swear by this now. Save this video, comment yes, and follow me so I can send you the recipe."
        ),
        "takes_falas": (
            "Rub baking soda under your armpits every night and watch your body start dropping weight while you sleep. || "
            "Your armpits sit right on top of your largest fat burning lymph nodes. || "
            "My clients swear by this now. Save this video, comment yes, and follow me so I can send you the recipe."
        ),
    },
    {
        "id": "SPY_F05_GUT_PULL_7_DAYS_490K",
        "categoria": "Top 15 Spies L10–L15 (490k views — Nicole Harris)",
        "titulo": "🏆 F05 — Pulls Out of Your Gut in 7 Days (490k views — Homem Forte na Cozinha)",
        "familia": "GUT-PULL",
        "formato_visual_recomendado": "cozinha_clara_homem_forte_50_24mm",
        "objeto_principal_en": "an Arm & Hammer orange box of baking soda, cut lemon halves, a glass of cold water, and a clear glass bowl on the counter",
        "fala_completa": (
            "This is what baking soda pulls out of your gut in just seven days. Just watch. "
            "Just one teaspoon of baking soda, add the juice of half a lemon, a pinch of salt, and cold water. "
            "No more needles, no restrictive diets, no exercise. It solves the problem from the inside out. "
            "Comment yes to receive all the infos and follow me."
        ),
        "takes_falas": (
            "This is what baking soda pulls out of your gut in just seven days. Just watch. || "
            "Just one teaspoon of baking soda, add the juice of half a lemon, a pinch of salt, and cold water. No more needles, no restrictive diets, no exercise. || "
            "It solves the problem from the inside out. Comment yes to receive all the infos and follow me."
        ),
    },
    {
        "id": "SPY_F06_DO_NOT_DRINK_428K",
        "categoria": "Top 15 Spies L10–L15 (428k views — Quebra de Padrão)",
        "titulo": "⚡ F06 — Do Not Drink Baking Soda (428k views — Juliet / Jamal)",
        "familia": "DO-NOT-DRINK",
        "formato_visual_recomendado": "cozinha_clara_enfermeira_24mm",
        "objeto_principal_en": "a clear glass of water and an Arm & Hammer orange box of baking soda on the kitchen counter",
        "fala_completa": (
            "Do not drink baking soda until you know the exact proportion. "
            "If you take it the wrong way, it does nothing for your belly fat. "
            "Mix half a spoon with lemon and cold water on an empty stomach. Comment yes and I'll send you the exact step-by-step."
        ),
        "takes_falas": (
            "Do not drink baking soda until you know the exact proportion. || "
            "If you take it the wrong way, it does nothing for your belly fat. Mix half a spoon with lemon and cold water on an empty stomach. || "
            "Comment yes and I'll send you the exact step-by-step."
        ),
    },
    {
        "id": "SPY_F07_GROIN_CREASES_LYMPH",
        "categoria": "Variação Linfonodos Aula 21/10 (Grace Lin 38k)",
        "titulo": "🔥 F07 — Groin Creases + Lower Lymph Nodes (Com Contorno Anti-Bloqueio Veo)",
        "familia": "CORPO-A-NOITE",
        "formato_visual_recomendado": "cozinha_clara_enfermeira_24mm",
        "objeto_principal_en": "an Arm & Hammer orange box of baking soda and a small ceramic bowl with white paste",
        "fala_completa": (
            "Rub baking soda on your groin creases every night and watch your body start dropping weight while you sleep. "
            "Your groin holds the largest lower body lymph nodes that flush out trapped fat and water weight. "
            "Every woman I treat does this now. Save this video, comment yes, and follow me so I can send you the recipe."
        ),
        "takes_falas": (
            "Rub baking soda on your groin creases every night and watch your body start dropping weight while you sleep. || "
            "Your groin holds the largest lower body lymph nodes that flush out trapped fat and water weight. || "
            "Every woman I treat does this now. Save this video, comment yes, and follow me so I can send you the recipe."
        ),
    },
    {
        "id": "SPY_F08_WHAT_IT_DOES_TO_BELLY_1M",
        "categoria": "Top 15 Spies L10–L15 (1.0M views — Lisa Morgan)",
        "titulo": "🏆 F08 — What Baking Soda Does To Your Belly (1.0M views)",
        "familia": "DOES-TO-FAT",
        "formato_visual_recomendado": "ugc_cozinha_selfie_24mm",
        "objeto_principal_en": "an Arm & Hammer orange box of baking soda, half a fresh lemon, cinnamon, and a clear glass of fizzing water",
        "fala_completa": (
            "This is what baking soda does to your belly. Now look at that, flat, okay? "
            "First, half a teaspoon of baking soda. Then squeeze in half a lemon. Watch it fizz! Last, a pinch of cinnamon. "
            "Sip it slow on an empty stomach. Comment yes for the full recipe and follow me."
        ),
        "takes_falas": (
            "This is what baking soda does to your belly. Now look at that, flat, okay? || "
            "First, half a teaspoon of baking soda. Then squeeze in half a lemon. Watch it fizz! Last, a pinch of cinnamon. || "
            "Sip it slow on an empty stomach. Comment yes for the full recipe and follow me."
        ),
    },
    {
        "id": "SPY_F09_SOLES_OF_FEET_199K",
        "categoria": "Top 15 Spies L10–L15 (199k views — Steve Caldwell)",
        "titulo": "🔥 F09 — Soles of Your Feet Every Night (199k views)",
        "familia": "CORPO-A-NOITE",
        "formato_visual_recomendado": "cozinha_clara_enfermeira_24mm",
        "objeto_principal_en": "an Arm & Hammer orange box of baking soda and a small white ceramic bowl with white paste",
        "fala_completa": (
            "Rub baking soda on the soles of your feet every night and watch your body start dropping weight while you sleep. "
            "Add one more ingredient from your kitchen and it works three times faster. "
            "Comment yes and I will send you the full recipe."
        ),
        "takes_falas": (
            "Rub baking soda on the soles of your feet every night and watch your body start dropping weight while you sleep. || "
            "Add one more ingredient from your kitchen and it works three times faster. || "
            "Comment yes and I will send you the full recipe."
        ),
    },
]


def aplicar_edicao_barata_video_pronto(
    video_entrada: Path | str,
    video_saida: Path | str,
    img_antes_depois_1: Path | str | None = None,
    img_antes_depois_2: Path | str | None = None,
    img_apoio_mecanismo: Path | str | None = None,
    img_apoio_1: Path | str | None = None,
    img_apoio_hook: Path | str | None = None,
    img_balao_comentario: Path | str | None = None,
    t_mecanismo_ini: float = 5.2,
    t_mecanismo_fim: float = 9.4,
) -> Path:
    """
    Implementa as Ideias #1 e #2 da Aula de Brainstorming (21/10):
    Recebe um vídeo JÁ PRONTO e sobrepõe no canto direito acima da legenda (x=W-w-36:y=760 num 1080x1920),
    sem tampar o rosto nem a legenda (que fica em y=1240):
      - 0.2s a 2.65s: Antes e Depois #1 (ou Imagem de Apoio do Hook)
      - 2.65s a 5.15s: Antes e Depois #2
      - t_mecanismo_ini a t_mecanismo_fim (ex: 5.2s a 9.4s): Imagem de Apoio do Mecanismo (mapa dos lymph nodes / GLP-1)
      - Opcional (0.15s a 4.8s): Balão de Resposta a Comentário no topo (x=(W-w)/2:y=56)
    Usa aceleração GPU (`h264_nvenc`) quando disponível.
    """
    video_entrada = Path(video_entrada)
    video_saida = Path(video_saida)
    video_saida.parent.mkdir(parents=True, exist_ok=True)

    apoio_mec = img_apoio_mecanismo or img_apoio_1
    p_ba1 = Path(img_antes_depois_1) if img_antes_depois_1 else None
    p_ba2 = Path(img_antes_depois_2) if img_antes_depois_2 else None
    p_aph = Path(img_apoio_hook) if img_apoio_hook else None
    p_apm = Path(apoio_mec) if apoio_mec else None
    p_bal = Path(img_balao_comentario) if img_balao_comentario else None

    inputs = ["-i", str(video_entrada)]
    filter_parts = []
    last_stream = "[0:v]"
    input_idx = 1

    # 1. Balão de comentário no topo (se fornecido)
    if p_bal and p_bal.is_file():
        inputs.extend(["-i", str(p_bal)])
        sc = f"[ov{input_idx}]"
        out_s = f"[v{input_idx}]"
        filter_parts.append(f"[{input_idx}:v]scale=820:-1{sc}")
        filter_parts.append(f"{last_stream}{sc}overlay=(W-w)/2:56:enable='between(t,0.15,4.80)'{out_s}")
        last_stream = out_s
        input_idx += 1

    # 2. Cards laterais à direita logo acima da legenda (sem encostar na legenda em y=1240)
    overlays_cfg = []
    if p_ba1 and p_ba1.is_file():
        overlays_cfg.append((p_ba1, 0.20, 2.65, 340, 740))
    elif p_aph and p_aph.is_file():
        overlays_cfg.append((p_aph, 0.20, 3.20, 320, 720))

    if p_ba2 and p_ba2.is_file():
        overlays_cfg.append((p_ba2, 2.65, 5.15, 340, 740))

    if p_apm and p_apm.is_file():
        overlays_cfg.append((p_apm, t_mecanismo_ini, t_mecanismo_fim, 245, 650))

    for img_path, t_start, t_end, larg, pos_y in overlays_cfg:
        inputs.extend(["-i", str(img_path)])
        scaled = f"[ov{input_idx}]"
        out_s = f"[v{input_idx}]"
        filter_parts.append(f"[{input_idx}:v]scale={larg}:-1,pad=iw+10:ih+10:5:5:white{scaled}")
        filter_parts.append(
            f"{last_stream}{scaled}overlay=W-w-36:{pos_y}:enable='between(t,{t_start:.2f},{t_end:.2f})'{out_s}"
        )
        last_stream = out_s
        input_idx += 1

    if not filter_parts:
        import shutil
        shutil.copy2(video_entrada, video_saida)
        return video_saida

    filter_complex = ";".join(filter_parts)
    cmd_nvenc = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", last_stream, "-map", "0:a?",
        "-c:v", "h264_nvenc", "-preset", "p2", "-rc", "vbr", "-cq", "20", "-pix_fmt", "yuv420p",
        "-c:a", "copy", "-movflags", "+faststart",
        str(video_saida),
    ]
    proc = subprocess.run(cmd_nvenc, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        cmd_cpu = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            *inputs,
            "-filter_complex", filter_complex,
            "-map", last_stream, "-map", "0:a?",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
            "-c:a", "copy", "-movflags", "+faststart",
            str(video_saida),
        ]
        subprocess.run(cmd_cpu, capture_output=True, text=True, check=True)
    return video_saida


# ==============================================================================
# 2. ASSISTIR VIRAL E SALVAR NA MEMÓRIA (JSON + OBSIDIAN BIDIRECIONAL)
# ==============================================================================
def carregar_memoria_virais(path: Path = MEMORIA_VIRAIS_PATH) -> dict[str, Any]:
    if path.is_file():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "schema": "MEMORIA_VIRAIS_FORJA_V2",
        "atualizado_em": datetime.now().isoformat(timespec="seconds"),
        "formatos_visuais_disponiveis": list(FORMATOS_VISUAIS_CATALOGO.keys()),
        "virais_catalogados": {},
    }


def _gerar_markdown_obsidian_viral(registro: dict[str, Any]) -> str:
    vid_id = registro["viral_id"]
    dna_v = registro["dna_verbal"]
    dna_vis = registro["dna_visual"]
    metricas = registro["metricas_ritmo"]
    cortes = registro.get("cortes_cena_detectados_s", [])

    takes_md = []
    for t in dna_v.get("takes_originais", []):
        takes_md.append(
            f"### Take {t['take']} ({t['papel'].upper()} — {t['palavras']} palavras | ~{t['duracao_estimada_s']}s)\n"
            f"- **Fala:** \"{t['fala']}\"\n"
        )
    takes_str = "\n".join(takes_md)

    formatos_str = "\n".join(
        f"- `{fid}`: **{finfo['titulo']}**" for fid, finfo in FORMATOS_VISUAIS_CATALOGO.items()
    )

    return f"""---
viral_id: "{vid_id}"
formato_original: "{registro['formato_original']}"
ingrediente: "{dna_v['ingrediente_detectado']}"
objeto_principal_en: "{dna_v['objeto_principal_visual_en']}"
local_corpo: "{dna_v['local_corpo_detectado']}"
frequencia: "{dna_v['frequencia_detectada']}"
cta_palavra: "{dna_v['cta_palavra']}"
duracao_s: {metricas['duracao_s']}
palavras_por_segundo: {metricas['palavras_por_segundo']}
atualizado_em: "{registro['atualizado_em']}"
---

# 🎬 DNA do Viral: `{vid_id}` ({registro['formato_original']})

> [!TIP] Edição ao Vivo pelo Obsidian
> Qualquer alteração que você fizer nos campos do cabeçalho YAML acima (`objeto_principal_en`, `ingrediente`, `cta_palavra`) ou nas falas abaixo será lida automaticamente pelo `motor_virais.py` na hora de transplantar ou forjar um lote!

## 1. Métricas de Ritmo & Cortes Reais Detectados
- **Arquivo de Origem:** `{registro['arquivo_viral']}`
- **Duração Total:** `{metricas['duracao_s']}s` | **Total de Palavras:** `{metricas['total_palavras']}`
- **Cadência:** `{metricas['palavras_por_segundo']} palavras/s` (Fala ativa: `{metricas['palavras_por_segundo_fala_ativa']} palavras/s`)
- **Cortes de Cena Detectados (FFmpeg):** `{cortes if cortes else 'Plano-sequência contínuo (cortes por frase)'}`
- **Análise Óptica OpenCV:** Plano `{dna_vis['metricas_opencv'].get('plano_camera_detectado')}` | Iluminação `{dna_vis['metricas_opencv'].get('iluminacao_detectada')}`

---

## 2. Camada Verbal (Esqueleto de Copy & Takes)

### Esqueleto Parametrizado
```text
{dna_v['esqueleto_copy_parametrizado']}
```

{takes_str}

---

## 3. Camada Visual Original
- **Hook Visual (0–3s):** {dna_vis['hook_visual'].get('resumo')}
- **Gesto Físico do Hook:** {dna_vis['hook_visual'].get('gesto')}
- **Objeto em Destaque (EN):** `{dna_v['objeto_principal_visual_en']}`
- **Cenário Original:** {dna_vis['cena'].get('cenario')}
- **Personagem/Roupa Original:** {dna_vis['cena'].get('personagem')} — {dna_vis['cena'].get('roupa')}

---

## 4. Formatos Visuais Disponíveis para Transplante Imediato
Para recriar este mesmo vídeo em **outro formato visual** (com Alto Realismo Cru de Celular 24mm + Zero Bokeh), escolha qualquer formato abaixo:
{formatos_str}

### Comando Rápido de Transplante:
```powershell
python forjar.py --viral "{registro['arquivo_viral']}" --formato-destino ugc_cozinha_selfie_24mm --qtd 10
```
"""


def sincronizar_edicoes_do_obsidian(viral_id: str, registro: dict[str, Any]) -> dict[str, Any]:
    """
    Se existir a nota Markdown no Obsidian e o usuário tiver editado `objeto_principal_en` ou `cta_palavra`
    no frontmatter YAML, aplica as edições na memória da Forja.
    """
    md_path = OBSIDIAN_CATALOGO_DIR / f"{viral_id}.md"
    if not md_path.is_file():
        return registro
    try:
        conteudo = md_path.read_text(encoding="utf-8")
        m_obj = re.search(r'^objeto_principal_en:\s*"([^"]+)"', conteudo, flags=re.MULTILINE)
        if m_obj:
            registro["dna_verbal"]["objeto_principal_visual_en"] = m_obj.group(1).strip()
        m_cta = re.search(r'^cta_palavra:\s*"([^"]+)"', conteudo, flags=re.MULTILINE)
        if m_cta:
            registro["dna_verbal"]["cta_palavra"] = m_cta.group(1).strip()
    except Exception:
        pass
    return registro


def assistir_e_memorizar_viral(
    video_path: Path,
    viral_id: str | None = None,
    formato_nome: str | None = None,
) -> dict[str, Any]:
    """
    Assiste um vídeo viral novo:
    1. Roda Whisper GPU + extração de frames do Hook e por take (`analisar_viral`);
    2. Detecta os cortes de cena reais via FFmpeg (`detectar_cortes_cena_ffmpeg`);
    3. Extrai métricas ópticas locais via OpenCV (`analisar_metricas_visuais_opencv`);
    4. Separa o DNA Verbal (Esqueleto + Objeto Principal) e DNA Visual;
    5. Salva em `memoria_virais.json` e cria a nota editável no Cofre do Obsidian.
    """
    video_path = video_path.resolve()
    analise = analisar_viral(video_path, formato_nome=formato_nome)
    roteiro = gerar_roteiro_takes(analise)
    cortes_s = detectar_cortes_cena_ffmpeg(video_path)

    frames_hook_paths = [Path(p) for p in analise.get("frames_hook", {}).values()]
    metricas_cv = analisar_metricas_visuais_opencv(frames_hook_paths)
    dna_verbal = extrair_dna_verbal_e_esqueleto(analise["transcricao"]["texto"], roteiro)

    vid_key = viral_id or f"{video_path.stem}_{analise['formato']}"
    registro = {
        "viral_id": vid_key,
        "arquivo_viral": str(video_path),
        "formato_original": analise["formato"],
        "atualizado_em": datetime.now().isoformat(timespec="seconds"),
        "metricas_ritmo": analise["metricas_ritmo"],
        "cortes_cena_detectados_s": cortes_s,
        "dna_verbal": dna_verbal,
        "dna_visual": {
            "hook_visual": analise["hook_visual"],
            "cena": analise["cena"],
            "cena_fixa_en": analise.get("cena_fixa_en", ""),
            "acoes_en": analise.get("acoes_en", {}),
            "metricas_opencv": metricas_cv,
        },
        "analise_bruta": analise,
    }

    memoria = carregar_memoria_virais()
    memoria["atualizado_em"] = registro["atualizado_em"]
    memoria["virais_catalogados"][vid_key] = registro
    MEMORIA_VIRAIS_PATH.write_text(json.dumps(memoria, ensure_ascii=False, indent=2), encoding="utf-8")

    # Salva também na pasta do Cofre do Obsidian para edição fácil pelo usuário
    try:
        OBSIDIAN_CATALOGO_DIR.mkdir(parents=True, exist_ok=True)
        md_path = OBSIDIAN_CATALOGO_DIR / f"{vid_key}.md"
        md_path.write_text(_gerar_markdown_obsidian_viral(registro), encoding="utf-8")
        registro["nota_obsidian"] = str(md_path)
    except Exception as e:
        registro["aviso_obsidian"] = str(e)

    return registro


# ==============================================================================
# 3. MOTOR DE TRANSPLANTE DE FORMATO VISUAL (1 VÍDEO -> OUTRO FORMATO VISUAL)
# ==============================================================================
def transplantar_formato_visual(
    analise_viral: dict[str, Any],
    formato_destino_id: str,
    objeto_override_en: str | None = None,
    troca_copy: str | None = None,
) -> dict[str, Any]:
    """
    Recebe o `analise_viral` de qualquer vídeo (ex.: Médico em Consultório aplicando bicarbonato na coxa)
    e transplanta 100% da sua camada visual (cenário, avatares, roupas, enquadramento e ações físicas de cada take)
    para o `formato_destino_id` escolhido (ex.: `ugc_cozinha_selfie_24mm` — Pessoa Comum na Cozinha de Casa em Selfie 24mm)!

    Retorna um novo dicionário `analise_viral` transplantado pronto para ser consumido por `gerar_prompts_video()`!
    """
    if formato_destino_id not in FORMATOS_VISUAIS_CATALOGO:
        disponiveis = ", ".join(FORMATOS_VISUAIS_CATALOGO.keys())
        raise ValueError(f"Formato de destino '{formato_destino_id}' desconhecido. Disponíveis: {disponiveis}")

    fmt = FORMATOS_VISUAIS_CATALOGO[formato_destino_id]
    if formato_destino_id == "medico_consultorio_original":
        return dict(analise_viral)

    roteiro_temp = gerar_roteiro_takes(analise_viral, troca=troca_copy)
    texto_atual = " ".join(t["fala"] for t in roteiro_temp.get("takes", []))
    dna_v = extrair_dna_verbal_e_esqueleto(texto_atual, roteiro_temp)

    objeto_en = (objeto_override_en or dna_v["objeto_principal_visual_en"]).strip()

    cena_fixa_nova = fmt["cena_fixa_template_en"].format(OBJETO_PRINCIPAL_EN=objeto_en)
    acoes_novas = {
        chave: tpl.format(OBJETO_PRINCIPAL_EN=objeto_en)
        for chave, tpl in fmt["acoes_template_en"].items()
    }

    nova_analise = json.loads(json.dumps(analise_viral))
    nova_analise["formato_origem"] = analise_viral.get("formato", "indefinido")
    nova_analise["formato"] = f"{analise_viral.get('formato', 'viral')}__{formato_destino_id}"
    nova_analise["formato_visual_transplantado"] = formato_destino_id
    nova_analise["titulo_formato_visual"] = fmt["titulo"]
    nova_analise["cena_fixa_en"] = cena_fixa_nova
    nova_analise["acoes_en"] = acoes_novas
    nova_analise["provas_de_vida_override_en"] = fmt["provas_de_vida_en"]
    nova_analise["luz_fisica_override_en"] = fmt["luz_fisica_en"]
    nova_analise["variacoes_avatar"] = fmt["avatares"]
    nova_analise["hook_visual"] = {
        "resumo": f"[{fmt['titulo']}] Personagem apresenta {objeto_en} em perspectiva forçada na lente 24mm sem cobrir a boca.",
        "gesto": acoes_novas.get("hook_frame1", ""),
        "objeto": objeto_en,
        "enquadramento": "Vertical 9:16 front-facing iPhone 24mm wide-angle lens with deep depth of field and zero bokeh.",
    }
    return nova_analise


def main() -> None:
    parser = argparse.ArgumentParser(description="Forja — Motor de Virais (Assistir, Memorizar no Obsidian e Transplantar Formato)")
    sub = parser.add_subparsers(dest="comando", required=True)

    p_ass = sub.add_parser("assistir", help="Assiste um vídeo viral novo, extrai o DNA e salva em memoria_virais.json + Obsidian")
    p_ass.add_argument("--viral", default="virais/viral_ref_01.mp4", help="Caminho do arquivo .mp4 viral")
    p_ass.add_argument("--id", default="", help="ID opcional para o catálogo")
    p_ass.add_argument("--formato", default="", help="Nome opcional do formato original")

    p_tr = sub.add_parser("transplantar", help="Transplanta um viral para outro formato visual (ex: ugc_cozinha_selfie_24mm)")
    p_tr.add_argument("--viral", default="virais/viral_ref_01.mp4", help="Caminho do arquivo .mp4 viral")
    p_tr.add_argument(
        "--formato-destino",
        default="ugc_cozinha_selfie_24mm",
        choices=list(FORMATOS_VISUAIS_CATALOGO.keys()),
        help="Formato visual de destino para o transplante",
    )
    p_tr.add_argument("--objeto", default="", help="Override opcional do objeto em inglês (ex: 'a glass jar of pink salt')")
    p_tr.add_argument("--troca", default="", help="Trocas opcionais na copy (ex: 'baking soda=>pink salt|thighs=>tongue')")

    p_list = sub.add_parser("formatos", help="Lista todos os formatos visuais disponíveis para transplante")

    args = parser.parse_args()
    if args.comando == "formatos":
        print(json.dumps(FORMATOS_VISUAIS_CATALOGO, ensure_ascii=False, indent=2))
        return

    if args.comando == "assistir":
        reg = assistir_e_memorizar_viral(
            video_path=Path(args.viral),
            viral_id=args.id or None,
            formato_nome=args.formato or None,
        )
        resumo = {
            "status": "MEMORIZADO_COM_SUCESSO",
            "viral_id": reg["viral_id"],
            "formato_original": reg["formato_original"],
            "cortes_cena_detectados_s": reg["cortes_cena_detectados_s"],
            "metricas_ritmo": reg["metricas_ritmo"],
            "dna_verbal": reg["dna_verbal"],
            "metricas_opencv": reg["dna_visual"]["metricas_opencv"],
            "memoria_json": str(MEMORIA_VIRAIS_PATH),
            "nota_obsidian": reg.get("nota_obsidian", ""),
        }
        print(json.dumps(resumo, ensure_ascii=False, indent=2))
        return

    if args.comando == "transplantar":
        from forja.prompts import gerar_prompts_video

        v_path = Path(args.viral).resolve()
        analise_orig = analisar_viral(v_path)
        analise_transp = transplantar_formato_visual(
            analise_viral=analise_orig,
            formato_destino_id=args.formato_destino,
            objeto_override_en=args.objeto or None,
            troca_copy=args.troca or None,
        )
        roteiro = gerar_roteiro_takes(analise_transp, troca=args.troca or None)
        prompts_exemplo = gerar_prompts_video(analise_transp, roteiro, indice_variacao=0, usar_angulo=True)
        print(
            json.dumps(
                {
                    "status": "TRANSPLANTE_CONCLUIDO",
                    "formato_origem": analise_transp.get("formato_origem"),
                    "formato_destino": args.formato_destino,
                    "titulo_formato_visual": analise_transp.get("titulo_formato_visual"),
                    "cena_fixa_en": analise_transp.get("cena_fixa_en"),
                    "prompts_variacao_1": prompts_exemplo,
                },
                ensure_ascii=False,
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
