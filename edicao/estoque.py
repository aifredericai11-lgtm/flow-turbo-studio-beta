"""
Edição — Etapa 7: Classificação, Estoque e Painel Rápido (edicao/estoque.py).
Regras:
- Dá um ID curto sequencial para o vídeo aprovado (V001, V002...).
- Salva em prontos/<formato>/V001_<formato>_<avatar>.mp4.
- Registra em estoque.json (ID, formato, avatar, takes, durações, status disponivel / usado / bloqueado, conta em que subiu, pasta em _feitos/).
- Respeita bloqueados.json: formato ou avatar bloqueado não entra em lote novo.
- Painel rápido: quantos vídeos prontos por formato, quantos em revisão, quantos já usados.
"""

from __future__ import annotations

import json
import re
import shutil
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

_ESTOQUE_LOCK = threading.Lock()

from forja.estrutura import (
    BLOQUEADOS_JSON,
    ESTOQUE_JSON,
    FEITOS_DIR,
    PRONTOS_DIR,
    REVISAO_DIR,
    ROOT_DIR,
    carregar_bloqueados,
    item_esta_bloqueado,
)


def _slug_curto(texto: str, max_len: int = 28) -> str:
    limpo = re.sub(r"[^a-zA-Z0-9]+", "_", texto.strip().lower()).strip("_")
    return limpo[:max_len].strip("_") or "padrao"


def carregar_estoque(estoque_path: Path = ESTOQUE_JSON) -> dict[str, Any]:
    if not estoque_path.is_file():
        dados = {"proximo_numero": 1, "videos": []}
        estoque_path.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
        return dados
    return json.loads(estoque_path.read_text(encoding="utf-8"))


def salvar_estoque(dados: dict[str, Any], estoque_path: Path = ESTOQUE_JSON) -> None:
    estoque_path.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")


def registrar_video_no_estoque(
    video_pronto_mp4: Path,
    formato: str,
    avatar: str,
    takes_info: list[dict[str, Any]],
    duracao_total_s: float,
    pasta_originais_feitos: Path,
    lote_origem: str = "",
    video_origem_lote: str = "",
    conta_subida: str = "",
    root: Path = ROOT_DIR,
) -> dict[str, Any]:
    """
    Atribui ID curto (V001, V002...), copia o vídeo final para prontos/<formato>/V001_<formato>_<avatar>.mp4
    e registra todos os metadados em estoque.json.
    """
    estoque_path = root / "estoque.json"
    bloqueados_path = root / "bloqueados.json"
    prontos_root = root / "prontos"

    with _ESTOQUE_LOCK:
        estoque = carregar_estoque(estoque_path)
        bloqueados = carregar_bloqueados(bloqueados_path)
        esta_bloq, _ = item_esta_bloqueado(formato=formato, avatar=avatar, bloqueados=bloqueados)

        num = int(estoque.get("proximo_numero", 1))
        id_curto = f"V{num:03d}"
        estoque["proximo_numero"] = num + 1

        formato_slug = _slug_curto(formato, max_len=36)
        avatar_slug = _slug_curto(avatar, max_len=24)

        pasta_formato = prontos_root / formato_slug
        pasta_formato.mkdir(parents=True, exist_ok=True)

        nome_arquivo = f"{id_curto}_{formato_slug}_{avatar_slug}.mp4"
        destino_pronto = pasta_formato / nome_arquivo
        shutil.copy2(video_pronto_mp4, destino_pronto)

        status_inicial = "bloqueado" if esta_bloq else "disponivel"
        registro = {
            "id": id_curto,
            "formato": formato,
            "formato_slug": formato_slug,
            "avatar": avatar,
            "avatar_slug": avatar_slug,
            "arquivo_pronto": str(destino_pronto),
            "pasta_originais_feitos": str(pasta_originais_feitos),
            "lote_origem": lote_origem,
            "video_origem_lote": video_origem_lote,
            "qtd_takes": len(takes_info),
            "takes": takes_info,
            "duracao_total_s": round(float(duracao_total_s), 3),
            "status": status_inicial,
            "conta_subida": conta_subida,
            "criado_em": datetime.now().isoformat(timespec="seconds"),
            "atualizado_em": datetime.now().isoformat(timespec="seconds"),
        }
        estoque.setdefault("videos", []).append(registro)
        salvar_estoque(estoque, estoque_path)
        return registro


