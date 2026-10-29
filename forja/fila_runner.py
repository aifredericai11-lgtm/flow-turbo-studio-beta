"""
Forja — Etapa 7: Fila Completa e Entrega (forja/fila_runner.py).
Regras:
- Roda a fila do lote (lotes/<id>/fila.json) vídeo a vídeo.
- Respeita bloqueados.json: formato ou avatar bloqueado não entra em lote novo / é pulado.
- A cada vídeo que terminar com todos os takes aprovados no QA:
  - monta a pasta com 1.mp4 .. N.mp4 + falas.json
  - entrega atomicamente na pasta entregues/ para a esteira de edição (Vigia) pegar na hora.
- No fim do lote, gera e exibe o resumo completo: quantos vídeos ficaram prontos, quantos reprovaram e por quê.
"""

from __future__ import annotations

import json
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from forja.estrutura import (
    BLOQUEADOS_JSON,
    ENTREGUES_DIR,
    LOTES_DIR,
    ROOT_DIR,
    BatchLogger,
    atualizar_status_video_fila,
    carregar_bloqueados,
    item_esta_bloqueado,
)
from forja.geracao_flow import executar_geracao_video_forja
from forja.qa_clipe import avaliar_qa_clipe, mover_para_reprovados


def entregar_video_aprovado(
    lote_id: str,
    video_id: str,
    pasta_video_lote: Path,
    entregues_root: Path = ENTREGUES_DIR,
    logger: BatchLogger | None = None,
) -> Path:
    """
    Monta a pasta final de entrega com 1.mp4 .. N.mp4 + falas.json e move atomicamente
    para entregues/<lote_id>_<video_id>/ para o Vigia da Edição capturar na hora.
    """
    entregues_root.mkdir(parents=True, exist_ok=True)
    nome_entrega = f"{lote_id}_{video_id}"
    pasta_temp = entregues_root.parent / "_staging_edicao" / f"_tmp_entrega_{nome_entrega}"
    pasta_final = entregues_root / nome_entrega

    if pasta_temp.exists():
        shutil.rmtree(pasta_temp)
    pasta_temp.mkdir(parents=True, exist_ok=True)

    falas_src = pasta_video_lote / "falas.json"
    if not falas_src.is_file():
        raise FileNotFoundError(f"falas.json não encontrado em {pasta_video_lote}")

    falas_data = json.loads(falas_src.read_text(encoding="utf-8"))
    for t in falas_data.get("takes", []):
        nome_mp4 = t["arquivo"]
        src_mp4 = pasta_video_lote / nome_mp4
        if not src_mp4.is_file():
            raise FileNotFoundError(f"Clipe {nome_mp4} ausente em {pasta_video_lote}")
        dst_mp4 = pasta_temp / nome_mp4
        try:
            os.link(src_mp4, dst_mp4)
        except Exception:
            shutil.copy2(src_mp4, dst_mp4)

    shutil.copy2(falas_src, pasta_temp / "falas.json")
    for extra_name in ("frame_1.jpg", "prompts.json", "cache_video.json"):
        extra_src = pasta_video_lote / extra_name
        if extra_src.is_file():
            shutil.copy2(extra_src, pasta_temp / extra_name)

    if pasta_final.exists():
        shutil.rmtree(pasta_final)
    shutil.move(str(pasta_temp), str(pasta_final))

    if logger:
        logger.log(f"[ENTREGUE] Pasta {pasta_final.name} publicada em entregues/ com {len(falas_data.get('takes', []))} takes + falas.json.")
    return pasta_final


