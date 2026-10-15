from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event
from time import monotonic, sleep

import pytest
from fastapi.testclient import TestClient

from app.domain.exceptions import RecipeNotFound
from app.domain.models import User
from app.infrastructure.database import connect
from app.infrastructure.repositories.collections import PostgreSQLCollectionRepository
from app.infrastructure.repositories.recipes import PostgreSQLRecipeRepository
from app.main import create_app
from app.services.collections import CollectionService

pytestmark = pytest.mark.integration


@pytest.fixture
def write_headers(register_and_login, origin):
    return {**origin, "X-CSRF-Token": register_and_login["csrf_token"]}


@pytest.fixture
def collection_data(database, register_and_login):
    owner_id = register_and_login["user"]["id"]
    foreign_id = database.execute(
        "INSERT INTO users (email, display_name, password_hash) "
        "VALUES ('foreign@example.com', 'Інший автор', 'unused-in-test') RETURNING id"
    ).fetchone()["id"]
    category = database.execute(
        "INSERT INTO categories (name, normalized_name) VALUES ('Сніданки', 'сніданки') "
        "RETURNING id"
    ).fetchone()["id"]
    ingredient = database.execute(
        "INSERT INTO ingredients (name, normalized_name) VALUES ('Яйце', 'яйце') RETURNING id"
    ).fetchone()["id"]
    recipe_ids = []
    for author, title in [
        (owner_id, "Мій омлет"),
        (foreign_id, "Чужий омлет"),
        (foreign_id, "Каша"),
    ]:
        recipe_id = database.execute(
            "INSERT INTO recipes (author_id, category_id, title, description, cooking_time, "
            "status, published_at) VALUES (%s, %s, %s, 'Опис страви', 15, 'PUBLISHED', "
            "CURRENT_TIMESTAMP) RETURNING id",
            (author, category, title),
        ).fetchone()["id"]
        database.execute(
            "INSERT INTO recipe_ingredients (recipe_id, position, ingredient_id, quantity, unit) "
            "VALUES (%s, 1, %s, 2, 'pcs')",
            (recipe_id, ingredient),
        )
        database.execute(
            "INSERT INTO instruction_steps (recipe_id, number, description) "
            "VALUES (%s, 1, 'Приготувати.')",
            (recipe_id,),
        )
        recipe_ids.append(recipe_id)
    return {"owner_id": owner_id, "foreign_id": foreign_id, "recipes": recipe_ids}


