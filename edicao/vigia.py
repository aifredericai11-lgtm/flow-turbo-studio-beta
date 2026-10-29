"""
Edição — Etapa 1: VIGIA.
- Um processo permanente observa a pasta entregues/.
- Quando aparece uma pasta nova completa (todos os clipes 1.mp4..N.mp4 + falas.json), ele edita.
- Uma pasta por vez; se der erro, registra no log e segue para a próxima.
- SEGURANÇA: Nunca apaga arquivos originais. Reprovado vai para _reprovados/;
  o original fica em _feitos/ depois de editado.
"""

from __future__ import annotations

import json
import re
import shutil
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from edicao.transcricao_cortes import processar_transcricao_e_cortes_pasta
from forja.estrutura import ROOT_DIR, inicializar_estrutura, mover_para_reprovados


class VigiaEdicao:
    def __init__(self, root: Path = ROOT_DIR):
        self.root = root
        self.paths = inicializar_estrutura(root)
        self.entregues_dir = self.paths["entregues"]
        self.feitos_dir = self.paths["feitos"]
        self.reprovados_dir = self.paths["reprovados"]
        self.staging_dir = self.root / "_staging_edicao"
        self.staging_dir.mkdir(parents=True, exist_ok=True)
        self.log_path = self.paths["logs"] / "vigia.log"

    def log(self, msg: str, nivel: str = "INFO") -> str:
        agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        linha = f"[{agora}] [{nivel}] [VIGIA] {msg}"
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(linha + "\n")
        print(linha, flush=True)
        return linha

    def pasta_esta_completa(self, pasta: Path) -> tuple[bool, str]:
        """
        Verifica se a subpasta dentro de entregues/ contém falas.json válido
        e todos os clipes 1.mp4..N.mp4 completos (tamanho > 1024 bytes).
        """
        if not pasta.is_dir() or pasta.name.startswith(".") or pasta.name.startswith("_"):
            return False, "Pasta ignorada"

        falas_file = pasta / "falas.json"
        if not falas_file.is_file() or falas_file.stat().st_size == 0:
            return False, "Aguardando falas.json"

        try:
            falas_data = json.loads(falas_file.read_text(encoding="utf-8"))
        except Exception as e:
            return False, f"falas.json inválido ou em escrita: {e}"

        # Determina quantos clipes são esperados
        qtd_esperada = 0
        if isinstance(falas_data.get("takes"), list):
            qtd_esperada = len(falas_data["takes"])
        elif isinstance(falas_data.get("falas"), list):
            qtd_esperada = len(falas_data["falas"])
        elif isinstance(falas_data.get("fala"), list):
            qtd_esperada = len(falas_data["fala"])
        elif isinstance(falas_data.get("qtd_clipes"), int):
            qtd_esperada = falas_data["qtd_clipes"]

        clipes_numerados = sorted(
            [p for p in pasta.glob("*.mp4") if re.fullmatch(r"\d+\.mp4", p.name)],
            key=lambda p: int(p.stem),
        )
        if not clipes_numerados:
            return False, "Nenhum clipe 1.mp4..N.mp4 presente ainda"

        if qtd_esperada > 0 and len(clipes_numerados) < qtd_esperada:
            return False, f"Clipes incompletos ({len(clipes_numerados)}/{qtd_esperada})"

        # Verifica sequência contínua 1..N e se nenhum arquivo está vazio
        for idx, clipe in enumerate(clipes_numerados, start=1):
            if int(clipe.stem) != idx:
                return False, f"Falta o clipe {idx}.mp4 na sequência"
            if clipe.stat().st_size < 1024:
                return False, f"Clipe {clipe.name} ainda está sendo gravado (tamanho < 1KB)"

        return True, f"Completa ({len(clipes_numerados)} clipes + falas.json)"

    def mover_para_feitos(self, pasta: Path) -> Path:
        """Move a pasta original intacta para _feitos/ após edição."""
        self.feitos_dir.mkdir(parents=True, exist_ok=True)
        carimbo = datetime.now().strftime("%Y%m%d_%H%M%S")
        destino = (
            self.feitos_dir / f"{pasta.name}_{carimbo}"
            if (self.feitos_dir / pasta.name).exists()
            else self.feitos_dir / pasta.name
        )
        shutil.move(str(pasta), str(destino))
        return destino

    def processar_uma_pasta(
        self,
        pasta: Path,
        pipeline_fn: Callable[[Path, Path], dict[str, Any]] | None = None,
        mover_ao_finalizar: bool = True,
    ) -> dict[str, Any]:
        """
        Processa 1 pasta completa de entregues/ por vez.
        Se der erro, registra no log e segue para a próxima sem travar.
        """
        self.log(f"Iniciando processamento da pasta: {pasta.name}")
        trabalho_dir = self.staging_dir / pasta.name
        trabalho_dir.mkdir(parents=True, exist_ok=True)

        if pipeline_fn is None:
            from edicao.reeditar import processar_entrega_completa

            try:
                resultado = processar_entrega_completa(pasta_entregue=pasta, root=self.root)
                self.log(
                    f"Pasta {pasta.name} finalizada pelo Vigia -> Status: {resultado.get('status')} | ID Estoque: {resultado.get('id_estoque', '-')}"
                )
                return {"status": "ok", "pasta": pasta.name, "resultado": resultado}
            except Exception as exc:
                tb = traceback.format_exc()
                self.log(f"ERRO ao processar {pasta.name}: {exc}\n{tb.splitlines()[-1]}", nivel="ERROR")
                dest_erro = mover_para_reprovados(pasta, f"Erro de execução na esteira: {exc}", root=self.root)
                return {"status": "erro", "pasta": pasta.name, "erro": str(exc), "destino_original": str(dest_erro)}

        fn = pipeline_fn
        try:
            resultado = fn(pasta, trabalho_dir)
            if resultado.get("reprovado"):
                motivo = resultado.get("motivo_reprovacao", "Reprovado no controle de qualidade")
                dest_rep = mover_para_reprovados(pasta, motivo, root=self.root)
                self.log(f"Pasta {pasta.name} REPROVADA -> {dest_rep.name} ({motivo})", nivel="WARN")
                resultado["destino_original"] = str(dest_rep)
            else:
                if resultado.get("marcado_para_revisao"):
                    self.log(
                        f"Pasta {pasta.name} marcada para revisão: {resultado.get('motivos_revisao')}",
                        nivel="WARN",
                    )
                if mover_ao_finalizar:
                    dest_feito = self.mover_para_feitos(pasta)
                    self.log(f"Pasta {pasta.name} processada com sucesso. Original movido para _feitos/{dest_feito.name}")
                    resultado["destino_original"] = str(dest_feito)
                else:
                    self.log(f"Pasta {pasta.name} validada (modo etapa de teste, original mantido).")
            return {"status": "ok", "pasta": pasta.name, "resultado": resultado}
        except Exception as exc:
            tb = traceback.format_exc()
            self.log(f"ERRO ao processar {pasta.name}: {exc}\n{tb.splitlines()[-1]}", nivel="ERROR")
            dest_erro = mover_para_reprovados(pasta, f"Erro de execução na esteira: {exc}", root=self.root)
            return {"status": "erro", "pasta": pasta.name, "erro": str(exc), "destino_original": str(dest_erro)}

    def varrer_uma_vez(self, mover_ao_finalizar: bool = True, max_workers: int = 4) -> list[dict[str, Any]]:
        """Verifica entregues/ e processa as pastas completas (em paralelo quando há múltiplas entregas de lote)."""
        from concurrent.futures import ThreadPoolExecutor

        subpastas = sorted([p for p in self.entregues_dir.iterdir() if p.is_dir()], key=lambda p: p.name)
        prontas: list[Path] = []
        for sub in subpastas:
            completa, detalhe = self.pasta_esta_completa(sub)
            if not completa:
                self.log(f"Ignorando {sub.name} por enquanto: {detalhe}", nivel="DEBUG")
                continue
            prontas.append(sub)

        if not prontas:
            return []
        if len(prontas) == 1 or max_workers <= 1:
            return [self.processar_uma_pasta(sub, mover_ao_finalizar=mover_ao_finalizar) for sub in prontas]

        with ThreadPoolExecutor(max_workers=min(max_workers, len(prontas))) as pool:
            return list(pool.map(lambda s: self.processar_uma_pasta(s, mover_ao_finalizar=mover_ao_finalizar), prontas))

    def rodar_permanente(self, intervalo_s: float = 3.0) -> None:
        """Loop permanente observando entregues/."""
        self.log(f"Vigia iniciado. Observando: {self.entregues_dir}")
        while True:
            try:
                self.varrer_uma_vez(mover_ao_finalizar=True)
            except Exception as exc:
                self.log(f"Erro no ciclo do Vigia: {exc}", nivel="ERROR")
            time.sleep(intervalo_s)
