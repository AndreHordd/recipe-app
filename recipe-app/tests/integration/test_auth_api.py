from typing import Annotated

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient

from app.dependencies import COOKIE_NAME, require_admin
from app.domain.models import User
from app.infrastructure.security import Argon2PasswordHasher
from app.main import create_app
from app.services.authentication import hash_token
from scripts.seed import seed_database

pytestmark = pytest.mark.integration


def test_register_login_me_logout(client, origin, database):
    data = {"email": " USER@EXAMPLE.COM ", "display_name": "  Олена  ", "password": "password-123"}
    registered = client.post("/api/auth/register", json=data, headers=origin)
    assert registered.status_code == 201
    assert registered.json() == {
        "id": 1,
        "email": "user@example.com",
        "display_name": "Олена",
        "role": "USER",
        "is_active": True,
    }
    assert COOKIE_NAME not in client.cookies
    assert client.get("/api/auth/me").status_code == 401
    row = database.execute("SELECT password_hash FROM users").fetchone()
    assert row["password_hash"].startswith("$argon2id$")
    assert data["password"] not in row["password_hash"]
    login = client.post(
        "/api/auth/login",
        json={"email": data["email"], "password": data["password"]},
        headers=origin,
    )
    assert login.status_code == 200
    cookie = login.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=lax" in cookie and "Path=/" in cookie
    assert "Max-Age=604800" in cookie
    token = client.cookies[COOKIE_NAME]
    row = database.execute("SELECT token_hash, csrf_token FROM user_sessions").fetchone()
    assert row["token_hash"] == hash_token(token) and row["token_hash"] != token
    me = client.get("/api/auth/me")
    assert me.json() == login.json()
    assert me.headers["cache-control"] == "no-store"
    response = client.post(
        "/api/auth/logout", headers={**origin, "X-CSRF-Token": me.json()["csrf_token"]}
    )
    assert response.status_code == 204 and response.content == b""
    assert COOKIE_NAME not in client.cookies
    client.cookies.set(COOKIE_NAME, token)
    assert client.get("/api/auth/me").status_code == 401
    assert database.execute("SELECT count(*) AS n FROM user_sessions").fetchone()["n"] == 0


@pytest.mark.parametrize(
    "app_origin, browser_origin",
    [
        ("http://testserver", "http://testserver"),
        ("http://localhost:8000", "http://localhost:8000"),
        ("http://localhost:8000", "http://127.0.0.1:8000"),
        ("http://127.0.0.1:8000", "http://localhost:8000"),
    ],
)
def test_provisioned_admin_can_login_with_short_credentials(
    database, test_settings, app_origin, browser_origin
):
    database.execute(
        "INSERT INTO users (email, display_name, password_hash, role) VALUES (%s, %s, %s, %s)",
        ("bbb", "bbb", Argon2PasswordHasher().hash("bbb"), "ADMIN"),
    )
    settings = test_settings.model_copy(update={"app_origin": app_origin})
    with TestClient(create_app(settings), base_url=browser_origin) as client:
        origin = {"Origin": browser_origin}
        failed = client.post(
            "/api/auth/login", json={"email": "bbb", "password": "bad"}, headers=origin
        )
        assert failed.status_code == 401
        assert COOKIE_NAME not in client.cookies
        login = client.post(
            "/api/auth/login", json={"email": " BBB ", "password": "bbb"}, headers=origin
        )
        assert login.status_code == 200
        assert login.json()["user"]["email"] == "bbb"
        assert login.json()["user"]["role"] == "ADMIN"
        assert client.get("/api/auth/me").json()["user"] == login.json()["user"]
        assert client.get("/api/admin/users").status_code == 200
        assert (
            client.post(
                "/api/auth/logout", headers={**origin, "X-CSRF-Token": login.json()["csrf_token"]}
            ).status_code
            == 204
        )


