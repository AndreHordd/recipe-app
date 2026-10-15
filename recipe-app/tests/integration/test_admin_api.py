from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event
from time import monotonic, sleep

import pytest
from fastapi.testclient import TestClient

from app.api.recipe_schemas import RecipeCreate
from app.domain.exceptions import InactiveUser, VersionConflict
from app.domain.models import User
from app.infrastructure.database import connect
from app.infrastructure.repositories.catalog import PostgreSQLCatalogRepository
from app.infrastructure.repositories.recipes import PostgreSQLRecipeRepository
from app.infrastructure.repositories.sessions import SqlSessionRepository
from app.infrastructure.repositories.users import SqlUserRepository
from app.main import create_app
from app.services.authentication import AuthenticationService, hash_token
from app.services.moderation import ModerationService
from app.services.recipes import RecipeService

pytestmark = pytest.mark.integration
TARGET_LOGIN = {"email": "author@example.com", "password": "author-password-123"}


@pytest.fixture
def admin_session(client, database, register_and_login):
    user = register_and_login["user"]
    database.execute("UPDATE users SET role = 'ADMIN' WHERE id = %s", (user["id"],))
    return {**register_and_login, "user": {**user, "role": "ADMIN"}}


@pytest.fixture
def admin_headers(admin_session, origin):
    return {**origin, "X-CSRF-Token": admin_session["csrf_token"]}


@pytest.fixture
def author(client, admin_session, test_settings, origin):
    response = client.post(
        "/api/auth/register",
        json={**TARGET_LOGIN, "display_name": "Автор Їжак 100%_\\"},
        headers=origin,
    )
    assert response.status_code == 201, response.text
    with TestClient(create_app(test_settings)) as author_client:
        login = author_client.post("/api/auth/login", json=TARGET_LOGIN, headers=origin)
        assert login.status_code == 200, login.text
        session = login.json()
        yield author_client, session, {**origin, "X-CSRF-Token": session["csrf_token"]}


@pytest.fixture
def published(client, admin_headers, author):
    category = client.post(
        "/api/admin/categories", json={"name": "Сніданки"}, headers=admin_headers
    ).json()
    tag = client.post("/api/admin/tags", json={"name": "Швидко"}, headers=admin_headers).json()
    author_client, _, headers = author
    ingredient = author_client.post(
        "/api/ingredients", json={"name": "Яйце"}, headers=headers
    ).json()
    body = {
        "title": "Омлет Їжака 100%_\\",
        "description": "Опис рецепта",
        "category_id": category["id"],
        "tag_ids": [tag["id"]],
        "cooking_time": 15,
        "servings": 2,
        "ingredients": [{"ingredient_id": ingredient["id"], "quantity": "2.125", "unit": "pcs"}],
        "steps": [{"description": "Збити яйця."}, {"description": "Приготувати."}],
    }
    created = author_client.post("/api/recipes", json=body, headers=headers)
    assert created.status_code == 201, created.text
    response = author_client.post(
        f"/api/recipes/{created.json()['id']}/publish", json={"version": 1}, headers=headers
    )
    assert response.status_code == 200, response.text
    return response.json(), body


def assert_error(response, status, code):
    assert response.status_code == status, response.text
    assert response.json()["error"]["code"] == code


def admin_mutations(recipe_id=1, user_id=2):
    return [
        ("POST", f"/api/admin/recipes/{recipe_id}/hide", {"version": 2, "reason": "Причина"}),
        ("POST", f"/api/admin/recipes/{recipe_id}/restore", {"version": 2}),
        ("PATCH", f"/api/admin/users/{user_id}", {"is_active": False}),
        *[
            (method, f"/api/admin/{kind}{suffix}", body)
            for kind in ["categories", "tags"]
            for method, suffix, body in [
                ("POST", "", {"name": "Нова"}),
                ("PUT", "/1", {"name": "Нова"}),
                ("DELETE", "/1", None),
            ]
        ],
    ]


