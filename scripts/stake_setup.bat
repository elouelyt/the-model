@echo off
cd /d "%~dp0\.."
echo === Stake.com Scraper Setup via CDP ===
echo.
echo IMPORTANTE: Chrome debe estar corriendo con --remote-debugging-port=9222
echo.
echo Si NO lo has configurado todavia:
echo   1. Cierra Chrome completamente
echo   2. Ve al acceso directo de Chrome (escritorio o barra de tareas)
echo   3. Click derecho → Propiedades
echo   4. En "Destino" añade al final: --remote-debugging-port=9222
echo      Ejemplo: "C:\...\chrome.exe" --remote-debugging-port=9222
echo   5. Abre Chrome con ese acceso directo
echo   6. Navega a stake.com (no hace falta login)
echo   7. Vuelve a ejecutar este bat
echo.
pause

echo Instalando dependencias...
pip install websocket-client requests -q
echo.

echo Probando scraper...
python scripts\stake_scraper.py
if errorlevel 1 (
    echo.
    echo ERROR - asegurate de:
    echo   - Chrome abierto con --remote-debugging-port=9222
    echo   - Stake.com abierto en alguna pestana (o se abrira automaticamente)
    pause
) else (
    echo.
    echo COMPLETADO - datos en data\stake_cache.json
    pause
)
