# Сборка .exe

Редактор собирается в один исполняемый файл: `pyside6-deploy` → Nuitka, режим `onefile`.
Все флаги сборки лежат в [`src/pysidedeploy.spec`](../src/pysidedeploy.spec) — это единственный
источник правды и для локальной сборки, и для CI.

## Локально

```powershell
.\rebuild-env.bat   # один раз: .venv + зависимости из requirements.txt
.\deploy.ps1        # сборка; результат — dist\M4 DayZ CE Map Editor.exe
```

`deploy.ps1` требует `.venv\Scripts\pyside6-deploy.exe`, создаёт `dist\` (сам pyside6-deploy
его не создаёт) и запускает сборку из каталога `src\`.

## В GitHub Actions

Workflow: [`.github/workflows/build-windows.yml`](../.github/workflows/build-windows.yml),
раннер `windows-latest`.

Запускается:

* пушем тега `vX.Y.Z` — собирает exe и создаёт **GitHub Release** с приложенными `.exe` и `.zip`;
* вручную (Actions → build windows exe → Run workflow) — тогда exe лежит в **Artifacts** 30 дней.

```powershell
git tag v0.1.0
git push origin v0.1.0
```

Шаг «Generate CI spec» гоняет [`tools/make_ci_spec.ps1`](../tools/make_ci_spec.ps1): в коммит-спеке
абсолютные пути машины разработчика (`exec_directory`, `icon`, `python_path`, `--include-data-dir`),
скрипт пересаживает их на каталог раннера и подставляет его Python. Генерится
`src/pysidedeploy.ci.spec` — временный файл, в git не хранится.

Кеш Nuitka (`~\AppData\Local\Nuitka`) переживает запуски; ключ кеша завязан на
`requirements.txt` и `src/pysidedeploy.spec`, так что смена зависимостей или флагов сборки
кеш инвалидирует.

## Что попадает в exe, а что нет

Бандлятся только переводы (`assets/i18n`) — поэтому они **обязаны** быть в репозитории.
Тайлы подложки (`assets/tiles`) и датасеты зданий (`assets/buildings`) пользователь
распаковывает из файлов игры сам; данные портативные и ложатся в `appdata/` рядом с exe
(если каталог только для чтения — в `%localappdata%/m4dayzcemapeditor`, см. `src/core/paths.py`).

## Подводные камни

* `src/pysidedeploy.spec` и `.ps1`-скрипты держим **только в ASCII**: pyside6-deploy читает
  спеку как cp1252, а Windows PowerShell 5.1 читает `.ps1` в системной кодировке — кириллица
  ломает разбор.
* Сборка не подписана: SmartScreen на чужой машине покажет предупреждение.
* Сборка Nuitka идёт долго (десятки минут), таймаут job — 90 минут.
