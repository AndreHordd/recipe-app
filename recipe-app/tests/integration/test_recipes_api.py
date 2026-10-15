from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier

import pytest
from fastapi.testclient import TestClient

from app.domain.enums import IngredientUnit
from app.domain.exceptions import VersionConflict
from app.domain.recipes import InstructionStep, RecipeDetails, RecipeIngredient
from app.infrastructure.database import connect
from app.infrastructure.repositories.recipes import PostgreSQLRecipeRepository
from app.main import create_app

pytestmark = pytest.mark.integration


@pytest.fixture
def recipe_data(database):
    category = database.execute(
        "INSERT INTO categories (name, normalized_name) VALUES ('Сніданки', 'сніданки') "
        "RETURNING id"
    ).fetchone()["id"]
    tags = []
    for name in ["Швидко", "Бюджетне"]:
        tags.append(
            database.execute(
                "INSERT INTO tags (name, normalized_name) VALUES (%s, %s) RETURNING id",
                (name, name.casefold()),
            ).fetchone()["id"]
        )
    ingredient = database.execute(
        "INSERT INTO ingredients (name, normalized_name) VALUES ('Яйце', 'яйце') RETURNING id"
    ).fetchone()["id"]
    return {
        "title": "  Омлет  ",
        "description": "Простий сніданок",
        "cooking_time": 10,
        "servings": 2,
        "category_id": category,
        "tag_ids": tags,
        "ingredients": [
            {"ingredient_id": ingredient, "quantity": "2", "unit": "pcs"},
            {"ingredient_id": ingredient, "quantity": "1.250", "unit": "pcs"},
        ],
        "steps": [{"description": "  Збити яйця.  "}, {"description": "Посмажити."}],
    }


@pytest.fixture
def write_headers(register_and_login, origin):
    return {**origin, "X-CSRF-Token": register_and_login["csrf_token"]}


