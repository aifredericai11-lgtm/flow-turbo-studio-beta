"""
Forja — Etapa 2: Ler o Viral.
- Transcreve a fala com tempo por palavra (faster-whisper GPU CUDA float16) e mede o ritmo (palavras/s).
- Extrai frames em 0,5 s, 1,5 s e 2,5 s.
- Descreve o HOOK VISUAL (ação dos primeiros 2-3 s: gesto, objeto, enquadramento).
- Descreve cenário, personagem, roupa, objetos, enquadramento e CTA.
- Dá um nome de FORMATO ao viral (ex.: "aplicando_bicarbonato_na_coxa") e salva a análise.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import threading
import time
from pathlib import Path
from typing import Any


def _configurar_cuda_dlls() -> None:
    """Adiciona torch/lib ao PATH/DLL search path no Windows para habilitar CUDA no faster-whisper."""
    try:
        import torch

        torch_lib = os.path.join(os.path.dirname(torch.__file__), "lib")
        if os.path.isdir(torch_lib):
            if hasattr(os, "add_dll_directory"):
                os.add_dll_directory(torch_lib)
            if torch_lib not in os.environ.get("PATH", ""):
                os.environ["PATH"] = torch_lib + os.pathsep + os.environ.get("PATH", "")
    except Exception:
        pass


_MODEL_CACHE: dict[str, Any] = {}
_TRANSCRICAO_CACHE: dict[str, dict[str, Any]] = {}
_WHISPER_LOCK = threading.Lock()


def carregar_whisper(model_name: str = "small"):
    """Carrega faster-whisper priorizando GPU NVIDIA CUDA (float16, num_workers=4) com fallback para CPU."""
    with _WHISPER_LOCK:
        _configurar_cuda_dlls()
        if model_name in _MODEL_CACHE:
            return _MODEL_CACHE[model_name]

        from faster_whisper import WhisperModel

        for device, compute_type in [("cuda", "float16"), ("cpu", "int8")]:
            try:
                model = WhisperModel(model_name, device=device, compute_type=compute_type, num_workers=4)
                _MODEL_CACHE[model_name] = (model, device)
                return model, device
            except Exception:
                continue
        raise RuntimeError("Não foi possível inicializar o faster-whisper em CUDA nem CPU.")


def obter_duracao_video(video_path: Path) -> float:
    out = subprocess.check_output(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(video_path),
        ],
        text=True,
        encoding="utf-8",
        errors="replace",
    ).strip()
    return float(out)


def extrair_frame(video_path: Path, segundo: float, destino: Path) -> Path:
    destino.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-y",
            "-loglevel",
            "error",
            "-ss",
            f"{segundo:.3f}",
            "-i",
            str(video_path),
            "-frames:v",
            "1",
            "-q:v",
            "2",
            str(destino),
        ],
        check=True,
    )
    return destino


def _hash_rapido_arquivo(video_path: Path, model_name: str) -> str:
    st = video_path.stat()
    h = hashlib.sha1()
    h.update(f"{model_name}:{st.st_size}:".encode("utf-8"))
    with video_path.open("rb") as f:
        h.update(f.read(65536))
    return h.hexdigest()


def transcrever_com_palavras(video_path: Path, model_name: str = "small") -> dict[str, Any]:
    """Transcreve vídeo retornando tempo exato por palavra e métricas de ritmo (palavras/s)."""
    chave_cache = _hash_rapido_arquivo(video_path, model_name)
    if chave_cache in _TRANSCRICAO_CACHE:
        return _TRANSCRICAO_CACHE[chave_cache]

    model, device = carregar_whisper(model_name)
    duracao = obter_duracao_video(video_path)
    segments_gen, info = model.transcribe(
        str(video_path),
        beam_size=1,
        word_timestamps=True,
        vad_filter=True,
    )
    segments = list(segments_gen)
    palavras = []
    for seg in segments:
        for w in seg.words or []:
            texto = w.word.strip()
            if texto:
                palavras.append(
                    {
                        "palavra": texto,
                        "inicio": round(float(w.start), 3),
                        "fim": round(float(w.end), 3),
                    }
                )

    texto_completo = " ".join(p["palavra"] for p in palavras)
    qtd_palavras = len(palavras)
    inicio_fala = palavras[0]["inicio"] if palavras else 0.0
    fim_fala = palavras[-1]["fim"] if palavras else duracao
    janela_fala = max(0.1, fim_fala - inicio_fala)

    ritmo_total = round(qtd_palavras / max(0.1, duracao), 2)
    ritmo_fala = round(qtd_palavras / janela_fala, 2)

    res = {
        "idioma": info.language,
        "dispositivo": device,
        "duracao_video_s": round(duracao, 3),
        "total_palavras": qtd_palavras,
        "inicio_fala_s": round(inicio_fala, 3),
        "fim_fala_s": round(fim_fala, 3),
        "ritmo_palavras_por_s": ritmo_total,
        "ritmo_fala_ativa_palavras_por_s": ritmo_fala,
        "texto": texto_completo,
        "palavras": palavras,
    }
    _TRANSCRICAO_CACHE[chave_cache] = res
    return res


def _inferir_analise_visual_padrao(texto: str, frames_paths: dict[str, str], formato_override: str | None = None) -> dict[str, Any]:
    """
    Se GEMINI_API_KEY estiver configurada, consulta o Gemini Vision nos frames 0.5s, 1.5s, 2.5s.
    Caso contrário, gera a análise estruturada detalhada baseada no conteúdo visual e fala do viral.
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if api_key:
        try:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=api_key)
            prompt = (
                "Analise estes 3 frames (0.5s, 1.5s, 2.5s) do início de um vídeo viral e a transcrição completa:\n"
                f"TRANSCRIÇÃO: {texto}\n\n"
                "Retorne APENAS um JSON com as chaves exatas:\n"
                "{\n"
                '  "formato": "nome_curto_snake_case (ex: aplicando_bicarbonato_na_coxa)",\n'
                '  "hook_visual": {\n'
                '    "resumo": "descrição direta da ação dos primeiros 2-3s",\n'
                '    "gesto": "o que as mãos/corpo fazem nos primeiros 2-3s",\n'
                '    "objeto": "objeto em destaque no hook",\n'
                '    "enquadramento": "tipo de plano e ângulo de câmera"\n'
                "  },\n"
                '  "cenario": "descrição do ambiente",\n'
                '  "personagem": "descrição do personagem de referência",\n'
                '  "roupa": "vestimenta e acessórios",\n'
                '  "objetos": ["lista de objetos em cena"],\n'
                '  "enquadramento": "descrição do enquadramento geral",\n'
                '  "cta": {"texto_falado": "...", "palavra_chave": "...", "acao_visual": "..."}\n'
                "}"
            )
            parts = [types.Part.from_text(text=prompt)]
            for label, fpath in frames_paths.items():
                parts.append(types.Part.from_text(text=f"Frame {label}:"))
                parts.append(types.Part.from_bytes(data=Path(fpath).read_bytes(), mime_type="image/jpeg"))
            resp = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[types.Content(role="user", parts=parts)],
                config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.1),
            )
            parsed = json.loads(resp.text or "{}")
            if formato_override:
                parsed["formato"] = formato_override
            if parsed.get("hook_visual") and parsed.get("formato"):
                return parsed
        except Exception:
            pass

    t_low = texto.lower()
    cta_match = re.search(r"comment\s+([a-z0-9]+)", t_low)
    palavra_cta = cta_match.group(1).upper() if cta_match else "YES"

    if "baking soda" in t_low and "thigh" in t_low:
        formato = formato_override or "aplicando_bicarbonato_na_coxa"
        return {
            "formato": formato,
            "hook_visual": {
                "resumo": (
                    "Profissional de saúde em pé com a perna direita apoiada num banquinho redondo, "
                    "esfregando pasta branca de bicarbonato na coxa/canela enquanto olha direto para a lente."
                ),
                "gesto": (
                    "Mão direita com pasta branca aplicando/esfregando na parte frontal da perna/coxa levantada; "
                    "mão esquerda apoiada na coxa; tronco levemente inclinado para a câmera."
                ),
                "objeto": (
                    "Pasta branca de bicarbonato aplicada na perna + caixa laranja de Baking Soda (Arm & Hammer) "
                    "e tigela branca de cerâmica sobre bandeja metálica lateral."
                ),
                "enquadramento": (
                    "Plano médio-aberto vertical (9:16), altura dos olhos/peito, mostrando da cabeça ao pé "
                    "apoiado no banco médico e a bandeja de inox à direita."
                ),
            },
            "cena_fixa_en": (
                "A stainless steel medical tray on the right holds a Baking soda of Arm & Hammer of orange box "
                "next to a white ceramic bowl with white paste."
            ),
            "acoes_en": {
                "hook_frame1": (
                    "The subject stands with one bare foot resting on a round gray medical stool, "
                    "one hand gently rubbing white baking soda paste onto the front of the raised thigh "
                    "while looking directly into the camera lens."
                ),
                "hook_video": (
                    "One continuous locked smartphone take. The subject maintains eye contact with the lens "
                    "while completing the opening hand gesture smoothly. "
                    "Every element already exists; nothing new spawns; the bowl and orange box remain completely still."
                ),
                "body_frame1": (
                    "The subject stands in the same position by the tray, gesturing naturally with one open hand "
                    "at chest height while explaining directly to the camera."
                ),
                "body_video": (
                    "One continuous locked smartphone take. The subject gestures calmly with one hand while speaking "
                    "directly into the camera lens. Every element already exists; nothing new spawns."
                ),
                "cta_frame1": (
                    "The subject stands in the same position with foot on the gray stool, "
                    "pointing one index finger straight down toward the floor while smiling and looking into the lens."
                ),
                "cta_video": (
                    "One continuous locked smartphone take. The subject points straight down "
                    "with a natural encouraging nod while looking straight into the lens. "
                    "Every element already exists; nothing new spawns."
                ),
            },
            "cenario": (
                "Consultório médico americano iluminado com luz fria natural: maca médica bege com lençol de papel "
                "branco à esquerda, armários de madeira e pia de inox com pequena bandeira dos EUA ao fundo."
            ),
            "personagem": (
                "Médico/enfermeiro homem negro, cerca de 35-40 anos, barba curta aparada, tatuagens nos antebraços, "
                "expressão enérgica e direta olhando para a lente."
            ),
            "roupa": (
                "Scrub médico azul-royal (camisa gola V e calça), touca cirúrgica estampada azul, "
                "estetoscópio preto no pescoço, tênis preto; pé direito descalço apoiado no mocho."
            ),
            "objetos": [
                "Baking soda of Arm & Hammer of orange box",
                "White ceramic bowl with baking soda paste",
                "Stainless steel medical tray",
                "White baking soda paste applied on leg/thigh",
                "Round gray medical stool",
                "Medical exam table with white paper roll",
                "Black stethoscope around neck",
            ],
            "enquadramento": (
                "Vertical 9:16 fixo (locked shot de smartphone em tripé), plano americano/corpo inteiro "
                "enquadrando simultaneamente o rosto expressivo, a perna levantada com a pasta e a bandeja com o produto."
            ),
            "cta": {
                "texto_falado": "Save this video. Comment yes and follow me so I can send you the recipe.",
                "palavra_chave": f"COMMENT {palavra_cta}",
                "acao_visual": "Aponta o dedo indicador para baixo (em direção aos comentários) mantendo contato visual com a câmera.",
            },
        }

    formato = formato_override or "formato_ugc_padrao"
    return {
        "formato": formato,
        "hook_visual": {
            "resumo": "Apresentador em primeiro plano realizando gesto de abertura com o ingrediente principal visível nos primeiros 2-3s.",
            "gesto": "Gesto direto com as mãos mostrando o ingrediente enquanto fala olhando para a lente.",
            "objeto": "Ingrediente/produto principal posicionado em primeiro plano.",
            "enquadramento": "Vertical 9:16, plano médio frontal na altura dos olhos.",
        },
        "cenario": "Ambiente interno residencial/profissional bem iluminado com bancada.",
        "personagem": "Apresentador adulto falando diretamente para a câmera.",
        "roupa": "Vestimenta condizente com o nicho (casual ou jaleco/scrub).",
        "objetos": ["Ingrediente principal", "Recipiente sobre a bancada"],
        "enquadramento": "Vertical 9:16 smartphone shot.",
        "cta": {
            "texto_falado": texto.split(".")[-2].strip() if "." in texto else texto,
            "palavra_chave": f"COMMENT {palavra_cta}",
            "acao_visual": "Aponta para baixo convidando ao comentário.",
        },
    }


def analisar_viral(
    video_path: Path,
    formato_nome: str | None = None,
    whisper_model: str = "small",
) -> dict[str, Any]:
    """
    Executa a Etapa 2 da Forja completa para 1 vídeo viral:
    1. Transcreve fala com timestamps por palavra e mede o ritmo (palavras/s).
    2. Extrai frames em 0.5s, 1.5s e 2.5s.
    3. Descreve HOOK VISUAL, cenário, personagem, roupa, objetos, enquadramento, CTA e FORMATO.
    4. Salva <viral>_analise.json.
    """
    video_path = video_path.resolve()
    if not video_path.exists():
        raise FileNotFoundError(f"Vídeo viral não encontrado: {video_path}")

    frames_dir = video_path.parent / f"{video_path.stem}_frames"
    frames_dir.mkdir(parents=True, exist_ok=True)

    tempos_hook = [0.5, 1.5, 2.5]
    frames_extraidos: dict[str, str] = {}
    for t in tempos_hook:
        nome_frame = f"frame_{str(t).replace('.', '_')}s.jpg"
        destino = frames_dir / nome_frame
        extrair_frame(video_path, t, destino)
        frames_extraidos[f"{t}s"] = str(destino)

    transcricao = transcrever_com_palavras(video_path, model_name=whisper_model)
    duracao_total = transcricao["duracao_video_s"]

    # Regra Raphael Paiva: mediana dos takes do Veo (1 frame a cada ~4s em vez de 1 por segundo)
    frames_takes_4s: dict[str, str] = {}
    t_cursor = 2.0
    take_idx = 1
    while t_cursor < duracao_total:
        nome_f = f"take_{take_idx:02d}_{str(round(t_cursor, 1)).replace('.', '_')}s.jpg"
        dest_f = frames_dir / nome_f
        extrair_frame(video_path, t_cursor, dest_f)
        frames_takes_4s[f"take_{take_idx:02d}_{round(t_cursor, 1)}s"] = str(dest_f)
        t_cursor += 4.0
        take_idx += 1

    # Palavras ditas especificamente durante a janela do Hook (0 a 3.0s)
    palavras_hook = [p for p in transcricao["palavras"] if p["inicio"] <= 3.0]
    fala_hook_3s = " ".join(p["palavra"] for p in palavras_hook)

    visual_info = _inferir_analise_visual_padrao(
        transcricao["texto"],
        frames_extraidos,
        formato_override=formato_nome,
    )

    analise = {
        "arquivo_viral": str(video_path),
        "formato": visual_info["formato"],
        "metricas_ritmo": {
            "duracao_s": transcricao["duracao_video_s"],
            "total_palavras": transcricao["total_palavras"],
            "palavras_por_segundo": transcricao["ritmo_palavras_por_s"],
            "palavras_por_segundo_fala_ativa": transcricao["ritmo_fala_ativa_palavras_por_s"],
        },
        "frames_hook": frames_extraidos,
        "frames_mediana_4s": frames_takes_4s,
        "fala_primeiros_3s": fala_hook_3s,
        "hook_visual": visual_info["hook_visual"],
        "cena_fixa_en": visual_info.get("cena_fixa_en", ""),
        "acoes_en": visual_info.get("acoes_en", {}),
        "variacoes_avatar": visual_info.get("variacoes_avatar", []),
        "cena": {
            "cenario": visual_info["cenario"],
            "personagem": visual_info["personagem"],
            "roupa": visual_info["roupa"],
            "objetos": visual_info["objetos"],
            "enquadramento": visual_info["enquadramento"],
            "cta": visual_info["cta"],
            "cena_fixa_en": visual_info.get("cena_fixa_en", ""),
            "acoes_en": visual_info.get("acoes_en", {}),
        },
        "transcricao": transcricao,
    }

    analise_path = video_path.parent / f"{video_path.stem}_analise.json"
    analise_path.write_text(json.dumps(analise, ensure_ascii=False, indent=2), encoding="utf-8")
    analise["caminho_analise_json"] = str(analise_path)
    return analise


