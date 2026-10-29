@echo off
chcp 65001 >nul
title Flow Turbo Studio Beta - Instalador de Dependencias
echo ============================================================
echo   INSTALANDO DEPENDENCIAS DO FLOW TURBO STUDIO (BETA)
echo ============================================================
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
echo.
echo [OK] Dependencias instaladas com sucesso!
pause