def atualizar_status_estoque(
    video_id_curto: str,
    novo_status: str,
    conta_subida: str | None = None,
    estoque_path: Path = ESTOQUE_JSON,
) -> dict[str, Any]:
    """Atualiza o status de um vídeo no estoque ('disponivel', 'usado', 'bloqueado') e a conta em que subiu."""
    if novo_status not in ("disponivel", "usado", "bloqueado"):
        raise ValueError(f"Status inválido: {novo_status}")

    estoque = carregar_estoque(estoque_path)
    for v in estoque.get("videos", []):
        if v["id"].upper() == video_id_curto.upper():
            v["status"] = novo_status
            if conta_subida is not None:
                v["conta_subida"] = conta_subida
            v["atualizado_em"] = datetime.now().isoformat(timespec="seconds")
            salvar_estoque(estoque, estoque_path)
            return v
    raise KeyError(f"Vídeo '{video_id_curto}' não encontrado no estoque.json.")


def bloquear_formato_ou_avatar(
    formato: str | None = None,
    avatar: str | None = None,
    motivo: str = "Bloqueado manualmente",
    root: Path = ROOT_DIR,
) -> dict[str, Any]:
    """
    Adiciona um formato ou avatar ao bloqueados.json (para nunca mais entrar em lote novo)
    e marca como 'bloqueado' os vídeos correspondentes no estoque.json.
    """
    bloq_path = root / "bloqueados.json"
    estoque_path = root / "estoque.json"
    bloqueados = carregar_bloqueados(bloq_path)

    if formato and formato not in bloqueados["formatos_bloqueados"]:
        bloqueados["formatos_bloqueados"].append(formato)
    if avatar and avatar not in bloqueados["avatares_bloqueados"]:
        bloqueados["avatares_bloqueados"].append(avatar)

    bloqueados.setdefault("historico", []).append(
        {
            "formato": formato,
            "avatar": avatar,
            "motivo": motivo,
            "data": datetime.now().isoformat(timespec="seconds"),
        }
    )
    bloq_path.write_text(json.dumps(bloqueados, ensure_ascii=False, indent=2), encoding="utf-8")

    estoque = carregar_estoque(estoque_path)
    for v in estoque.get("videos", []):
        if (formato and v.get("formato") == formato) or (avatar and v.get("avatar") == avatar):
            v["status"] = "bloqueado"
            v["atualizado_em"] = datetime.now().isoformat(timespec="seconds")
    salvar_estoque(estoque, estoque_path)
    return bloqueados


def gerar_painel_estoque(root: Path = ROOT_DIR) -> dict[str, Any]:
    """
    Painel rápido do estoque:
    - Quantos vídeos prontos (disponíveis) por formato;
    - Quantos já usados;
    - Quantos bloqueados;
    - Quantos em revisão (_revisao/).
    """
    estoque = carregar_estoque(root / "estoque.json")
    revisao_dir = root / "_revisao"
    videos = estoque.get("videos", [])

    prontos_por_formato: dict[str, int] = {}
    usados_por_formato: dict[str, int] = {}
    qtd_disponiveis = 0
    qtd_usados = 0
    qtd_bloqueados = 0

    for v in videos:
        fmt = v.get("formato", "indefinido")
        st = v.get("status", "disponivel")
        if st == "disponivel":
            qtd_disponiveis += 1
            prontos_por_formato[fmt] = prontos_por_formato.get(fmt, 0) + 1
        elif st == "usado":
            qtd_usados += 1
            usados_por_formato[fmt] = usados_por_formato.get(fmt, 0) + 1
        elif st == "bloqueado":
            qtd_bloqueados += 1

    pastas_revisao = (
        [p.name for p in sorted(revisao_dir.iterdir()) if p.is_dir() and not p.name.startswith(".")]
        if revisao_dir.is_dir()
        else []
    )

    return {
        "total_registrados": len(videos),
        "disponiveis": qtd_disponiveis,
        "usados": qtd_usados,
        "bloqueados": qtd_bloqueados,
        "em_revisao": len(pastas_revisao),
        "prontos_por_formato": prontos_por_formato,
        "usados_por_formato": usados_por_formato,
        "itens_em_revisao": pastas_revisao,
    }
