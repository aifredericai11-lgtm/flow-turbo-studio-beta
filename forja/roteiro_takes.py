"""
Forja — Etapa 3: Roteiro dos Takes.
Regras:
- Divida a fala em takes de até ~8 s, com 21 a 24 palavras por take, sem passar o ritmo do viral (teto ~3,5 palavras/s).
- Nunca corte frase no meio. Junte frases curtas para gastar MENOS takes: cada take é crédito.
- O último take traz o CTA.
- Opções: --troca "X=>Y|A=>B" (trocar palavras da copy) e --falas "take1||take2" (falas prontas).
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


def aplicar_trocas(texto: str, trocas_str: str | None) -> str:
    """Aplica substituições no formato 'X=>Y|A=>B' preservando espaçamento."""
    if not trocas_str or not trocas_str.strip():
        return texto
    resultado = texto
    pares = [p.strip() for p in trocas_str.split("|") if "=>" in p]
    for par in pares:
        origem, destino = par.split("=>", 1)
        origem, destino = origem.strip(), destino.strip()
        if not origem:
            continue
        padrao = re.compile(re.escape(origem), re.IGNORECASE)
        resultado = padrao.sub(destino, resultado)
    return resultado


def dividir_em_frases(texto: str) -> list[str]:
    """Divide o texto em frases completas sem jamais cortar frase no meio."""
    limpo = re.sub(r"\s+", " ", texto.strip())
    if not limpo:
        return []
    partes = re.split(r"(?<=[.!?])\s+", limpo)
    return [p.strip() for p in partes if p.strip()]


def _contar_palavras(frase: str) -> int:
    return len(re.findall(r"[A-Za-z0-9']+", frase))


def _particionar_frases_otimo(
    frases: list[str],
    ritmo_alvo: float,
    min_ideal: int = 21,
    max_palavras: int = 24,
    max_segundos: float = 8.0,
) -> list[str]:
    """
    Agrupa frases completas (sem jamais cortar frase no meio) minimizando o número total de takes
    (economia de créditos) e priorizando takes na faixa de 21 a 24 palavras e <= 8s.
    """
    if not frases:
        return []
    n = len(frases)
    contagens = [_contar_palavras(f) for f in frases]

    # DP: melhor[i] = (num_takes, penalidade, lista_de_blocos) para frases[i:]
    melhor: dict[int, tuple[int, float, list[str]]] = {n: (0, 0.0, [])}

    for i in range(n - 1, -1, -1):
        opcoes: list[tuple[int, float, list[str]]] = []
        palavras_acum = 0
        for j in range(i, n):
            palavras_acum += contagens[j]
            duracao = palavras_acum / ritmo_alvo
            # Permite se for uma única frase ou se respeitar os tetos de palavras (<=24) e duração (<=8s)
            if j > i and (palavras_acum > max_palavras or duracao > max_segundos):
                break
            bloco_txt = " ".join(frases[i : j + 1])
            # Bônus forte quando o take cai na faixa ideal de 21..24 palavras (<= 8s)
            if min_ideal <= palavras_acum <= max_palavras:
                penalidade_bloco = -15.0
            elif palavras_acum < min_ideal:
                penalidade_bloco = float(min_ideal - palavras_acum)
            else:
                penalidade_bloco = float((palavras_acum - max_palavras) * 5)

            sub_takes, sub_pen, sub_blocos = melhor[j + 1]
            opcoes.append((1 + sub_takes, penalidade_bloco + sub_pen, [bloco_txt] + sub_blocos))

        melhor[i] = min(opcoes, key=lambda x: (x[0], x[1]))

    return melhor[0][2]


def gerar_roteiro_takes(
    analise_viral: dict[str, Any],
    troca: str | None = None,
    falas_prontas: str | None = None,
    max_palavras_take: int = 24,
    min_ideal_palavras: int = 21,
    max_segundos_take: float = 8.0,
    teto_ritmo_pps: float = 3.5,
) -> dict[str, Any]:
    """
    Gera o roteiro dividido em takes econômicos de até ~8s (21-24 palavras por take quando possível,
    nunca cortando frase no meio e garantindo o CTA no último take).
    """
    ritmo_viral = float(analise_viral.get("metricas_ritmo", {}).get("palavras_por_segundo", 3.18))
    ritmo_alvo = min(ritmo_viral, teto_ritmo_pps)
    if ritmo_alvo <= 0:
        ritmo_alvo = 3.0

    if falas_prontas and falas_prontas.strip():
        blocos_brutos = [b.strip() for b in falas_prontas.split("||") if b.strip()]
        blocos = [aplicar_trocas(b, troca) for b in blocos_brutos]
    else:
        texto_original = analise_viral.get("transcricao", {}).get("texto", "")
        texto_modificado = aplicar_trocas(texto_original, troca)
        frases = dividir_em_frases(texto_modificado)
        blocos = _particionar_frases_otimo(
            frases,
            ritmo_alvo=ritmo_alvo,
            min_ideal=min_ideal_palavras,
            max_palavras=max_palavras_take,
            max_segundos=max_segundos_take,
        )

    takes = []
    total_takes = len(blocos)
    for i, fala in enumerate(blocos, start=1):
        palavras = _contar_palavras(fala)
        duracao_est = round(min(max_segundos_take, max(2.5, palavras / ritmo_alvo)), 2)
        ritmo_take = round(palavras / duracao_est, 2)
        if i == 1:
            papel = "hook"
        elif i == total_takes:
            papel = "cta"
        else:
            papel = "body"

        takes.append(
            {
                "take": i,
                "papel": papel,
                "fala": fala,
                "palavras": palavras,
                "duracao_estimada_s": duracao_est,
                "ritmo_palavras_por_s": min(ritmo_take, teto_ritmo_pps),
                "dentro_da_meta_21_24": min_ideal_palavras <= palavras <= max_palavras_take,
            }
        )

    roteiro = {
        "formato": analise_viral.get("formato", "indefinido"),
        "ritmo_viral_pps": ritmo_viral,
        "teto_ritmo_pps": teto_ritmo_pps,
        "opcoes_aplicadas": {
            "troca": troca or "",
            "falas_prontas": bool(falas_prontas),
        },
        "qtd_takes": total_takes,
        "total_palavras": sum(t["palavras"] for t in takes),
        "duracao_total_estimada_s": round(sum(t["duracao_estimada_s"] for t in takes), 2),
        "cta_palavra": analise_viral.get("cena", {}).get("cta", {}).get("palavra_chave", "COMMENT YES"),
        "takes": takes,
    }
    return roteiro


def main() -> None:
    parser = argparse.ArgumentParser(description="Forja Etapa 3 — Roteiro dos Takes")
    parser.add_argument("--analise", required=True, help="Caminho do arquivo <viral>_analise.json")
    parser.add_argument("--troca", default="", help='Ex: "thighs=>groin|sleep=>rest"')
    parser.add_argument("--falas", default="", help='Ex: "fala take 1||fala take 2"')
    parser.add_argument("--saida", default="", help="Caminho para salvar o roteiro.json")
    args = parser.parse_args()

    analise_path = Path(args.analise).resolve()
    analise_data = json.loads(analise_path.read_text(encoding="utf-8"))
    roteiro = gerar_roteiro_takes(analise_data, troca=args.troca, falas_prontas=args.falas)

    saida_path = Path(args.saida).resolve() if args.saida else analise_path.with_name(f"{analise_path.stem}_roteiro.json")
    saida_path.write_text(json.dumps(roteiro, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(roteiro, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