def test_hide_restore_lifecycle_preserves_aggregate_and_publication(
    client, admin_headers, author, published
):
    recipe, body = published
    path = f"/api/admin/recipes/{recipe['id']}"
    original = {
        key: value
        for key, value in recipe.items()
        if key not in {"status", "version", "hide_reason", "updated_at"}
    }
    response = client.post(
        path + "/hide", json={"version": 2, "reason": "  Уточніть кроки  "}, headers=admin_headers
    )
    assert response.status_code == 200, response.text
    hidden = response.json()
    assert hidden["status"] == "HIDDEN" and hidden["version"] == 3
    assert hidden["hide_reason"] == "Уточніть кроки"
    assert {key: hidden[key] for key in original} == original
    assert client.get("/api/recipes").json()["items"] == []
    assert client.get(f"/api/recipes/{recipe['id']}").json() == hidden
    for action in ["hide", "restore"]:
        data = {"version": 2, **({"reason": "Причина"} if action == "hide" else {})}
        assert_error(
            client.post(path + "/" + action, json=data, headers=admin_headers),
            409,
            "VERSION_CONFLICT",
        )
    assert_error(
        client.post(path + "/hide", json={"version": 3, "reason": "Повтор"}, headers=admin_headers),
        409,
        "INVALID_STATE",
    )
    restored = client.post(path + "/restore", json={"version": 3}, headers=admin_headers)
    assert restored.status_code == 200, restored.text
    draft = restored.json()
    assert draft["status"] == "DRAFT" and draft["version"] == 4
    assert draft["hide_reason"] is None
    assert {key: draft[key] for key in original} == original
    for action in ["hide", "restore"]:
        data = {"version": 4, **({"reason": "Причина"} if action == "hide" else {})}
        assert_error(
            client.post(path + "/" + action, json=data, headers=admin_headers), 409, "INVALID_STATE"
        )
    assert_error(
        client.put(
            f"/api/recipes/{recipe['id']}", json={**body, "version": 4}, headers=admin_headers
        ),
        403,
        "ACCESS_DENIED",
    )
    author_client, _, headers = author
    assert (
        author_client.post(
            f"/api/recipes/{recipe['id']}/publish", json={"version": 4}, headers=headers
        ).status_code
        == 200
    )
    for action in ["hide", "restore"]:
        data = {"version": 1, **({"reason": "Причина"} if action == "hide" else {})}
        assert_error(
            client.post(f"/api/admin/recipes/99999/{action}", json=data, headers=admin_headers),
            404,
            "RECIPE_NOT_FOUND",
        )


def test_every_admin_endpoint_rejects_users_and_guests(author, origin):
    author_client, _, headers = author
    routes = [("GET", "/api/admin/recipes", None), ("GET", "/api/admin/users", None)]
    routes += admin_mutations()
    for expected, request_headers in [(403, headers), (401, origin)]:
        if expected == 401:
            author_client.cookies.clear()
        for method, path, body in routes:
            response = author_client.request(
                method,
                path,
                headers=request_headers,
                **({"json": body} if body is not None else {}),
            )
            assert response.status_code == expected, (method, path, response.text)


def test_admin_mutations_require_origin_csrf_and_json(client, admin_headers, origin):
    for method, path, body in admin_mutations():
        kwargs = {"json": body} if body is not None else {}
        for headers in [
            {},
            origin,
            {**admin_headers, "X-CSRF-Token": "wrong"},
            {**admin_headers, "Origin": "https://other.example"},
        ]:
            assert client.request(method, path, headers=headers, **kwargs).status_code == 403
        if body is not None:
            response = client.request(
                method, path, content="{}", headers={**admin_headers, "Content-Type": "text/plain"}
            )
            assert_error(response, 415, "JSON_REQUIRED")
    for path in ["/api/admin/recipes", "/api/admin/users"]:
        assert client.get(path).headers["Cache-Control"] == "no-store"


