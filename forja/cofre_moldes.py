#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
COFRE IMUTÁVEL DE MOLDES HOMOLOGADOS (`forja/cofre_moldes.py`)
==============================================================
Gerenciador determinístico dos moldes homologados via Modo A (3 Pilotos Omni 1.2 Flash)
prontos para escala infinita no Modo B (Daemon JIT Zero-Token & Zero-Crédito em `:5255`).

Travas Cravadas pelo Operador no Schema Oficial do `manifest.json`:
1. ZERO Copy Padrão Fixa Injetada -> 100% fiel à copy literal do viral recente validada nos 3 pilotos Omni 1.2 Flash.
2. Realismo Oficial da Skill do Motor (`realismo-e-animacao-universal` Fusão Suprema V2 + `AD06` Física Biomecânica Causal + `lote-100-blindado` Clone Literal 1:1 da estética do viral, sem forçar paleta pastel).
3. Casting / Arquétipo 100% ditado pelo viral (`archetype_from_viral`: `male_clinician` | `female_presenter` | `duo_swap` | `hands_only_no_face`) + `SFace < 0.62` no `sface_global_registry.sqlite`.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import time
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
MOLDES_LOCAL_DIR = ROOT / "forja" / "moldes_homologados"
COFRE_DRIVE_DIR = Path(r"H:\Meu Drive\HUB CENTRAL OP ORGÂNICO\04_COFRE_IMUTAVEL_POR_FORMATO")
SFACE_DB_PATH = "C:/Hub001/sface_global_registry.sqlite"


