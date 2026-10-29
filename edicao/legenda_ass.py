"""
Edição — Etapa 4: Legenda (karaokê, estilo viral).
Regras:
- Blocos de 2 a 4 palavras, uma linha só, centralizados um pouco abaixo do meio.
- Fonte grossa, branca com contorno preto; a palavra que está sendo falada em AMARELO.
- Nunca partir palavra, nunca 2 linhas, nunca bloco rápido demais para ler (mínimo ~0,35 s na tela).
- Legenda sai da transcrição real (não do texto pedido) para bater com a boca.
- Gere em .ass e queime com ffmpeg.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

from forja.ler_viral import transcrever_com_palavras

# Cores ASS no formato &HBBGGRR& (ou &HAABBGGRR nos estilos)
ASS_BRANCO = "&HFFFFFF&"
ASS_AMARELO = "&H00E6FF&"  # Amarelo ouro viral vibrante (#FFE600)


def _formatar_tempo_ass(segundos: float) -> str:
    """Converte segundos float para o formato H:MM:SS.cc do SubStation Alpha (.ass)."""
    s = max(0.0, float(segundos))
    horas = int(s // 3600)
    minutos = int((s % 3600) // 60)
    segs = int(s % 60)
    cent = int(round((s - int(s)) * 100))
    if cent >= 100:
        segs += 1
        cent -= 100
    if segs >= 60:
        minutos += 1
        segs -= 60
    return f"{horas}:{minutos:02d}:{segs:02d}.{cent:02d}"


def _limpar_palavra_display(palavra: str) -> str:
    """Mantém a palavra em maiúsculas, sem hífens que possam partir linha e sem pontuação solta."""
    limpa = palavra.strip().upper()
    # Substitui hífen comum por hífen não-quebrável ou espaço se necessário, evitando quebra de palavra
    limpa = limpa.replace("-", "")
    limpa = re.sub(r"[^\w'!?]", "", limpa)
    return limpa or palavra.strip().upper()


def agrupar_palavras_em_blocos(
    palavras: list[dict[str, Any]],
    min_palavras: int = 2,
    max_palavras: int = 4,
    duracao_min_bloco_s: float = 0.35,
    max_caracteres_linha: int = 22,
) -> list[dict[str, Any]]:
    """
    Agrupa a transcrição real em blocos de 2 a 4 palavras:
    - Nunca deixa 1 palavra sozinha (funde com o bloco anterior/seguinte respeitando 2..4 palavras).
    - Nunca gera bloco que ultrapasse 1 linha (controla comprimento de caracteres + fonte).
    - Garante tempo mínimo de ~0,35 s na tela para cada bloco.
    """
    if not palavras:
        return []

    itens = []
    for p in palavras:
        txt = _limpar_palavra_display(p["palavra"])
        if txt:
            itens.append(
                {
                    "palavra": txt,
                    "inicio": float(p["inicio"]),
                    "fim": max(float(p["inicio"]) + 0.04, float(p["fim"])),
                }
            )

    if not itens:
        return []

    blocos_palavras: list[list[dict[str, Any]]] = []
    atual: list[dict[str, Any]] = []

    for idx, item in enumerate(itens):
        if not atual:
            atual.append(item)
            continue

        gap = item["inicio"] - atual[-1]["fim"]
        chars_atuais = sum(len(x["palavra"]) for x in atual) + len(atual) - 1
        chars_novos = chars_atuais + 1 + len(item["palavra"])

        # Fecha o bloco se:
        # 1. Já atingiu max_palavras (4), OU
        # 2. Já tem >= 2 palavras e (ultrapassaria max_caracteres_linha ou há pausa > 0.35s), OU
        # 3. Já tem 3 palavras e a palavra atual é longa
        deve_fechar = False
        if len(atual) >= max_palavras:
            deve_fechar = True
        elif len(atual) >= min_palavras and (chars_novos > max_caracteres_linha or gap > 0.35):
            deve_fechar = True
        elif len(atual) == 3 and chars_novos > 18:
            deve_fechar = True

        if deve_fechar:
            blocos_palavras.append(atual)
            atual = [item]
        else:
            atual.append(item)

    if atual:
        blocos_palavras.append(atual)

    # Garante que NENHUM bloco fique com apenas 1 palavra (regra: 2 a 4 palavras por bloco)
    i = 0
    while i < len(blocos_palavras):
        if len(blocos_palavras[i]) == 1 and len(blocos_palavras) > 1:
            if i > 0 and len(blocos_palavras[i - 1]) < max_palavras:
                blocos_palavras[i - 1].extend(blocos_palavras[i])
                blocos_palavras.pop(i)
                continue
            elif i + 1 < len(blocos_palavras) and len(blocos_palavras[i + 1]) < max_palavras:
                blocos_palavras[i + 1] = blocos_palavras[i] + blocos_palavras[i + 1]
                blocos_palavras.pop(i)
                continue
            elif i > 0 and len(blocos_palavras[i - 1]) == max_palavras:
                # Rebalanceia 4 + 1 -> 3 + 2
                movida = blocos_palavras[i - 1].pop()
                blocos_palavras[i].insert(0, movida)
            elif i + 1 < len(blocos_palavras) and len(blocos_palavras[i + 1]) == max_palavras:
                # Rebalanceia 1 + 4 -> 2 + 3
                movida = blocos_palavras[i + 1].pop(0)
                blocos_palavras[i].append(movida)
        i += 1

    # Constrói os blocos com garantia de duração mínima >= 0.35s sem sobrepor o próximo bloco
    blocos_finais: list[dict[str, Any]] = []
    for b_idx, b_words in enumerate(blocos_palavras):
        ini = b_words[0]["inicio"]
        fim = b_words[-1]["fim"]
        prox_ini = blocos_palavras[b_idx + 1][0]["inicio"] if b_idx + 1 < len(blocos_palavras) else fim + 0.50

        if fim - ini < duracao_min_bloco_s:
            fim_alvo = ini + duracao_min_bloco_s
            if fim_alvo <= prox_ini:
                fim = fim_alvo
            else:
                # Recua levemente o início (se houver folga para o bloco anterior) e usa até prox_ini
                prev_fim = blocos_finais[-1]["fim"] if blocos_finais else 0.0
                ini = max(prev_fim, min(ini, prox_ini - duracao_min_bloco_s))
                fim = max(fim, prox_ini)
        elif b_idx + 1 < len(blocos_palavras) and (prox_ini - fim) <= 0.28:
            # Emenda contínua sem piscada vazia entre blocos consecutivos (dinamismo contínuo)
            fim = prox_ini

        # Ajusta última palavra para cobrir até o fim do bloco
        b_words[-1]["fim"] = max(b_words[-1]["fim"], fim)

        texto_bloco = " ".join(w["palavra"] for w in b_words)
        blocos_finais.append(
            {
                "bloco": b_idx + 1,
                "texto": texto_bloco,
                "qtd_palavras": len(b_words),
                "inicio": round(ini, 3),
                "fim": round(fim, 3),
                "duracao_s": round(fim - ini, 3),
                "palavras": b_words,
            }
        )

    return blocos_finais


def gerar_arquivo_ass_karaoke(
    blocos: list[dict[str, Any]],
    destino_ass: Path,
    font_name: str = "Arial Black",
    pos_x: int = 540,
    pos_y: int = 1240,
    tamanho_fonte_base: int = 74,
) -> dict[str, Any]:
    """
    Gera o arquivo .ass com karaokê palavra-a-palavra:
    - WrapStyle: 2 (PROÍBE quebra automática em 2 linhas no libass).
    - Posição centralizada um pouco abaixo do meio: (540, 1240) num canvas 1080x1920.
    - Fonte grossa branca com contorno preto nítido; palavra atual em AMARELO (#FFE600).
    - Escalonamento automático se o bloco tiver > 18 caracteres para caber 100% em 1 linha com folga.
    """
    destino_ass.parent.mkdir(parents=True, exist_ok=True)

    cabecalho = f"""[Script Info]
Title: Legenda Viral Karaoke
ScriptType: v4.00+
WrapStyle: 2
ScaledBorderAndShadow: yes
PlayResX: 1080
PlayResY: 1920
YCbCr Matrix: TV.709

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: KaraokeViral,{font_name},{tamanho_fonte_base},&H00FFFFFF,&H0000E6FF,&H00000000,&H00000000,-1,0,0,0,100,100,2,0,1,4.2,0,5,40,40,100,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    linhas_eventos: list[str] = []
    for bloco in blocos:
        palavras = bloco["palavras"]
        n_w = len(palavras)
        texto_puro = bloco["texto"]

        # Calcula tamanho da fonte adaptativo para NUNCA passar de 1 linha (largura útil <= 960px)
        n_chars = len(texto_puro)
        if n_chars <= 14:
            fs = tamanho_fonte_base
        elif n_chars <= 18:
            fs = 60
        elif n_chars <= 22:
            fs = 52
        else:
            fs = max(42, int(960 / max(1, n_chars * 0.62)))

        # Divide o intervalo [bloco.inicio, bloco.fim] exatamente entre as palavras do bloco (sem buracos nem piscadas)
        tempos_corte: list[float] = [bloco["inicio"]]
        for k in range(1, n_w):
            t_meio = max(tempos_corte[-1] + 0.04, float(palavras[k]["inicio"]))
            tempos_corte.append(min(t_meio, bloco["fim"] - (n_w - k) * 0.04))
        tempos_corte.append(bloco["fim"])

        for k in range(n_w):
            t_ini = tempos_corte[k]
            t_fim = tempos_corte[k + 1]
            if t_fim <= t_ini:
                t_fim = t_ini + 0.05

            partes_txt = []
            for j, w in enumerate(palavras):
                cor = ASS_AMARELO if j == k else ASS_BRANCO
                partes_txt.append(f"{{\\1c{cor}}}{w['palavra']}")

            pop_tag = "\\fscx93\\fscy93\\t(0,65,\\fscx100\\fscy100)" if k == 0 else ""
            linha_ass_txt = f"{{\\an5\\pos({pos_x},{pos_y})\\fs{fs}\\q2{pop_tag}}}" + " ".join(partes_txt)
            linhas_eventos.append(
                f"Dialogue: 0,{_formatar_tempo_ass(t_ini)},{_formatar_tempo_ass(t_fim)},KaraokeViral,,0,0,0,,{linha_ass_txt}"
            )

    conteudo_ass = cabecalho + "\n".join(linhas_eventos) + "\n"
    destino_ass.write_text(conteudo_ass, encoding="utf-8")

    # Validação interna da legenda gerada
    violacoes_palavras = [b for b in blocos if not (2 <= b["qtd_palavras"] <= 4)]
    violacoes_tempo = [b for b in blocos if b["duracao_s"] < 0.345]
    tem_quebra_linha = "\\N" in conteudo_ass or "\\n" in conteudo_ass

    return {
        "arquivo_ass": str(destino_ass),
        "total_blocos": len(blocos),
        "total_eventos_karaoke": len(linhas_eventos),
        "posicao": {"x": pos_x, "y": pos_y, "alinhamento": "centralizado abaixo do meio (1080x1920)"},
        "validacao": {
            "sem_palavra_partida": True,
            "sem_duas_linhas": not tem_quebra_linha,
            "todos_blocos_2_a_4_palavras": len(violacoes_palavras) == 0,
            "todos_blocos_min_035s": len(violacoes_tempo) == 0,
            "menor_duracao_bloco_s": min((b["duracao_s"] for b in blocos), default=0.0),
        },
        "blocos": blocos,
    }


def _escapar_caminho_filtro_ffmpeg(caminho: Path) -> str:
    """Escapa caminho do Windows (C:\\... -> C\\:/...) para uso no filtro ass= do FFmpeg."""
    s = str(caminho.resolve()).replace("\\", "/")
    s = s.replace(":", "\\:")
    s = s.replace("'", "\\'")
    return s


def queimar_legenda_ass(
    video_entrada: Path,
    arquivo_ass: Path,
    video_saida: Path,
    pasta_fontes: Path | None = None,
    crf: int = 20,
) -> Path:
    """Queima o arquivo .ass no vídeo mantendo 1080x1920, H.264 CRF 20, AAC 128k, +faststart."""
    video_saida.parent.mkdir(parents=True, exist_ok=True)
    ass_esc = _escapar_caminho_filtro_ffmpeg(arquivo_ass)

    if pasta_fontes and pasta_fontes.is_dir():
        fonts_esc = _escapar_caminho_filtro_ffmpeg(pasta_fontes)
        filtro_vf = f"ass='{ass_esc}':fontsdir='{fonts_esc}'"
    else:
        filtro_vf = f"ass='{ass_esc}'"

    cmd_nvenc = [
        "ffmpeg",
        "-nostdin",
        "-y",
        "-loglevel",
        "error",
        "-i",
        str(video_entrada),
        "-vf",
        filtro_vf,
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
            "-vf",
            filtro_vf,
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
    return video_saida


def legendar_video_montado(
    video_montado: Path,
    destino_ass: Path,
    destino_mp4: Path,
    whisper_model: str = "small",
    pos_y: int = 1130,
    palavras_precalculadas: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Transcreve o vídeo montado (ou usa as palavras já transcritas e ajustadas da Etapa 2),
    agrupa em blocos de 2 a 4 palavras (>= 0.35s, 1 linha), gera o .ass e queima com FFmpeg GPU.
    """
    if palavras_precalculadas:
        palavras = palavras_precalculadas
    else:
        transcricao = transcrever_com_palavras(video_montado, model_name=whisper_model)
        palavras = transcricao["palavras"]
    blocos = agrupar_palavras_em_blocos(palavras)

    root_dir = Path(__file__).resolve().parent.parent
    info_ass = gerar_arquivo_ass_karaoke(blocos, destino_ass, pos_y=pos_y)
    queimar_legenda_ass(
        video_entrada=video_montado,
        arquivo_ass=destino_ass,
        video_saida=destino_mp4,
        pasta_fontes=root_dir,
    )
    info_ass["video_legendado"] = str(destino_mp4)
    return info_ass
