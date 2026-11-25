#!/bin/bash
# ==============================================================================
# 3_INICIAR_STUDIO_BETA_MAC.command — Inicia o Studio Web no MacBook sem dormir
# Usa `caffeinate -dimsu` nativo do macOS para impedir App Nap / Sleep em lotes!
# ==============================================================================
cd "$(dirname "$0")"
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"

echo "🚀 Iniciando Flow Turbo Studio em http://localhost:8788 (com caffeinate anti-sono ativo)..."
caffeinate -dimsu python3 studio_web.py