def create_recipe(client, headers, data):
    response = client.post("/api/recipes", json=data, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def test_complete_lifecycle_and_private_visibility(client, write_headers, recipe_data):
    recipe = create_recipe(client, write_headers, recipe_data)
    recipe_id = recipe["id"]
    assert recipe["title"] == "Омлет" and recipe["status"] == "DRAFT"
    assert recipe["version"] == 1 and recipe["published_at"] is None
    assert recipe["author"] == {"id": 1, "display_name": "Користувач"}
    assert [item["position"] for item in recipe["ingredients"]] == [1, 2]
    assert [step["number"] for step in recipe["steps"]] == [1, 2]
    assert recipe["steps"][0]["description"] == "Збити яйця."
    assert Decimal(recipe["ingredients"][1]["quantity"]) == Decimal("1.250")
    assert len(recipe["tags"]) == 2
    assert client.get("/api/recipes").json()["items"] == []
    assert client.get("/api/recipes/mine?status=DRAFT").json()["items"][0]["id"] == recipe_id
    cookie = client.cookies.get("recipe_session")
    client.cookies.clear()
    assert client.get(f"/api/recipes/{recipe_id}").status_code == 404
    assert client.get("/api/recipes/mine").status_code == 401
    client.cookies.set("recipe_session", cookie)
    published = client.post(
        f"/api/recipes/{recipe_id}/publish", json={"version": 1}, headers=write_headers
    ).json()
    assert published["status"] == "PUBLISHED" and published["version"] == 2
    assert published["published_at"]
    client.cookies.clear()
    public = client.get(f"/api/recipes/{recipe_id}")
    assert public.status_code == 200 and public.json() == published
    assert "email" not in public.text and "csrf" not in public.text
    assert client.get("/api/recipes").json()["items"][0]["id"] == recipe_id
    client.cookies.set("recipe_session", cookie)
    edited = client.put(
        f"/api/recipes/{recipe_id}",
        json={**recipe_data, "title": "Новий омлет", "version": 2},
        headers=write_headers,
    ).json()
    assert edited["version"] == 3 and edited["status"] == "DRAFT"
    assert edited["published_at"] == published["published_at"]
    assert client.get("/api/recipes").json()["items"] == []
    republished = client.post(
        f"/api/recipes/{recipe_id}/publish", json={"version": 3}, headers=write_headers
    ).json()
    assert republished["published_at"] >= published["published_at"]
    unpublished = client.post(
        f"/api/recipes/{recipe_id}/unpublish", json={"version": 4}, headers=write_headers
    )
    assert unpublished.status_code == 200 and unpublished.json()["version"] == 5
    assert unpublished.json()["published_at"] == republished["published_at"]


def test_incomplete_draft_and_invalid_transitions(client, write_headers):
    recipe = create_recipe(client, write_headers, {"title": "Ідея"})
    for action, code in [("publish", "INVALID_RECIPE"), ("unpublish", "INVALID_STATE")]:
        response = client.post(
            f"/api/recipes/{recipe['id']}/{action}", json={"version": 1}, headers=write_headers
        )
        assert response.json()["error"]["code"] == code
    assert client.get(f"/api/recipes/{recipe['id']}").json() == recipe


def test_hidden_recipe_cannot_escape_moderation(client, database, write_headers, recipe_data):
    recipe = create_recipe(client, write_headers, recipe_data)
    database.execute(
        "UPDATE recipes SET status = 'HIDDEN', hide_reason = 'Уточніть кроки', "
        "version = version + 1 WHERE id = %s",
        (recipe["id"],),
    )
    for action in ["publish", "unpublish"]:
        response = client.post(
            f"/api/recipes/{recipe['id']}/{action}", json={"version": 2}, headers=write_headers
        )
        assert response.status_code == 409
    edited = client.put(
        f"/api/recipes/{recipe['id']}",
        json={"title": "Виправлення", "version": 2},
        headers=write_headers,
    ).json()
    assert edited["status"] == "HIDDEN" and edited["hide_reason"] == "Уточніть кроки"
    assert edited["ingredients"] == [] and edited["steps"] == [] and edited["version"] == 3
    assert client.get("/api/recipes/mine?status=HIDDEN").json()["items"][0]["id"] == recipe["id"]


@pytest.mark.parametrize("role", ["USER", "ADMIN"])
def test_other_user_and_admin_cannot_edit_foreign_recipe(
    client, database, origin, write_headers, recipe_data, role
):
    recipe = create_recipe(client, write_headers, recipe_data)
    client.post(
        "/api/auth/register",
        headers=origin,
        json={
            "email": "second@example.com",
            "display_name": "Інший",
            "password": "password-456",
        },
    )
    database.execute("UPDATE users SET role = %s WHERE email = 'second@example.com'", (role,))
    session = client.post(
        "/api/auth/login",
        headers=origin,
        json={
            "email": "second@example.com",
            "password": "password-456",
        },
    ).json()
    headers = {**origin, "X-CSRF-Token": session["csrf_token"]}
    assert client.get("/api/recipes/mine").json()["items"] == []
    assert client.get(f"/api/recipes/{recipe['id']}").status_code == (
        200 if role == "ADMIN" else 404
    )
    assert client.put(
        f"/api/recipes/{recipe['id']}", json={**recipe_data, "version": 1}, headers=headers
    ).status_code == (403 if role == "ADMIN" else 404)
    client.cookies.clear()
    # Make the recipe publicly visible using the owner's existing session.
    owner_login = client.post(
        "/api/auth/login",
        headers=origin,
        json={
            "email": "user@example.com",
            "password": "password-123",
        },
    ).json()
    client.post(
        f"/api/recipes/{recipe['id']}/publish",
        json={"version": 1},
        headers={
            **origin,
            "X-CSRF-Token": owner_login["csrf_token"],
        },
    )
    session = client.post(
        "/api/auth/login",
        headers=origin,
        json={
            "email": "second@example.com",
            "password": "password-456",
        },
    ).json()
    headers["X-CSRF-Token"] = session["csrf_token"]
    for method, path, body in [
        ("PUT", f"/api/recipes/{recipe['id']}", {**recipe_data, "version": 2}),
        ("POST", f"/api/recipes/{recipe['id']}/unpublish", {"version": 2}),
        ("DELETE", f"/api/recipes/{recipe['id']}?version=2", None),
    ]:
        kwargs = {"headers": headers}
        if body is not None:
            kwargs["json"] = body
        assert client.request(method, path, **kwargs).status_code == 403


def test_stale_version_never_overwrites_current_data(client, write_headers, recipe_data):
    recipe = create_recipe(client, write_headers, recipe_data)
    current = client.put(
        f"/api/recipes/{recipe['id']}",
        json={**recipe_data, "title": "Актуальна", "version": 1},
        headers=write_headers,
    ).json()
    for method, path, body in [
        ("PUT", f"/api/recipes/{recipe['id']}", {**recipe_data, "version": 1}),
        ("POST", f"/api/recipes/{recipe['id']}/publish", {"version": 1}),
        ("POST", f"/api/recipes/{recipe['id']}/unpublish", {"version": 1}),
        ("DELETE", f"/api/recipes/{recipe['id']}?version=1", None),
    ]:
        kwargs = {"headers": write_headers}
        if body is not None:
            kwargs["json"] = body
        response = client.request(method, path, **kwargs)
        assert (
            response.status_code == 409 and response.json()["error"]["code"] == "VERSION_CONFLICT"
        )
    assert client.get(f"/api/recipes/{recipe['id']}").json() == current


@pytest.mark.parametrize("reference", ["category_id", "tag_ids", "ingredients"])
def test_invalid_reference_rolls_back_create_and_update(
    client, database, write_headers, recipe_data, reference
):
    recipe = create_recipe(client, write_headers, recipe_data)
    invalid = dict(recipe_data)
    invalid[reference] = {
        "category_id": 9999,
        "tag_ids": [9999],
        "ingredients": [{"ingredient_id": 9999, "quantity": "1", "unit": "g"}],
    }[reference]
    assert client.post("/api/recipes", json=invalid, headers=write_headers).status_code == 422
    response = client.put(
        f"/api/recipes/{recipe['id']}", json={**invalid, "version": 1}, headers=write_headers
    )
    assert response.status_code == 422 and response.json()["error"]["code"] == "INVALID_REFERENCE"
    assert client.get(f"/api/recipes/{recipe['id']}").json() == recipe
    assert database.execute("SELECT count(*) AS n FROM recipes").fetchone()["n"] == 1


def test_child_insert_failure_rolls_back_entire_update(
    client, test_settings, database, write_headers, recipe_data
):
    recipe = create_recipe(client, write_headers, recipe_data)
    database.execute("""CREATE FUNCTION fail_step_insert() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'Injected failure'; END $$""")
    database.execute("""CREATE TRIGGER fail_steps BEFORE INSERT ON instruction_steps
        FOR EACH ROW EXECUTE FUNCTION fail_step_insert()""")
    try:
        with TestClient(create_app(test_settings), raise_server_exceptions=False) as failing:
            failing.cookies.update(client.cookies)
            response = failing.put(
                f"/api/recipes/{recipe['id']}",
                headers=write_headers,
                json={
                    **recipe_data,
                    "title": "Не збережено",
                    "ingredients": [],
                    "version": 1,
                },
            )
        assert response.status_code == 500
        assert response.json()["error"]["code"] == "INTERNAL_ERROR"
        assert client.get(f"/api/recipes/{recipe['id']}").json() == recipe
    finally:
        database.execute("DROP TRIGGER fail_steps ON instruction_steps")
        database.execute("DROP FUNCTION fail_step_insert()")


def test_real_concurrent_updates_commit_only_one_aggregate(
    client, write_headers, recipe_data, test_settings
):
    recipe = create_recipe(client, write_headers, recipe_data)
    barrier = Barrier(2)

    def update(title):
        with connect(test_settings) as connection:
            repository = PostgreSQLRecipeRepository(connection)
            aggregate = repository.find_by_id(recipe["id"])
            aggregate.update_details(
                RecipeDetails(
                    title=title,
                    ingredients=[
                        RecipeIngredient(
                            recipe_data["ingredients"][0]["ingredient_id"],
                            Decimal("1"),
                            IngredientUnit.PIECE,
                            1,
                        )
                    ],
                    steps=[InstructionStep(1, title)],
                )
            )
            barrier.wait(timeout=10)
            try:
                with connection.transaction():
                    repository.save(aggregate, 1)
                return title
            except VersionConflict:
                return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(update, ["Перша зміна", "Друга зміна"]))
    winners = [title for title in outcomes if title]
    assert len(winners) == 1
    current = client.get(f"/api/recipes/{recipe['id']}").json()
    assert current["version"] == 2 and current["title"] == winners[0]
    assert current["steps"] == [{"number": 1, "description": winners[0]}]
    assert len(current["ingredients"]) == 1 and current["tags"] == []


