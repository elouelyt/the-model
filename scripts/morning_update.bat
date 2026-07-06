@echo off
setlocal

set PROJECT_DIR=C:\Users\ojiyo\Desktop\tennis\tennis-ai-data-platform-main\tennis-ai-data-platform-main
set LOG_FILE=%PROJECT_DIR%\logs\morning_update.log

cd /d "%PROJECT_DIR%"

mkdir "%PROJECT_DIR%\logs" 2>nul

echo. >> "%LOG_FILE%"
echo ======================================== >> "%LOG_FILE%"
echo %DATE% %TIME% — morning_update.bat start >> "%LOG_FILE%"
echo ======================================== >> "%LOG_FILE%"

if exist "%PROJECT_DIR%\.venv\Scripts\activate.bat" (
    echo Activating .venv... >> "%LOG_FILE%"
    call "%PROJECT_DIR%\.venv\Scripts\activate.bat"
) else (
    echo .venv not found, using system Python >> "%LOG_FILE%"
)

echo Running stake_update.py... >> "%LOG_FILE%"
python scripts\stake_update.py >> "%LOG_FILE%" 2>&1
if %ERRORLEVEL% neq 0 (
    echo [WARN] stake_update.py exited with code %ERRORLEVEL% >> "%LOG_FILE%"
) else (
    echo stake_update.py OK >> "%LOG_FILE%"
)

echo Running rankings_update.py... >> "%LOG_FILE%"
python scripts\rankings_update.py >> "%LOG_FILE%" 2>&1
if %ERRORLEVEL% neq 0 (
    echo [WARN] rankings_update.py exited with code %ERRORLEVEL% >> "%LOG_FILE%"
) else (
    echo rankings_update.py OK >> "%LOG_FILE%"
)

echo Running check_results.py (Google News, needs internet)... >> "%LOG_FILE%"
python scripts\check_results.py >> "%LOG_FILE%" 2>&1
if %ERRORLEVEL% neq 0 (
    echo [WARN] check_results.py exited with code %ERRORLEVEL% >> "%LOG_FILE%"
) else (
    echo check_results.py OK >> "%LOG_FILE%"
)

echo Committing track_record.json if changed... >> "%LOG_FILE%"
git add data\track_record.json >> "%LOG_FILE%" 2>&1
git diff --cached --quiet || git commit -m "data: update track record results %DATE%" >> "%LOG_FILE%" 2>&1
git fetch origin main >> "%LOG_FILE%" 2>&1
git rebase origin/main >> "%LOG_FILE%" 2>&1
git push >> "%LOG_FILE%" 2>&1

echo Triggering Daily Predictions workflow... >> "%LOG_FILE%"
gh workflow run "Daily Predictions" --repo elouelyt/the-model >> "%LOG_FILE%" 2>&1
if %ERRORLEVEL% neq 0 (
    echo [ERROR] gh workflow run failed with code %ERRORLEVEL% >> "%LOG_FILE%"
) else (
    echo Daily Predictions triggered OK >> "%LOG_FILE%"
)

echo %DATE% %TIME% — morning_update.bat done >> "%LOG_FILE%"

endlocal
