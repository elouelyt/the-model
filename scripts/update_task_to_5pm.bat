@echo off
REM Update Tennis Morning Update task to run at 17:00 (5 PM)
REM Run this file with "Run as Administrator"

echo Updating Tennis Morning Update task to 17:00...
schtasks /change /tn "Tennis Morning Update" /st 17:00

echo.
echo Verifying update...
schtasks /query /tn "Tennis Morning Update" /fo list /v | find "Hora de inicio" || find "Start Time"

echo.
echo Done. The task will now run at 17:00 (5 PM) instead of 7:00 AM.
pause
