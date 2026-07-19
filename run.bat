@echo off
rem M4 DayZ CE Map Editor — быстрый запуск
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
if not exist ".venv\Scripts\python.exe" (
  echo Не найдено окружение .venv. Создай его: rebuild-env.bat
  pause
  exit /b 1
)
".venv\Scripts\python.exe" "src\app.py"
if errorlevel 1 (
  echo.
  echo Приложение завершилось с ошибкой. Смотри вывод выше.
  pause
)
