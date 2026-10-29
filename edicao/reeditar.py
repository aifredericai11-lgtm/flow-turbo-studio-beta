"""
Edição — Etapa 8: Reedição por ID (edicao/reeditar.py) + Processador Completo de Entrega.
Regras:
- Comando para reeditar qualquer vídeo pelo ID (ex: V001) sem gerar nada de novo no Flow:
  puxa os originais preservados em _feitos/, refaz corte / montagem / legenda / CTA com os ajustes pedidos,
  valida no QA final e substitui o arquivo pronto em prontos/<formato>/.
- Também fornece processar_entrega_completa(), que o Vigia chama automaticamente para cada pasta em entregues/.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from edicao.apoio_visual_linfonodos import aplicar_apoio_visual_variado, escolher_ativo_e_layout
from edicao.cta import aplicar_cta_ultimo_take
from edicao.estoque import carregar_estoque, registrar_video_no_estoque, salvar_estoque
from edicao.legenda_ass import legendar_video_montado
from edicao.montagem import montar_video
from edicao.qa_final import avaliar_qa_final_video, enviar_para_revisao
from edicao.transcricao_cortes import processar_transcricao_e_cortes_pasta
from forja.estrutura import FEITOS_DIR, ROOT_DIR, STAGING_EDICAO_DIR


def processar_entrega_completa(
    pasta_entregue: Path,
    root: Path = ROOT_DIR,
    usar_flash_branco: bool = True,
    frames_flash: int = 2,
    pos_y_legenda: int = 1240,
    texto_cta: str | None = None,
    y_base_cta: int = 1480,
) -> dict[str, Any]:
    """
    Executa a Esteira de Edição completa (Etapas 2, 3, 4, 5, 6 e 7) sobre uma pasta entregue:
    1) Etapa 2: Transcrição Whisper GPU e cortes exatos.
    2) Etapa 3: Montagem 1080x1920 + flash branco + FCPXML DaVinci Resolve.
    3) Etapa 4: Legenda Karaokê .ass da fala real.
    4) Etapa 5: CTA com pulo no último take.
    5) Etapa 6: QA Final (se reprovar, envia para _revisao/ com motivo).
    6) Etapa 7: Salva originais em _feitos/, classifica como V001..Vxxx em prontos/<formato>/ e registra no estoque.json.
    """
    nome_pasta = pasta_entregue.name
    staging_dir = root / "_staging_edicao" / nome_pasta
    staging_dir.mkdir(parents=True, exist_ok=True)

    falas_path = pasta_entregue / "falas.json"
    falas_data = json.loads(falas_path.read_text(encoding="utf-8")) if falas_path.is_file() else {}
    formato = falas_data.get("formato", "formato_geral")
    avatar = falas_data.get("avatar", "avatar_padrao")
    cta_label = texto_cta or falas_data.get("cta_texto", "COMMENT YES")

    # Etapa 2: Transcrição e Cortes
    rel_etapa2 = processar_transcricao_e_cortes_pasta(
        pasta_entregue=pasta_entregue,
        pasta_trabalho=staging_dir,
    )
    (staging_dir / "relatorio_etapa2.json").write_text(
        json.dumps(rel_etapa2, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # Etapa 3: Montagem
    eh_split_nativo = "split" in formato.lower()
    if eh_split_nativo and pos_y_legenda == 1240:
        pos_y_legenda = 960

    clipes_cortados = sorted((staging_dir / "cortados").glob("*.mp4"), key=lambda p: int(p.stem))
    montado_mp4 = staging_dir / "montado_etapa3.mp4"
    rel_etapa3 = montar_video(
        clipes_cortados=clipes_cortados,
        destino_mp4=montado_mp4,
        formato=formato,
        usar_flash_branco=usar_flash_branco,
        frames_flash=frames_flash,
        fps=30,
        crf=20,
        sincronizar_resolve=True,
        usar_punch_in_corpo=not eh_split_nativo,
    )
    (staging_dir / "relatorio_etapa3_montagem.json").write_text(
        json.dumps(rel_etapa3, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # Etapa 3.5: Apoio Visual Variado (apenas quando o vídeo não é Split-Screen nativo do Veo 3.1)
    video_para_legendar = montado_mp4
    takes_etapa3 = rel_etapa3.get("takes", [])
    if not eh_split_nativo:
        texto_copy_total = " ".join(str(t) for t in falas_data.get("falas", []))
        idx_var = sum(ord(ch) for ch in nome_pasta)
        ativo_apoio, layout_apoio = escolher_ativo_e_layout(formato, texto_copy_total, indice_variacao=idx_var)
        if ativo_apoio.is_file():
            montado_com_apoio_mp4 = staging_dir / "montado_etapa3_com_apoio.mp4"
            ini_apoio = float(takes_etapa3[1]["inicio_s"]) if len(takes_etapa3) > 1 else 0.4
            fim_apoio = float(takes_etapa3[-1]["inicio_s"]) if len(takes_etapa3) > 2 else None
            rel_apoio = aplicar_apoio_visual_variado(
                video_entrada=montado_mp4,
                video_saida=montado_com_apoio_mp4,
                imagem_apoio=ativo_apoio,
                layout=layout_apoio,
                inicio_s=ini_apoio,
                fim_s=fim_apoio,
                crf=20,
            )
            rel_etapa3["apoio_visual"] = rel_apoio
            video_para_legendar = montado_com_apoio_mp4
            if layout_apoio == "quadro6_3d_meio_apresentador_canto":
                pos_y_legenda = 960

    # Etapa 4: Legenda Karaokê .ass (reutiliza timestamps por palavra já extraídos na Etapa 2 + offsets da Etapa 3)
    palavras_montado: list[dict[str, Any]] = []
    clipes_etapa2 = rel_etapa2.get("clipes", [])
    for idx_t, c_info in enumerate(clipes_etapa2):
        offset_t = float(takes_etapa3[idx_t]["inicio_s"]) if idx_t < len(takes_etapa3) else 0.0
        for w in c_info.get("palavras", []):
            palavras_montado.append(
                {
                    "palavra": w["palavra"],
                    "inicio": round(float(w["inicio"]) + offset_t, 3),
                    "fim": round(float(w["fim"]) + offset_t, 3),
                }
            )

    ass_path = staging_dir / "legenda_karaoke.ass"
    legendado_mp4 = staging_dir / "legendado_etapa4.mp4"
    rel_etapa4 = legendar_video_montado(
        video_montado=video_para_legendar,
        destino_ass=ass_path,
        destino_mp4=legendado_mp4,
        pos_y=pos_y_legenda,
        palavras_precalculadas=palavras_montado if palavras_montado else None,
    )
    (staging_dir / "relatorio_etapa4_legenda.json").write_text(
        json.dumps(rel_etapa4, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # Etapa 5: CTA com pulo no último take
    inicio_ultimo_take = rel_etapa3["takes"][-1]["inicio_s"]
    final_cta_mp4 = staging_dir / "final_etapa5_cta.mp4"
    rel_etapa5 = aplicar_cta_ultimo_take(
        video_entrada=legendado_mp4,
        video_saida=final_cta_mp4,
        inicio_ultimo_take_s=inicio_ultimo_take,
        texto_cta=cta_label,
        y_base=y_base_cta,
    )
    (staging_dir / "relatorio_etapa5_cta.json").write_text(
        json.dumps(rel_etapa5, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # Etapa 6: QA Final
    rel_qa_final = avaliar_qa_final_video(
        video_pronto_path=final_cta_mp4,
        ass_path=ass_path,
        relatorio_etapa2=rel_etapa2,
        duracao_esperada_s=rel_etapa3["duracao_final_s"],
    )
    (staging_dir / "relatorio_etapa6_qa_final.json").write_text(
        json.dumps(rel_qa_final, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # Preserva os originais em _feitos/<nome_pasta>/ (nunca apaga)
    feitos_pasta = root / "_feitos" / nome_pasta
    if pasta_entregue.resolve() != feitos_pasta.resolve():
        if feitos_pasta.exists():
            shutil.rmtree(feitos_pasta)
        shutil.copytree(pasta_entregue, feitos_pasta)
        if pasta_entregue.parent.name == "entregues":
            shutil.rmtree(pasta_entregue)

    if not rel_qa_final["aprovado"]:
        pasta_rev = enviar_para_revisao(
            video_path=final_cta_mp4,
            identificador=nome_pasta,
            relatorio_qa=rel_qa_final,
            revisao_root=root / "_revisao",
        )
        return {
            "aprovado": False,
            "status": "em_revisao",
            "pasta_revisao": str(pasta_rev),
            "pasta_feitos": str(feitos_pasta),
            "qa_final": rel_qa_final,
        }

    # Etapa 7: Classificação e Estoque (V001...)
    registro_estoque = registrar_video_no_estoque(
        video_pronto_mp4=final_cta_mp4,
        formato=formato,
        avatar=avatar,
        takes_info=rel_etapa3["takes"],
        duracao_total_s=rel_etapa3["duracao_final_s"],
        pasta_originais_feitos=feitos_pasta,
        lote_origem=falas_data.get("lote_id", ""),
        video_origem_lote=falas_data.get("video_id", nome_pasta),
        root=root,
    )
    return {
        "aprovado": True,
        "status": "pronto_no_estoque",
        "id_estoque": registro_estoque["id"],
        "arquivo_pronto": registro_estoque["arquivo_pronto"],
        "pasta_feitos": str(feitos_pasta),
        "qa_final": rel_qa_final,
        "registro_estoque": registro_estoque,
    }


def reeditar_video_por_id(
    video_id_curto: str,
    texto_cta: str | None = None,
    pos_y_legenda: int = 1240,
    y_base_cta: int = 1480,
    usar_flash_branco: bool = True,
    frames_flash: int = 2,
    crf: int = 20,
    root: Path = ROOT_DIR,
) -> dict[str, Any]:
    """
    Etapa 8 da Edição: Reedita qualquer vídeo pelo ID curto (ex: 'V001') sem gerar nada de novo no Flow.
    Puxa os originais de _feitos/, refaz corte / montagem / legenda / CTA com os ajustes pedidos
    e substitui o arquivo pronto em prontos/<formato>/.
    """
    estoque_path = root / "estoque.json"
    estoque = carregar_estoque(estoque_path)

    alvo = next(
        (v for v in estoque.get("videos", []) if v["id"].upper() == video_id_curto.upper()),
        None,
    )
    if alvo is None:
        raise KeyError(f"Vídeo '{video_id_curto}' não encontrado em {estoque_path}.")

    pasta_feitos = Path(alvo["pasta_originais_feitos"])
    if not pasta_feitos.is_dir():
        raise FileNotFoundError(f"Pasta de originais em _feitos/ não encontrada: {pasta_feitos}")

    staging_dir = root / "_staging_edicao" / f"reedicao_{alvo['id']}"
    if staging_dir.exists():
        shutil.rmtree(staging_dir)
    staging_dir.mkdir(parents=True, exist_ok=True)

    falas_path = pasta_feitos / "falas.json"
    falas_data = json.loads(falas_path.read_text(encoding="utf-8")) if falas_path.is_file() else {}
    cta_final = texto_cta or falas_data.get("cta_texto", "COMMENT YES")

    rel_etapa2 = processar_transcricao_e_cortes_pasta(
        pasta_entregue=pasta_feitos,
        pasta_trabalho=staging_dir,
    )
    clipes_cortados = sorted((staging_dir / "cortados").glob("*.mp4"), key=lambda p: int(p.stem))
    montado_mp4 = staging_dir / "montado_reedicao.mp4"
    rel_etapa3 = montar_video(
        clipes_cortados=clipes_cortados,
        destino_mp4=montado_mp4,
        formato=alvo["formato"],
        usar_flash_branco=usar_flash_branco,
        frames_flash=frames_flash,
        fps=30,
        crf=crf,
        sincronizar_resolve=True,
    )

    palavras_montado: list[dict[str, Any]] = []
    takes_etapa3 = rel_etapa3.get("takes", [])
    clipes_etapa2 = rel_etapa2.get("clipes", [])
    for idx_t, c_info in enumerate(clipes_etapa2):
        offset_t = float(takes_etapa3[idx_t]["inicio_s"]) if idx_t < len(takes_etapa3) else 0.0
        for w in c_info.get("palavras", []):
            palavras_montado.append(
                {
                    "palavra": w["palavra"],
                    "inicio": round(float(w["inicio"]) + offset_t, 3),
                    "fim": round(float(w["fim"]) + offset_t, 3),
                }
            )

    ass_path = staging_dir / "legenda_reedicao.ass"
    legendado_mp4 = staging_dir / "legendado_reedicao.mp4"
    rel_etapa4 = legendar_video_montado(
        video_montado=montado_mp4,
        destino_ass=ass_path,
        destino_mp4=legendado_mp4,
        pos_y=pos_y_legenda,
        palavras_precalculadas=palavras_montado if palavras_montado else None,
    )

    inicio_ultimo_take = rel_etapa3["takes"][-1]["inicio_s"]
    final_cta_mp4 = staging_dir / "final_reedicao_cta.mp4"
    rel_etapa5 = aplicar_cta_ultimo_take(
        video_entrada=legendado_mp4,
        video_saida=final_cta_mp4,
        inicio_ultimo_take_s=inicio_ultimo_take,
        texto_cta=cta_final,
        y_base=y_base_cta,
    )

    rel_qa = avaliar_qa_final_video(
        video_pronto_path=final_cta_mp4,
        ass_path=ass_path,
        relatorio_etapa2=rel_etapa2,
        duracao_esperada_s=rel_etapa3["duracao_final_s"],
    )
    if not rel_qa["aprovado"]:
        raise RuntimeError(f"Reedição de {video_id_curto} reprovou no QA Final: {rel_qa['motivos_reprovacao']}")

    arquivo_pronto = Path(alvo["arquivo_pronto"])
    arquivo_pronto.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(final_cta_mp4, arquivo_pronto)

    alvo["duracao_total_s"] = round(float(rel_etapa3["duracao_final_s"]), 3)
    alvo["takes"] = rel_etapa3["takes"]
    alvo["atualizado_em"] = datetime.now().isoformat(timespec="seconds")
    alvo["ultima_reedicao"] = {
        "data": alvo["atualizado_em"],
        "texto_cta": cta_final,
        "pos_y_legenda": pos_y_legenda,
        "y_base_cta": y_base_cta,
        "usar_flash_branco": usar_flash_branco,
        "frames_flash": frames_flash,
    }
    salvar_estoque(estoque, estoque_path)

    return {
        "id": alvo["id"],
        "reeditado_com_sucesso": True,
        "arquivo_pronto_substituido": str(arquivo_pronto),
        "originais_usados": str(pasta_feitos),
        "ajustes_aplicados": alvo["ultima_reedicao"],
        "qa_final": rel_qa,
    }


def main() -> None:
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Reedita qualquer vídeo do estoque pelo ID (ex: V001) sem usar o Flow.")
    parser.add_argument("id", help="ID curto do vídeo no estoque (ex: V001)")
    parser.add_argument("--cta", default=None, help="Novo texto do CTA no último take (ex: 'COMMENT SODA')")
    parser.add_argument("--pos-y-legenda", type=int, default=1240, help="Posição Y da legenda karaokê (padrão: 1240)")
    parser.add_argument("--pos-y-cta", type=int, default=1480, help="Posição Y base da caixa de CTA (padrão: 1480)")
    parser.add_argument("--sem-flash", action="store_true", help="Desativa o flash branco nas transições")
    parser.add_argument("--frames-flash", type=int, default=2, help="Quantidade de frames do flash branco (2 ou 3)")
    args = parser.parse_args()

    res = reeditar_video_por_id(
        video_id_curto=args.id,
        texto_cta=args.cta,
        pos_y_legenda=args.pos_y_legenda,
        y_base_cta=args.pos_y_cta,
        usar_flash_branco=not args.sem_flash,
        frames_flash=args.frames_flash,
    )
    print(json.dumps(res, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