def test_delete_cascades_recipe_children_and_collection_entry(
    client, database, write_headers, recipe_data, register_and_login
):
    recipe = create_recipe(client, write_headers, recipe_data)
    collection = database.execute(
        "INSERT INTO collections (owner_id, name) VALUES (%s, 'Мої страви') RETURNING id",
        (register_and_login["user"]["id"],),
    ).fetchone()["id"]
    database.execute(
        "INSERT INTO collection_entries (collection_id, recipe_id) VALUES (%s, %s)",
        (collection, recipe["id"]),
    )
    assert client.delete(f"/api/recipes/{recipe['id']}", headers=write_headers).status_code == 422
    assert (
        client.delete(f"/api/recipes/{recipe['id']}?version=1", headers=write_headers).status_code
        == 204
    )
    assert client.get(f"/api/recipes/{recipe['id']}").status_code == 404
    for table in ["recipe_ingredients", "instruction_steps", "recipe_tags", "collection_entries"]:
        # Table names are fixed test constants, never request input.
        assert database.execute(f"SELECT count(*) AS n FROM {table}").fetchone()["n"] == 0
    assert database.execute("SELECT count(*) AS n FROM collections").fetchone()["n"] == 1
    assert database.execute("SELECT count(*) AS n FROM ingredients").fetchone()["n"] == 1


