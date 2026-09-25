@echo off
REM Lanza Chrome con el puerto de debug CDP abierto para el scraper de Stake.
REM Usa un perfil de usuario separado para no chocar con una sesion normal de Chrome ya abierta.

set CHROME_EXE=C:\Program Files\Google\Chrome\Application\chrome.exe
set DEBUG_PROFILE=%TEMP%\chrome-debug-profile

if not exist "%CHROME_EXE%" (
    echo ERROR: No se encontro Chrome en "%CHROME_EXE%"
    pause
    exit /b 1
)

echo Iniciando Chrome con --remote-debugging-port=9222 ...
start "" "%CHROME_EXE%" --remote-debugging-port=9222 --remote-allow-origins=* --user-data-dir="%DEBUG_PROFILE%" "https://stake.com"

echo Chrome deberia abrirse con stake.com. Esperando a que cargue...
ping -n 6 127.0.0.1 >nul

echo Listo. Ya puedes ejecutar scripts\stake_scraper.py
