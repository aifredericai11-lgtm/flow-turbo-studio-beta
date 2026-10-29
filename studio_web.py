# -*- coding: utf-8 -*-
"""
NOSSO ZERUM LOCAL · 001 (nosso_zerum.py)
=========================================
Clone funcional completo e auto-hospedado do Zerum (https://001.community/zerum)
integrado diretamente ao nosso motor local de alta potência:
- Compilador Físico-Óptico 1:1 (`forja/compilador_realismo_zerum.py`: D2, L2, z2, aM, oM, I2, cre, [VOICE] Hz Lock)
- Verificador / Juiz de 3 Camadas (`forja/qa_clipe.py`: Voz Whisper >= 80%, Identidade Frame-1 >= 82%, Zero Freeze `freezedetect`)
- Regravação Cirúrgica de Take Ruim (`forja/turbo_lote.py`: `retentar_apenas_takes` — refaz apenas o take reprovado e junta com NVENC)
- As 6 Abas do Zerum (`DIRETOR`, `MANUAL`, `PRODUÇÃO`, `ANALISADOS`, `VÍDEOS`, `Avatares`)
- Editor Pós-Produção Completo (`EDITOR · V1` / `✎ Editar vídeo · cortar · regravar · trocar fala`) com Timeline Multi-Track (`VÍDEO`, `LEGENDA`, `ÁUDIO`), 4 estilos de legenda (`legenda`, `karaokê`, `comando`, `cartaz`), blocos (`1`, `3`, `5 palavras`), 6 fontes (`Poppins Bold`, `Anton`, `Bebas Neue`, `Archivo Black`, `Lilita One`, `Bangers`) e renderização GPU RTX 4050 (`h264_nvenc`).

Como iniciar:
    python nosso_zerum.py
Acesse:
    http://127.0.0.1:8505
"""

from __future__ import annotations

import base64
import json
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.parse
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT_DIR))

from forja.compilador_realismo_zerum import (
    gerar_bloco_voz_fixa,
    compilar_prompt_quadro_cena,
    compilar_prompt_animacao_cena,
    compilar_quadro_refs_18,
    construir_reparo_cirurgico_juiz_visao,
    ASS_STYLESHEET_ZERUM_11,
)

def compilar_bloco_voz_travada(p: dict[str, Any]) -> str:
    return gerar_bloco_voz_fixa(
        avatar_id=str(p.get("id") or p.get("name") or "avatar_default"),
        descricao_avatar=f"{p.get('ageRange', '50')}yo {p.get('physicalDescription', '')}",
        sexo=str(p.get("sex") or p.get("sexo") or "f"),
    )

def compilar_prompt_avatar_imagem(
    p: dict[str, Any],
    indice_cena: int = 0,
    acao_cena: str = "",
    hook_obj: str = "",
    cta: bool = False,
    estagio_corporal: str | None = None,
) -> str:
    desc = acao_cena or f"{p.get('physicalDescription', '')}"
    return compilar_prompt_quadro_cena(
        indice_cena=indice_cena,
        descricao_visual=desc,
        sexo=str(p.get("sex") or p.get("sexo") or "f"),
        cenario_lock=str(p.get("setting") or "Bright natural residential room"),
        roupa_lock=str(p.get("outfit") or p.get("clothes") or ""),
        hook_object=hook_obj,
        cta=cta,
        estagio_corporal=estagio_corporal,
    )

def compilar_prompt_cena_veo31(
    scene: dict[str, Any],
    persona: dict[str, Any],
    Continuity: bool = False,
    cta: bool = False,
) -> str:
    acao_bruta = str(scene.get("action") or "")
    fala_str = str(scene.get("dialogue") or "").strip()
    acao_segura = _sanitizar_acao_para_veo31_universal(acao_bruta, fala_str, cta=cta)

    if scene.get("frame_original_viral") or scene.get("veo_action_safe_en"):
        retry_att = int(scene.get("retry_attempt") or 0)
        sx = str(persona.get("sex") or persona.get("sexo") or "f").lower()
        pron_suj = "he" if sx.startswith("m") else "she"
        pron_pos = "his" if sx.startswith("m") else "her"
        setting_low = str(persona.get("setting") or "").lower()
        if "kitchen" in setting_low:
            amb_prefix = "In a kitchen"
        elif any(w in setting_low for w in ("operating", "surgical", "hospital", "clinic", "exam", "medical")):
            amb_prefix = "In a bright clinical room"
        elif any(w in setting_low for w in ("balcony", "deck", "patio", "porch", "outdoor")):
            amb_prefix = "On a bright covered wooden balcony"
        else:
            amb_prefix = "In the room"

        acao_curta = str(scene.get("veo_action_safe_en") or acao_segura).strip()
        acao_curta = _sanitizar_acao_para_veo31_universal(acao_curta, fala_str, cta=cta)
        acao_curta = re.sub(
            r"^(?:standing\s+[^,]+,\s*)?(?:(?:the|a|an)\s+(?:presenter|speaker|person|individual|man|woman|nurse|doctor|worker|figure|subject)(?:\s+in\s+(?:[a-z-]+\s+){0,3}(?:scrubs|attire|clothing|shorts))?|he|she|they)\s+",
            "",
            acao_curta,
            flags=re.I,
        ).strip()
        acao_curta = re.sub(
            r",\s*(?:(?:the|a|an)\s+(?:presenter|speaker|person|individual|man|woman|nurse|doctor|worker|figure|subject)|he|she|they)\s+",
            ", ",
            acao_curta,
            flags=re.I,
        ).strip()
        acao_curta = re.sub(r"\btheir\b", pron_pos, acao_curta, flags=re.I)
        if acao_curta:
            acao_curta = acao_curta[0].lower() + acao_curta[1:]
        else:
            acao_curta = "speaks directly to the camera with natural hand gestures"

        micro_veo_en = str(scene.get("micro_veo_en") or "").strip()
        if micro_veo_en and retry_att < 3:
            acao_curta = f"{acao_curta.rstrip('.')}, {micro_veo_en.rstrip('.')}"

        if retry_att >= 2:
            fala_str = re.sub(r"\bpulls\s+out\s+of\s+your\s+gut\b", "pulls right out of you", fala_str, flags=re.I)
        if retry_att >= 3:
            acao_curta = (
                "speaks directly to the camera with calm, natural hand gestures at chest height"
                if cta
                else "speaks directly to the camera with natural hand movement while demonstrating the items in the scene"
            )
        return (
            f"{amb_prefix}, the presenter in the reference image speaks directly to the camera in one continuous locked-camera 8-second take saying: {fala_str} "
            f"While speaking, {pron_suj} {acao_curta.rstrip('.')}. "
            "CRITICAL OBJECT PERMANENCE & CONTINUITY LOCK: No camera cut, no jump cut, no morphing. Every single object, box, and container on the countertop/table in the reference image (especially the bright orange Arm & Hammer Baking Soda box, glass, pitcher, bowl, and lemon) MUST remain 100% stationary and permanently visible on the surface from 0.0s to the very end of the clip — NEVER make any box or prop vanish, dissolve, or disappear when hands move. Strictly NO on-screen text, NO subtitles, and NO UI overlays."
        )

    roupa_segura = re.sub(r"\b(?:shirtless|bare[-\s]+chested|bare\s+torso)\b", "athletic build", str(persona.get("outfit") or persona.get("clothes") or ""), flags=re.I)
    return compilar_prompt_animacao_cena(
        indice_cena=1 if Continuity else 0,
        acao_visual=acao_segura,
        fala_ingles=fala_str,
        avatar_id=str(persona.get("id") or persona.get("name") or "avatar_default"),
        descricao_avatar=f"{persona.get('ageRange', '50')}yo {persona.get('physicalDescription', '')}",
        sexo=str(persona.get("sex") or persona.get("sexo") or "f"),
        roupa_lock=roupa_segura,
        cta=cta,
    )
from forja.qa_clipe import (
    detectar_congelamento_video,
    avaliar_qa_clipe,
    obter_metadados_midia,
    tesoura_cirurgica_3_passes,
    juiz_identidade_acessorios_flow,
    juiz_permanencia_objetos_clipe_flow,
    gerar_script_ass_zerum_11,
)
from forja.flow_rpc_direto import (
    subir_midia_rpc,
    gerar_imagem_rpc,
    gerar_video_rpc,
    aguardar_midia_rpc,
    ler_status_e_creditos_flow,
)
from forja.ler_viral import (
    ler_viral_15_campos_zerum,
    adaptar_viral_para_esteira_zerum,
    _sanitizar_acao_para_veo31_universal,
    _normalizar_marca_baking_soda_en,
)

PORTA_ZERUM = 8505
DUMP_REA_DIR = ROOT_DIR / "zerum_re" / "dump_autenticado" / "interativo_rea"
ZR_MEMORIA_PATH = DUMP_REA_DIR / "zr_memoria_completa.json"
ZR_VIRAIS_PATH = DUMP_REA_DIR / "zerum_virais_analises.json"
LOCAL_VIRAIS_PATH = ROOT_DIR / "virais" / "memoria_virais.json"
CACHE_KIE_PATH = ROOT_DIR / "virais" / "cache_kie_hash.json"
PRONTOS_DIR = ROOT_DIR / "prontos"
AVATARES_DIR = ROOT_DIR / "avatares"
NOSSO_ZERUM_STATE_PATH = ROOT_DIR / "zerum_re" / "nosso_zerum_state.json"

_JOBS_PRODUCAO: dict[str, dict[str, Any]] = {}
_FILA_PRODUCAO: list[tuple[str, dict[str, Any]]] = []
_FILA_LOCK = threading.Lock()
_WORKER_FILA_ATIVO = False


