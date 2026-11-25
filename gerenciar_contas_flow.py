#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
GERENCIADOR OFICIAL DO POOL MULTI-CONTAS GOOGLE FLOW (`gerenciar_contas_flow.py`)
=================================================================================
Como funciona cada slot de conta:
- Slot 1 -> Porta CDP `:9225` | Perfil `%LOCALAPPDATA%\Google\Chrome\FlowProfile` (Conta principal atual)
- Slot 2 -> Porta CDP `:9226` | Perfil `%LOCALAPPDATA%\Google\Chrome\FlowProfile_02`
- Slot 3 -> Porta CDP `:9227` | Perfil `%LOCALAPPDATA%\Google\Chrome\FlowProfile_03`
- Slot 4 -> Porta CDP `:9228` | Perfil `%LOCALAPPDATA%\Google\Chrome\FlowProfile_04`
- Slot N -> Porta CDP `:(9224 + N)` | Perfil `%LOCALAPPDATA%\Google\Chrome\FlowProfile_0N`

Comandos diretos:
  python gerenciar_contas_flow.py --status           # Mostra todas as contas abertas, e-mail, projeto e créditos
  python gerenciar_contas_flow.py --abrir 2 3 4      # Abre janelas isoladas das Contas 2, 3 e 4 para você logar no Google Flow
  python gerenciar_contas_flow.py --salvar           # Escaneia todas as janelas logadas e salva no pool oficial (`forja/contas_flow.json`)
  python gerenciar_contas_flow.py --subir-todas      # Reabre automaticamente todas as contas já cadastradas após reiniciar o PC
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import urllib.request as _ur

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from forja.flow_rpc_direto import (
    CONTAS_JSON_PATH,
    EXT_DIR,
    carregar_registro_contas_flow,
    ler_status_e_creditos_flow,
    salvar_registro_contas_flow,
    usar_conta_flow,
)
from forja.hw_accel import (
    disparar_chrome_persistente,
    encontrar_chrome_bin,
    pasta_perfil_flow,
)


def _encontrar_chrome_exe() -> str:
    return encontrar_chrome_bin()


def _perfil_e_porta_do_slot(slot: int) -> tuple[int, str]:
    if slot < 1 or slot > 20:
        raise ValueError("Slot deve estar entre 1 e 20.")
    porta = 9224 + slot
    prof = str(pasta_perfil_flow(slot))
    return porta, prof


def _porta_online(porta: int) -> list[dict]:
    try:
        raw = _ur.urlopen(f"http://127.0.0.1:{porta}/json/list", timeout=0.4).read()
        return json.loads(raw)
    except Exception:
        return []


def abrir_slot_flow(slot: int, url_inicial: str = "") -> dict:
    porta, prof = _perfil_e_porta_do_slot(slot)
    os.makedirs(prof, exist_ok=True)
    tabs = _porta_online(porta)
    if tabs:
        print(f"  [Slot {slot:02d} · :{porta}] Já está aberto ({len([t for t in tabs if t.get('type') == 'page'])} abas).")
        return {"slot": slot, "porta": porta, "ja_aberto": True}

    # Busca URL de projeto salva se existir
    if not url_inicial:
        for c in carregar_registro_contas_flow():
            if int(c.get("slot") or 0) == slot and c.get("project_url"):
                url_inicial = str(c["project_url"])
                break
    if not url_inicial:
        url_inicial = "https://flow.google.com/"

    pid = disparar_chrome_persistente(
        porta=porta,
        profile_dir=prof,
        ext_dir=EXT_DIR,
        url_inicial=url_inicial,
    )
    time.sleep(3.2)
    print(f"  [Slot {slot:02d} · :{porta}] Janela persistente aberta ({sys.platform}, PID: {pid})! Perfil: {prof}")
    print(f"     -> Faça login Google nessa janela e abra/crie 1 projeto no Flow (`flow.google.com/project/...`)!")
    return {"slot": slot, "porta": porta, "profile_dir": prof, "url_inicial": url_inicial}