def create_collection(client, headers, name="  Сніданки  "):
    response = client.post("/api/collections", json={"name": name}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def entries_url(collection_id):
    return f"/api/collections/{collection_id}/recipes"


def test_collection_lifecycle_preserves_recipes_and_accepts_duplicate_names(
    client, database, write_headers, collection_data
):
    first = create_collection(client, write_headers)
    second = create_collection(client, write_headers)
    assert first["name"] == second["name"] == "Сніданки"
    assert set(first) == {"id", "name", "created_at", "updated_at"}
    assert client.get(f"/api/collections/{first['id']}").json() == first
    response = client.put(
        f"/api/collections/{first['id']}", json={"name": "  Обіди  "}, headers=write_headers
    )
    assert response.status_code == 200
    renamed = response.json()
    assert renamed["name"] == "Обіди" and renamed["created_at"] == first["created_at"]
    assert renamed["updated_at"] >= first["updated_at"]
    recipe_id = collection_data["recipes"][0]
    assert (
        client.put(f"{entries_url(first['id'])}/{recipe_id}", headers=write_headers).status_code
        == 204
    )
    assert (
        client.delete(f"/api/collections/{first['id']}", headers=write_headers).status_code == 204
    )
    assert client.get(f"/api/collections/{first['id']}").status_code == 404
    assert database.execute("SELECT count(*) AS n FROM collection_entries").fetchone()["n"] == 0
    assert database.execute("SELECT count(*) AS n FROM recipes").fetchone()["n"] == 3
    assert database.execute("SELECT count(*) AS n FROM instruction_steps").fetchone()["n"] == 3
    assert client.get(f"/api/recipes/{recipe_id}").status_code == 200
    assert [item["id"] for item in client.get("/api/collections").json()["items"]] == [second["id"]]


def test_add_and_remove_are_idempotent_including_saved_dates(
    client, database, write_headers, collection_data
):
    collection = create_collection(client, write_headers)
    path = f"{entries_url(collection['id'])}/{collection_data['recipes'][1]}"
    assert client.put(path, headers=write_headers).status_code == 204
    first_entry = client.get(entries_url(collection["id"])).json()["items"]
    first_metadata = client.get(f"/api/collections/{collection['id']}").json()
    assert len(first_entry) == 1 and first_entry[0]["available"]
    assert first_entry[0]["recipe"]["title"] == "Чужий омлет"
    assert "ingredients" not in first_entry[0]["recipe"] and "email" not in str(first_entry)
    assert client.put(path, headers=write_headers).status_code == 204
    assert client.get(entries_url(collection["id"])).json()["items"] == first_entry
    assert client.get(f"/api/collections/{collection['id']}").json() == first_metadata
    assert client.delete(path, headers=write_headers).status_code == 204
    removed = client.get(f"/api/collections/{collection['id']}").json()
    assert client.delete(path, headers=write_headers).status_code == 204
    assert (
        client.delete(f"{entries_url(collection['id'])}/99999", headers=write_headers).status_code
        == 204
    )
    assert client.get(f"/api/collections/{collection['id']}").json() == removed
    assert database.execute("SELECT count(*) AS n FROM collection_entries").fetchone()["n"] == 0


@pytest.mark.parametrize("role", ["USER", "ADMIN"])
def test_foreign_collections_are_inaccessible_for_all_roles(
    client, database, write_headers, collection_data, role
):
    database.execute(
        "UPDATE users SET role = %s WHERE id = %s", (role, collection_data["owner_id"])
    )
    foreign = database.execute(
        "INSERT INTO collections (owner_id, name) VALUES (%s, 'Чужа добірка') RETURNING id",
        (collection_data["foreign_id"],),
    ).fetchone()["id"]
    path = f"/api/collections/{foreign}"
    mutations = [
        ("GET", path, None),
        ("GET", path + "/recipes", None),
        ("PUT", path, {"name": "Зміна"}),
        ("DELETE", path, None),
        ("PUT", path + "/recipes/99999", None),
        ("DELETE", path + "/recipes/99999", None),
    ]
    for method, url, body in mutations:
        response = client.request(
            method, url, headers=write_headers, **({"json": body} if body else {})
        )
        assert response.status_code == 404, response.text
        assert response.json()["error"]["code"] == "COLLECTION_NOT_FOUND"
    assert client.get("/api/collections").json()["items"] == []
    assert (
        database.execute("SELECT name FROM collections WHERE id = %s", (foreign,)).fetchone()[
            "name"
        ]
        == "Чужа добірка"
    )


@pytest.mark.parametrize("status", ["DRAFT", "HIDDEN"])
@pytest.mark.parametrize("role", ["USER", "ADMIN"])
def test_private_foreign_entry_is_redacted_and_can_be_removed(
    client, database, write_headers, collection_data, status, role
):
    collection = create_collection(client, write_headers)
    recipe_id = collection_data["recipes"][1]
    path = f"{entries_url(collection['id'])}/{recipe_id}"
    assert client.put(path, headers=write_headers).status_code == 204
    original = client.get(entries_url(collection["id"])).json()["items"][0]
    database.execute(
        "UPDATE recipes SET status = %s, hide_reason = %s, title = 'Таємна назва', "
        "description = 'Таємний опис', version = version + 1 WHERE id = %s",
        (status, "Приватна причина" if status == "HIDDEN" else None, recipe_id),
    )
    database.execute(
        "UPDATE users SET role = %s WHERE id = %s", (role, collection_data["owner_id"])
    )
    response = client.get(entries_url(collection["id"]))
    assert response.status_code == 200
    assert response.json()["items"] == [
        {
            "recipe_id": recipe_id,
            "saved_at": original["saved_at"],
            "available": False,
            "recipe": None,
        }
    ]
    for private in ["Таємна", "Інший автор", "Приватна", "HIDDEN", "DRAFT"]:
        assert private not in response.text
    assert client.put(path, headers=write_headers).status_code == 404
    assert client.delete(path, headers=write_headers).status_code == 204
    assert client.get(entries_url(collection["id"])).json()["items"] == []


@pytest.mark.parametrize("status", ["DRAFT", "HIDDEN"])
def test_own_private_recipe_remains_available_but_cannot_be_added(
    client, database, write_headers, collection_data, status
):
    collection = create_collection(client, write_headers)
    recipe_id = collection_data["recipes"][0]
    path = f"{entries_url(collection['id'])}/{recipe_id}"
    assert client.put(path, headers=write_headers).status_code == 204
    database.execute(
        "UPDATE recipes SET status = %s, hide_reason = %s WHERE id = %s",
        (status, "Уточнити кроки" if status == "HIDDEN" else None, recipe_id),
    )
    entry = client.get(entries_url(collection["id"])).json()["items"][0]
    assert entry["available"] and entry["recipe"]["status"] == status
    assert entry["recipe"]["title"] == "Мій омлет" and "hide_reason" not in entry["recipe"]
    response = client.put(path, headers=write_headers)
    assert (
        response.status_code == 409 and response.json()["error"]["code"] == "RECIPE_NOT_PUBLISHED"
    )
    assert (
        client.put(f"{entries_url(collection['id'])}/99999", headers=write_headers).status_code
        == 404
    )


def test_collection_and_entry_pagination_have_stable_tie_breakers(
    client, database, write_headers, collection_data
):
    collections = [create_collection(client, write_headers, f"Добірка {n}")["id"] for n in range(3)]
    database.execute("UPDATE collections SET created_at = '2026-01-01T00:00:00Z'")
    first = client.get("/api/collections?page_size=2").json()
    second = client.get("/api/collections?page_size=2&page=2").json()
    assert [item["id"] for item in first["items"] + second["items"]] == collections[::-1]
    assert first["has_next"] and not second["has_next"]
    for recipe_id in collection_data["recipes"]:
        assert (
            client.put(
                f"{entries_url(collections[0])}/{recipe_id}", headers=write_headers
            ).status_code
            == 204
        )
    database.execute("UPDATE collection_entries SET saved_at = '2026-01-01T00:00:00Z'")
    first = client.get(entries_url(collections[0]) + "?page_size=2").json()
    second = client.get(entries_url(collections[0]) + "?page_size=2&page=2").json()
    assert [item["recipe_id"] for item in first["items"] + second["items"]] == collection_data[
        "recipes"
    ][::-1]
    assert first["has_next"] and not second["has_next"]
    for path in ["/api/collections", entries_url(collections[0])]:
        assert client.get(path + "?page=10").json()["items"] == []
        for invalid in ["page=0", "page_size=0", "page_size=51", "page=" + str(2**63)]:
            assert client.get(path + "?" + invalid).status_code == 422


def test_collection_names_are_validated_without_side_effects(client, write_headers):
    collection = create_collection(client, write_headers)
    for invalid in [
        {"name": " "},
        {"name": "Ї" * 101},
        {"name": 123},
        {"name": "Мої", "owner_id": 2},
        {},
    ]:
        for method, path in [
            ("POST", "/api/collections"),
            ("PUT", f"/api/collections/{collection['id']}"),
        ]:
            assert (
                client.request(method, path, json=invalid, headers=write_headers).status_code == 422
            )
    assert client.get(f"/api/collections/{collection['id']}").json() == collection
    assert len(client.get("/api/collections").json()["items"]) == 1
    assert (
        client.put(
            f"/api/collections/{collection['id']}", json={"name": "Ї" * 100}, headers=write_headers
        ).status_code
        == 200
    )


def test_all_collection_endpoints_require_session_and_writes_require_origin_csrf_and_json(
    client, write_headers, origin, collection_data
):
    collection = create_collection(client, write_headers)
    path = f"/api/collections/{collection['id']}"
    mutations = [
        ("POST", "/api/collections", {"name": "Мої"}),
        ("PUT", path, {"name": "Нова"}),
        ("DELETE", path, None),
        ("PUT", path + "/recipes/1", None),
        ("DELETE", path + "/recipes/1", None),
    ]
    for method, url, body in mutations:
        kwargs = {"json": body} if body else {}
        assert client.request(method, url, **kwargs).status_code == 403
        assert client.request(method, url, headers=origin, **kwargs).status_code == 403
        assert (
            client.request(
                method, url, headers={**write_headers, "X-CSRF-Token": "invalid"}, **kwargs
            ).status_code
            == 403
        )
    for method, url in [("POST", "/api/collections"), ("PUT", path)]:
        assert (
            client.request(
                method,
                url,
                content='{"name":"Name"}',
                headers={**write_headers, "Content-Type": "text/plain"},
            ).status_code
            == 415
        )
    assert client.get(path).headers["Cache-Control"] == "no-store"
    client.cookies.clear()
    for url in ["/api/collections", path, path + "/recipes"]:
        assert client.get(url).status_code == 401
    for method, url, body in mutations:
        assert (
            client.request(
                method, url, headers=write_headers, **({"json": body} if body else {})
            ).status_code
            == 401
        )


@pytest.mark.parametrize("operation", ["add", "remove"])
def test_entry_and_collection_timestamp_roll_back_together_on_failure(
    client, database, write_headers, collection_data, test_settings, operation
):
    collection = create_collection(client, write_headers)
    path = f"{entries_url(collection['id'])}/{collection_data['recipes'][1]}"
    if operation == "remove":
        assert client.put(path, headers=write_headers).status_code == 204
    before = client.get(f"/api/collections/{collection['id']}").json()
    before_entries = client.get(entries_url(collection["id"])).json()
    database.execute(
        "CREATE FUNCTION fail_collection_touch() RETURNS trigger LANGUAGE plpgsql "
        "AS $$ BEGIN RAISE EXCEPTION 'forced test failure'; END $$"
    )
    database.execute(
        "CREATE TRIGGER reject_collection_update BEFORE UPDATE ON collections "
        "FOR EACH ROW EXECUTE FUNCTION fail_collection_touch()"
    )
    try:
        with TestClient(create_app(test_settings), raise_server_exceptions=False) as failing_client:
            failing_client.cookies.update(client.cookies)
            response = failing_client.request(
                "PUT" if operation == "add" else "DELETE", path, headers=write_headers
            )
        assert response.status_code == 500 and response.json()["error"]["code"] == "INTERNAL_ERROR"
        assert "forced test failure" not in response.text
    finally:
        database.execute("DROP TRIGGER reject_collection_update ON collections")
        database.execute("DROP FUNCTION fail_collection_touch()")
    assert client.get(f"/api/collections/{collection['id']}").json() == before
    assert client.get(entries_url(collection["id"])).json() == before_entries


def test_concurrent_duplicate_adds_create_one_entry(
    client, database, write_headers, collection_data, register_and_login, test_settings
):
    collection = create_collection(client, write_headers)
    actor = User(**register_and_login["user"])
    barrier = Barrier(2)

    def add():
        with connect(test_settings) as connection:
            connection.execute("SET statement_timeout = '5s'")
            service = CollectionService(
                PostgreSQLCollectionRepository(connection),
                PostgreSQLRecipeRepository(connection),
                connection.transaction,
            )
            barrier.wait(timeout=5)
            service.add_entry(collection["id"], collection_data["recipes"][1], actor)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(add), pool.submit(add)]
        for future in futures:
            future.result(timeout=10)
    assert len(client.get(entries_url(collection["id"])).json()["items"]) == 1
    assert database.execute("SELECT count(*) AS n FROM collection_entries").fetchone()["n"] == 1


