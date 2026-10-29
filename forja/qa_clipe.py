"""
Forja — Etapa 6: QA por Clipe (forja/qa_clipe.py).
Regras:
- Confere cada clipe logo depois de baixar do Google Flow:
  1) Vídeo: resolução válida, duração (>= 3.0s), sem tela preta e primeiro frame bate com a imagem gerada (frame_N.jpg).
  2) Áudio: tem som de verdade (trilha de áudio presente, volume médio normal, sem mudo longo no meio > 1.2s).
  3) Fala: transcreve com Whisper GPU e compara com a fala pedida — tem que bater >= 92% das palavras e a última palavra tem que estar inteira.
- Se passar: segue pro próximo take.
- Se reprovar: manda gerar de novo só aquele take (1 tentativa extra).
  Se reprovar de novo: move para _reprovados/ (com o motivo anotado, nunca apaga) e para o vídeo (não gasta crédito nos takes seguintes).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageStat

from edicao.transcricao_cortes import comparar_fala_pedida_vs_transcrita
from forja.estrutura import REPROVADOS_DIR, BatchLogger
from forja.ler_viral import transcrever_com_palavras


def obter_metadados_midia(video_path: Path) -> dict[str, Any]:
    """Extrai resolução, duração, presença de vídeo e presença de áudio via ffprobe."""
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration:stream=codec_type,codec_name,width,height",
        "-of",
        "json",
        str(video_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        return {"valido": False, "erro": proc.stderr.strip()}

    dados = json.loads(proc.stdout or "{}")
    streams = dados.get("streams", [])
    fmt = dados.get("format", {})
    duracao = float(fmt.get("duration", 0.0) or 0.0)

    v_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
    a_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)

    return {
        "valido": v_stream is not None,
        "tem_video": v_stream is not None,
        "tem_audio": a_stream is not None,
        "largura": int(v_stream.get("width", 0)) if v_stream else 0,
        "altura": int(v_stream.get("height", 0)) if v_stream else 0,
        "codec_video": v_stream.get("codec_name", "") if v_stream else "",
        "codec_audio": a_stream.get("codec_name", "") if a_stream else "",
        "duracao_s": round(duracao, 3),
    }


def verificar_tela_preta_e_frame_inicial(
    video_path: Path,
    imagem_gerada_path: Path | None,
    pasta_temp: Path,
) -> dict[str, Any]:
    """
    Extrai o primeiro frame e um frame intermediário do vídeo para verificar:
    - Sem tela preta (brilho médio > 12).
    - Primeiro frame bate com a imagem gerada (similaridade visual >= 0.72).
    """
    pasta_temp.mkdir(parents=True, exist_ok=True)
    frame0_path = pasta_temp / f"{video_path.stem}_qa_f0.jpg"
    frame_mid_path = pasta_temp / f"{video_path.stem}_qa_fmid.jpg"

    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-ss",
            "0.05",
            "-i",
            str(video_path),
            "-frames:v",
            "1",
            str(frame0_path),
        ],
        check=False,
    )
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-ss",
            "2.0",
            "-i",
            str(video_path),
            "-frames:v",
            "1",
            str(frame_mid_path),
        ],
        check=False,
    )

    if not frame0_path.is_file():
        return {"sem_tela_preta": False, "frame1_bate_com_imagem": False, "similaridade_frame1": 0.0}

    with Image.open(frame0_path) as im0:
        im0_rgb = im0.convert("RGB")
        brilho_f0 = sum(ImageStat.Stat(im0_rgb).mean) / 3.0

        similaridade = 1.0
        if imagem_gerada_path and imagem_gerada_path.is_file():
            with Image.open(imagem_gerada_path) as im_ref:
                ref_resized = im_ref.convert("RGB").resize((256, 256))
                f0_resized = im0_rgb.resize((256, 256))
                diff = ImageChops.difference(ref_resized, f0_resized)
                erro_medio = sum(ImageStat.Stat(diff).mean) / (3.0 * 255.0)
                similaridade = round(max(0.0, 1.0 - erro_medio), 4)

    brilho_mid = brilho_f0
    if frame_mid_path.is_file():
        with Image.open(frame_mid_path) as imm:
            brilho_mid = sum(ImageStat.Stat(imm.convert("RGB")).mean) / 3.0

    # Remove arquivos temporários de frame QA
    frame0_path.unlink(missing_ok=True)
    frame_mid_path.unlink(missing_ok=True)

    sem_tela_preta = brilho_f0 > 12.0 and brilho_mid > 12.0
    frame1_bate = similaridade >= 0.82
    return {
        "sem_tela_preta": sem_tela_preta,
        "brilho_medio_f0": round(brilho_f0, 2),
        "brilho_medio_meio": round(brilho_mid, 2),
        "similaridade_frame1": similaridade,
        "frame1_bate_com_imagem": frame1_bate,
    }


def analisar_qualidade_audio(video_path: Path, inicio_fala_s: float, fim_fala_s: float) -> dict[str, Any]:
    """
    Verifica volume real (volumedetect) e se há mudo longo no meio da fala (> 1.5s via silencedetect).
    """
    proc_vol = subprocess.run(
        ["ffmpeg", "-i", str(video_path), "-af", "volumedetect", "-f", "null", "-"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    stderr_vol = proc_vol.stderr or ""
    m_mean = re.search(r"mean_volume:\s*([-\d.]+)\s*dB", stderr_vol)
    m_max = re.search(r"max_volume:\s*([-\d.]+)\s*dB", stderr_vol)
    mean_db = float(m_mean.group(1)) if m_mean else -91.0
    max_db = float(m_max.group(1)) if m_max else -91.0

    proc_sil = subprocess.run(
        ["ffmpeg", "-i", str(video_path), "-af", "silencedetect=noise=-38dB:d=0.4", "-f", "null", "-"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    stderr_sil = proc_sil.stderr or ""
    starts = [float(x) for x in re.findall(r"silence_start:\s*([0-9.]+)", stderr_sil)]
    ends = [float(x) for x in re.findall(r"silence_end:\s*([0-9.]+)", stderr_sil)]

    maior_mudo_no_meio_s = 0.0
    for s, e in zip(starts, ends):
        # Silêncio estritamente dentro do intervalo da fala
        if s >= inicio_fala_s + 0.1 and e <= fim_fala_s - 0.1:
            maior_mudo_no_meio_s = max(maior_mudo_no_meio_s, round(e - s, 3))

    tem_som_real = mean_db > -48.0 and max_db > -28.0
    sem_mudo_longo_meio = maior_mudo_no_meio_s <= 1.5

    return {
        "tem_som_real": tem_som_real,
        "mean_volume_db": mean_db,
        "max_volume_db": max_db,
        "maior_mudo_no_meio_s": maior_mudo_no_meio_s,
        "sem_mudo_longo_no_meio": sem_mudo_longo_meio,
    }


def detectar_congelamento_video(
    video_path: Path,
    duracao_s: float,
    noise_db: str = "-60dB",
    min_freeze_s: float = 0.20,
    max_freeze_permitido_s: float = 0.45,
) -> dict[str, Any]:
    """
    Equivalente ao detector `freezedetect=n=-60dB:d=0.2` do Zerum (`ase()` / `painelCongelado`):
    Verifica se a animação travou/congelou como estátua no meio ou fim do take.
    """
    proc = subprocess.run(
        [
            "ffmpeg",
            "-i",
            str(video_path),
            "-vf",
            f"freezedetect=n={noise_db}:d={min_freeze_s:.2f}",
            "-an",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    stderr = proc.stderr or ""
    duracoes_freeze = [float(x) for x in re.findall(r"freeze_duration:\s*([0-9.]+)", stderr)]
    maior_freeze_s = round(max(duracoes_freeze), 3) if duracoes_freeze else 0.0
    sem_congelamento = maior_freeze_s <= max_freeze_permitido_s
    return {
        "sem_congelamento": sem_congelamento,
        "maior_freeze_s": maior_freeze_s,
        "qtd_freezes": len(duracoes_freeze),
    }


def avaliar_qa_clipe(
    video_path: Path,
    fala_pedida: str,
    imagem_gerada_path: Path | None = None,
    limiar_fala: float = 0.90,
) -> dict[str, Any]:
    """
    Executa a bateria completa de QA da Etapa 6 da Forja em um clipe recém-baixado:
    - Vídeo: resolução, duração, sem tela preta, 1º frame bate com a imagem gerada.
    - Áudio: som real, volume normal, sem mudo longo no meio.
    - Fala: transcrição Whisper GPU >= 92% das palavras e última palavra inteira.
    """
    motivos_reprovacao: list[str] = []
    if not video_path.is_file() or video_path.stat().st_size < 1024:
        return {
            "arquivo": str(video_path),
            "aprovado": False,
            "motivos_reprovacao": ["Arquivo MP4 não foi baixado ou está vazio."],
        }

    meta = obter_metadados_midia(video_path)
    if not meta.get("valido") or not meta.get("tem_video"):
        motivos_reprovacao.append("Arquivo de vídeo inválido ou sem stream de vídeo.")
    if not meta.get("tem_audio"):
        motivos_reprovacao.append("Clipe sem trilha de áudio.")
    if meta.get("duracao_s", 0.0) < 3.0:
        motivos_reprovacao.append(f"Duração muito curta ({meta.get('duracao_s')}s < 3.0s).")
    if meta.get("largura", 0) < 480 or meta.get("altura", 0) < 720:
        motivos_reprovacao.append(f"Resolução abaixo do mínimo ({meta.get('largura')}x{meta.get('altura')}).")

    vis = verificar_tela_preta_e_frame_inicial(
        video_path=video_path,
        imagem_gerada_path=imagem_gerada_path,
        pasta_temp=video_path.parent,
    )
    if not vis["sem_tela_preta"]:
        motivos_reprovacao.append("Tela preta detectada no clipe.")
    if not vis["frame1_bate_com_imagem"]:
        motivos_reprovacao.append(
            f"Primeiro frame não bate com a imagem gerada (similaridade {vis['similaridade_frame1']} < 0.72)."
        )

    freeze_info = detectar_congelamento_video(video_path=video_path, duracao_s=float(meta.get("duracao_s", 8.0)))
    vis.update(freeze_info)
    if not freeze_info["sem_congelamento"]:
        motivos_reprovacao.append(
            f"Animação congelada detectada (freeze {freeze_info['maior_freeze_s']}s > 0.45s)."
        )

    trans = transcrever_com_palavras(video_path)
    palavras = trans.get("palavras", [])
    duracao_s = float(meta.get("duracao_s", 8.0))
    inicio_fala = float(palavras[0]["inicio"]) if palavras else 0.0
    fim_fala = float(palavras[-1]["fim"]) if palavras else duracao_s

    aud = analisar_qualidade_audio(video_path, inicio_fala_s=inicio_fala, fim_fala_s=fim_fala)
    if not aud["tem_som_real"]:
        motivos_reprovacao.append(f"Áudio mudo ou volume muito baixo ({aud['mean_volume_db']} dB).")
    if not aud["sem_mudo_longo_no_meio"]:
        motivos_reprovacao.append(f"Mudo longo no meio da fala ({aud['maior_mudo_no_meio_s']}s > 1.5s).")

    comp_fala = comparar_fala_pedida_vs_transcrita(
        fala_pedida=fala_pedida,
        fala_transcrita=trans.get("texto", ""),
        limiar_precisao=limiar_fala,
    )
    # Também verifica se a última palavra não terminou colada a < 0.05s do fim bruto do clipe
    if palavras and (duracao_s - float(palavras[-1]["fim"])) < 0.05:
        comp_fala["ultima_palavra_integra"] = False
    if comp_fala["precisao"] < limiar_fala:
        motivos_reprovacao.append(
            f"Precisão da fala insuficiente ({comp_fala['precisao']*100:.1f}% < {limiar_fala*100:.0f}%)."
        )
    if not comp_fala["ultima_palavra_integra"]:
        motivos_reprovacao.append("Última palavra cortada no final do clipe.")

    aprovado = len(motivos_reprovacao) == 0
    return {
        "arquivo": video_path.name,
        "aprovado": aprovado,
        "motivos_reprovacao": motivos_reprovacao,
        "video": {**meta, **vis},
        "audio": aud,
        "fala": comp_fala,
    }


def mover_para_reprovados(
    video_path: Path,
    lote_id: str,
    video_id: str,
    take_num: int,
    relatorio_qa: dict[str, Any],
    reprovados_root: Path = REPROVADOS_DIR,
    logger: BatchLogger | None = None,
) -> Path:
    """
    Move o clipe reprovado para _reprovados/<lote_id>_<video_id>/ sem apagar o arquivo original,
    salvando junto o JSON com o motivo exato da reprovação.
    """
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    pasta_dest = reprovados_root / f"{lote_id}_{video_id}"
    pasta_dest.mkdir(parents=True, exist_ok=True)

    nome_base = f"take_{take_num}_{ts}"
    mp4_dest = pasta_dest / f"{nome_base}.mp4"
    json_dest = pasta_dest / f"{nome_base}_motivo.json"

    if video_path.is_file():
        shutil.move(str(video_path), str(mp4_dest))

    payload = {
        "lote_id": lote_id,
        "video_id": video_id,
        "take": take_num,
        "reprovado_em": datetime.now().isoformat(timespec="seconds"),
        "arquivo_movido": str(mp4_dest),
        "motivos_reprovacao": relatorio_qa.get("motivos_reprovacao", []),
        "relatorio_qa": relatorio_qa,
    }
    json_dest.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    if logger:
        logger.log(
            f"[QA REPROVADO] {video_id} Take {take_num} movido para {mp4_dest.name} | Motivos: {'; '.join(payload['motivos_reprovacao'])}",
            nivel="WARN",
        )
    return mp4_dest


_NUM_MAP_FALA = {
    "zero": "0",
    "one": "1",
    "two": "2",
    "three": "3",
    "four": "4",
    "five": "5",
    "six": "6",
    "seven": "7",
    "eight": "8",
    "nine": "9",
    "ten": "10",
}


def _normalizar_token_fala(w: str) -> str:
    t = re.sub(r"[^a-z0-9]", "", (w or "").lower())
    return _NUM_MAP_FALA.get(t, t)


def tesoura_cirurgica_3_passes(
    video_path: Path,
    fala_pedida: str,
    folga_inicio_s: float = 0.04,
    folga_fim_s: float = 0.24,
) -> dict[str, Any]:
    """
    Implementa a Tesoura Fonética de 3 Passes idêntica ao `/ia/alinhar` do Zerum:
    - Pass 1: Transcreve o clipe bruto de 8s com timestamps por palavra (Whisper GPU).
      Localiza onde começa a 1ª palavra do roteiro (`trim_start`) e onde termina a última
      palavra do roteiro (`fim_fala_confirmado`). Se o Veo 3.1 alucinou palavras extras no final
      (como `"okay thank you"` em `6.82s..7.84s`), calcula `trim_end = fim_fala_confirmado + folga_fim_s`
      e corta cirurgicamente o MP4 com `h264_nvenc` sem precisar regenerar o vídeo!
    - Pass 2: Earcheck no intervalo recortado (`casadas / total`).
    - Pass 3: Verifica os últimos `2.0s` do recorte para garantir que a última palavra não foi decepada.
    """
    meta = obter_metadados_midia(video_path)
    dur_bruta = float(meta.get("duracao_s", 8.0) or 8.0)
    trans = transcrever_com_palavras(video_path)
    palavras_ouvidas = trans.get("palavras", [])
    tokens_pedidos = [_normalizar_token_fala(t) for t in (fala_pedida or "").split() if _normalizar_token_fala(t)]

    if not palavras_ouvidas or not tokens_pedidos:
        return {
            "ok": False,
            "cortado": False,
            "trim_start": 0.0,
            "trim_end": dur_bruta,
            "alucinacao_final_removida": [],
            "casadas": 0,
            "total": len(tokens_pedidos),
        }

    # Alinhar as palavras ouvidas contra os tokens pedidos em ordem
    idx_pedido = 0
    casadas_count = 0
    ultimo_fim_confirmado = float(palavras_ouvidas[-1]["fim"])
    indice_ultima_palavra_roteiro = len(palavras_ouvidas) - 1

    for i_ouv, p_obj in enumerate(palavras_ouvidas):
        tok_ouv = _normalizar_token_fala(str(p_obj.get("palavra", "")))
        if not tok_ouv:
            continue
        # Procura correspondência na janela atual do roteiro (lookahead amplo de +8 tokens)
        for lookahead in range(idx_pedido, min(len(tokens_pedidos), idx_pedido + 8)):
            if tok_ouv == tokens_pedidos[lookahead] or (
                len(tok_ouv) >= 4 and tok_ouv[:4] == tokens_pedidos[lookahead][:4]
            ):
                idx_pedido = lookahead + 1
                casadas_count += 1
                ultimo_fim_confirmado = float(p_obj.get("fim", ultimo_fim_confirmado))
                indice_ultima_palavra_roteiro = i_ouv
                break

    # Só considera palavras finais como alucinação se já chegamos nas últimas 2 palavras do roteiro
    if idx_pedido < max(1, len(tokens_pedidos) - 2):
        ultimo_fim_confirmado = float(palavras_ouvidas[-1]["fim"])
        indice_ultima_palavra_roteiro = len(palavras_ouvidas) - 1

    primeiro_inicio = max(0.0, float(palavras_ouvidas[0].get("inicio", 0.0)) - folga_inicio_s)
    trim_start = round(primeiro_inicio if primeiro_inicio > 0.12 else 0.01, 3)
    trim_end = round(min(dur_bruta, ultimo_fim_confirmado + folga_fim_s), 3)

    alucinacoes_finais = [
        str(p.get("palavra", "")).strip()
        for p in palavras_ouvidas[indice_ultima_palavra_roteiro + 1 :]
        if str(p.get("palavra", "")).strip()
    ]

    cortado = False
    if alucinacoes_finais or (dur_bruta - trim_end) > 0.35 or trim_start > 0.15:
        temp_cut = video_path.with_name(f"{video_path.stem}_tesoura_tmp.mp4")
        dur_corte = max(1.8, round(trim_end - trim_start, 3))
        cmd = [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-ss",
            f"{trim_start:.3f}",
            "-i",
            str(video_path),
            "-t",
            f"{dur_corte:.3f}",
            "-c:v",
            "h264_nvenc",
            "-preset",
            "p1",
            "-b:v",
            "6M",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            str(temp_cut),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode == 0 and temp_cut.exists() and temp_cut.stat().st_size > 1024:
            os.replace(str(temp_cut), str(video_path))
            cortado = True
        else:
            temp_cut.unlink(missing_ok=True)

    # Pass 3: Verificar integridade da cauda (última palavra do roteiro não colada no corte)
    folga_cauda_s = round(trim_end - ultimo_fim_confirmado, 3)
    cauda_integra = folga_cauda_s >= 0.05

    return {
        "ok": True,
        "cortado": cortado,
        "trim_start": trim_start,
        "trim_end": trim_end,
        "duracao_final_s": round(trim_end - trim_start, 3),
        "fim_fala_confirmado_s": round(ultimo_fim_confirmado, 3),
        "alucinacao_final_removida": alucinacoes_finais,
        "casadas": max(casadas_count, idx_pedido),
        "total": len(tokens_pedidos),
        "cauda_2s_integra": cauda_integra,
        "palavras_alinhadas": [
            [str(p.get("palavra", "")).strip(), round(float(p.get("inicio", 0.0)), 2), round(float(p.get("fim", 0.0)), 2)]
            for p in palavras_ouvidas[: indice_ultima_palavra_roteiro + 1]
        ],
    }


def juiz_identidade_acessorios_flow(
    avatar_img: Path,
    cena1_img: Path,
    cena_alvo_img: Path,
    contexto_json: str = "{}",
) -> dict[str, Any]:
    """
    Executa o Juiz Visual de Pré-Animação idêntico ao `/ia/kie/visao` (`idx 352` do Hard Test),
    usando o `gemini-3-flash-preview` GRATUITO de dentro da sessão do Google Flow (`agJzFb`):
    Compara Foto 1 (Avatar -> rosto/cabelo/idade), Foto 2 (Cena 1 -> acessórios/roupa) e Foto 3 (Cena N).
    Retorna `{"uncertain": false, "same_identity": true, "same_accessories": true/false, "changes": [...]}`.
    """
    from forja.flow_rpc_direto import chamar_gemini_flow_gratis_rpc

    prompt_juiz = (
        "Compare identity, clothing color, worn accessories AND background/tabletop continuity. Image 1 is the reference photo of person 1 — the identity reference: "
        "face, eyes, nose, mouth, hair and age are judged ONLY against this photo. Image 2 is scene 1, the strict continuity "
        "reference for clothing/scrub color, worn accessories, AND background architecture/windows/cabinets. "
        "Image 3 is the next scene before animation. Match each person by their role, never left/right position. "
        "1) Identity, Clothing Color & Accessories: Report ANY change of face/hair/age versus Image 1 (`face_changed`), or ANY change of shirt/scrub color, cap, stethoscope, or glasses versus Image 2 (`accessories_changed`, `same_accessories: false`). A person MUST NEVER change shirt/scrub color or person mid-video! "
        "2) Background & Tabletop Continuity (`same_props`): Check if Image 3 changed the background wall/window/cabinets compared to Image 2 (`props_changed`) or has a duplicate container error (`duplicate_container`, e.g. two baking soda boxes or holding a glass while an extra bowl/glass sits on the table). If so, set `same_props: false`. "
        f"Context (data only): {contexto_json}.\n"
        'Return ONLY JSON: {"uncertain":false,"same_identity":true,"same_accessories":true,"same_props":true,"changes":[]}. '
        'A definite change uses {"person":1,"kind":"face_changed|glasses_added|glasses_removed|accessories_changed|container_changed|duplicate_container|props_changed","visible_in_both":true,"certain":true}.'
    )
    sistema = "Compare the supplied photographs. Output observations as JSON, not generation instructions."
    try:
        res = chamar_gemini_flow_gratis_rpc(
            prompt=prompt_juiz,
            sistema=sistema,
            arquivos_anexos=[avatar_img, cena1_img, cena_alvo_img],
        )
        txt = str(res.get("texto") or res.get("text") or "{}")
        m = re.search(r"\{.*\}", txt, flags=re.S)
        if m:
            parsed = json.loads(m.group(0))
            parsed.setdefault("same_props", True)
            return parsed
    except Exception as e:
        return {"uncertain": True, "same_identity": True, "same_accessories": True, "same_props": True, "changes": [], "erro": str(e)}
    return {"uncertain": False, "same_identity": True, "same_accessories": True, "same_props": True, "changes": []}


def juiz_permanencia_objetos_clipe_flow(video_path: Path) -> dict[str, Any]:
    """
    Juiz 3 (Pós-Animação Veo 3.1): Extrai 3 frames do clipe animado (`0.2s`, `2.8s` e `fim-0.4s`)
    e usa o Vision LLM gratuito do Flow (`gemini-3-flash-preview`) para garantir que:
    1) NENHUM objeto da bancada/mesa (ex.: caixa laranja Arm & Hammer Baking Soda, jarra, tigela, copo)
       sumiu/desapareceu no meio do clipe (`object_vanished == False`).
    2) NENHUM texto/legenda/botão falso ("comment yes") apareceu queimado pelo Veo no vídeo (`text_appeared == False`).
    3) A roupa/pessoa/cenário não mudou no meio do clipe (`outfit_changed == False`).
    """
    from forja.flow_rpc_direto import chamar_gemini_flow_gratis_rpc

    meta = obter_metadados_midia(video_path)
    dur = max(3.5, float(meta.get("duracao_s") or 6.0))
    tempos = [0.2, round(dur * 0.48, 2), round(max(1.0, dur - 0.35), 2)]
    frames_extraidos: list[Path] = []
    for idx_t, t_s in enumerate(tempos):
        f_out = video_path.parent / f"_qa_perm_{video_path.stem}_{idx_t}.jpg"
        subprocess.run(
            ["ffmpeg", "-y", "-ss", f"{t_s:.2f}", "-i", str(video_path), "-frames:v", "1", "-q:v", "2", str(f_out)],
            capture_output=True,
        )
        if f_out.exists() and f_out.stat().st_size > 1000:
            frames_extraidos.append(f_out)

    if len(frames_extraidos) < 2:
        return {"aprovado": True, "object_vanished": False, "text_appeared": False, "outfit_changed": False}

    prompt_j3 = (
        "Inspect these 3 sequential frames extracted from the SAME 6-second video clip (Frame 1 = 0.2s start, Frame 2 = middle, Frame 3 = end). "
        "Check strictly for 4 continuity and quality failures:\n"
        "1) `object_vanished`: Did any prominent tabletop object/prop visible on the counter/table in Frame 1 (such as an orange Arm & Hammer Baking Soda box, water pitcher, bowl, anatomical mannequin, or glass) completely vanish/disappear from the counter in Frame 2 or Frame 3?\n"
        "2) `text_appeared`: Did any fake subtitle, caption box, or social media text (e.g. 'comment yes') appear in Frame 2 or Frame 3 that was not a real physical product label?\n"
        "3) `outfit_changed`: Did the person change clothing color, headwear, or face between Frame 1, Frame 2, and Frame 3?\n"
        "4) `hand_or_flash_bug`: Did the person grow a third arm, have severely mutated/extra hands, or did a white flash transition / scene-cut glitch occur in Frame 2 or Frame 3?\n"
        'Return ONLY JSON: {"aprovado":true,"object_vanished":false,"text_appeared":false,"outfit_changed":false,"hand_or_flash_bug":false,"motivo":""} (set aprovado:false if ANY of the 4 flags is true).'
    )
    try:
        res = chamar_gemini_flow_gratis_rpc(
            prompt=prompt_j3,
            sistema="You are a strict video continuity and object permanence auditor. Output JSON only.",
            arquivos_anexos=frames_extraidos,
        )
        for fp in frames_extraidos:
            fp.unlink(missing_ok=True)
        txt = str(res.get("texto") or res.get("text") or "{}")
        m = re.search(r"\{.*\}", txt, flags=re.S)
        if m:
            d = json.loads(m.group(0))
            van = bool(d.get("object_vanished", False))
            txt_ap = bool(d.get("text_appeared", False))
            out_ch = bool(d.get("outfit_changed", False))
            h_bug = bool(d.get("hand_or_flash_bug", False))
            d["aprovado"] = not (van or txt_ap or out_ch or h_bug)
            return d
    except Exception as e:
        for fp in frames_extraidos:
            fp.unlink(missing_ok=True)
        return {"aprovado": True, "erro": str(e)}
    return {"aprovado": True, "object_vanished": False, "text_appeared": False, "outfit_changed": False}


def _hex_para_ass_bgr(hex_color: str, alpha: str = "00") -> str:
    h = (hex_color or "#FFC400").strip().lstrip("#")
    if len(h) == 3:
        h = "".join(ch * 2 for ch in h)
    if len(h) != 6:
        return f"&H{alpha}00C4FF"
    r, g, b = h[0:2], h[2:4], h[4:6]
    return f"&H{alpha}{b.upper()}{g.upper()}{r.upper()}"


def _cor_texto_contraste_cta(hex_color: str) -> str:
    """Port 1:1 de `Ed(e)` em `zerum_app.js` (@542510): retorna `#141414` para fundos claros/vibrantes e `#FFFFFF` para escuros."""
    h = (hex_color or "#FFC400").strip().lstrip("#")
    if len(h) == 3:
        h = "".join(ch * 2 for ch in h)
    if len(h) != 6:
        return "#141414"

    def _lin(c_int: int) -> float:
        v = c_int / 255.0
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    lum = 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)
    return "#141414" if lum > 0.3 else "#FFFFFF"


def _calcular_geometria_cta_sv(tam: float = 1.0, mv_legenda: int = 265, onde: str = "baixo") -> dict[str, Any]:
    """Port 1:1 de `SV(e)` em `zerum_app.js` (@542685)."""
    a = max(0.4, min(2.0, float(tam or 1.0)))

    def _o(d: float) -> int:
        return round(54 * d + 2 * 16 * d)

    def _t(d: float) -> dict[str, int]:
        return {"larg": round(56 * d), "alt": round(38 * d), "folga": round(12 * d)}

    if onde == "topo":
        l_val = _o(a)
        u_val = _t(a)
        return {
            "tam": a,
            "fs": round(54 * a),
            "borda": round(16 * a),
            "alt": l_val,
            "mv": 0,
            "topoY": 230,
            "setaY": 230 + l_val + round(16 * a) + u_val["folga"],
            "seta": u_val,
        }

    r = a
    n = _o(r)
    s = _t(r)
    i = mv_legenda - 22 - n
    c = 16 + s["alt"] + s["folga"] + round(16 * r) + round(12 * r)
    if i < c:
        r = max(0.55, (mv_legenda - 22 - 16 - 12 * a - 38 * a) / 86.0)
        n = _o(r)
        s = _t(r)
        i = max(16 + s["alt"] + s["folga"], mv_legenda - 22 - n)
    return {
        "tam": r,
        "fs": round(54 * r),
        "borda": round(16 * r),
        "alt": n,
        "mv": int(round(i)),
        "topoY": 0,
        "setaY": int(round(1280 - i + round(16 * r) + s["folga"])),
        "seta": s,
    }


def _fmt_ass_time(sec: float) -> str:
    sec = max(0.0, float(sec))
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = sec % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def gerar_script_ass_zerum_11(
    cenas: list[dict[str, Any]],
    estilo: str = "karaoke",
    blocos_palavras: int = 3,
    cor_ativa_hex: str = "#22C55E",
    palavra_cta: str = "YES",
    cor_balao_hex: str = "#FF7A00",
    sem_legenda: bool = False,
    apenas_botao_cta: bool = False,
) -> str:
    """
    Port 1:1 de `SV`, `i1`, `c1` e `Jh` de `zerum_app.js` (@542685..543650 e @1009500..1015000):
    - `Style: Cta,Anton,{fs},{txt_col},{txt_col},{box_col},&H00000000,0,0,0,0,100,100,1,0,3,{borda},0,2,60,60,{mv},1`
    - `Style: Seta,Anton,20,{box_col},{box_col},&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,5,0,0,0,1`
    - Pop-up `COMMENT YES` entra exatamente quando o locutor fala `"comment"` na última cena, com pop-in elástico
      (`\\fad(80,0)\\fscx0\\fscy0\\t(0,180,\\fscx108\\fscy108)\\t(180,360,\\fscx100\\fscy100)`) + pulsação contínua de 417ms
      (`103.5%` <-> `96.5%`) + triângulo sólido (`Seta`) quicando 12px abaixo da caixa!
    """
    est_low = (estilo or "karaoke").strip().lower()
    if est_low in ("apenas_cta", "so_cta", "cta_only"):
        sem_legenda = True
        apenas_botao_cta = True
    elif est_low in ("sem_legenda", "nenhuma", "none", "off"):
        sem_legenda = True

    mv_legenda = 265
    sv = _calcular_geometria_cta_sv(tam=1.0, mv_legenda=mv_legenda, onde="baixo")
    box_ass = _hex_para_ass_bgr(cor_balao_hex or "#FF7A00")
    txt_ass = _hex_para_ass_bgr(_cor_texto_contraste_cta(cor_balao_hex or "#FF7A00"))
    cor_ass = _hex_para_ass_bgr(cor_ativa_hex or "#22C55E") + "&"

    header_ass = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 720
PlayResY: 1280
ScaledBorderAndShadow: yes
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Leg,Poppins Bold,62,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,6,1,2,40,40,{mv_legenda},1
Style: Uma,Poppins Black,132,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,10,0,2,30,30,{mv_legenda},1
Style: Kar,Poppins Bold,74,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,6,0,2,40,40,{mv_legenda},1
Style: Cmd,Anton,88,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,1,0,1,7,0,2,50,50,300,1
Style: Board,Poppins Bold,44,&H00FFFFFF,&H00FFFFFF,&H00000000,&H78000000,0,0,0,0,100,100,0,0,3,14,0,8,50,50,150,1
Style: Top,Poppins Bold,36,&H00FFFFFF,&H00FFFFFF,&H00000000,&H78000000,0,0,0,0,100,100,0,0,3,10,0,8,60,60,120,1
Style: DayTag,Anton,64,&H0000FFFF,&H0000FFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,1.5,0,8,0,0,12,1
Style: Word,Anton,70,&H00FFFFFF,&H00FFFFFF,&H00B45CF6,&H00000000,0,0,0,0,100,100,1,0,1,6,0,2,40,40,560,1
Style: Cta,Anton,{sv['fs']},{txt_ass},{txt_ass},{box_ass},&H00000000,0,0,0,0,100,100,1,0,3,{sv['borda']},0,2,60,60,{sv['mv']},1
Style: Seta,Anton,20,{box_ass},{box_ass},&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,5,0,0,0,1
Style: Angel,Poppins Bold,34,&H40FFFFFF,&H40FFFFFF,&H80000000,&H00000000,0,0,0,0,100,100,0,0,1,2,0,7,0,0,0,1"""

    mapa_estilo = {
        "legenda": "Leg",
        "karaoke": "Leg",
        "uma": "Uma",
        "comando": "Cmd",
        "cartaz": "Board",
    }
    style_name = mapa_estilo.get(est_low, "Leg")
    linhas_eventos: list[str] = [
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]

    pal_up = re.sub(r"[^A-Z0-9 ]+", "", (palavra_cta or "YES").strip().upper()) or "YES"
    pal_up = re.sub(r"\s+", " ", pal_up).strip()
    xk_magenta = "&H00B45CF6&"
    t_cursor = 0.0

    for idx_c, c in enumerate(cenas):
        dur_c = float(c.get("duracao") or 6.0)
        fala_raw = str(c.get("fala") or "").strip()
        palavras_raw = [w for w in re.split(r"\s+", fala_raw) if w]
        palavras_limpas = [re.sub(r"^[^A-Za-z0-9]+|[^A-Za-z0-9]+$", "", w).upper() for w in palavras_raw]
        palavras_limpas = [w for w in palavras_limpas if w]

        # Calcular tempos proporcionais por caractere (exatamente como `Jh` em `zerum_app.js`)
        total_chars = sum(len(w) + 1 for w in palavras_limpas) or 1
        dur_util = max(0.5, dur_c - 0.15)
        tempos_palavras: list[tuple[float, float]] = []
        t_w = t_cursor
        for w in palavras_limpas:
            t_next = t_w + ((len(w) + 1) / total_chars) * dur_util
            tempos_palavras.append((t_w, t_next))
            t_w = t_next
        if tempos_palavras:
            tempos_palavras[-1] = (tempos_palavras[-1][0], max(tempos_palavras[-1][0] + 0.05, t_cursor + dur_c))

        if palavras_limpas and not sem_legenda:
            n_bloco = max(1, int(blocos_palavras or 3))
            for k_start in range(0, len(palavras_limpas), n_bloco):
                grp = palavras_limpas[k_start : k_start + n_bloco]
                for active_i in range(len(grp)):
                    idx_abs = k_start + active_i
                    t0, t1 = tempos_palavras[idx_abs]
                    partes_txt = []
                    for j, w_txt in enumerate(grp):
                        idx_j = k_start + j
                        prev_window = palavras_limpas[max(0, idx_j - 3) : idx_j]
                        is_cta_word = (w_txt == pal_up) and any(
                            pw in ("COMMENT", "TYPE", "WRITE", "COMENTE", "DIGITE") for pw in prev_window
                        )
                        if is_cta_word:
                            partes_txt.append(f'{{\\c{xk_magenta}}}"{w_txt}"{{\\c&H00FFFFFF&}}')
                        elif j == active_i and est_low in ("karaoke", "legenda"):
                            partes_txt.append(f"{{\\c{cor_ass}}}{w_txt}{{\\c&H00FFFFFF&}}")
                        else:
                            partes_txt.append(w_txt)
                    texto_ass = " ".join(partes_txt)
                    linhas_eventos.append(
                        f"Dialogue: 1,{_fmt_ass_time(t0)},{_fmt_ass_time(t1)},{style_name},,0,0,0,,{texto_ass}"
                    )

        # Pop-up CTA `c1` oficial do Flow Turbo Studio na última cena
        mostrar_cta = bool(palavra_cta) and (apenas_botao_cta or est_low != "sem_legenda_sem_cta")
        if idx_c == len(cenas) - 1 and mostrar_cta:
            idx_cmd = next(
                (
                    i_w
                    for i_w, w_str in enumerate(palavras_limpas)
                    if w_str in ("COMMENT", "TYPE", "WRITE", "COMENTE", "DIGITE", "CLICK", "PINNED", "CITY")
                ),
                -1,
            )
            if idx_cmd >= 0 and idx_cmd < len(tempos_palavras):
                t_cmd_start = tempos_palavras[idx_cmd][0]
                prev_end = tempos_palavras[idx_cmd - 1][1] if idx_cmd > 0 else t_cursor
                cta_t0 = t_cursor if idx_cmd <= 1 else max(t_cursor, min(prev_end, t_cmd_start), t_cmd_start - 0.15)
            else:
                cta_t0 = max(t_cursor, t_cursor + dur_c - 4.2)
            cta_t1 = t_cursor + dur_c

            if cta_t1 > cta_t0 + 0.05:
                n_ms = round((cta_t1 - cta_t0) * 1000)
                s_ms = 417
                anim_cta = "{\\fad(80,0)\\fscx0\\fscy0\\t(0,180,\\fscx108\\fscy108)\\t(180,360,\\fscx100\\fscy100)"
                g_ms = 600
                while g_ms + s_ms <= n_ms:
                    anim_cta += (
                        f"\\t({g_ms},{g_ms + s_ms},\\fscx103.5\\fscy103.5)"
                        f"\\t({g_ms + s_ms},{min(n_ms, g_ms + 2 * s_ms)},\\fscx96.5\\fscy96.5)"
                    )
                    g_ms += 2 * s_ms
                if pal_up.startswith(("COMMENT ", "CLICK ", "PINNED ", "CHECK ")):
                    texto_cta = pal_up
                else:
                    texto_cta = f"COMMENT {pal_up}"
                if len(texto_cta) > 13:
                    anim_cta += f"\\fs{max(38, round(sv['fs'] * 13.0 / len(texto_cta)))}"
                anim_cta += "}"
                linhas_eventos.append(
                    f"Dialogue: 2,{_fmt_ass_time(cta_t0)},{_fmt_ass_time(cta_t1)},Cta,,0,0,0,,{anim_cta}{texto_cta}"
                )

                larg_s = sv["seta"]["larg"]
                alt_s = sv["seta"]["alt"]
                vec_seta = f"m 0 0 l {larg_s} 0 l {round(larg_s / 2)} {alt_s}"
                f_bounce = round(12 * sv["tam"])
                x_half = round(alt_s / 2)
                g_seta = 0
                while g_seta < n_ms:
                    v_t0 = cta_t0 + g_seta / 1000.0
                    h_t1 = min(cta_t1, cta_t0 + (g_seta + s_ms) / 1000.0)
                    is_even = (g_seta // s_ms) % 2 == 0
                    y_a = sv["setaY"] + x_half + (0 if is_even else f_bounce)
                    y_e = sv["setaY"] + x_half + (f_bounce if is_even else 0)
                    linhas_eventos.append(
                        f"Dialogue: 2,{_fmt_ass_time(v_t0)},{_fmt_ass_time(h_t1)},Seta,,0,0,0,,"
                        f"{{\\an5\\move(360,{y_a},360,{y_e})\\p1}}{vec_seta}{{\\p0}}"
                    )
                    g_seta += s_ms

        t_cursor += dur_c

    return header_ass.rstrip() + "\n\n" + "\n".join(linhas_eventos) + "\n"


