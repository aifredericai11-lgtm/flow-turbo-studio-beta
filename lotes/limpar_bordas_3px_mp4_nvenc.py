#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
LIMPADOR GPU NVENC DE BORDAS PRETAS (`3px` PILLARBOX DO VEO 3.1 LITE)
=====================================================================
Remove cirurgicamente qualquer barra escura lateral/superior (`crop=iw-12:ih-20:6:10,scale=720:1280:flags=lanczos`)
dos vídeos `.mp4` gerados em `veo_3_1_i2v_lite_low_priority` (onde o BELUGA 768x1376 gerava 3px de borda preta
na esquerda `x=0..2` e na direita `x=717..719`), garantindo 100% tela cheia 720x1280 no Checklist da Meta!
"""
from __future__ import annotations

import concurrent.futures
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import cv2
import numpy as np

FFMPEG_BIN = shutil.which("ffmpeg") or "ffmpeg"
NVENC_SEM = concurrent.futures.ThreadPoolExecutor(max_workers=6)


def tem_borda_preta_mp4(mp4_path: Path) -> tuple[bool, tuple[int, int, int, int]]:
    try:
        cap = cv2.VideoCapture(str(mp4_path))
        ok, im = cap.read()
        cap.release()
        if not ok or im is None:
            return False, (0, 0, 0, 0)
        h, w = im.shape[:2]
        gray = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)

        def dr(rows):
            c = 0
            for r in rows:
                if np.percentile(gray[r, :], 90) < 32:
                    c += 1
                else:
                    break
            return c

        def dc(cols):
            c = 0
            for col_i in cols:
                if np.percentile(gray[:, col_i], 90) < 32:
                    c += 1
                else:
                    break
            return c

        tb = (
            dr(range(int(h * 0.18))),
            dr(range(h - 1, int(h * 0.82), -1)),
            dc(range(int(w * 0.18))),
            dc(range(w - 1, int(w * 0.82), -1)),
        )
        return (max(tb) >= 1), tb
    except Exception:
        return False, (0, 0, 0, 0)


def limpar_borda_um_mp4(mp4_path: Path) -> dict:
    has_b, tb = tem_borda_preta_mp4(mp4_path)
    if not has_b:
        return {"file": mp4_path.name, "action": "ALREADY_CLEAN", "bars": tb}

    t, b, l, r = tb
    # Margem de segurança de +3px além da borda detectada, mantendo aspecto 9:16
    crop_x = max(6, max(l, r) + 3)
    crop_y = max(10, max(t, b) + int(round(crop_x * 16.0 / 9.0)))
    cw = 720 - 2 * crop_x
    ch = 1280 - 2 * crop_y

    tmp_out = mp4_path.with_suffix(".noborder.tmp.mp4")
    vf = f"crop={cw}:{ch}:{crop_x}:{crop_y},scale=720:1280:flags=lanczos,format=yuv420p"
    from forja.hw_accel import args_h264_hw, encontrar_ffmpeg_bin

    cmd = [
        encontrar_ffmpeg_bin(), "-y", "-loglevel", "error",
        "-i", str(mp4_path),
        "-vf", vf,
        *args_h264_hw(bitrate="2.4M", maxrate="3.5M", bufsize="5M", cq=22),
        "-c:a", "copy", "-movflags", "+faststart",
        str(tmp_out),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode == 0 and tmp_out.exists() and tmp_out.stat().st_size > 100_000:
        tmp_out.replace(mp4_path)
        still_b, tb_after = tem_borda_preta_mp4(mp4_path)
        return {"file": mp4_path.name, "action": "FIXED", "before": tb, "after": tb_after, "clean": not still_b}
    else:
        tmp_out.unlink(missing_ok=True)
        return {"file": mp4_path.name, "action": "ERROR", "err": res.stderr[:200]}


def main() -> None:
    t0 = time.time()
    target_dirs = [
        Path(r"C:\Hub001\VIDEOS_PRONTOS\LOTE_100__WL_USA__F37_BICARBONATO_LINGUA_2_JAPONESAS"),
        Path(r"C:\Hub001\VIDEOS_PRONTOS\LOTE_100_PT2__WL_USA__F37_BICARBONATO_LINGUA_2_JAPONESAS_MAXPOWER"),
        Path(r"C:\Hub001\VIDEOS_PRONTOS\TESTE_40__WL_USA__F37_BICARBONATO_LINGUA_2_JAPONESAS"),
        Path(r"C:\Hub001\VIDEOS_PRONTOS\LOTE_200__AQUECIMENTO__F38_VELA_INFINITA_INGLES_E_ALEMAO"),
        Path(r"C:\Hub001\VIDEOS_PRONTOS\22_LOTE_20_BATWINGS_V02_ENFERMEIRA_SEM_MANGA"),
        Path(r"C:\Hub001\VIDEOS_PRONTOS\23_LOTE_20_BATWINGS_V03_ENFERMEIRA_SEM_MANGA"),
        Path(r"C:\Hub001\VIDEOS_PRONTOS\24_LOTE_20_PE_500K_PERTO_HOMEM_BRANCO"),
        Path(r"C:\Hub001\VIDEOS_PRONTOS\25_LOTE_20_BATWINGS_V02_ENFERMEIRA_SEM_MANGA_PT2"),
        Path(r"C:\Hub001\VIDEOS_PRONTOS\26_LOTE_20_BATWINGS_V03_ENFERMEIRA_SEM_MANGA_PT2"),
        Path(r"C:\Hub001\VIDEOS_PRONTOS\27_LOTE_20_PE_500K_PERTO_HOMEM_BRANCO_PT2"),
        Path(r"C:\Hub001\VIDEOS_PRONTOS\28_LOTE_20_LIVER1_PE_PRIMEIRO_PISO_MADEIRA_PT2"),
        Path(r"C:\Hub001\VIDEOS_PRONTOS\29_LOTE_20_NOVO_VIRAL_COXA_INTERNA_MANEQUIM_HOMEM"),
        Path(r"C:\Hub001\VIDEOS_PRONTOS\30_LOTE_20_NOVO_VIRAL_MACA_CLINICA_DOIS_PES_325K_BRANCA"),
    ]
    all_mp4s: list[Path] = []
    for d in target_dirs:
        if d.exists():
            all_mp4s.extend(sorted(d.glob("*.mp4")))

    print(f"=== LIMPADOR GPU NVENC DE BORDAS PRETAS | {len(all_mp4s)} VIDEOS ALVO ===", flush=True)
    fixed = 0
    already_clean = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
        futs = {ex.submit(limpar_borda_um_mp4, p): p for p in all_mp4s}
        for idx, f in enumerate(concurrent.futures.as_completed(futs), 1):
            r = f.result()
            if r["action"] == "FIXED":
                fixed += 1
            elif r["action"] == "ALREADY_CLEAN":
                already_clean += 1
            if idx % 25 == 0 or idx == len(all_mp4s):
                print(f"  [{idx}/{len(all_mp4s)}] Corrigidos: {fixed} | Ja limpos: {already_clean} | {(time.time()-t0):.1f}s", flush=True)

    # Espelha os arquivos limpos de volta no Cofre Imutável do Drive
    cofre_map = {
        "LOTE_100__WL_USA__F37_BICARBONATO_LINGUA_2_JAPONESAS": r"H:\Meu Drive\HUB CENTRAL OP ORGÂNICO\04_COFRE_IMUTAVEL_POR_FORMATO\F37_BICARBONATO_LINGUA_2_ASIATICAS",
        "LOTE_100_PT2__WL_USA__F37_BICARBONATO_LINGUA_2_JAPONESAS_MAXPOWER": r"H:\Meu Drive\HUB CENTRAL OP ORGÂNICO\04_COFRE_IMUTAVEL_POR_FORMATO\F37_BICARBONATO_LINGUA_2_ASIATICAS",
        "TESTE_40__WL_USA__F37_BICARBONATO_LINGUA_2_JAPONESAS": r"H:\Meu Drive\HUB CENTRAL OP ORGÂNICO\04_COFRE_IMUTAVEL_POR_FORMATO\F37_BICARBONATO_LINGUA_2_ASIATICAS",
        "22_LOTE_20_BATWINGS_V02_ENFERMEIRA_SEM_MANGA": r"H:\Meu Drive\HUB CENTRAL OP ORGÂNICO\04_COFRE_IMUTAVEL_POR_FORMATO\F31_BATWINGS_V02_ENF_SEM_MANGA",
        "25_LOTE_20_BATWINGS_V02_ENFERMEIRA_SEM_MANGA_PT2": r"H:\Meu Drive\HUB CENTRAL OP ORGÂNICO\04_COFRE_IMUTAVEL_POR_FORMATO\F31_BATWINGS_V02_ENF_SEM_MANGA",
        "23_LOTE_20_BATWINGS_V03_ENFERMEIRA_SEM_MANGA": r"H:\Meu Drive\HUB CENTRAL OP ORGÂNICO\04_COFRE_IMUTAVEL_POR_FORMATO\F32_BATWINGS_V03_PINCH_SEM_MANGA",
        "26_LOTE_20_BATWINGS_V03_ENFERMEIRA_SEM_MANGA_PT2": r"H:\Meu Drive\HUB CENTRAL OP ORGÂNICO\04_COFRE_IMUTAVEL_POR_FORMATO\F32_BATWINGS_V03_PINCH_SEM_MANGA",
        "24_LOTE_20_PE_500K_PERTO_HOMEM_BRANCO": r"H:\Meu Drive\HUB CENTRAL OP ORGÂNICO\04_COFRE_IMUTAVEL_POR_FORMATO\F33_PE_500K_PERTO_HOMEM_BRANCO",
        "27_LOTE_20_PE_500K_PERTO_HOMEM_BRANCO_PT2": r"H:\Meu Drive\HUB CENTRAL OP ORGÂNICO\04_COFRE_IMUTAVEL_POR_FORMATO\F33_PE_500K_PERTO_HOMEM_BRANCO",
        "28_LOTE_20_LIVER1_PE_PRIMEIRO_PISO_MADEIRA_PT2": r"H:\Meu Drive\HUB CENTRAL OP ORGÂNICO\04_COFRE_IMUTAVEL_POR_FORMATO\F21_LIVER1_PE_PISO_MADEIRA",
        "29_LOTE_20_NOVO_VIRAL_COXA_INTERNA_MANEQUIM_HOMEM": r"H:\Meu Drive\HUB CENTRAL OP ORGÂNICO\04_COFRE_IMUTAVEL_POR_FORMATO\F35_COXA_INTERNA_MANEQUIM",
        "30_LOTE_20_NOVO_VIRAL_MACA_CLINICA_DOIS_PES_325K_BRANCA": r"H:\Meu Drive\HUB CENTRAL OP ORGÂNICO\04_COFRE_IMUTAVEL_POR_FORMATO\F36_MACA_CLINICA_2PES_325K",
    }
    synced = 0
    for src_folder, dst_cofre in cofre_map.items():
        s_dir = Path(r"C:\Hub001\VIDEOS_PRONTOS") / src_folder
        d_dir = Path(dst_cofre)
        if s_dir.exists() and d_dir.exists():
            for mp4 in s_dir.glob("*.mp4"):
                shutil.copy2(mp4, d_dir / mp4.name)
                synced += 1

    print(json.dumps({"ok": True, "total": len(all_mp4s), "fixed": fixed, "already_clean": already_clean, "synced_to_cofre": synced, "elapsed_s": round(time.time() - t0, 1)}, indent=2))


if __name__ == "__main__":
    main()
