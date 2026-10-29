"""
Forja — Etapa 1: Estrutura, Fila, Logs e Segurança.
Regras de Segurança:
- Nunca cria contas nem digita senhas/códigos.
- Nunca apaga arquivos: o que for ruim vai para _reprovados/.
- Pausa progressiva (3 -> 6 -> 10 min) se o Flow avisar "atividade incomum".
"""

from __future__ import annotations

import json
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent

DIRS = {
    "virais": ROOT_DIR / "virais",
    "bases": ROOT_DIR / "bases",
    "lotes": ROOT_DIR / "lotes",
    "entregues": ROOT_DIR / "entregues",
    "editados": ROOT_DIR / "editados",
    "feitos": ROOT_DIR / "_feitos",
    "reprovados": ROOT_DIR / "_reprovados",
    "logs": ROOT_DIR / "logs",
}

FILA_PATH = ROOT_DIR / "fila.json"
BACKOFF_MINUTES = [3, 6, 10]


def inicializar_estrutura(root: Path = ROOT_DIR) -> dict[str, Path]:
    """Garante que todas as pastas da Forja e da Edição existam, além do fila.json inicial."""
    paths = {
        "virais": root / "virais",
        "bases": root / "bases",
        "lotes": root / "lotes",
        "entregues": root / "entregues",
        "editados": root / "editados",
        "feitos": root / "_feitos",
        "reprovados": root / "_reprovados",
        "logs": root / "logs",
    }
    for p in paths.values():
        p.mkdir(parents=True, exist_ok=True)

    fila_file = root / "fila.json"
    if not fila_file.exists():
        fila_padrao = [
            {
                "nome": "lote_001_baking_soda",
                "viral": "virais/viral_ref_01.mp4",
                "qtd": 1,
                "opcoes": {
                    "formato": "aplicando_bicarbonato_na_coxa",
                    "troca": "",
                    "falas": "",
                    "angulo": True,
                    "base": None,
                    "so_frame1": False,
                },
            }
        ]
        fila_file.write_text(json.dumps(fila_padrao, ensure_ascii=False, indent=2), encoding="utf-8")

    return paths


class BatchLogger:
    """Um log por lote, com hora em cada linha."""

    def __init__(self, lote_id: str, root: Path = ROOT_DIR):
        self.lote_id = lote_id
        self.lote_dir = root / "lotes" / lote_id
        self.lote_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir = root / "logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.lote_log_path = self.lote_dir / "lote.log"
        self.central_log_path = self.log_dir / f"{lote_id}.log"

    def log(self, mensagem: str, nivel: str = "INFO") -> str:
        agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        linha = f"[{agora}] [{nivel}] [{self.lote_id}] {mensagem}"
        with self.lote_log_path.open("a", encoding="utf-8") as f1:
            f1.write(linha + "\n")
        with self.central_log_path.open("a", encoding="utf-8") as f2:
            f2.write(linha + "\n")
        return linha


class FlowSafetyGuard:
    """Controle de segurança de limites do Google Flow (3 -> 6 -> 10 min crescendo)."""

    def __init__(self, logger: BatchLogger):
        self.logger = logger
        self.strikes = 0

    def registrar_atividade_incomum(self, detalhe: str = "atividade incomum detectada", dry_run: bool = False) -> int:
        minutos = BACKOFF_MINUTES[min(self.strikes, len(BACKOFF_MINUTES) - 1)]
        self.strikes += 1
        self.logger.log(
            f"ALERTA FLOW ('{detalhe}'): Pausando por {minutos} min (strike #{self.strikes}). Nunca contornar aviso.",
            nivel="WARN",
        )
        if not dry_run:
            time.sleep(minutos * 60)
        return minutos

    def resetar(self) -> None:
        self.strikes = 0


def criar_pasta_video_lote(
    lote_id: str,
    video_id: str,
    falas_data: dict[str, Any],
    root: Path = ROOT_DIR,
) -> Path:
    """Cria lotes/<id>/V01..Vn/ com falas.json estruturado."""
    v_dir = root / "lotes" / lote_id / video_id
    v_dir.mkdir(parents=True, exist_ok=True)
    falas_path = v_dir / "falas.json"
    falas_path.write_text(json.dumps(falas_data, ensure_ascii=False, indent=2), encoding="utf-8")
    return v_dir


