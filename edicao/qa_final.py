"""
Edição — Etapa 6: QA Final do Vídeo Pronto (edicao/qa_final.py).
Regras:
- Confere o vídeo pronto:
  1) 1080x1920, duração certa, áudio + vídeo presentes.
  2) Sem silêncio no começo (> 0.35s antes da primeira palavra), sem corte no meio de palavra no fim.
  3) Legenda inteira dentro da tela (sem estourar lateral ou rodapé).
- Se reprovar, move para _revisao/ com o motivo anotado (nunca apaga arquivos).
"""

from __future__ import annotations

import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from forja.estrutura import REVISAO_DIR
from forja.qa_clipe import analisar_qualidade_audio, obter_metadados_midia


def validar_legenda_dentro_da_tela(
    ass_path: Path | None,
    largura_tela: int = 1080,
    altura_tela: int = 1920,
    margem_seguranca_x: int = 40,
    margem_seguranca_rodape: int = 120,
) -> dict[str, Any]:
    """
    Verifica geometricamente se todos os blocos da legenda .ass cabem inteiros dentro da tela (1080x1920),
    sem estourar as laterais nem o rodapé.
    """
    if ass_path is None or not ass_path.is_file():
        return {
            "legenda_presente": False,
            "dentro_da_tela": False,
            "motivo": "Arquivo .ass não encontrado.",
        }

    conteudo = ass_path.read_text(encoding="utf-8", errors="replace")
    m_size = re.search(r"Style:\s*Karaoke,[^,]+,(\d+)", conteudo)
    font_size = int(m_size.group(1)) if m_size else 66

    # Extrai eventos Dialogue e verifica largura estimada de cada linha e posição Y (\pos(x,y))
    linhas_dialogue = [ln for ln in conteudo.splitlines() if ln.startswith("Dialogue:")]
    estouros_laterais: list[str] = []
    estouros_rodape: list[str] = []

    largura_util_max = largura_tela - (2 * margem_seguranca_x)
    # Arial Black 66pt tem largura média ~0.58 * font_size por caractere
    largura_media_char = font_size * 0.56

    for ln in linhas_dialogue:
        m_pos = re.search(r"\\pos\((\d+),(\d+)\)", ln)
        if m_pos:
            pos_y = int(m_pos.group(2))
            if pos_y + font_size > (altura_tela - margem_seguranca_rodape):
                estouros_rodape.append(f"pos_y={pos_y} excede limite de rodapé")

        # Remove tags ASS {...} para medir o texto puro visível na linha
        partes = ln.split(",", 9)
        if len(partes) == 10:
            texto_limpo = re.sub(r"\{[^}]*\}", "", partes[9]).strip()
            if "\\N" in texto_limpo or "\n" in texto_limpo:
                estouros_laterais.append(f"Quebra em duas linhas detectada: '{texto_limpo}'")
            largura_estimada = len(texto_limpo) * largura_media_char
            if largura_estimada > largura_util_max:
                estouros_laterais.append(f"Texto '{texto_limpo}' ({int(largura_estimada)}px > {largura_util_max}px)")

    dentro_da_tela = len(estouros_laterais) == 0 and len(estouros_rodape) == 0
    return {
        "legenda_presente": True,
        "dentro_da_tela": dentro_da_tela,
        "font_size": font_size,
        "total_dialogues_verificados": len(linhas_dialogue),
        "estouros_laterais": estouros_laterais[:5],
        "estouros_rodape": estouros_rodape[:5],
    }


