"""
Edição — Etapa 5: CTA.
Regras:
- No último take: caixa amarela arredondada com contorno preto e o texto do CTA (ex.: "COMMENT YES") com ícone ▶.
- Animação de PULO leve: sobe e desce ~25–30 px, ~1,4 vez por segundo (y = -28*|sin(2π·1,4·t)|),
  desde o início do último take até o fim.
- Se o clipe já trouxer o CTA gravado, não sobreponha.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from forja.ler_viral import extrair_frame, obter_duracao_video


def _carregar_fonte_cta(tamanho: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    root_dir = Path(__file__).resolve().parent.parent
    candidatas = [
        root_dir / "Montserrat-Black.ttf",
        root_dir / "Montserrat-ExtraBold.ttf",
        Path(r"C:\Windows\Fonts\ariblk.ttf"),
        Path(r"C:\Windows\Fonts\impact.ttf"),
    ]
    for c in candidatas:
        if c.is_file():
            try:
                return ImageFont.truetype(str(c), tamanho)
            except Exception:
                continue
    return ImageFont.load_default()


def gerar_badge_cta_png(
    texto_cta: str,
    destino_png: Path,
    cor_caixa: tuple[int, int, int, int] = (255, 230, 0, 255),
    cor_borda: tuple[int, int, int, int] = (0, 0, 0, 255),
    cor_texto: tuple[int, int, int, int] = (0, 0, 0, 255),
) -> Path:
    """
    Gera um PNG transparente em alta definição (supersampling 2x) contendo:
    - Caixa amarela arredondada (#FFE600) com contorno preto sólido grosso e sombra suave;
    - Ícone vetorial ▶ perfeito à esquerda + texto do CTA (ex: "COMMENT YES").
    """
    destino_png.parent.mkdir(parents=True, exist_ok=True)
    texto_limpo = texto_cta.replace("▶", "").strip().upper() or "COMMENT YES"

    # Desenha em escala 2x e reduz com LANCZOS para bordas perfeitamente suaves
    escala = 2
    fonte = _carregar_fonte_cta(54 * escala)

    dummy = Image.new("RGBA", (10, 10), (0, 0, 0, 0))
    d_dummy = ImageDraw.Draw(dummy)
    bbox = d_dummy.textbbox((0, 0), texto_limpo, font=fonte)
    largura_txt = bbox[2] - bbox[0]
    altura_txt = bbox[3] - bbox[1]

    tam_icone = 44 * escala
    espaco_icone_txt = 24 * escala
    pad_x = 46 * escala
    pad_y = 28 * escala
    borda_px = 7 * escala
    sombra_offset = 6 * escala

    largura_caixa = pad_x * 2 + tam_icone + espaco_icone_txt + largura_txt
    altura_caixa = pad_y * 2 + max(altura_txt, tam_icone)

    largura_canvas = largura_caixa + borda_px * 2 + sombra_offset + 8
    altura_canvas = altura_caixa + borda_px * 2 + sombra_offset + 8

    img = Image.new("RGBA", (largura_canvas, altura_canvas), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    x0 = borda_px
    y0 = borda_px
    x1 = x0 + largura_caixa
    y1 = y0 + altura_caixa
    raio = int(altura_caixa * 0.36)

    # Sombra preta suave
    draw.rounded_rectangle(
        [x0 + sombra_offset, y0 + sombra_offset, x1 + sombra_offset, y1 + sombra_offset],
        radius=raio,
        fill=(0, 0, 0, 140),
    )

    # Caixa amarela arredondada com contorno preto grosso
    draw.rounded_rectangle(
        [x0, y0, x1, y1],
        radius=raio,
        fill=cor_caixa,
        outline=cor_borda,
        width=borda_px,
    )

    # Desenha ícone ▶ (triângulo play) centralizado verticalmente à esquerda
    centro_y = (y0 + y1) // 2
    ix0 = x0 + pad_x
    iy_top = centro_y - tam_icone // 2
    iy_bot = centro_y + tam_icone // 2
    ix_tip = ix0 + int(tam_icone * 0.92)
    draw.polygon([(ix0, iy_top), (ix0, iy_bot), (ix_tip, centro_y)], fill=cor_texto)

    # Desenha texto do CTA centralizado verticalmente ao lado do ▶
    tx = ix_tip + espaco_icone_txt
    ty = centro_y - (altura_txt // 2) - bbox[1]
    draw.text((tx, ty), texto_limpo, font=fonte, fill=cor_texto)

    # Reduz de 2x para 1x com antialiasing LANCZOS
    larg_final = largura_canvas // escala
    alt_final = altura_canvas // escala
    img_final = img.resize((larg_final, alt_final), resample=Image.Resampling.LANCZOS)
    img_final.save(destino_png, "PNG")
    return destino_png


def detectar_cta_visual_gravado(
    video_path: Path,
    inicio_ultimo_take_s: float,
    falas_json: dict[str, Any] | None = None,
) -> tuple[bool, str]:
    """
    Verifica se o último take já traz uma caixa/banner de CTA gravado na imagem:
    1) Checa flag explícita 'cta_ja_gravado' no falas.json;
    2) Analisa a faixa da caixa do CTA no último take procurando retângulo amarelo saturado largo
       pré-existente (típico de caixa CTA já queimada).
    """
    if falas_json and falas_json.get("cta_ja_gravado") is True:
        return True, "Flag 'cta_ja_gravado: true' informada no falas.json"

    dur = obter_duracao_video(video_path)
    t_amostra = min(dur - 0.2, inicio_ultimo_take_s + max(0.3, (dur - inicio_ultimo_take_s) * 0.5))
    temp_frame = video_path.parent / "_check_cta_frame.jpg"
    try:
        extrair_frame(video_path, max(0.0, t_amostra), temp_frame)
        with Image.open(temp_frame) as im:
            im_rgb = im.convert("RGB")
            w, h = im_rgb.size
            # Analisa a zona superior/inferior típica de botão CTA largo (40% da largura central)
            # Uma caixa CTA amarela tem > 35% dos pixels da faixa com R>220, G>190, B<60 contínuos
            faixa = im_rgb.crop((int(w * 0.20), int(h * 0.72), int(w * 0.80), int(h * 0.84)))
            pixels = list(faixa.getdata())
            amarelos = sum(1 for (r, g, b) in pixels if r > 220 and g > 190 and b < 55)
            proporcao = amarelos / max(1, len(pixels))
            if proporcao > 0.35:
                return True, f"Caixa amarela pré-existente detectada no último take ({proporcao*100:.1f}% da faixa)"
    finally:
        if temp_frame.exists():
            temp_frame.unlink()

    return False, "Nenhum CTA visual pré-gravado detectado"


def aplicar_cta_ultimo_take(
    video_entrada: Path,
    video_saida: Path,
    inicio_ultimo_take_s: float,
    texto_cta: str = "COMMENT YES",
    falas_json: dict[str, Any] | None = None,
    y_base: int = 1480,
    crf: int = 20,
) -> dict[str, Any]:
    """
    Aplica a caixa amarela arredondada com contorno preto e ícone ▶ ("▶ COMMENT YES")
    no último take com animação de pulo leve:
      y = y_base - 28 * |sin(2 * pi * 1.4 * (t - t0))|
    Se o clipe já trouxer o CTA gravado, copia sem sobrepor.
    """
    video_saida.parent.mkdir(parents=True, exist_ok=True)
    duracao = obter_duracao_video(video_entrada)

    ja_tem_cta, motivo_deteccao = detectar_cta_visual_gravado(
        video_entrada,
        inicio_ultimo_take_s,
        falas_json=falas_json,
    )
    if ja_tem_cta:
        if video_entrada.resolve() != video_saida.resolve():
            import shutil

            shutil.copy2(video_entrada, video_saida)
        return {
            "cta_sobreposto": False,
            "motivo": motivo_deteccao,
            "arquivo_saida": str(video_saida),
        }

    badge_png = video_saida.parent / "cta_badge.png"
    gerar_badge_cta_png(texto_cta=texto_cta, destino_png=badge_png)

    t0 = round(max(0.0, inicio_ultimo_take_s), 3)
    # Fórmula exata pedida: y = -28 * |sin(2π * 1.4 * t)| desde o início do último take até o fim
    expr_y = f"{y_base}-28*abs(sin(2*PI*1.4*(t-{t0})))"
    filtro = (
        f"[0:v][1:v]overlay=x=(W-w)/2:y='{expr_y}':enable='between(t,{t0},{duracao + 0.5:.3f})'[vout]"
    )

    cmd_nvenc = [
        "ffmpeg",
        "-nostdin",
        "-y",
        "-loglevel",
        "error",
        "-i",
        str(video_entrada),
        "-i",
        str(badge_png),
        "-filter_complex",
        filtro,
        "-map",
        "[vout]",
        "-map",
        "0:a?",
        "-c:v",
        "h264_nvenc",
        "-preset",
        "p2",
        "-rc",
        "vbr",
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
            "-i",
            str(badge_png),
            "-filter_complex",
            filtro,
            "-map",
            "[vout]",
            "-map",
            "0:a?",
            "-c:v",
            "libx264",
            "-crf",
            str(crf),
            "-preset",
            "veryfast",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-movflags",
            "+faststart",
            str(video_saida),
        ]
        subprocess.run(cmd_cpu, check=True)

    return {
        "cta_sobreposto": True,
        "texto_cta": f"▶ {texto_cta.replace('▶', '').strip().upper()}",
        "badge_png": str(badge_png),
        "inicio_ultimo_take_s": t0,
        "fim_video_s": round(duracao, 3),
        "formula_pulo_y": f"y = {y_base} - 28*|sin(2*pi*1.4*(t - {t0}))|",
        "amplitude_px": 28,
        "frequencia_hz": 1.4,
        "arquivo_saida": str(video_saida),
    }