def assert_blocked_by(database, waiter_pid, blocker_pid):
    deadline = monotonic() + 3
    while monotonic() < deadline:
        blockers = database.execute(
            "SELECT pg_blocking_pids(%s) AS pids", (waiter_pid,)
        ).fetchone()["pids"]
        if blocker_pid in blockers:
            return
        sleep(0.01)
    pytest.fail("Expected recipe lock was not observed")


def test_add_locks_recipe_until_commit_and_later_hidden_entry_is_redacted(
    client, database, write_headers, collection_data, register_and_login, test_settings
):
    collection = create_collection(client, write_headers)
    recipe_id = collection_data["recipes"][1]
    actor = User(**register_and_login["user"])
    locked, writer_ready, release = Event(), Event(), Event()
    pids = {}

    class BlockingReader(PostgreSQLRecipeRepository):
        def find_by_id(self, recipe_id, *, for_share=False):
            recipe = super().find_by_id(recipe_id, for_share=for_share)
            locked.set()
            assert release.wait(timeout=8)
            return recipe

    def add():
        with connect(test_settings) as connection:
            connection.execute("SET statement_timeout = '5s'")
            pids["adder"] = connection.info.backend_pid
            service = CollectionService(
                PostgreSQLCollectionRepository(connection),
                BlockingReader(connection),
                connection.transaction,
            )
            service.add_entry(collection["id"], recipe_id, actor)

    def hide():
        with connect(test_settings) as connection:
            connection.execute("SET statement_timeout = '5s'")
            pids["writer"] = connection.info.backend_pid
            writer_ready.set()
            connection.execute(
                "UPDATE recipes SET status = 'HIDDEN', hide_reason = 'Перевірка' WHERE id = %s",
                (recipe_id,),
            )

    with ThreadPoolExecutor(max_workers=2) as pool:
        adder = pool.submit(add)
        try:
            assert locked.wait(timeout=5)
            writer = pool.submit(hide)
            assert writer_ready.wait(timeout=5)
            assert_blocked_by(database, pids["writer"], pids["adder"])
        finally:
            release.set()
        adder.result(timeout=10)
        writer.result(timeout=10)
    entry = client.get(entries_url(collection["id"])).json()["items"][0]
    assert not entry["available"] and entry["recipe"] is None