def avaliar_qa_final_video(
    video_pronto_path: Path,
    ass_path: Path | None,
    relatorio_etapa2: dict[str, Any] | None = None,
    duracao_esperada_s: float | None = None,
) -> dict[str, Any]:
    """
    Executa o QA Final (Etapa 6 da Edição) no vídeo montado, legendado e com CTA:
    - 1080x1920, duração certa, áudio + vídeo presentes.
    - Sem silêncio no começo, sem corte no meio de palavra no fim.
    - Legenda inteira dentro da tela (sem estourar lateral ou rodapé).
    """
    motivos_reprovacao: list[str] = []

    meta = obter_metadados_midia(video_pronto_path)
    if not meta.get("valido") or not meta.get("tem_video"):
        motivos_reprovacao.append("Vídeo final inválido ou sem trilha de vídeo.")
    if not meta.get("tem_audio"):
        motivos_reprovacao.append("Vídeo final sem trilha de áudio.")
    if meta.get("largura") != 1080 or meta.get("altura") != 1920:
        motivos_reprovacao.append(f"Resolução incorreta: {meta.get('largura')}x{meta.get('altura')} (esperado 1080x1920).")

    duracao_real = float(meta.get("duracao_s", 0.0))
    if duracao_real < 8.0:
        motivos_reprovacao.append(f"Duração final muito curta ({duracao_real}s).")
    if duracao_esperada_s is not None and abs(duracao_real - duracao_esperada_s) > 0.6:
        motivos_reprovacao.append(
            f"Duração final diverge do esperado ({duracao_real}s vs {duracao_esperada_s}s)."
        )

    # Verifica ausência de silêncio no começo e integridade da última palavra de cada take
    sem_silencio_comeco = True
    sem_corte_palavra_fim = True
    if relatorio_etapa2:
        if relatorio_etapa2.get("marcado_para_revisao"):
            motivos_reprovacao.extend(relatorio_etapa2.get("motivos_revisao", ["Marcado para revisão na Etapa 2."]))
        clipes = relatorio_etapa2.get("clipes", [])
        if clipes:
            primeiro_clipe = clipes[0]
            palavras_c1 = primeiro_clipe.get("palavras", [])
            if palavras_c1 and float(palavras_c1[0].get("inicio", 0.0)) > 0.35:
                sem_silencio_comeco = False
                motivos_reprovacao.append(
                    f"Silêncio excessivo no começo do vídeo ({palavras_c1[0]['inicio']}s antes da 1ª palavra)."
                )
            for c in clipes:
                comp = c.get("comparacao_fala", {})
                if not comp.get("ultima_palavra_integra", True):
                    sem_corte_palavra_fim = False
                    motivos_reprovacao.append(f"Corte no meio da última palavra em {c.get('arquivo')}.")

    aud = analisar_qualidade_audio(video_pronto_path, inicio_fala_s=0.1, fim_fala_s=max(1.0, duracao_real - 0.3))
    if not aud["tem_som_real"]:
        motivos_reprovacao.append("Áudio final mudo ou muito baixo.")

    leg = validar_legenda_dentro_da_tela(ass_path)
    if not leg["dentro_da_tela"]:
        motivos_reprovacao.append(
            f"Legenda fora dos limites da tela: laterais={leg.get('estouros_laterais')}, rodapé={leg.get('estouros_rodape')}"
        )

    aprovado = len(motivos_reprovacao) == 0
    return {
        "arquivo_video": str(video_pronto_path),
        "aprovado": aprovado,
        "motivos_reprovacao": motivos_reprovacao,
        "resolucao_1080x1920": meta.get("largura") == 1080 and meta.get("altura") == 1920,
        "duracao_s": duracao_real,
        "tem_video_e_audio": bool(meta.get("tem_video") and meta.get("tem_audio")),
        "sem_silencio_no_comeco": sem_silencio_comeco,
        "sem_corte_palavra_no_fim": sem_corte_palavra_fim,
        "audio": aud,
        "legenda": leg,
    }


def enviar_para_revisao(
    video_path: Path,
    identificador: str,
    relatorio_qa: dict[str, Any],
    revisao_root: Path = REVISAO_DIR,
) -> Path:
    """
    Copia/move o vídeo reprovado no QA final para _revisao/ com o motivo anotado em JSON,
    nunca apagando arquivos originais.
    """
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    pasta_dest = revisao_root / f"{identificador}_{ts}"
    pasta_dest.mkdir(parents=True, exist_ok=True)

    mp4_dest = pasta_dest / video_path.name
    json_dest = pasta_dest / "motivo_revisao.json"

    if video_path.is_file():
        shutil.copy2(str(video_path), str(mp4_dest))

    payload = {
        "identificador": identificador,
        "enviado_em": datetime.now().isoformat(timespec="seconds"),
        "arquivo_video": str(mp4_dest),
        "motivos_reprovacao": relatorio_qa.get("motivos_reprovacao", []),
        "relatorio_qa_final": relatorio_qa,
    }
    json_dest.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return pasta_dest
