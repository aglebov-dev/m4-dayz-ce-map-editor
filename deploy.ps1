# Сборка .exe редактора через pyside6-deploy (бэкенд Nuitka).
# Запуск из корня репозитория:  ./deploy.ps1
# Конфигурация сборки — в src\pysidedeploy.spec. Готовый exe кладётся в .\dist\.
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$deploy = Join-Path $root ".venv\Scripts\pyside6-deploy.exe"
if (-not (Test-Path $deploy)) {
    Write-Error "Не найден $deploy. Создай окружение: rebuild-env.bat"
    exit 1
}
# pyside6-deploy ждёт input_file (app.py) и .spec в текущей папке — работаем из src\
Push-Location (Join-Path $root "src")
try {
    & $deploy -c pysidedeploy.spec --keep-deployment-files
}
finally {
    Pop-Location
}
Write-Host ""
Write-Host "Готово. exe: $(Join-Path $root 'dist')" -ForegroundColor Green