def rodar_fila_lote(
    lote_id: str,
    project_url: str | None = None,
    modo_simulacao_local: bool = False,
    root: Path = ROOT_DIR,
) -> dict[str, Any]:
    """
    Roda a fila do lote (lotes/<lote_id>/fila.json) vídeo a vídeo:
    1) Verifica bloqueados.json (formato ou avatar bloqueado não roda).
    2) Executa geração + QA por clipe para cada vídeo.
    3) Se todos os takes do vídeo já estavam em cache, roda a verificação QA de integridade nos clipes.
    4) Entrega na hora em entregues/<lote_id>_<video_id>/ cada vídeo 100% aprovado.
    5) Retorna e salva o resumo final do lote (prontos, reprovados, bloqueados e motivos).
    """
    logger = BatchLogger(lote_id, root=root)
    pasta_lote = root / "lotes" / lote_id
    fila_path = pasta_lote / "fila.json"
    if not fila_path.is_file():
        raise FileNotFoundError(f"Arquivo de fila não encontrado: {fila_path}")

    fila_data = json.loads(fila_path.read_text(encoding="utf-8"))
    bloqueados = carregar_bloqueados(root / "bloqueados.json")

    prontos: list[dict[str, Any]] = []
    reprovados: list[dict[str, Any]] = []
    pulados_bloqueio: list[dict[str, Any]] = []

    for item in fila_data.get("videos", []):
        video_id = item["video_id"]
        pasta_video = pasta_lote / video_id
        prompts_path = pasta_video / "prompts.json"
        if not prompts_path.is_file():
            reprovados.append({"video_id": video_id, "motivo": "prompts.json ausente na pasta do vídeo."})
            continue

        prompts_video = json.loads(prompts_path.read_text(encoding="utf-8"))
        formato = prompts_video.get("formato", "")
        avatar = prompts_video.get("avatar", "")

        bloq, motivo_bloq = item_esta_bloqueado(formato=formato, avatar=avatar, bloqueados=bloqueados)
        if bloq:
            atualizar_status_video_fila(fila_path, video_id, status="bloqueado", erro=motivo_bloq)
            pulados_bloqueio.append({"video_id": video_id, "motivo": motivo_bloq})
            logger.log(f"[BLOQUEADO] Vídeo {video_id} ignorado: {motivo_bloq}", nivel="WARN")
            continue

        atualizar_status_video_fila(fila_path, video_id, status="gerando")
        res_geracao = executar_geracao_video_forja(
            lote_id=lote_id,
            prompts_video=prompts_video,
            so_frame1=False,
            modo_simulacao_local=modo_simulacao_local,
            project_url=project_url,
            root=root,
        )

        if res_geracao.get("modo") == "reprovado_qa" or res_geracao.get("aprovado") is False:
            motivo_str = "; ".join(res_geracao.get("motivos", ["Reprovado no QA de clipe"]))
            atualizar_status_video_fila(fila_path, video_id, status="reprovado", erro=motivo_str)
            reprovados.append(
                {
                    "video_id": video_id,
                    "take_reprovado": res_geracao.get("take_reprovado"),
                    "motivos": res_geracao.get("motivos", []),
                }
            )
            continue

        # Valida QA de todos os takes do vídeo antes da entrega (inclusive takes vindos do cache)
        todos_takes_ok = True
        relatorios_qa_takes = []
        for t in prompts_video.get("takes", []):
            num = int(t["take"])
            clip_p = pasta_video / f"{num}.mp4"
            img_p = pasta_video / f"frame_{num}.jpg"
            qa = avaliar_qa_clipe(
                video_path=clip_p,
                fala_pedida=t["fala"],
                imagem_gerada_path=img_p if img_p.exists() and not modo_simulacao_local else None,
            )
            relatorios_qa_takes.append(qa)
            if not qa["aprovado"]:
                todos_takes_ok = False
                mover_para_reprovados(
                    video_path=clip_p,
                    lote_id=lote_id,
                    video_id=video_id,
                    take_num=num,
                    relatorio_qa=qa,
                    reprovados_root=root / "_reprovados",
                    logger=logger,
                )
                atualizar_status_video_fila(
                    fila_path,
                    video_id,
                    status="reprovado",
                    erro="; ".join(qa["motivos_reprovacao"]),
                )
                reprovados.append(
                    {
                        "video_id": video_id,
                        "take_reprovado": num,
                        "motivos": qa["motivos_reprovacao"],
                    }
                )
                break

        if not todos_takes_ok:
            continue

        # Salva relatório de QA dos takes na pasta do vídeo e entrega em entregues/
        (pasta_video / "qa_takes.json").write_text(
            json.dumps(relatorios_qa_takes, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        pasta_entregue = entregar_video_aprovado(
            lote_id=lote_id,
            video_id=video_id,
            pasta_video_lote=pasta_video,
            entregues_root=root / "entregues",
            logger=logger,
        )
        atualizar_status_video_fila(
            fila_path,
            video_id,
            status="entregue",
            takes_prontos=[int(t["take"]) for t in prompts_video.get("takes", [])],
        )
        prontos.append(
            {
                "video_id": video_id,
                "formato": formato,
                "avatar": avatar,
                "pasta_entregue": str(pasta_entregue),
                "qtd_takes": len(prompts_video.get("takes", [])),
            }
        )

    resumo = {
        "lote_id": lote_id,
        "finalizado_em": datetime.now().isoformat(timespec="seconds"),
        "total_videos_fila": len(fila_data.get("videos", [])),
        "qtd_prontos_entregues": len(prontos),
        "qtd_reprovados": len(reprovados),
        "qtd_bloqueados": len(pulados_bloqueio),
        "prontos": prontos,
        "reprovados": reprovados,
        "bloqueados": pulados_bloqueio,
    }
    (pasta_lote / "resumo_lote.json").write_text(
        json.dumps(resumo, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.log(
        f"=== RESUMO DO LOTE {lote_id}: {len(prontos)} prontos/entregues | {len(reprovados)} reprovados | {len(pulados_bloqueio)} bloqueados ==="
    )
    return resumo