def test_admin_input_validation_has_no_side_effects(client, admin_headers, author, published):
    recipe, _ = published
    user_id = author[1]["user"]["id"]
    hide = f"/api/admin/recipes/{recipe['id']}/hide"
    for body in [
        {"version": 2, "reason": " "},
        {"version": 2, "reason": "x" * 501},
        {"reason": "Причина"},
        {"version": True, "reason": "Причина"},
        {"version": "2", "reason": "Причина"},
        {"version": 0, "reason": "Причина"},
        {"version": 2, "reason": "Причина", "status": "DRAFT"},
    ]:
        assert client.post(hide, json=body, headers=admin_headers).status_code == 422
    for body in [{}, {"version": False}, {"version": "2"}, {"version": 2, "reason": "x"}]:
        assert (
            client.post(
                hide.replace("/hide", "/restore"), json=body, headers=admin_headers
            ).status_code
            == 422
        )
    for body in [{"is_active": value} for value in [0, 1, "false", None]] + [
        {},
        {"is_active": False, "role": "ADMIN"},
    ]:
        assert (
            client.patch(
                f"/api/admin/users/{user_id}", json=body, headers=admin_headers
            ).status_code
            == 422
        )
    for kind in ["categories", "tags"]:
        for body in [
            {"name": " "},
            {"name": "x" * 81},
            {"name": 42},
            {"name": "Нова", "id": 1},
            {},
        ]:
            for method, suffix in [("POST", ""), ("PUT", "/1")]:
                assert (
                    client.request(
                        method, f"/api/admin/{kind}{suffix}", json=body, headers=admin_headers
                    ).status_code
                    == 422
                )
    assert client.get(f"/api/recipes/{recipe['id']}").json() == recipe
    assert author[0].get("/api/auth/me").json()["user"]["is_active"]


def test_admin_lists_filter_unicode_literal_text_author_status_and_pages(
    client, database, admin_headers, admin_session, author, published
):
    recipe, _ = published
    other = client.post(
        "/api/recipes", json={"title": "Інша чернетка"}, headers=admin_headers
    ).json()
    assert (
        client.post(
            f"/api/admin/recipes/{recipe['id']}/hide",
            json={"version": 2, "reason": "Причина"},
            headers=admin_headers,
        ).status_code
        == 200
    )
    database.execute("UPDATE recipes SET created_at = '2026-01-01T00:00:00Z'")
    first = client.get("/api/admin/recipes?page_size=1").json()
    second = client.get("/api/admin/recipes?page_size=1&page=2").json()
    assert [r["id"] for r in first["items"] + second["items"]] == [other["id"], recipe["id"]]
    assert first["has_next"] and not second["has_next"]
    for q in ["їжака", "%", "_", "\\"]:
        rows = client.get("/api/admin/recipes", params={"q": q}).json()["items"]
        assert [r["id"] for r in rows] == [recipe["id"]]
    for status, owner, expected in [
        ("HIDDEN", author[1]["user"]["id"], [recipe["id"]]),
        ("DRAFT", admin_session["user"]["id"], [other["id"]]),
        ("HIDDEN", admin_session["user"]["id"], []),
    ]:
        rows = client.get("/api/admin/recipes", params={"status": status, "author_id": owner})
        assert [r["id"] for r in rows.json()["items"]] == expected
    for q in ["їжак", "AUTHOR@EXAMPLE", "%", "_", "\\"]:
        response = client.get("/api/admin/users", params={"q": q})
        assert [u["id"] for u in response.json()["items"]] == [author[1]["user"]["id"]]
        assert "password" not in response.text and "csrf" not in response.text
    first = client.get("/api/admin/users?page_size=1").json()
    second = client.get("/api/admin/users?page_size=1&page=2").json()
    assert [u["id"] for u in first["items"] + second["items"]] == [
        admin_session["user"]["id"],
        author[1]["user"]["id"],
    ]
    assert first["has_next"] and not second["has_next"]
    for path in ["/api/admin/users", "/api/admin/recipes"]:
        for query in ["page=0", "page_size=51", "q=" + "x" * 101, "page=" + str(2**63)]:
            assert client.get(path + "?" + query).status_code == 422
    for query in ["status=BAD", "author_id=0"]:
        assert client.get("/api/admin/recipes?" + query).status_code == 422


