"""Поставщики ВНЕШНИХ данных (сервер DayZ) — отдельный слой от файлов приложения
(те живут в `core.paths.AppPaths`). Ядро (`core/*`) читает локальные пути, поэтому
провайдер умеет ОТДАВАТЬ файлы: локальный — напрямую, SFTP — скачивая в кэш. Так
добавление нового провайдера не трогает ридеры.

`root` — это БАЗА источника, которую выбрал пользователь: корень сервера DayZ (в нём
лежит `mpmissions/`) или сама папка миссии. Все `rel`-пути адресуются относительно этой
базы через '/', даже на Windows (нормализуем). Для SFTP root обязателен (корень
подключения); для локального — это выбранная папка (можно абсолютную)."""
from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path


class ProviderError(Exception):
    pass


def _norm(rel: str) -> str:
    return rel.replace("\\", "/").strip("/")


class DataProvider:
    """Абстрактный поставщик. rel — путь относительно корня, через '/'."""

    kind = "abstract"

    @property
    def label(self) -> str:
        raise NotImplementedError

    def exists(self, rel: str) -> bool:
        raise NotImplementedError

    def list_dir(self, rel: str = "") -> list[str]:
        raise NotImplementedError

    def read_bytes(self, rel: str) -> bytes:
        raise NotImplementedError

    def mtime(self, rel: str) -> float:
        return 0.0

    def read_header(self, rel: str, n: int = 24) -> bytes:
        """Первые n байт файла (дёшево; переопределяется без чтения целиком)."""
        return self.read_bytes(rel)[:n]

    def fetch_to(self, rel: str, local_path: str):
        """Положить файл rel в local_path (скачать/скопировать). Каталоги создаём."""
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        with open(local_path, "wb") as f:
            f.write(self.read_bytes(rel))

    def close(self):
        pass


class LocalProvider(DataProvider):
    """Файловая система: `root` — выбранная папка-база (корень сервера или папка миссии)."""

    kind = "local"

    def __init__(self, root: Path | str):
        self.root = Path(root).resolve()
        if not self.root.is_dir():
            raise ProviderError(f"нет папки: {self.root}")

    @property
    def label(self) -> str:
        return str(self.root)

    def _abs(self, rel: str) -> Path:
        return self.root / _norm(rel)

    def exists(self, rel: str) -> bool:
        return self._abs(rel).exists()

    def list_dir(self, rel: str = "") -> list[str]:
        p = self._abs(rel)
        return sorted(c.name for c in p.iterdir()) if p.is_dir() else []

    def read_bytes(self, rel: str) -> bytes:
        return self._abs(rel).read_bytes()

    def read_header(self, rel: str, n: int = 24) -> bytes:
        with open(self._abs(rel), "rb") as f:
            return f.read(n)

    def mtime(self, rel: str) -> float:
        p = self._abs(rel)
        return p.stat().st_mtime if p.exists() else 0.0

    def fetch_to(self, rel: str, local_path: str):
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        shutil.copy2(self._abs(rel), local_path)   # copy2 сохраняет mtime


class SftpProvider(DataProvider):
    """SFTP: корень — папка сервера DayZ на удалённой машине. paramiko обязателен."""

    kind = "sftp"

    def __init__(self, host: str, user: str, root: str, *, port: int = 22,
                 password: str | None = None, key_path: str | None = None):
        try:
            import paramiko  # noqa: F401
        except ImportError as e:
            raise ProviderError(
                "SFTP недоступен: не установлен paramiko (pip install paramiko)") from e
        self.host, self.port, self.user = host, port, user
        self.root = "/" + _norm(root) if root else "/"
        self._password = password
        self._key_path = key_path
        self._client = None
        self._sftp = None

    @property
    def label(self) -> str:
        return f"sftp://{self.user}@{self.host}:{self.port}{self.root}"

    def _connect(self):
        if self._sftp is not None:
            return
        import paramiko
        cli = paramiko.SSHClient()
        cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        kw = {"hostname": self.host, "port": self.port, "username": self.user,
              "timeout": 15}
        if self._key_path:
            kw["key_filename"] = self._key_path
        else:
            kw["password"] = self._password
        try:
            cli.connect(**kw)
        except Exception as e:
            raise ProviderError(f"SFTP-подключение не удалось: {e}") from e
        self._client = cli
        self._sftp = cli.open_sftp()

    def _rpath(self, rel: str) -> str:
        return f"{self.root.rstrip('/')}/{_norm(rel)}"

    def exists(self, rel: str) -> bool:
        self._connect()
        try:
            self._sftp.stat(self._rpath(rel))
            return True
        except IOError:
            return False

    def list_dir(self, rel: str = "") -> list[str]:
        self._connect()
        try:
            return sorted(self._sftp.listdir(self._rpath(rel)))
        except IOError:
            return []

    def read_bytes(self, rel: str) -> bytes:
        self._connect()
        with self._sftp.open(self._rpath(rel), "rb") as f:
            return f.read()

    def read_header(self, rel: str, n: int = 24) -> bytes:
        self._connect()
        with self._sftp.open(self._rpath(rel), "rb") as f:
            return f.read(n)          # SFTP читает только n байт, не весь файл

    def mtime(self, rel: str) -> float:
        self._connect()
        try:
            return float(self._sftp.stat(self._rpath(rel)).st_mtime)
        except IOError:
            return 0.0

    def fetch_to(self, rel: str, local_path: str):
        self._connect()
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        self._sftp.get(self._rpath(rel), local_path)

    def close(self):
        if self._sftp:
            self._sftp.close()
        if self._client:
            self._client.close()
        self._sftp = self._client = None


def sftp_available() -> bool:
    try:
        import paramiko  # noqa: F401
        return True
    except ImportError:
        return False


def make_provider(cfg: dict) -> DataProvider:
    """Провайдер из конфигурации: {'kind': 'local'|'sftp', ...}."""
    kind = cfg.get("kind", "local")
    if kind in ("local", "projects"):
        return LocalProvider(cfg["root"])
    if kind == "sftp":
        return SftpProvider(cfg["host"], cfg["user"], cfg["root"],
                            port=int(cfg.get("port", 22)),
                            password=cfg.get("password"),
                            key_path=cfg.get("key_path"))
    raise ProviderError(f"Unknown provider: {kind}")
