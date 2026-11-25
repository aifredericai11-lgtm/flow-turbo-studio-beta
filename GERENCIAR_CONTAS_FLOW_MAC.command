#!/bin/bash
# ==============================================================================
# GERENCIAR_CONTAS_FLOW_MAC.command — Pool Multi-Contas (:9225..:9236) no MacBook
# ==============================================================================
cd "$(dirname "$0")"
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
xattr -cr ./extensao_flow_rpc 2>/dev/null || true

python3 gerenciar_contas_flow.py
