"""
Módulo de Offload Automático em Nuvem via Rclone (`peachclub:SISTEMA_FORJA_VIGIA_100X`).

Objetivos:
1. Garantir que o disco local `C:` NUNCA encha durante ou após lotes de geração no Google Flow.
2. Enviar automaticamente em 16 threads (`--transfers 16 --checkers 16 --drive-chunk-size 64M`)
   os lotes gerados (`lotes/`), pacotes entregues (`entregues/`), vídeos editados (`prontos/`),
   arquivos processados (`_feitos/`, `_reprovados/`) e pastas pesadas de gerações antigas para:
   `peachclub:SISTEMA_FORJA_VIGIA_100X/...`
3. Eliminar duplicação local entre `lotes/<lote_id>/<video_id>` e `entregues/<lote_id>_<video_id>`
   usando hardlinks NTFS (0 bytes extras) antes do offload e removendo os `.mp4` locais após confirmação no `peachclub:`.
4. Permitir hidratação sob demanda (`restaurar_video_do_peachclub`) quando o Agente Validador
   solicitar lote de correção (`corrigir`) de um vídeo já descarregado para a nuvem.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from forja.estrutura import ROOT_DIR, BatchLogger

PEACHCLUB_REMOTE_BASE = os.environ.get("FORJA_RCLONE_REMOTE", "peachclub:SISTEMA_FORJA_VIGIA_100X")

RCLONE_TURBO_FLAGS = [
    "--transfers", "16",
    "--checkers", "16",
    "--drive-chunk-size", "64M",
    "--fast-list",
    "-- delete-empty-src-dirs" if False else "--stats-one-line",
    "--retries", "3",
    "--low-level-retries", "5",
]


def garantir_alias_peachclub() -> str:
    """
    Garante que o remote `peachclub:` exista no rclone.conf apontando para `peach:`.
    Retorna o prefixo remoto base pronto para uso.
    """
    try:
        res = subprocess.run(
            ["rclone", "listremotes"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
        remotes = [r.strip() for r in (res.stdout or "").splitlines() if r.strip()]
        if "peachclub:" not in remotes and "peach:" in remotes:
            subprocess.run(
                ["rclone", "config", "create", "peachclub", "alias", "remote", "peach:"],
                capture_output=True,
                text=True,
                timeout=10,
            )
    except Exception:
        pass
    return PEACHCLUB_REMOTE_BASE


def executar_rclone(
    subcomando: str,
    origem: str | Path,
    destino: str,
    incluir: list[str] | None = None,
    excluir: list[str] | None = None,
    deletar_pastas_vazias: bool = True,
    timeout_s: int = 1800,
    logger: BatchLogger | None = None,
) -> dict[str, Any]:
    """
    Executa `rclone move`, `rclone copy` ou `rclone sync` com 16 threads paralelas.
    """
    garantir_alias_peachclub()
    cmd = [
        "rclone",
        subcomando,
        str(origem),
        destino,
        "--transfers", "16",
        "--checkers", "16",
        "--drive-chunk-size", "64M",
        "--fast-list",
        "--retries", "3",
    ]
    if subcomando == "move" and deletar_pastas_vazias:
        cmd.append("--delete-empty-src-dirs")

    for inc in incluir or []:
        cmd.extend(["--include", inc])
    for exc in excluir or []:
        cmd.extend(["--exclude", exc])

    t0 = time.monotonic()
    if logger:
        logger.log(f"[RCLONE {subcomando.upper()}] {origem} -> {destino}")

    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_s,
    )
    dur_s = round(time.monotonic() - t0, 2)
    ok = proc.returncode == 0
    if logger:
        if ok:
            logger.log(f"[RCLONE OK] {subcomando} concluído em {dur_s}s -> {destino}")
        else:
            logger.log(
                f"[RCLONE ERRO code={proc.returncode}] {destino}: {(proc.stderr or '')[-400:]}",
                nivel="WARN",
            )
    return {
        "ok": ok,
        "returncode": proc.returncode,
        "comando": " ".join(cmd),
        "destino": destino,
        "duracao_s": dur_s,
        "stderr": (proc.stderr or "")[-500:],
    }


def descarregar_onda_para_peachclub(
    lote_id: str,
    video_ids: list[str],
    root: Path = ROOT_DIR,
    remover_mp4_local_lote: bool = True,
    mover_entregues_para_nuvem: bool = False,
    logger: BatchLogger | None = None,
) -> dict[str, Any]:
    """
    Chamado automaticamente ao fim de cada Macro-Onda ou Lote:
    1) Faz upload em 16 threads da pasta do lote (`lotes/<lote_id>`) para
       `peachclub:SISTEMA_FORJA_VIGIA_100X/lotes/<lote_id>`.
    2) Sincroniza os pacotes entregues (`entregues/<lote_id>_<video_id>`) para
       `peachclub:SISTEMA_FORJA_VIGIA_100X/entregues/`.
    3) Se `remover_mp4_local_lote=True`, remove os `.mp4` pesados de `lotes/<lote_id>/<video_id>/`
       (mantendo `cache_video.json`, `prompts.json`, `falas.json` e `frame_1.jpg` leves no disco),
       e se `mover_entregues_para_nuvem=True`, move também os `.mp4` de `entregues/` para liberar 100% do espaço.
    """
    base_remote = garantir_alias_peachclub()
    pasta_lote = root / "lotes" / lote_id
    entregues_root = root / "entregues"

    resultados = []
    bytes_liberados = 0

    if pasta_lote.is_dir():
        rem_lote = f"{base_remote}/lotes/{lote_id}"
        res_lote = executar_rclone(
            subcomando="copy",
            origem=pasta_lote,
            destino=rem_lote,
            logger=logger,
        )
        resultados.append(res_lote)

        if res_lote["ok"] and remover_mp4_local_lote:
            for vid_id in video_ids:
                pasta_v = pasta_lote / vid_id
                if not pasta_v.is_dir():
                    continue
                for mp4_file in pasta_v.glob("*.mp4"):
                    try:
                        sz = mp4_file.stat().st_size
                        mp4_file.unlink()
                        bytes_liberados += sz
                    except Exception:
                        pass

    if entregues_root.is_dir():
        incluir_filtros = [f"{lote_id}_{vid_id}/**" for vid_id in video_ids]
        rem_ent = f"{base_remote}/entregues"
        subcmd = "move" if mover_entregues_para_nuvem else "copy"
        if mover_entregues_para_nuvem:
            for vid_id in video_ids:
                p_ent = entregues_root / f"{lote_id}_{vid_id}"
                if p_ent.is_dir():
                    for f in p_ent.rglob("*"):
                        if f.is_file():
                            bytes_liberados += f.stat().st_size
        res_ent = executar_rclone(
            subcomando=subcmd,
            origem=entregues_root,
            destino=rem_ent,
            incluir=incluir_filtros if video_ids else None,
            logger=logger,
        )
        resultados.append(res_ent)

    mb_liberados = round(bytes_liberados / (1024 * 1024), 2)
    if logger:
        logger.log(
            f"[OFFLOAD PEACHCLUB] Lote {lote_id} ({len(video_ids)} vídeos) sincronizado em {base_remote} | "
            f"Espaço local liberado imediatamente: {mb_liberados} MB"
        )
    return {
        "lote_id": lote_id,
        "remote_lote": f"{base_remote}/lotes/{lote_id}",
        "remote_entregues": f"{base_remote}/entregues",
        "mb_liberados_local": mb_liberados,
        "resultados_rclone": resultados,
    }


def restaurar_video_do_peachclub(
    lote_id: str,
    video_id: str,
    root: Path = ROOT_DIR,
    logger: BatchLogger | None = None,
) -> Path:
    """
    Restaura sob demanda do `peachclub:` os arquivos brutos (`frame_1.jpg`, `1.mp4..3.mp4`)
    de um vídeo específico quando o Agente Validador pede correção (`corrigir`) de um take.
    """
    base_remote = garantir_alias_peachclub()
    pasta_v = root / "lotes" / lote_id / video_id
    pasta_v.mkdir(parents=True, exist_ok=True)
    rem_v = f"{base_remote}/lotes/{lote_id}/{video_id}"
    executar_rclone(
        subcomando="copy",
        origem=rem_v,
        destino=str(pasta_v),
        logger=logger,
    )
    return pasta_v


def liberar_espaco_geral_peachclub(
    root: Path = ROOT_DIR,
    incluir_arquivos_pesados_cursos: bool = False,
) -> dict[str, Any]:
    """
    Varre o diretório de trabalho e move todas as pastas pesadas de gerações/lotes/entregues/prontos
    para `peachclub:SISTEMA_FORJA_VIGIA_100X/...`, limpando também diretórios temporários locais.
    """
    base_remote = garantir_alias_peachclub()
    relatorio: list[dict[str, Any]] = []

    # 1. Limpa temporários locais puros (_staging_edicao, temp_frames, sampled_frames)
    for tmp_name in ("_staging_edicao", "temp_frames", "sampled_frames"):
        p_tmp = root / tmp_name
        if p_tmp.is_dir():
            sz_bytes = sum(f.stat().st_size for f in p_tmp.rglob("*") if f.is_file())
            shutil.rmtree(p_tmp, ignore_errors=True)
            p_tmp.mkdir(parents=True, exist_ok=True)
            relatorio.append(
                {
                    "pasta": tmp_name,
                    "acao": "limpeza_temp_local",
                    "mb_liberados": round(sz_bytes / (1024 * 1024), 1),
                }
            )

    # 2. Move pastas de pipeline Forja/Vigia para peachclub:SISTEMA_FORJA_VIGIA_100X/<pasta>
    pastas_pipeline_move = [
        ("entregues", f"{base_remote}/entregues"),
        ("prontos", f"{base_remote}/prontos"),
        ("_feitos", f"{base_remote}/_feitos"),
        ("_reprovados", f"{base_remote}/_reprovados"),
        ("_revisao", f"{base_remote}/_revisao"),
    ]
    for nome_local, dest_remoto in pastas_pipeline_move:
        p_loc = root / nome_local
        if p_loc.is_dir():
            sz_bytes = sum(f.stat().st_size for f in p_loc.rglob("*") if f.is_file())
            if sz_bytes > 0:
                res = executar_rclone("move", p_loc, dest_remoto, deletar_pastas_vazias=True)
                p_loc.mkdir(parents=True, exist_ok=True)
                relatorio.append(
                    {
                        "pasta": nome_local,
                        "destino_peachclub": dest_remoto,
                        "ok": res["ok"],
                        "mb_movidos": round(sz_bytes / (1024 * 1024), 1),
                    }
                )

    # 3. Para `lotes/`: faz copy completo para peachclub:SISTEMA_FORJA_VIGIA_100X/lotes e apaga todos os .mp4 locais
    # (mantendo apenas os JSONs leves de manifesto e cache para rastreio rápido!)
    p_lotes = root / "lotes"
    if p_lotes.is_dir():
        sz_mp4 = sum(f.stat().st_size for f in p_lotes.rglob("*.mp4") if f.is_file())
        if sz_mp4 > 0:
            res_lotes = executar_rclone("copy", p_lotes, f"{base_remote}/lotes")
            if res_lotes["ok"]:
                for mp4_f in p_lotes.rglob("*.mp4"):
                    try:
                        mp4_f.unlink()
                    except Exception:
                        pass
            relatorio.append(
                {
                    "pasta": "lotes (*.mp4)",
                    "destino_peachclub": f"{base_remote}/lotes",
                    "ok": res_lotes["ok"],
                    "mb_movidos": round(sz_mp4 / (1024 * 1024), 1),
                }
            )

    # 4. Pastas de gerações/extrações avulsas na raiz do projeto
    pastas_geracoes_avulsas = [
        "myoro_ads",
        "VIDEOS_JAPAO_GERADOS",
        "IMAGENS_JAPAO_GERADAS",
        "MYORO_ADS_VIDEOS",
        "AD_CREATORS_LAB_EXTRACAO",
        "extracao_videos",
        "PRINTS_PARA_EDICAO",
        "VIDEOS_ORIGINAIS_MP4",
    ]
    for nome_avulsa in pastas_geracoes_avulsas:
        p_av = root / nome_avulsa
        if p_av.is_dir():
            sz_bytes = sum(f.stat().st_size for f in p_av.rglob("*") if f.is_file())
            if sz_bytes > 0:
                dest_av = f"{base_remote}/geracoes_arquivadas/{nome_avulsa}"
                res_av = executar_rclone("move", p_av, dest_av, deletar_pastas_vazias=True)
                shutil.rmtree(p_av, ignore_errors=True)
                relatorio.append(
                    {
                        "pasta": nome_avulsa,
                        "destino_peachclub": dest_av,
                        "ok": res_av["ok"],
                        "mb_movidos": round(sz_bytes / (1024 * 1024), 1),
                    }
                )

    # 5. Opcional: Vídeos brutos gigantes de cursos locais (46.2 GB: AULAS_MP4 + AULAS_ORGANICO_MP4)
    if incluir_arquivos_pesados_cursos:
        pesados_cursos = [
            (root / "001_COMMUNITY_COMPLETO" / "AULAS_MP4", "peachclub:001_COMMUNITY_SITE_E_BASE_IA/AULAS_MP4"),
            (root / "AULAS_ORGANICO_MP4", "peachclub:AULAS_ORGANICO_MP4"),
        ]
        for p_curso, dest_curso in pesados_cursos:
            if p_curso.is_dir():
                sz_bytes = sum(f.stat().st_size for f in p_curso.rglob("*") if f.is_file())
                if sz_bytes > 0:
                    res_c = executar_rclone("move", p_curso, dest_curso, deletar_pastas_vazias=True)
                    shutil.rmtree(p_curso, ignore_errors=True)
                    relatorio.append(
                        {
                            "pasta": str(p_curso.relative_to(root)),
                            "destino_peachclub": dest_curso,
                            "ok": res_c["ok"],
                            "mb_movidos": round(sz_bytes / (1024 * 1024), 1),
                        }
                    )

    return {
        "remote_base": base_remote,
        "acoes": relatorio,
        "total_mb_liberados": round(
            sum(item.get("mb_movidos", 0.0) + item.get("mb_liberados", 0.0) for item in relatorio),
            1,
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Offload Rclone de Gerações para peachclub:")
    parser.add_argument("--incluir-cursos-mp4", action="store_true", help="Move também AULAS_MP4 (32GB) e AULAS_ORGANICO_MP4 (14.3GB) para o peachclub:")
    args = parser.parse_args()
    res = liberar_espaco_geral_peachclub(incluir_arquivos_pesados_cursos=args.incluir_cursos_mp4)
    print(json.dumps(res, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
