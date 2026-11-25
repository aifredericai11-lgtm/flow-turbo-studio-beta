#!/bin/bash
# ==============================================================================
# 1_INSTALAR_DEPENDENCIAS_MAC.command — Instalador MacBook (Apple Silicon / Intel)
# Dê dois cliques neste arquivo no Finder para instalar FFmpeg + Python packages!
# ==============================================================================
set -e
cd "$(dirname "$0")"

echo "================================================================"
echo "  FLOW TURBO STUDIO — INSTALACAO MACBOOK (M1/M2/M3/M4/M5 & Intel)"
echo "================================================================"

# Remove quarentena do Gatekeeper caso tenha sido baixado via .zip
xattr -cr . 2>/dev/null || true
chmod +x ./*.command 2>/dev/null || true

# Garante Homebrew no PATH (Apple Silicon /opt/homebrew e Intel /usr/local)
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "📦 FFmpeg não encontrado. Tentando instalar via Homebrew..."
  if command -v brew >/dev/null 2>&1; then
    brew install ffmpeg
  else
    echo "⚠️ Homebrew não encontrado! Instale o Homebrew primeiro em https://brew.sh e depois rode:"
    echo "   brew install ffmpeg python"
    exit 1
  fi
fi

echo "✅ FFmpeg detectado: $(command -v ffmpeg)"
echo "📦 Instalando bibliotecas Python (requirements.txt)..."
python3 -m pip install --upgrade pip --break-system-packages 2>/dev/null || python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt --break-system-packages 2>/dev/null || python3 -m pip install -r requirements.txt

echo ""
echo "✅ TUDO PRONTO NO MACBOOK! Próximo passo:"
echo "   -> Dê dois cliques em 2_ABRIR_CHROME_FLOW_MAC.command (ou GERENCIAR_CONTAS_FLOW_MAC.command)"
read -rp "Pressione ENTER para fechar..."
