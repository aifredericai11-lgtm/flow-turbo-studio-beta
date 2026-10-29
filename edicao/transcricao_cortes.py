"""
Edição — Etapa 2: Transcrição e Cortes Ultra-Dinâmicos (Acoustic Waveform Slicer + Pace Booster).
Regras de Alto Dinamismo:
- Combina Whisper GPU com Detector Acústico de Forma de Onda (`silencedetect=noise=-30dB:d=0.13`)
  para não ser enganado quando o Whisper estica o timestamp de uma palavra por cima de um silêncio.
- Ataque Acústico Imediato: corta 100% do silêncio real antes da 1ª sílaba (deixa apenas 0,025 s de ataque).
- Fim Acústico Colado: corta imediatamente no fim real da última sílaba (+0,04 s) para entrar direto no Mix (xfade + acrossfade).
- Fatiador Acústico de Pausas Internas (Intra-Take Breath Slicer): remove cirurgicamente qualquer respiração
  ou pausa acústica interna >= 0,14 s no meio das frases, aplicando micro-zoom dinâmico (1.035x) nos jump-cuts.
- Dynamic Pace Booster: acelera takes lentos (fator até 1,18x) para cravar a cadência viral de ~3,25 palavras/s.
"""

from __future__ import annotations

import json
import re
import subprocess
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from forja.ler_viral import obter_duracao_video, transcrever_com_palavras


def _normalizar_tokens(texto: str) -> list[str]:
    limpo = unicodedata.normalize("NFKD", texto.casefold())
    limpo = "".join(c for c in limpo if not unicodedata.combining(c))
    return re.findall(r"[a-z0-9']+", limpo)


