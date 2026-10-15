import hashlib
from pathlib import Path

from psycopg import Connection

from app.config import APP_ROOT, Settings
from app.infrastructure.database import connect

MIGRATIONS_DIR = APP_ROOT / "migrations"


def apply_migrations(connection: Connection, directory: Path = MIGRATIONS_DIR) -> list[str]:
    applied = []
    # A transaction-level lock serializes runners and is released even after a rollback.
    with connection.transaction():
        connection.execute("SELECT pg_advisory_xact_lock(748271901)")
        connection.execute(
            """CREATE TABLE IF NOT EXISTS schema_migrations (
                name TEXT PRIMARY KEY,
                checksum CHAR(64) NOT NULL,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
            )"""
        )
        for path in sorted(directory.glob("*.sql")):
            source = path.read_text(encoding="utf-8-sig")
            checksum = hashlib.sha256(source.encode("utf-8")).hexdigest()
            existing = connection.execute(
                "SELECT checksum FROM schema_migrations WHERE name = %s", (path.name,)
            ).fetchone()
            if existing:
                if existing["checksum"] != checksum:
                    raise RuntimeError(f"Applied migration changed: {path.name}")
                continue
            connection.execute(source, prepare=False)
            connection.execute(
                "INSERT INTO schema_migrations (name, checksum) VALUES (%s, %s)",
                (path.name, checksum),
            )
            applied.append(path.name)
    return applied


def main() -> None:
    with connect(Settings()) as connection:
        applied = apply_migrations(connection)
    print("Застосовано: " + ", ".join(applied) if applied else "Міграції вже застосовано.")


if __name__ == "__main__":
    main()
