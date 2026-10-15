"""Local development entry point used by the PyCharm run configurations."""

import argparse
import os
import subprocess
from pathlib import Path
from urllib.parse import urlsplit

import psycopg
import uvicorn
from psycopg.conninfo import conninfo_to_dict

from app.config import APP_ROOT, Settings
from app.infrastructure.database import connect
from scripts.migrate import apply_migrations


def ensure_database(settings: Settings) -> None:
    try:
        with connect(settings) as connection:
            connection.execute("SELECT 1")
        return
    except psycopg.OperationalError:
        pass

    connection_info = conninfo_to_dict(settings.database_url.get_secret_value())
    if (
        os.name != "nt"
        or connection_info.get("host") not in {"localhost", "127.0.0.1"}
        or connection_info.get("port", "5432") != "54329"
    ):
        raise RuntimeError("База недоступна. Запустіть PostgreSQL і перевірте DATABASE_URL у .env.")

    location_file = APP_ROOT / ".local" / "postgres-location.txt"
    if location_file.is_file():
        portable_root = Path(location_file.read_text(encoding="utf-8-sig").strip())
        bin_path = portable_root / "pgsql" / "bin"
        data_path = portable_root / "pgdata"
        log_path = portable_root / "postgresql.log"
    else:
        bin_path = APP_ROOT / ".local" / "postgresql" / "pgsql" / "bin"
        data_path = APP_ROOT / ".local" / "pgdata"
        log_path = APP_ROOT / ".local" / "postgresql.log"
    pg_control = bin_path / "pg_ctl.exe"
    if not pg_control.is_file() or not (data_path / "PG_VERSION").is_file():
        raise RuntimeError("Локальну PostgreSQL не знайдено. Дивіться інструкцію в README.")

    print("Запускаємо локальну PostgreSQL…", flush=True)
    result = subprocess.run(
        [
            str(pg_control),
            "-D",
            str(data_path),
            "-l",
            str(log_path),
            "-o",
            "-h 127.0.0.1 -p 54329",
            "-w",
            "start",
        ],
        # PostgreSQL outlives pg_ctl. Pipes would remain open in the server process.
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW,
        timeout=70,
    )
    if result.returncode:
        raise RuntimeError("Не вдалося запустити PostgreSQL. Перевірте локальний postgresql.log.")
    with connect(settings) as connection:
        connection.execute("SELECT 1")


def main() -> None:
    parser = argparse.ArgumentParser(description="Запуск проєкту для локальної розробки")
    parser.add_argument("--no-reload", action="store_true", help="Запуск без перезавантаження")
    parser.add_argument("--prepare-only", action="store_true", help="Підготувати тільки базу")
    arguments = parser.parse_args()

    settings = Settings()
    origin = urlsplit(settings.app_origin)
    if origin.scheme != "http" or origin.hostname not in {"localhost", "127.0.0.1"}:
        raise SystemExit("Для локального запуску задайте APP_ORIGIN=http://localhost:8000 у .env.")
    try:
        ensure_database(settings)
        with connect(settings) as connection:
            applied = apply_migrations(connection)
    except (psycopg.Error, subprocess.TimeoutExpired):
        raise SystemExit("База недоступна. Перевірте PostgreSQL і налаштування .env.") from None
    except RuntimeError as error:
        raise SystemExit(str(error)) from None
    print("Міграції: " + (", ".join(applied) if applied else "усі застосовано"), flush=True)
    if arguments.prepare_only:
        print("База готова до роботи.", flush=True)
        return

    print(f"Відкрийте застосунок: {settings.app_origin}", flush=True)
    uvicorn.run(
        "app.main:create_app",
        factory=True,
        host="127.0.0.1",
        port=origin.port or 80,
        reload=not arguments.no_reload,
        reload_dirs=[str(APP_ROOT / "app")] if not arguments.no_reload else None,
    )


if __name__ == "__main__":
    main()
