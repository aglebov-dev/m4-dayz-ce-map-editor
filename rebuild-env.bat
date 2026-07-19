@echo off
chcp 65001 > nul
setlocal enabledelayedexpansion

echo [1/5] Проверка старого окружения...
if exist .venv (
    echo Сохраняем список текущих зависимостей в requirements.txt...
    .venv\Scripts\python.exe -m pip freeze > requirements.txt
    
    echo Удаляем сломанное виртуальное окружение...
    rmdir /s /q .venv
) else (
    echo Старое окружение .venv не найдено. Будет создано новое.
)

echo.
echo [2/5] Создание нового окружения .venv...
python -m venv .venv
if %errorlevel% neq 0 (
    echo Ошибка при создании окружения. Убедитесь, что Python добавлен в PATH.
    pause
    exit /b
)

echo.
echo [3/5] Обновление менеджера пакетов pip...
.venv\Scripts\python.exe -m pip install --upgrade pip

echo.
echo [4/5] Восстановление зависимостей...
if exist requirements.txt (
    .venv\Scripts\pip.exe install -r requirements.txt
) else (
    echo Файл requirements.txt не найден. Устанавливаем только PySide6.
    .venv\Scripts\pip.exe install PySide6
)

echo.
echo [5/5] Запуск инициализации PySide6...
.venv\Scripts\pyside6-deploy.exe --init

echo.
echo ===================================================
echo  Пересоздание окружения успешно завершено!
echo ===================================================
pause