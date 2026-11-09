@echo off
chcp 65001 >nul
title Abrir Chrome Flow RPC (Porta 9225)
set EXT_DIR=%~dp0extensao_flow_rpc
set PROFILE_DIR=%~dp0chrome_flow_profile
if not exist "%PROFILE_DIR%" mkdir "%PROFILE_DIR%"
echo Iniciando Google Chrome com extensao Flow RPC na porta 9225...
echo Faca login na sua conta Google em https://flow.google.com/ e abra ou crie qualquer projeto (/project/ID).
start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9225 --remote-allow-origins=* --disable-background-timer-throttling --disable-backgrounding-occluded-windows --disable-renderer-backgrounding --user-data-dir="%PROFILE_DIR%" --load-extension="%EXT_DIR%" "https://flow.google.com/"