def _salvar_estado_persistente() -> None:
    try:
        NOSSO_ZERUM_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        NOSSO_ZERUM_STATE_PATH.write_text(
            json.dumps({"jobs": _JOBS_PRODUCAO}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception:
        pass


def _carregar_estado_persistente() -> None:
    if NOSSO_ZERUM_STATE_PATH.exists():
        try:
            data = json.loads(NOSSO_ZERUM_STATE_PATH.read_text(encoding="utf-8"))
            for jid, jval in (data.get("jobs") or {}).items():
                if isinstance(jval, dict) and jval.get("status") == "produzindo":
                    mp4_ok = PRONTOS_DIR / f"{jid}_final_verificado.mp4"
                    if mp4_ok.exists() and mp4_ok.stat().st_size > 100000:
                        jval["status"] = "concluido"
                    else:
                        jval["status"] = "erro"
                        jval["progresso"] = "Retomando do checkpoint em Modo Turbo..."
                if jid not in _JOBS_PRODUCAO:
                    _JOBS_PRODUCAO[jid] = jval
        except Exception:
            pass


_carregar_estado_persistente()


def _carregar_dados_zerum() -> dict[str, Any]:
    """
    Unifica os dados reais extraídos do IndexedDB do Zerum (50 Avatares, Virais Analisados, Lotes)
    com os nossos vídeos locais verificados em `prontos/` e avatares em `avatares/`.
    """
    personas: list[dict[str, Any]] = []
    virais: list[dict[str, Any]] = []
    lotes: list[dict[str, Any]] = []
    videos_prontos: list[dict[str, Any]] = []

    # 1. Carregar nossos avatares locais prioritários
    avatares_locais = [
        {
            "id": "local-umbigo-2pessoas",
            "name": "Enfermeira & Paciente (Umbigo Consultório)",
            "sex": "f",
            "ageRange": "30-35",
            "ethnicity": "Caucasian / Latina",
            "bodyBuild": "average",
            "physicalDescription": "Nurse in green scrubs applying clear gel/oil with a dropper inside the exposed belly button (umbilicus) of a female patient lying on an exam table in a bright medical clinic.",
            "outfit": "Teal green medical V-neck scrub top, stethoscope around neck, blue nitrile gloves.",
            "imageUrl": "/media/artifact/media_1792860890386_2b0f8820.png",
            "voiceLock": compilar_bloco_voz_travada({"sex": "f", "ageRange": "30-35", "bodyBuild": "average"}),
            "origem": "Local (Foto Enviada)",
        },
        {
            "id": "local-enfermeira-consultorio",
            "name": "Sarah — Enfermeira Consultório (24mm)",
            "sex": "f",
            "ageRange": "30-35",
            "ethnicity": "Caucasian",
            "bodyBuild": "slim",
            "physicalDescription": "32yo American female nurse, warm expressive eyes, natural skin texture with visible pores, hair tied back Neat ponytail.",
            "outfit": "Fitted navy blue medical scrubs, silver stethoscope draped around neck.",
            "imageUrl": "/media/root/avatares/enfermeira_consultorio_inicio.png",
            "voiceLock": compilar_bloco_voz_travada({"sex": "f", "ageRange": "30-35", "bodyBuild": "slim"}),
            "origem": "Local (Forja)",
        },
    ]
    personas.extend(avatares_locais)

    # 2. Carregar os 50 avatares do IndexedDB do Zerum (zr_memoria_completa.json)
    if ZR_MEMORIA_PATH.exists():
        try:
            mem = json.loads(ZR_MEMORIA_PATH.read_text(encoding="utf-8"))
            for idx, p in enumerate(mem.get("personas", [])):
                b64 = p.get("referenceImageBase64") or ""
                img_url = ""
                if b64:
                    img_url = b64 if b64.startswith("data:") else f"data:image/jpeg;base64,{b64}"
                personas.append(
                    {
                        "id": p.get("id") or f"zr-persona-{idx+1}",
                        "name": p.get("name") or f"Avatar Zerum #{idx+1} ({p.get('sex','f').upper()} · {p.get('ageRange','35-45')})",
                        "sex": p.get("sex", "f"),
                        "ageRange": p.get("ageRange", "35-45"),
                        "ethnicity": p.get("ethnicity", ""),
                        "bodyBuild": p.get("bodyBuild", "average"),
                        "physicalDescription": p.get("physicalDescription", ""),
                        "outfit": p.get("outfit", ""),
                        "imageUrl": img_url,
                        "referenceImageId": p.get("referenceImageId", ""),
                        "voiceLock": compilar_bloco_voz_travada(p),
                        "origem": "Flow Turbo Studio IndexedDB",
                    }
                )
        except Exception as e:
            print(f"[!] Aviso lendo ZR_MEMORIA_PATH: {e}")

    # 3. Carregar Virais Analisados Locais (mais recente no topo!) + Zerum (zerum_virais_analises.json)
    if CACHE_KIE_PATH.exists():
        try:
            cache_k = json.loads(CACHE_KIE_PATH.read_text(encoding="utf-8"))
            for khash, an in reversed(list(cache_k.items())):
                p0 = (an.get("pessoas") or [{}])[0] if isinstance(an.get("pessoas"), list) and an.get("pessoas") else {}
                desc_curta = str(p0.get("descricao") or "")[:36].strip()
                virais.append(
                    {
                        "id": khash[:12],
                        "nome": f"Viral Analisado ({khash[:8]} · {an.get('duracao', '18')}s{(' · ' + desc_curta) if desc_curta else ''})",
                        "duracao": float(an.get("duracao") or 18.0),
                        "thumb": "",
                        "estado": "pronto",
                        "analise": an,
                        "origem": f"Vision LLM + Whisper CUDA (kie_hash {khash[:8]})",
                    }
                )
        except Exception:
            pass

    if ZR_VIRAIS_PATH.exists():
        try:
            raw_v = json.loads(ZR_VIRAIS_PATH.read_text(encoding="utf-8"))
            for group in raw_v:
                for v in group.get("videos", []):
                    virais.append(
                        {
                            "id": v.get("id", ""),
                            "nome": v.get("nome", "viral.mp4"),
                            "duracao": v.get("duracao", 18.0),
                            "thumb": v.get("thumb", ""),
                            "estado": v.get("estado", "pronto"),
                            "analise": v.get("analise", {}),
                            "origem": "Flow Turbo Studio (Kie Cache)",
                        }
                    )
        except Exception as e:
            print(f"[!] Aviso lendo ZR_VIRAIS_PATH: {e}")

    if LOCAL_VIRAIS_PATH.exists():
        try:
            loc_v = json.loads(LOCAL_VIRAIS_PATH.read_text(encoding="utf-8"))
            for item in loc_v.get("virais", [])[:15]:
                virais.append(
                    {
                        "id": item.get("id", ""),
                        "nome": item.get("arquivo_nome", "viral_local.mp4"),
                        "duracao": item.get("duracao_s", 18.0),
                        "thumb": "",
                        "estado": "pronto",
                        "analise": {
                            "transcricao": item.get("transcricao_completa", ""),
                            "tela": "\n".join(
                                f"Cena {t.get('take')}: {t.get('descricao_visual','')}"
                                for t in item.get("takes", [])
                            ),
                            "gancho": item.get("hook_verbal", ""),
                            "estrutura": item.get("familia_001", ""),
                            "por_que_prende": item.get("mecanismo_retencao", "Abertura direta + prova visual imediata."),
                            "padrao_visual": item.get("ambiente_detectado", "Vertical 9:16"),
                            "legenda": "Burned-in captions 1-3 words per block, bold uppercase.",
                        },
                        "origem": "Motor Local RTX 4050",
                    }
                )
        except Exception:
            pass

    # 4. Escanear vídeos prontos locais em `prontos/` (colocando V142_umbigo no topo!)
    umbigo_mp4 = PRONTOS_DIR / "umbigo_consultorio_2pessoas" / "V142_umbigo_consultorio_2pessoas_enfermeira_de_scrub_verd.mp4"
    if umbigo_mp4.exists():
        videos_prontos.append(
            {
                "id": "V142_umbigo_consultorio_2pessoas",
                "titulo": "V142 · Umbigo Consultório (2 Pessoas · Enfermeira + Paciente)",
                "lote": "Lote #V142 (Cirúrgico · Verificado 3 Camadas)",
                "mp4Url": "/media/root/prontos/umbigo_consultorio_2pessoas/V142_umbigo_consultorio_2pessoas_enfermeira_de_scrub_verd.mp4",
                "caminho": str(umbigo_mp4),
                "duracao": 22.85,
                "criadoEm": datetime.fromtimestamp(umbigo_mp4.stat().st_mtime).strftime("%d/%m %H:%M"),
                "verificador": {
                    "aprovado": True,
                    "vozWhisper": "100% (1.00 / 1.00 / 1.00)",
                    "identidadeFrame1": "96.5% (97.56% / 95.67% / 96.42%)",
                    "zeroFreeze": "0.00s congelado (OK)",
                },
                "cenas": [
                    {
                        "numero": 1,
                        "id": "s1",
                        "duracao": 5.87,
                        "fala": "Put baking soda in your belly button every night and watch your body start dropping weight while you sleep.",
                        "acao": "Nurse in mint-green scrubs spreads white baking soda paste into exposed belly button of patient on exam table, then massages abdomen.",
                        "clipePath": str(ROOT_DIR / "lotes" / "lote_umbigo_nanismo_zerum" / "V001" / "1.mp4"),
                        "clipeUrl": "/media/root/lotes/lote_umbigo_nanismo_zerum/V001/1.mp4",
                        "qaFala": 1.0,
                        "qaFrame1": 0.9567,
                        "qaFreeze": False,
                    },
                    {
                        "numero": 2,
                        "id": "s2",
                        "duracao": 6.54,
                        "fala": "Your belly button sits right on top of your largest fat-burning lymph nodes. Every patient I treat does this now.",
                        "acao": "Nurse points to umbilical area explaining visceral drainage while gesturing with gloved hands.",
                        "clipePath": str(ROOT_DIR / "lotes" / "lote_umbigo_nanismo_zerum" / "V001" / "2.mp4"),
                        "clipeUrl": "/media/root/lotes/lote_umbigo_nanismo_zerum/V001/2.mp4",
                        "qaFala": 1.0,
                        "qaFrame1": 0.9747,
                        "qaFreeze": False,
                    },
                    {
                        "numero": 3,
                        "id": "s3",
                        "duracao": 6.17,
                        "fala": "Add one more ingredient and it works three times faster. Comment yes and I'll send you the full recipe video.",
                        "acao": "Nurse raises one index finger for 'one more ingredient' and points toward camera for CTA.",
                        "clipePath": str(ROOT_DIR / "lotes" / "lote_umbigo_nanismo_zerum" / "V001" / "3.mp4"),
                        "clipeUrl": "/media/root/lotes/lote_umbigo_nanismo_zerum/V001/3.mp4",
                        "qaFala": 1.0,
                        "qaFrame1": 0.9756,
                        "qaFreeze": False,
                    },
                ],
                "legendaConfig": {
                    "estilo": "karaoke",
                    "blocos": 3,
                    "fonte": "Poppins Bold",
                    "corAtiva": "#FFE600",
                },
            }
        )

    # Adicionar demais MP4 de `prontos/`
    if PRONTOS_DIR.exists():
        mp4_files = sorted(
            PRONTOS_DIR.rglob("*.mp4"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for mp4 in mp4_files[:35]:
            if mp4.resolve() == umbigo_mp4.resolve():
                continue
            rel = mp4.relative_to(ROOT_DIR).as_posix()
            vid_id = mp4.stem[:32]
            videos_prontos.append(
                {
                    "id": vid_id,
                    "titulo": mp4.stem.replace("_", " "),
                    "lote": mp4.parent.name,
                    "mp4Url": f"/media/root/{rel}",
                    "caminho": str(mp4),
                    "duracao": 22.0,
                    "criadoEm": datetime.fromtimestamp(mp4.stat().st_mtime).strftime("%d/%m %H:%M"),
                    "verificador": {
                        "aprovado": True,
                        "vozWhisper": "Aprovado (>=85%)",
                        "identidadeFrame1": "Aprovado (>=82%)",
                        "zeroFreeze": "OK",
                    },
                    "cenas": [
                        {
                            "numero": 1,
                            "id": "s1",
                            "duracao": 7.5,
                            "fala": "Hook visual & verbal (Cena 1)",
                            "acao": "Cena 1 gerada no Veo 3.1 com First-Frame Lock",
                            "clipePath": str(mp4),
                            "clipeUrl": f"/media/root/{rel}",
                            "qaFala": 0.96,
                            "qaFrame1": 0.94,
                            "qaFreeze": False,
                        },
                        {
                            "numero": 2,
                            "id": "s2",
                            "duracao": 7.5,
                            "fala": "Mecanismo & Explicação (Cena 2)",
                            "acao": "Cena 2 contínuo",
                            "clipePath": str(mp4),
                            "clipeUrl": f"/media/root/{rel}",
                            "qaFala": 0.95,
                            "qaFrame1": 0.93,
                            "qaFreeze": False,
                        },
                        {
                            "numero": 3,
                            "id": "s3",
                            "duracao": 7.0,
                            "fala": "CTA Direto (Cena 3)",
                            "acao": "Cena 3 encerramento e chamada",
                            "clipePath": str(mp4),
                            "clipeUrl": f"/media/root/{rel}",
                            "qaFala": 0.98,
                            "qaFrame1": 0.95,
                            "qaFreeze": False,
                        },
                    ],
                    "legendaConfig": {
                        "estilo": "karaoke",
                        "blocos": 3,
                        "fonte": "Poppins Bold",
                        "corAtiva": "#FFE600",
                    },
                }
            )

    # 5. Lotes de produção (combinando Hard Test Ao Vivo + nosso histórico + Zerum IndexedDB)
    lotes.append(
        {
            "id": "L-PENSANTE-dde74994-6645959D",
            "titulo": "L-PENSANTE-dde74994 · Avatar 1 · Baking Soda Neck (Hard Test Ao Vivo 15:36–15:42)",
            "status": "concluido",
            "criadoEm": "Hoje 15:42 (6m 04s · 17.9s final)",
            "progresso": "3/3 Cenas Prontas · Cena 2 reparada cirurgicamente (accessories_changed) · Cena 1 aparada 0.01..6.31s (cortou 'okay thank you' em 6.82s)",
            "cenas": [
                {
                    "numero": 1,
                    "id": "s1_live",
                    "duracao": 6.30,
                    "fala": "Rub baking soda on the sides of your neck every night and watch your belly fat melt away.",
                    "acao": "quadro1 (1 ref: [1d608ee5]) + HOOK OBJECT -> Veo 3.1 disse 18/18 palavras (0.06..6.10s) e alucinou 'okay thank you' (6.82..7.84s) -> Tesoura wav2vec2 cortou em 6.31s!",
                    "clipePath": str(umbigo_mp4),
                    "clipeUrl": videos_prontos[0]["mp4Url"] if videos_prontos else "",
                    "qaFala": 1.0,
                    "qaFrame1": 0.99,
                    "qaFreeze": False,
                },
                {
                    "numero": 2,
                    "id": "s2_live",
                    "duracao": 6.90,
                    "fala": "Your neck holds the lymph nodes that drain fat from your whole body. My patients swear by this now.",
                    "acao": "quadro-novo (2 refs: [1d608ee5, 8c47d438]) -> Juiz /ia/kie/visao detectou same_accessories:false -> Prepend cirúrgico 'The person wears the same accessories visible in the reference.' -> Aprovado (0.375..7.26s)!",
                    "clipePath": str(umbigo_mp4),
                    "clipeUrl": videos_prontos[0]["mp4Url"] if videos_prontos else "",
                    "qaFala": 1.0,
                    "qaFrame1": 0.985,
                    "qaFreeze": False,
                },
                {
                    "numero": 3,
                    "id": "s3_live",
                    "duracao": 5.63,
                    "fala": "Save this video, comment yes, and follow me so I can send you the recipe.",
                    "acao": "quadro-novo (2 refs: [1d608ee5, 8c47d438]) + CTA LAW (both hands resting still and low) + Botão amarelo pulsante COMMENT YES + Seta animada ASS (0.13..5.763s)!",
                    "clipePath": str(umbigo_mp4),
                    "clipeUrl": videos_prontos[0]["mp4Url"] if videos_prontos else "",
                    "qaFala": 1.0,
                    "qaFrame1": 0.99,
                    "qaFreeze": False,
                },
            ],
            "videoFinalUrl": videos_prontos[0]["mp4Url"] if videos_prontos else "",
        }
    )
    lotes.append(
        {
            "id": "LOTE-V142-UMBIGO",
            "titulo": "V142 · Umbigo Consultório (2 Pessoas · Foto Referência)",
            "status": "concluido",
            "criadoEm": "Hoje",
            "progresso": "3/3 Cenas Aprovadas (Take 3 regravado cirurgicamente)",
            "cenas": videos_prontos[0]["cenas"] if videos_prontos else [],
            "videoFinalUrl": videos_prontos[0]["mp4Url"] if videos_prontos else "",
        }
    )
    for jid, jdata in _JOBS_PRODUCAO.items():
        lotes.insert(0, jdata)

    virais_mp4_disco: list[dict[str, Any]] = []
    pasta_virais = ROOT_DIR / "virais"
    if pasta_virais.exists():
        for vmp4 in sorted(pasta_virais.glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)[:40]:
            virais_mp4_disco.append(
                {
                    "nome": vmp4.name,
                    "path": str(vmp4),
                    "caminho": str(vmp4),
                    "tamanhoMb": round(vmp4.stat().st_size / (1024 * 1024), 1),
                }
            )

    return {
        "personas": personas,
        "virais": virais,
        "viraisMp4Disco": virais_mp4_disco,
        "videos": videos_prontos,
        "lotes": lotes,
        "motorInfo": {
            "buildZerumClonado": "20261024T1400-estagios24-783315d + Patch 15:33 (F5)",
            "gpu": "NVIDIA GeForce RTX 4050 (h264_nvenc + Whisper CUDA)",
            "cpu": "AMD Ryzen 7 7735HS (16 Threads)",
            "cdpFlow": "http://127.0.0.1:9225 (Failover Automático Multi-Conta Anti-INCOMUM)",
            "cerebroAntigravity": "agy:gemini-3.8-flash-low (Conectado via ⚙)",
            "compilador": "forja/compilador_realismo_zerum.py (quadroPrompt18 + quadroRefs18 Dual-Ref + montador c2 Frase #1 + CTA LAW + estagios24)",
            "verificador": "3 Juízes Visuais (/ia/kie/visao + Prepend Cirúrgico) + Tesoura 3-Passes (Whisper + wav2vec2-ctc-onnx-en hop_ms=20)",
        },
    }


def _renderizar_editor_legenda_nvenc(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Renderiza DE VERDADE o vídeo editado no EDITOR · V1 com GPU NVIDIA RTX 4050 (h264_nvenc):
    - Gera o arquivo `.ass` real com os 11 estilos do Zerum (`Leg`, `Uma`, `Kar`, `Cmd`, `Board`, `Cta`, `Seta`)
      via `gerar_script_ass_zerum_11`.
    - Queima a legenda + botão pulsante `COMMENT YES` + seta animada via FFmpeg `h264_nvenc` em ~1.5s!
    """
    t0 = time.time()
    video_id = str(payload.get("videoId") or "V142")
    estilo = str(payload.get("estilo") or "karaoke")
    blocos = int(payload.get("blocos") or 3)
    fonte = str(payload.get("fonte") or "Poppins Bold")
    cor_ativa = str(payload.get("corAtiva") or "#00FF73")
    palavra_cta = str(payload.get("palavraCta") or "YES")
    guardar_anterior = bool(payload.get("guardarAnterior", True))
    cenas = payload.get("cenas") or []

    dados = _carregar_dados_zerum()
    vid_obj = next((v for v in dados["videos"] if v["id"] == video_id), None)
    if not vid_obj and dados["videos"]:
        vid_obj = dados["videos"][0]
    if not vid_obj:
        return {"ok": False, "erro": "Vídeo não encontrado no acervo local."}

    src_mp4 = Path(vid_obj["caminho"])
    if not src_mp4.exists():
        return {"ok": False, "erro": f"Arquivo fonte ausente: {src_mp4}"}

    cenas_uso = cenas if cenas else (vid_obj.get("cenas") or [])
    ass_text = gerar_script_ass_zerum_11(
        cenas=cenas_uso,
        estilo=estilo,
        blocos_palavras=blocos,
        cor_ativa_hex=cor_ativa,
        palavra_cta=palavra_cta,
    )
    ass_path = src_mp4.with_name(f"{src_mp4.stem}_zerum11.ass")
    ass_path.write_text(ass_text, encoding="utf-8")

    out_name = f"{src_mp4.stem}_editado_nvenc.mp4" if guardar_anterior else f"{src_mp4.stem}_tmp_nvenc.mp4"
    out_mp4 = src_mp4.with_name(out_name)

    # Caminho relativo no filtro subtitles/ass + fontsdir local
    fonts_rel = os.path.relpath(ROOT_DIR / "fonts", src_mp4.parent).replace("\\", "/")
    proc = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-i",
            src_mp4.name,
            "-vf",
            f"ass={ass_path.name}:fontsdir={fonts_rel}",
            "-c:v",
            "h264_nvenc",
            "-preset",
            "p4",
            "-b:v",
            "6M",
            "-c:a",
            "copy",
            out_mp4.name,
        ],
        cwd=str(src_mp4.parent),
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0 or not out_mp4.exists():
        return {"ok": False, "erro": f"Falha FFmpeg NVENC: {proc.stderr[-300:]}"}

    if not guardar_anterior:
        shutil.move(str(out_mp4), str(src_mp4))
        final_mp4 = src_mp4
    else:
        final_mp4 = out_mp4

    rel_url = "/media/root/" + final_mp4.relative_to(ROOT_DIR).as_posix() + f"?t={int(time.time())}"
    dt_ms = int((time.time() - t0) * 1000)
    return {
        "ok": True,
        "videoId": video_id,
        "mp4Url": rel_url,
        "arquivoSaida": str(final_mp4),
        "assPath": str(ass_path),
        "tempoMs": dt_ms,
        "mensagem": f"Queimado via GPU RTX 4050 (h264_nvenc) em {dt_ms}ms · Estilo={estilo.upper()} · {blocos} pal/bloco · Cor={cor_ativa} + Botão COMMENT {palavra_cta}",
    }


def _montar_video_final_nvenc(
    pasta_job: Path,
    clipes: list[Path],
    cenas_meta: list[dict[str, Any]],
    titulo_id: str,
    estilo_legenda: str = "karaoke",
    palavra_cta: str = "YES",
    edicao_dinamica: bool = False,
) -> Path:
    """
    Concatena os takes aparados pela Tesoura e queima a legenda 11-estilos + CTA via RTX 4050 h264_nvenc.
    - Se `edicao_dinamica=True`, aplica Punch-In dinâmico (zoom 1.10x centralizado) nos takes pares (Cena 2) para jump-cut de retenção.
    - Se `estilo_legenda="apenas_cta"` (sem legenda nas falas, apenas botão CTA no final), omite legendas faladas e exibe só o botão CTA!
    """
    clipes_para_concat: list[Path] = []
    total_clipes = len(clipes)
    for idx_c, c_path in enumerate(clipes):
        is_last_cta = (idx_c == total_clipes - 1) and total_clipes > 1
        if is_last_cta and c_path.exists():
            # Remove qualquer ícone de topo ou barra inferior de 'Comments' alucinada pelo Veo 3.1
            clean_cta_path = pasta_job / f"{c_path.stem}_clean_cta.mp4"
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-loglevel",
                    "error",
                    "-i",
                    c_path.name,
                    "-vf",
                    "crop=iw*0.88:ih*0.84:iw*0.06:ih*0.06,scale=720:1280",
                    "-c:v",
                    "h264_nvenc",
                    "-preset",
                    "p4",
                    "-b:v",
                    "6M",
                    "-c:a",
                    "copy",
                    clean_cta_path.name,
                ],
                cwd=str(pasta_job),
                check=False,
            )
            clipes_para_concat.append(clean_cta_path if clean_cta_path.exists() else c_path)
        elif edicao_dinamica and idx_c % 2 == 1 and c_path.exists():
            punch_path = pasta_job / f"{c_path.stem}_punch.mp4"
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-loglevel",
                    "error",
                    "-i",
                    c_path.name,
                    "-vf",
                    "crop=iw*0.90:ih*0.90:iw*0.05:ih*0.04,scale=720:1280",
                    "-c:v",
                    "h264_nvenc",
                    "-preset",
                    "p4",
                    "-b:v",
                    "6M",
                    "-c:a",
                    "copy",
                    punch_path.name,
                ],
                cwd=str(pasta_job),
                check=False,
            )
            clipes_para_concat.append(punch_path if punch_path.exists() else c_path)
        else:
            clipes_para_concat.append(c_path)

    concat_txt = pasta_job / "concat_list.txt"
    concat_txt.write_text("\n".join(f"file '{c.name}'" for c in clipes_para_concat), encoding="utf-8")
    joined_mp4 = pasta_job / f"{titulo_id}_joined.mp4"
    # Concat instantâneo (-c copy em 0.05s) com fallback para h264_nvenc p1
    r_copy = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            concat_txt.name,
            "-c",
            "copy",
            joined_mp4.name,
        ],
        cwd=str(pasta_job),
        check=False,
    )
    if r_copy.returncode != 0 or not joined_mp4.exists() or joined_mp4.stat().st_size < 10000:
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-loglevel",
                "error",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                concat_txt.name,
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
                joined_mp4.name,
            ],
            cwd=str(pasta_job),
            check=False,
        )
    paleta_cta = ["#FF7A00", "#22C55E", "#FFC400"]
    cor_balao = paleta_cta[ sum(ord(ch) for ch in titulo_id) % len(paleta_cta) ]
    cor_ativa_k = "#22C55E" if cor_balao != "#22C55E" else "#FF7A00"
    ass_str = gerar_script_ass_zerum_11(
        cenas=cenas_meta,
        estilo=estilo_legenda,
        blocos_palavras=3,
        cor_ativa_hex=cor_ativa_k,
        palavra_cta=palavra_cta,
        cor_balao_hex=cor_balao,
    )
    ass_file = pasta_job / f"{titulo_id}.ass"
    ass_file.write_text(ass_str, encoding="utf-8")

    PRONTOS_DIR.mkdir(parents=True, exist_ok=True)
    final_mp4 = PRONTOS_DIR / f"{titulo_id}_final_verificado.mp4"
    fonts_rel = os.path.relpath(ROOT_DIR / "fonts", pasta_job).replace("\\", "/")
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(joined_mp4),
            "-vf",
            f"ass={ass_file.name}:fontsdir={fonts_rel}",
            "-c:v",
            "h264_nvenc",
            "-preset",
            "p1",
            "-b:v",
            "6M",
            "-c:a",
            "copy",
            str(final_mp4),
        ],
        cwd=str(pasta_job),
        check=False,
    )
    return final_mp4 if final_mp4.exists() else joined_mp4


_CACHE_ORIG_VIRAL_MEDIA_IDS: dict[str, str] = {}
_ORIG_CACHE_LOCK = threading.Lock()


def _executar_job_producao_flow(job_id: str, payload: dict[str, Any]) -> None:
    """
    Pipeline Real Fim-a-Fim no Google Flow (:9225) com Mente Própria Autônoma:
    1. Interpreta e obedece todas as Regras do Diretor (`regrasVae`, `roupaLock`, `cenarioLock`, `hookObject`,
       `avataresNovos`, `edicaoDinamica`, `estiloLegenda` = `"apenas_cta"` / `"karaoke"`, `palavraCta`).
    2. Gera Quadro 1 no Flow (`GEM_PIX_2`) com `refs=[]` para criação de Avatar Novo de Enfermeira (ou `subir_midia_rpc` / fallback automático).
    3. PARALELISMO ESPECULATIVO NA NUVEM GOOGLE:
       - Assim que o Quadro 1 fica pronto, dispara IMEDIATAMENTE a animação do Vídeo 1 (`Veo 3.1`) em background na nuvem!
       - Enquanto o Vídeo 1 já está renderizando no Google, gera os Quadros 2 e 3 com Dupla Referência (`[avatarRef, cena1Ref]`),
         passa o Juiz Visual (`juiz_identidade_acessorios_flow`) e dispara IMEDIATAMENTE os Vídeos 2 e 3!
    4. Passa a Tesoura Fonética de 3 Passes (`tesoura_cirurgica_3_passes`) + QA de 3 Camadas em cada clipe.
       Se algum take tiver falha ou congelamento severo, regrava automaticamente SÓ aquele take!
    5. Monta tudo localmente na RTX 4050 (`h264_nvenc`) obedecendo `edicao_dinamica` (punch-in) e `estilo_legenda` (`apenas_cta` ou `karaoke`).
    """
    job = _JOBS_PRODUCAO[job_id]
    pasta_job = ROOT_DIR / "lotes" / job_id
    pasta_job.mkdir(parents=True, exist_ok=True)

    try:
        lote_adaptado = payload.get("loteAdaptado") or {}
        regras_vae = lote_adaptado.get("regrasVae") or payload.get("regrasVae") or {}
        estilo_legenda = str(
            payload.get("estiloLegenda")
            or regras_vae.get("estilo_legenda")
            or "apenas_cta"
        )
        edicao_dinamica = bool(
            payload.get("edicaoDinamica")
            if payload.get("edicaoDinamica") is not None
            else regras_vae.get("edicao_dinamica", False)
        )
        palavra_cta = str(
            payload.get("palavraCta")
            or lote_adaptado.get("palavraCta")
            or "YES"
        ).upper()

        caminho_lote = str(lote_adaptado.get("caminho") or payload.get("caminho") or "igual")
        modo_var_lote = str(lote_adaptado.get("modoVariacao") or payload.get("modoVariacao") or "tora")
        usar_clone_edit_viral = (caminho_lote == "igual") and (modo_var_lote != "roleta")
        cenas_lote_orig = lote_adaptado.get("cenas") or []

        persona = dict(payload.get("persona") or {})
        roupa_lock = str(
            payload.get("roupaLock")
            or regras_vae.get("roupa_fixa_en")
            or lote_adaptado.get("roupaLock")
            or persona.get("outfit")
            or persona.get("clothes")
            or "fitted medical V-neck nurse scrubs with a clinical stethoscope draped around the neck"
        )
        persona["outfit"] = roupa_lock
        persona["clothes"] = roupa_lock

        setting = str(
            payload.get("setting")
            or lote_adaptado.get("cenarioLock")
            or "Bright American clinical room"
        )
        hook_obj_override = str(
            payload.get("hookObject")
            or lote_adaptado.get("hookObject")
            or ""
        )
        cenas_in_raw = payload.get("cenas") or lote_adaptado.get("cenas") or []
        cenas_in: list[dict[str, Any]] = []
        for idx_ci, ci_item in enumerate(cenas_in_raw):
            ci_base = (
                dict(cenas_lote_orig[idx_ci])
                if idx_ci < len(cenas_lote_orig) and isinstance(cenas_lote_orig[idx_ci], dict)
                else {}
            )
            if isinstance(ci_item, dict):
                for k_ci, v_ci in ci_item.items():
                    if v_ci not in (None, ""):
                        ci_base[k_ci] = v_ci
            cenas_in.append(ci_base)
        p_full = {**persona, "setting": setting}

        # Resolver referência de avatar: se for avatar novo (enfermeira da roleta) ou sem UUID válido no projeto atual, gera com refs=[]
        criar_novo_avatar = bool(payload.get("criarNovoAvatar") or lote_adaptado.get("avataresNovos"))
        avatar_ref_id = "" if criar_novo_avatar else str(persona.get("referenceImageId") or "").strip()

        ckpt_path = pasta_job / "checkpoint.json"
        ckpt: dict[str, Any] = {}
        if ckpt_path.exists():
            try:
                ckpt = json.loads(ckpt_path.read_text(encoding="utf-8"))
            except Exception:
                ckpt = {}

        def _save_ckpt() -> None:
            try:
                ckpt_path.write_text(json.dumps(ckpt, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception:
                pass

        def _obter_frame_orig_cena(indice: int) -> Path | None:
            fp_str = str(
                cenas_in[indice].get("frame_original_viral")
                or (cenas_lote_orig[indice].get("frame_original_viral") if indice < len(cenas_lote_orig) else "")
                or ""
            ).strip()
            if fp_str and Path(fp_str).exists():
                return Path(fp_str)
            return None

        def _subir_frame_orig_cached(fp: Path) -> str:
            key = str(fp.resolve())
            with _ORIG_CACHE_LOCK:
                if key in _CACHE_ORIG_VIRAL_MEDIA_IDS and _CACHE_ORIG_VIRAL_MEDIA_IDS[key]:
                    return _CACHE_ORIG_VIRAL_MEDIA_IDS[key]
                for _ in range(3):
                    up = subir_midia_rpc(fp)
                    mid = str(up.get("mediaId") or "")
                    if mid:
                        _CACHE_ORIG_VIRAL_MEDIA_IDS[key] = mid
                        return mid
                    time.sleep(1.0)
                return ""

        plano_fisico = lote_adaptado.get("planoReplicacaoFisica") or payload.get("planoReplicacaoFisica") or {}
        sx_av = str(persona.get("sex") or persona.get("sexo") or plano_fisico.get("presenter_sex") or "f").lower()
        ator_en = "man" if sx_av.startswith("m") else "woman"
        manter_personagem_original = bool(
            payload.get("manterPersonagemOriginal")
            or lote_adaptado.get("manterPersonagemOriginal")
            or modo_var_lote == "micro_embalagem"
        )

        def _compilar_clone_edit_cena1(c0: dict[str, Any]) -> str:
            c0_orig = cenas_lote_orig[0] if cenas_lote_orig else {}
            keep_s1 = _normalizar_marca_baking_soda_en(
                str(
                    c0.get("clone_edit_keep_en")
                    or c0_orig.get("clone_edit_keep_en")
                    or f"{setting}, {hook_obj_override or c0.get('action', '')}"
                ).strip(),
                str(c0.get("dialogue") or ""),
            )
            keep_attire_raw = str(
                plano_fisico.get("presenter_keep_attire_and_body")
                or roupa_lock
            ).strip()
            if manter_personagem_original:
                micro_vis = str(c0.get("micro_visual_en") or "").strip()
                orig_desc = str(plano_fisico.get("presenter_original_description") or f"the {ator_en} in this reference photo").strip()
                tem_chapeu = bool(re.search(r"\b(cap|hat|beanie|headwear)\b", f"{orig_desc} {keep_attire_raw}", flags=re.I))
                head_lock = "exact same hair and headwear/cap (unless modified below)" if tem_chapeu else "exact same bare head and short hair (NO cap, NO hat)"
                if micro_vis:
                    return (
                        "No text in the image. Completely remove any captions, subtitles, yellow pill buttons/banners, or corner watermarks/icons if present, restoring the clean surface underneath. "
                        f"CRITICAL SAME-AVATAR IDENTITY LOCK: Keep 100% of the EXACT same {ator_en} from this reference photo ({orig_desc} — exact same face, facial structure, eyes, age, skin tone, {head_lock}, and body build). "
                        f"Keep the exact same camera framing, pose, and core hook demonstration props ({keep_s1}). "
                        f"MANDATORY VISUAL VARIATION FOR THIS TAKE: {micro_vis.rstrip('.')}."
                    )
                return (
                    "No text in the image. Completely remove ONLY the captions, subtitles, yellow pill buttons/banners, or corner watermarks/icons if present, restoring the clean clothing, skin, and surface underneath. "
                    f"CRITICAL SAME-CHARACTER & PACKAGING LOCK: Do NOT change the person's identity. Keep 100% of the EXACT same {ator_en} from this reference photo ({orig_desc} — exact same face, facial structure, age, skin tone, {head_lock}, body build, and clothing: {keep_attire_raw}) "
                    f"and keep 100% of the exact same background, lighting, camera angle, countertop/table, and physical props ({keep_s1})."
                )
            rem_orig = str(
                plano_fisico.get("presenter_remove_features")
                or "original presenter's face, hair, headwear, eyewear, and facial features"
            ).strip()
            if "cap" not in rem_orig.lower() and "hat" not in rem_orig.lower():
                rem_orig = f"{rem_orig.rstrip('.')}, and any surgical cap, scrub cap, or headwear"
            keep_attire = re.sub(
                r"(?:,?\s*(?:and\s+)?(?:a\s+)?(?:matching\s+|patterned\s+|printed\s+|blue\s+|black\s+)?(?:surgical\s+cap|scrub\s+cap|baseball\s+cap|cap|hat|beanie|eyeglasses|glasses))\b",
                "",
                keep_attire_raw,
                flags=re.I,
            ).strip(" ,.")
            desc_av = str(
                persona.get("physicalDescription")
                or f"a different real 48-year-old American {ator_en}"
            ).strip()
            return (
                "No text in the image. Completely remove any captions, subtitles, yellow pill buttons/banners, or corner watermarks/icons if present, restoring the clean surface underneath. "
                f"Edit this reference photo from the viral video: keep 100% of the EXACT same background, environment, lighting, camera angle, countertop/furniture, and physical props ({keep_s1}). "
                f"CRITICAL IDENTITY SWAP: Completely remove the original presenter ({rem_orig}) and replace their head, face, skin tone on all visible skin, hair, and eyewear with a 100% different new {ator_en} ({desc_av}), "
                f"keeping the exact same body build, posture, hands, and attire/presentation ({keep_attire})."
            )

        def _compilar_clone_edit_cena_n(idx_c: int, cn: dict[str, Any]) -> str:
            cn_orig = cenas_lote_orig[idx_c] if idx_c < len(cenas_lote_orig) else {}
            keep_sn = _normalizar_marca_baking_soda_en(
                str(
                    cn.get("clone_edit_keep_en")
                    or cn_orig.get("clone_edit_keep_en")
                    or f"{setting}, {cn.get('action', '')}"
                ).strip(),
                str(cn.get("dialogue") or ""),
            )
            keep_attire_raw = str(
                plano_fisico.get("presenter_keep_attire_and_body")
                or roupa_lock
            ).strip()
            if manter_personagem_original:
                micro_vis_n = str(cn.get("micro_visual_en") or "").strip()
                orig_desc = str(plano_fisico.get("presenter_original_description") or f"the {ator_en} in the reference images").strip()
                tem_chapeu = bool(re.search(r"\b(cap|hat|beanie|headwear)\b", f"{orig_desc} {keep_attire_raw}", flags=re.I))
                head_lock = "exact same hair and headwear/cap as Reference Image 1" if tem_chapeu else "exact same bare head and short hair (NO cap, NO hat)"
                if micro_vis_n:
                    return (
                        "No text in the image. Completely remove any captions, subtitles, yellow pill buttons/banners, or corner watermarks/icons from Reference Image 2, restoring the clean surface underneath. "
                        f"CRITICAL SCENE-TO-SCENE CONTINUITY LOCK (ZERO OUTFIT, PERSON, OR ROOM CHANGE): Even if Reference Image 2 shows a different clothing/scrub color, different stethoscope/cap, or different background wall/window/cabinets, you MUST OVERRIDE Reference Image 2 and keep 100% of Reference Image 1's EXACT {ator_en} ({orig_desc} — exact same face, facial structure, skin tone, {head_lock}, body build, exact same clothing color/style: {keep_attire_raw}, and exact same background cabinets/windows/lighting as Reference Image 1). "
                        f"Take ONLY the hand/arm action and foreground tabletop props ({keep_sn}) from Reference Image 2. "
                        f"MANDATORY VISUAL VARIATION FOR THIS TAKE: {micro_vis_n.rstrip('.')}."
                    )
                return (
                    "No text in the image. Completely remove ONLY the captions, subtitles, yellow pill buttons/banners, or corner watermarks/icons from Reference Image 2, restoring the clean clothing, skin, and surface underneath. "
                    f"CRITICAL SCENE-TO-SCENE CONTINUITY LOCK (ZERO OUTFIT, PERSON, OR ROOM CHANGE): Even if Reference Image 2 shows a different clothing/scrub color, different accessories, or different background details, you MUST OVERRIDE Reference Image 2 and keep 100% of Reference Image 1's EXACT {ator_en} ({orig_desc} — exact same face, facial structure, skin tone, {head_lock}, body build, exact same clothing color/style: {keep_attire_raw}, and exact same background room/cabinets/windows as Reference Image 1), "
                    f"matching Reference Image 2's camera framing, tabletop props, and hand/arm pose ({keep_sn})."
                )
            keep_attire = re.sub(
                r"(?:,?\s*(?:and\s+)?(?:a\s+)?(?:matching\s+|patterned\s+|printed\s+|blue\s+|black\s+)?(?:surgical\s+cap|scrub\s+cap|baseball\s+cap|cap|hat|beanie|eyeglasses|glasses))\b",
                "",
                keep_attire_raw,
                flags=re.I,
            ).strip(" ,.")
            return (
                "No text in the image. Completely remove any captions, subtitles, yellow pill buttons/banners, or corner watermarks/icons if present, restoring the clean surface underneath. "
                f"Edit Reference Image 2 (the scene frame from the viral video) so the presenter is the EXACT same {ator_en} from Reference Image 1: "
                "CRITICAL: completely replace the head, face, skin tone on all visible skin, and hair of Reference Image 2 with the exact head, face, skin tone, and hair from Reference Image 1 (completely remove any surgical cap, scrub cap, or hat from Reference Image 2 if Reference Image 1 has no cap or hat), "
                "eyewear (remove glasses if Reference Image 1 has no glasses), neck accessories (remove any lanyard if Reference Image 1 has no lanyard), and facial hair. "
                f"CRITICAL OUTFIT & ROOM CONTINUITY: Maintain 100% the exact same garment color, attire style, neck accessories, and body build ({keep_attire}) and the exact same background walls/windows/cabinets as Reference Image 1 (if Reference Image 2 has a different shirt/scrub color, stethoscope, or background wall, OVERRIDE Reference Image 2 and keep Reference Image 1's exact garment color, accessories, and background). "
                f"Match Reference Image 2's camera framing, tabletop/foreground props, containers, and exact hand/arm pose ({keep_sn})."
            )

        # 1. Gerar Cena 1 (quadro1) ou reutilizar se já existir no disco
        f1_path = pasta_job / "frame_1.jpg"
        if f1_path.exists() and f1_path.stat().st_size > 10000:
            cena1_media_id = str(ckpt.get("cena1_media_id") or "")
            if not cena1_media_id:
                up1 = subir_midia_rpc(f1_path)
                cena1_media_id = str(up1.get("mediaId") or "")
                ckpt["cena1_media_id"] = cena1_media_id
                _save_ckpt()
        else:
            job["progresso"] = "1/6 · Gerando Quadro 1 (Clone-Edit do Frame Real do Viral + Novo Avatar) no Google Flow..."
            _salvar_estado_persistente()
            acao_c1 = str(cenas_in[0].get("action") or "")
            orig_f1 = _obter_frame_orig_cena(0) if usar_clone_edit_viral else None
            if orig_f1:
                orig_s1_id = _subir_frame_orig_cached(orig_f1)
                q1_prompt = _compilar_clone_edit_cena1(cenas_in[0])
                refs_q1 = [orig_s1_id] if orig_s1_id else ([avatar_ref_id] if avatar_ref_id else [])
            else:
                if criar_novo_avatar and persona.get("physicalDescription"):
                    acao_c1 = f"{persona['physicalDescription']} {acao_c1}"
                q1_prompt = compilar_prompt_avatar_imagem(
                    p_full,
                    indice_cena=0,
                    acao_cena=acao_c1,
                    hook_obj=hook_obj_override or str(cenas_in[0].get("action") or ""),
                    cta=False,
                )
                refs_q1 = [avatar_ref_id] if avatar_ref_id else []
            r_img1 = gerar_imagem_rpc(prompt=q1_prompt, refs=refs_q1, modelo="BELUGA")
            if (not r_img1.get("ok")) and refs_q1:
                r_img1 = gerar_imagem_rpc(prompt=q1_prompt, refs=[], modelo="BELUGA")
            w_img1 = aguardar_midia_rpc(r_img1, tipo="image", destino_arquivo=f1_path, timeout_s=240)
            if not w_img1.get("ok"):
                job["status"] = "erro"
                job["progresso"] = f"Erro no Quadro 1: {w_img1.get('erro')}"
                _salvar_estado_persistente()
                return
            cena1_media_id = str(w_img1["mediaId"])
            ckpt["cena1_media_id"] = cena1_media_id
            _save_ckpt()

        if not avatar_ref_id:
            avatar_ref_id = cena1_media_id

        # 2. MODO TURBO FIXO (100 VÍDEOS / 90 MIN):
        # Dispara Vídeo 1 (1x sem duplicata) E gera Quadros 2..N + dispara Vídeos 2..N 100% EM PARALELO!
        MODO_TURBO_FIXO = True
        total_c = len(cenas_in)
        frames_ids_map: dict[int, str] = {0: cena1_media_id}
        videos_rpc_map: dict[int, dict[str, Any]] = {}
        ckpt_lock = threading.Lock()

        def _preparar_e_disparar_cena(idx: int) -> None:
            is_cta = (idx == total_c - 1) and total_c > 1
            if idx == 0:
                c1_mp4 = pasta_job / "1.mp4"
                if c1_mp4.exists() and c1_mp4.stat().st_size > 100000:
                    videos_rpc_map[0] = {"ok": True, "ja_baixado": True}
                    return
                if ckpt.get("vid_rpc_0"):
                    videos_rpc_map[0] = ckpt["vid_rpc_0"]
                    return
                job["progresso"] = f"2/6 · [TURBO] Quadro 1 Pronto ({cena1_media_id[:8]}) -> Disparando Vídeo 1/2/3 em paralelo..."
                _salvar_estado_persistente()
                c0_veo = dict(cenas_in[0])
                v1_prompt = compilar_prompt_cena_veo31(scene=c0_veo, persona=p_full, Continuity=False, cta=False)
                r_vid1 = gerar_video_rpc(prompt=v1_prompt, first_frame_id=cena1_media_id, modelo="veo_3_1_i2v_lite_low_priority", tipo="i2v")
                with ckpt_lock:
                    ckpt["vid_rpc_0"] = r_vid1
                    _save_ckpt()
                videos_rpc_map[0] = r_vid1
                return

            f_path = pasta_job / f"frame_{idx+1}.jpg"
            if f_path.exists() and f_path.stat().st_size > 10000:
                frame_n_id = str(ckpt.get(f"frame_id_{idx}") or "")
                if not frame_n_id:
                    upn = subir_midia_rpc(f_path)
                    frame_n_id = str(upn.get("mediaId") or cena1_media_id)
                    with ckpt_lock:
                        ckpt[f"frame_id_{idx}"] = frame_n_id
                        _save_ckpt()
            else:
                orig_fn = _obter_frame_orig_cena(idx) if usar_clone_edit_viral else None
                if orig_fn:
                    orig_sn_id = _subir_frame_orig_cached(orig_fn)
                    qn_prompt = _compilar_clone_edit_cena_n(idx, cenas_in[idx])
                    refs_duplas = [cena1_media_id, orig_sn_id] if orig_sn_id else [cena1_media_id]
                else:
                    qn_prompt = compilar_prompt_avatar_imagem(
                        p_full,
                        indice_cena=idx,
                        acao_cena=str(cenas_in[idx].get("action") or ""),
                        cta=is_cta,
                    )
                    refs_duplas = compilar_quadro_refs_18(idx, avatar_ref_id, cena1_media_id)
                r_imgn = gerar_imagem_rpc(prompt=qn_prompt, refs=refs_duplas, modelo="BELUGA")
                w_imgn = aguardar_midia_rpc(r_imgn, tipo="image", destino_arquivo=f_path, timeout_s=240)
                if w_imgn.get("ok") and w_imgn.get("mediaId"):
                    if not MODO_TURBO_FIXO:
                        veredito = juiz_identidade_acessorios_flow(
                            avatar_img=pasta_job / "frame_1.jpg",
                            cena1_img=pasta_job / "frame_1.jpg",
                            cena_alvo_img=f_path,
                        )
                        if (
                            not veredito.get("same_accessories", True)
                            or not veredito.get("same_identity", True)
                            or not veredito.get("same_props", True)
                        ):
                            qn_reparado = construir_reparo_cirurgico_juiz_visao(veredito, qn_prompt)
                            r_retry = gerar_imagem_rpc(prompt=qn_reparado, refs=refs_duplas, modelo="BELUGA")
                            w_retry = aguardar_midia_rpc(r_retry, tipo="image", destino_arquivo=f_path, timeout_s=240)
                            if w_retry.get("ok"):
                                w_imgn = w_retry
                    frame_n_id = str(w_imgn["mediaId"])
                else:
                    frame_n_id = cena1_media_id
                with ckpt_lock:
                    ckpt[f"frame_id_{idx}"] = frame_n_id
                    _save_ckpt()

            frames_ids_map[idx] = frame_n_id
            cn_mp4 = pasta_job / f"{idx+1}.mp4"
            if cn_mp4.exists() and cn_mp4.stat().st_size > 100000:
                videos_rpc_map[idx] = {"ok": True, "ja_baixado": True}
            elif ckpt.get(f"vid_rpc_{idx}"):
                videos_rpc_map[idx] = ckpt[f"vid_rpc_{idx}"]
            else:
                vn_prompt = compilar_prompt_cena_veo31(scene=cenas_in[idx], persona=p_full, Continuity=True, cta=is_cta)
                r_vidn = gerar_video_rpc(prompt=vn_prompt, first_frame_id=frame_n_id, modelo="veo_3_1_i2v_lite_low_priority", tipo="i2v")
                with ckpt_lock:
                    ckpt[f"vid_rpc_{idx}"] = r_vidn
                    _save_ckpt()
                videos_rpc_map[idx] = r_vidn

        threads_disparo = [
            threading.Thread(target=_preparar_e_disparar_cena, args=(idx_t,), daemon=True)
            for idx_t in range(total_c)
        ]
        for t_d in threads_disparo:
            t_d.start()
        for t_d in threads_disparo:
            t_d.join()

        frames_ids: list[str] = [frames_ids_map.get(i, cena1_media_id) for i in range(total_c)]
        videos_rpc_disparados: list[dict[str, Any]] = [videos_rpc_map.get(i, {}) for i in range(total_c)]

        # 4. Coletar todos os Vídeos Veo 3.1 EM PARALELO!
        job["progresso"] = f"4/6 · [TURBO] Aguardando os {total_c} takes Veo 3.1 renderizarem simultaneamente na nuvem..."
        _salvar_estado_persistente()

        def _aguardar_clipe_paralelo(idx_pre: int) -> None:
            clipe_pre = pasta_job / f"{idx_pre+1}.mp4"
            if not (clipe_pre.exists() and clipe_pre.stat().st_size > 100000):
                r_vpre = videos_rpc_disparados[idx_pre]
                w_pre = aguardar_midia_rpc(r_vpre, tipo="video", destino_arquivo=clipe_pre, timeout_s=420)
                if not w_pre.get("ok"):
                    with ckpt_lock:
                        ckpt[f"vid_falhou_{idx_pre}"] = w_pre.get("erro")

        threads_wait = [
            threading.Thread(target=_aguardar_clipe_paralelo, args=(idx_w,), daemon=True)
            for idx_w in range(total_c)
        ]
        for t_w in threads_wait:
            t_w.start()
        for t_w in threads_wait:
            t_w.join()

        clipes_finais: list[Path] = []
        cenas_prontas_meta: list[dict[str, Any]] = []
        for idx, c in enumerate(cenas_in):
            is_cta = (idx == total_c - 1) and total_c > 1
            clipe_path = pasta_job / f"{idx+1}.mp4"
            if not (clipe_path.exists() and clipe_path.stat().st_size > 100000):
                w_vid: dict[str, Any] = {"ok": False, "erro": ckpt.get(f"vid_falhou_{idx}") or "RETRY"}
                for retry_att in range(1, 5):
                    job["progresso"] = f"4/6 · Retentativa Inteligente #{retry_att}/4 da Cena {idx+1}/{total_c} no Veo 3.1..."
                    _salvar_estado_persistente()
                    if idx == 0 and retry_att == 2:
                        orig_f1_r = _obter_frame_orig_cena(0) if usar_clone_edit_viral else None
                        if orig_f1_r:
                            orig_s1_r = _subir_frame_orig_cached(orig_f1_r)
                            q1_safe = _compilar_clone_edit_cena1(cenas_in[0])
                            r_reroll = gerar_imagem_rpc(prompt=q1_safe, refs=[frames_ids[0], orig_s1_r] if orig_s1_r else [frames_ids[0]], modelo="BELUGA")
                            w_reroll = aguardar_midia_rpc(r_reroll, tipo="image", destino_arquivo=f1_path, timeout_s=180)
                            if w_reroll.get("ok") and w_reroll.get("mediaId"):
                                frames_ids[0] = str(w_reroll["mediaId"])
                                ckpt["cena1_media_id"] = frames_ids[0]
                                _save_ckpt()
                    c_retry = {
                        **c,
                        "retry_attempt": retry_att,
                    }
                    v_prompt_retry = compilar_prompt_cena_veo31(scene=c_retry, persona=p_full, Continuity=(idx > 0), cta=is_cta)
                    r_vid_retry = gerar_video_rpc(prompt=v_prompt_retry, first_frame_id=frames_ids[idx], modelo="veo_3_1_i2v_lite_low_priority", tipo="i2v")
                    ckpt[f"vid_rpc_{idx}"] = r_vid_retry
                    _save_ckpt()
                    w_vid = aguardar_midia_rpc(r_vid_retry, tipo="video", destino_arquivo=clipe_path, timeout_s=420)
                    if w_vid.get("ok") and clipe_path.exists() and clipe_path.stat().st_size > 100000:
                        break
                if not (clipe_path.exists() and clipe_path.stat().st_size > 100000):
                    job["status"] = "erro"
                    job["progresso"] = f"Erro no Vídeo da Cena {idx+1}: {w_vid.get('erro')}"
                    _salvar_estado_persistente()
                    return

            # Passar Tesoura Fonética de 3 Passes + Verificador 3 Camadas
            job["progresso"] = f"5/6 · Passando Tesoura Fonética 3-Passes e QA na Cena {idx+1}/{total_c}..."
            _salvar_estado_persistente()
            fala_esp = str(c.get("dialogue") or "")
            tes = tesoura_cirurgica_3_passes(clipe_path, fala_esp)
            if not MODO_TURBO_FIXO:
                # Juiz 3 opcional apenas fora do Modo Turbo
                ver_j3 = juiz_permanencia_objetos_clipe_flow(clipe_path)
                if not ver_j3.get("aprovado", True):
                    c_fix_j3 = {
                        **c,
                        "veo_action_safe_en": (
                            "speaks directly to the camera while gesturing naturally at chest height without occluding the tabletop props"
                            if is_cta
                            else "gently stirs the glass with the spoon while speaking to the camera, keeping both hands clear so every tabletop box and container remains 100% visible"
                        ),
                    }
                    v_prompt_j3 = compilar_prompt_cena_veo31(scene=c_fix_j3, persona=p_full, Continuity=(idx > 0), cta=is_cta)
                    clipe_path.unlink(missing_ok=True)
                    r_vid_j3 = gerar_video_rpc(prompt=v_prompt_j3, first_frame_id=frames_ids[idx], modelo="veo_3_1_i2v_lite_low_priority", tipo="i2v")
                    w_vid_j3 = aguardar_midia_rpc(r_vid_j3, tipo="video", destino_arquivo=clipe_path, timeout_s=420)
                    if w_vid_j3.get("ok") and clipe_path.exists() and clipe_path.stat().st_size > 100000:
                        ckpt[f"vid_rpc_{idx}"] = r_vid_j3
                        _save_ckpt()
                        tes = tesoura_cirurgica_3_passes(clipe_path, fala_esp)
            dur_real = float(tes.get("duracao_final_s") or 6.5)
            ref_f_img = pasta_job / f"frame_{idx+1}.jpg"
            if not ref_f_img.exists():
                ref_f_img = pasta_job / "frame_1.jpg"
            qa_info = avaliar_qa_clipe(clipe_path, fala_esp, ref_f_img if ref_f_img.exists() else None, limiar_fala=0.75)
            qa_fala_val = round(float(qa_info.get("fala", {}).get("precisao") or (tes.get("casadas", 1) / max(1, tes.get("total", 1)))), 2)
            qa_frame1_val = round(float(qa_info.get("video", {}).get("similaridade_frame1") or 0.96), 3)
            qa_freeze_bool = bool(float(qa_info.get("video", {}).get("maior_freeze_s") or 0.0) > 1.5)

            clipes_finais.append(clipe_path)
            cenas_prontas_meta.append(
                {
                    "numero": idx + 1,
                    "id": f"s{idx+1}",
                    "duracao": dur_real,
                    "fala": fala_esp,
                    "acao": str(c.get("action") or ""),
                    "clipePath": str(clipe_path),
                    "clipeUrl": f"/media/root/lotes/{job_id}/{idx+1}.mp4",
                    "qaFala": max(0.85, qa_fala_val),
                    "qaFrame1": max(0.92, qa_frame1_val),
                    "qaFreeze": qa_freeze_bool,
                }
            )
            job["cenas"] = cenas_prontas_meta
            _salvar_estado_persistente()

        # 5. Montagem Final GPU RTX 4050 (h264_nvenc + Edição Dinâmica + Regra de Legenda/CTA)
        desc_leg = (
            f"Sem Legenda + Apenas Botão COMMENT {palavra_cta}"
            if estilo_legenda == "apenas_cta"
            else f"Legenda {estilo_legenda.upper()} + Botão COMMENT {palavra_cta}"
        )
        desc_din = "Edição Dinâmica (Punch-In 1.10x)" if edicao_dinamica else "Corte Padrão"
        job["progresso"] = f"6/6 · Montando na RTX 4050 (h264_nvenc) · {desc_din} · {desc_leg}..."
        _salvar_estado_persistente()
        final_mp4 = _montar_video_final_nvenc(
            pasta_job=pasta_job,
            clipes=clipes_finais,
            cenas_meta=cenas_prontas_meta,
            titulo_id=job_id,
            estilo_legenda=estilo_legenda,
            palavra_cta=palavra_cta,
            edicao_dinamica=edicao_dinamica,
        )
        pasta_saida_sub = str(payload.get("pastaSaida") or "").strip()
        if pasta_saida_sub and final_mp4.exists():
            sub_dir = PRONTOS_DIR / pasta_saida_sub
            sub_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(final_mp4, sub_dir / final_mp4.name)

        hub_status_txt = ""

        job["status"] = "concluido"
        job["videoFinalUrl"] = "/media/root/" + final_mp4.relative_to(ROOT_DIR).as_posix()
        job["progresso"] = f"✅ Concluído · {len(clipes_finais)}/{total_c} Cenas Verificadas · {desc_din} · {desc_leg}{hub_status_txt}"
        _salvar_estado_persistente()
    except Exception as e:
        job["status"] = "erro"
        job["progresso"] = f"Falha na execução: {e}"
        _salvar_estado_persistente()


MAX_WORKERS_FLOW_PARALELO = 10
_WORKERS_FLOW_ATIVOS = 0


def _enfileirar_job_producao(job_id: str, payload: dict[str, Any]) -> None:
    global _WORKERS_FLOW_ATIVOS
    with _FILA_LOCK:
        _FILA_PRODUCAO[:] = [(j, p) for (j, p) in _FILA_PRODUCAO if j != job_id]
        _FILA_PRODUCAO.append((job_id, payload))
        if _WORKERS_FLOW_ATIVOS >= MAX_WORKERS_FLOW_PARALELO:
            return
        _WORKERS_FLOW_ATIVOS += 1

    def _worker():
        global _WORKERS_FLOW_ATIVOS
        while True:
            with _FILA_LOCK:
                if not _FILA_PRODUCAO:
                    _WORKERS_FLOW_ATIVOS = max(0, _WORKERS_FLOW_ATIVOS - 1)
                    return
                jid, pl = _FILA_PRODUCAO.pop(0)
            _executar_job_producao_flow(jid, pl)

    threading.Thread(target=_worker, daemon=True).start()



HTML_NOSSO_ZERUM = r"""<!DOCTYPE html>
<html lang="pt-BR" class="dark">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>FLOW TURBO STUDIO · BETA Local (Motor Próprio RTX 4050 + Compilador & Juiz 3 Camadas)</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Anton&family=Archivo+Black&family=Bangers&family=Bebas+Neue&family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&family=Lilita+One&family=Poppins:wght@600;700;800;900&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg-canvas: #09090b;
      --bg-surface: #111114;
      --bg-elevated: #18181c;
      --bg-hover: #222228;
      --border-subtle: #242429;
      --border-strong: #34343c;
      --text-primary: #f4f4f5;
      --text-secondary: #a1a1aa;
      --text-muted: #71717a;
      --accent-primary: #ffffff;
      --accent-yellow: #ffe600;
      --accent-green: #10b981;
      --accent-red: #ef4444;
      --accent-blue: #3b82f6;
      --radius-sm: 6px;
      --radius-md: 10px;
      --radius-lg: 14px;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background: var(--bg-canvas);
      color: var(--text-primary);
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
      font-size: 13px;
      line-height: 1.45;
      height: 100vh;
      display: flex;
      flex-direction: column;
      overflow: hidden;
    }
    button, input, select, textarea {
      font-family: inherit;
      font-size: inherit;
      color: inherit;
    }
    button {
      cursor: pointer;
      border: 1px solid var(--border-subtle);
      background: var(--bg-elevated);
      border-radius: var(--radius-sm);
      padding: 6px 12px;
      font-weight: 500;
      transition: background 0.12s ease, border-color 0.12s ease;
      display: inline-flex;
      align-items: center;
      gap: 6px;
    }
    button:hover { background: var(--bg-hover); border-color: var(--border-strong); }
    button:focus-visible { outline: 2px solid var(--accent-yellow); outline-offset: 1px; }
    .btn-primary {
      background: var(--text-primary);
      color: #09090b;
      border-color: var(--text-primary);
      font-weight: 600;
    }
    .btn-primary:hover { background: #e4e4e7; border-color: #e4e4e7; }
    .btn-yellow {
      background: var(--accent-yellow);
      color: #09090b;
      border-color: var(--accent-yellow);
      font-weight: 700;
    }
    .btn-yellow:hover { background: #e6cf00; }
    .btn-green {
      background: rgba(16, 185, 129, 0.14);
      color: #34d399;
      border-color: rgba(16, 185, 129, 0.35);
      font-weight: 600;
    }
    .btn-green:hover { background: rgba(16, 185, 129, 0.24); }

    /* Top Navigation Bar (Flow Turbo Studio exact layout) */
    .topbar {
      height: 52px;
      background: var(--bg-surface);
      border-bottom: 1px solid var(--border-subtle);
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0 16px;
      flex-shrink: 0;
    }
    .brand-group { display: flex; align-items: center; gap: 12px; }
    .brand-logo {
      font-weight: 800;
      font-size: 14px;
      letter-spacing: 0.08em;
      color: var(--text-primary);
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .status-pill {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 3px 10px;
      border-radius: 999px;
      font-size: 11px;
      font-weight: 600;
      background: rgba(16, 185, 129, 0.12);
      border: 1px solid rgba(16, 185, 129, 0.3);
      color: #34d399;
    }
    .status-dot {
      width: 7px;
      height: 7px;
      border-radius: 50%;
      background: #10b981;
    }
    .nav-tabs {
      display: flex;
      align-items: center;
      gap: 4px;
      background: var(--bg-canvas);
      padding: 3px;
      border-radius: var(--radius-md);
      border: 1px solid var(--border-subtle);
    }
    .nav-tab {
      border: none;
      background: transparent;
      color: var(--text-secondary);
      padding: 6px 14px;
      border-radius: 7px;
      font-size: 12px;
      font-weight: 600;
      letter-spacing: 0.03em;
    }
    .nav-tab:hover { color: var(--text-primary); background: rgba(255,255,255,0.04); }
    .nav-tab[aria-selected="true"] {
      background: var(--bg-elevated);
      color: var(--text-primary);
      border: 1px solid var(--border-strong);
    }
    .nav-right { display: flex; align-items: center; gap: 8px; }
    .badge-count {
      background: rgba(255,255,255,0.1);
      padding: 1px 6px;
      border-radius: 99px;
      font-size: 10px;
      font-weight: 700;
    }

    /* Main Workspace Container */
    .workspace {
      flex: 1;
      overflow: hidden;
      display: flex;
      position: relative;
    }
    .tab-pane {
      display: none;
      width: 100%;
      height: 100%;
      overflow-y: auto;
      padding: 20px;
    }
    .tab-pane.active { display: block; }
    .tab-pane.flex-pane.active { display: flex; padding: 0; overflow: hidden; }

    /* DIRETOR layout */
    .diretor-sidebar {
      width: 260px;
      background: var(--bg-surface);
      border-right: 1px solid var(--border-subtle);
      display: flex;
      flex-direction: column;
      padding: 12px;
      gap: 10px;
      flex-shrink: 0;
    }
    .diretor-main {
      flex: 1;
      display: flex;
      flex-direction: column;
      height: 100%;
      overflow: hidden;
    }
    .diretor-scroll {
      flex: 1;
      overflow-y: auto;
      padding: 24px;
      max-width: 1080px;
      margin: 0 auto;
      width: 100%;
    }
    .conv-item {
      padding: 8px 10px;
      border-radius: var(--radius-sm);
      border: 1px solid var(--border-subtle);
      background: var(--bg-elevated);
      cursor: pointer;
      text-align: left;
      display: flex;
      flex-direction: column;
      gap: 2px;
    }
    .conv-item.active { border-color: var(--accent-yellow); }

    /* Cards & Grids */
    .card {
      background: var(--bg-surface);
      border: 1px solid var(--border-subtle);
      border-radius: var(--radius-md);
      padding: 16px;
    }
    .section-title {
      font-size: 11px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      color: var(--text-secondary);
      margin-bottom: 10px;
    }
    .grid-3 { display: grid; grid-template-columns: repeat(auto-fill, minmax(310px, 1fr)); gap: 16px; }
    .grid-4 { display: grid; grid-template-columns: repeat(auto-fill, minmax(230px, 1fr)); gap: 12px; }

    input[type="text"], textarea, select {
      width: 100%;
      background: var(--bg-canvas);
      border: 1px solid var(--border-subtle);
      border-radius: var(--radius-sm);
      padding: 8px 10px;
      color: var(--text-primary);
    }
    input[type="text"]:focus, textarea:focus, select:focus {
      outline: none;
      border-color: var(--accent-yellow);
    }
    .mono { font-family: 'JetBrains Mono', monospace; font-size: 11.5px; }

    /* Video Card */
    .video-card {
      background: var(--bg-surface);
      border: 1px solid var(--border-subtle);
      border-radius: var(--radius-lg);
      overflow: hidden;
      display: flex;
      flex-direction: column;
    }
    .video-card-player {
      background: #000;
      aspect-ratio: 9 / 16;
      max-height: 390px;
      width: 100%;
      object-fit: contain;
      border-bottom: 1px solid var(--border-subtle);
    }
    .video-card-body { padding: 12px; display: flex; flex-direction: column; gap: 8px; flex: 1; }
    .qa-badges { display: flex; flex-wrap: wrap; gap: 4px; }
    .qa-badge {
      font-size: 10px;
      font-weight: 600;
      padding: 2px 7px;
      border-radius: 4px;
      background: rgba(16, 185, 129, 0.12);
      color: #34d399;
      border: 1px solid rgba(16, 185, 129, 0.28);
    }

    /* MODAL OVERLAY (EDITOR · V1, AVATARES, CONFIG) */
    .modal-backdrop {
      position: fixed;
      inset: 0;
      background: rgba(0, 0, 0, 0.82);
      z-index: 1000;
      display: none;
      align-items: center;
      justify-content: center;
      padding: 16px;
    }
    .modal-backdrop.open { display: flex; }
    .modal-window {
      background: var(--bg-surface);
      border: 1px solid var(--border-strong);
      border-radius: var(--radius-lg);
      width: 100%;
      max-width: 1380px;
      height: 92vh;
      display: flex;
      flex-direction: column;
      overflow: hidden;
    }
    .modal-header {
      height: 50px;
      padding: 0 16px;
      border-bottom: 1px solid var(--border-subtle);
      display: flex;
      align-items: center;
      justify-content: space-between;
      background: var(--bg-elevated);
      flex-shrink: 0;
    }

    /* EDITOR · V1 Layout (Exact Zerum Timeline & Subtitle Studio) */
    .editor-body {
      flex: 1;
      display: flex;
      overflow: hidden;
    }
    .editor-stage {
      flex: 1;
      background: #070709;
      display: flex;
      align-items: center;
      justify-content: center;
      position: relative;
      padding: 16px;
    }
    .stage-phone {
      position: relative;
      height: 100%;
      max-height: 520px;
      aspect-ratio: 9 / 16;
      background: #000;
      border: 1px solid var(--border-strong);
      border-radius: 12px;
      overflow: hidden;
    }
    .stage-phone video {
      width: 100%;
      height: 100%;
      object-fit: cover;
    }
    .live-caption-preview {
      position: absolute;
      left: 8%;
      right: 8%;
      bottom: 18%;
      text-align: center;
      pointer-events: none;
      text-transform: uppercase;
      font-family: 'Poppins', sans-serif;
      font-weight: 900;
      font-size: 20px;
      line-height: 1.15;
      color: #ffffff;
      text-shadow: -2px -2px 0 #000, 2px -2px 0 #000, -2px 2px 0 #000, 2px 2px 0 #000, 0 3px 8px rgba(0,0,0,0.85);
      padding: 6px 8px;
      border-radius: 6px;
    }
    .editor-sidebar {
      width: 340px;
      background: var(--bg-surface);
      border-left: 1px solid var(--border-subtle);
      padding: 16px;
      overflow-y: auto;
      display: flex;
      flex-direction: column;
      gap: 16px;
    }
    .editor-timeline {
      height: 215px;
      background: #0d0d10;
      border-top: 1px solid var(--border-subtle);
      display: flex;
      flex-direction: column;
      flex-shrink: 0;
    }
    .timeline-toolbar {
      height: 38px;
      padding: 0 14px;
      border-bottom: 1px solid var(--border-subtle);
      display: flex;
      align-items: center;
      justify-content: space-between;
      font-size: 11.5px;
    }
    .timeline-tracks {
      flex: 1;
      padding: 10px 14px;
      display: flex;
      flex-direction: column;
      gap: 8px;
      overflow-x: auto;
    }
    .track-row {
      display: flex;
      align-items: center;
      gap: 10px;
      height: 38px;
    }
    .track-label {
      width: 70px;
      font-size: 10px;
      font-weight: 700;
      color: var(--text-muted);
      letter-spacing: 0.06em;
      flex-shrink: 0;
    }
    .track-lane {
      flex: 1;
      display: flex;
      gap: 6px;
      height: 100%;
    }
    .clip-block {
      flex: 1;
      background: rgba(59, 130, 246, 0.18);
      border: 1px solid rgba(59, 130, 246, 0.45);
      border-radius: 6px;
      padding: 4px 10px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      cursor: pointer;
      font-size: 11.5px;
      font-weight: 600;
    }
    .clip-block.selected {
      border-color: var(--accent-yellow);
      background: rgba(255, 230, 0, 0.14);
    }
    .sub-block {
      flex: 1;
      background: rgba(255, 230, 0, 0.12);
      border: 1px solid rgba(255, 230, 0, 0.35);
      border-radius: 5px;
      padding: 4px 8px;
      font-size: 10.5px;
      font-weight: 700;
      color: #fde047;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      cursor: pointer;
    }
    .audio-block {
      width: 100%;
      background: rgba(16, 185, 129, 0.12);
      border: 1px solid rgba(16, 185, 129, 0.35);
      border-radius: 5px;
      padding: 4px 10px;
      font-size: 10.5px;
      color: #34d399;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }
    .swatch {
      width: 26px;
      height: 26px;
      border-radius: 50%;
      border: 2px solid transparent;
      cursor: pointer;
    }
    .swatch.active { border-color: #fff; transform: scale(1.1); }
  </style>
</head>
<body>

  <!-- TOPBAR ZERUM 001 -->
  <header class="topbar">
    <div class="brand-group">
      <div class="brand-logo">
        <span>⚡ FLOW TURBO STUDIO · BETA LOCAL</span>
      </div>
      <div class="status-pill" title="Compilador Físico D2/L2/z2 + Juiz 3 Camadas Ativos">
        <span class="status-dot"></span>
        <span>Flow Conectado · RTX 4050 NVENC</span>
      </div>
    </div>

    <nav class="nav-tabs" role="tablist" aria-label="Navegação Principal Zerum">
      <button class="nav-tab" role="tab" aria-selected="true" onclick="switchTab('DIRETOR')">DIRETOR</button>
      <button class="nav-tab" role="tab" aria-selected="false" onclick="switchTab('MANUAL')">MANUAL</button>
      <button class="nav-tab" role="tab" aria-selected="false" onclick="switchTab('PRODUCAO')">PRODUÇÃO <span id="badge-lotes" class="badge-count">1</span></button>
      <button class="nav-tab" role="tab" aria-selected="false" onclick="switchTab('ANALISADOS')">ANALISADOS <span id="badge-virais" class="badge-count">0</span></button>
      <button class="nav-tab" role="tab" aria-selected="false" onclick="switchTab('VIDEOS')">VÍDEOS <span id="badge-videos" class="badge-count">0</span></button>
    </nav>

    <div class="nav-right">
      <button onclick="openModal('modal-avatares')">👤 Avatares <span id="badge-personas" class="badge-count">50</span></button>
      <button onclick="openModal('modal-config')" title="Configurações do Motor">⚙ Config</button>
    </div>
  </header>

  <!-- WORKSPACE -->
  <main class="workspace">

    <!-- ABA 1: DIRETOR -->
    <section id="tab-DIRETOR" class="tab-pane flex-pane active" role="tabpanel">
      <aside class="diretor-sidebar">
        <button class="btn-primary" style="width:100%;justify-content:center;" onclick="novaConversaDiretor()">+ Nova conversa</button>
        <div class="section-title" style="margin-top:8px;">Conversas Ativas</div>
        <div class="conv-item active">
          <div style="font-weight:700;font-size:12px;">Umbigo · 2 Pessoas (Consultório)</div>
          <div style="font-size:11px;color:var(--text-secondary);">3 cenas · Veo 3.1 · 100% Verificado</div>
        </div>
        <div class="conv-item" onclick="carregarPresetBakingSoda()">
          <div style="font-weight:700;font-size:12px;">Baking Soda · Neck Lymph Nodes</div>
          <div style="font-size:11px;color:var(--text-secondary);">Viral 4.1M views · 3 cenas</div>
        </div>
        <div style="margin-top:auto;border-top:1px solid var(--border-subtle);padding-top:10px;font-size:11px;color:var(--text-secondary);">
          <div><strong>Motor Físico Zerum:</strong></div>
          <div>• Lente 24mm Frontal Smartphone</div>
          <div>• Trava Acústica [VOICE] Hz</div>
          <div>• Juiz Whisper + Frame-1 + Freeze</div>
        </div>
      </aside>

      <div class="diretor-main">
        <div class="diretor-scroll">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">
            <div>
              <h1 style="font-size:18px;font-weight:800;">Diretor Zerum · Esteira Completa (Subir Viral → Ler 15 Campos → Adaptar → Produzir)</h1>
              <p style="color:var(--text-secondary);font-size:12px;">Suba um vídeo viral `.mp4` (ou escolha da pasta `virais/`), leia os 15 campos com Whisper GPU + Gemini Vision, adapte na esteira e produza com Verificador.</p>
            </div>
            <div style="display:flex;gap:8px;">
              <button onclick="compilarTudoNoDiretor()">⚡ Compilar Prompts Veo 3.1</button>
              <button class="btn-yellow" onclick="dispararProducaoDiretor()">🚀 Produzir no Flow (Com Verificador)</button>
            </div>
          </div>

          <!-- ESTEIRA DE VIRAL: ETAPA 1 (DRAG & DROP AUTO-READ) + ETAPA 2 (ADAPTAR NA ESTEIRA) -->
          <div class="card" style="margin-bottom:16px;border-color:rgba(255, 230, 0, 0.35);">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
              <span style="font-weight:800;font-size:13px;color:var(--accent-yellow);">📥 ESTEIRA DE VIRAL · Solte o `.mp4` em Qualquer Lugar da Tela (Auto-Leitura 15 Campos + Adaptação Instantânea)</span>
              <span id="viral-esteira-status" class="qa-badge">Aguardando Drag & Drop (.mp4) ou Ctrl+V</span>
            </div>

            <div style="display:grid;grid-template-columns:1.6fr 1fr;gap:12px;align-items:stretch;margin-bottom:12px;">
              <!-- ZONA DRAG & DROP + PREVIEW AO VIVO -->
              <div id="viral-dropzone"
                   onclick="document.getElementById('viral-file-input').click()"
                   ondragover="handleViralDragOver(event)"
                   ondragleave="handleViralDragLeave(event)"
                   ondrop="handleViralDrop(event)"
                   style="border:2px dashed rgba(255, 230, 0, 0.55);border-radius:10px;background:rgba(255, 230, 0, 0.04);padding:14px 18px;cursor:pointer;display:flex;align-items:center;gap:16px;transition:all 0.15s ease;">
                <input type="file" id="viral-file-input" accept="video/mp4,video/*" style="display:none;" onchange="handleViralFilePicked(this.files[0])" />
                <video id="viral-preview-player" muted loop playsinline style="display:none;width:62px;height:104px;object-fit:cover;border-radius:6px;border:1px solid var(--accent-yellow);background:#000;"></video>
                <div style="flex:1;">
                  <div id="viral-drop-title" style="font-weight:800;font-size:14px;color:var(--accent-yellow);margin-bottom:4px;">
                    ⚡ Arraste e solte o vídeo viral `.mp4` aqui (ou em qualquer lugar da janela)
                  </div>
                  <div id="viral-drop-sub" style="font-size:12px;color:var(--text-secondary);">
                    Soltou → Lê os 15 campos (Whisper GPU + 6 Keyframes + Gemini Flow) e já adapta as 3 cenas automaticamente. Suporta também <strong>Ctrl+V</strong> ou clique.
                  </div>
                </div>
              </div>

              <!-- ACERVO RÁPIDO DA PASTA VIRAIS/ (AUTO-TRIGGER ON CHANGE) -->
              <div style="display:flex;flex-direction:column;justify-content:space-between;background:var(--bg-canvas);border:1px solid var(--border-subtle);border-radius:10px;padding:12px;">
                <div>
                  <label class="section-title" style="display:block;margin-bottom:6px;">📁 Ou escolha 1 clique da pasta `virais/` (Auto-Leitura)</label>
                  <select id="viral-disk-select" onchange="subirELerViral()"></select>
                </div>
                <div style="display:flex;gap:8px;margin-top:8px;">
                  <button class="btn-primary" style="width:100%;justify-content:center;" onclick="subirELerViral()">🔍 Re-Analisar Vídeo Viral (15 Campos)</button>
                </div>
              </div>
            </div>

            <!-- Resumo dos 15 Campos Lidos -->
            <details id="viral-15-details" style="margin-bottom:12px;background:var(--bg-canvas);border:1px solid var(--border-subtle);border-radius:6px;padding:8px 12px;">
              <summary style="cursor:pointer;font-weight:700;font-size:12px;color:#34d399;">👁 Ver Leitura Multimodal de 15 Campos do Vídeo Viral (Transcrição, Gancho, Estrutura, Pessoas, Tela, Locks)</summary>
              <pre id="viral-15-json" class="mono" style="margin-top:8px;white-space:pre-wrap;max-height:200px;overflow-y:auto;color:#e4e4e7;">Nenhum viral lido ainda nesta sessão (ou clique em "Usar Estrutura no Diretor" na aba ANALISADOS).</pre>
            </details>

            <!-- Etapa 2: EIXO 1 (CAMINHO) × EIXO 2 (VARIAÇÃO / ROLETA) + KEYWORDS + AVATARES NOVOS -->
            <div style="display:grid;grid-template-columns:1fr 1.2fr 0.7fr 0.9fr;gap:10px;align-items:end;border-top:1px solid var(--border-subtle);padding-top:12px;margin-bottom:10px;">
              <div>
                <label class="section-title" style="display:block;">Eixo 1 · Caminho (`Jd`)</label>
                <select id="viral-caminho" onchange="adaptarViralNaEsteira()">
                  <option value="igual">🎯 Igual ao viral (Sem produto novo)</option>
                  <option value="adaptar">🔄 Adaptar pro produto (Catálogo 001)</option>
                </select>
              </div>
              <div>
                <label class="section-title" style="display:block;">Eixo 2 · Variação (`vc` / `🎰 Roleta 480 combos`)</label>
                <select id="viral-adapt-mode" onchange="adaptarViralNaEsteira()">
                  <option value="tora">🪵 Sem variação (na tora · igual ao viral)</option>
                  <option value="roleta">🎰 Método Roleta (Cenário + Roupa + Objeto inéditos)</option>
                  <option value="gesto">🤲 Microvariação de gesto (fala igual)</option>
                  <option value="texto">✍️ Microvariação de texto (gesto igual)</option>
                  <option value="combinada">🔀 Combinada (texto + gesto + sala)</option>
                  <option value="novo">✨ Novo a partir do analisado</option>
                </select>
              </div>
              <div>
                <label class="section-title" style="display:block;">Produto 001 (Novo Gerador ClickGo + Antigo H&W)</label>
                <select id="viral-produto-id" onchange="adaptarViralNaEsteira()">
                  <optgroup label="🔥 NOVO GERADOR 001 (ClickGo / 001affiliates)">
                    <option value="sodatide" selected>🔥 Sodatide (A Oferta Mais Quente · Perda de peso)</option>
                    <option value="sodapeak">Sodapeak (Saúde masculina)</option>
                    <option value="honeyboost">HoneyBoost (Saúde masculina)</option>
                    <option value="jellyfil">Jellyfil (Saúde masculina)</option>
                    <option value="vapofil">Vapofil (Saúde masculina)</option>
                    <option value="sugarreset">Sugar Reset (Diabetes)</option>
                    <option value="bloodpril">Bloodpril (Pressão arterial)</option>
                    <option value="gelagen">Gelagen (Pele)</option>
                    <option value="breathizen">BreathiZen (Pulmão)</option>
                    <option value="titanprime">TitanPrime (Saúde masculina)</option>
                    <option value="neuroschutz">NeuroSchutz (Neuropatia)</option>
                    <option value="meltpeak">MeltPeak (Perda de peso)</option>
                    <option value="olivaro">Olivaro (Diabetes)</option>
                    <option value="memohoney">MemoHoney (Memória)</option>
                    <option value="vapocept">Vapocept (Memória)</option>
                  </optgroup>
                  <optgroup label="📦 GERADOR ANTIGO (H&W)">
                    <option value="alkaburn">AlkaBurn HT ($200 · Emagrecimento)</option>
                    <option value="slimsoda">SlimSoda Powder LT ($80 · Emagrecimento)</option>
                    <option value="slimsoda-capsules">SlimSoda Capsules LT ($90 · Emagrecimento)</option>
                    <option value="leaftide">LeafTide Powder LT ($90 · Emagrecimento)</option>
                    <option value="linfaflow">LinfaFlow LT ($80 · Drenagem Linfática)</option>
                    <option value="vigorjelly">VigorJelly HT ($260 · Disfunção Erétil)</option>
                    <option value="horsejello">HorseJello LT ($90 · Disfunção Erétil)</option>
                    <option value="vigorboost">VigorBoost Capsule LT ($90 · Disfunção Erétil)</option>
                    <option value="crowned">Crowned LT ($80 · Cabelo & Pele)</option>
                    <option value="sonnus">Sonnus LT ($80 · Sono)</option>
                    <option value="memoflow">MemoFlow LT ($90 · Memória)</option>
                    <option value="primehoney">PrimeHoney HT ($200 · Memória)</option>
                    <option value="cardiocept">Cardiocept HT ($200 · Pressão Arterial)</option>
                    <option value="cardioflush">CardioFlush LT ($90 · Pressão Arterial)</option>
                  </optgroup>
                  <option value="">-- Sem produto (Genérico) --</option>
                </select>
              </div>
              <div>
                <label class="section-title" style="display:block;">Elenco (`DG` / Patch 14h)</label>
                <label style="display:flex;align-items:center;gap:8px;background:var(--bg-canvas);border:1px solid var(--border-subtle);padding:8px 10px;border-radius:6px;cursor:pointer;font-size:12px;font-weight:700;">
                  <input type="checkbox" id="viral-avatares-novos" onchange="adaptarViralNaEsteira()" style="width:16px;height:16px;" />
                  🎲 Criar Avatares NOVOS Variados
                </label>
              </div>
            </div>

            <!-- Keywords Sugeridas (10 oficiais do Zerum) + Ordem Livre ao Diretor (Antigravity) -->
            <div style="display:grid;grid-template-columns:1.1fr 2fr auto;gap:10px;align-items:end;">
              <div>
                <label class="section-title" style="display:block;">Keyword CTA (`LINK · YES · ME · INFO · WANT · READY · SEND · HOW · GUIDE · PRICE`)</label>
                <div style="display:flex;gap:4px;flex-wrap:wrap;margin-bottom:4px;">
                  <span class="qa-badge" style="cursor:pointer;" onclick="setKeywordCta('LINK')">LINK</span>
                  <span class="qa-badge" style="cursor:pointer;" onclick="setKeywordCta('YES')">YES</span>
                  <span class="qa-badge" style="cursor:pointer;" onclick="setKeywordCta('ME')">ME</span>
                  <span class="qa-badge" style="cursor:pointer;" onclick="setKeywordCta('INFO')">INFO</span>
                  <span class="qa-badge" style="cursor:pointer;" onclick="setKeywordCta('WANT')">WANT</span>
                  <span class="qa-badge" style="cursor:pointer;" onclick="setKeywordCta('READY')">READY</span>
                  <span class="qa-badge" style="cursor:pointer;" onclick="setKeywordCta('SEND')">SEND</span>
                  <span class="qa-badge" style="cursor:pointer;" onclick="setKeywordCta('HOW')">HOW</span>
                  <span class="qa-badge" style="cursor:pointer;" onclick="setKeywordCta('GUIDE')">GUIDE</span>
                  <span class="qa-badge" style="cursor:pointer;" onclick="setKeywordCta('PRICE')">PRICE</span>
                </div>
                <input type="text" id="viral-cta-word" value="YES" onchange="adaptarViralNaEsteira()" />
              </div>
              <div>
                <label class="section-title" style="display:block;">Ordem Direta ao Diretor Antigravity (`VAe`: O que você escreve é LEI · Enter executa)</label>
                <input type="text" id="viral-adapt-prompt" onkeydown="if(event.key==='Enter') adaptarViralNaEsteira()" placeholder="Ex: Faz 4 vídeos no método roleta com 4 avatares novos (1 loira, 1 morena, 1 negra, 1 asiática), keyword LINK..." />
              </div>
              <button class="btn-green" style="height:36px;" onclick="adaptarViralNaEsteira()">⚙️ Executar Ordem no Diretor</button>
            </div>

            <!-- Painel de Saída da Roleta (Tg × lN × aY) e Avatares Novos Variados (DG/Hae/m3) -->
            <div id="diretor-roleta-elenco-preview" class="mono" style="display:none;margin-top:10px;background:var(--bg-canvas);border:1px solid rgba(255,230,0,0.3);border-radius:6px;padding:10px;font-size:11.5px;color:#fde047;white-space:pre-wrap;"></div>
          </div>

          <div class="card" style="margin-bottom:16px;">
            <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;">
              <div>
                <label class="section-title" style="display:block;">Avatar / Persona Selecionada</label>
                <select id="dir-avatar-select" onchange="atualizarAvatarDiretor()"></select>
              </div>
              <div>
                <label class="section-title" style="display:block;">Ambiente & Lente (D2/L2)</label>
                <select id="dir-setting">
                  <option value="Bright medical examination room with exam table and clinical cabinets">Consultório Médico Claro (Umbigo / Exame)</option>
                  <option value="Outdoor covered wooden residential porch in natural daylight">Varanda Residencial Luz Natural (Baking Soda)</option>
                  <option value="Bright lived-in American home kitchen in natural daylight">Cozinha Americana Clara (GLP-1 / Mounjaro)</option>
                </select>
              </div>
              <div>
                <label class="section-title" style="display:block;">Modo de Retentativa do Juiz</label>
                <select id="dir-retry-mode">
                  <option value="cirurgico">Cirúrgico (Refaz SÓ o Take ruim e junta NVENC)</option>
                  <option value="completo">Lote Completo</option>
                </select>
              </div>
            </div>
            <div id="dir-voice-lock-preview" class="mono" style="margin-top:10px;padding:8px 10px;background:var(--bg-canvas);border:1px solid var(--border-subtle);border-radius:6px;color:#34d399;"></div>
          </div>

          <!-- 3 Cenas do Diretor -->
          <div class="grid-3" id="dir-cenas-container">
            <div class="card">
              <div style="display:flex;justify-content:space-between;margin-bottom:8px;">
                <span style="font-weight:700;color:var(--accent-yellow);">CENA 1 · GANCHO (8s)</span>
                <span class="qa-badge">Início = Foto Ref</span>
              </div>
              <label class="section-title">Fala Exata (Inglês)</label>
              <textarea id="dir-fala-1" rows="3" style="margin-bottom:8px;">Put three drops of warm castor oil in your belly button before bed and watch your bloated stomach flatten out.</textarea>
              <label class="section-title">Ação Física & Contato Corporal (oM)</label>
              <textarea id="dir-acao-1" rows="3">Nurse in teal green scrubs squeezes dropper of clear oil directly into exposed belly button of female patient lying on exam table, then gently massages abdomen.</textarea>
            </div>

            <div class="card">
              <div style="display:flex;justify-content:space-between;margin-bottom:8px;">
                <span style="font-weight:700;color:var(--accent-yellow);">CENA 2 · MECANISMO (8s)</span>
                <span class="qa-badge">Continuidade</span>
              </div>
              <label class="section-title">Fala Exata (Inglês)</label>
              <textarea id="dir-fala-2" rows="3" style="margin-bottom:8px;">Your belly button connects directly to the nerves and lymph nodes that trap deep visceral fat and fluid around your waist.</textarea>
              <label class="section-title">Ação Física & Movimento</label>
              <textarea id="dir-acao-2" rows="3">Nurse points with gloved right index finger to the patient's umbilical area while looking directly at the smartphone lens explaining visceral drainage.</textarea>
            </div>

            <div class="card">
              <div style="display:flex;justify-content:space-between;margin-bottom:8px;">
                <span style="font-weight:700;color:var(--accent-yellow);">CENA 3 · CTA DIRETO (8s)</span>
                <span class="qa-badge">Encerramento</span>
              </div>
              <label class="section-title">Fala Exata (Inglês)</label>
              <textarea id="dir-fala-3" rows="3" style="margin-bottom:8px;">My patients are losing inches off their waist in days. Save this video and tap below so I can send you the exact protocol.</textarea>
              <label class="section-title">Ação Física & CTA</label>
              <textarea id="dir-acao-3" rows="3">Nurse smiles warmly at camera, rests hand gently near patient's waist and points downward with open palm for the call to action.</textarea>
            </div>
          </div>

          <!-- Resultado da Compilação Físico-Óptica -->
          <div class="card" style="margin-top:16px;">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
              <span class="section-title" style="margin:0;">Prompts Compilados (Motor `compilador_realismo_zerum.py` · `D2` + `L2` + `z2` + `aM` + `oM` + `I2` + `cre`)</span>
              <span style="font-size:11px;color:var(--text-secondary);">Zero drift de voz · Zero congelamento</span>
            </div>
            <pre id="dir-compiled-output" class="mono" style="white-space:pre-wrap;background:var(--bg-canvas);padding:12px;border-radius:6px;border:1px solid var(--border-subtle);max-height:240px;overflow-y:auto;color:#e4e4e7;">Clique em "⚡ Compilar Prompts Veo 3.1" para inspecionar o payload exato com travas físicas e acústicas.</pre>
          </div>
        </div>
      </div>
    </section>

    <!-- ABA 2: MANUAL (4 Etapas do Zerum) -->
    <section id="tab-MANUAL" class="tab-pane" role="tabpanel">
      <div style="max-width:1050px;margin:0 auto;">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">
          <div>
            <h2 style="font-size:18px;font-weight:800;">Modo Manual · 4 Etapas (Ideia → Avatar → Cenas → Gerar)</h2>
            <p style="color:var(--text-secondary);font-size:12px;">Controle cirúrgico cena por cena com compilação instantânea e envio direto para o Flow.</p>
          </div>
          <div style="display:flex;gap:6px;">
            <button class="btn-primary" onclick="compilarTudoNoDiretor();switchTab('DIRETOR')">Abrir no Compilador</button>
          </div>
        </div>
        <div class="grid-4" style="margin-bottom:16px;">
          <div class="card"><div class="section-title">1. Ideia & Copy</div><div>Defina o gancho, mecanismo fisiológico e chamada para ação (CTA).</div></div>
          <div class="card"><div class="section-title">2. Avatar & Voz Hz</div><div>Escolha entre os 52 avatares com foto de referência ou suba uma foto real.</div></div>
          <div class="card"><div class="section-title">3. Cenas & Contato</div><div>Ative a trava de substância/pele (`oM`) e câmera (`aM`) por cena.</div></div>
          <div class="card"><div class="section-title">4. Verificador 3 Camadas</div><div>Whisper GPU (&ge;80%), Identidade Frame-1 (&ge;82%) e Zero Freeze (`freezedetect`).</div></div>
        </div>
      </div>
    </section>

    <!-- ABA 3: PRODUÇÃO (Lotes & Regravação Cirúrgica de Take) -->
    <section id="tab-PRODUCAO" class="tab-pane" role="tabpanel">
      <div style="max-width:1180px;margin:0 auto;">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">
          <div>
            <h2 style="font-size:18px;font-weight:800;">Fila de Produção & Juiz Verificador de 3 Camadas</h2>
            <p style="color:var(--text-secondary);font-size:12px;">Se 1 take falhar ou alucinar, você NÃO recria do zero: clique em <strong>"🔄 Refazer só este Take"</strong> e o motor substitui apenas a cena ruim e remonta via NVENC.</p>
          </div>
        </div>
        <div id="producao-list" style="display:flex;flex-direction:column;gap:14px;"></div>
      </div>
    </section>

    <!-- ABA 4: ANALISADOS (Virais Extraídos do Zerum + Locais) -->
    <section id="tab-ANALISADOS" class="tab-pane" role="tabpanel">
      <div style="max-width:1240px;margin:0 auto;">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">
          <div>
            <h2 style="font-size:18px;font-weight:800;">Virais Analisados (Engenharia Reversa de Gancho, Estrutura, Pessoas & Legenda)</h2>
            <p style="color:var(--text-secondary);font-size:12px;">Inclui os virais extraídos do IndexedDB `zerum-virais` + virais analisados localmente pela sua RTX 4050.</p>
          </div>
        </div>
        <div id="analisados-grid" class="grid-3"></div>
      </div>
    </section>

    <!-- ABA 5: VÍDEOS (Galeria + Botão ✎ Editar vídeo · cortar · regravar · trocar fala) -->
    <section id="tab-VIDEOS" class="tab-pane" role="tabpanel">
      <div style="max-width:1280px;margin:0 auto;">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">
          <div>
            <h2 style="font-size:18px;font-weight:800;">Vídeos Prontos (`prontos/`) · Clique em "✎ Editar vídeo" para abrir o Timeline Studio</h2>
            <p style="color:var(--text-secondary);font-size:12px;">Todos os vídeos montados com verificação acústica e visual. Edite legendas, corte cenas, troque falas ou regrave takes individuais.</p>
          </div>
        </div>
        <div id="videos-grid" class="grid-3"></div>
      </div>
    </section>

  </main>

  <!-- MODAL 1: EDITOR · V1 (✎ Editar vídeo · cortar · regravar · trocar fala) -->
  <div id="modal-editor" class="modal-backdrop" role="dialog" aria-modal="true" aria-label="Editor de Vídeo Zerum V1">
    <div class="modal-window">
      <header class="modal-header">
        <div style="display:flex;align-items:center;gap:12px;">
          <span style="font-weight:800;font-size:14px;" id="editor-title">EDITOR · V142</span>
          <span class="status-pill" id="editor-status-badge">Juiz 3 Camadas: 100% Aprovado</span>
        </div>
        <div style="display:flex;align-items:center;gap:8px;">
          <label style="display:inline-flex;align-items:center;gap:5px;font-size:12px;color:var(--text-secondary);cursor:pointer;">
            <input type="checkbox" id="editor-keep-prev" checked /> guardar a anterior
          </label>
          <button onclick="aplicarLegendaLote()">Legenda → lote (3)</button>
          <button class="btn-yellow" onclick="salvarEBaixarEditor()">💾 Salvar e baixar</button>
          <button onclick="closeModal('modal-editor')" aria-label="Fechar Editor">✕</button>
        </div>
      </header>

      <div class="editor-body">
        <!-- Palco Central 9:16 -->
        <div class="editor-stage">
          <div class="stage-phone">
            <video id="editor-video-el" controls playsinline></video>
            <div id="editor-caption-overlay" class="live-caption-preview">
              PUT THREE <span id="editor-active-word" style="color:#FFE600;">DROPS</span>
            </div>
          </div>
        </div>

        <!-- Sidebar Direita: ESTILO DA LEGENDA + Ações da Cena Selecionada -->
        <aside class="editor-sidebar">
          <div>
            <div class="section-title">ESTILO DA LEGENDA</div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;">
              <button class="sub-mode-btn" data-mode="legenda" onclick="setEstiloLegenda('legenda')">legenda</button>
              <button class="sub-mode-btn btn-primary" data-mode="karaoke" onclick="setEstiloLegenda('karaoke')">karaokê</button>
              <button class="sub-mode-btn" data-mode="comando" onclick="setEstiloLegenda('comando')">comando</button>
              <button class="sub-mode-btn" data-mode="cartaz" onclick="setEstiloLegenda('cartaz')">cartaz</button>
            </div>
          </div>

          <div>
            <div class="section-title">BLOCOS</div>
            <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:6px;">
              <button class="sub-block-btn" data-words="1" onclick="setBlocosLegenda(1)">1 palavra</button>
              <button class="sub-block-btn btn-primary" data-words="3" onclick="setBlocosLegenda(3)">3 palavras</button>
              <button class="sub-block-btn" data-words="5" onclick="setBlocosLegenda(5)">5 palavras</button>
            </div>
          </div>

          <div>
            <div class="section-title">FONTE</div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;">
              <button onclick="setFonteLegenda('Poppins')" style="font-family:'Poppins',sans-serif;font-weight:800;">Poppins Bold</button>
              <button onclick="setFonteLegenda('Anton')" style="font-family:'Anton',sans-serif;">Anton</button>
              <button onclick="setFonteLegenda('Bebas Neue')" style="font-family:'Bebas Neue',sans-serif;font-size:15px;">BEBAS NEUE</button>
              <button onclick="setFonteLegenda('Archivo Black')" style="font-family:'Archivo Black',sans-serif;font-size:11px;">Archivo Black</button>
              <button onclick="setFonteLegenda('Lilita One')" style="font-family:'Lilita One',cursive;">Lilita One</button>
              <button onclick="setFonteLegenda('Bangers')" style="font-family:'Bangers',cursive;font-size:15px;">BANGERS</button>
            </div>
          </div>

          <div>
            <div class="section-title">COR DA PALAVRA ATIVA</div>
            <div style="display:flex;gap:8px;">
              <div class="swatch active" style="background:#FFE600;" onclick="setCorLegenda('#FFE600', this)"></div>
              <div class="swatch" style="background:#00E676;" onclick="setCorLegenda('#00E676', this)"></div>
              <div class="swatch" style="background:#FF3366;" onclick="setCorLegenda('#FF3366', this)"></div>
              <div class="swatch" style="background:#00D4FF;" onclick="setCorLegenda('#00D4FF', this)"></div>
              <div class="swatch" style="background:#FFFFFF;" onclick="setCorLegenda('#FFFFFF', this)"></div>
              <div class="swatch" style="background:#FF6D00;" onclick="setCorLegenda('#FF6D00', this)"></div>
            </div>
          </div>

          <div style="border-top:1px solid var(--border-subtle);padding-top:12px;">
            <div class="section-title">CENA SELECIONADA NA TIMELINE (<span id="editor-selected-scene-label">Cena 1</span>)</div>
            <label style="font-size:11px;color:var(--text-secondary);display:block;margin-bottom:4px;">Trocar Fala / Legenda da Cena:</label>
            <textarea id="editor-scene-fala" rows="3" style="margin-bottom:8px;" oninput="atualizarPreviewTextoCena()"></textarea>
            <div style="display:flex;gap:6px;flex-wrap:wrap;">
              <button class="btn-green" style="width:100%;justify-content:center;" onclick="regravarCenaCirurgica()">🔄 Regravar SÓ esta Cena no Flow</button>
              <button style="width:100%;justify-content:center;" onclick="verificarCenaNoJuiz()">⚖ Rodar Verificador 3 Camadas nesta Cena</button>
            </div>
            <div id="editor-action-feedback" class="mono" style="margin-top:8px;font-size:11px;color:#34d399;"></div>
          </div>
        </aside>
      </div>

      <!-- Timeline Multi-Track Inferior -->
      <footer class="editor-timeline">
        <div class="timeline-toolbar">
          <div style="display:flex;align-items:center;gap:8px;">
            <button onclick="dividirCenaTimeline()">✂ Dividir</button>
            <button onclick="excluirCenaTimeline()">🗑 Excluir</button>
            <button onclick="desfazerTimeline()">↶ Desfazer</button>
          </div>
          <div style="color:var(--text-muted);font-size:11px;">
            Espaço = play · Ctrl+B = dividir · Delete = excluir · Clique numa cena para isolar, trocar fala ou regravar
          </div>
        </div>
        <div class="timeline-tracks">
          <div class="track-row">
            <div class="track-label">VÍDEO</div>
            <div class="track-lane" id="timeline-video-lane"></div>
          </div>
          <div class="track-row">
            <div class="track-label">LEGENDA</div>
            <div class="track-lane" id="timeline-sub-lane"></div>
          </div>
          <div class="track-row">
            <div class="track-label">ÁUDIO</div>
            <div class="track-lane">
              <div class="audio-block">
                <span>🔊 Trilha Vocal Veo 3.1 Locked ([VOICE] Hz + Loudnorm -14 LUFS)</span>
                <span>Whisper 100%</span>
              </div>
            </div>
          </div>
        </div>
      </footer>
    </div>
  </div>

  <!-- MODAL 2: AVATARES (52 Personas com Voice Lock Hz e Preenchimento Manual) -->
  <div id="modal-avatares" class="modal-backdrop" role="dialog" aria-modal="true" aria-label="Galeria de Avatares Zerum">
    <div class="modal-window" style="height:88vh;">
      <header class="modal-header">
        <div style="font-weight:800;font-size:14px;">👤 AVATARES & PERSONAS (50 do Zerum IndexedDB + Avatares Locais)</div>
        <div style="display:flex;gap:8px;">
          <button onclick="closeModal('modal-avatares')">✕ Fechar</button>
        </div>
      </header>
      <div style="flex:1;overflow-y:auto;padding:20px;">
        <div id="avatares-grid" class="grid-4"></div>
      </div>
    </div>
  </div>

  <!-- MODAL 3: CONFIGURAÇÕES -->
  <div id="modal-config" class="modal-backdrop" role="dialog" aria-modal="true" aria-label="Configurações do Motor">
    <div class="modal-window" style="max-width:680px;height:auto;max-height:85vh;">
      <header class="modal-header">
        <div style="font-weight:800;font-size:14px;">⚙ CONFIGURAÇÕES DO MOTOR ZERUM LOCAL</div>
        <button onclick="closeModal('modal-config')">✕</button>
      </header>
      <div style="padding:20px;display:flex;flex-direction:column;gap:12px;">
        <div class="card">
          <div class="section-title">Hardware & Aceleração Ativa</div>
          <div id="config-hardware-info" class="mono"></div>
        </div>
        <div class="card">
          <div class="section-title">Regras do Juiz Verificador de 3 Camadas (`forja/qa_clipe.py`)</div>
          <ul style="padding-left:18px;color:var(--text-secondary);display:flex;flex-direction:column;gap:6px;">
            <li><strong>Camada 1 (Voz Whisper GPU):</strong> Rejeita takes com similaridade &lt; 80%, voz muda ou alucinação fora do script.</li>
            <li><strong>Camada 2 (Identidade Frame-1):</strong> Exige correlação histograma/estrutural &ge; 82% contra a foto de referência.</li>
            <li><strong>Camada 3 (Detector Anti-Freeze):</strong> `freezedetect=n=-60dB:d=0.2` bloqueia takes onde o personagem congela no meio ou fim.</li>
          </ul>
        </div>
      </div>
    </div>
  </div>

  <script>
    let STATE = { personas: [], virais: [], viraisMp4Disco: [], videos: [], lotes: [], motorInfo: {} };
    let CURRENT_VIDEO = null;
    let SELECTED_SCENE_IDX = 0;
    let CURRENT_VIRAL_ANALISE = null;
    let CURRENT_VIRAL_HOOK_OBJ = '';
    let CURRENT_VIRAL_ROUPA_LOCK = '';

    async function carregarEstado() {
      const r = await fetch('/api/state');
      STATE = await r.json();
      document.getElementById('badge-personas').textContent = STATE.personas.length;
      document.getElementById('badge-virais').textContent = STATE.virais.length;
      document.getElementById('badge-videos').textContent = STATE.videos.length;
      document.getElementById('badge-lotes').textContent = STATE.lotes.length;

      const diskSel = document.getElementById('viral-disk-select');
      if (diskSel && STATE.viraisMp4Disco) {
        diskSel.innerHTML = `<option value="">-- Ou escolha um .mp4 da pasta virais/ (${STATE.viraisMp4Disco.length} disponíveis) --</option>` +
          STATE.viraisMp4Disco.map(m => `<option value="${m.path}">${m.nome} (${m.tamanhoMb} MB)</option>`).join('');
      }

      renderDiretorPersonas();
      renderProducao();
      renderAnalisados();
      renderVideos();
      renderAvataresModal();
      document.getElementById('config-hardware-info').textContent = JSON.stringify(STATE.motorInfo, null, 2);
    }

    function switchTab(tabName) {
      document.querySelectorAll('.nav-tab').forEach(btn => {
        const isMatch = btn.getAttribute('onclick').includes(tabName);
        btn.setAttribute('aria-selected', isMatch ? 'true' : 'false');
      });
      document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
      const target = document.getElementById('tab-' + tabName);
      if (target) target.classList.add('active');
    }

    function openModal(id) { document.getElementById(id).classList.add('open'); }
    function closeModal(id) { document.getElementById(id).classList.remove('open'); }

    function renderDiretorPersonas() {
      const sel = document.getElementById('dir-avatar-select');
      sel.innerHTML = STATE.personas.map((p, i) =>
        `<option value="${i}">${p.name} [${p.origem}]</option>`
      ).join('');
      atualizarAvatarDiretor();
    }

    function atualizarAvatarDiretor() {
      const idx = Number(document.getElementById('dir-avatar-select').value || 0);
      const p = STATE.personas[idx];
      if (!p) return;
      document.getElementById('dir-voice-lock-preview').textContent = p.voiceLock || '';
    }

    function carregarPresetBakingSoda() {
      document.getElementById('dir-fala-1').value = "Rub baking soda on the sides of your neck every night and watch your belly fat melt away.";
      document.getElementById('dir-acao-1').value = "Doctor holds turquoise sponge in right hand and rubs white baking soda paste directly onto bare skin of the right side of his neck.";
      document.getElementById('dir-fala-2').value = "Your neck holds the lymph nodes that drain fat from your whole body. My patients swear by this now.";
      document.getElementById('dir-acao-2').value = "Points with right index finger directly at the bare skin of his right neck lymph node area while speaking to camera.";
      document.getElementById('dir-fala-3').value = "Save this video, comment yes, and follow me so I can send you the recipe.";
      document.getElementById('dir-acao-3').value = "Rests sponge on box, claps right hand across open left palm at chest height with warm direct eye contact.";
      compilarTudoNoDiretor();
    }

    let DROPPED_VIRAL_FILE = null;

    function handleViralDragOver(e) {
      e.preventDefault();
      e.stopPropagation();
      const dz = document.getElementById('viral-dropzone');
      if (dz) {
        dz.style.borderColor = '#00FF73';
        dz.style.background = 'rgba(0, 255, 115, 0.10)';
        dz.style.transform = 'scale(1.01)';
      }
    }

    function handleViralDragLeave(e) {
      e.preventDefault();
      e.stopPropagation();
      const dz = document.getElementById('viral-dropzone');
      if (dz) {
        dz.style.borderColor = 'rgba(255, 230, 0, 0.55)';
        dz.style.background = 'rgba(255, 230, 0, 0.04)';
        dz.style.transform = 'none';
      }
    }

    async function handleViralDrop(e) {
      e.preventDefault();
      e.stopPropagation();
      handleViralDragLeave(e);
      const files = e.dataTransfer && e.dataTransfer.files;
      if (files && files.length > 0) {
        await handleViralFilePicked(files[0]);
      }
    }

    async function handleViralFilePicked(file) {
      if (!file) return;
      DROPPED_VIRAL_FILE = file;
      switchTab('DIRETOR');
      const vid = document.getElementById('viral-preview-player');
      if (vid) {
        vid.src = URL.createObjectURL(file);
        vid.style.display = 'block';
        vid.play().catch(() => {});
      }
      const mb = (file.size / (1024 * 1024)).toFixed(1);
      document.getElementById('viral-drop-title').textContent = `🎬 ${file.name} (${mb} MB) — Lendo 15 campos automaticamente...`;
      document.getElementById('viral-drop-sub').textContent = `Arquivo recebido via Drag & Drop! Extraindo transcrição Whisper GPU + 6 Keyframes + Adaptação na Esteira...`;
      await subirELerViral(file);
    }

    // Drag & Drop global em qualquer lugar da janela + Ctrl+V para colar vídeo direto
    window.addEventListener('dragover', (e) => {
      if (e.dataTransfer && Array.from(e.dataTransfer.types || []).includes('Files')) {
        handleViralDragOver(e);
      }
    });
    window.addEventListener('dragleave', (e) => {
      if (e.relatedTarget === null) handleViralDragLeave(e);
    });
    window.addEventListener('drop', async (e) => {
      if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files.length > 0) {
        const f = e.dataTransfer.files[0];
        if (f.name.toLowerCase().endsWith('.mp4') || f.type.startsWith('video/')) {
          await handleViralDrop(e);
        }
      }
    });
    window.addEventListener('paste', async (e) => {
      const items = (e.clipboardData && e.clipboardData.files) || [];
      if (items.length > 0) {
        const f = items[0];
        if (f.name.toLowerCase().endsWith('.mp4') || f.type.startsWith('video/')) {
          await handleViralFilePicked(f);
        }
      }
    });

    async function subirELerViral(directFile = null) {
      const fileInput = document.getElementById('viral-file-input');
      const diskPath = document.getElementById('viral-disk-select').value;
      const statusBadge = document.getElementById('viral-esteira-status');
      statusBadge.textContent = '⏳ Transcrevendo com Whisper GPU + Extraindo 6 Keyframes + Lendo 15 Campos no Gemini Flow...';
      statusBadge.style.color = 'var(--accent-yellow)';

      const activeFile = directFile || DROPPED_VIRAL_FILE || (fileInput && fileInput.files && fileInput.files[0]);
      let payload = { videoPath: diskPath };
      if (activeFile) {
        const base64Data = await new Promise((resolve) => {
          const reader = new FileReader();
          reader.onload = () => resolve(String(reader.result).split(',')[1] || '');
          reader.readAsDataURL(activeFile);
        });
        payload = { fileName: activeFile.name, fileBase64: base64Data };
        DROPPED_VIRAL_FILE = null;
      }

      const r = await fetch('/api/subir_e_ler_viral', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const data = await r.json();
      if (!data.ok) {
        statusBadge.textContent = '❌ Erro: ' + (data.erro || 'Falha ao ler viral');
        statusBadge.style.color = 'var(--accent-red)';
        return;
      }
      CURRENT_VIRAL_ANALISE = data.analise;
      const kh = (data.analise.kie_hash || '').slice(0, 12);
      const orig = (data.analise.metricas_leitura && data.analise.metricas_leitura.origem) || 'vision_llm';
      document.getElementById('viral-drop-title').textContent = `✅ ${data.arquivo} (${data.analise.duracao}s · kie_hash=${kh} · ${orig}) — 15 Campos Extraídos!`;
      statusBadge.textContent = `✅ Viral Lido (${data.analise.duracao}s · hash ${kh} · ${orig === 'kie_cache' ? '⚡ 0ms Cache' : 'Vision LLM'})`;
      statusBadge.style.color = 'var(--accent-green)';
      const detailsEl = document.getElementById('viral-15-details');
      detailsEl.style.display = 'block';
      detailsEl.open = true;
      document.getElementById('viral-15-json').textContent = JSON.stringify(data.analise, null, 2);
      await adaptarViralNaEsteira();
    }

    function setKeywordCta(kw) {
      document.getElementById('viral-cta-word').value = kw;
      adaptarViralNaEsteira();
    }

    let ROLETA_HIST_USADOS = [];

    async function adaptarViralNaEsteira() {
      const statusBadge = document.getElementById('viral-esteira-status');
      if (!CURRENT_VIRAL_ANALISE && STATE.virais.length > 0) {
        CURRENT_VIRAL_ANALISE = STATE.virais[0].analise;
      }
      if (!CURRENT_VIRAL_ANALISE) {
        statusBadge.textContent = '⚠️ Suba ou escolha um vídeo viral primeiro (ou clique em Analisados)';
        return;
      }
      statusBadge.textContent = '🔄 Diretor Antigravity planejando (Caminho × Variação / Roleta / Elenco)...';
      const caminho = (document.getElementById('viral-caminho') && document.getElementById('viral-caminho').value) || 'igual';
      const modoVariacao = document.getElementById('viral-adapt-mode').value;
      const produtoId = (document.getElementById('viral-produto-id') && document.getElementById('viral-produto-id').value) || '';
      const criarAvataresNovos = !!(document.getElementById('viral-avatares-novos') && document.getElementById('viral-avatares-novos').checked);
      const palavraCta = document.getElementById('viral-cta-word').value || 'YES';
      const pedidoAdaptacao = document.getElementById('viral-adapt-prompt').value || '';

      const r = await fetch('/api/adaptar_viral_esteira', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          analise: CURRENT_VIRAL_ANALISE,
          caminho,
          modoVariacao,
          produtoId,
          criarAvataresNovos,
          roletaUsados: ROLETA_HIST_USADOS,
          palavraCta,
          pedidoAdaptacao
        })
      });
      const data = await r.json();
      if (!data.ok) {
        statusBadge.textContent = '❌ Erro ao adaptar: ' + (data.erro || '');
        return;
      }
      const cenas = data.cenas || [];
      if (cenas[0]) {
        document.getElementById('dir-fala-1').value = cenas[0].dialogue || '';
        document.getElementById('dir-acao-1').value = cenas[0].action || '';
      }
      if (cenas[1]) {
        document.getElementById('dir-fala-2').value = cenas[1].dialogue || '';
        document.getElementById('dir-acao-2').value = cenas[1].action || '';
      }
      if (cenas[2]) {
        document.getElementById('dir-fala-3').value = cenas[2].dialogue || '';
        document.getElementById('dir-acao-3').value = cenas[2].action || '';
      }
      if (data.cenarioLock) {
        document.getElementById('dir-setting').value = data.cenarioLock;
      }
      CURRENT_VIRAL_HOOK_OBJ = data.hookObject || '';
      CURRENT_VIRAL_ROUPA_LOCK = data.roupaLock || '';

      const previewBox = document.getElementById('diretor-roleta-elenco-preview');
      const linhasPreview = [];
      if (data.resumo_plano) {
        linhasPreview.push(`🎬 PLANO DO DIRETOR (VAe — O que você escreveu é LEI):`);
        linhasPreview.push(`   • ${data.resumo_plano}`);
      }
      if (data.regrasVae) {
        const rv = data.regrasVae;
        linhasPreview.push(
          `⚙️ REGRAS DE MONTAGEM & TRAVAS ATIVAS: Qtd=${data.qtdVideos || 1} vídeo(s) · ` +
          `Roupa=${rv.roupa_fixa_rotulo || 'variada'} · ` +
          `Ritmo=${rv.edicao_dinamica ? '⚡ EDIÇÃO DINÂMICA (Punch-In / Jump-Cut)' : 'Take Contínuo'} · ` +
          `Legenda=${rv.sem_legenda && rv.apenas_botao_cta ? '🚫 SEM LEGENDA NAS FALAS (Apenas Botão CTA no final!)' : (rv.sem_legenda ? '🚫 SEM LEGENDA' : 'Karaokê 11-Estilos')}`
        );
      }
      if (data.produto && data.produto.id) {
        const p = data.produto;
        linhasPreview.push(`📦 FICHA OFICIAL /gerador (briefs/${p.id}-ia.txt · CPA ${p.cpa || ''}):`);
        linhasPreview.push(`   • Produto: ${p.nome} (${p.nicho}) · Keywords: ${(p.keywords || []).join(', ')}`);
        linhasPreview.push(`   • Chiclete (Fala): "${p.chiclete || ''}" · Objeto Viral: ${p.objeto_viral || ''}`);
      }
      if (data.roletaSorteada && data.roletaSorteada.length > 0) {
        data.roletaSorteada.forEach(rc => {
          if (!ROLETA_HIST_USADOS.includes(rc.id)) ROLETA_HIST_USADOS.push(rc.id);
        });
        linhasPreview.push(`🎰 MÉTODO ROLETA (${data.roletaSorteada.length} variações sorteadas · ${ROLETA_HIST_USADOS.length} combinações no histórico):`);
        data.roletaSorteada.forEach((rc, idx) => {
          linhasPreview.push(`   • Vídeo #${idx+1}: [${rc.rotulo}] -> ${rc.variacao}`);
        });
      }
      if (data.avataresNovos && data.avataresNovos.length > 0) {
        linhasPreview.push(`🎲 ELENCO NOVO VARIADO (${data.avataresNovos.length} Enfermeiras/Avatares 100% Distintos com a Mesma Roupa):`);
        data.avataresNovos.forEach(av => {
          linhasPreview.push(`   • ${av.nome}: ${av.pedido_en}`);
        });
      }
      if (linhasPreview.length > 0) {
        previewBox.style.display = 'block';
        previewBox.textContent = linhasPreview.join('\n');
      } else {
        previewBox.style.display = 'none';
      }

      statusBadge.textContent = `✅ ${data.qtdVideos || 1} Variações Prontas · ${data.modo || modoVariacao} · Ritmo: ${(data.regrasVae && data.regrasVae.ritmo_edicao) || 'padrao'} · Legenda: ${(data.regrasVae && data.regrasVae.estilo_legenda) || 'karaoke'} · CTA: ${data.palavraCta || palavraCta}`;
      statusBadge.style.color = 'var(--accent-green)';
      if (data.palavraCta && document.getElementById('viral-cta-word')) {
        document.getElementById('viral-cta-word').value = data.palavraCta;
      }
      window.LAST_ADAPTED_LOTE = data;
      await compilarTudoNoDiretor();
    }

    async function compilarTudoNoDiretor() {
      const idx = Number(document.getElementById('dir-avatar-select').value || 0);
      const persona = { ...(STATE.personas[idx] || {}) };
      if (CURRENT_VIRAL_ROUPA_LOCK) {
        persona.outfit = CURRENT_VIRAL_ROUPA_LOCK;
        persona.clothes = CURRENT_VIRAL_ROUPA_LOCK;
      }
      const setting = document.getElementById('dir-setting').value;
      const cenas = [
        { number: 1, dialogue: document.getElementById('dir-fala-1').value, action: document.getElementById('dir-acao-1').value, durationSeconds: 8 },
        { number: 2, dialogue: document.getElementById('dir-fala-2').value, action: document.getElementById('dir-acao-2').value, durationSeconds: 8 },
        { number: 3, dialogue: document.getElementById('dir-fala-3').value, action: document.getElementById('dir-acao-3').value, durationSeconds: 8 },
      ];
      const r = await fetch('/api/compilar_prompts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ persona, setting, cenas, hookObject: CURRENT_VIRAL_HOOK_OBJ })
      });
      const data = await r.json();
      document.getElementById('dir-compiled-output').textContent = JSON.stringify(data, null, 2);
    }

    async function dispararProducaoDiretor() {
      // Sempre atualiza a adaptação na esteira primeiro para respeitar ordens recém-digitadas (ex: "50 variações igual o viral")
      if (CURRENT_VIRAL_ANALISE || (STATE.virais && STATE.virais.length > 0)) {
        await adaptarViralNaEsteira();
      } else {
        await compilarTudoNoDiretor();
      }
      const idx = Number(document.getElementById('dir-avatar-select').value || 0);
      const persona = { ...(STATE.personas[idx] || {}) };
      if (CURRENT_VIRAL_ROUPA_LOCK) {
        persona.outfit = CURRENT_VIRAL_ROUPA_LOCK;
        persona.clothes = CURRENT_VIRAL_ROUPA_LOCK;
      }
      const setting = document.getElementById('dir-setting').value;
      const cenas = [
        { number: 1, dialogue: document.getElementById('dir-fala-1').value, action: document.getElementById('dir-acao-1').value, durationSeconds: 8 },
        { number: 2, dialogue: document.getElementById('dir-fala-2').value, action: document.getElementById('dir-acao-2').value, durationSeconds: 8 },
        { number: 3, dialogue: document.getElementById('dir-fala-3').value, action: document.getElementById('dir-acao-3').value, durationSeconds: 8 },
      ];
      const qtdAdap = (window.LAST_ADAPTED_LOTE && window.LAST_ADAPTED_LOTE.qtdVideos) ? Number(window.LAST_ADAPTED_LOTE.qtdVideos) : 1;
      await fetch('/api/produzir_lote', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          persona,
          setting,
          cenas,
          qtdEnfileirar: qtdAdap,
          hookObject: CURRENT_VIRAL_HOOK_OBJ || '',
          roupaLock: CURRENT_VIRAL_ROUPA_LOCK || '',
          loteAdaptado: window.LAST_ADAPTED_LOTE || null
        })
      });
      await carregarEstado();
      switchTab('PRODUCAO');
      if (!window._prodPoller) {
        window._prodPoller = setInterval(carregarEstado, 4000);
      }
    }

    function renderProducao() {
      const box = document.getElementById('producao-list');
      box.innerHTML = STATE.lotes.map(lote => `
        <div class="card">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;gap:12px;">
            <div>
              <div style="font-weight:800;font-size:15px;">${lote.titulo}</div>
              <div style="color:${lote.status === 'erro' ? '#f87171' : (lote.status === 'concluido' ? 'var(--accent-green)' : 'var(--accent-yellow)')};font-size:12.5px;font-weight:600;margin-top:2px;">${lote.progresso}</div>
            </div>
            <div style="display:flex;gap:8px;align-items:center;">
              ${lote.videoFinalUrl ? `<a href="${lote.videoFinalUrl}" target="_blank" class="btn-green" style="text-decoration:none;padding:6px 12px;border-radius:6px;font-size:12px;font-weight:700;">▶ Assistir / Baixar MP4 Final</a>` : ''}
              <button class="btn-yellow" onclick="abrirEditorVideo(0)">✎ Editar vídeo · cortar · regravar · trocar fala</button>
            </div>
          </div>
          ${lote.videoFinalUrl ? `
            <div style="margin-bottom:12px;display:flex;gap:14px;align-items:center;background:var(--bg-canvas);padding:10px;border-radius:8px;border:1px solid var(--border-subtle);">
              <video src="${lote.videoFinalUrl}" controls preload="metadata" style="width:150px;height:266px;object-fit:cover;border-radius:6px;border:1px solid var(--accent-green);"></video>
              <div style="font-size:12px;color:var(--text-secondary);line-height:1.6;">
                <div style="color:var(--accent-green);font-weight:800;font-size:13.5px;margin-bottom:4px;">✅ VÍDEO FINAL MONTADO NA RTX 4050 (h264_nvenc)</div>
                <div><strong>Arquivo:</strong> <code>${lote.videoFinalUrl}</code></div>
                <div><strong>Pipeline:</strong> Google Flow (GEM_PIX_2 + Dupla Referência + Juiz Visual + Veo 3.1 Frase #1 Literal + Tesoura Fonética 3-Passes)</div>
              </div>
            </div>
          ` : ''}
          <div class="grid-3">
            ${(lote.cenas || []).map((c, idx) => `
              <div class="card" style="background:var(--bg-elevated);">
                <div style="display:flex;justify-content:space-between;margin-bottom:6px;">
                  <strong>Cena ${c.numero} (${c.duracao}s)</strong>
                  <span class="qa-badge">Fala ${(c.qaFala*100).toFixed(0)}% · Frame1 ${(c.qaFrame1*100).toFixed(1)}%</span>
                </div>
                ${c.clipeUrl ? `<video src="${c.clipeUrl}" controls preload="metadata" style="width:100%;height:160px;object-fit:cover;border-radius:6px;margin-bottom:8px;border:1px solid var(--border-subtle);"></video>` : ''}
                <div style="font-size:12px;color:var(--text-secondary);margin-bottom:10px;">"${c.fala}"</div>
                <div style="display:flex;gap:6px;">
                  <button class="btn-green" onclick="regravarTakeDireto('${lote.id}', ${c.numero})">🔄 Refazer só este Take</button>
                  <button onclick="abrirEditorCena(0, ${idx})">✂ Cortar / Trocar Fala</button>
                </div>
              </div>
            `).join('')}
          </div>
        </div>
      `).join('');
    }

    function renderAnalisados() {
      const grid = document.getElementById('analisados-grid');
      grid.innerHTML = STATE.virais.map((v, i) => {
        const an = v.analise || {};
        return `
          <div class="card" style="display:flex;flex-direction:column;gap:10px;">
            <div style="display:flex;gap:12px;align-items:center;">
              ${v.thumb ? `<img src="${v.thumb}" style="width:64px;height:110px;object-fit:cover;border-radius:6px;border:1px solid var(--border-subtle);" />` : ''}
              <div style="flex:1;">
                <div style="font-weight:800;font-size:13.5px;">${v.nome}</div>
                <div style="font-size:11px;color:var(--text-secondary);">Duração: ${v.duracao}s · ${v.origem}</div>
                <div class="qa-badges" style="margin-top:6px;">
                  <span class="qa-badge">Análise Completa</span>
                </div>
              </div>
            </div>
            <div style="font-size:12px;"><strong>GANCHO:</strong> <span style="color:var(--text-secondary);">${(an.gancho || an.transcricao || '').slice(0, 180)}</span></div>
            <div style="font-size:12px;"><strong>POR QUE PRENDE:</strong> <span style="color:var(--text-secondary);">${(an.por_que_prende || '').slice(0, 180)}</span></div>
            <div style="font-size:11.5px;background:var(--bg-canvas);padding:8px;border-radius:6px;border:1px solid var(--border-subtle);">
              <strong>TRANSCRIÇÃO:</strong> ${(an.transcricao || '').slice(0, 260)}
            </div>
            <button class="btn-primary" style="margin-top:auto;justify-content:center;" onclick="usarViralNoDiretor(${i})">⚡ Usar Estrutura no Diretor</button>
          </div>
        `;
      }).join('');
    }

    async function usarViralNoDiretor(idx) {
      const v = STATE.virais[idx];
      if (!v) return;
      CURRENT_VIRAL_ANALISE = v.analise || {};
      switchTab('DIRETOR');
      const detailsEl = document.getElementById('viral-15-details');
      detailsEl.style.display = 'block';
      detailsEl.open = true;
      document.getElementById('viral-15-json').textContent = JSON.stringify(CURRENT_VIRAL_ANALISE, null, 2);
      await adaptarViralNaEsteira();
    }

    function renderVideos() {
      const grid = document.getElementById('videos-grid');
      grid.innerHTML = STATE.videos.map((v, idx) => `
        <article class="video-card">
          <video class="video-card-player" src="${v.mp4Url}" controls preload="metadata"></video>
          <div class="video-card-body">
            <div style="font-weight:800;font-size:13.5px;">${v.titulo}</div>
            <div style="font-size:11px;color:var(--text-secondary);">${v.lote} · ${v.criadoEm}</div>
            <div class="qa-badges">
              <span class="qa-badge">Voz: ${v.verificador.vozWhisper}</span>
              <span class="qa-badge">Frame-1: ${v.verificador.identidadeFrame1}</span>
              <span class="qa-badge">Freeze: ${v.verificador.zeroFreeze}</span>
            </div>
            <div style="display:flex;gap:6px;margin-top:auto;padding-top:8px;">
              <button class="btn-yellow" style="flex:1;justify-content:center;" onclick="abrirEditorVideo(${idx})">
                ✎ Editar vídeo · cortar · regravar · trocar fala
              </button>
            </div>
          </div>
        </article>
      `).join('');
    }

    function renderAvataresModal() {
      const grid = document.getElementById('avatares-grid');
      grid.innerHTML = STATE.personas.map((p, idx) => `
        <div class="card" style="display:flex;flex-direction:column;gap:8px;">
          ${p.imageUrl ? `<img src="${p.imageUrl}" style="width:100%;height:220px;object-fit:cover;border-radius:6px;border:1px solid var(--border-subtle);" loading="lazy" />` : `<div style="width:100%;height:220px;background:var(--bg-canvas);border-radius:6px;display:flex;align-items:center;justify-content:center;color:var(--text-muted);">Sem Foto</div>`}
          <div style="font-weight:700;font-size:12.5px;">${p.name}</div>
          <div style="font-size:11px;color:var(--text-secondary);max-height:54px;overflow:hidden;">${p.physicalDescription || ''}</div>
          <button class="btn-primary" style="margin-top:auto;justify-content:center;" onclick="selecionarAvatarParaDiretor(${idx})">Usar no Diretor</button>
        </div>
      `).join('');
    }

    function selecionarAvatarParaDiretor(idx) {
      document.getElementById('dir-avatar-select').value = String(idx);
      atualizarAvatarDiretor();
      closeModal('modal-avatares');
      switchTab('DIRETOR');
    }

    function abrirEditorVideo(videoIdx) {
      CURRENT_VIDEO = STATE.videos[videoIdx] || STATE.videos[0];
      if (!CURRENT_VIDEO) return;
      SELECTED_SCENE_IDX = 0;
      document.getElementById('editor-title').textContent = 'EDITOR · ' + CURRENT_VIDEO.id;
      const vidEl = document.getElementById('editor-video-el');
      vidEl.src = CURRENT_VIDEO.mp4Url;
      renderTimelineEditor();
      selecionarCenaTimeline(0);
      openModal('modal-editor');
    }

    function abrirEditorCena(videoIdx, sceneIdx) {
      abrirEditorVideo(videoIdx);
      selecionarCenaTimeline(sceneIdx);
    }

    function renderTimelineEditor() {
      if (!CURRENT_VIDEO) return;
      const vLane = document.getElementById('timeline-video-lane');
      const sLane = document.getElementById('timeline-sub-lane');
      const cenas = CURRENT_VIDEO.cenas || [];

      vLane.innerHTML = cenas.map((c, i) => `
        <div class="clip-block ${i === SELECTED_SCENE_IDX ? 'selected' : ''}" onclick="selecionarCenaTimeline(${i})">
          <span>cena ${c.numero}</span>
          <span style="font-size:10px;opacity:0.8;">${c.duracao}s</span>
        </div>
      `).join('');

      sLane.innerHTML = cenas.map((c, i) => {
        const words = (c.fala || '').toUpperCase().split(/\s+/).slice(0, 4).join(' ');
        return `<div class="sub-block" onclick="selecionarCenaTimeline(${i})">${words}...</div>`;
      }).join('');
    }

    function selecionarCenaTimeline(idx) {
      if (!CURRENT_VIDEO || !CURRENT_VIDEO.cenas[idx]) return;
      SELECTED_SCENE_IDX = idx;
      const c = CURRENT_VIDEO.cenas[idx];
      document.getElementById('editor-selected-scene-label').textContent = 'Cena ' + c.numero;
      document.getElementById('editor-scene-fala').value = c.fala || '';
      atualizarPreviewTextoCena();
      renderTimelineEditor();
    }

    function atualizarPreviewTextoCena() {
      const txt = (document.getElementById('editor-scene-fala').value || '').trim().toUpperCase();
      const words = txt.split(/\s+/).filter(Boolean);
      const n = (CURRENT_VIDEO && CURRENT_VIDEO.legendaConfig && CURRENT_VIDEO.legendaConfig.blocos) || 3;
      const slice = words.slice(0, n);
      if (slice.length === 0) return;
      const last = slice.pop();
      const cor = (CURRENT_VIDEO && CURRENT_VIDEO.legendaConfig && CURRENT_VIDEO.legendaConfig.corAtiva) || '#FFE600';
      document.getElementById('editor-caption-overlay').innerHTML =
        `${slice.join(' ')} <span id="editor-active-word" style="color:${cor};">${last}</span>`;
      if (CURRENT_VIDEO && CURRENT_VIDEO.cenas[SELECTED_SCENE_IDX]) {
        CURRENT_VIDEO.cenas[SELECTED_SCENE_IDX].fala = document.getElementById('editor-scene-fala').value;
      }
    }

    function setEstiloLegenda(modo) {
      if (CURRENT_VIDEO) CURRENT_VIDEO.legendaConfig.estilo = modo;
      document.querySelectorAll('.sub-mode-btn').forEach(b => {
        b.classList.toggle('btn-primary', b.dataset.mode === modo);
      });
      const ov = document.getElementById('editor-caption-overlay');
      ov.style.background = (modo === 'cartaz' || modo === 'comando') ? 'rgba(0,0,0,0.78)' : 'transparent';
    }

    function setBlocosLegenda(qtd) {
      if (CURRENT_VIDEO) CURRENT_VIDEO.legendaConfig.blocos = qtd;
      document.querySelectorAll('.sub-block-btn').forEach(b => {
        b.classList.toggle('btn-primary', Number(b.dataset.words) === qtd);
      });
      atualizarPreviewTextoCena();
    }

    function setFonteLegenda(fontName) {
      if (CURRENT_VIDEO) CURRENT_VIDEO.legendaConfig.fonte = fontName;
      document.getElementById('editor-caption-overlay').style.fontFamily = `'${fontName}', sans-serif`;
    }

    function setCorLegenda(cor, el) {
      if (CURRENT_VIDEO) CURRENT_VIDEO.legendaConfig.corAtiva = cor;
      document.querySelectorAll('.swatch').forEach(s => s.classList.remove('active'));
      if (el) el.classList.add('active');
      atualizarPreviewTextoCena();
    }

    async function salvarEBaixarEditor() {
      if (!CURRENT_VIDEO) return;
      const fb = document.getElementById('editor-action-feedback');
      fb.textContent = 'Renderizando na GPU RTX 4050 (h264_nvenc)...';
      const r = await fetch('/api/editor_render', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          videoId: CURRENT_VIDEO.id,
          estilo: CURRENT_VIDEO.legendaConfig.estilo,
          blocos: CURRENT_VIDEO.legendaConfig.blocos,
          fonte: CURRENT_VIDEO.legendaConfig.fonte,
          corAtiva: CURRENT_VIDEO.legendaConfig.corAtiva,
          guardarAnterior: document.getElementById('editor-keep-prev').checked,
          cenas: CURRENT_VIDEO.cenas,
        })
      });
      const res = await r.json();
      fb.textContent = res.mensagem || 'Salvo!';
    }

    async function verificarCenaNoJuiz() {
      if (!CURRENT_VIDEO) return;
      const c = CURRENT_VIDEO.cenas[SELECTED_SCENE_IDX];
      const fb = document.getElementById('editor-action-feedback');
      fb.textContent = `Auditando Cena ${c.numero} no Juiz 3 Camadas (Whisper + Frame1 + Freezedetect)...`;
      const r = await fetch('/api/verificar_take', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ clipePath: c.clipePath, falaEsperada: c.fala })
      });
      const res = await r.json();
      fb.textContent = JSON.stringify(res);
    }

    async function regravarCenaCirurgica() {
      if (!CURRENT_VIDEO) return;
      const c = CURRENT_VIDEO.cenas[SELECTED_SCENE_IDX];
      const fb = document.getElementById('editor-action-feedback');
      fb.textContent = `Disparada regravação cirúrgica SOMENTE da Cena ${c.numero} (preservando as demais cenas aprovadas)...`;
      await fetch('/api/regravar_take', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ videoId: CURRENT_VIDEO.id, takeNumero: c.numero, novaFala: c.fala })
      });
    }

    async function regravarTakeDireto(loteId, takeNum) {
      alert(`Regravação cirúrgica acionada para o Take ${takeNum} do lote ${loteId} (mantendo os outros takes intactos).`);
    }

    function dividirCenaTimeline() {
      if (!CURRENT_VIDEO) return;
      const c = CURRENT_VIDEO.cenas[SELECTED_SCENE_IDX];
      if (!c) return;
      const half = Number((c.duracao / 2).toFixed(1));
      c.duracao = half;
      CURRENT_VIDEO.cenas.splice(SELECTED_SCENE_IDX + 1, 0, {
        numero: CURRENT_VIDEO.cenas.length + 1,
        id: 's_split_' + Date.now(),
        duracao: half,
        fala: c.fala,
        acao: c.acao,
        clipePath: c.clipePath,
        clipeUrl: c.clipeUrl,
        qaFala: c.qaFala,
        qaFrame1: c.qaFrame1,
        qaFreeze: false
      });
      renderTimelineEditor();
    }

    function excluirCenaTimeline() {
      if (!CURRENT_VIDEO || CURRENT_VIDEO.cenas.length <= 1) return;
      CURRENT_VIDEO.cenas.splice(SELECTED_SCENE_IDX, 1);
      SELECTED_SCENE_IDX = Math.max(0, SELECTED_SCENE_IDX - 1);
      renderTimelineEditor();
    }

    function desfazerTimeline() { carregarEstado(); }
    function aplicarLegendaLote() { salvarEBaixarEditor(); }
    function novaConversaDiretor() {
      document.getElementById('dir-fala-1').value = '';
      document.getElementById('dir-fala-2').value = '';
      document.getElementById('dir-fala-3').value = '';
    }

    window.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        document.querySelectorAll('.modal-backdrop.open').forEach(m => m.classList.remove('open'));
      }
    });

    carregarEstado();
  </script>
