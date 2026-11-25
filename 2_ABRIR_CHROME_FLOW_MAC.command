#!/bin/bash
# ==============================================================================
# 2_ABRIR_CHROME_FLOW_MAC.command — Abre o Chrome isolado (:9225) no MacBook
# ==============================================================================
cd "$(dirname "$0")"
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
xattr -cr ./extensao_flow_rpc 2>/dev/null || true

python3 abrir_chrome_flow.py
echo ""
read -rp "Pressione ENTER para fechar esta janela (o Chrome continuará aberto)..."
