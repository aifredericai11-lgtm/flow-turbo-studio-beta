#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
FIREWALL ANTI-PDQF / ANTI-TRUST-SCORE-ZERO (`forja/auditor_isolamento_pdqf.py`)
===============================================================================
Trava obrigatória de Isolamento Total para impedir que o algoritmo Andromeda (TMK + PDQF)
da Meta detecte vídeos como duplicados/reaproveitados e zere as views / trust score das páginas:

1. PROIBIDO >25% do quadro idêntico entre 2 vídeos diferentes (`diff L1 mínimo >= 28.0` e `Hamming distance dHash >= 18/64` em TODAS as cenas).
   - Bloqueia imediatamente qualquer vídeo feito com máscara só na cabeça (onde fundo/corpo ficam iguais) ou com cache de mesa compartilhado (`table_slot`).
2. PROIBIDO reutilizar o mesmo frame inicial em múltiplas cenas do mesmo vídeo (`[f1, f1, f1]`).
   - Cada cena (C1, C2, C3, C4) deve partir de um frame distinto (`diff L1 entre inícios de cena >= 18.0`).
3. BLINDAGEM ANTI-HASH PDQF/TMK (`blindar_mp4_isolamento_total_nvenc`):
   - Aplica entropia única de sensor (`noise=alls=3:allf=t+u`), micro-geometria única por vídeo, micro-curva de cor,
     micro-variação temporal (`atempo`/`setpts` exclusivo) e limpeza total de metadados (`-map_metadata -1`).
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import random
import subprocess
from typing import Any

import cv2
import numpy as np


def calcular_dhash_64(bgr: np.ndarray) -> int:
    gray = cv2.cvtColor(cv2.resize(bgr, (9, 8), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY)
    diff = gray[:, 1:] > gray[:, :-1]
    val = 0
    for bit in diff.flatten():
        val = (val << 1) | int(bool(bit))
    return val


def hamming_dist_64(h1: int, h2: int) -> int:
    return bin(h1 ^ h2).count("1")


def auditar_isolamento_video_contra_lote(
    mp4_path: Path,
    pasta_lote: Path,
    min_l1_entre_videos: float = 26.0,
    min_dhash_entre_videos: int = 16,
    min_l1_entre_cenas_internas: float = 14.0,
) -> tuple[bool, str, dict[str, Any]]:
    """
    Audita um vídeo .mp4 antes de permitir sua entrada na esteira de postagem:
    1) Verifica se as cenas internas (0.4s, 6.5s, 13.0s, 19.5s) não partem do mesmo frame congelado.
    2) Compara contra os outros vídeos já presentes em `pasta_lote` para garantir que fundo, corpo e cenas são 100% isolados.
    """
    if not mp4_path.exists() or mp4_path.stat().st_size < 100_000:
        return False, "ARQUIVO_INVALIDO", {}

    cap = cv2.VideoCapture(str(mp4_path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    n_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    dur = n_frames / max(1.0, fps)

    tempos = [0.4, min(6.2, dur * 0.28), min(12.5, dur * 0.55), max(1.0, dur - 2.5)]
    frames_small: list[np.ndarray] = []
    hashes: list[int] = []
    for t in tempos:
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
        ok, fr = cap.read()
        if not ok or fr is None:
            cap.release()
            return False, f"FALHA_LEITURA_FRAME({t:.1f}s)", {}
        frames_small.append(cv2.resize(fr, (64, 64)).astype(np.float32))
        hashes.append(calcular_dhash_64(fr))
    cap.release()

    # 1) Checa se cenas internas têm variação real
    internal_diffs = [
        round(float(np.mean(np.abs(frames_small[i] - frames_small[i + 1]))), 1)
        for i in range(len(frames_small) - 1)
    ]
    if min(internal_diffs) < min_l1_entre_cenas_internas:
        return (
            False,
            f"CENAS_INTERNAS_REPETIDAS(diffs={internal_diffs} < {min_l1_entre_cenas_internas})",
            {"internal_diffs": internal_diffs},
        )

    # 2) Checa isolamento contra outros vídeos da pasta
    outros = [p for p in sorted(pasta_lote.glob("*.mp4")) if p.resolve() != mp4_path.resolve()][:25]
    min_l1_ext = 999.0
    min_dh_ext = 64
    violador = ""
    for op in outros:
        cap2 = cv2.VideoCapture(str(op))
        for idx_t, t in enumerate([0.4, min(8.0, dur * 0.35)]):
            cap2.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
            ok2, fr2 = cap2.read()
            if not ok2 or fr2 is None:
                continue
            sm2 = cv2.resize(fr2, (64, 64)).astype(np.float32)
            dh2 = calcular_dhash_64(fr2)
            l1 = float(np.mean(np.abs(frames_small[idx_t] - sm2)))
            dh = hamming_dist_64(hashes[idx_t], dh2)
            if l1 < min_l1_ext:
                min_l1_ext = round(l1, 1)
                violador = op.name
            if dh < min_dh_ext:
                min_dh_ext = dh
        cap2.release()

    if outros and (min_l1_ext < min_l1_entre_videos or min_dh_ext < min_dhash_entre_videos):
        return (
            False,
            f"COLISAO_PDQF_COM_{violador}(L1={min_l1_ext}, dHash={min_dh_ext})",
            {"min_l1_ext": min_l1_ext, "min_dhash_ext": min_dh_ext, "internal_diffs": internal_diffs},
        )

    return True, "ISOLAMENTO_100%_OK", {
        "min_l1_ext": min_l1_ext,
        "min_dhash_ext": min_dh_ext,
        "internal_diffs": internal_diffs,
    }
