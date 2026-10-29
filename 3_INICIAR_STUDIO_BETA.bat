@echo off
chcp 65001 >nul
title Flow Turbo Studio Beta (Porta 8788)
echo ============================================================
echo   INICIANDO FLOW TURBO STUDIO BETA EM http://localhost:8788
echo ============================================================
start "" http://localhost:8788
python studio_web.py
pause
