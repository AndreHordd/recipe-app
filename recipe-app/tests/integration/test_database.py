import shutil

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from scripts.migrate import MIGRATIONS_DIR, apply_migrations
from scripts.seed import seed_database

pytestmark = pytest.mark.integration


def test_migrations_are_idempotent(database):
    assert apply_migrations(database) == []
    row = database.execute("SELECT count(*) AS n FROM schema_migrations").fetchone()
    assert row["n"] == 2
    tables = database.execute(
        "SELECT count(*) AS n FROM information_schema.tables WHERE table_schema = current_schema()"
    ).fetchone()
    assert tables["n"] == 12


def test_changed_applied_migration_is_rejected(database, tmp_path):
    target = tmp_path / "001_init.sql"
    shutil.copyfile(MIGRATIONS_DIR / "001_init.sql", target)
    with target.open("a", encoding="utf-8") as stream:
        stream.write("\n-- changed\n")
    with pytest.raises(RuntimeError, match="Applied migration changed"):
        apply_migrations(database, tmp_path)
    assert database.execute("SELECT count(*) AS n FROM schema_migrations").fetchone()["n"] == 2


def test_failed_migration_rolls_back_schema_and_history(database, tmp_path):
    target = tmp_path / "002_failure.sql"
    target.write_text("CREATE TABLE rollback_probe(id INT); SELECT 1/0;", encoding="utf-8")
    with pytest.raises(psycopg.errors.DivisionByZero):
        apply_migrations(database, tmp_path)
    assert (
        database.execute("SELECT to_regclass('rollback_probe') AS name").fetchone()["name"] is None
    )
    assert database.execute("SELECT count(*) AS n FROM schema_migrations").fetchone()["n"] == 2


def test_foreign_key_and_session_expiry_constraints(database):
    with pytest.raises(psycopg.errors.ForeignKeyViolation), database.transaction():
        database.execute(
            "INSERT INTO user_sessions VALUES (%s, 999, 'csrf', NOW(), NOW() + INTERVAL '1 day')",
            ("a" * 64,),
        )
    with pytest.raises(psycopg.errors.CheckViolation), database.transaction():
        database.execute(
            "INSERT INTO users (email, display_name, password_hash) "
            "VALUES (' UPPER@EXAMPLE.COM ', 'Name', 'hash')"
        )
    user = database.execute(
        "INSERT INTO users (email, display_name, password_hash) "
        "VALUES ('user@example.com', 'Name', 'hash') RETURNING id"
    ).fetchone()
    with pytest.raises(psycopg.errors.CheckViolation), database.transaction():
        database.execute(
            "INSERT INTO user_sessions (token_hash, user_id, csrf_token, expires_at) "
            "VALUES (%s, %s, 'csrf', NOW() - INTERVAL '1 day')",
            ("a" * 64, user["id"]),
        )


def test_seed_does_not_promote_registered_user(database, test_settings):
    database.execute(
        "INSERT INTO users (email, display_name, password_hash) "
        "VALUES ('admin@example.com', 'User', 'hash')"
    )
    with pytest.raises(ValueError, match="different role"):
        seed_database(database, test_settings)
    assert database.execute("SELECT role FROM users").fetchone()["role"] == "USER"
    assert database.execute("SELECT count(*) AS n FROM categories").fetchone()["n"] == 0


def test_recipe_seed_is_idempotent_and_preserves_existing_changes(database, test_settings):
    seed_database(database, test_settings)
    before = database.execute("SELECT id, version FROM recipes ORDER BY id").fetchall()
    assert len(before) == 12
    database.execute(
        "UPDATE recipes SET description = 'Зміна користувача' WHERE id = %s", (before[0]["id"],)
    )
    seed_database(database, test_settings)
    assert database.execute("SELECT id, version FROM recipes ORDER BY id").fetchall() == before
    assert (
        database.execute(
            "SELECT description FROM recipes WHERE id = %s", (before[0]["id"],)
        ).fetchone()["description"]
        == "Зміна користувача"
    )
    statuses = database.execute(
        "SELECT status, count(*) AS n FROM recipes GROUP BY status"
    ).fetchall()
    assert {row["status"]: row["n"] for row in statuses} == {
        "PUBLISHED": 10,
        "DRAFT": 1,
        "HIDDEN": 1,
    }


def test_database_failure_returns_503_without_dsn(test_settings):
    settings = test_settings.model_copy(
        update={
            "database_url": type(test_settings.database_url)(
                "postgresql://user:secret@127.0.0.1:1/unavailable"
            ),
            "database_timeout": 1,
        }
    )
    with TestClient(create_app(settings)) as client:
        response = client.get("/api/health")
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "DATABASE_UNAVAILABLE"
        assert "secret" not in response.text and "postgresql" not in response.text