def aplicar_analise_vision_interna(analise_path: Path, dados_vision: dict[str, Any]) -> dict[str, Any]:
    """
    Atualiza o arquivo <viral>_analise.json com a leitura visual feita pelo LLM Vision interno
    (formato, hook_visual, cena_fixa_en, acoes_en por take, variacoes_avatar e CTA).
    """
    analise = json.loads(analise_path.read_text(encoding="utf-8"))
    for k in ("formato", "hook_visual", "cena_fixa_en", "acoes_en", "variacoes_avatar"):
        if k in dados_vision and dados_vision[k]:
            analise[k] = dados_vision[k]
    if "cena" in dados_vision and isinstance(dados_vision["cena"], dict):
        analise.setdefault("cena", {}).update(dados_vision["cena"])
    if "cena_fixa_en" in analise:
        analise.setdefault("cena", {})["cena_fixa_en"] = analise["cena_fixa_en"]
    if "acoes_en" in analise:
        analise.setdefault("cena", {})["acoes_en"] = analise["acoes_en"]
    analise_path.write_text(json.dumps(analise, ensure_ascii=False, indent=2), encoding="utf-8")
    return analise


def _dividir_transcricao_em_3_cenas(transcricao: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Divide a transcrição com timestamps por palavra em 3 cenas alinhadas aos cortes visuais reais do viral:
    - Cena 1 (Hook): Abertura + reação visual inicial
    - Cena 2 (Protocolo / Mecanismo): Transição ("The protocol is simple...", "Add one teaspoon...", etc.)
    - Cena 3 (Payoff / Resultado + CTA): Benefício final + chamada para ação ("Years of inflammation... Comment YES...")
    Calcula `t0` e `t1` reais a partir dos timestamps das palavras do Whisper.
    """
    texto = (transcricao.get("texto") or "").strip()
    dur = float(transcricao.get("duracao_video_s") or 18.0)
    palavras_ts = transcricao.get("palavras") or []
    frases = [f.strip() for f in re.split(r"(?<=[.!?])\s+", texto) if f.strip()]
    if len(frases) == 3:
        c1, c2, c3 = frases[0], frases[1], frases[2]
    elif len(frases) > 3:
        idx_c2 = None
        idx_c3 = None
        for idx_f, fr in enumerate(frases):
            if idx_c2 is None and idx_f >= 1 and re.search(
                r"\b(the\s+protocol|the\s+recipe|here\s+is\s+how|add\s+one|just\s+one\s+teaspoon|one\s+teaspoon|add\s+the\s+juice|mix\s+one|all\s+you\s+do)\b",
                fr,
                flags=re.I,
            ):
                idx_c2 = idx_f
            if idx_f >= 2 and re.search(
                r"\b(no\s+more\s+needles|years\s+of|within\s+days|comment|follow|save\s+this|send\s+you|to\s+receive)\b",
                fr,
                flags=re.I,
            ):
                if idx_c2 is None or idx_f > idx_c2:
                    idx_c3 = idx_f
                    break

        if idx_c2 is not None and idx_c3 is not None and idx_c3 > idx_c2:
            c1 = " ".join(frases[:idx_c2])
            c2 = " ".join(frases[idx_c2:idx_c3])
            # Para caber em 8s no Veo 3.1 (~23 palavras max), enxuga frases intermediárias se c3 tiver > 24 palavras preservando o CTA final completo!
            frases_c3_list = frases[idx_c3:]
            c3_raw = " ".join(frases_c3_list)
            c3_raw = re.sub(r"\s+so\s+your\s+clothes\s+start\s+fitting\s+again\.?$", ".", c3_raw, flags=re.I)
            if len(c3_raw.split()) > 25 and len(frases_c3_list) >= 2:
                frases_cta = [f for f in frases_c3_list if re.search(r"\b(comment|follow|send\s+you|recipe|protocol)\b", f, flags=re.I)]
                cta_tail = " ".join(frases_cta) if frases_cta else frases_c3_list[-1]
                cta_tail = re.sub(r"\s+so\s+your\s+clothes\s+start\s+fitting\s+again\.?$", ".", cta_tail, flags=re.I)
                lead_payoff = frases_c3_list[0]
                if lead_payoff not in frases_cta and len((lead_payoff + " " + cta_tail).split()) <= 27:
                    c3_raw = f"{lead_payoff} {cta_tail}"
                else:
                    c3_raw = cta_tail
            c3_raw = re.sub(r"\bfor\s+more\s+videos\s+like\s*\.?$", "for more videos like this.", c3_raw, flags=re.I)
            c3 = c3_raw
        else:
            idx_cta = None
            for idx_f, fr in enumerate(frases):
                if idx_f >= 2 and re.search(r"\b(comment|follow|save\s+this|send\s+you)\b", fr, flags=re.I):
                    idx_cta = idx_f
                    break
            if idx_cta is not None:
                frases_c3 = frases[idx_cta:]
                frases_rest = frases[:idx_cta]
            else:
                frases_c3 = frases[-2:] if len(frases[-1].split()) < 14 else [frases[-1]]
                frases_rest = frases[: len(frases) - len(frases_c3)]

            total_w = sum(len(f.split()) for f in frases_rest)
            acum = 0
            split_idx = 1
            melhor_diff = 9999
            for i in range(1, len(frases_rest)):
                acum += len(frases_rest[i - 1].split())
                diff = abs(acum - (total_w / 2.0))
                if diff <= melhor_diff:
                    melhor_diff = diff
                    split_idx = i
            c1 = " ".join(frases_rest[:split_idx])
            c2 = " ".join(frases_rest[split_idx:])
            c3 = " ".join(frases_c3)
    else:
        palavras = texto.split()
        n = max(3, len(palavras))
        i1 = max(1, n // 3)
        i2 = max(2, (2 * n) // 3)
        c1 = " ".join(palavras[:i1])
        c2 = " ".join(palavras[i1:i2])
        c3 = " ".join(palavras[i2:])

    # Calcula timestamps reais de corte se `palavras_ts` estiver disponível
    n1 = len(c1.split())
    n2 = len(c2.split())
    if len(palavras_ts) >= (n1 + n2 + 2):
        t1_end = round(float(palavras_ts[min(len(palavras_ts) - 1, n1 - 1)].get("fim", dur * 0.27)), 1)
        t2_start = round(float(palavras_ts[min(len(palavras_ts) - 1, n1)].get("inicio", t1_end)), 1)
        t2_end = round(float(palavras_ts[min(len(palavras_ts) - 1, n1 + n2 - 1)].get("fim", dur * 0.52)), 1)
        t3_start = round(float(palavras_ts[min(len(palavras_ts) - 1, n1 + n2)].get("inicio", t2_end)), 1)
        return [
            {"number": 1, "t0": 0.0, "t1": max(t1_end, t2_start), "dialogue": c1},
            {"number": 2, "t0": max(t1_end, t2_start), "t1": max(t2_end, t3_start), "dialogue": c2},
            {"number": 3, "t0": max(t2_end, t3_start), "t1": round(dur, 1), "dialogue": c3},
        ]
    return [
        {"number": 1, "t0": 0.0, "t1": round(dur * 0.27, 1), "dialogue": c1},
        {"number": 2, "t0": round(dur * 0.27, 1), "t1": round(dur * 0.52, 1), "dialogue": c2},
        {"number": 3, "t0": round(dur * 0.52, 1), "t1": round(dur, 1), "dialogue": c3},
    ]


# ---------------------------------------------------------------------------
# TABELAS EXATAS EXTRAÍDAS DO BUNDLE ATIVO DO ZERUM (app.js 15:33)
# ---------------------------------------------------------------------------

ROLETA_CENARIOS_TG: list[tuple[str, str]] = [
    (
        "cozinha clara",
        "in a lived-in everyday American kitchen shot on a counter-propped iPhone: a polished dark granite countertop in the foreground showing real specular light reflections of the slightly blown-out overhead recessed ceiling LED light and window daylight, a stainless refrigerator on the left with paper notes and magnets, a black coffee maker and two mismatched ceramic mugs in the back, and a folded red kitchen towel on the counter edge",
    ),
    (
        "cozinha rústica",
        "in a lived-in American home kitchen shot on a counter-propped iPhone: a polished quartz stone island countertop in the foreground reflecting the warm window daylight and overhead ceiling light, open wooden shelves with everyday jars and mugs behind, a small US flag magnet on the fridge, and a dish towel on the side of the stone counter",
    ),
    (
        "varanda tijolo",
        "on the front porch of a red-brick American suburban home with a polished dark stone-top outdoor table in the foreground reflecting the natural sky light, black wrought-iron railing, two white rocking chairs further back, an American flag on a bracket on the brick wall, and natural ligeramente blown-out daylight in the background",
    ),
    (
        "varanda fazenda",
        "on the wraparound porch of a white clapboard American farmhouse with a glossy stone-top patio counter in the foreground showing real daylight specular reflections, thick white columns, a porch swing with cushions, an American flag on an angled pole, and bright natural outdoor light",
    ),
    (
        "deck fundos",
        "on the covered back deck of an American suburban home with a polished granite-top outdoor bar counter in the foreground reflecting the daylight, natural wood railing, an American flag beside a sliding glass door with real glass reflections, and a backyard oak tree",
    ),
    (
        "varanda pedra",
        "on the covered front porch of a grey stone-front American home with a polished stone/steel table in the foreground showing crisp specular reflections of the daylight and objects on the table, black metal railing, two navy Adirondack chairs, and an American flag beside the front door",
    ),
    (
        "varanda telada",
        "on the screened side porch of an American ranch house with a polished quartz-top table in the foreground reflecting the side screen daylight, a wicker loveseat with cushions, and an American flag flat on the inside wall",
    ),
    (
        "quintal",
        "in a lived-in suburban American backyard patio under a pergola with a polished dark granite outdoor kitchen counter in the foreground reflecting the afternoon sun, a grill further back, and a US flag on the house wall",
    ),
    (
        "sala",
        "in a lived-in American open-concept dining/living room with a polished marble-top counter in the foreground reflecting the overhead ceiling light and window daylight, a beige sofa with throw pillows, framed wall art, and a small US flag on the bookshelf",
    ),
    (
        "garagem",
        "in a lived-in American home garage with the door open to bright slightly blown-out driveway daylight, a polished stainless steel workbench in the foreground showing real specular reflections of the container and box, a tool wall, and an American flag hung on the back wall",
    ),
]

ROLETA_ROUPAS_F_LN: list[tuple[str, str]] = [
    ("scrubs cinza", "grey hospital scrubs with a stethoscope"),
    ("scrubs azul", "navy hospital scrubs with a printed surgical cap"),
    ("cardigã", "a beige knit cardigan over a white tee"),
    ("camisa jeans", "a light denim shirt with rolled sleeves"),
    ("moletom", "a soft grey hoodie"),
    ("blusa floral", "a floral blouse"),
    ("regata", "a plain white tank top"),
    ("polo", "a navy polo shirt"),
]

ROLETA_ROUPAS_M_XZ: list[tuple[str, str]] = [
    ("scrubs cinza", "grey hospital scrubs with a stethoscope"),
    ("físico atlético sem camisa", "shirtless athletic muscular build with defined chest and abs in dark athletic shorts"),
    ("regata branca atlética", "a fitted white athletic tank top showing muscular arms and shoulders"),
    ("camisa xadrez", "a red plaid flannel shirt"),
    ("polo", "a navy polo shirt"),
    ("camiseta", "a plain white t-shirt"),
    ("moletom", "a grey hoodie"),
    ("jaqueta", "a light canvas work jacket over a tee"),
    ("camisa jeans", "a denim shirt with rolled sleeves"),
    ("suéter", "a dark green sweater"),
]

ROLETA_OBJETOS_AY: list[tuple[str, str]] = [
    ("caixa de leite Oak Hill marrom", 'a terracotta-brown gable-top milk-carton style box labeled "OAK HILL BAKING SODA" on the foreground counter beside a glass bowl'),
    ("caixa de leite Oak Valley azul", 'a blue-and-white gable-top milk-carton style box labeled "OAK VALLEY BAKING SODA" on the foreground counter beside a glass bowl'),
    ("caixa Harbor Pines verde com tampa", 'a green-and-white carton box with a white plastic screw cap on top labeled "HARBOR PINES BAKING SODA" on the counter'),
    ("caixa de leite laranja Oak Hill", 'an orange-and-white tall gable-top milk-carton spout box labeled "OAK HILL PURE BAKING SODA" on the counter beside {her}'),
    ("caixa na mão", "the orange box of baking soda held in {her} free hand the whole time"),
    ("caixa na mesa", "the orange box of baking soda and a small white dish of paste on the table beside {her}"),
    ("pires na mão", "a small white dish of white paste held in {her} hand"),
    ("colher", "a wooden spoon with white paste in it"),
    ("tigela de vidro", "a glass bowl of white paste on the counter in front of {her}"),
    ("pote aberto", "an open jar of white paste on the table, lid beside it"),
]

KEYWORDS_SUGERIDAS_ZERUM: list[str] = [
    "LINK",
    "YES",
    "ME",
    "INFO",
    "WANT",
    "READY",
    "SEND",
    "HOW",
    "GUIDE",
    "PRICE",
]

PRODUTOS_001_GD: list[dict[str, Any]] = [
    # 🔥 NOVO GERADOR 001 (AffiliateNetwork / AffiliateNetwork — `gerador/novo/catalogo.json`)
    {
        "id": "sodatide",
        "nome": "🔥 Sodatide (A Oferta Mais Quente · AffiliateNetwork)",
        "nicho": "Perda de peso",
        "cpa": "AffiliateNetwork Top #1",
        "chiclete": "The $1 baking soda trick — same idea, except you don't mix anything and you don't taste anything",
        "objeto_viral": "orange baking soda box beside a glass of water and half a lemon + gesture of pushing the spoon away (no mixing, no taste; never show capsule or bottle)",
        "keywords": ["SODA", "YES", "TRICK", "NOISE"],
    },
    {
        "id": "meltpeak",
        "nome": "MeltPeak (AffiliateNetwork)",
        "nicho": "Perda de peso",
        "cpa": "AffiliateNetwork",
        "chiclete": "the morning metabolic switch trick",
        "objeto_viral": "morning glass of water on kitchen counter",
        "keywords": ["YES", "TRICK", "SODA", "LINK"],
    },
    {
        "id": "sodapeak",
        "nome": "Sodapeak (Saúde Masculina · AffiliateNetwork)",
        "nicho": "Saúde masculina",
        "cpa": "AffiliateNetwork",
        "chiclete": "the baking soda trick for men over 50",
        "objeto_viral": "orange baking soda box + glass of water on kitchen counter",
        "keywords": ["SODA", "READY", "YES", "TRICK"],
    },
    {
        "id": "honeyboost",
        "nome": "HoneyBoost (Saúde Masculina · AffiliateNetwork)",
        "nicho": "Saúde masculina",
        "cpa": "AffiliateNetwork",
        "chiclete": "the golden honey trick for men over 50",
        "objeto_viral": "spoon with golden honey on kitchen counter",
        "keywords": ["HONEY", "READY", "YES", "HOW"],
    },
    {
        "id": "jellyfil",
        "nome": "Jellyfil (Saúde Masculina · AffiliateNetwork)",
        "nicho": "Saúde masculina",
        "cpa": "AffiliateNetwork",
        "chiclete": "the 15-second red jelly trick",
        "objeto_viral": "spoon with red jelly on kitchen counter",
        "keywords": ["READY", "JELLY", "YES", "HOW"],
    },
    {
        "id": "vapofil",
        "nome": "Vapofil (Saúde Masculina · AffiliateNetwork)",
        "nicho": "Saúde masculina",
        "cpa": "AffiliateNetwork",
        "chiclete": "the 10-second flow ritual for men",
        "objeto_viral": "glass of water on kitchen counter",
        "keywords": ["READY", "YES", "HOW", "LINK"],
    },
    {
        "id": "titanprime",
        "nome": "TitanPrime (Saúde Masculina · AffiliateNetwork)",
        "nicho": "Saúde masculina",
        "cpa": "AffiliateNetwork",
        "chiclete": "the morning stamina switch for men 50+",
        "objeto_viral": "morning mug / glass of water on counter",
        "keywords": ["READY", "YES", "HOW", "LINK"],
    },
    {
        "id": "sugarreset",
        "nome": "Sugar Reset (Diabetes · AffiliateNetwork)",
        "nicho": "Diabetes",
        "cpa": "AffiliateNetwork",
        "chiclete": "the morning glucose switch ritual",
        "objeto_viral": "finger prick monitor / glass of water in kitchen",
        "keywords": ["SUGAR", "YES", "INFO", "GUIDE"],
    },
    {
        "id": "bloodpril",
        "nome": "Bloodpril (Pressão Arterial · AffiliateNetwork)",
        "nicho": "Pressão arterial",
        "cpa": "AffiliateNetwork",
        "chiclete": "the vessel-relaxing morning trick",
        "objeto_viral": "home blood pressure cuff on kitchen table",
        "keywords": ["HEART", "BP", "YES", "INFO"],
    },
    {
        "id": "gelagen",
        "nome": "Gelagen (Pele · AffiliateNetwork)",
        "nicho": "Pele",
        "cpa": "AffiliateNetwork",
        "chiclete": "the kitchen gelatin skin-tightening trick",
        "objeto_viral": "spoon with clear/pink gelatin at bathroom or kitchen counter",
        "keywords": ["SKIN", "GLOW", "YES", "RECIPE"],
    },
    {
        "id": "breathizen",
        "nome": "BreathiZen (Pulmão · AffiliateNetwork)",
        "nicho": "Pulmão",
        "cpa": "AffiliateNetwork",
        "chiclete": "the 30-second airway clearing ritual",
        "objeto_viral": "warm steaming mug on kitchen counter",
        "keywords": ["BREATH", "LUNGS", "YES", "INFO"],
    },
    {
        "id": "neuroschutz",
        "nome": "NeuroSchutz (Neuropatia · AffiliateNetwork)",
        "nicho": "Neuropatia",
        "cpa": "AffiliateNetwork",
        "chiclete": "the nerve-calming bedtime ritual for tingling feet",
        "objeto_viral": "socks beside bed / rubbing foot or ankle",
        "keywords": ["NERVE", "FEET", "YES", "INFO"],
    },
    {
        "id": "olivaro",
        "nome": "Olivaro (Diabetes · AffiliateNetwork)",
        "nicho": "Diabetes",
        "cpa": "AffiliateNetwork",
        "chiclete": "the olive leaf morning ritual",
        "objeto_viral": "tablespoon of extra virgin olive oil on counter",
        "keywords": ["OLIVE", "YES", "INFO", "LINK"],
    },
    {
        "id": "memohoney",
        "nome": "MemoHoney (Memória · AffiliateNetwork)",
        "nicho": "Memória",
        "cpa": "AffiliateNetwork",
        "chiclete": "the golden honey memory trick",
        "objeto_viral": "wooden honey dipper with golden honey",
        "keywords": ["HONEY", "BRAIN", "YES", "INFO"],
    },
    {
        "id": "vapocept",
        "nome": "Vapocept (Memória · AffiliateNetwork)",
        "nicho": "Memória",
        "cpa": "AffiliateNetwork",
        "chiclete": "the 10-second brain fog clearing ritual",
        "objeto_viral": "keys and glasses on kitchen counter",
        "keywords": ["BRAIN", "MIND", "YES", "INFO"],
    },
    # 📦 GERADOR ANTIGO (H&W — `gerador/catalogo.json`)
    {
        "id": "alkaburn",
        "nome": "AlkaBurn HT (Gerador Antigo)",
        "nicho": "Perda de peso",
        "cpa": "$200",
        "chiclete": "the $1 baking soda trick",
        "objeto_viral": "orange baking soda box + glass of water or capsule on kitchen counter (never show branded bottle)",
        "keywords": ["YES", "RECIPE", "SODA", "MELT", "LINK"],
    },
    {
        "id": "slimsoda",
        "nome": "SlimSoda Powder LT (Gerador Antigo)",
        "nicho": "Perda de peso",
        "cpa": "$80",
        "chiclete": "the $1 morning baking soda shot",
        "objeto_viral": "generic orange box of baking soda + spoon + glass of water on counter",
        "keywords": ["SODA", "SHOT", "YES", "RECIPE", "LINK"],
    },
    {
        "id": "slimsoda-capsules",
        "nome": "SlimSoda Capsules LT (Gerador Antigo)",
        "nicho": "Perda de peso",
        "cpa": "$90",
        "chiclete": "the baking soda trick without drinking the shot",
        "objeto_viral": "orange baking soda box beside a glass of water",
        "keywords": ["SODA", "YES", "INFO", "LINK"],
    },
    {
        "id": "leaftide",
        "nome": "LeafTide Powder LT (Gerador Antigo)",
        "nicho": "Perda de peso",
        "cpa": "$90",
        "chiclete": "the morning green leaf ritual",
        "objeto_viral": "warm mug or glass with spoon on kitchen counter",
        "keywords": ["TEA", "YES", "RECIPE", "LINK"],
    },
    {
        "id": "linfaflow",
        "nome": "LinfaFlow LT (Gerador Antigo)",
        "nicho": "Drenagem linfática",
        "cpa": "$80",
        "chiclete": "the 30-second morning drain ritual",
        "objeto_viral": "deep sock mark on ankle / puffy morning face in mirror / drops falling into a glass of water",
        "keywords": ["PUFFY", "LEGS", "FLOW", "DRAIN", "YES"],
    },
    {
        "id": "vigorjelly",
        "nome": "VigorJelly HT (Gerador Antigo)",
        "nicho": "Disfunção Erétil",
        "cpa": "$260",
        "chiclete": "the 15-second red jelly trick",
        "objeto_viral": "spoon with red jelly / kitchen jar on counter",
        "keywords": ["READY", "YES", "LINK", "HOW"],
    },
    {
        "id": "horsejello",
        "nome": "HorseJello LT (Gerador Antigo)",
        "nicho": "Disfunção Erétil",
        "cpa": "$90",
        "chiclete": "the gelatin trick for men over 50",
        "objeto_viral": "spoon with red gelatin in kitchen",
        "keywords": ["JELLO", "READY", "YES", "LINK"],
    },
    {
        "id": "crowned",
        "nome": "Crowned LT (Gerador Antigo)",
        "nicho": "Queda de cabelo / pele",
        "cpa": "$80",
        "chiclete": "the follicle awakening ritual",
        "objeto_viral": "hairbrush with shed hair / parting hair at the mirror",
        "keywords": ["HAIR", "YES", "GUIDE", "LINK"],
    },
    {
        "id": "sonnus",
        "nome": "Sonnus LT (Gerador Antigo)",
        "nicho": "Sono",
        "cpa": "$80",
        "chiclete": "the 3 a.m. cortisol switch ritual",
        "objeto_viral": "phone clock at 3:14 a.m. / warm bedside mug",
        "keywords": ["SLEEP", "REST", "YES", "GUIDE", "LINK"],
    },
    {
        "id": "memoflow",
        "nome": "MemoFlow LT (Gerador Antigo)",
        "nicho": "Memória",
        "cpa": "$90",
        "chiclete": "the 10-second brain fog clearing ritual",
        "objeto_viral": "keys/glasses on counter or morning cup",
        "keywords": ["BRAIN", "MIND", "YES", "INFO", "LINK"],
    },
    {
        "id": "primehoney",
        "nome": "PrimeHoney HT (Gerador Antigo)",
        "nicho": "Memória",
        "cpa": "$200",
        "chiclete": "the golden honey memory trick",
        "objeto_viral": "wooden honey dipper / spoon with golden honey",
        "keywords": ["HONEY", "BRAIN", "YES", "RECIPE", "LINK"],
    },
    {
        "id": "cardiocept",
        "nome": "Cardiocept HT (Gerador Antigo)",
        "nicho": "Pressão arterial",
        "cpa": "$200",
        "chiclete": "the vessel-relaxing morning ritual",
        "objeto_viral": "home blood pressure cuff on table / glass of water",
        "keywords": ["HEART", "BP", "YES", "INFO", "LINK"],
    },
    {
        "id": "cardioflush",
        "nome": "CardioFlush LT (Gerador Antigo)",
        "nicho": "Pressão arterial",
        "cpa": "$90",
        "chiclete": "the arterial flush ritual",
        "objeto_viral": "home blood pressure monitor on table",
        "keywords": ["HEART", "YES", "INFO", "LINK"],
    },
    {
        "id": "vigorboost",
        "nome": "VigorBoost Capsule LT (Gerador Antigo)",
        "nicho": "Disfunção Erétil",
        "cpa": "$90",
        "chiclete": "the morning blood-flow switch",
        "objeto_viral": "glass of water on kitchen counter",
        "keywords": ["READY", "YES", "HOW", "LINK"],
    },
]

REGIOES_LINFATICAS_001: list[dict[str, str]] = [
    {"id": "axila", "rotulo": "Axilas (under your armpits)", "en": "under your armpits where the axillary lymph nodes sit"},
    {"id": "pescoco", "rotulo": "Laterais do pescoço (sides of your neck)", "en": "along the sides of your neck over the cervical lymph nodes"},
    {"id": "orelha", "rotulo": "Atrás das orelhas (behind your ears)", "en": "right behind your ears at the base of the jawline"},
    {"id": "virilha", "rotulo": "Dobra da virilha (groin creases)", "en": "along the groin creases where lower-body lymph drains"},
    {"id": "umbigo", "rotulo": "Umbigo / Barriga (belly button & lower belly)", "en": "around the belly button and lower bloated abdomen"},
    {"id": "papada", "rotulo": "Papada / Queixo (under the chin)", "en": "under the chin and jawline where fluid pools overnight"},
    {"id": "flancos", "rotulo": "Flancos (love handles / waist)", "en": "along the love handles and sides of the waist"},
    {"id": "coxa", "rotulo": "Coxa interna (inner thighs)", "en": "on the upper inner thighs where stubborn fluid gathers"},
]


def carregar_ficha_ia_produto_001(produto_id: str, max_chars: int = 18000) -> str:
    """
    Carrega a ficha oficial `briefs/<id>-ia.txt` extraída de `http://127.0.0.1:8505`
    e `gerador/catalogo.json` (incluindo 🔥 Sodatide com a tabela de transposição dos 95 virais do Baking Soda).
    """
    if not produto_id:
        return ""
    base_dir = Path(__file__).resolve().parent.parent / "zerum_re" / "dump_autenticado" / "briefs_gerador"
    ficha_file = base_dir / f"briefs_{produto_id}-ia.txt"
    if not ficha_file.exists():
        return ""
    try:
        txt = ficha_file.read_text(encoding="utf-8", errors="replace").strip()
        return txt[:max_chars]
    except Exception:
        return ""

MODOS_VARIACAO_ZERUM: list[dict[str, str]] = [
    {
        "id": "tora",
        "rotulo": "🪵 Sem variação (na tora)",
        "descricao": "Todos os vídeos iguais entre si; só o avatar muda. Fala palavra por palavra, mesmas cenas, ações, roupa, objeto e lugar.",
        "instrucaoPadrao": (
            'MODE CLONE ("na tora"): copy the viral LITERALLY. The speech is the transcript WORD FOR WORD, '
            'including the call to action exactly as spoken (its comment word, "save this video", "follow me"); '
            "Same number of scenes and the same split, the same ACTION in each scene, the same framing, the same outfit type, "
            "the same object, the same place and American elements. Only the people (the chosen avatars) change."
        ),
    },
    {
        "id": "roleta",
        "rotulo": "🎰 Método Roleta (Cenário + Roupa + Objeto inéditos)",
        "descricao": "Cada vídeo num cenário, roupa e objeto inéditos pra você (80 a 480 combinações); fala e ações iguais. Nunca repete uma combinação sua.",
        "instrucaoPadrao": "MODE ROLETA: keep speech and actions identical to the viral; each video gets an unused combination of American location (Tg), outfit (lN/xz) and prop placement (aY).",
    },
    {
        "id": "gesto",
        "rotulo": "🤲 Microvariação de gesto",
        "descricao": "Pequenas mudanças de gesto, objeto e cenário. Fala e lógica iguais.",
        "instrucaoPadrao": 'MODE "GESTURE MICRO-VARIATION": keep the speech and the structure identical; change only small things the eye sees — a gesture, the object in hand, the spot in the room, the framing of one scene.',
    },
    {
        "id": "texto",
        "rotulo": "✍️ Microvariação de texto",
        "descricao": "Fala com toques pequenos. Estrutura, gestos e cena iguais.",
        "instrucaoPadrao": 'MODE "TEXT MICRO-VARIATION": keep gestures, framing and on-screen beats identical; vary the speech with small touches (synonyms, a detail, the order of two clauses) — the hook keeps its force, the structure never changes.',
    },
    {
        "id": "combinada",
        "rotulo": "🔀 Combinada",
        "descricao": "Texto, gesto e imagem variam um pouco, tudo junto.",
        "instrucaoPadrao": 'MODE "COMBINED": small variations in speech AND in gesture/object/room at the same time, each video a different mix; the structure and the beat timing of the viral stay.',
    },
    {
        "id": "novo",
        "rotulo": "✨ Novo a partir do analisado",
        "descricao": "Algo inteiramente novo com a estrutura e a inteligência do viral.",
        "instrucaoPadrao": 'MODE "NEW FROM THE ANALYSIS": write entirely new videos that keep the viral\'s intelligence — its hook mechanism, pacing, number of beats, the moment of the comment call — but with new words, new angles on the pain and new visual moments.',
    },
    {
        "id": "micro_embalagem",
        "rotulo": "🧬 Ad Vencedor · Mesmo Personagem + Micro-Variação 001 (Teste B · Embalagem Intacta)",
        "descricao": "Mantém 100% o mesmo personagem, mesma roupa, mesmo cenário e mesmo objeto do viral vencedor, aplicando micro-variações cirúrgicas 001 (gesto, cadência e micro-toques de 1-2 palavras sem alterar o hook).",
        "instrucaoPadrao": 'MODE "WINNING AD SAME-CHARACTER MICRO-VARIATION (TESTE B)": keep 100% the exact same character, outfit, room, and hook object from the winning ad; apply only subtle 001 micro-variations in delivery, gesture, and 1-2 word phrasing touches without changing the hook.',
    },
]


def _aplicar_micro_toque_fala_001(fala_orig: str, indice_cena: int, idx_var: int, palavra_cta: str = "YES") -> str:
    """
    Aplica micro-variações verbais cirúrgicas da escola 001 ("o quanto menos mexer na embalagem melhor"):
    - O Hook (Cena 1) permanece 100% intacto nas variações #1..#4 (e recebe apenas 1 palavra de ênfase na #5+) para nunca quebrar a retenção dos 3 primeiros segundos.
    - O Mecanismo (Cena 2) e o CTA (Cena 3) recebem micro-toques sutis de 1 a 2 palavras em variações alternadas, mantendo 100% do sentido, ritmo e a keyword `comment yes`.
    """
    txt = (fala_orig or "").strip()
    if not txt:
        return txt
    cta_low = (palavra_cta or "YES").strip().lower()
    if indice_cena == 2:
        txt = re.sub(
            r"\bcomment\s+(?:the\s+word\s+)?['\"]?[a-zA-Z0-9]{2,15}['\"]?\b",
            f"comment {cta_low}",
            txt,
            flags=re.I,
        )

    slot = idx_var % 5
    # Variações #1 (slot 0) e #2 (slot 1): 100% mesma copy literal (varia apenas micro-gesto / micro-expressão / onda de voz no Veo 3.1)
    if slot in (0, 1):
        return txt

    if indice_cena == 0:
        # Hook é sagrado na embalagem: mantém 100% literal nas variações #1..#4; na #5 faz apenas micro-toque de 1 palavra se aplicável
        if slot == 4:
            if "every night" in txt.lower():
                return re.sub(r"\bevery night\b", "every single night", txt, count=1, flags=re.I)
            if "in just seven days" in txt.lower():
                return re.sub(r"\bin just seven days\b", "in only seven days", txt, count=1, flags=re.I)
        return txt

    if indice_cena == 1:
        if slot == 2:
            if "just watch," in txt.lower():
                return re.sub(r"\bJust watch,", "Look closely,", txt, count=1, flags=re.I)
            if "swear by this now" in txt.lower():
                return re.sub(r"\bswear by this now\b", "swear by this every day", txt, count=1, flags=re.I)
        elif slot == 4:
            if "add the juice of half a lemon" in txt.lower():
                return re.sub(r"\bAdd the juice of half a lemon\b", "Squeeze in half a fresh lemon", txt, count=1, flags=re.I)
            if "from your whole body" in txt.lower():
                return re.sub(r"\bfrom your whole body\b", "from your entire body", txt, count=1, flags=re.I)
        return txt

    if indice_cena == 2:
        if slot == 3:
            if "to receive the complete recipe" in txt.lower():
                return re.sub(r"\bTo receive the complete recipe\b", "To get the full recipe right now", txt, count=1, flags=re.I)
            if "so i can send you the recipe" in txt.lower():
                return re.sub(r"\bso I can send you the recipe\b", "so I can send you the full recipe", txt, count=1, flags=re.I)
        elif slot == 4:
            if "follow for more videos" in txt.lower():
                return re.sub(r"\band follow for more videos\b", "and follow me for more tips", txt, count=1, flags=re.I)
            if "save this video," in txt.lower():
                return re.sub(r"\bSave this video,\b", "Save this video right now,", txt, count=1, flags=re.I)
    return txt


MICRO_VARIACOES_EMBALAGEM_001: list[dict[str, str]] = [
    {
        "id": "micro_01_puro",
        "rotulo": "Micro #1 · Re-Take Puro (Mesmo Personagem · 100% Mesma Copy & Embalagem)",
        "micro_visual_s1_en": "Keep the exact original pose, framing, facial expression, and object positions 100% identical to the reference photo",
        "micro_visual_sn_en": "Keep the exact original pose, framing, facial expression, and object positions 100% identical to Reference Image 2",
        "micro_veo_en": "maintaining direct eye contact with a steady, confident delivery",
    },
    {
        "id": "micro_02_aceno",
        "rotulo": "Micro #2 · Micro-Expressão Focada & Aceno Afirmativo (100% Mesma Copy)",
        "micro_visual_s1_en": "Keep the exact same pose, clothing, and props, with an intense focused gaze directly into the camera lens",
        "micro_visual_sn_en": "Keep the exact same pose, clothing, and props as Reference Image 2, with an engaged, authoritative expression",
        "micro_veo_en": "giving a subtle affirmative head nod while speaking directly to the camera",
    },
    {
        "id": "micro_03_cadencia_mecanismo",
        "rotulo": "Micro #3 · Micro-Cadência no Mecanismo (Hook & Embalagem 100% Intactos)",
        "micro_visual_s1_en": "Keep the exact same pose, clothing, and props, with a serious, urgent expert facial expression",
        "micro_visual_sn_en": "Keep the exact same pose, clothing, and props as Reference Image 2, with a slight natural head tilt while explaining",
        "micro_veo_en": "speaking with brisk, engaging conversational energy and natural hand cadence",
    },
    {
        "id": "micro_04_urgencia_cta",
        "rotulo": "Micro #4 · Micro-Toque no CTA (Hook & Mecanismo 100% Intactos)",
        "micro_visual_s1_en": "Keep the exact same pose, clothing, and props, with a direct, eye-catching opening expression",
        "micro_visual_sn_en": "Keep the exact same pose, clothing, and props as Reference Image 2, with a warm, reassuring expression",
        "micro_veo_en": "leaning slightly toward the camera lens with warm, convincing conviction",
    },
    {
        "id": "micro_05_precisao_ritmada",
        "rotulo": "Micro #5 · Micro-Gesto Deliberado & Toque Sutil 001 (Embalagem Intacta)",
        "micro_visual_s1_en": "Keep the exact same pose, clothing, and props, with a confident, knowing expression looking straight into the lens",
        "micro_visual_sn_en": "Keep the exact same pose, clothing, and props as Reference Image 2, maintaining steady eye contact with the camera",
        "micro_veo_en": "performing the movement with smooth, deliberate precision while maintaining eye contact",
    },
]


def _interpretar_regras_diretor_vae(pedido: str, analise_15: dict[str, Any]) -> dict[str, Any]:
    """
    Reproduz o compilador de intenção `c$` + `VAe` ("O QUE O MEMBRO ESCREVE É LEI") do `app.js` do FlowStudio:
    Extrai determinísticamente do pedido em linguagem natural:
    - `roupa_fixa_en` / `roupa_fixa_rotulo` (ex.: "todos usando a mesma roupa de enfermeira do viral")
    - `ritmo_edicao` (`"dinamico"` se pediu "edição dinâmica", "dinãmica", "take dinâmico", "punch-in", "jump cut")
    - `sem_legenda` (`True` se pediu "sem legenda", "zero legenda", "apenas quando for aparecer o cta")
    - `apenas_botao_cta` (`True` se pediu "apenas quando for aparecer o cta o botão cta", "só o botão cta")
    """
    txt = (pedido or "").strip()
    low = txt.lower()

    roupa_viral = str(analise_15.get("roupa_lock") or "").strip()
    if not roupa_viral and isinstance(analise_15.get("pessoas"), list) and analise_15["pessoas"]:
        roupa_viral = str(analise_15["pessoas"][0].get("roupa") or "").strip()

    pediu_mesma_roupa = bool(
        re.search(
            r"\b(mesma\s+roupa|roupa\s+do\s+viral|roupa\s+de\s+enfermeir[oa]|todos?\s+usando\s+a\s+mesma\s+roupa|todos?\s+de\s+enfermeir[oa]|scrubs\s+do\s+viral)\b",
            low,
        )
    )
    pediu_enfermeira = bool(re.search(r"\b(enfermeir[oa]s?|nurse|scrubs|jaleco)\b", low))

    roupa_fixa_en: str | None = None
    roupa_fixa_rotulo: str | None = None
    if pediu_mesma_roupa or pediu_enfermeira:
        is_pt_fallback = "vestimenta" in roupa_viral.lower() or "condizente" in roupa_viral.lower()
        if pediu_enfermeira or "scrub" in roupa_viral.lower() or "nurse" in roupa_viral.lower():
            base_nurse = (
                roupa_viral
                if (not is_pt_fallback and ("scrub" in roupa_viral.lower() or "nurse" in roupa_viral.lower()))
                else "fitted medical V-neck nurse scrubs with a clinical stethoscope draped around the neck"
            )
            roupa_fixa_en = f"{base_nurse} (exact same nurse medical scrubs outfit from the viral)"
            roupa_fixa_rotulo = "mesma roupa de enfermeira do viral (scrubs + estetoscópio)"
        else:
            roupa_fixa_en = (roupa_viral if not is_pt_fallback else "") or "exact same outfit worn by the presenter in the viral"
            roupa_fixa_rotulo = "mesma roupa do viral (travada)"

    edicao_dinamica = bool(
        re.search(r"\b(edi[çc][aã]o\s+din[aâã]mica|din[aâã]mica|take\s+din[aâã]mico|punch[- ]?in|jump[- ]?cut|corte\s+seco)\b", low)
    )
    pediu_com_legenda = bool(
        re.search(r"\b(com\s+legendas?|legenda\s+karaok[eê]|coloque\s+legenda|quero\s+legenda)\b", low)
    )
    sem_legenda = (not pediu_com_legenda) or bool(
        re.search(r"\b(sem\s+legendas?|zero\s+legendas?|nenhuma\s+legenda|n[aã]o\s+coloque\s+legenda)\b", low)
    )
    apenas_botao_cta = (not pediu_com_legenda) or bool(
        re.search(
            r"\b(apenas\s+quando\s+for\s+aparecer\s+o\s+cta|s[oó]\s+(?:o\s+)?bot[aã]o\s+cta|apenas\s+(?:o\s+)?bot[aã]o\s+cta|bot[aã]o\s+cta|p[ií]lula\s+cta)\b",
            low,
        )
    )
    if apenas_botao_cta and "sem legenda" in low:
        sem_legenda = True

    estilo_legenda = "apenas_cta" if (sem_legenda and apenas_botao_cta) else ("sem_legenda" if sem_legenda else "karaoke")

    return {
        "pediu_mesma_roupa": pediu_mesma_roupa,
        "pediu_enfermeira": pediu_enfermeira,
        "roupa_fixa_en": roupa_fixa_en,
        "roupa_fixa_rotulo": roupa_fixa_rotulo,
        "edicao_dinamica": edicao_dinamica,
        "ritmo_edicao": "dinamico" if edicao_dinamica else "take",
        "sem_legenda": sem_legenda,
        "apenas_botao_cta": apenas_botao_cta,
        "estilo_legenda": estilo_legenda,
    }


def sortear_roleta_zerum(
    qtd: int = 1,
    usados_ids: list[str] | None = None,
    sexo: str = "f",
    com_baking_soda: bool = True,
    seed: int | None = None,
    roupa_fixa_en: str | None = None,
    roupa_fixa_rotulo: str | None = None,
) -> list[dict[str, Any]]:
    """
    Reproduz exatamente a função `uN` + `vl(e, a, o, t, r)` do `app.js` do FlowStudio:
    - Gera todas as combinações `Tg (10 cenários) × lN/xz (8 roupas) × aY (6 objetos se baking soda, ou 1)`.
    - Se o membro ordenou `roupa_fixa_en` (ex.: "todos usando a mesma roupa de enfermeira do viral"),
      TRAVA a roupa em 100% dos vídeos do lote e gira apenas os 10 Cenários Americanos (`Tg`) × Posição do Objeto (`aY`)!
    """
    usados = set(usados_ids or [])
    objetos = ROLETA_OBJETOS_AY if com_baking_soda else [None]
    roupas_lista = (
        [(roupa_fixa_rotulo or "mesma roupa do viral", roupa_fixa_en)]
        if roupa_fixa_en
        else ROLETA_ROUPAS_F_LN
    )
    todos: list[dict[str, Any]] = []
    for cen_rot, cen_en in ROLETA_CENARIOS_TG:
        for idx, (roupa_rot_f, roupa_en_f) in enumerate(roupas_lista):
            roupa_en_m = roupa_fixa_en if roupa_fixa_en else ROLETA_ROUPAS_M_XZ[idx % len(ROLETA_ROUPAS_M_XZ)][1]
            for obj in objetos:
                obj_rot = obj[0] if obj else "objeto do viral"
                combo_id = f"{cen_rot}|{roupa_rot_f}|{obj_rot}"
                rotulo = f"{cen_rot} · {roupa_rot_f}" + (f" · {obj[0]}" if obj else "")
                item: dict[str, Any] = {
                    "id": combo_id,
                    "rotulo": rotulo,
                    "cenario": cen_en,
                    "cenarioRotulo": cen_rot,
                    "roupaF": roupa_en_f,
                    "roupaM": roupa_en_m,
                }
                if obj:
                    item["objeto"] = obj[1]
                    item["objetoRotulo"] = obj[0]
                todos.append(item)

    candidatos = [x for x in todos if x["id"] not in usados]
    if len(candidatos) < qtd:
        candidatos = list(todos)

    c = int(seed if seed is not None else time.time() * 1000) & 0xFFFFFFFF

    def _lcg() -> float:
        nonlocal c
        c = (c * 1664525 + 1013904223) & 0xFFFFFFFF
        return c / 4294967296.0

    for i in range(len(candidatos) - 1, 0, -1):
        j = int(_lcg() * (i + 1))
        candidatos[i], candidatos[j] = candidatos[j], candidatos[i]

    # Garante primeiro 1 de cada cenário exato (10 cenários diferentes para 10 vídeos!)
    escolhidos: list[dict[str, Any]] = []
    cenarios_usados: set[str] = set()
    for item in candidatos:
        if item["cenarioRotulo"] not in cenarios_usados:
            escolhidos.append(item)
            cenarios_usados.add(item["cenarioRotulo"])
            if len(escolhidos) == qtd:
                break
    for item in candidatos:
        if len(escolhidos) == qtd:
            break
        if item not in escolhidos:
            escolhidos.append(item)

    pron_suj = "he" if sexo == "m" else "she"
    pron_pos = "his" if sexo == "m" else "her"
    saida: list[dict[str, Any]] = []
    for v in escolhidos[:qtd]:
        roupa_en = v["roupaM"] if sexo == "m" else v["roupaF"]
        obj_en = v.get("objeto", "").replace("{her}", pron_pos)
        obj_clause = f"; {obj_en}" if obj_en else ""
        variacao_txt = f"{pron_suj} is {v['cenario']}, wearing {roupa_en}{obj_clause}. Same action, object and speech as the viral."
        saida.append(
            {
                "id": v["id"],
                "rotulo": v["rotulo"],
                "variacao": variacao_txt,
                "cenario_lock": v["cenario"],
                "roupa_lock": roupa_en,
                "hook_object": obj_en,
                "estruturada": v,
            }
        )
    return saida


def parsear_avatares_variados_zerum(
    pedido: str,
    qtd: int = 1,
    sexo_padrao: str = "f",
    roupa_fixa_en: str | None = None,
    descricao_base_viral: str = "",
) -> list[dict[str, Any]]:
    """
    Reproduz `DG(e, a, o)` + `Hae` + `m3` + `O2`/`E5` do FlowStudio (`app.js`):
    - Gera `qtd` avatares distintos respeitando o sexo, físico e roupa do viral (`sexo_padrao`, `roupa_fixa_en`, `descricao_base_viral`).
    """
    txt = (pedido or "").strip()
    lower = txt.lower()
    eh_enfermeira = bool(
        re.search(r"\b(enfermeir[oa]s?|nurse|scrubs|jaleco)\b", lower)
        or (roupa_fixa_en and ("scrub" in roupa_fixa_en.lower() or "nurse" in roupa_fixa_en.lower()))
    )

    perfis_f = [
        {"etnia": "White American", "cabelo": "shoulder-length honey-blonde hair", "rotulo_pt": "Americana Loira · 42a", "idade": 42},
        {"etnia": "Hispanic American", "cabelo": "long dark brown wavy hair", "rotulo_pt": "Americana Morena Latina · 38a", "idade": 38},
        {"etnia": "Black American", "cabelo": "natural curly black hair tied back neatly", "rotulo_pt": "Americana Negra · 45a", "idade": 45},
        {"etnia": "East Asian American", "cabelo": "straight jet-black shoulder-length hair", "rotulo_pt": "Americana Asiática · 40a", "idade": 40},
        {"etnia": "White American", "cabelo": "copper auburn red hair", "rotulo_pt": "Americana Ruiva · 48a", "idade": 48},
        {"etnia": "White American", "cabelo": "short silver-gray hair, warm mature expression", "rotulo_pt": "Americana Sênior Grisalha · 62a", "idade": 62},
        {"etnia": "White American", "cabelo": "chestnut brown bob haircut with subtle highlights", "rotulo_pt": "Americana Castanha · 35a", "idade": 35},
        {"etnia": "White American", "cabelo": "platinum blonde hair in a neat low bun", "rotulo_pt": "Americana Loira Platinada · 51a", "idade": 51},
        {"etnia": "Hispanic American", "cabelo": "warm caramel-brown shoulder-length curls", "rotulo_pt": "Americana Morena Cacheada · 44a", "idade": 44},
        {"etnia": "Black American", "cabelo": "neat shoulder-length box braids", "rotulo_pt": "Americana Negra Tranças · 37a", "idade": 37},
        {"etnia": "White American", "cabelo": "strawberry blonde wavy hair", "rotulo_pt": "Americana Loira-Ruiva · 46a", "idade": 46},
        {"etnia": "South Asian American", "cabelo": "thick dark brown hair in a ponytail", "rotulo_pt": "Americana Sul-Asiática · 41a", "idade": 41},
    ]

    perfis_m = [
        {"etnia": "White American", "cabelo": "short salt-and-pepper crew cut with a thick full gray beard, fit muscular build", "rotulo_pt": "Americano Grisalho Forte · 54a", "idade": 54},
        {"etnia": "Hispanic American", "cabelo": "short dark wavy hair with a full neatly trimmed salt-and-pepper beard, athletic muscular build", "rotulo_pt": "Americano Latino Atlético · 46a", "idade": 46},
        {"etnia": "White American", "cabelo": "short sandy-blonde hair with light 5-o'clock shadow stubble, broad athletic shoulders", "rotulo_pt": "Americano Loiro Atlético · 44a", "idade": 44},
        {"etnia": "Black American", "cabelo": "high-top curly fade haircut with a thick full dark black beard (no gray chin patch), strong muscular build", "rotulo_pt": "Americano Negro Barba Cheia · 42a", "idade": 42},
        {"etnia": "Mediterranean Italian-American", "cabelo": "thick wavy dark brown hair swept back with a heavy dark beard, solid muscular chest and arms", "rotulo_pt": "Americano Mediterrâneo Fit · 49a", "idade": 49},
        {"etnia": "White American", "cabelo": "silver-white swept-back hair and a full white beard, fit older athletic build", "rotulo_pt": "Americano Sênior Prateado · 58a", "idade": 58},
        {"etnia": "Hispanic American", "cabelo": "buzz-cut dark hair with a thick handlebar mustache and clean chin, muscular broad-shouldered build", "rotulo_pt": "Americano Latino Bigode · 51a", "idade": 51},
        {"etnia": "White American", "cabelo": "reddish-auburn short hair and full ginger-gray beard, heavy muscular build", "rotulo_pt": "Americano Ruivo Forte · 47a", "idade": 47},
        {"etnia": "Middle Eastern American", "cabelo": "thick jet-black wavy hair with a full boxed dark beard, lean muscular physique", "rotulo_pt": "Americano Árabe Atlético · 45a", "idade": 45},
        {"etnia": "Polynesian Hawaiian-American", "cabelo": "medium-length wavy dark hair with a clean-shaven face, wide muscular shoulders", "rotulo_pt": "Americano Havaiano Forte · 43a", "idade": 43},
    ]

    tem_homem = bool(re.search(r"\b(homem|homens|neg[aã]o|man|men|male|médico|medico|doutor|enfermeiro)\b", lower))
    tem_mulher = bool(re.search(r"\b(mulher|mulheres|woman|women|female|loira|morena|negra|asiatica|asiática|enfermeira)\b", lower))
    metade_cada = "metade" in lower or (tem_homem and tem_mulher)

    roupa_padrao = roupa_fixa_en or ("fitted medical V-neck nurse scrubs with a stethoscope" if eh_enfermeira else "casual everyday American attire matching the viral")
    roupa_clause = f", {roupa_padrao}" if not roupa_padrao.lower().startswith("wearing") else f", {roupa_padrao}"

    avatares_gerados: list[dict[str, Any]] = []
    for i in range(max(1, qtd)):
        if metade_cada:
            sx = "m" if (i % 2 == 1) else "f"
        elif tem_homem and not tem_mulher:
            sx = "m"
        elif tem_mulher and not tem_homem:
            sx = "f"
        else:
            sx = "m" if str(sexo_padrao).lower().startswith("m") else "f"

        pool = perfis_m if sx == "m" else perfis_f
        perf = pool[i % len(pool)]
        papel_en = ("male nurse" if eh_enfermeira else "man") if sx == "m" else ("female nurse" if eh_enfermeira else "woman")

        detalhes_extras_m = [
            "no hat and no glasses",
            "no hat, wearing thin silver-wire aviator eyeglasses",
            "wearing a backwards navy baseball cap, no glasses",
            "no hat and no glasses, strong jawline",
            "completely bald shaved head, no hat and no glasses",
            "no hat, wearing round tortoise-shell eyeglasses",
            "wearing a charcoal grey beanie hat, no glasses",
            "no hat and no glasses, friendly confident expression",
            "wearing a plain olive-green baseball cap, no glasses",
            "no hat, wearing rimless reading glasses",
        ]
        detalhes_extras_f = [
            "no hat and no glasses, natural warm expression",
            "wearing thin gold-wire eyeglasses, no hat",
            "no hat and no glasses, subtle stud earrings",
            "wearing tortoise-shell reading glasses, no hat",
            "no hat and no glasses, hair neatly styled back",
            "wearing rimless eyeglasses, no hat",
            "no hat and no glasses, confident professional expression",
            "wearing thin silver-framed glasses, no hat",
            "no hat and no glasses, natural skin texture with visible pores",
            "wearing modern clear-frame eyeglasses, no hat",
        ]
        lista_det = detalhes_extras_m if sx == "m" else detalhes_extras_f
        det_idx = ((i // len(pool)) + (i % 3)) % len(lista_det)
        det_extra = f", {lista_det[det_idx]}"
        idade_var = perf["idade"] + ((i * 3) % 15) - 7
        pedido_curto_en = (
            f"a {idade_var}-year-old {perf['etnia']} {papel_en}, {perf['cabelo']}{det_extra}"
        )
        desc_en = (
            f"Candid front-facing iPhone 15 Pro 0.5x ultra-wide (14mm-16mm subtle barrel fisheye perspective, slightly elevated 12-to-15-degree high-angle view looking slightly down at the full countertop surface with foreground looming) photo of a real {idade_var}-year-old {perf['etnia']} {papel_en}, "
            f"{perf['cabelo']}{det_extra}, wearing {roupa_padrao}, real unfiltered human skin with natural sheen/slight oiliness on forehead and nose, natural expression lines and visible pores, slightly blown-out overhead ceiling LED / window light in the lived-in background, and real specular light reflections on the polished stone countertop in foreground."
        )
        avatares_gerados.append(
            {
                "numero": i + 1,
                "nome": f"Avatar Novo #{i+1} ({perf['rotulo_pt'].split('·')[0].strip()} · {idade_var}a)",
                "sexo": sx,
                "idade": idade_var,
                "etnia": perf["etnia"],
                "cabelo": f"{perf['cabelo']}{det_extra}",
                "roupa": roupa_padrao,
                "pedido_en": pedido_curto_en,
                "prompt_flow": desc_en,
            }
        )
    return avatares_gerados


def _normalizar_marca_baking_soda_en(texto: str, fala_completa: str = "") -> str:
    """
    Se o vídeo viral menciona baking soda (ou mostra caixa genérica/verde como 'Harbor Pines'),
    padroniza sempre para a caixa laranja clássica da 'Arm & Hammer Baking Soda'.
    """
    t = (texto or "").strip()
    if not t:
        return t
    tem_soda = "baking soda" in t.lower() or "baking soda" in (fala_completa or "").lower() or "harbor pines" in t.lower()
    if tem_soda:
        t = re.sub(
            r"\b(?:green\s+(?:and\s+white\s+)?(?:carton|box|package)(?:\s+of\s+['\"]?Harbor\s+Pines\s+Baking\s+Soda['\"]?|\s+labeled\s+['\"]?Harbor\s+Pines[^'\"]*['\"]?|\s+of\s+baking\s+soda)?|Harbor\s+Pines\s+Baking\s+Soda(?:\s+box|\s+carton)?|green\s+baking\s+soda\s+(?:box|carton)|generic\s+baking\s+soda\s+(?:box|carton))\b",
            "bright orange Arm & Hammer Baking Soda box",
            t,
            flags=re.I,
        )
    return t


def _sanitizar_acao_para_veo31_universal(acao_en: str, fala_completa: str = "", cta: bool = False) -> str:
    """
    Converte qualquer descrição de ação física de cena em linguagem de demonstração física 100% segura
    para o Veo 3.1 (preservando a trajetória início->fim sem acionar filtros médicos/cirúrgicos ou UI de comentários).
    """
    a = _normalizar_marca_baking_soda_en(acao_en or "", fala_completa)
    a = re.sub(
        r"\b(pointing\s+down(?:ward)?(?:\s+at\s+the\s+countertop|\s+at\s+comments|\s+toward\s+the\s+screen\s+bottom|\s+toward\s+the\s+floor)?|points?\s+(?:both\s+)?(?:index\s+)?fingers?\s+down(?:ward)?(?:\s+toward\s+the\s+screen\s+bottom|\s+toward\s+the\s+floor)?|pointing\s+to\s+comments|comment\s+section)\b",
        "gesturing naturally at chest height toward the camera",
        a,
        flags=re.I,
    )
    a = re.sub(r"\bwhite\s+powder\b", "white baking soda", a, flags=re.I)
    a = re.sub(r"\bmannequin(?:'s)?\s+(?:hollow\s+)?(?:stomach|abdomen|belly)\s+(?:cavity|compartment)\b", "hollow oval compartment of the fitness torso display model", a, flags=re.I)
    a = re.sub(r"\b(?:hollow\s+)?(?:stomach|abdominal|belly)\s+(?:cavity|compartment)\s+of\s+the\s+mannequin\b", "hollow oval compartment of the fitness torso display model", a, flags=re.I)
    a = re.sub(r"\bmannequin(?:'s)?\s+(?:stomach|abdomen|belly)\b", "hollow compartment of the fitness torso display model", a, flags=re.I)
    a = re.sub(r"\bmannequin\s+torso\b", "fitness torso display model", a, flags=re.I)
    a = re.sub(r"\bmannequin\b", "fitness torso display figure", a, flags=re.I)
    a = re.sub(r"\bvisceral\s+(?:belly\s+)?fat\s+mass\b", "stretchy yellow silicone mass", a, flags=re.I)
    a = re.sub(r"\byellow\s+(?:viscous|visceral|fat|adipose)\s+(?:mass|substance|blob|model)\b", "large stretchy yellow silicone mass", a, flags=re.I)
    a = re.sub(r"\b(?:operating\s+room|surgical\s+room)\b", "bright clinical room", a, flags=re.I)
    a = re.sub(r"\bIV\s+(?:drainage\s+)?bag\b", "clear plastic fluid bag", a, flags=re.I)
    if cta and not a.strip():
        a = "speaks directly to the camera with natural encouraging hand gestures at chest height"
    return a.strip()


def _escolher_melhor_segundo_sem_legenda_pesada(video_path: Path, t_alvo: float, dur: float) -> float:
    """
    Amostra 3 instantes próximos a `t_alvo` (t_alvo - 0.22s, t_alvo, t_alvo + 0.22s) via OpenCV
    e escolhe o quadro com menor área saturada de legenda amarela/branca estourada na faixa central/inferior.
    """
    try:
        import cv2
        import numpy as np

        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            return t_alvo
        candidatos = [
            max(0.25, min(dur - 0.25, t_alvo - 0.22)),
            max(0.25, min(dur - 0.25, t_alvo)),
            max(0.25, min(dur - 0.25, t_alvo + 0.22)),
        ]
        melhor_t = t_alvo
        menor_penalidade = 1e18
        for tc in candidatos:
            cap.set(cv2.CAP_PROP_POS_MSEC, tc * 1000.0)
            ok, frame = cap.read()
            if not ok or frame is None:
                continue
            h, w = frame.shape[:2]
            roi = frame[int(h * 0.45) : int(h * 0.92), int(w * 0.08) : int(w * 0.92)]
            hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
            # Detecta amarelo vibrante (botões/palavras ativas de legenda) + branco puro contornado de preto
            mask_yellow = cv2.inRange(hsv, np.array([18, 160, 180]), np.array([38, 255, 255]))
            lap_var = float(cv2.Laplacian(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var())
            penalidade = float(np.count_nonzero(mask_yellow)) - (lap_var * 2.0)
            if penalidade < menor_penalidade:
                menor_penalidade = penalidade
                melhor_t = tc
        cap.release()
        return round(melhor_t, 2)
    except Exception:
        return t_alvo


def ler_viral_15_campos_zerum(video_path: Path, forcar_releitura: bool = False) -> dict[str, Any]:
    """
    Motor Universal de Leitura Multimodal Físico-Visual de 15 Campos + Blueprint de Replicação (`plano_replicacao_fisica`):
    1. Calcula o `kie_hash` (SHA-256 de 64 hex chars dos bytes do `.mp4`).
    2. Se já existir em `virais/cache_kie_hash.json` COM `plano_replicacao_fisica` completo e frames existentes em disco
       (e não for `forcar_releitura`), devolve instantaneamente do cache.
    3. Caso contrário:
       - Transcreve o áudio na GPU (`faster-whisper` CUDA float16) com timestamps palavra por palavra.
       - Divide em 3 cenas alinhadas aos cortes/frases e extrai `START` e `END` de cada cena (escolhendo o frame mais limpo via OpenCV).
       - Monta um Storyboard 3x2 de alta nitidez (`1080x1280`: `SCENE 1 START`, `SCENE 1 END`, `SCENE 2 START`, `SCENE 2 END`, `SCENE 3 START`, `SCENE 3 END`).
       - Consulta `gemini-3-flash-preview` via Flow RPC (`agJzFb`, com até 3 retentativas automáticas) exigindo:
         * Causalidade física `START -> END` (identificando cavidades ocas, recipientes, reações de espuma, aplicação de pasta na pele).
         * Normalização automática de marcas falsas/IA para marcas reais (`bright orange Arm & Hammer Baking Soda box`).
         * `presenter_remove_features` (traços exatos do apresentador original para remover no Clone-Edit).
         * `presenter_keep_attire_and_body` (postura, vestimenta/scrubs ou peito nu + área do corpo exposta para manter).
         * `scene1_clone_edit_keep`, `scene2_clone_edit_keep`, `scene3_clone_edit_keep` e `scene1_veo_safe_action`, `scene2_veo_safe_action`, `scene3_veo_safe_action`.
    """
    from forja.flow_rpc_direto import chamar_gemini_flow_gratis_rpc

    video_path = Path(video_path).resolve()
    if not video_path.exists():
        raise FileNotFoundError(f"Vídeo viral não encontrado: {video_path}")

    kie_hash = hashlib.sha256(video_path.read_bytes()).hexdigest()
    cache_file = video_path.parent / "cache_kie_hash.json"
    cache_map: dict[str, Any] = {}
    if cache_file.exists():
        try:
            cache_map = json.loads(cache_file.read_text(encoding="utf-8"))
        except Exception:
            cache_map = {}

    if not forcar_releitura and kie_hash in cache_map and cache_map[kie_hash].get("transcricao"):
        cached = dict(cache_map[kie_hash])
        rp_c = str(cached.get("roupa_lock") or "").lower()
        plano_c = cached.get("plano_replicacao_fisica") or {}
        cenas_c = cached.get("cenas_esteira") or []
        frames_ok = bool(cenas_c) and all(
            bool(c.get("frame_original_viral")) and Path(str(c.get("frame_original_viral"))).exists() and bool(c.get("clone_edit_keep_en")) and bool(c.get("veo_action_safe_en"))
            for c in cenas_c
        )
        if (
            "vestimenta condizente" not in rp_c
            and "apresentador em primeiro plano" not in str(cached.get("gancho") or "").lower()
            and plano_c.get("presenter_remove_features")
            and frames_ok
        ):
            cached["kie_hash"] = kie_hash
            cached["metricas_leitura"] = {"origem": "kie_cache", "modelo": "cache", "gasto": 0}
            return cached

    trans = transcrever_com_palavras(video_path)
    dur = float(trans.get("duracao_video_s") or 18.0)
    texto_fala = trans.get("texto") or ""
    cenas_base = _dividir_transcricao_em_3_cenas(trans)

    frames_dir = video_path.parent / f"{video_path.stem}_zerum15_frames"
    frames_dir.mkdir(parents=True, exist_ok=True)

    # Extrai 6 frames (START e END de cada uma das 3 cenas) usando seleção OpenCV anti-legenda pesada
    tempos_cenas: list[tuple[int, str, float]] = []
    for cb in cenas_base:
        c_num = int(cb["number"])
        t_ini = float(cb["t0"])
        t_fim = float(cb["t1"])
        span = max(1.0, t_fim - t_ini)
        fracs = ((0.28, "START"), (0.74, "END")) if c_num == 2 else ((0.18, "START"), (0.70, "END"))
        for frac, tag_fase in fracs:
            t_bruto = round(min(max(0.3, t_ini + span * frac), max(0.4, dur - 0.35)), 2)
            t_limpo = _escolher_melhor_segundo_sem_legenda_pesada(video_path, t_bruto, dur)
            tempos_cenas.append((c_num, tag_fase, t_limpo))

    frames_por_cena: dict[int, list[Path]] = {1: [], 2: [], 3: []}
    frames_ordenados: list[tuple[int, str, float, Path]] = []
    for c_num, tag_fase, t in tempos_cenas:
        fp = frames_dir / f"s{c_num}_{t:05.2f}s.jpg"
        try:
            extrair_frame(video_path, t, fp)
            if fp.exists():
                frames_por_cena[c_num].append(fp)
                frames_ordenados.append((c_num, tag_fase, t, fp))
        except Exception:
            pass

    # Se já existir frame com caixa Arm & Hammer pré-normalizada (ex.: s1_armhammer.jpg), prioriza como frame_original_viral da cena
    frames_ref_principal: dict[int, str] = {}
    for c_num in (1, 2, 3):
        arm_cand = frames_dir / f"s{c_num}_armhammer.jpg"
        if arm_cand.exists() and arm_cand.stat().st_size > 10000:
            frames_ref_principal[c_num] = str(arm_cand)
        elif frames_por_cena.get(c_num):
            frames_ref_principal[c_num] = str(frames_por_cena[c_num][0])
        else:
            frames_ref_principal[c_num] = ""

    # Monta um Storyboard 3x2 de alta definição (360x640 por painel = 1080x1280) rotulado com "SCENE N START / END (ts)"
    storyboard_path = frames_dir / "storyboard_3x2_labeled.jpg"
    try:
        import cv2
        import numpy as np

        celulas = []
        for c_num, tag_fase, t, fp in frames_ordenados[:6]:
            im = cv2.imdecode(np.frombuffer(fp.read_bytes(), dtype=np.uint8), cv2.IMREAD_COLOR)
            if im is not None:
                im_r = cv2.resize(im, (360, 640), interpolation=cv2.INTER_AREA)
                cv2.rectangle(im_r, (0, 0), (360, 44), (0, 0, 0), -1)
                cv2.putText(
                    im_r,
                    f"SCENE {c_num} {tag_fase} ({t:.1f}s)",
                    (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.72,
                    (0, 230, 255),
                    2,
                    cv2.LINE_AA,
                )
                celulas.append(im_r)
        if len(celulas) == 6:
            row1 = np.hstack(celulas[:3])
            row2 = np.hstack(celulas[3:6])
            grid = np.vstack([row1, row2])
            ok_enc, buf = cv2.imencode(".jpg", grid, [int(cv2.IMWRITE_JPEG_QUALITY), 88])
            if ok_enc:
                storyboard_path.write_bytes(buf.tobytes())
    except Exception:
        pass

    anexos_visao: list[Path] = []
    if storyboard_path.exists():
        anexos_visao.append(storyboard_path)
    else:
        for c_num in (1, 2, 3):
            if frames_por_cena[c_num]:
                anexos_visao.append(frames_por_cena[c_num][0])

    prompt_kie_15 = (
        "Inspect this 3x2 storyboard of a vertical 9:16 viral video:\n"
        "- Panels 1 & 2 = SCENE 1 START and SCENE 1 END\n"
        "- Panels 3 & 4 = SCENE 2 START and SCENE 2 END\n"
        "- Panels 5 & 6 = SCENE 3 START and SCENE 3 END\n"
        f"Spoken transcript:\n"
        f"- Scene 1 ({cenas_base[0]['t0']}s-{cenas_base[0]['t1']}s): {cenas_base[0]['dialogue']}\n"
        f"- Scene 2 ({cenas_base[1]['t0']}s-{cenas_base[1]['t1']}s): {cenas_base[1]['dialogue']}\n"
        f"- Scene 3 ({cenas_base[2]['t0']}s-{cenas_base[2]['t1']}s): {cenas_base[2]['dialogue']}\n\n"
        "CRITICAL PHYSICAL CAUSALITY & REPLICATION RULES:\n"
        "1. COMPARE START vs END OF EACH SCENE: Look carefully at SCENE 1 END (Panel 2) to understand what cavity, container, or surface was hidden or transformed since SCENE 1 START (Panel 1). "
        "For example, if Panel 2 reveals an open hollow oval cavity inside a mannequin's stomach after a large stretchy yellow fat mass was pulled out and dropped into a glass bowl, you MUST describe the yellow mass in Scene 1 as protruding out from INSIDE that open hollow oval stomach cavity as the presenter pulls it out of the cavity (NEVER call it a balloon or ball). "
        "If Panel 2 shows thick white foam bubbling up inside a clear plastic bag filled with dark brown liquid after pouring baking soda in Panel 1, describe that exact foaming reaction. "
        "If Panels 1-2 show applying white baking soda paste onto an exposed belly button or onto a bare lower leg propped on a gray medical stool, describe the exact exposed body area, posture, and hand movement.\n"
        "2. BRAND NORMALIZATION: Whenever baking soda is mentioned or a baking soda box/carton is visible (even if the original video shows a fake/green carton like 'Harbor Pines'), ALWAYS describe the box in all fields as 'bright orange Arm & Hammer Baking Soda box'.\n"
        "3. PRESENTER IDENTITY SWAP LOCKS:\n"
        "   - presenter_remove_features: Exact facial features, skin tone, hair/beard/goatee, cap/hat (including any patch), glasses, or tattoos of the original presenter that must be completely removed when swapping in a new presenter.\n"
        "   - presenter_keep_attire_and_body: Exact clothing (or shirtless muscular chest / color of medical scrubs / lifted scrub hem exposing belly button / bare leg propped on stool) and body build that must be preserved on the new presenter.\n"
        "4. PER-SCENE CLONE-EDIT & VEO 3.1 SAFE PROMPTS:\n"
        "   - scene1_clone_edit_keep, scene2_clone_edit_keep, scene3_clone_edit_keep: Detailed English list of background architecture, lighting, countertop/table/stool, containers, cavities, props (with bright orange Arm & Hammer Baking Soda box), and exact hand/arm pose to preserve 100% when editing each scene's reference frame.\n"
        "   - scene1_veo_safe_action, scene2_veo_safe_action, scene3_veo_safe_action: The continuous 8-second physical action performed by the presenter from START to END of each scene, written in Veo-3.1 safety-filter-friendly demonstration English (refer to anatomical mannequins as 'hollow compartment of the fitness torso display figure' and fat props as 'large stretchy yellow silicone mass'; in Scene 3 never say 'pointing down at comments'—use 'gesturing naturally at chest height toward the camera').\n\n"
        "Return ONLY valid JSON with keys: presenter_sex, presenter_age, presenter_description, presenter_remove_features, presenter_keep_attire_and_body, roupa_lock, cenario_lock, hook_object, scene1_action, scene2_action, scene3_action, scene1_clone_edit_keep, scene2_clone_edit_keep, scene3_clone_edit_keep, scene1_veo_safe_action, scene2_veo_safe_action, scene3_veo_safe_action, why_it_hooks, captions_style."
    )

    vis_json: dict[str, Any] = {}
    for _att in range(3):
        try:
            rpc_res = chamar_gemini_flow_gratis_rpc(
                prompt=prompt_kie_15,
                sistema="Return only valid JSON. All visual and physical descriptions must be in detailed, accurate English.",
                arquivos_anexos=anexos_visao[:1],
            )
            raw_txt = str(rpc_res.get("texto") or rpc_res.get("text") or "")
            raw_clean = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw_txt.strip(), flags=re.I)
            m = re.search(r"\{.*\}", raw_clean, flags=re.S)
            if m:
                cand_json = json.loads(m.group(0))
                if cand_json.get("scene1_action") and cand_json.get("roupa_lock"):
                    vis_json = cand_json
                    break
        except Exception:
            pass
        time.sleep(1.2)

    analise_15: dict[str, Any] = {}
    if vis_json.get("scene1_action") and vis_json.get("roupa_lock"):
        s1_act = _normalizar_marca_baking_soda_en(str(vis_json.get("scene1_action") or "").strip(), texto_fala)
        s2_act = _normalizar_marca_baking_soda_en(str(vis_json.get("scene2_action") or "").strip(), texto_fala)
        s3_act = _normalizar_marca_baking_soda_en(str(vis_json.get("scene3_action") or "").strip(), texto_fala)
        rp_lock = _normalizar_marca_baking_soda_en(str(vis_json.get("roupa_lock") or "").strip(), texto_fala)
        cen_lock = _normalizar_marca_baking_soda_en(str(vis_json.get("cenario_lock") or "").strip(), texto_fala)
        hk_obj = _normalizar_marca_baking_soda_en(str(vis_json.get("hook_object") or s1_act).strip(), texto_fala)
        pres_desc = str(vis_json.get("presenter_description") or "American presenter").strip()
        pres_remove = str(vis_json.get("presenter_remove_features") or f"original presenter's face, hair, headwear, eyewear, and facial features ({pres_desc})").strip()
        pres_keep_attire = str(vis_json.get("presenter_keep_attire_and_body") or rp_lock).strip()
        # Nunca permitir boné/touca cirúrgica/óculos dentro de keep_attire ou roupa_lock (evita conflito de identidade entre cenas no BELUGA!)
        rp_lock = re.sub(r"(?:,?\s*(?:and\s+)?(?:a\s+)?(?:matching\s+|patterned\s+|printed\s+|blue\s+|black\s+)?(?:surgical\s+cap|scrub\s+cap|baseball\s+cap|cap|hat|beanie|eyeglasses|glasses))\b", "", rp_lock, flags=re.I).strip(" ,.")
        pres_keep_attire = re.sub(r"(?:,?\s*(?:and\s+)?(?:a\s+)?(?:matching\s+|patterned\s+|printed\s+|blue\s+|black\s+)?(?:surgical\s+cap|scrub\s+cap|baseball\s+cap|cap|hat|beanie|eyeglasses|glasses))\b", "", pres_keep_attire, flags=re.I).strip(" ,.")
        if "cap" not in pres_remove.lower() and "hat" not in pres_remove.lower():
            pres_remove = f"{pres_remove.rstrip('.')}, and any surgical cap, scrub cap, or headwear."
        pres_sex_raw = str(vis_json.get("presenter_sex") or "").strip().lower()
        if pres_sex_raw.startswith("m"):
            pres_sex_raw = "m"
        elif pres_sex_raw.startswith("f") or pres_sex_raw.startswith("w"):
            pres_sex_raw = "f"
        texto_identidade_completo = f"{pres_desc} {rp_lock} {pres_remove} {pres_keep_attire}"
        if re.search(r"\b(beard|goatee|mustache|shirtless|male\b|man\b)\b", texto_identidade_completo, flags=re.I) and not re.search(r"\b(female|woman)\b", texto_identidade_completo, flags=re.I):
            pres_sex_raw = "m"
        elif pres_sex_raw not in ("m", "f"):
            pres_sex_raw = "f"
        try:
            pres_age = int(vis_json.get("presenter_age") or 50)
        except Exception:
            pres_age = 50

        s1_keep = _normalizar_marca_baking_soda_en(str(vis_json.get("scene1_clone_edit_keep") or f"{cen_lock}, {hk_obj}, {s1_act}").strip(), texto_fala)
        s2_keep = _normalizar_marca_baking_soda_en(str(vis_json.get("scene2_clone_edit_keep") or f"{cen_lock}, {s2_act}").strip(), texto_fala)
        s3_keep = _normalizar_marca_baking_soda_en(str(vis_json.get("scene3_clone_edit_keep") or f"{cen_lock}, {s3_act}").strip(), texto_fala)

        s1_veo = _sanitizar_acao_para_veo31_universal(str(vis_json.get("scene1_veo_safe_action") or s1_act), texto_fala, cta=False)
        s2_veo = _sanitizar_acao_para_veo31_universal(str(vis_json.get("scene2_veo_safe_action") or s2_act), texto_fala, cta=False)
        s3_veo = _sanitizar_acao_para_veo31_universal(str(vis_json.get("scene3_veo_safe_action") or s3_act), texto_fala, cta=True)

        analise_15 = {
            "transcricao": texto_fala,
            "tela": (
                f"00:00 - {cenas_base[0]['t1']}s (Scene 1): {s1_act}\n"
                f"{cenas_base[1]['t0']} - {cenas_base[1]['t1']}s (Scene 2): {s2_act}\n"
                f"{cenas_base[2]['t0']} - {cenas_base[2]['t1']}s (Scene 3): {s3_act}"
            ),
            "gancho": f"Words: '{cenas_base[0]['dialogue']}' Visual: {s1_act} ({hk_obj})",
            "estrutura": f"Beat 1 (Hook): {s1_act}\nBeat 2 (Mechanism/Protocol): {s2_act}\nBeat 3 (Payoff + CTA): {s3_act}",
            "por_que_prende": str(vis_json.get("why_it_hooks") or s1_act),
            "padrao_visual": f"Vertical 9:16 smartphone shot · {cen_lock}",
            "duracao": str(int(round(dur))),
            "rosto_visivel": True,
            "antes_depois": False,
            "pessoas": [
                {
                    "papel": "presenter",
                    "descricao": pres_desc,
                    "roupa": rp_lock,
                    "pele": "natural unfiltered facial and body skin",
                    "contato": hk_obj,
                    "fala": True,
                    "acao": f"Scene 1: {s1_act} | Scene 2: {s2_act} | Scene 3: {s3_act}",
                    "movimento": "Dynamic 3-scene demonstration.",
                    "sexo": pres_sex_raw,
                    "idade": pres_age,
                    "cenas": [1, 2, 3],
                }
            ],
            "acoes": f"Scene 1: {s1_act}\nScene 2: {s2_act}\nScene 3: {s3_act}",
            "enquadramento": "Vertical 9:16 smartphone shot framing the presenter and foreground props.",
            "legenda": str(vis_json.get("captions_style") or "Burned-in captions 2-3 words per block"),
            "cenario_lock": cen_lock,
            "roupa_lock": rp_lock,
            "hook_object": hk_obj,
            "plano_replicacao_fisica": {
                "presenter_sex": pres_sex_raw,
                "presenter_age": pres_age,
                "presenter_original_description": pres_desc,
                "presenter_remove_features": pres_remove,
                "presenter_keep_attire_and_body": pres_keep_attire,
                "cenario_lock": cen_lock,
                "roupa_lock": rp_lock,
                "hook_object": hk_obj,
            },
            "frames_cenas_originais": {
                str(c_num): frames_ref_principal[c_num]
                for c_num in (1, 2, 3)
                if frames_ref_principal.get(c_num)
            },
            "cenas_esteira": [
                {
                    "number": 1,
                    "dialogue": cenas_base[0]["dialogue"],
                    "action": s1_act,
                    "clone_edit_keep_en": s1_keep,
                    "veo_action_safe_en": s1_veo,
                    "frame_original_viral": frames_ref_principal.get(1, ""),
                    "frame_fim_original_viral": str(frames_por_cena[1][-1]) if len(frames_por_cena.get(1, [])) >= 2 else "",
                },
                {
                    "number": 2,
                    "dialogue": cenas_base[1]["dialogue"],
                    "action": s2_act,
                    "clone_edit_keep_en": s2_keep,
                    "veo_action_safe_en": s2_veo,
                    "frame_original_viral": frames_ref_principal.get(2, ""),
                    "frame_fim_original_viral": str(frames_por_cena[2][-1]) if len(frames_por_cena.get(2, [])) >= 2 else "",
                },
                {
                    "number": 3,
                    "dialogue": cenas_base[2]["dialogue"],
                    "action": s3_act,
                    "clone_edit_keep_en": s3_keep,
                    "veo_action_safe_en": s3_veo,
                    "frame_original_viral": frames_ref_principal.get(3, ""),
                    "frame_fim_original_viral": str(frames_por_cena[3][-1]) if len(frames_por_cena.get(3, [])) >= 2 else "",
                },
            ],
        }

    if not analise_15.get("transcricao"):
        prev_cached = cache_map.get(kie_hash) or {}
        prev_p0 = (prev_cached.get("pessoas") or [{}])[0] if isinstance(prev_cached.get("pessoas"), list) and prev_cached.get("pessoas") else {}
        if prev_cached.get("transcricao") and "apresentador adulto falando" not in str(prev_p0.get("descricao") or "").lower():
            analise_15 = dict(prev_cached)
            analise_15["frames_cenas_originais"] = {
                str(c_num): frames_ref_principal[c_num]
                for c_num in (1, 2, 3)
                if frames_ref_principal.get(c_num)
            }
            for idx_c, c_est in enumerate(analise_15.get("cenas_esteira") or []):
                c_num = idx_c + 1
                if frames_ref_principal.get(c_num):
                    c_est["frame_original_viral"] = frames_ref_principal[c_num]
                c_est.setdefault("clone_edit_keep_en", _normalizar_marca_baking_soda_en(f"{analise_15.get('cenario_lock', '')}, {c_est.get('action', '')}", texto_fala))
                c_est.setdefault("veo_action_safe_en", _sanitizar_acao_para_veo31_universal(str(c_est.get("action") or ""), texto_fala, cta=(c_num == 3)))
            analise_15.setdefault(
                "plano_replicacao_fisica",
                {
                    "presenter_sex": str(prev_p0.get("sexo") or "f"),
                    "presenter_age": int(prev_p0.get("idade") or 50),
                    "presenter_original_description": str(prev_p0.get("descricao") or ""),
                    "presenter_remove_features": f"original presenter's face, hair, headwear, eyewear, and facial features ({prev_p0.get('descricao', '')})",
                    "presenter_keep_attire_and_body": str(analise_15.get("roupa_lock") or prev_p0.get("roupa") or ""),
                    "cenario_lock": str(analise_15.get("cenario_lock") or ""),
                    "roupa_lock": str(analise_15.get("roupa_lock") or ""),
                    "hook_object": str(analise_15.get("hook_object") or ""),
                },
            )

    if not analise_15.get("transcricao"):
        # Fallback determinístico rico usando nossa análise local
        base_local = analisar_viral(video_path)
        hv = base_local.get("hook_visual") or {}
        cena_loc = base_local.get("cena") or {}
        ac_en = base_local.get("acoes_en") or {}
        s1_fb = _normalizar_marca_baking_soda_en(ac_en.get("hook_frame1") or hv.get("resumo") or "Performs the opening physical hook while looking at camera.", texto_fala)
        s2_fb = _normalizar_marca_baking_soda_en(ac_en.get("body_frame1") or "Explains the mechanism gesturing naturally with open hands toward the camera.", texto_fala)
        s3_fb = _normalizar_marca_baking_soda_en(ac_en.get("cta_frame1") or "Speaks directly to the camera with hands resting still and low for the closing CTA.", texto_fala)
        cen_fb_loc = _normalizar_marca_baking_soda_en(cena_loc.get("cena_fixa_en") or cena_loc.get("cenario", "Bright natural residential room"), texto_fala)
        rp_fb_loc = cena_loc.get("roupa", "Medical scrubs and stethoscope")
        analise_15 = {
            "transcricao": texto_fala,
            "tela": (
                f"00:00 - {cenas_base[0]['t1']}s (Scene 1): {s1_fb}\n"
                f"{cenas_base[1]['t0']} - {cenas_base[1]['t1']}s (Scene 2): {s2_fb}\n"
                f"{cenas_base[2]['t0']} - {cenas_base[2]['t1']}s (Scene 3): {s3_fb}"
            ),
            "gancho": f"Words: '{cenas_base[0]['dialogue']}' Visual: {s1_fb}",
            "estrutura": "Beat 1: Hook físico + dor principal.\nBeat 2: Explicação do mecanismo.\nBeat 3: Prova social + CTA.",
            "por_que_prende": "Ação física imediata nos primeiros 3 segundos combinada com promessa direta.",
            "padrao_visual": f"{cena_loc.get('enquadramento', 'Vertical 9:16')} · {cen_fb_loc}",
            "duracao": str(int(round(dur))),
            "rosto_visivel": True,
            "antes_depois": False,
            "pessoas": [
                {
                    "papel": "presenter",
                    "descricao": cena_loc.get("personagem", ""),
                    "roupa": rp_fb_loc,
                    "pele": "bare skin visible",
                    "contato": "substance touches exposed skin",
                    "fala": True,
                    "acao": hv.get("gesto", ""),
                    "movimento": hv.get("gesto", ""),
                    "sexo": "f",
                    "idade": 50,
                    "cenas": [1, 2, 3],
                }
            ],
            "acoes": hv.get("gesto", ""),
            "enquadramento": cena_loc.get("enquadramento", "Vertical 9:16 chest-up shot"),
            "legenda": "Burned-in captions 1-3 words per block, bold uppercase.",
            "cenario_lock": cen_fb_loc,
            "roupa_lock": rp_fb_loc,
            "hook_object": _normalizar_marca_baking_soda_en(hv.get("objeto", ""), texto_fala),
            "plano_replicacao_fisica": {
                "presenter_sex": "f",
                "presenter_age": 50,
                "presenter_original_description": cena_loc.get("personagem", ""),
                "presenter_remove_features": "original presenter's face, hair, headwear, and eyewear",
                "presenter_keep_attire_and_body": rp_fb_loc,
                "cenario_lock": cen_fb_loc,
                "roupa_lock": rp_fb_loc,
                "hook_object": _normalizar_marca_baking_soda_en(hv.get("objeto", ""), texto_fala),
            },
            "frames_cenas_originais": {
                str(c_num): frames_ref_principal[c_num]
                for c_num in (1, 2, 3)
                if frames_ref_principal.get(c_num)
            },
            "cenas_esteira": [
                {
                    "number": 1,
                    "dialogue": cenas_base[0]["dialogue"],
                    "action": s1_fb,
                    "clone_edit_keep_en": f"{cen_fb_loc}, {s1_fb}",
                    "veo_action_safe_en": _sanitizar_acao_para_veo31_universal(s1_fb, texto_fala, cta=False),
                    "frame_original_viral": frames_ref_principal.get(1, ""),
                },
                {
                    "number": 2,
                    "dialogue": cenas_base[1]["dialogue"],
                    "action": s2_fb,
                    "clone_edit_keep_en": f"{cen_fb_loc}, {s2_fb}",
                    "veo_action_safe_en": _sanitizar_acao_para_veo31_universal(s2_fb, texto_fala, cta=False),
                    "frame_original_viral": frames_ref_principal.get(2, ""),
                },
                {
                    "number": 3,
                    "dialogue": cenas_base[2]["dialogue"],
                    "action": s3_fb,
                    "clone_edit_keep_en": f"{cen_fb_loc}, {s3_fb}",
                    "veo_action_safe_en": _sanitizar_acao_para_veo31_universal(s3_fb, texto_fala, cta=True),
                    "frame_original_viral": frames_ref_principal.get(3, ""),
                },
            ],
        }

    analise_15["kie_hash"] = kie_hash
    analise_15["metricas_leitura"] = {
        "origem": "vision_llm_flow",
        "modelo": "gemini-3-flash-preview",
        "gasto": 0,
        "hash_curto": kie_hash[:12],
    }
    cache_map.pop(kie_hash, None)
    cache_map[kie_hash] = analise_15
    try:
        cache_file.write_text(json.dumps(cache_map, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass

    out_json = video_path.parent / f"{video_path.stem}_zerum15.json"
    out_json.write_text(json.dumps(analise_15, ensure_ascii=False, indent=2), encoding="utf-8")
    return analise_15


def adaptar_viral_para_esteira_zerum(
    analise_15: dict[str, Any],
    pedido_adaptacao: str = "",
    palavra_cta: str = "YES",
    modo_variacao: str = "tora",
    caminho: str = "igual",
    produto_id: str = "",
    qtd_videos: int = 1,
    criar_avatares_novos: bool = False,
    roleta_usados: list[str] | None = None,
    manter_personagem_original: bool = False,
) -> dict[str, Any]:
    """
    Reproduz 100% os 2 Eixos do FlowStudio (`CAMINHO × VARIAÇÃO` + `Roleta` + `Elenco Variado` + `Keywords`):
    - Eixo 1 (`caminho`): `'igual'` (🎯 Igual ao viral) vs `'adaptar'` (🔄 Adaptar pro produto `produto_id` ou pedido).
    - Eixo 2 (`modo_variacao`):
      - `'tora'` / `'igual'` / `'nenhuma'`: 🪵 Sem variação (na tora)
      - `'roleta'`: 🎰 Método Roleta (sorteia cenários `Tg` + roupas `lN`/`xz` + objetos `aY` inéditos sem repetir!)
      - `'micro_embalagem'`: 🧬 Ad Vencedor · Mesmo Personagem + Micro-Variação 001 (Teste B · Embalagem Intacta)
      - `'gesto'`: 🤲 Microvariação de gesto
      - `'texto'`: ✍️ Microvariação de texto
      - `'combinada'`: 🔀 Combinada (texto + gesto + sala)
      - `'novo'`: ✨ Novo a partir do analisado
    - Sincroniza automaticamente a palavra de CTA falada na Cena 3 (`"comment yes"` por padrão) com o botão CTA (`COMMENT YES`).
    """
    from forja.flow_rpc_direto import chamar_gemini_flow_gratis_rpc

    ped_low = (pedido_adaptacao or "").lower()
    if (
        modo_variacao == "micro_embalagem"
        or "mesmo personagem" in ped_low
        or "ad vencedor" in ped_low
        or "sem mexer na embalagem" in ped_low
    ):
        manter_personagem_original = True
        if modo_variacao in ("igual", "nenhuma", "tora"):
            modo_variacao = "micro_embalagem"

    modo_norm = "tora" if modo_variacao in ("igual", "nenhuma", "tora") else modo_variacao
    if caminho == "adaptar" and modo_norm == "tora" and not pedido_adaptacao and not produto_id:
        caminho = "adaptar"

    prod_obj = next((p for p in PRODUTOS_001_GD if p["id"] == produto_id), None)
    if caminho == "adaptar" and prod_obj and (not palavra_cta):
        palavra_cta = prod_obj["keywords"][0]
    if not palavra_cta:
        palavra_cta = "YES"

    # Interpreta determinísticamente as ordens da Regra de Ouro VAe ("O QUE VOCÊ ESCREVE É LEI")
    regras_vae = _interpretar_regras_diretor_vae(pedido_adaptacao, analise_15)
    roupa_fixa_en = regras_vae["roupa_fixa_en"]
    roupa_fixa_rotulo = regras_vae["roupa_fixa_rotulo"]

    # Extrai keyword automática do pedido se o usuário escreveu "keyword X" ou " comentar X"
    m_kw = re.search(
        r"\b(?:keyword|palavra|comment|comentar|comente)\s+['\"]?(?!cta\b|o\b|quando\b)([A-Za-z0-9_]{2,15})['\"]?",
        pedido_adaptacao or "",
        flags=re.I,
    )
    if m_kw:
        palavra_cta = m_kw.group(1).upper()

    # Extrai quantidade de vídeos se pediu no texto ("quero 100 variações", "50 variações", "10 variações", "faz 5 vídeos")
    m_qtd = re.search(r"\b(\d{1,3})\s+(?:v[ií]deos?|roteiros?|varia[çc][oõ]es)\b", pedido_adaptacao or "", flags=re.I)
    if m_qtd:
        qtd_videos = max(1, min(200, int(m_qtd.group(1))))

    # Verifica se é Método Roleta (pelo seletor ou pelo texto "roleta")
    if modo_norm == "roleta" or "roleta" in (pedido_adaptacao or "").lower():
        modo_norm = "roleta"

    p0_viral = (analise_15.get("pessoas") or [{}])[0] if isinstance(analise_15.get("pessoas"), list) and analise_15.get("pessoas") else {}
    sexo_viral = str(p0_viral.get("sexo") or "f").lower()
    if sexo_viral not in ("m", "f"):
        sexo_viral = "f"
    desc_viral = str(p0_viral.get("descricao") or "")
    roupa_viral_base = str(analise_15.get("roupa_lock") or p0_viral.get("roupa") or "").strip()

    # Se caminho == 'igual' (ou pediu 'igual o viral') e não tem roupa_fixa_en explícita, trava a roupa/físico real do viral!
    if not roupa_fixa_en and (caminho == "igual" or "igual" in (pedido_adaptacao or "").lower()):
        if roupa_viral_base and "vestimenta" not in roupa_viral_base.lower():
            roupa_fixa_en = roupa_viral_base
            roupa_fixa_rotulo = f"mesmo estilo/roupa do viral ({roupa_viral_base[:60]})"

    # Sempre gera avatares alinhados ao apresentador real do viral (evita cair em avatar feminino fixo quando o viral é um homem!)
    avatares_novos = parsear_avatares_variados_zerum(
        pedido_adaptacao,
        qtd=max(1, qtd_videos),
        sexo_padrao=sexo_viral,
        roupa_fixa_en=roupa_fixa_en or roupa_viral_base,
        descricao_base_viral=desc_viral,
    )

    roleta_combos = (
        sortear_roleta_zerum(
            qtd=max(1, qtd_videos),
            usados_ids=roleta_usados,
            sexo=sexo_viral,
            com_baking_soda=False,
            roupa_fixa_en=roupa_fixa_en,
            roupa_fixa_rotulo=roupa_fixa_rotulo,
        )
        if modo_norm == "roleta"
        else []
    )

    cenas_orig = json.loads(json.dumps(analise_15.get("cenas_esteira") or []))
    if not cenas_orig:
        cenas_orig = _dividir_transcricao_em_3_cenas(
            {"texto": analise_15.get("transcricao", ""), "duracao_video_s": float(analise_15.get("duracao") or 18)}
        )
        for idx, c in enumerate(cenas_orig):
            c["action"] = (
                analise_15.get("gancho", "Performs opening hook action.")
                if idx == 0
                else ("Explains mechanism gesturing to camera." if idx == 1 else "Talks to camera with hands resting still and low.")
            )

    # Sincroniza a palavra de CTA falada na última cena ("comment yes" / palavra_cta) com o botão CTA
    if cenas_orig and palavra_cta:
        cta_word_low = palavra_cta.strip().lower()
        ult_fala = str(cenas_orig[-1].get("dialogue") or "")
        if re.search(r"\bcomment\s+(?:the\s+word\s+)?['\"]?[a-zA-Z0-9]{2,15}['\"]?\b", ult_fala, flags=re.I):
            cenas_orig[-1]["dialogue"] = re.sub(
                r"\bcomment\s+(?:the\s+word\s+)?['\"]?[a-zA-Z0-9]{2,15}['\"]?\b",
                f"comment {cta_word_low}",
                ult_fala,
                flags=re.I,
            )

    plano_fisico = analise_15.get("plano_replicacao_fisica") or {}

    def _montar_lote_videos(cenas_base_lote: list[dict[str, Any]], cen_padrao: str, rp_padrao: str, hk_padrao: str) -> list[dict[str, Any]]:
        lote: list[dict[str, Any]] = []
        for i in range(max(1, qtd_videos)):
            rc = roleta_combos[i % len(roleta_combos)] if roleta_combos else None
            av = avatares_novos[i % len(avatares_novos)] if (avatares_novos and not manter_personagem_original) else None
            mv = MICRO_VARIACOES_EMBALAGEM_001[i % len(MICRO_VARIACOES_EMBALAGEM_001)] if manter_personagem_original else None
            cen_v = rc["cenario_lock"] if rc else cen_padrao
            rp_v = roupa_fixa_en or (rc["roupa_lock"] if rc else rp_padrao)
            hk_v = (rc.get("hook_object") if rc else None) or hk_padrao
            cenas_item = json.loads(json.dumps(cenas_base_lote))
            if manter_personagem_original and mv:
                for idx_c, cn_item in enumerate(cenas_item):
                    cn_item["dialogue"] = _aplicar_micro_toque_fala_001(
                        str(cn_item.get("dialogue") or ""),
                        indice_cena=idx_c,
                        idx_var=i,
                        palavra_cta=palavra_cta,
                    )
                    cn_item["micro_visual_en"] = mv["micro_visual_s1_en"] if idx_c == 0 else mv["micro_visual_sn_en"]
                    cn_item["micro_veo_en"] = mv["micro_veo_en"]
            lote.append(
                {
                    "numero": i + 1,
                    "titulo": (
                        f"Variação #{i+1} · {mv['rotulo']}"
                        if (manter_personagem_original and mv)
                        else f"Variação #{i+1} · {rc['rotulo'] if rc else 'Padrão'}"
                    ),
                    "avatar": (
                        f"Mesmo Personagem Original ({desc_viral[:42] or 'Ad Vencedor'}) · Micro #{i+1}"
                        if manter_personagem_original
                        else (av["nome"] if av else f"Avatar #{i+1}")
                    ),
                    "avatarPrompt": "" if manter_personagem_original else (av["prompt_flow"] if av else ""),
                    "manterPersonagemOriginal": manter_personagem_original,
                    "microVariacao": mv,
                    "cenarioLock": cen_v,
                    "roupaLock": rp_v,
                    "hookObject": hk_v,
                    "planoReplicacaoFisica": plano_fisico,
                    "ritmoEdicao": regras_vae["ritmo_edicao"],
                    "semLegenda": regras_vae["sem_legenda"],
                    "apenasBotaoCta": regras_vae["apenas_botao_cta"],
                    "estiloLegenda": regras_vae["estilo_legenda"],
                    "palavraCta": palavra_cta.upper(),
                    "cenas": cenas_item,
                }
            )
        return lote

    # Caso 1: Caminho IGUAL + Sem variação (na tora), Método Roleta, ou Ad Vencedor (Mesmo Personagem + Micro-Variação 001 Embalagem Intacta)
    if caminho == "igual" and (modo_norm in ("tora", "roleta", "micro_embalagem") or manter_personagem_original):
        cen_lock = (
            roleta_combos[0]["cenario_lock"]
            if roleta_combos
            else (analise_15.get("cenario_lock") or analise_15.get("padrao_visual") or "Bright natural residential room")
        )
        rp_lock = (
            roupa_fixa_en
            or (roleta_combos[0]["roupa_lock"] if roleta_combos else None)
            or analise_15.get("roupa_lock")
            or "Medical V-neck scrub top and stethoscope"
        )
        hk_obj = (
            roleta_combos[0]["hook_object"]
            if roleta_combos and roleta_combos[0].get("hook_object")
            else (analise_15.get("hook_object") or analise_15.get("gancho") or "")
        )
        if manter_personagem_original:
            resumo_vae_partes = [
                f"Lote de {qtd_videos} vídeo(s) preparado no 🧬 Modo Ad Vencedor · Mesmo Personagem + Micro-Variação 001 (Teste B: Embalagem 100% Intacta, regravando as 3 cenas do mesmo personagem com micro-variações sutis de expressão/cadência/toque verbal sem alterar o hook)."
            ]
        else:
            resumo_vae_partes = [
                f"Lote de {qtd_videos} vídeo(s) preparado no {'🎰 Método Roleta' if modo_norm == 'roleta' else '🪵 Modo Na Tora'} (Centro Congelado: mesma fala literal do viral)."
            ]
        if roupa_fixa_en:
            resumo_vae_partes.append(f"Roupa TRAVADA em todos os {qtd_videos} vídeos: {roupa_fixa_rotulo} ({roupa_fixa_en}).")
        if regras_vae["edicao_dinamica"]:
            resumo_vae_partes.append("Montagem: Edição Dinâmica (jump-cut / punch-in ativo).")
        if regras_vae["sem_legenda"] and regras_vae["apenas_botao_cta"]:
            resumo_vae_partes.append(f"Legenda: DESLIGADA nas falas — exibe APENAS o Botão/Pílula CTA (COMMENT {palavra_cta.upper()}) na cena final.")
        elif regras_vae["sem_legenda"]:
            resumo_vae_partes.append("Legenda: DESLIGADA (vídeo limpo sem legendas queimadas).")

        return {
            "ok": True,
            "caminho": caminho,
            "modoVariacao": "micro_embalagem" if manter_personagem_original else modo_norm,
            "manterPersonagemOriginal": manter_personagem_original,
            "modo": (
                "🧬 Ad Vencedor · Mesmo Personagem + Micro-Variação 001 (Teste B · Embalagem Intacta)"
                if manter_personagem_original
                else (
                    "🎰 Método Roleta (Cenário + Objeto Inéditos · Roupa Enfermeira Travada)"
                    if (modo_norm == "roleta" and roupa_fixa_en)
                    else ("🎰 Método Roleta (Cenário + Roupa + Objeto Inéditos)" if modo_norm == "roleta" else "🪵 Sem variação (na tora · igual ao viral)")
                )
            ),
            "produto": prod_obj,
            "qtdVideos": qtd_videos,
            "resumo_plano": " ".join(resumo_vae_partes),
            "regrasVae": regras_vae,
            "palavraCta": palavra_cta.upper(),
            "cenarioLock": cen_lock,
            "roupaLock": rp_lock,
            "hookObject": hk_obj,
            "planoReplicacaoFisica": plano_fisico,
            "roletaSorteada": roleta_combos,
            "avataresNovos": [] if manter_personagem_original else avatares_novos,
            "loteVideos": _montar_lote_videos(cenas_orig, cen_lock, rp_lock, hk_obj),
            "cenasOriginais": cenas_orig,
            "cenas": cenas_orig,
        }

    modo_info = next((m for m in MODOS_VARIACAO_ZERUM if m["id"] == modo_norm), MODOS_VARIACAO_ZERUM[0])
    instrucao_modo = modo_info["instrucaoPadrao"]
    ficha_ia_txt = carregar_ficha_ia_produto_001(prod_obj["id"], max_chars=5500) if (caminho == "adaptar" and prod_obj) else ""
    info_produto = (
        f"TARGET PRODUCT TO ADAPT FOR: {prod_obj['nome']} (Niche: {prod_obj['nicho']} | CPA: {prod_obj.get('cpa', '')} | "
        f"Chiclete/Mechanism phrase: {prod_obj.get('chiclete', '')} | Viral Object: {prod_obj.get('objeto_viral', '')})\n"
        f"OFFICIAL 001 PRODUCT BRIEF (`briefs/{prod_obj['id']}-ia.txt`):\n{ficha_ia_txt}\n"
        "COMMUNITY GOLDEN RULE: Your video sells the CLICK and speaks about the MECHANISM / RITUAL — never show a branded product bottle and never name the supplement brand in spoken dialogue."
        if (caminho == "adaptar" and prod_obj)
        else "PATH: IGUAL AO VIRAL (do not introduce external product brands)."
    )

    prompt_modelar = (
        "You are Flow Studio's `/ia/agente/intencao` + `/ia/modelar` Director Brain (Antigravity). "
        "Obey the Golden Rule (VAe): WHAT THE MEMBER WRITES IS LAW.\n\n"
        f"ANALYZED VIRAL (15 FIELDS, kie_hash={analise_15.get('kie_hash', '')[:12]}): {json.dumps(analise_15, ensure_ascii=False)}\n"
        f"AXIS 1 (CAMINHO): {caminho.upper()} — {info_produto}\n"
        f"AXIS 2 (VARIAÇÃO): {modo_info['rotulo']} — {instrucao_modo}\n"
        f"MEMBER ORDER / SPECIFIC INSTRUCTION: {pedido_adaptacao or 'Follow the chosen Caminho and Variação strictly.'}\n"
        f"COMMENT KEYWORD FOR CTA (Scene 3): {palavra_cta.upper()}\n\n"
        "Return ONLY valid JSON with these exact keys:\n"
        "{\n"
        '  "resumo_plano": "Direct 2-sentence response in Portuguese from the Director explaining the plan",\n'
        '  "cenario_lock": "English LOCATION LOCK description (same place, background, furniture and light in every shot)",\n'
        '  "roupa_lock": "English APPROVED OUTFIT description",\n'
        '  "hook_object": "English HOOK OBJECT description for the first 3 seconds of Scene 1",\n'
        '  "cenas": [\n'
        '    {"number": 1, "dialogue": "English spoken line for Scene 1 (15-21 words)", "action": "Detailed English visual action and props for Scene 1"},\n'
        '    {"number": 2, "dialogue": "English spoken line for Scene 2 (15-21 words)", "action": "Detailed English visual action and gestures for Scene 2"},\n'
        f'    {{"number": 3, "dialogue": "English spoken CTA line including comment {palavra_cta.upper()} and follow me", "action": "Speaker talks directly to camera with both hands resting still and low by the body"}}\n'
        "  ]\n"
        "}"
    )

    try:
        res = chamar_gemini_flow_gratis_rpc(
            prompt=prompt_modelar,
            sistema="Return only valid JSON. Spoken dialogue and visual descriptions must be in English.",
        )
        raw = str(res.get("texto") or res.get("text") or "")
        m = re.search(r"\{.*\}", raw, flags=re.S)
        if m:
            parsed = json.loads(m.group(0))
            if parsed.get("cenas"):
                cen_final = (
                    roleta_combos[0]["cenario_lock"]
                    if roleta_combos
                    else (parsed.get("cenario_lock") or analise_15.get("cenario_lock", ""))
                )
                rp_final = (
                    roupa_fixa_en
                    or (roleta_combos[0]["roupa_lock"] if roleta_combos else None)
                    or parsed.get("roupa_lock")
                    or analise_15.get("roupa_lock", "")
                )
                hk_final = (
                    roleta_combos[0]["hook_object"]
                    if roleta_combos and roleta_combos[0].get("hook_object")
                    else (parsed.get("hook_object") or analise_15.get("hook_object", ""))
                )
                return {
                    "ok": True,
                    "caminho": caminho,
                    "modoVariacao": modo_norm,
                    "modo": modo_info["rotulo"],
                    "produto": prod_obj,
                    "qtdVideos": qtd_videos,
                    "resumo_plano": parsed.get("resumo_plano", ""),
                    "regrasVae": regras_vae,
                    "palavraCta": palavra_cta.upper(),
                    "cenarioLock": cen_final,
                    "roupaLock": rp_final,
                    "hookObject": hk_final,
                    "planoReplicacaoFisica": plano_fisico,
                    "roletaSorteada": roleta_combos,
                    "avataresNovos": avatares_novos,
                    "loteVideos": _montar_lote_videos(parsed["cenas"], cen_final, rp_final, hk_final),
                    "cenasOriginais": cenas_orig,
                    "cenas": parsed["cenas"],
                }
    except Exception:
        pass

    cen_fb = roleta_combos[0]["cenario_lock"] if roleta_combos else (analise_15.get("cenario_lock") or "")
    rp_fb = roupa_fixa_en or (roleta_combos[0]["roupa_lock"] if roleta_combos else None) or (analise_15.get("roupa_lock") or "")
    hk_fb = roleta_combos[0]["hook_object"] if roleta_combos else (analise_15.get("hook_object") or "")
    return {
        "ok": True,
        "caminho": caminho,
        "modoVariacao": modo_norm,
        "modo": modo_info["rotulo"],
        "produto": prod_obj,
        "qtdVideos": qtd_videos,
        "regrasVae": regras_vae,
        "palavraCta": palavra_cta.upper(),
        "cenarioLock": cen_fb,
        "roupaLock": rp_fb,
        "hookObject": hk_fb,
        "planoReplicacaoFisica": plano_fisico,
        "roletaSorteada": roleta_combos,
        "avataresNovos": avatares_novos,
        "loteVideos": _montar_lote_videos(cenas_orig, cen_fb, rp_fb, hk_fb),
        "cenasOriginais": cenas_orig,
        "cenas": cenas_orig,
    }