def detectar_silencios_acusticos(
    video_path: Path,
    duracao: float,
    noise_db: str = "-30dB",
    min_dur_s: float = 0.13,
) -> list[tuple[float, float]]:
    """
    Detecta todos os intervalos reais de silêncio acústico [(inicio, fim), ...] na forma de onda
    usando silencedetect do FFmpeg.
    """
    cmd = [
        "ffmpeg",
        "-i",
        str(video_path),
        "-af",
        f"silencedetect=noise={noise_db}:d={min_dur_s:.2f}",
        "-f",
        "null",
        "-",
    ]
    proc = subprocess.run(
        cmd,
        stderr=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    stderr = proc.stderr or ""

    starts: list[float] = []
    ends: list[float] = []
    for line in stderr.splitlines():
        if "silence_start:" in line:
            m = re.search(r"silence_start:\s*([0-9.]+)", line)
            if m:
                starts.append(float(m.group(1)))
        elif "silence_end:" in line:
            m = re.search(r"silence_end:\s*([0-9.]+)", line)
            if m:
                ends.append(float(m.group(1)))

    intervalos: list[tuple[float, float]] = []
    for idx, s in enumerate(starts):
        e = ends[idx] if idx < len(ends) else duracao
        if e > s:
            intervalos.append((round(s, 3), round(e, 3)))
    return intervalos


def detectar_fim_fala_acustico(video_path: Path, duracao: float, noise_db: str = "-30dB") -> float:
    """
    Retorna o fim acústico real da fala na forma de onda.
    """
    intervalos = detectar_silencios_acusticos(video_path, duracao, noise_db=noise_db, min_dur_s=0.12)
    if intervalos:
        ult_s, ult_e = intervalos[-1]
        if duracao - ult_e <= 0.30 and ult_s > 0.2:
            return round(ult_s, 3)
    return round(duracao, 3)


def comparar_fala_pedida_vs_transcrita(
    fala_pedida: str,
    fala_transcrita: str,
    limiar_precisao: float = 0.90,
) -> dict[str, Any]:
    """
    Compara a fala transcrita com a pedida (falas.json).
    """
    pedidas = _normalizar_tokens(fala_pedida)
    ouvidas = _normalizar_tokens(fala_transcrita)

    matcher = SequenceMatcher(None, pedidas, ouvidas)
    opcodes = matcher.get_opcodes()

    faltando: list[str] = []
    inventadas: list[str] = []

    for tag, i1, i2, j1, j2 in opcodes:
        if tag == "delete":
            faltando.extend(pedidas[i1:i2])
        elif tag == "insert":
            inventadas.extend(ouvidas[j1:j2])
        elif tag == "replace":
            seg_ped = pedidas[i1:i2]
            seg_ouv = ouvidas[j1:j2]
            sim = SequenceMatcher(None, " ".join(seg_ped), " ".join(seg_ouv)).ratio()
            if sim < 0.78:
                faltando.extend(seg_ped)
                inventadas.extend(seg_ouv)

    similaridade_tokens = round(matcher.ratio(), 3)
    similaridade_chars = round(SequenceMatcher(None, " ".join(pedidas), " ".join(ouvidas)).ratio(), 3)
    precisao = max(similaridade_tokens, similaridade_chars)

    ultima_ok = bool(pedidas and ouvidas and SequenceMatcher(None, pedidas[-1], ouvidas[-1]).ratio() >= 0.75)

    if precisao >= limiar_precisao and ultima_ok and len(inventadas) <= 1:
        revisao = False
    else:
        revisao = bool(faltando or inventadas or precisao < limiar_precisao or not ultima_ok)

    motivos = []
    if revisao:
        if faltando:
            motivos.append(f"palavra(s) faltando: {', '.join(faltando)}")
        if inventadas:
            motivos.append(f"palavra(s)/frase inventada: {', '.join(inventadas)}")
        if not ultima_ok and pedidas:
            motivos.append(f"última palavra divergente/cortada (esperado '{pedidas[-1]}')")

    return {
        "fala_pedida": fala_pedida,
        "fala_transcrita": fala_transcrita,
        "precisao": precisao,
        "limiar_precisao": limiar_precisao,
        "ultima_palavra_integra": ultima_ok,
        "palavras_faltando": faltando,
        "palavras_inventadas": inventadas,
        "marcar_para_revisao": revisao,
        "motivo_revisao": "; ".join(motivos) if motivos else f"OK (precisão {precisao*100:.1f}% >= 92%)",
    }


def _mapear_tempo_em_segmentos(
    t_orig: float,
    segmentos: list[dict[str, Any]],
    fator_velocidade: float = 1.0,
) -> float:
    """
    Converte qualquer instante `t_orig` do vídeo bruto para o novo instante exato no clipe
    após a remoção das pausas internas e aplicação do `fator_velocidade`.
    """
    acumulado = 0.0
    for seg in segmentos:
        si = float(seg["inicio_s"])
        sf = float(seg["fim_s"])
        dur = sf - si
        if t_orig <= si:
            return round(acumulado / fator_velocidade, 3)
        if t_orig <= sf:
            return round((acumulado + (t_orig - si)) / fator_velocidade, 3)
        acumulado += dur
    return round(acumulado / fator_velocidade, 3)


def _construir_segmentos_hibridos_sem_pausa(
    palavras: list[dict[str, Any]],
    silencios_acusticos: list[tuple[float, float]],
    inicio_corte: float,
    fim_corte: float,
    fator_velocidade: float = 1.0,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Une os buracos de silêncio acústico (`silencedetect`) e os gaps entre palavras do Whisper
    dentro de `[inicio_corte, fim_corte]` para fatiar e arrancar todo ar morto interno (> 0.14s).
    """
    buracos_candidatos: list[tuple[float, float]] = []

    # 1. Silêncios acústicos reais detectados na forma de onda
    for s_ini, s_fim in silencios_acusticos:
        # Mantém 30ms de saída da consoante anterior e 25ms de ataque da próxima sílaba
        b_ini = max(inicio_corte + 0.14, s_ini + 0.03)
        b_fim = min(fim_corte - 0.14, s_fim - 0.025)
        if b_fim - b_ini >= 0.07:
            buracos_candidatos.append((round(b_ini, 3), round(b_fim, 3)))

    # 2. Gaps explícitos entre palavras do Whisper (> 0.15s)
    for i in range(1, len(palavras)):
        w_ant = palavras[i - 1]
        w_atu = palavras[i]
        gap = float(w_atu["inicio"]) - float(w_ant["fim"])
        if gap > 0.15:
            b_ini = max(inicio_corte + 0.14, float(w_ant["fim"]) + 0.03)
            b_fim = min(fim_corte - 0.14, float(w_atu["inicio"]) - 0.025)
            if b_fim - b_ini >= 0.07:
                buracos_candidatos.append((round(b_ini, 3), round(b_fim, 3)))

    # Mescla buracos sobrepostos
    buracos_candidatos.sort(key=lambda x: x[0])
    buracos_mesclados: list[tuple[float, float]] = []
    for b_ini, b_fim in buracos_candidatos:
        if not buracos_mesclados or b_ini > buracos_mesclados[-1][1] + 0.04:
            buracos_mesclados.append((b_ini, b_fim))
        else:
            ant_i, ant_f = buracos_mesclados[-1]
            buracos_mesclados[-1] = (ant_i, max(ant_f, b_fim))

    # Constrói os segmentos ativos complementares dentro de [inicio_corte, fim_corte]
    segmentos: list[dict[str, Any]] = []
    cursor = inicio_corte
    for b_ini, b_fim in buracos_mesclados:
        if b_ini > cursor + 0.10:
            segmentos.append(
                {
                    "inicio_s": round(cursor, 3),
                    "fim_s": round(b_ini, 3),
                    "duracao_s": round(b_ini - cursor, 3),
                    "pausa_removida_s": round(b_fim - b_ini, 3),
                }
            )
            cursor = b_fim

    if fim_corte > cursor + 0.05:
        segmentos.append(
            {
                "inicio_s": round(cursor, 3),
                "fim_s": round(fim_corte, 3),
                "duracao_s": round(fim_corte - cursor, 3),
                "pausa_removida_s": 0.0,
            }
        )

    if not segmentos:
        segmentos = [
            {
                "inicio_s": round(inicio_corte, 3),
                "fim_s": round(fim_corte, 3),
                "duracao_s": round(fim_corte - inicio_corte, 3),
                "pausa_removida_s": 0.0,
            }
        ]

    palavras_ajustadas: list[dict[str, Any]] = []
    for p in palavras:
        t_i = _mapear_tempo_em_segmentos(float(p["inicio"]), segmentos, fator_velocidade)
        t_f = _mapear_tempo_em_segmentos(float(p["fim"]), segmentos, fator_velocidade)
        if t_f <= t_i + 0.04:
            t_f = round(t_i + 0.06, 3)
        palavras_ajustadas.append(
            {
                "palavra": p["palavra"],
                "inicio_original": p["inicio"],
                "fim_original": p["fim"],
                "inicio": t_i,
                "fim": t_f,
            }
        )

    return segmentos, palavras_ajustadas


def calcular_cortes_clipe(
    video_path: Path,
    fala_pedida: str,
    whisper_model: str = "small",
    remover_pausas_internas: bool = True,
    meta_palavras_por_segundo: float = 3.25,
) -> dict[str, Any]:
    """
    Transcreve o clipe e aplica o Motor Híbrido (Whisper + Forma de Onda Acústica):
    - Corta 100% do silêncio acústico inicial (mesmo quando o Whisper mente que a 1ª palavra começou em 0.0s).
    - Remove todas as pausas e respirações acústicas internas >= 0.13s.
    - Corta o final colado na última sílaba acústica (+0.04s) para entrar no Mix sem pausa.
    - Aplica Dynamic Pace Booster (até 1.16x) para atingir a cadência viral de ~3.25 palavras/s.
    """
    duracao_clipe = obter_duracao_video(video_path)
    transcricao = transcrever_com_palavras(video_path, model_name=whisper_model)
    palavras = transcricao["palavras"]

    if not palavras:
        return {
            "arquivo": video_path.name,
            "duracao_original_s": round(duracao_clipe, 3),
            "erro": "Nenhuma palavra detectada no áudio",
            "marcar_para_revisao": True,
            "motivo_revisao": "Clipe mudo ou sem fala reconhecida",
        }

    primeira = palavras[0]
    ultima = palavras[-1]

    silencios = detectar_silencios_acusticos(video_path, duracao_clipe, noise_db="-30dB", min_dur_s=0.13)

    # 1. Ataque Acústico Real no Início:
    # Se houver silêncio acústico começando logo no início (<= 0.15s) que termina depois do início reportado pelo Whisper,
    # usamos o fim real do silêncio acústico para não deixar ar morto na entrada do take!
    ataque_acustico_ini = float(primeira["inicio"])
    for s_ini, s_fim in silencios:
        if s_ini <= 0.15 and s_fim < float(primeira["fim"]) + 0.25:
            ataque_acustico_ini = max(ataque_acustico_ini, s_fim)
            break
    inicio_corte = round(max(0.0, ataque_acustico_ini - 0.025), 3)

    # 2. Fim Acústico Real na Última Sílaba:
    fim_acustico = detectar_fim_fala_acustico(video_path, duracao_clipe, noise_db="-30dB")
    fim_detectado = round(min(float(ultima["fim"]) + 0.06, max(float(ultima["inicio"]) + 0.16, fim_acustico + 0.04)), 3)
    candidato_inicio_ult_mais_016 = round(float(ultima["inicio"]) + 0.16, 3)
    candidato_fim_ult_mais_004 = round(float(ultima["fim"]) + 0.04, 3)

    fim_corte = round(
        min(
            duracao_clipe,
            max(fim_detectado, candidato_inicio_ult_mais_016, min(candidato_fim_ult_mais_004, fim_acustico + 0.05)),
        ),
        3,
    )

    # Primeiro constrói os segmentos sem pausa com fator 1.0 para medir a duração limpa
    if remover_pausas_internas:
        segmentos_base, _ = _construir_segmentos_hibridos_sem_pausa(
            palavras=palavras,
            silencios_acusticos=silencios,
            inicio_corte=inicio_corte,
            fim_corte=fim_corte,
            fator_velocidade=1.0,
        )
    else:
        segmentos_base = [
            {
                "inicio_s": inicio_corte,
                "fim_s": fim_corte,
                "duracao_s": round(fim_corte - inicio_corte, 3),
                "pausa_removida_s": 0.0,
            }
        ]

    duracao_sem_pausas = sum(s["duracao_s"] for s in segmentos_base)
    wps_atual = len(palavras) / max(0.2, duracao_sem_pausas)

    # Dynamic Pace Booster: acelera até 1.16x se o take ainda estiver abaixo de 3.25 palavras/s
    fator_velocidade = 1.0
    if wps_atual < meta_palavras_por_segundo:
        fator_velocidade = round(min(1.16, max(1.0, meta_palavras_por_segundo / max(0.5, wps_atual))), 3)
        if fator_velocidade < 1.02:
            fator_velocidade = 1.0

    # Mapeia os timestamps finais das palavras já com fator_velocidade aplicado
    segmentos_ativos, palavras_ajustadas = _construir_segmentos_hibridos_sem_pausa(
        palavras=palavras,
        silencios_acusticos=silencios if remover_pausas_internas else [],
        inicio_corte=inicio_corte,
        fim_corte=fim_corte,
        fator_velocidade=fator_velocidade,
    )

    duracao_final_cortada = round(duracao_sem_pausas / fator_velocidade, 3)
    total_pausas_internas_removidas = round(sum(s["pausa_removida_s"] for s in segmentos_ativos), 3)

    comparacao = comparar_fala_pedida_vs_transcrita(fala_pedida, transcricao["texto"])

    return {
        "arquivo": video_path.name,
        "duracao_original_s": round(duracao_clipe, 3),
        "inicio_corte_s": inicio_corte,
        "fim_corte_s": fim_corte,
        "duracao_cortada_s": duracao_final_cortada,
        "fator_velocidade": fator_velocidade,
        "segmentos_ativos": segmentos_ativos,
        "pausas_internas_removidas_s": total_pausas_internas_removidas,
        "regra_fim_detalhes": {
            "primeira_palavra": primeira,
            "ultima_palavra": ultima,
            "fim_detectado_s": fim_detectado,
            "inicio_ultima_mais_016_s": candidato_inicio_ult_mais_016,
            "fim_ultima_mais_004_s": candidato_fim_ult_mais_004,
            "tamanho_clipe_s": round(duracao_clipe, 3),
        },
        "comparacao_fala": comparacao,
        "marcar_para_revisao": comparacao["marcar_para_revisao"],
        "motivo_revisao": comparacao["motivo_revisao"],
        "palavras": palavras_ajustadas,
    }


def cortar_clipe_ffmpeg(
    origem: Path,
    destino: Path,
    inicio_s: float,
    fim_s: float,
    segmentos_ativos: list[dict[str, Any]] | None = None,
    fator_velocidade: float = 1.0,
    aplicar_micro_zoom_jumpcut: bool = False,
) -> Path:
    """
    Recorta o clipe eliminando todas as pausas acústicas internas (Jump-Cuts) e aplicando o
    Dynamic Pace Booster (fator_velocidade) via filter_complex em 1 única passada GPU/CPU.
    """
    destino.parent.mkdir(parents=True, exist_ok=True)
    segs = segmentos_ativos or [{"inicio_s": inicio_s, "fim_s": fim_s}]

    if len(segs) == 1 and abs(fator_velocidade - 1.0) < 0.01:
        s0 = segs[0]
        duracao = max(0.05, float(s0["fim_s"]) - float(s0["inicio_s"]))
        cmd_nvenc = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-ss", f"{float(s0['inicio_s']):.3f}",
            "-i", str(origem),
            "-t", f"{duracao:.3f}",
            "-c:v", "h264_nvenc", "-preset", "p2", "-rc", "vbr", "-cq", "18", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k", "-ar", "48000",
            str(destino),
        ]
        if subprocess.run(cmd_nvenc).returncode != 0:
            cmd_cpu = [
                "ffmpeg", "-y", "-loglevel", "error",
                "-ss", f"{float(s0['inicio_s']):.3f}",
                "-i", str(origem),
                "-t", f"{duracao:.3f}",
                "-c:v", "libx264", "-crf", "18", "-preset", "veryfast", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "128k", "-ar", "48000",
                str(destino),
            ]
            subprocess.run(cmd_cpu, check=True)
        return destino

    filtros: list[str] = []
    partes_concat: list[str] = []
    for idx, s in enumerate(segs):
        si = float(s["inicio_s"])
        sf = float(s["fim_s"])
        dur_s = max(0.04, sf - si)
        if aplicar_micro_zoom_jumpcut and idx % 2 == 1:
            filtros.append(
                f"[0:v]trim=start={si:.3f}:end={sf:.3f},setpts=PTS-STARTPTS,"
                f"scale=1118:1988:force_original_aspect_ratio=increase,crop=1080:1920:(iw-1080)/2:(ih-1920)/2,setsar=1[sv{idx}]"
            )
        else:
            filtros.append(
                f"[0:v]trim=start={si:.3f}:end={sf:.3f},setpts=PTS-STARTPTS,"
                f"scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black,setsar=1[sv{idx}]"
            )
        filtros.append(
            f"[0:a]atrim=start={si:.3f}:end={sf:.3f},asetpts=PTS-STARTPTS,"
            f"afade=t=in:st=0:d=0.012,afade=t=out:st={max(0.0, dur_s - 0.012):.3f}:d=0.012[sa{idx}]"
        )
        partes_concat.append(f"[sv{idx}][sa{idx}]")

    n_s = len(segs)
    if abs(fator_velocidade - 1.0) >= 0.01:
        filtros.append(f"{''.join(partes_concat)}concat=n={n_s}:v=1:a=1[vc][ac]")
        filtros.append(f"[vc]setpts=PTS/{fator_velocidade:.4f}[vout]")
        filtros.append(f"[ac]atempo={fator_velocidade:.4f}[aout]")
    else:
        filtros.append(f"{''.join(partes_concat)}concat=n={n_s}:v=1:a=1[vout][aout]")

    fc_str = ";".join(filtros)
    cmd_nvenc = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", str(origem),
        "-filter_complex", fc_str,
        "-map", "[vout]", "-map", "[aout]",
        "-c:v", "h264_nvenc", "-preset", "p2", "-rc", "vbr", "-cq", "18", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k", "-ar", "48000",
        str(destino),
    ]
    if subprocess.run(cmd_nvenc).returncode != 0:
        cmd_cpu = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-i", str(origem),
            "-filter_complex", fc_str,
            "-map", "[vout]", "-map", "[aout]",
            "-c:v", "libx264", "-crf", "18", "-preset", "veryfast", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k", "-ar", "48000",
            str(destino),
        ]
        subprocess.run(cmd_cpu, check=True)
    return destino


def _extrair_lista_falas(falas_json: dict[str, Any], qtd_clipes: int) -> list[str]:
    """Lê as falas pedidas por clipe a partir do falas.json."""
    if isinstance(falas_json.get("takes"), list):
        return [
            (t.get("fala") if isinstance(t, dict) else str(t))
            for t in falas_json["takes"]
        ]
    if isinstance(falas_json.get("falas"), list):
        return [str(x) for x in falas_json["falas"]]
    if isinstance(falas_json.get("fala"), list):
        return [str(x) for x in falas_json["fala"]]
    if isinstance(falas_json.get("fala"), str) and "||" in falas_json["fala"]:
        return [x.strip() for x in falas_json["fala"].split("||") if x.strip()]
    if isinstance(falas_json.get("fala"), str):
        return [falas_json["fala"]] * qtd_clipes
    return [""] * qtd_clipes


def processar_transcricao_e_cortes_pasta(
    pasta_entregue: Path,
    pasta_trabalho: Path,
    whisper_model: str = "small",
) -> dict[str, Any]:
    """
    Executa a Etapa 2 da Edição em uma pasta entregue (1.mp4, 2.mp4... + falas.json).
    Nunca altera nem apaga os originais em pasta_entregue.
    Salva os clipes cortados (sem pausas acústicas e com cadência dinâmica) e o relatorio_etapa2.json.
    """
    falas_path = pasta_entregue / "falas.json"
    if not falas_path.exists():
        raise FileNotFoundError(f"falas.json ausente em {pasta_entregue}")

    falas_json = json.loads(falas_path.read_text(encoding="utf-8"))
    clipes = sorted(
        [p for p in pasta_entregue.glob("*.mp4") if re.fullmatch(r"\d+\.mp4", p.name)],
        key=lambda p: int(p.stem),
    )
    if not clipes:
        raise FileNotFoundError(f"Nenhum clipe numerado (1.mp4, 2.mp4...) encontrado em {pasta_entregue}")

    falas_pedidas = _extrair_lista_falas(falas_json, len(clipes))
    cortados_dir = pasta_trabalho / "cortados"
    cortados_dir.mkdir(parents=True, exist_ok=True)

    resultados_clipes = []
    qualquer_revisao = False
    motivos_gerais = []

    n_clipes = len(clipes)
    for idx, clipe_path in enumerate(clipes):
        fala_pedida = falas_pedidas[idx] if idx < len(falas_pedidas) else ""
        analise_clipe = calcular_cortes_clipe(clipe_path, fala_pedida, whisper_model=whisper_model)

        if "erro" not in analise_clipe:
            destino_cortado = cortados_dir / clipe_path.name
            eh_meio = 0 < idx < (n_clipes - 1)
            cortar_clipe_ffmpeg(
                origem=clipe_path,
                destino=destino_cortado,
                inicio_s=analise_clipe["inicio_corte_s"],
                fim_s=analise_clipe["fim_corte_s"],
                segmentos_ativos=analise_clipe.get("segmentos_ativos"),
                fator_velocidade=analise_clipe.get("fator_velocidade", 1.0),
                aplicar_micro_zoom_jumpcut=eh_meio,
            )
            analise_clipe["arquivo_cortado"] = str(destino_cortado)

        if analise_clipe.get("marcar_para_revisao"):
            qualquer_revisao = True
            motivos_gerais.append(f"{clipe_path.name}: {analise_clipe.get('motivo_revisao')}")

        resultados_clipes.append(analise_clipe)

    relatorio = {
        "pasta_origem": str(pasta_entregue),
        "formato": falas_json.get("formato", "indefinido"),
        "avatar": falas_json.get("avatar", "indefinido"),
        "qtd_clipes": len(clipes),
        "marcado_para_revisao": qualquer_revisao,
        "motivos_revisao": motivos_gerais,
        "clipes": resultados_clipes,
    }

    relatorio_path = pasta_trabalho / "relatorio_etapa2.json"
    relatorio_path.write_text(json.dumps(relatorio, ensure_ascii=False, indent=2), encoding="utf-8")
    return relatorio