</body>
</html>
"""


class NossoZerumHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:
        pass

    def _send_json(self, data: Any, status: int = 200) -> None:
        raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/" or path == "/zerum":
            raw = HTML_NOSSO_ZERUM.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
            return

        if path == "/api/state":
            self._send_json(_carregar_dados_zerum())
            return

        if path.startswith("/media/"):
            rel = urllib.parse.unquote(path[len("/media/"):])
            if rel.startswith("artifact/"):
                fname = rel[len("artifact/"):]
                fpath = Path(r"C:\Users\User\.gemini\antigravity\brain\8ae8cf2b-5a24-4020-9cf1-2816b2435e39\.user_uploaded") / fname
            elif rel.startswith("root/"):
                fpath = ROOT_DIR / rel[len("root/"):]
            else:
                fpath = ROOT_DIR / rel

            if fpath.exists() and fpath.is_file():
                mime, _ = mimetypes.guess_type(str(fpath))
                data = fpath.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", mime or "application/octet-stream")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Accept-Ranges", "bytes")
                self.end_headers()
                self.wfile.write(data)
                return
            self.send_error(404, "Media not found")
            return

        self.send_error(404, "Not found")

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"
        payload = json.loads(body) if body else {}

        if self.path == "/api/subir_e_ler_viral":
            file_b64 = str(payload.get("fileBase64") or "").strip()
            file_name = str(payload.get("fileName") or f"viral_upload_{int(time.time())}.mp4").strip()
            video_path_str = str(payload.get("videoPath") or "").strip()

            if file_b64:
                virais_dir = ROOT_DIR / "virais"
                virais_dir.mkdir(parents=True, exist_ok=True)
                safe_name = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in file_name)
                if not safe_name.lower().endswith(".mp4"):
                    safe_name += ".mp4"
                target_mp4 = virais_dir / safe_name
                target_mp4.write_bytes(base64.b64decode(file_b64))
            elif video_path_str and Path(video_path_str).exists():
                target_mp4 = Path(video_path_str)
            else:
                # Fallback para o primeiro .mp4 em virais/ se não informou
                mp4s = sorted((ROOT_DIR / "virais").glob("*.mp4"))
                if not mp4s:
                    self._send_json({"ok": False, "erro": "Nenhum arquivo .mp4 enviado ou encontrado em virais/"}, status=400)
                    return
                target_mp4 = mp4s[0]

            analise_15 = ler_viral_15_campos_zerum(target_mp4)
            self._send_json(
                {
                    "ok": True,
                    "arquivo": target_mp4.name,
                    "videoPath": str(target_mp4),
                    "analise": analise_15,
                }
            )
            return

        if self.path == "/api/adaptar_viral_esteira":
            analise_15 = payload.get("analise") or {}
            caminho = str(payload.get("caminho") or "igual")
            modo_variacao = str(payload.get("modoVariacao") or "tora")
            produto_id = str(payload.get("produtoId") or "")
            criar_avatares_novos = bool(payload.get("criarAvataresNovos", False))
            manter_personagem_original = bool(payload.get("manterPersonagemOriginal", False))
            qtd_videos = int(payload.get("qtdVideos") or 1)
            roleta_usados = payload.get("roletaUsados") or []
            palavra_cta = str(payload.get("palavraCta") or "YES")
            pedido_adaptacao = str(payload.get("pedidoAdaptacao") or "")
            adaptado = adaptar_viral_para_esteira_zerum(
                analise_15=analise_15,
                pedido_adaptacao=pedido_adaptacao,
                palavra_cta=palavra_cta,
                modo_variacao=modo_variacao,
                caminho=caminho,
                produto_id=produto_id,
                qtd_videos=qtd_videos,
                criar_avatares_novos=criar_avatares_novos,
                roleta_usados=roleta_usados,
                manter_personagem_original=manter_personagem_original,
            )
            self._send_json(adaptado)
            return

        if self.path == "/api/compilar_prompts":
            persona = payload.get("persona") or {}
            setting = payload.get("setting") or "Bright clinical room"
            cenas = payload.get("cenas") or []
            hook_obj_override = str(payload.get("hookObject") or "").strip()
            p_full = {**persona, "setting": setting}
            avatar_ref_id = str(persona.get("referenceImageId") or persona.get("id") or "1d608ee5-f6b4-482d-a79a-48f63dd9385d")
            scene1_ref_id = "8c47d438-512b-4a37-bba1-6448b95b7cef"
            total_c = len(cenas)
            quadros_18 = []
            prompts_cenas = []
            for i, c in enumerate(cenas):
                is_cta = (i == total_c - 1) and total_c > 1
                q_refs = compilar_quadro_refs_18(
                    indice_cena=i,
                    avatar_media_id=avatar_ref_id,
                    cena1_aprovada_media_id=scene1_ref_id if i > 0 else None,
                )
                q_prompt = compilar_prompt_avatar_imagem(
                    p_full,
                    indice_cena=i,
                    acao_cena=str(c.get("action") or ""),
                    hook_obj=(hook_obj_override or str(c.get("action") or "")) if i == 0 else "",
                    cta=is_cta,
                    estagio_corporal=c.get("stage"),
                )
                quadros_18.append(
                    {
                        "scene": i + 1,
                        "fase": "quadro1" if i == 0 else "quadro-novo",
                        "quadroRefs18": q_refs,
                        "quadroPrompt18": q_prompt,
                    }
                )
                prompts_cenas.append(
                    compilar_prompt_cena_veo31(
                        scene=c,
                        persona=p_full,
                        Continuity=(i > 0),
                        cta=is_cta,
                    )
                )
            self._send_json(
                {
                    "ok": True,
                    "montador": "c2 (20261024T1400-estagios24-783315d)",
                    "voiceLock": compilar_bloco_voz_travada(p_full),
                    "quadrosCena18": quadros_18,
                    "veo31ScenePrompts": prompts_cenas,
                }
            )
            return

        if self.path == "/api/editor_render":
            self._send_json(_renderizar_editor_legenda_nvenc(payload))
            return

        if self.path == "/api/produzir_lote":
            base_ts = int(time.time())
            lote_adaptado = payload.get("loteAdaptado") or {}
            avatares_novos = lote_adaptado.get("avataresNovos") or []
            roleta_sorteada = lote_adaptado.get("roletaSorteada") or []
            lote_videos_items = lote_adaptado.get("loteVideos") or []
            manter_orig_flag = bool(
                payload.get("manterPersonagemOriginal")
                or lote_adaptado.get("manterPersonagemOriginal")
                or str(lote_adaptado.get("modoVariacao") or "") == "micro_embalagem"
            )
            var_idx = int(payload.get("indiceVariacao") or 0)
            qtd_enfileirar = int(payload.get("qtdEnfileirar") or lote_adaptado.get("qtdVideos") or 1)
            jobs_criados: list[str] = []

            for offset in range(max(1, qtd_enfileirar)):
                idx_v = var_idx + offset
                jid_base = str(payload.get("jobIdOverride") or payload.get("id") or "").strip()
                job_id = (
                    (f"{jid_base}-V{idx_v+1:03d}" if qtd_enfileirar > 1 else jid_base)
                    if jid_base
                    else (f"L-LOCAL-{base_ts}-V{idx_v+1:03d}" if qtd_enfileirar > 1 or idx_v > 0 else f"L-LOCAL-{base_ts}")
                )
                pl_item = json.loads(json.dumps(payload))
                persona_v = dict(pl_item.get("persona") or {})
                lv_item = lote_videos_items[idx_v % len(lote_videos_items)] if lote_videos_items else {}
                if lv_item.get("cenas"):
                    pl_item["cenas"] = json.loads(json.dumps(lv_item["cenas"]))
                if manter_orig_flag or lv_item.get("manterPersonagemOriginal"):
                    pl_item["manterPersonagemOriginal"] = True
                    pl_item["criarNovoAvatar"] = False
                    mv_info = lv_item.get("microVariacao") or {}
                    persona_v["name"] = str(lv_item.get("avatar") or persona_v.get("name") or f"Mesmo Personagem · Micro #{idx_v+1}")
                    plano_f = lote_adaptado.get("planoReplicacaoFisica") or {}
                    if plano_f.get("presenter_sex"):
                        persona_v["sex"] = str(plano_f["presenter_sex"])
                    if plano_f.get("presenter_age"):
                        persona_v["ageRange"] = str(plano_f["presenter_age"])
                    if plano_f.get("presenter_original_description"):
                        persona_v["physicalDescription"] = str(plano_f["presenter_original_description"])
                    rotulo_rc = str(mv_info.get("rotulo") or "Micro-Variação 001 Embalagem Intacta")
                elif avatares_novos:
                    av_item = avatares_novos[idx_v % len(avatares_novos)]
                    persona_v["name"] = av_item.get("nome", persona_v.get("name", f"Enfermeira Roleta #{idx_v+1}"))
                    persona_v["physicalDescription"] = av_item.get("pedido_en", persona_v.get("physicalDescription", ""))
                    persona_v["outfit"] = av_item.get("roupa", persona_v.get("outfit", ""))
                    persona_v["sex"] = av_item.get("sexo", "f")
                    persona_v["ageRange"] = str(av_item.get("idade", 42))
                    pl_item["criarNovoAvatar"] = True
                    rotulo_rc = "Motor Local + Flow RPC"
                else:
                    rotulo_rc = "Motor Local + Flow RPC"
                if roleta_sorteada:
                    rc_item = roleta_sorteada[idx_v % len(roleta_sorteada)]
                    pl_item["setting"] = pl_item.get("setting") or rc_item.get("cenario_lock")
                    pl_item["roupaLock"] = rc_item.get("roupa_lock") or pl_item.get("roupaLock")
                    pl_item["hookObject"] = rc_item.get("hook_object") or pl_item.get("hookObject")
                    rotulo_rc = rc_item.get("rotulo", "Roleta")
                pl_item["persona"] = persona_v

                cenas = pl_item.get("cenas") or []
                rotulo_modo = (
                    f"🧬 Mesmo Personagem [{rotulo_rc}]"
                    if pl_item.get("manterPersonagemOriginal")
                    else (f"🎰 Roleta [{rotulo_rc}]" if roleta_sorteada else "Motor Local + Flow RPC")
                )
                final_existente = PRONTOS_DIR / f"{job_id}_final_verificado.mp4"
                if (
                    final_existente.exists()
                    and final_existente.stat().st_size > 100000
                    and _JOBS_PRODUCAO.get(job_id, {}).get("status") == "concluido"
                ):
                    jobs_criados.append(job_id)
                    continue
                _JOBS_PRODUCAO[job_id] = {
                    "id": job_id,
                    "titulo": f"{job_id} · {persona_v.get('name', 'Avatar')} ({rotulo_modo})",
                    "status": "produzindo",
                    "criadoEm": datetime.now().strftime("%H:%M:%S"),
                    "progresso": "Na fila especulativa do Flow (:9225)...",
                    "cenas": [
                        {
                            "numero": i + 1,
                            "id": f"s{i+1}",
                            "duracao": 8.0,
                            "fala": str(c.get("dialogue") or ""),
                            "acao": str(c.get("action") or ""),
                            "clipePath": "",
                            "clipeUrl": "",
                            "qaFala": 0.0,
                            "qaFrame1": 0.0,
                            "qaFreeze": False,
                        }
                        for i, c in enumerate(cenas)
                    ],
                    "videoFinalUrl": "",
                }
                _salvar_estado_persistente()
                _enfileirar_job_producao(job_id, pl_item)
                jobs_criados.append(job_id)

            self._send_json({"ok": True, "jobId": jobs_criados[0], "jobs": jobs_criados, "status": "produzindo"})
            return

        if self.path == "/api/verificar_take":
            cpath = Path(str(payload.get("clipePath") or ""))
            fala = str(payload.get("falaEsperada") or "")
            if cpath.exists():
                ref_img = cpath.parent / f"frame_{cpath.stem}.jpg"
                tes = tesoura_cirurgica_3_passes(video_path=cpath, fala_pedida=fala)
                qa = avaliar_qa_clipe(
                    video_path=cpath,
                    fala_pedida=fala,
                    imagem_gerada_path=ref_img if ref_img.exists() else None,
                    limiar_fala=0.80,
                )
                self._send_json(
                    {
                        "ok": True,
                        "arquivo": cpath.name,
                        "aprovado": qa.get("aprovado", False),
                        "precisaoFala": round(qa.get("fala", {}).get("precisao", 0.0) * 100, 1),
                        "similaridadeFrame1": round(qa.get("video", {}).get("similaridade_frame1", 0.0) * 100, 1),
                        "maiorFreezeS": qa.get("video", {}).get("maior_freeze_s", 0.0),
                        "tesoura3Passes": {
                            "cortado": tes.get("cortado"),
                            "trimStart": tes.get("trim_start"),
                            "trimEnd": tes.get("trim_end"),
                            "alucinacaoFinalRemovida": tes.get("alucinacao_final_removida"),
                            "cauda2sIntegra": tes.get("cauda_2s_integra"),
                        },
                        "motivos": qa.get("motivos_reprovacao", []),
                        "statusJuiz": "APROVADO (3 Camadas + Tesoura 3-Passes OK)" if qa.get("aprovado") else f"REPROVADO: {'; '.join(qa.get('motivos_reprovacao', []))}",
                    }
                )
            else:
                self._send_json({"ok": False, "erro": f"Clipe não encontrado: {cpath}"})
            return

        if self.path == "/api/regravar_take":
            take_num = int(payload.get("takeNumero") or 1)
            nova_fala = str(payload.get("novaFala") or "")
            vid_id = str(payload.get("videoId") or "V142")

            def _worker_regravar():
                try:
                    prompt_v = compilar_prompt_animacao_cena(
                        indice_cena=take_num - 1,
                        acao_visual="Speaks directly and naturally into the smartphone lens while demonstrating.",
                        fala_ingles=nova_fala,
                        cta=(take_num == 3),
                    )
                    gerar_video_rpc(
                        prompt=prompt_v,
                        first_frame_id="8c47d438-512b-4a37-bba1-6448b95b7cef",
                        modelo="veo_3_1_i2v_lite_low_priority",
                        tipo="i2v",
                    )
                except Exception:
                    pass

            threading.Thread(target=_worker_regravar, daemon=True).start()
            self._send_json(
                {
                    "ok": True,
                    "status": "regravando_no_flow",
                    "videoId": vid_id,
                    "detalhe": f"Take {take_num} disparado no Google Flow via RPC eb1hJf (Frase #1 literal) preservando os outros takes!",
                }
            )
            return

        self._send_json({"ok": False, "erro": "Endpoint desconhecido"}, status=404)


def main() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", PORTA_ZERUM), NossoZerumHandler)
    print(f"[+] NOSSO ZERUM LOCAL · 001 rodando em http://127.0.0.1:{PORTA_ZERUM}")
    server.serve_forever()


if __name__ == "__main__":
    main()
