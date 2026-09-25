@echo off
REM Runs every morning. rankings_update.py itself skips the scrape (and does nothing)
REM if data/rankings_cache.json is already dated today (UTC) - see _already_updated_today().
setlocal

set PROJECT_DIR=C:\Users\ojiyo\Desktop\tennis\tennis-ai-data-platform-main\tennis-ai-data-platform-main
set LOG_FILE=%PROJECT_DIR%\logs\rankings_morning_check.log

cd /d "%PROJECT_DIR%"
mkdir "%PROJECT_DIR%\logs" 2>nul

echo. >> "%LOG_FILE%"
echo ======================================== >> "%LOG_FILE%"
echo %DATE% %TIME% — rankings_morning_check.bat start >> "%LOG_FILE%"
echo ======================================== >> "%LOG_FILE%"

if exist "%PROJECT_DIR%\.venv\Scripts\activate.bat" (
    call "%PROJECT_DIR%\.venv\Scripts\activate.bat"
)

python scripts\rankings_update.py >> "%LOG_FILE%" 2>&1
if %ERRORLEVEL% neq 0 (
    echo [WARN] rankings_update.py exited with code %ERRORLEVEL% >> "%LOG_FILE%"
) else (
    echo rankings_update.py OK >> "%LOG_FILE%"
)

echo %DATE% %TIME% — rankings_morning_check.bat done >> "%LOG_FILE%"
endlocal
