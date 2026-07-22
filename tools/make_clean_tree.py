"""Собрать рядом с репозиторием минимальное дерево, из которого собирается exe.

В копию попадает только то, без чего сборка не проходит: пакет `src`, переводы, иконка,
`requirements.txt` и скрипты сборки. Ни `.git`, ни `.venv`, ни `appdata`, ни документация,
ни сами `tools` — Nuitka идёт по импортам от `app.py`, поэтому в бинарник ничего из этого
и так не входит; копия просто делает это явным.

Из `.py` вырезаются комментарии (документирующие строки остаются — они часть кода).
На содержимое exe это не влияет: комментарии отбрасываются ещё при разборе исходника,
до компиляции. Копия — снимок для передачи и сборки, не место для дальнейшей правки.

Запуск из корня репозитория:

    python tools\\make_clean_tree.py                       # -> ..\\<имя репозитория>.clean
    python tools\\make_clean_tree.py --target D:\\build\\m4  # произвольный каталог
    python tools\\make_clean_tree.py --keep-comments
"""
from __future__ import annotations

import argparse
import io
import shutil
import sys
import tokenize
from pathlib import Path

# Что копируем. Пути относительно корня репозитория; каталоги копируются целиком,
# минус `SKIP_DIRECTORIES` и `SKIP_SUFFIXES`.
INCLUDE = [
    "src",                  # сам код + pysidedeploy.spec
    "assets/i18n",          # единственный ассет, который бандлится в exe
    "app_icon_high.ico",    # иконка из спеки
    "requirements.txt",
    "deploy.ps1",
    "rebuild-env.bat",
    "run.bat",
]
SKIP_DIRECTORIES = {"__pycache__", "deployment", ".venv", ".git", "appdata"}
SKIP_SUFFIXES = {".pyc", ".pyo"}


def strip_comments(source: str) -> str:
    """Убрать комментарии, сохранив разбивку на строки и отступы.

    Идём по токенам: `tokenize` помечает комментариями только настоящие комментарии, `#`
    внутри строкового литерала останется на месте. Строку, состоявшую из одного лишь
    комментария, выкидываем целиком, иначе после чистки останется висячая пустая строка.
    Первую строку не трогаем: там может быть shebang или объявление кодировки.
    """
    lines = source.splitlines(keepends=True)
    # (номер строки -> список колонок начала комментариев), нумерация строк с единицы
    cuts: dict[int, int] = {}
    tokens = tokenize.generate_tokens(io.StringIO(source).readline)
    for token in tokens:
        if token.type != tokenize.COMMENT:
            continue
        row, column = token.start
        if row == 1 and (source.startswith("#!") or "coding" in token.string):
            continue
        # На строке может быть только один комментарий, и он тянется до её конца.
        cuts[row] = column

    result = []
    for number, line in enumerate(lines, start=1):
        if number not in cuts:
            result.append(line)
            continue
        head = line[: cuts[number]]
        if not head.strip():
            continue                                  # строка была целиком комментарием
        ending = "\r\n" if line.endswith("\r\n") else "\n" if line.endswith("\n") else ""
        result.append(head.rstrip() + ending)
    return "".join(result)


def copy_file(source: Path, target: Path, keep_comments: bool) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if source.suffix == ".py" and not keep_comments:
        text = source.read_text(encoding="utf-8")
        cleaned = strip_comments(text)
        compile(cleaned, str(source), "exec")          # чистка не должна ломать синтаксис
        target.write_text(cleaned, encoding="utf-8")
    else:
        shutil.copy2(source, target)


def copy_tree(root: Path, target_root: Path, keep_comments: bool) -> tuple[int, int]:
    files = 0
    stripped = 0
    for entry in INCLUDE:
        source = root / entry
        if not source.exists():
            raise SystemExit(f"нет обязательного пути: {source}")
        candidates = [source] if source.is_file() else sorted(source.rglob("*"))
        for path in candidates:
            if not path.is_file():
                continue
            if SKIP_DIRECTORIES & set(path.relative_to(root).parts):
                continue
            if path.suffix in SKIP_SUFFIXES:
                continue
            copy_file(path, target_root / path.relative_to(root), keep_comments)
            files += 1
            if path.suffix == ".py" and not keep_comments:
                stripped += 1
    return files, stripped


def rebase_spec(root: Path, target_root: Path) -> None:
    """Пересадить абсолютные пути в pysidedeploy.spec на новый корень.

    Стиль слешей сохраняем: `pyside6-deploy` разбирает `extra_args` через `shlex` в
    posix-режиме, где `\\` съедается как экранирование, и путь приезжает в Nuitka склеенным.
    """
    spec = target_root / "src" / "pysidedeploy.spec"
    text = spec.read_text(encoding="cp1252")
    old = str(root)
    for old_root, new_root in ((old, str(target_root)),
                               (old.replace("\\", "/"), str(target_root).replace("\\", "/"))):
        text = text.replace(old_root, new_root)
    spec.write_text(text, encoding="cp1252")


def main() -> int:
    # Консоль Windows по умолчанию cp1252/cp866 — кириллица в выводе иначе роняет скрипт.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path, default=root.parent / f"{root.name}.clean")
    parser.add_argument("--keep-comments", action="store_true")
    parser.add_argument("--force", action="store_true",
                        help="перезаписать целевой каталог, если он уже есть")
    arguments = parser.parse_args()

    target = arguments.target.resolve()
    if target == root:
        raise SystemExit("целевой каталог совпадает с репозиторием")
    if target.exists():
        if not arguments.force:
            raise SystemExit(f"каталог уже есть: {target}\nдобавь --force, чтобы перезаписать")
        shutil.rmtree(target)

    files, stripped = copy_tree(root, target, arguments.keep_comments)
    rebase_spec(root, target)

    print(f"дерево собрано: {target}")
    print(f"  файлов: {files}, из них .py без комментариев: {stripped}")
    print(f"  сборка: cd {target} && .\\rebuild-env.bat && .\\deploy.ps1")
    return 0


if __name__ == "__main__":
    sys.exit(main())