DEFAULT_MOLDES_CATALOG: list[dict[str, Any]] = [
    {
        "molde_id": "US_WL_F37_C01_G00",
        "folder_cofre": "F37_BICARBONATO_LINGUA_2_ASIATICAS",
        "taxonomy_6_blocos": {
            "country": "US",
            "niche": "WL",
            "format": "F37",
            "copy": "C01",
            "hook": "G00",
            "default_batch": "L01",
        },
        "idioma": "EN",
        "ingrediente_ancora": "BAKING_SODA",
        "viral_source": {
            "ref_video_path": "H:/Meu Drive/HUB CENTRAL OP ORGÂNICO/03_VIRAIS_CONCORRENTES_SPY/VIRAIS_REFERENCIA_CLONADOS/REF_F37_LINGUA_2_JAPONESAS.mp4",
            "copy_literal_do_viral": True,
            "zero_frase_fixa_injetada": True,
            "cenas_dialogo_exato": [
                "Put a pinch of baking soda on your tongue like this, and watch your body drop stubborn belly fat overnight.",
                "It activates your natural fat-burning switch while you sleep: no strict diet, no gym, no rebounding.",
                "And the best part? You can make it right in your kitchen in thirty seconds with two simple ingredients.",
                "Comment yes below and tell me what city you're watching from so I can send you the exact step-by-step recipe right now.",
            ],
        },
        "motor_realismo_skill": {
            "skill_imagem": "realismo-e-animacao-universal (Fusao Suprema V2 - iPhone 24mm deep focus, zero fake bokeh, raw skin texture)",
            "skill_animacao": "AD06 Fisica Biomecanica Causal (11 blocos JSON, cadeia articular ombro->cotovelo->punho->mao)",
            "skill_lote": "lote-100-blindado (Pilotos Omni 1.2 Flash macaron_cookie_i2v_8s -> Escala veo_3_1_i2v_lite_low_priority 0 creditos)",
            "compartilhamento_frames_anti_3_braco": ["F1", "F1_SHARED", "F2", "F2_SHARED"],
            "pilot_matrices": [
                "C:/Hub001/MATRIZES_VIRAIS_1611/f37_lingua_2_japonesas/omni_pilot_001_s1_identity_masked.jpg",
                "C:/Hub001/MATRIZES_VIRAIS_1611/f37_lingua_2_japonesas/omni_pilot_002_s1_identity_masked.jpg",
                "C:/Hub001/MATRIZES_VIRAIS_1611/f37_lingua_2_japonesas/omni_pilot_003_s1_identity_masked.jpg",
                "C:/Hub001/MATRIZES_VIRAIS_1611/f37_lingua_2_japonesas/s3_womanB_bowl_clean.jpg",
            ],
        },
        "roleta_arquetipo_viral": {
            "archetype_from_viral": "duo_swap",
            "descricao_arquetipo": "Dupla de mulheres asiaticas 100% diferentes no mesmo video (Mulher A Cenas 1-2 com bicarbonato na lingua + Mulher B Cenas 3-4 com tigela de vidro na cozinha)",
            "unicidade_sface_db": SFACE_DB_PATH,
            "sface_max_cosine": 0.62,
            "pool_combinatorial_size": 480,
        },
        "whisper_qa_local_gpu": {
            "fidelidade_copy_viral": True,
            "anti_repeticao_bigrama": True,
            "corte_fonetico_exato_ms": True,
            "velocidade": 1.0,
        },
        "render_nvenc": {
            "codec": "h264_nvenc",
            "cq": 23,
            "bitrate": "2.4M",
            "maxrate": "3.4M",
            "estilo_legenda": "apenas_cta",
            "cta_visual_badge": "Comment \"YES\" below",
        },
        "script_runner": "scratch/forjar_f37_lingua_2_japonesas.py",
        "cofre_estoque_dir": "H:/Meu Drive/HUB CENTRAL OP ORGÂNICO/04_COFRE_IMUTAVEL_POR_FORMATO/F37_BICARBONATO_LINGUA_2_ASIATICAS",
    },
    {
        "molde_id": "US_WARM_F38_C01_G00",
        "folder_cofre": "F38_VELA_INFINITA_INGLES_E_ALEMAO/EN",
        "taxonomy_6_blocos": {
            "country": "US",
            "niche": "WARM",
            "format": "F38",
            "copy": "C01",
            "hook": "G00",
            "default_batch": "L01",
        },
        "idioma": "EN",
        "ingrediente_ancora": "DIY_INFINITE_CANDLE",
        "viral_source": {
            "ref_video_path": "H:/Meu Drive/HUB CENTRAL OP ORGÂNICO/03_VIRAIS_CONCORRENTES_SPY/VIRAIS_REFERENCIA_CLONADOS/REF_F38_VELA_INFINITA_AQUECIMENTO.mp4",
            "copy_literal_do_viral": True,
            "zero_frase_fixa_injetada": True,
            "cenas_dialogo_exato": [
                "Melt the bottom of a candle, stick it inside a glass, and pour water right up to the middle.",
                "Now add a layer of olive oil on top, light the wick, and this candle will burn for hours.",
            ],
        },
        "motor_realismo_skill": {
            "skill_imagem": "realismo-e-animacao-universal (Fusao Suprema V2 - POV tabletop 24mm deep focus, zero fake bokeh)",
            "skill_animacao": "AD06 Fisica Biomecanica Causal (11 blocos JSON, fisica real de agua, azeite e chama)",
            "skill_lote": "lote-100-blindado (Pilotos Omni 1.2 Flash -> Escala veo_3_1_i2v_lite_low_priority 0 creditos)",
            "compartilhamento_frames_anti_3_braco": ["F1", "F2"],
            "pilot_matrices": [
                "C:/Hub001/MATRIZES_VIRAIS_1611/f38_vela_infinita/omni_pilot_EN_001_f1.jpg",
                "C:/Hub001/MATRIZES_VIRAIS_1611/f38_vela_infinita/omni_pilot_EN_001_f2.jpg",
                "C:/Hub001/MATRIZES_VIRAIS_1611/f38_vela_infinita/omni_pilot_EN_002_f1.jpg",
                "C:/Hub001/MATRIZES_VIRAIS_1611/f38_vela_infinita/omni_pilot_EN_002_f2.jpg",
            ],
        },
        "roleta_arquetipo_viral": {
            "archetype_from_viral": "hands_only_no_face",
            "descricao_arquetipo": "Apenas maos reais manipulando vela, isqueiro, jarra de agua e azeite sobre bancada de madeira/pedra",
            "unicidade_sface_db": SFACE_DB_PATH,
            "sface_max_cosine": 0.62,
            "pool_combinatorial_size": 200,
        },
        "whisper_qa_local_gpu": {
            "fidelidade_copy_viral": True,
            "anti_repeticao_bigrama": True,
            "corte_fonetico_exato_ms": True,
            "velocidade": 1.0,
        },
        "render_nvenc": {
            "codec": "h264_nvenc",
            "cq": 23,
            "bitrate": "2.4M",
            "maxrate": "3.4M",
            "estilo_legenda": "sem_cta",
            "cta_visual_badge": "",
        },
        "script_runner": "scratch/forjar_f38_vela_infinita_ing_ale.py",
        "cofre_estoque_dir": "H:/Meu Drive/HUB CENTRAL OP ORGÂNICO/04_COFRE_IMUTAVEL_POR_FORMATO/F38_VELA_INFINITA_INGLES_E_ALEMAO/EN",
    },
    {
        "molde_id": "DE_WARM_F38_C01_G00",
        "folder_cofre": "F38_VELA_INFINITA_INGLES_E_ALEMAO/DE",
        "taxonomy_6_blocos": {
            "country": "DE",
            "niche": "WARM",
            "format": "F38",
            "copy": "C01",
            "hook": "G00",
            "default_batch": "L01",
        },
        "idioma": "DE",
        "ingrediente_ancora": "DIY_INFINITE_CANDLE_DE",
        "viral_source": {
            "ref_video_path": "H:/Meu Drive/HUB CENTRAL OP ORGÂNICO/03_VIRAIS_CONCORRENTES_SPY/VIRAIS_REFERENCIA_CLONADOS/REF_F38_VELA_INFINITA_AQUECIMENTO.mp4",
            "copy_literal_do_viral": True,
            "zero_frase_fixa_injetada": True,
            "cenas_dialogo_exato": [
                "Erhitze das Ende einer Kerze, stelle sie fest in ein Glas und gieße vorsichtig Wasser hinein.",
                "Gib jetzt etwas Olivenöl oben drauf, zünde den Docht an und die Kerze brennt stundenlang.",
            ],
        },
        "motor_realismo_skill": {
            "skill_imagem": "realismo-e-animacao-universal (Fusao Suprema V2 - POV tabletop 24mm deep focus, zero fake bokeh)",
            "skill_animacao": "AD06 Fisica Biomecanica Causal (11 blocos JSON, fisica real de agua, azeite e chama)",
            "skill_lote": "lote-100-blindado (Pilotos Omni 1.2 Flash -> Escala veo_3_1_i2v_lite_low_priority 0 creditos)",
            "compartilhamento_frames_anti_3_braco": ["F1", "F2"],
            "pilot_matrices": [
                "C:/Hub001/MATRIZES_VIRAIS_1611/f38_vela_infinita/omni_pilot_DE_001_f1.jpg",
                "C:/Hub001/MATRIZES_VIRAIS_1611/f38_vela_infinita/omni_pilot_DE_001_f2.jpg",
                "C:/Hub001/MATRIZES_VIRAIS_1611/f38_vela_infinita/omni_pilot_DE_002_f1.jpg",
                "C:/Hub001/MATRIZES_VIRAIS_1611/f38_vela_infinita/omni_pilot_DE_002_f2.jpg",
            ],
        },
        "roleta_arquetipo_viral": {
            "archetype_from_viral": "hands_only_no_face",
            "descricao_arquetipo": "Apenas maos reais manipulando vela, isqueiro, jarra de agua e azeite sobre bancada europeia de madeira/pedra",
            "unicidade_sface_db": SFACE_DB_PATH,
            "sface_max_cosine": 0.62,
            "pool_combinatorial_size": 200,
        },
        "whisper_qa_local_gpu": {
            "fidelidade_copy_viral": True,
            "anti_repeticao_bigrama": True,
            "corte_fonetico_exato_ms": True,
            "velocidade": 1.0,
        },
        "render_nvenc": {
            "codec": "h264_nvenc",
            "cq": 23,
            "bitrate": "2.4M",
            "maxrate": "3.4M",
            "estilo_legenda": "sem_cta",
            "cta_visual_badge": "",
        },
        "script_runner": "scratch/forjar_f38_vela_infinita_ing_ale.py",
        "cofre_estoque_dir": "H:/Meu Drive/HUB CENTRAL OP ORGÂNICO/04_COFRE_IMUTAVEL_POR_FORMATO/F38_VELA_INFINITA_INGLES_E_ALEMAO/DE",
    },
    {
        "molde_id": "US_WL_M01_C01_G00",
        "aliases_format": ["M01", "F31"],
        "folder_cofre": "F31_BATWINGS_V02_ENF_SEM_MANGA",
        "taxonomy_6_blocos": {
            "country": "US",
            "niche": "WL",
            "format": "M01",
            "copy": "C01",
            "hook": "G00",
            "default_batch": "L01",
        },
        "idioma": "EN",
        "ingrediente_ancora": "BAKING_SODA",
        "viral_source": {
            "ref_video_path": "H:/Meu Drive/HUB CENTRAL OP ORGÂNICO/03_VIRAIS_CONCORRENTES_SPY/VIRAIS_REFERENCIA_CLONADOS/REF_M01_BATWINGS_V02.mp4",
            "copy_literal_do_viral": True,
            "zero_frase_fixa_injetada": True,
            "cenas_dialogo_exato": [
                "Rub baking soda under your upper arm every night and watch hanging arm fat tighten while you sleep.",
                "Your underarm lymph nodes control how fast your upper body drains trapped fat cells.",
                "Now comment yes and where you're watching from so I can send you the exact step-by-step recipe.",
            ],
        },
        "motor_realismo_skill": {
            "skill_imagem": "realismo-e-animacao-universal (Fusao Suprema V2 - iPhone 24mm deep focus, zero fake bokeh)",
            "skill_animacao": "AD06 Fisica Biomecanica Causal (11 blocos JSON)",
            "skill_lote": "lote-100-blindado (Clone Literal 1:1 da estetica do viral)",
            "compartilhamento_frames_anti_3_braco": ["F1", "F1_SHARED", "F2", "F2_SHARED"],
            "pilot_matrices": ["C:/Hub001/MATRIZES_VIRAIS_1611/m01_batwings_v02/s1.jpg"],
        },
        "roleta_arquetipo_viral": {
            "archetype_from_viral": "female_presenter",
            "descricao_arquetipo": "Apresentadora mulher aplicando pasta de bicarbonato no braco (Batwings V02 Selfie)",
            "unicidade_sface_db": SFACE_DB_PATH,
            "sface_max_cosine": 0.62,
            "pool_combinatorial_size": 300,
        },
        "whisper_qa_local_gpu": {
            "fidelidade_copy_viral": True,
            "anti_repeticao_bigrama": True,
            "corte_fonetico_exato_ms": True,
            "velocidade": 1.0,
        },
        "render_nvenc": {
            "codec": "h264_nvenc",
            "cq": 23,
            "bitrate": "2.4M",
            "maxrate": "3.4M",
            "estilo_legenda": "apenas_cta",
            "cta_visual_badge": "Comment \"YES\" below",
        },
        "script_runner": "scratch/forjar_6_lotes_20_virais_1611.py",
        "cofre_estoque_dir": "H:/Meu Drive/HUB CENTRAL OP ORGÂNICO/04_COFRE_IMUTAVEL_POR_FORMATO/F31_BATWINGS_V02_ENF_SEM_MANGA",
    },
    {
        "molde_id": "US_WL_M02_C01_G00",
        "aliases_format": ["M02", "F32"],
        "folder_cofre": "F32_BATWINGS_V03_PINCH_SEM_MANGA",
        "taxonomy_6_blocos": {
            "country": "US",
            "niche": "WL",
            "format": "M02",
            "copy": "C01",
            "hook": "G00",
            "default_batch": "L01",
        },
        "idioma": "EN",
        "ingrediente_ancora": "BAKING_SODA",
        "viral_source": {
            "ref_video_path": "H:/Meu Drive/HUB CENTRAL OP ORGÂNICO/03_VIRAIS_CONCORRENTES_SPY/VIRAIS_REFERENCIA_CLONADOS/REF_M02_BATWINGS_V03.mp4",
            "copy_literal_do_viral": True,
            "zero_frase_fixa_injetada": True,
            "cenas_dialogo_exato": [
                "If your upper arm jiggles when you pinch it like this, rub baking soda right here before bed.",
                "It targets the stubborn arm pocket that regular workouts never reach.",
                "Comment yes and your city below so I can send you the exact nighttime recipe.",
            ],
        },
        "motor_realismo_skill": {
            "skill_imagem": "realismo-e-animacao-universal (Fusao Suprema V2)",
            "skill_animacao": "AD06 Fisica Biomecanica Causal",
            "skill_lote": "lote-100-blindado",
            "compartilhamento_frames_anti_3_braco": ["F1", "F1_SHARED", "F2", "F2_SHARED"],
            "pilot_matrices": ["C:/Hub001/MATRIZES_VIRAIS_1611/m02_batwings_v03/s1.jpg"],
        },
        "roleta_arquetipo_viral": {
            "archetype_from_viral": "female_presenter",
            "descricao_arquetipo": "Apresentadora mulher beliscando parte inferior do braco com pasta de bicarbonato (Batwings V03 Pinch)",
            "unicidade_sface_db": SFACE_DB_PATH,
            "sface_max_cosine": 0.62,
            "pool_combinatorial_size": 300,
        },
        "whisper_qa_local_gpu": {
            "fidelidade_copy_viral": True,
            "anti_repeticao_bigrama": True,
            "corte_fonetico_exato_ms": True,
            "velocidade": 1.0,
        },
        "render_nvenc": {
            "codec": "h264_nvenc",
            "cq": 23,
            "bitrate": "2.4M",
            "maxrate": "3.4M",
            "estilo_legenda": "apenas_cta",
            "cta_visual_badge": "Comment \"YES\" below",
        },
        "script_runner": "scratch/forjar_6_lotes_20_virais_1611.py",
        "cofre_estoque_dir": "H:/Meu Drive/HUB CENTRAL OP ORGÂNICO/04_COFRE_IMUTAVEL_POR_FORMATO/F32_BATWINGS_V03_PINCH_SEM_MANGA",
    },
    {
        "molde_id": "US_WL_M03_C01_G00",
        "aliases_format": ["M03", "F33"],
        "folder_cofre": "F33_PE_500K_PERTO_HOMEM_BRANCO",
        "taxonomy_6_blocos": {
            "country": "US",
            "niche": "WL",
            "format": "M03",
            "copy": "C01",
            "hook": "G00",
            "default_batch": "L01",
        },
        "idioma": "EN",
        "ingrediente_ancora": "BAKING_SODA",
        "viral_source": {
            "ref_video_path": "H:/Meu Drive/HUB CENTRAL OP ORGÂNICO/03_VIRAIS_CONCORRENTES_SPY/VIRAIS_REFERENCIA_CLONADOS/REF_M03_PE_500K.mp4",
            "copy_literal_do_viral": True,
            "zero_frase_fixa_injetada": True,
            "cenas_dialogo_exato": [
                "Press this exact spot on the top of your foot with baking soda paste before you go to sleep.",
                "It stimulates the metabolic nerve pathway connected directly to your midsection.",
                "Comment yes below so I can send you the exact routine.",
            ],
        },
        "motor_realismo_skill": {
            "skill_imagem": "realismo-e-animacao-universal (Fusao Suprema V2)",
            "skill_animacao": "AD06 Fisica Biomecanica Causal",
            "skill_lote": "lote-100-blindado",
            "compartilhamento_frames_anti_3_braco": ["F1", "F1_SHARED", "F2", "F2_SHARED"],
            "pilot_matrices": ["C:/Hub001/MATRIZES_VIRAIS_1611/m03_pe_500k/s1.jpg"],
        },
        "roleta_arquetipo_viral": {
            "archetype_from_viral": "male_clinician",
            "descricao_arquetipo": "Clinico/especialista homem demonstrando ponto anatomico no dorso do pe com pasta de bicarbonato",
            "unicidade_sface_db": SFACE_DB_PATH,
            "sface_max_cosine": 0.62,
            "pool_combinatorial_size": 300,
        },
        "whisper_qa_local_gpu": {
            "fidelidade_copy_viral": True,
            "anti_repeticao_bigrama": True,
            "corte_fonetico_exato_ms": True,
            "velocidade": 1.0,
        },
        "render_nvenc": {
            "codec": "h264_nvenc",
            "cq": 23,
            "bitrate": "2.4M",
            "maxrate": "3.4M",
            "estilo_legenda": "apenas_cta",
            "cta_visual_badge": "Comment \"YES\" below",
        },
        "script_runner": "scratch/forjar_6_lotes_20_virais_1611.py",
        "cofre_estoque_dir": "H:/Meu Drive/HUB CENTRAL OP ORGÂNICO/04_COFRE_IMUTAVEL_POR_FORMATO/F33_PE_500K_PERTO_HOMEM_BRANCO",
    },
    {
        "molde_id": "US_WL_M04_C01_G00",
        "aliases_format": ["M04", "F21"],
        "folder_cofre": "F21_LIVER1_PE_PISO_MADEIRA",
        "taxonomy_6_blocos": {
            "country": "US",
            "niche": "WL",
            "format": "M04",
            "copy": "C01",
            "hook": "G00",
            "default_batch": "L01",
        },
        "idioma": "EN",
        "ingrediente_ancora": "BAKING_SODA",
        "viral_source": {
            "ref_video_path": "H:/Meu Drive/HUB CENTRAL OP ORGÂNICO/03_VIRAIS_CONCORRENTES_SPY/VIRAIS_REFERENCIA_CLONADOS/REF_M04_LIVER1_PE.mp4",
            "copy_literal_do_viral": True,
            "zero_frase_fixa_injetada": True,
            "cenas_dialogo_exato": [
                "Right between your big toe and second toe sits the Liver 1 point that unlocks overnight fat burning.",
                "Apply a warm baking soda paste right here for two minutes before bed.",
                "Comment yes below and I will send you the full step-by-step guide.",
            ],
        },
        "motor_realismo_skill": {
            "skill_imagem": "realismo-e-animacao-universal (Fusao Suprema V2)",
            "skill_animacao": "AD06 Fisica Biomecanica Causal",
            "skill_lote": "lote-100-blindado",
            "compartilhamento_frames_anti_3_braco": ["F1", "F1_SHARED", "F2", "F2_SHARED"],
            "pilot_matrices": ["C:/Hub001/MATRIZES_VIRAIS_1611/m04_liver1_pe/s1.jpg"],
        },
        "roleta_arquetipo_viral": {
            "archetype_from_viral": "male_clinician",
            "descricao_arquetipo": "Clinico homem demonstrando ponto Liver 1 no pe sobre piso de madeira real",
            "unicidade_sface_db": SFACE_DB_PATH,
            "sface_max_cosine": 0.62,
            "pool_combinatorial_size": 300,
        },
        "whisper_qa_local_gpu": {
            "fidelidade_copy_viral": True,
            "anti_repeticao_bigrama": True,
            "corte_fonetico_exato_ms": True,
            "velocidade": 1.0,
        },
        "render_nvenc": {
            "codec": "h264_nvenc",
            "cq": 23,
            "bitrate": "2.4M",
            "maxrate": "3.4M",
            "estilo_legenda": "apenas_cta",
            "cta_visual_badge": "Comment \"YES\" below",
        },
        "script_runner": "scratch/forjar_6_lotes_20_virais_1611.py",
        "cofre_estoque_dir": "H:/Meu Drive/HUB CENTRAL OP ORGÂNICO/04_COFRE_IMUTAVEL_POR_FORMATO/F21_LIVER1_PE_PISO_MADEIRA",
    },
    {
        "molde_id": "US_WL_M05_C01_G00",
        "aliases_format": ["M05", "F35"],
        "folder_cofre": "F35_COXA_INTERNA_MANEQUIM",
        "taxonomy_6_blocos": {
            "country": "US",
            "niche": "WL",
            "format": "M05",
            "copy": "C01",
            "hook": "G00",
            "default_batch": "L01",
        },
        "idioma": "EN",
        "ingrediente_ancora": "BAKING_SODA",
        "viral_source": {
            "ref_video_path": "H:/Meu Drive/HUB CENTRAL OP ORGÂNICO/03_VIRAIS_CONCORRENTES_SPY/VIRAIS_REFERENCIA_CLONADOS/REF_M05_COXA_INTERNA.mp4",
            "copy_literal_do_viral": True,
            "zero_frase_fixa_injetada": True,
            "cenas_dialogo_exato": [
                "Rubbing baking soda paste along the inner thigh drainage line targets stubborn lower-body fat while you sleep.",
                "Look at how this anatomical pathway connects directly to your pelvic lymph nodes.",
                "Comment yes below so I can send you the exact nighttime preparation.",
            ],
        },
        "motor_realismo_skill": {
            "skill_imagem": "realismo-e-animacao-universal (Fusao Suprema V2)",
            "skill_animacao": "AD06 Fisica Biomecanica Causal",
            "skill_lote": "lote-100-blindado",
            "compartilhamento_frames_anti_3_braco": ["F1", "F1_SHARED", "F2", "F2_SHARED"],
            "pilot_matrices": ["C:/Hub001/MATRIZES_VIRAIS_1611/m05_coxa_interna/s1.jpg"],
        },
        "roleta_arquetipo_viral": {
            "archetype_from_viral": "male_clinician",
            "descricao_arquetipo": "Clinico homem manipulando manequim anatomico de coxa interna e pasta de bicarbonato",
            "unicidade_sface_db": SFACE_DB_PATH,
            "sface_max_cosine": 0.62,
            "pool_combinatorial_size": 300,
        },
        "whisper_qa_local_gpu": {
            "fidelidade_copy_viral": True,
            "anti_repeticao_bigrama": True,
            "corte_fonetico_exato_ms": True,
            "velocidade": 1.0,
        },
        "render_nvenc": {
            "codec": "h264_nvenc",
            "cq": 23,
            "bitrate": "2.4M",
            "maxrate": "3.4M",
            "estilo_legenda": "apenas_cta",
            "cta_visual_badge": "Comment \"YES\" below",
        },
        "script_runner": "scratch/forjar_6_lotes_20_virais_1611.py",
        "cofre_estoque_dir": "H:/Meu Drive/HUB CENTRAL OP ORGÂNICO/04_COFRE_IMUTAVEL_POR_FORMATO/F35_COXA_INTERNA_MANEQUIM",
    },
    {
        "molde_id": "US_WL_M06_C01_G00",
        "aliases_format": ["M06", "F36"],
        "folder_cofre": "F36_MACA_CLINICA_2PES_325K",
        "taxonomy_6_blocos": {
            "country": "US",
            "niche": "WL",
            "format": "M06",
            "copy": "C01",
            "hook": "G00",
            "default_batch": "L01",
        },
        "idioma": "EN",
        "ingrediente_ancora": "BAKING_SODA",
        "viral_source": {
            "ref_video_path": "H:/Meu Drive/HUB CENTRAL OP ORGÂNICO/03_VIRAIS_CONCORRENTES_SPY/VIRAIS_REFERENCIA_CLONADOS/REF_M06_MACA_325K.mp4",
            "copy_literal_do_viral": True,
            "zero_frase_fixa_injetada": True,
            "cenas_dialogo_exato": [
                "Apply baking soda paste right here on your lower abdomen while lying flat before sleep.",
                "This position lets the active mineral compound stimulate deep visceral fat release overnight.",
                "Comment yes below and tell me where you're watching from so I can send you the recipe.",
            ],
        },
        "motor_realismo_skill": {
            "skill_imagem": "realismo-e-animacao-universal (Fusao Suprema V2)",
            "skill_animacao": "AD06 Fisica Biomecanica Causal",
            "skill_lote": "lote-100-blindado",
            "compartilhamento_frames_anti_3_braco": ["F1", "F1_SHARED", "F2", "F2_SHARED"],
            "pilot_matrices": ["C:/Hub001/MATRIZES_VIRAIS_1611/m06_maca_325k/s1.jpg"],
        },
        "roleta_arquetipo_viral": {
            "archetype_from_viral": "female_presenter",
            "descricao_arquetipo": "Apresentadora mulher em maca clinica demonstrando aplicacao abdominal (Maca 325k)",
            "unicidade_sface_db": SFACE_DB_PATH,
            "sface_max_cosine": 0.62,
            "pool_combinatorial_size": 300,
        },
        "whisper_qa_local_gpu": {
            "fidelidade_copy_viral": True,
            "anti_repeticao_bigrama": True,
            "corte_fonetico_exato_ms": True,
            "velocidade": 1.0,
        },
        "render_nvenc": {
            "codec": "h264_nvenc",
            "cq": 23,
            "bitrate": "2.4M",
            "maxrate": "3.4M",
            "estilo_legenda": "apenas_cta",
            "cta_visual_badge": "Comment \"YES\" below",
        },
        "script_runner": "scratch/forjar_6_lotes_20_virais_1611.py",
        "cofre_estoque_dir": "H:/Meu Drive/HUB CENTRAL OP ORGÂNICO/04_COFRE_IMUTAVEL_POR_FORMATO/F36_MACA_CLINICA_2PES_325K",
    },
]