def escanear_e_salvar_pool(salvar: bool = True) -> list[dict]:
    existentes = {int(c.get("slot") or (int(c.get("porta", 9225)) - 9224)): dict(c) for c in carregar_registro_contas_flow()}
    relatorio = []

    print("\n========================================================================================")
    print("  POOL MULTI-CONTAS GOOGLE FLOW — STATUS AO VIVO")
    print("========================================================================================")
    total_creditos = 0
    ativas_ok = 0

    for slot in range(1, 13):
        porta, prof = _perfil_e_porta_do_slot(slot)
        cdp = f"http://127.0.0.1:{porta}"
        tabs = _porta_online(porta)
        if not tabs:
            if slot in existentes:
                c_old = existentes[slot]
                print(f"  [OFFLINE] Slot {slot:02d} (:{porta}) | Salva: {c_old.get('email', '?')} | Último saldo: {c_old.get('ultimo_saldo_creditos', '?')}")
            continue

        page_urls = [str(t.get("url") or "") for t in tabs if t.get("type") == "page"]
        tem_proj = any("/project/" in u for u in page_urls)
        if not tem_proj:
            print(f"  [AGUARDANDO LOGIN/PROJETO] Slot {slot:02d} (:{porta}) aberto, mas ainda não está em `/project/...` (URL atual: {page_urls[0] if page_urls else 'vazia'})")
            print(f"     -> Entre na conta Google e clique em '+ New Project' no Flow para ativar o RPC!")
            continue

        try:
            with usar_conta_flow(cdp):
                st = ler_status_e_creditos_flow(cdp)
            info = st.get("info") or {}
            email = str(info.get("email") or "desconhecido")
            proj_id = str(info.get("projeto") or "")
            if not proj_id:
                for u_p in page_urls:
                    m_p = re.search(r"/project/([0-9a-fA-F-]{36})", u_p)
                    if m_p:
                        proj_id = m_p.group(1)
                        break
            proj_url = f"https://flow.google.com/project/{proj_id}" if proj_id else "https://flow.google.com/"
            cred = st.get("creditos")
            if isinstance(cred, (int, float)):
                total_creditos += int(cred)
            ativas_ok += 1
            print(f"  [ONLINE OK] Slot {slot:02d} (:{porta}) | {email:<30} | Créditos: {str(cred):<6} | Trap: {info.get('armadilha')} | Proj: {proj_id[:8]}...")
            reg = {
                "slot": slot,
                "porta": porta,
                "cdp_url": cdp,
                "profile_dir": prof,
                "email": email,
                "project_id": proj_id,
                "project_url": proj_url,
                "ultimo_saldo_creditos": cred,
                "ativa": True,
            }
            existentes[slot] = reg
            relatorio.append(reg)
        except Exception as exc:
            print(f"  [ERRO RPC] Slot {slot:02d} (:{porta}) -> {exc}")

    if salvar and existentes:
        salvar_registro_contas_flow(list(existentes.values()))
        print("----------------------------------------------------------------------------------------")
        print(f"  Pool salvo em `{CONTAS_JSON_PATH.name}` | Contas Online Prontas: {ativas_ok} | Créditos Somados: {total_creditos}")
    print("========================================================================================\n")
    return relatorio


def menu_interativo() -> None:
    while True:
        escanear_e_salvar_pool(salvar=True)
        print("Escolha uma opção:")
        print("  [1] Abrir NOVA conta para fazer login (ex: digitar `2` ou `2 3 4` abre Contas 2, 3 e 4)")
        print("  [2] Reabrir TODAS as contas já salvas no pool (`contas_flow.json`)")
        print("  [3] Atualizar / Re-escanear contas logadas e salvar")
        print("  [0] Sair")
        op = input("\nOpção: ").strip()
        if op == "0":
            break
        elif op == "1":
            raw_slots = input("Quais números de conta quer abrir? (ex: 2 3 4): ").strip()
            nums = [int(x) for x in re.findall(r"\d+", raw_slots) if int(x) >= 1]
            for s in nums:
                abrir_slot_flow(s)
            input("\nDepois de fazer login e abrir 1 projeto em cada janela, aperte ENTER para validar e salvar...")
        elif op == "2":
            for c in carregar_registro_contas_flow():
                s = int(c.get("slot") or 0)
                if s >= 1:
                    abrir_slot_flow(s, str(c.get("project_url") or ""))
            time.sleep(3.0)
        elif op == "3":
            continue


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--status", action="store_true", help="Mostra status de todas as contas Flow e salva as online")
    ap.add_argument("--salvar", action="store_true", help="Escaneia e salva todas as contas online em forja/contas_flow.json")
    ap.add_argument("--abrir", nargs="+", type=int, help="Abre os slots informados (ex: --abrir 2 3 4) para login")
    ap.add_argument("--subir-todas", action="store_true", help="Abre todas as contas já cadastradas em contas_flow.json")
    args = ap.parse_args()

    if args.abrir:
        for s in args.abrir:
            abrir_slot_flow(s)
        escanear_e_salvar_pool(salvar=True)
    elif args.subir_todas:
        for c in carregar_registro_contas_flow():
            s = int(c.get("slot") or 0)
            if s >= 1:
                abrir_slot_flow(s, str(c.get("project_url") or ""))
        time.sleep(4.0)
        escanear_e_salvar_pool(salvar=True)
    elif args.status or args.salvar:
        escanear_e_salvar_pool(salvar=True)
    else:
        menu_interativo()


if __name__ == "__main__":
    main()