def test_add_waits_for_unpublication_and_checks_committed_status(
    client, database, write_headers, collection_data, register_and_login, test_settings
):
    collection = create_collection(client, write_headers)
    recipe_id = collection_data["recipes"][1]
    actor = User(**register_and_login["user"])
    writer_locked, adder_ready, release = Event(), Event(), Event()
    pids = {}

    def unpublish():
        with connect(test_settings) as connection, connection.transaction():
            pids["writer"] = connection.info.backend_pid
            connection.execute("UPDATE recipes SET status = 'DRAFT' WHERE id = %s", (recipe_id,))
            writer_locked.set()
            assert release.wait(timeout=8)

    def add():
        with connect(test_settings) as connection:
            connection.execute("SET statement_timeout = '5s'")
            pids["adder"] = connection.info.backend_pid
            service = CollectionService(
                PostgreSQLCollectionRepository(connection),
                PostgreSQLRecipeRepository(connection),
                connection.transaction,
            )
            adder_ready.set()
            with pytest.raises(RecipeNotFound):
                service.add_entry(collection["id"], recipe_id, actor)

    with ThreadPoolExecutor(max_workers=2) as pool:
        writer = pool.submit(unpublish)
        try:
            assert writer_locked.wait(timeout=5)
            adder = pool.submit(add)
            assert adder_ready.wait(timeout=5)
            assert_blocked_by(database, pids["adder"], pids["writer"])
        finally:
            release.set()
        writer.result(timeout=10)
        adder.result(timeout=10)
    assert client.get(entries_url(collection["id"])).json()["items"] == []
