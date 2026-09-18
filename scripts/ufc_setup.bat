@echo off
echo Iniciando setup UFC...
pause

cd /d "%~dp0\.."
echo Directorio: %CD%

if not exist logs md logs

echo [1/3] Scraping fighters con ESPN IDs (borrando cache vieja)...
del data\ufc_fighters_cache.json 2>nul
python scripts\ufc_scrape_fighters.py 2>logs\ufc_setup.log
if errorlevel 1 goto error
echo    OK - fighters guardados

echo.
echo [2/3] Scraping fight history por temporadas (2008-2025)...
python scripts\ufc_scrape_events.py 2>>logs\ufc_setup.log
if errorlevel 1 goto error
echo    OK - historial guardado

echo.
echo [3/3] Entrenando modelo...
python scripts\ufc_train_model.py 2>>logs\ufc_setup.log
if errorlevel 1 goto error
echo    OK - modelo entrenado

echo.
echo COMPLETADO - ahora haz git push de los 3 archivos data/
pause
goto end

:error
echo.
echo *** ERROR - abriendo log ***
start notepad logs\ufc_setup.log
pause

:end