@pytest.mark.parametrize("kind", ["categories", "tags"])
def test_catalog_crud_normalization_uniqueness_and_referenced_delete(
    client, admin_headers, published, kind
):
    recipe, _ = published
    used = recipe["category"]["id"] if kind == "categories" else recipe["tags"][0]["id"]
    path = f"/api/admin/{kind}"
    created = client.post(path, json={"name": "  Зелена   Їжа  "}, headers=admin_headers)
    assert created.status_code == 201, created.text
    item = created.json()
    assert item["name"] == "Зелена Їжа"
    assert_error(
        client.post(path, json={"name": "ЗЕЛЕНА ЇЖА"}, headers=admin_headers),
        409,
        "CATALOG_NAME_EXISTS",
    )
    assert_error(
        client.put(f"{path}/{used}", json={"name": "Зелена їжа"}, headers=admin_headers),
        409,
        "CATALOG_NAME_EXISTS",
    )
    assert_error(client.delete(f"{path}/{used}", headers=admin_headers), 409, "CATALOG_IN_USE")
    renamed = client.put(f"{path}/{used}", json={"name": "  Нова   назва  "}, headers=admin_headers)
    assert renamed.status_code == 200 and renamed.json()["name"] == "Нова назва"
    same = client.put(f"{path}/{used}", json={"name": "НОВА НАЗВА"}, headers=admin_headers)
    assert same.status_code == 200 and same.json()["id"] == used
    detail = client.get(f"/api/recipes/{recipe['id']}").json()
    assert (detail["category"]["name"] if kind == "categories" else detail["tags"][0]["name"]) == (
        "НОВА НАЗВА"
    )
    assert client.delete(f"{path}/{item['id']}", headers=admin_headers).status_code == 204
    assert item not in client.get(f"/api/{kind}").json()
    for method in ["PUT", "DELETE"]:
        kwargs = {"json": {"name": "Назва"}} if method == "PUT" else {}
        assert_error(
            client.request(method, f"{path}/{item['id']}", headers=admin_headers, **kwargs),
            404,
            "CATALOG_NOT_FOUND",
        )


def test_block_revokes_all_sessions_unblock_requires_new_login_and_preserves_public_recipe(
    client, database, test_settings, admin_headers, admin_session, author, published, origin
):
    author_client, session, _ = author
    recipe, _ = published
    user_id = session["user"]["id"]
    path = f"/api/admin/users/{user_id}"
    with TestClient(create_app(test_settings)) as second:
        assert second.post("/api/auth/login", json=TARGET_LOGIN, headers=origin).status_code == 200
        assert (
            database.execute(
                "SELECT count(*) AS n FROM user_sessions WHERE user_id = %s", (user_id,)
            ).fetchone()["n"]
            == 2
        )
        for _ in range(2):
            result = client.patch(path, json={"is_active": False}, headers=admin_headers)
            assert result.status_code == 200 and not result.json()["is_active"]
        for browser in [author_client, second]:
            assert browser.get("/api/auth/me").status_code == 401
        assert (
            database.execute(
                "SELECT count(*) AS n FROM user_sessions WHERE user_id = %s", (user_id,)
            ).fetchone()["n"]
            == 0
        )
        assert_error(
            second.post("/api/auth/login", json=TARGET_LOGIN, headers=origin), 403, "USER_INACTIVE"
        )
        assert_error(
            second.post(
                "/api/auth/login",
                json={**TARGET_LOGIN, "password": "wrong-password"},
                headers=origin,
            ),
            401,
            "INVALID_CREDENTIALS",
        )
        assert second.get(f"/api/recipes/{recipe['id']}").json() == recipe
        result = client.patch(path, json={"is_active": True}, headers=admin_headers)
        assert result.status_code == 200 and result.json()["is_active"]
        assert author_client.get("/api/auth/me").status_code == 401
        assert second.post("/api/auth/login", json=TARGET_LOGIN, headers=origin).status_code == 200
    other_admin = database.execute(
        "INSERT INTO users (email, display_name, password_hash, role) "
        "VALUES ('other-admin@example.com', 'Admin', 'unused', 'ADMIN') RETURNING id"
    ).fetchone()["id"]
    for protected_id in [admin_session["user"]["id"], other_admin]:
        assert_error(
            client.patch(
                f"/api/admin/users/{protected_id}", json={"is_active": False}, headers=admin_headers
            ),
            403,
            "ACCESS_DENIED",
        )
        assert database.execute(
            "SELECT is_active FROM users WHERE id = %s", (protected_id,)
        ).fetchone()["is_active"]
    assert_error(
        client.patch("/api/admin/users/99999", json={"is_active": False}, headers=admin_headers),
        404,
        "USER_NOT_FOUND",
    )


