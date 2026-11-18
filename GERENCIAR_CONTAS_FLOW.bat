@echo off
chcp 65001 >nul
title GERENCIADOR MULTI-CONTAS GOOGLE FLOW (:9225 .. :9236)
cd /d "%~dp0"
python gerenciar_contas_flow.py
pause
