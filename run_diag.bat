@echo off
rem M4 DayZ CE Map Editor -- run WITH dock diagnostics (writes appdata\dock_diag.log)
rem Use this only to catch the dock-drag crash: run it, reproduce the crash, then read
rem the tail it prints (or appdata\dock_diag.log). Normal launch is run.bat.
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
set M4_DIAG=1
if not exist ".venv\Scripts\python.exe" (
  echo No .venv found. Create it: rebuild-env.bat
  pause
  exit /b 1
)
del /q "appdata\dock_diag.log" 2>nul
".venv\Scripts\python.exe" "src\app.py"
echo.
echo ==== dock_diag.log (last 30 lines) ====
powershell -NoProfile -Command "if (Test-Path 'appdata\dock_diag.log') { Get-Content 'appdata\dock_diag.log' -Tail 30 } else { Write-Host 'no dock_diag.log created' }"
echo ==== end ====
pause
