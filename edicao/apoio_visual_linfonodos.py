"""
Motor de Adaptação Visual de Nódulos Linfáticos, GLP-1 Caseiro e Antes/Depois (Aula 21/10/2026).

Atende integralmente as diretrizes da aula e do usuário:
1. Combina ativos VISUAIS CRIADOS DO ZERO (Raio-X 3D de linfonodos inguinais/virilha, retroauriculares/pescoço,
   axilares, corpo 3D com gordura amarela derretendo, comparativo Homemade GLP-1 vs Mounjaro e Antes/Depois)
   com diagramas médicos reais do Google/Wikimedia.
2. Posicionamento variado na tela 9:16 (1080x1920), com foco no MEIO DA TELA (centralizado) e variações reais:
   - `meio_da_tela_centralizado`: Card médico/3D centralizado no meio da tela (`x=(W-w)/2:y=560`, `620x540`).
   - `meio_da_tela_destaque_grande`: Card amplo centralizado no meio da tela (`x=(W-w)/2:y=480`, `720x620`).
   - `quadro6_3d_meio_apresentador_canto`: Estilo Quadro 6 da aula (Corpo 3D Raio-X com gordura derretendo e
     linfonodos brilhando no centro/tela cheia + personagem falando no canto inferior direito + legenda no meio).
   - `canto_esquerdo_medio`: Posicionado à esquerda na altura média (`x=36:y=440`, `460x460`).
   - `canto_direito_alto`: Posicionado no canto superior direito (`x=W-w-36:y=240`, `460x460`).
   - `split_superior_central`: Divisão superior centralizada estilo L13-009 (`x=(W-w)/2:y=90`, `680x520`).
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from forja.estrutura import ROOT_DIR

ASSETS_CRIADOS_DIR = ROOT_DIR / "virais" / "assets_21_10" / "criados_do_zero"
ASSETS_GOOGLE_DIR = ROOT_DIR / "virais" / "assets_21_10" / "google_lymph_nodes"
ASSETS_AULA_DIR = ROOT_DIR / "virais" / "assets_21_10"

# Catálogo de ativos por formato/mecanismo (mesclando imagens criadas do zero + Google/Wikimedia)
CATALOGO_ATIVOS_POR_TEMA: dict[str, list[Path]] = {
    "groin_virilha": [
        ASSETS_CRIADOS_DIR / "linfonodos_virilha_inguinal_3d.jpg",
        ASSETS_CRIADOS_DIR / "corpo_3d_gordura_derretendo_linfonodos.jpg",
        ASSETS_GOOGLE_DIR / "google_body_lymph_nodes_machado.jpg",
        ASSETS_GOOGLE_DIR / "wiki_lymphatic_system_1.png",
    ],
    "ears_neck_pescoco": [
        ASSETS_CRIADOS_DIR / "linfonodos_pescoco_orelha_3d.jpg",
        ASSETS_GOOGLE_DIR / "wiki_head_neck_lymph_1.png",
        ASSETS_GOOGLE_DIR / "wiki_head_neck_lymph_2.png",
        ASSETS_CRIADOS_DIR / "corpo_3d_gordura_derretendo_linfonodos.jpg",
    ],
    "armpits_axila": [
        ASSETS_CRIADOS_DIR / "linfonodos_axila_anatomia_criado.jpg",
        ASSETS_GOOGLE_DIR / "google_axillary_cleveland_clinic.jpg",
        ASSETS_AULA_DIR / "apoio_linfonodo_axila_01.jpg",
        ASSETS_CRIADOS_DIR / "corpo_3d_gordura_derretendo_linfonodos.jpg",
    ],
    "glp1_mounjaro": [
        ASSETS_CRIADOS_DIR / "apoio_homemade_glp1_vs_mounjaro.jpg",
        ASSETS_CRIADOS_DIR / "antes_depois_paciente_susan_45.jpg",
        ASSETS_CRIADOS_DIR / "corpo_3d_gordura_derretendo_linfonodos.jpg",
        ASSETS_GOOGLE_DIR / "google_before_after_woman_1.jpg",
    ],
    "before_after_susan": [
        ASSETS_CRIADOS_DIR / "antes_depois_paciente_susan_45.jpg",
        ASSETS_GOOGLE_DIR / "google_before_after_woman_1.jpg",
        ASSETS_GOOGLE_DIR / "google_before_after_woman_2.jpg",
        ASSETS_AULA_DIR / "apoio_antes_depois_01.jpg",
    ],
}

LAYOUTS_POSICIONAMENTO = [
    "meio_da_tela_centralizado",
    "meio_da_tela_destaque_grande",
    "quadro6_3d_meio_apresentador_canto",
    "canto_esquerdo_medio",
    "canto_direito_alto",
    "split_superior_central",
]


def detectar_tema_visual(formato: str, texto_copy: str = "") -> str:
    txt = f"{formato} {texto_copy}".lower()
    if any(k in txt for k in ("groin", "virilha", "inguinal", "thigh", "coxa")):
        return "groin_virilha"
    if any(k in txt for k in ("ear", "orelha", "neck", "pesco", "cervical")):
        return "ears_neck_pescoco"
    if any(k in txt for k in ("armpit", "axila", "under your arm", "axillary")):
        return "armpits_axila"
    if any(k in txt for k in ("susan", "before", "antes", "45 pounds", "photo")):
        return "before_after_susan"
    if any(k in txt for k in ("glp", "mounjaro", "ozempic", "spoon")):
        return "glp1_mounjaro"
    return "groin_virilha"


def escolher_ativo_e_layout(formato: str, texto_copy: str = "", indice_variacao: int = 0) -> tuple[Path, str]:
    tema = detectar_tema_visual(formato, texto_copy)
    candidatos = [p for p in CATALOGO_ATIVOS_POR_TEMA.get(tema, []) if p.is_file()]
    if not candidatos:
        candidatos = [p for lista in CATALOGO_ATIVOS_POR_TEMA.values() for p in lista if p.is_file()]
    ativo = candidatos[indice_variacao % len(candidatos)]
    layout = LAYOUTS_POSICIONAMENTO[indice_variacao % len(LAYOUTS_POSICIONAMENTO)]
    return ativo, layout


def aplicar_apoio_visual_variado(
    video_entrada: Path,
    video_saida: Path,
    imagem_apoio: Path,
    layout: str = "meio_da_tela_centralizado",
    inicio_s: float = 0.0,
    fim_s: float | None = None,
    crf: int = 20,
) -> dict[str, Any]:
    """
    Aplica o elemento visual (nódulos linfáticos 3D/Google, comparativo GLP-1 ou Antes/Depois)
    no layout especificado (incluindo NO MEIO DA TELA ou estilo Quadro 6 3D + PIP).
    """
    video_saida.parent.mkdir(parents=True, exist_ok=True)
    enable_expr = f"between(t,{inicio_s:.2f},{fim_s:.2f})" if fim_s is not None else f"gte(t,{inicio_s:.2f})"

    if layout == "quadro6_3d_meio_apresentador_canto":
        # Estilo Quadro 6 da aula: Imagem 3D Raio-X preenche a tela central (1080x1920) e o apresentador
        # fica em Picture-in-Picture dinâmico no canto inferior direito (x=610, y=1150, 434x730)
        filtro = (
            f"[1:v]scale=1080:1920:force_original_aspect_ratio=increase,"
            f"crop=1080:1920,setsar=1[bg3d];"
            f"[0:v]scale=434:730:force_original_aspect_ratio=increase,"
            f"crop=434:730, pad=446:742:6:6:color=white@0.92[pip];"
            f"[0:v][bg3d]overlay=0:0:enable='{enable_expr}'[base];"
            f"[base][pip]overlay=x=W-w-32:y=H-h-48:enable='{enable_expr}'[vout]"
        )
    elif layout == "meio_da_tela_destaque_grande":
        # Reenquadra sem faixa preta e coloca o card GRANDE BEM NO MEIO DA TELA (y=750) abaixo do queixo
        filtro = (
            f"[0:v]scale=1180:2098:force_original_aspect_ratio=increase,crop=1080:1920:50:178[base_up];"
            f"[1:v]scale=620:520:force_original_aspect_ratio=decrease,"
            f"pad=iw+16:ih+16:8:8:color=0x00E5FF@0.95[ov];"
            f"[0:v][base_up]overlay=0:0:enable='{enable_expr}'[v_shift];"
            f"[v_shift][ov]overlay=x=(W-w)/2:y=750:enable='{enable_expr}'[vout]"
        )
    elif layout == "split_superior_central":
        # Estilo L13-009 sem faixa preta: Imagem médica grande no topo-centro (y=48) e personagem mais abaixo
        filtro = (
            f"[0:v]scale=1180:2098:force_original_aspect_ratio=increase,crop=1080:1920:50:0[base_down];"
            f"[1:v]scale=640:480:force_original_aspect_ratio=decrease,"
            f"pad=iw+16:ih+16:8:8:color=white@0.95[ov];"
            f"[0:v][base_down]overlay=0:0:enable='{enable_expr}'[v_shift];"
            f"[v_shift][ov]overlay=x=(W-w)/2:y=48:enable='{enable_expr}'[vout]"
        )
    elif layout == "canto_esquerdo_medio":
        # Card à esquerda na altura média-central (x=32, y=750 - abaixo do queixo, sem borda lateral sobrando)
        filtro = (
            f"[1:v]scale=460:460:force_original_aspect_ratio=decrease,"
            f"pad=iw+14:ih+14:7:7:color=0x00E5FF@0.95[ov];"
            f"[0:v][ov]overlay=x=32:y=750:enable='{enable_expr}'[vout]"
        )
    elif layout == "canto_direito_alto":
        # Card à direita na altura média-central (x=W-w-32, y=750 - abaixo do queixo, sem borda lateral sobrando)
        filtro = (
            f"[1:v]scale=460:460:force_original_aspect_ratio=decrease,"
            f"pad=iw+14:ih+14:7:7:color=white@0.95[ov];"
            f"[0:v][ov]overlay=x=W-w-32:y=750:enable='{enable_expr}'[vout]"
        )
    else:
        # Padrão: meio_da_tela_centralizado -> BEM NO MEIO DA TELA (x=(W-w)/2, y=760) com rosto 100% livre acima!
        filtro = (
            f"[0:v]scale=1180:2098:force_original_aspect_ratio=increase,crop=1080:1920:50:178[base_up];"
            f"[1:v]scale=560:490:force_original_aspect_ratio=decrease,"
            f"pad=iw+16:ih+16:8:8:color=white@0.95[ov];"
            f"[0:v][base_up]overlay=0:0:enable='{enable_expr}'[v_shift];"
            f"[v_shift][ov]overlay=x=(W-w)/2:y=760:enable='{enable_expr}'[vout]"
        )

    cmd_nvenc = [
        "ffmpeg",
        "-nostdin",
        "-y",
        "-loglevel",
        "error",
        "-i",
        str(video_entrada),
        "-loop",
        "1",
        "-t",
        "30",
        "-i",
        str(imagem_apoio),
        "-filter_complex",
        filtro,
        "-map",
        "[vout]",
        "-map",
        "0:a",
        "-shortest",
        "-c:v",
        "h264_nvenc",
        "-preset",
        "p2",
        "-cq",
        str(crf),
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "copy",
        "-movflags",
        "+faststart",
        str(video_saida),
    ]
    if subprocess.run(cmd_nvenc).returncode != 0:
        cmd_cpu = [
            "ffmpeg",
            "-nostdin",
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(video_entrada),
            "-loop",
            "1",
            "-t",
            "30",
            "-i",
            str(imagem_apoio),
            "-filter_complex",
            filtro,
            "-map",
            "[vout]",
            "-map",
            "0:a",
            "-shortest",
            "-c:v",
            "libx264",
            "-crf",
            str(crf),
            "-preset",
            "veryfast",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "copy",
            "-movflags",
            "+faststart",
            str(video_saida),
        ]
        subprocess.run(cmd_cpu, check=True)

    return {
        "video_saida": str(video_saida),
        "imagem_apoio": str(imagem_apoio),
        "layout": layout,
    }