def sincronizar_moldes_padrao() -> list[dict[str, Any]]:
    """Garante que todos os moldes homologados tenham `manifest.json` gravado local e no Cofre do Drive."""
    MOLDES_LOCAL_DIR.mkdir(parents=True, exist_ok=True)
    registrados: list[dict[str, Any]] = []
    for m in DEFAULT_MOLDES_CATALOG:
        mid = m["molde_id"]
        m_copy = dict(m)
        m_copy["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        # Conta estoque atual no Cofre se existir
        estoque_path = Path(m_copy.get("cofre_estoque_dir") or "")
        mp4_count = len(list(estoque_path.glob("*.mp4"))) if estoque_path.exists() else 0
        m_copy["cofre_mp4_ready_count"] = mp4_count

        # 1) Salva em forja/moldes_homologados/<MOLDE_ID>/manifest.json
        local_dir = MOLDES_LOCAL_DIR / mid
        local_dir.mkdir(parents=True, exist_ok=True)
        local_manifest = local_dir / "manifest.json"
        local_manifest.write_text(json.dumps(m_copy, indent=2, ensure_ascii=False), encoding="utf-8")

        # 2) Espelha em H:\Meu Drive\HUB CENTRAL OP ORGÂNICO\04_COFRE_IMUTAVEL_POR_FORMATO\<folder_cofre>\manifest.json
        if COFRE_DRIVE_DIR.exists():
            drive_sub = COFRE_DRIVE_DIR / m["folder_cofre"]
            try:
                drive_sub.mkdir(parents=True, exist_ok=True)
                (drive_sub / "manifest.json").write_text(json.dumps(m_copy, indent=2, ensure_ascii=False), encoding="utf-8")
            except Exception:
                pass

        registrados.append(m_copy)
    return registrados


def listar_moldes_homologados() -> list[dict[str, Any]]:
    if not MOLDES_LOCAL_DIR.exists() or not list(MOLDES_LOCAL_DIR.glob("*/manifest.json")):
        return sincronizar_moldes_padrao()
    out: list[dict[str, Any]] = []
    for mf in sorted(MOLDES_LOCAL_DIR.glob("*/manifest.json")):
        try:
            d = json.loads(mf.read_text(encoding="utf-8"))
            estoque_path = Path(d.get("cofre_estoque_dir") or "")
            d["cofre_mp4_ready_count"] = len(list(estoque_path.glob("*.mp4"))) if estoque_path.exists() else 0
            out.append(d)
        except Exception:
            continue
    return out


def resolver_molde_por_dna(dna: dict[str, Any]) -> dict[str, Any] | None:
    """Resolve um `manifest.json` pelo DNA `{ country, niche, format, copy, hook }` ou pelo `format`."""
    moldes = listar_moldes_homologados()
    country = str(dna.get("country") or "US").upper()
    niche = str(dna.get("niche") or "WL").upper()
    fmt = str(dna.get("format") or "").upper()
    copy_code = str(dna.get("copy") or "C01").upper()
    hook_code = str(dna.get("hook") or "G00").upper()

    exact_id = f"{country}_{niche}_{fmt}_{copy_code}_{hook_code}"
    for m in moldes:
        if str(m.get("molde_id") or "").upper() == exact_id:
            return m
    # Fallback por country + format (incluindo aliases_format ex: F31..F36)
    for m in moldes:
        tx = m.get("taxonomy_6_blocos") or {}
        aliases = [str(a).upper() for a in (m.get("aliases_format") or [])]
        if str(tx.get("country") or "").upper() == country and (str(tx.get("format") or "").upper() == fmt or fmt in aliases):
            return m
    # Fallback apenas por format (ex: F37, F38, M01..M06, F31..F36)
    for m in moldes:
        tx = m.get("taxonomy_6_blocos") or {}
        aliases = [str(a).upper() for a in (m.get("aliases_format") or [])]
        if str(tx.get("format") or "").upper() == fmt or fmt in aliases:
            return m
    return None


def registrar_novo_molde_cli(args: argparse.Namespace) -> dict[str, Any]:
    MOLDES_LOCAL_DIR.mkdir(parents=True, exist_ok=True)
    country = args.country.upper()
    niche = args.niche.upper()
    fmt = args.format.upper()
    copy_code = args.copy.upper()
    hook_code = args.hook.upper()
    molde_id = f"{country}_{niche}_{fmt}_{copy_code}_{hook_code}"
    cenas = [c.strip() for c in (args.dialogo or "").split("|") if c.strip()]
    matrizes = [m.strip() for m in (args.matrizes or "").split(",") if m.strip()]
    folder_cofre = args.folder_cofre or f"{fmt}_{niche}_{country}"
    cofre_dir = str((COFRE_DRIVE_DIR / folder_cofre).as_posix())

    novo = {
        "molde_id": molde_id,
        "folder_cofre": folder_cofre,
        "taxonomy_6_blocos": {
            "country": country,
            "niche": niche,
            "format": fmt,
            "copy": copy_code,
            "hook": hook_code,
            "default_batch": "L01",
        },
        "idioma": args.idioma.upper(),
        "ingrediente_ancora": args.ingrediente.upper(),
        "viral_source": {
            "ref_video_path": args.ref_video or "",
            "copy_literal_do_viral": True,
            "zero_frase_fixa_injetada": True,
            "cenas_dialogo_exato": cenas,
        },
        "motor_realismo_skill": {
            "skill_imagem": "realismo-e-animacao-universal (Fusao Suprema V2 - iPhone 24mm deep focus, zero fake bokeh, raw skin texture)",
            "skill_animacao": "AD06 Fisica Biomecanica Causal (11 blocos JSON)",
            "skill_lote": "lote-100-blindado (Pilotos Omni 1.2 Flash -> Escala veo_3_1_i2v_lite_low_priority 0 creditos)",
            "compartilhamento_frames_anti_3_braco": ["F1", "F1_SHARED", "F2", "F2_SHARED"],
            "pilot_matrices": matrizes,
        },
        "roleta_arquetipo_viral": {
            "archetype_from_viral": args.archetype,
            "descricao_arquetipo": f"Arquetipo fiel ao viral ({args.archetype})",
            "unicidade_sface_db": SFACE_DB_PATH,
            "sface_max_cosine": 0.62,
            "pool_combinatorial_size": 300,
        },
        "whisper_qa_local_gpu": {
            "fidelidade_copy_viral": True,
            "anti_repeticao_bigrama": True,
            "corte_fonetico_exato_ms": True,
            "velocidade": 1.0,
        },
        "render_nvenc": {
            "codec": "h264_nvenc",
            "cq": 23,
            "bitrate": "2.4M",
            "maxrate": "3.4M",
            "estilo_legenda": "apenas_cta" if args.cta_badge else "sem_cta",
            "cta_visual_badge": args.cta_badge or "",
        },
        "script_runner": args.script_runner or "",
        "cofre_estoque_dir": cofre_dir,
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    local_dir = MOLDES_LOCAL_DIR / molde_id
    local_dir.mkdir(parents=True, exist_ok=True)
    (local_dir / "manifest.json").write_text(json.dumps(novo, indent=2, ensure_ascii=False), encoding="utf-8")
    if COFRE_DRIVE_DIR.exists():
        d_sub = COFRE_DRIVE_DIR / folder_cofre
        d_sub.mkdir(parents=True, exist_ok=True)
        (d_sub / "manifest.json").write_text(json.dumps(novo, indent=2, ensure_ascii=False), encoding="utf-8")
    return novo


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Gerenciador do Cofre Imutável de Moldes Homologados")
    ap.add_argument("--sincronizar", action="store_true", help="Sincroniza os 8 moldes homologados atuais")
    ap.add_argument("--listar", action="store_true", help="Lista todos os moldes homologados")
    ap.add_argument("--registrar-molde", action="store_true", help="Registra novo molde homologado após 3 pilotos Omni")
    ap.add_argument("--country", default="US")
    ap.add_argument("--niche", default="WL")
    ap.add_argument("--format", default="F39")
    ap.add_argument("--copy", default="C01")
    ap.add_argument("--hook", default="G00")
    ap.add_argument("--idioma", default="EN")
    ap.add_argument("--ingrediente", default="BAKING_SODA")
    ap.add_argument("--archetype", default="female_presenter", choices=["male_clinician", "female_presenter", "duo_swap", "hands_only_no_face"])
    ap.add_argument("--dialogo", default="", help="Frases das cenas separadas por |")
    ap.add_argument("--matrizes", default="", help="Paths das matrizes dos pilotos Omni separados por virgula")
    ap.add_argument("--ref-video", default="")
    ap.add_argument("--folder-cofre", default="")
    ap.add_argument("--cta-badge", default='Comment "YES" below')
    ap.add_argument("--script-runner", default="")
    ns = ap.parse_args()

    if ns.registrar_molde:
        res = registrar_novo_molde_cli(ns)
        print(json.dumps({"ok": True, "molde_registrado": res["molde_id"]}, indent=2, ensure_ascii=False))
    elif ns.listar:
        ms = listar_moldes_homologados()
        print(json.dumps({"ok": True, "total": len(ms), "moldes": [m["molde_id"] for m in ms]}, indent=2, ensure_ascii=False))
    else:
        ms = sincronizar_moldes_padrao()
        print(json.dumps({"ok": True, "sincronizados": len(ms), "moldes": [{"id": m["molde_id"], "cofre_mp4": m["cofre_mp4_ready_count"]} for m in ms]}, indent=2, ensure_ascii=False))