def test_recipe_pagination_filter_and_input_validation(client, write_headers, recipe_data):
    ids = [
        create_recipe(client, write_headers, {**recipe_data, "title": f"Омлет {i}"})["id"]
        for i in range(3)
    ]
    for recipe_id in ids[:2]:
        assert (
            client.post(
                f"/api/recipes/{recipe_id}/publish", json={"version": 1}, headers=write_headers
            ).status_code
            == 200
        )
    first = client.get("/api/recipes/mine?page_size=2").json()
    second = client.get("/api/recipes/mine?page_size=2&page=2").json()
    assert [item["id"] for item in first["items"] + second["items"]] == ids[::-1]
    assert first["has_next"] and not second["has_next"]
    assert len(client.get("/api/recipes/mine?status=PUBLISHED").json()["items"]) == 2
    assert len(client.get("/api/recipes").json()["items"]) == 2
    for path in [
        "/api/recipes?page=0",
        "/api/recipes?page_size=51",
        "/api/recipes/mine?status=BAD",
    ]:
        assert client.get(path).status_code == 422
    for extra in [{"author_id": 2}, {"status": "PUBLISHED"}, {"version": 1}, {"tag_ids": [1, 1]}]:
        assert (
            client.post(
                "/api/recipes", json={**recipe_data, **extra}, headers=write_headers
            ).status_code
            == 422
        )


def test_every_recipe_mutation_requires_origin_session_and_csrf(
    client, write_headers, recipe_data, origin
):
    recipe = create_recipe(client, write_headers, recipe_data)
    mutations = [
        ("POST", "/api/recipes", recipe_data),
        ("PUT", f"/api/recipes/{recipe['id']}", {**recipe_data, "version": 1}),
        ("POST", f"/api/recipes/{recipe['id']}/publish", {"version": 1}),
        ("POST", f"/api/recipes/{recipe['id']}/unpublish", {"version": 1}),
        ("DELETE", f"/api/recipes/{recipe['id']}?version=1", None),
        ("POST", "/api/ingredients", {"name": "Молоко"}),
    ]
    for method, path, body in mutations:
        kwargs = {"json": body} if body is not None else {}
        assert client.request(method, path, **kwargs).status_code == 403
        assert client.request(method, path, headers=origin, **kwargs).status_code == 403
    client.cookies.clear()
    for method, path, body in mutations:
        kwargs = {"json": body} if body is not None else {}
        assert client.request(method, path, headers=write_headers, **kwargs).status_code == 401


def test_catalogue_names_are_idempotent_and_search_is_literal(client, write_headers, recipe_data):
    assert len(client.get("/api/categories").json()) == 1
    assert len(client.get("/api/tags").json()) == 2
    first = client.post(
        "/api/ingredients", json={"name": "  Вершкове   масло  "}, headers=write_headers
    )
    assert first.status_code == 201 and first.json()["name"] == "Вершкове масло"
    repeated = client.post(
        "/api/ingredients", json={"name": "ВЕРШКОВЕ МАСЛО"}, headers=write_headers
    )
    assert repeated.status_code == 200 and repeated.json() == first.json()
    assert client.get("/api/ingredients", params={"q": "  ВЕРШКОВЕ  "}).json()["items"] == [
        first.json()
    ]
    for name in ["100% какао", "a_b", "a\\b"]:
        assert (
            client.post("/api/ingredients", json={"name": name}, headers=write_headers).status_code
            == 201
        )
    for text, expected in [("%", "100% какао"), ("_", "a_b"), ("\\", "a\\b")]:
        results = client.get("/api/ingredients", params={"q": text}).json()["items"]
        assert [item["name"] for item in results] == [expected]
    page = client.get("/api/ingredients?page_size=2").json()
    assert len(page["items"]) == 2 and page["has_next"]
