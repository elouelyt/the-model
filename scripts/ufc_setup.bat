@echo off
echo ============================================
echo  UFC DATA SETUP - Scraping + Model Training
echo ============================================
echo.

cd /d "%~dp0\.."

echo [1/3] Scraping UFC fighter stats (ufcstats.com)...
python scripts\ufc_scrape_fighters.py
if errorlevel 1 (echo ERROR en fighter scraper & pause & exit /b 1)

echo.
echo [2/3] Scraping UFC fight history (todos los eventos)...
echo AVISO: esto puede tardar 10-20 minutos
python scripts\ufc_scrape_events.py
if errorlevel 1 (echo ERROR en events scraper & pause & exit /b 1)

echo.
echo [3/3] Entrenando modelo logistic regression...
python scripts\ufc_train_model.py
if errorlevel 1 (echo ERROR en model training & pause & exit /b 1)

echo.
echo ============================================
echo  COMPLETADO - Modelo listo
echo  Ahora commitea data/ufc_*.json y data/ufc_model.json
echo  para que GitHub Actions lo use
echo ============================================
pause