def test_duplicate_normalized_email_rolls_back(client, origin, register_and_login, database):
    response = client.post(
        "/api/auth/register",
        json={
            "email": " USER@EXAMPLE.COM ",
            "display_name": "Інший",
            "password": "password-456",
        },
        headers=origin,
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "EMAIL_EXISTS"
    assert database.execute("SELECT count(*) AS n FROM users").fetchone()["n"] == 1
    assert client.get("/api/auth/me").status_code == 200


@pytest.mark.parametrize(
    "header", [{}, {"Origin": "https://other.example.com"}, {"Origin": "null"}]
)
def test_registration_requires_same_origin(client, header, database):
    response = client.post(
        "/api/auth/register",
        json={
            "email": "user@example.com",
            "display_name": "Ім’я",
            "password": "password-123",
        },
        headers=header,
    )
    assert response.status_code == 403
    assert database.execute("SELECT count(*) AS n FROM users").fetchone()["n"] == 0


def test_form_payload_rejected(client, origin):
    response = client.post(
        "/api/auth/login",
        data={"email": "user@example.com", "password": "password-123"},
        headers=origin,
    )
    assert response.status_code == 415


@pytest.mark.parametrize("token", [None, "wrong-csrf", b"\xe9"])
def test_logout_requires_csrf(client, origin, register_and_login, token):
    headers = origin if token is None else {**origin, "X-CSRF-Token": token}
    assert client.post("/api/auth/logout", headers=headers).status_code == 403
    assert client.get("/api/auth/me").status_code == 200


def test_logout_requires_origin_even_with_csrf(client, register_and_login):
    response = client.post(
        "/api/auth/logout", headers={"X-CSRF-Token": register_and_login["csrf_token"]}
    )
    assert response.status_code == 403
    assert client.get("/api/auth/me").status_code == 200


@pytest.mark.parametrize(
    "email,password",
    [
        ("user@example.com", "wrong-password"),
        ("missing@example.com", "password-123"),
    ],
)
def test_invalid_login_is_401_without_secret_data(
    client, origin, register_and_login, email, password
):
    response = client.post(
        "/api/auth/login", json={"email": email, "password": password}, headers=origin
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"
    assert "password_hash" not in response.text and password not in response.text


def test_validation_does_not_reflect_password_or_allow_role(client, origin):
    password = "secret-that-must-not-be-reflected"
    response = client.post(
        "/api/auth/register",
        json={
            "email": "bad-address",
            "display_name": "Ім’я",
            "password": password,
            "role": "ADMIN",
        },
        headers=origin,
    )
    assert response.status_code == 422
    assert password not in response.text
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_blocking_user_invalidates_existing_session(client, origin, register_and_login, database):
    database.execute("UPDATE users SET is_active = FALSE")
    assert client.get("/api/auth/me").status_code == 401
    response = client.post(
        "/api/auth/login",
        json={"email": "user@example.com", "password": "password-123"},
        headers=origin,
    )
    assert response.status_code == 403
    wrong = client.post(
        "/api/auth/login",
        json={"email": "user@example.com", "password": "wrong-password"},
        headers=origin,
    )
    assert wrong.status_code == 401


def test_expired_and_malformed_sessions_are_401(client, register_and_login, database):
    database.execute(
        "UPDATE user_sessions SET created_at = NOW() - INTERVAL '2 days', "
        "expires_at = NOW() - INTERVAL '1 day'"
    )
    assert client.get("/api/auth/me").status_code == 401
    client.cookies.clear()
    client.cookies.set(COOKIE_NAME, "x" * 200)
    assert client.get("/api/auth/me").status_code == 401


def test_second_login_revokes_previous_cookie(client, origin, register_and_login, database):
    old_token = client.cookies[COOKIE_NAME]
    response = client.post(
        "/api/auth/login",
        json={"email": "user@example.com", "password": "password-123"},
        headers=origin,
    )
    assert response.status_code == 200
    assert client.cookies[COOKIE_NAME] != old_token
    assert database.execute("SELECT count(*) AS n FROM user_sessions").fetchone()["n"] == 1
    client.cookies.clear()
    client.cookies.set(COOKIE_NAME, old_token)
    assert client.get("/api/auth/me").status_code == 401


def test_roles_read_from_database(client, register_and_login, database):
    assert client.get("/api/auth/me").json()["user"]["role"] == "USER"
    database.execute("UPDATE users SET role = 'ADMIN'")
    assert client.get("/api/auth/me").json()["user"]["role"] == "ADMIN"


def test_failed_session_rotation_preserves_previous_session(
    test_settings, client, origin, register_and_login, database
):
    old_token = client.cookies[COOKIE_NAME]
    database.execute(
        """CREATE FUNCTION fail_session_insert() RETURNS trigger LANGUAGE plpgsql AS $$
           BEGIN RAISE EXCEPTION 'test session failure'; END; $$;
           CREATE TRIGGER fail_session BEFORE INSERT ON user_sessions
           FOR EACH ROW EXECUTE FUNCTION fail_session_insert();"""
    )
    try:
        with TestClient(create_app(test_settings), raise_server_exceptions=False) as other_client:
            other_client.cookies.set(COOKIE_NAME, old_token)
            response = other_client.post(
                "/api/auth/login",
                json={"email": "user@example.com", "password": "password-123"},
                headers=origin,
            )
            assert response.status_code == 500
            assert "test session failure" not in response.text
        assert client.get("/api/auth/me").status_code == 200
        assert database.execute("SELECT token_hash FROM user_sessions").fetchone()[
            "token_hash"
        ] == hash_token(old_token)
    finally:
        database.execute(
            "DROP TRIGGER fail_session ON user_sessions; DROP FUNCTION fail_session_insert()"
        )


def test_seed_is_idempotent_and_all_accounts_can_login(client, origin, database, test_settings):
    seed_database(database, test_settings)
    hashes = database.execute("SELECT email, password_hash FROM users ORDER BY email").fetchall()
    seed_database(database, test_settings)
    assert (
        database.execute("SELECT email, password_hash FROM users ORDER BY email").fetchall()
        == hashes
    )
    for email, role in [
        ("admin@example.com", "ADMIN"),
        ("andriy@example.com", "USER"),
        ("viktoriia@example.com", "USER"),
    ]:
        password = "Admin-test-password-123" if role == "ADMIN" else "User-test-password-123"
        response = client.post(
            "/api/auth/login", json={"email": email, "password": password}, headers=origin
        )
        assert response.status_code == 200
        assert response.json()["user"]["role"] == role


def test_admin_dependency_checks_live_role(test_settings, database, origin):
    application = create_app(test_settings)

    @application.get("/api/test-admin")
    def admin_probe(user: Annotated[User, Depends(require_admin)]):
        return {"id": user.id}

    seed_database(database, test_settings)
    with TestClient(application) as test_client:
        assert test_client.get("/api/test-admin").status_code == 401
        test_client.post(
            "/api/auth/login",
            json={"email": "andriy@example.com", "password": "User-test-password-123"},
            headers=origin,
        )
        assert test_client.get("/api/test-admin").status_code == 403
        test_client.post(
            "/api/auth/login",
            json={"email": "admin@example.com", "password": "Admin-test-password-123"},
            headers=origin,
        )
        assert test_client.get("/api/test-admin").status_code == 200


def test_html_and_health(client):
    for path in ["/", "/login", "/register"]:
        response = client.get(path)
        assert response.status_code == 200 and '<html lang="uk">' in response.text
    assert client.get("/static/css/styles.css").status_code == 200
    assert client.get("/api/health").json() == {"status": "ok"}
    assert client.get("/api/missing").json()["error"]["code"] == "HTTP_ERROR"


def test_secure_cookie_with_https(test_settings, database):
    settings = test_settings.model_copy(
        update={"app_origin": "https://testserver", "cookie_secure": True}
    )
    seed_database(database, test_settings)
    with TestClient(create_app(settings), base_url="https://testserver") as test_client:
        response = test_client.post(
            "/api/auth/login",
            json={"email": "admin@example.com", "password": "Admin-test-password-123"},
            headers={"Origin": "https://testserver"},
        )
        assert response.status_code == 200 and "Secure" in response.headers["set-cookie"]
        assert test_client.get("/api/auth/me").status_code == 200