def test_failed_session_revocation_rolls_back_user_activity(
    client, database, test_settings, admin_headers, author
):
    user_id = author[1]["user"]["id"]
    before = database.execute(
        "SELECT * FROM user_sessions WHERE user_id = %s", (user_id,)
    ).fetchall()
    database.execute(
        "CREATE FUNCTION reject_session_delete() RETURNS trigger LANGUAGE plpgsql "
        "AS $$ BEGIN RAISE EXCEPTION 'injected revocation failure'; END $$"
    )
    database.execute(
        "CREATE TRIGGER reject_session_delete BEFORE DELETE ON user_sessions "
        "FOR EACH ROW EXECUTE FUNCTION reject_session_delete()"
    )
    try:
        with TestClient(create_app(test_settings), raise_server_exceptions=False) as failing:
            failing.cookies.update(client.cookies)
            response = failing.patch(
                f"/api/admin/users/{user_id}", json={"is_active": False}, headers=admin_headers
            )
        assert_error(response, 500, "INTERNAL_ERROR")
        assert "injected" not in response.text
    finally:
        database.execute("DROP TRIGGER reject_session_delete ON user_sessions")
        database.execute("DROP FUNCTION reject_session_delete()")
    assert database.execute("SELECT is_active FROM users WHERE id = %s", (user_id,)).fetchone()[
        "is_active"
    ]
    assert (
        database.execute("SELECT * FROM user_sessions WHERE user_id = %s", (user_id,)).fetchall()
        == before
    )
    assert author[0].get("/api/auth/me").status_code == 200


def moderation(connection, users=None, recipes=None):
    recipes = recipes or PostgreSQLRecipeRepository(connection)
    return ModerationService(
        recipes,
        recipes,
        users or SqlUserRepository(connection),
        SqlSessionRepository(connection),
        PostgreSQLCatalogRepository(connection),
        connection.transaction,
    )


def assert_blocked_by(database, waiter, blocker):
    deadline = monotonic() + 4
    while monotonic() < deadline:
        if (
            blocker
            in database.execute("SELECT pg_blocking_pids(%s) AS pids", (waiter,)).fetchone()["pids"]
        ):
            return
        sleep(0.01)
    pytest.fail("Expected login/block row lock was not observed")


