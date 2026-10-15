import os
import uuid

import pytest
from fastapi.testclient import TestClient
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from app.config import Settings
from app.infrastructure.database import connect
from app.main import create_app
from scripts.migrate import apply_migrations


@pytest.fixture(scope="session")
def test_settings(tmp_path_factory):
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to a separate PostgreSQL database ending in _test")
    if not conninfo_to_dict(url).get("dbname", "").endswith("_test"):
        pytest.fail("TEST_DATABASE_URL must use a database ending in _test")
    schema = "test_" + uuid.uuid4().hex
    admin_settings = Settings(_env_file=None, database_url=url)
    with connect(admin_settings) as connection:
        connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    settings = Settings(
        _env_file=None,
        database_url=make_conninfo(url, options=f"-c search_path={schema}"),
        app_origin="http://testserver",
        seed_admin_password="Admin-test-password-123",
        seed_user_password="User-test-password-123",
        uploads_dir=tmp_path_factory.mktemp("photos"),
    )
    try:
        with connect(settings) as connection:
            apply_migrations(connection)
        yield settings
    finally:
        with connect(admin_settings) as connection:
            connection.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


@pytest.fixture
def database(test_settings):
    with connect(test_settings) as connection:
        connection.execute(
            "TRUNCATE users, recipes, collections, categories, tags, ingredients "
            "RESTART IDENTITY CASCADE"
        )
        yield connection


@pytest.fixture
def client(test_settings, database, tmp_path):
    settings = test_settings.model_copy(update={"uploads_dir": tmp_path / "photos"})
    with TestClient(create_app(settings)) as test_client:
        yield test_client


@pytest.fixture
def origin():
    return {"Origin": "http://testserver"}


@pytest.fixture
def register_and_login(client, origin):
    data = {"email": "user@example.com", "display_name": "Користувач", "password": "password-123"}
    response = client.post("/api/auth/register", json=data, headers=origin)
    assert response.status_code == 201
    login = client.post(
        "/api/auth/login",
        json={"email": data["email"], "password": data["password"]},
        headers=origin,
    )
    assert login.status_code == 200
    return login.json()