def salvar_resumo_lote(
    lote_id: str,
    entregues: int,
    descartados: int,
    clipes_usados: int,
    minutos: float,
    extras: dict[str, Any] | None = None,
    root: Path = ROOT_DIR,
) -> Path:
    """Salva lotes/<id>/resumo.json com entregues, descartados, clipes usados e minutos."""
    lote_dir = root / "lotes" / lote_id
    lote_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "lote_id": lote_id,
        "entregues": entregues,
        "descartados": descartados,
        "clipes_usados": clipes_usados,
        "minutos": round(minutos, 2),
        "atualizado_em": datetime.now().isoformat(timespec="seconds"),
    }
    if extras:
        payload.update(extras)
    resumo_path = lote_dir / "resumo.json"
    resumo_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return resumo_path


def mover_para_reprovados(origem: Path, motivo: str, root: Path = ROOT_DIR) -> Path:
    """Move pasta ou arquivo reprovado para _reprovados/ sem jamais apagar nada."""
    reprovados_dir = root / "_reprovados"
    reprovados_dir.mkdir(parents=True, exist_ok=True)
    carimbo = datetime.now().strftime("%Y%m%d_%H%M%S")
    destino = reprovados_dir / f"{origem.name}_{carimbo}" if (reprovados_dir / origem.name).exists() else reprovados_dir / origem.name

    shutil.move(str(origem), str(destino))
    if destino.is_dir():
        motivo_file = destino / "motivo_reprovacao.txt"
    else:
        motivo_file = destino.with_suffix(destino.suffix + ".motivo.txt")
    motivo_file.write_text(
        f"Data: {datetime.now().isoformat(timespec='seconds')}\nOrigem: {origem}\nMotivo: {motivo}\n",
        encoding="utf-8",
    )
    return destino


# Constantes de caminho compartilhadas entre Forja e Edição
LOTES_DIR = ROOT_DIR / "lotes"
ENTREGUES_DIR = ROOT_DIR / "entregues"
FEITOS_DIR = ROOT_DIR / "_feitos"
REPROVADOS_DIR = ROOT_DIR / "_reprovados"
REVISAO_DIR = ROOT_DIR / "_revisao"
PRONTOS_DIR = ROOT_DIR / "prontos"
STAGING_EDICAO_DIR = ROOT_DIR / "_staging_edicao"
ESTOQUE_JSON = ROOT_DIR / "estoque.json"
BLOQUEADOS_JSON = ROOT_DIR / "bloqueados.json"


def carregar_bloqueados(bloqueados_path: Path = BLOQUEADOS_JSON) -> dict[str, Any]:
    if not bloqueados_path.is_file():
        dados = {"formatos_bloqueados": [], "avatares_bloqueados": [], "historico": []}
        bloqueados_path.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
        return dados
    return json.loads(bloqueados_path.read_text(encoding="utf-8"))


def item_esta_bloqueado(
    formato: str = "",
    avatar: str = "",
    bloqueados: dict[str, Any] | None = None,
) -> tuple[bool, str]:
    dados = bloqueados if bloqueados is not None else carregar_bloqueados()
    fmt_list = [f.lower() for f in dados.get("formatos_bloqueados", [])]
    av_list = [a.lower() for a in dados.get("avatares_bloqueados", [])]

    if formato and formato.lower() in fmt_list:
        return True, f"Formato bloqueado em bloqueados.json: '{formato}'"
    if avatar and any(a in avatar.lower() for a in av_list if a):
        return True, f"Avatar bloqueado em bloqueados.json: '{avatar}'"
    return False, ""


def atualizar_status_video_fila(
    fila_path: Path,
    video_id: str,
    status: str,
    takes_prontos: list[int] | None = None,
    erro: str | None = None,
) -> None:
    if not fila_path.is_file():
        return
    dados = json.loads(fila_path.read_text(encoding="utf-8"))
    videos = dados.get("videos", []) if isinstance(dados, dict) else []
    for v in videos:
        if v.get("video_id") == video_id:
            v["status"] = status
            if takes_prontos is not None:
                v["takes_prontos"] = takes_prontos
            if erro is not None:
                v["erro"] = erro
            v["atualizado_em"] = datetime.now().isoformat(timespec="seconds")
            break
    if isinstance(dados, dict):
        fila_path.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")