@pytest.mark.parametrize("first", ["login", "block"])
def test_login_and_block_serialize_on_user_in_both_orders(
    client, database, test_settings, admin_session, author, first
):
    user_id = author[1]["user"]["id"]
    actor = User(**admin_session["user"])
    locked, waiter_ready, release = Event(), Event(), Event()
    pids = {}

    class GatedUsers(SqlUserRepository):
        def find_by_email(self, email, *, for_update=False):
            result = super().find_by_email(email, for_update=for_update)
            if first == "login":
                locked.set()
                assert release.wait(timeout=10)
            return result

        def find_by_id(self, target_id, *, for_update=False):
            result = super().find_by_id(target_id, for_update=for_update)
            if first == "block":
                locked.set()
                assert release.wait(timeout=10)
            return result

    def operate(operation):
        with connect(test_settings) as connection:
            connection.execute("SET statement_timeout = '8s'")
            pids[operation] = connection.info.backend_pid
            users = GatedUsers(connection) if operation == first else SqlUserRepository(connection)
            if operation != first:
                waiter_ready.set()
            if operation == "block":
                return moderation(connection, users).set_active(actor, user_id, False)
            auth = AuthenticationService(
                users,
                SqlSessionRepository(connection),
                client.app.state.passwords,
                connection.transaction,
                7,
            )
            if first == "block":
                with pytest.raises(InactiveUser):
                    auth.login(TARGET_LOGIN["email"], TARGET_LOGIN["password"], None)
                return None
            return auth.login(TARGET_LOGIN["email"], TARGET_LOGIN["password"], None)

    second = "block" if first == "login" else "login"
    with ThreadPoolExecutor(max_workers=2) as pool:
        first_job = pool.submit(operate, first)
        second_job = None
        try:
            assert locked.wait(timeout=5)
            second_job = pool.submit(operate, second)
            assert waiter_ready.wait(timeout=5)
            assert_blocked_by(database, pids[second], pids[first])
        finally:
            release.set()
        result = first_job.result(timeout=12)
        assert second_job is not None
        second_job.result(timeout=12)
    assert not database.execute("SELECT is_active FROM users WHERE id = %s", (user_id,)).fetchone()[
        "is_active"
    ]
    assert (
        database.execute(
            "SELECT count(*) AS n FROM user_sessions WHERE user_id = %s", (user_id,)
        ).fetchone()["n"]
        == 0
    )
    if first == "login":
        assert result.token
        assert SqlSessionRepository(database).find_live(hash_token(result.token)) is None


def test_concurrent_edit_and_hide_commit_only_one_complete_aggregate(
    client, test_settings, admin_session, author, published
):
    original, body = published
    barrier = Barrier(2)

    class RacingRecipes(PostgreSQLRecipeRepository):
        def save(self, recipe, expected_version):
            barrier.wait(timeout=5)
            return super().save(recipe, expected_version)

    def operate(action):
        with connect(test_settings) as connection:
            connection.execute("SET statement_timeout = '8s'")
            recipes = RacingRecipes(connection)
            try:
                if action == "hide":
                    moderation(connection, recipes=recipes).hide(
                        User(**admin_session["user"]), original["id"], 2, "Перевірка"
                    )
                else:
                    service = RecipeService(
                        recipes,
                        recipes,
                        PostgreSQLCatalogRepository(connection),
                        connection.transaction,
                    )
                    details = RecipeCreate.model_validate(
                        {
                            **body,
                            "title": "Зміна автора",
                            "ingredients": [],
                            "steps": [],
                            "tag_ids": [],
                        }
                    ).to_details()
                    service.update(original["id"], User(**author[1]["user"]), details, 2)
                return action
            except VersionConflict:
                return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(operate, ["edit", "hide"]))
    winners = [outcome for outcome in outcomes if outcome]
    assert len(winners) == 1
    current = client.get(f"/api/recipes/{original['id']}").json()
    assert current["version"] == 3 and current["published_at"] == original["published_at"]
    if winners[0] == "hide":
        assert current["status"] == "HIDDEN" and current["hide_reason"] == "Перевірка"
        for field in ["title", "description", "ingredients", "steps", "tags", "author"]:
            assert current[field] == original[field]
    else:
        assert current["status"] == "DRAFT" and current["hide_reason"] is None
        assert current["title"] == "Зміна автора"
        assert current["ingredients"] == current["steps"] == current["tags"] == []
