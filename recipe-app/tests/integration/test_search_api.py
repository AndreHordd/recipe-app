import pytest

from app.domain.criteria import RecipeQuery
from app.infrastructure.repositories.recipes import PostgreSQLRecipeRepository
from scripts.seed import seed_database

pytestmark = pytest.mark.integration


@pytest.fixture
def search_data(database, test_settings):
    seed_database(database, test_settings)
    return {
        "categories": {
            row["name"]: row["id"]
            for row in database.execute("SELECT id, name FROM categories").fetchall()
        },
        "tags": {
            row["name"]: row["id"]
            for row in database.execute("SELECT id, name FROM tags").fetchall()
        },
        "recipes": {
            row["title"]: row["id"]
            for row in database.execute("SELECT id, title FROM recipes").fetchall()
        },
    }


def titles(response):
    assert response.status_code == 200, response.text
    return [recipe["title"] for recipe in response.json()["items"]]


def test_title_search_is_case_insensitive_in_ukrainian_and_literal(client, database, search_data):
    assert titles(client.get("/api/recipes", params={"q": "  ОМЛЕТ  "})) == ["Омлет із сиром"]
    assert set(titles(client.get("/api/recipes", params={"q": "сир"}))) == {
        "Сирники",
        "Омлет із сиром",
    }
    recipe_id = search_data["recipes"]["Омлет із сиром"]
    for special in ["100%", "a_b", "a\\b", "%' OR TRUE --"]:
        database.execute("UPDATE recipes SET title = %s WHERE id = %s", (special, recipe_id))
        assert titles(client.get("/api/recipes", params={"q": special})) == [special]
    assert titles(client.get("/api/recipes", params={"q": "does not exist"})) == []


def test_ingredient_strategy_does_not_duplicate_recipe_with_repeated_ingredient(
    client, database, search_data
):
    recipe_id = search_data["recipes"]["Омлет із сиром"]
    egg = database.execute("SELECT id FROM ingredients WHERE name = 'Яйце'").fetchone()["id"]
    database.execute(
        """INSERT INTO recipe_ingredients
        (recipe_id, position, ingredient_id, quantity, unit) VALUES (%s, 4, %s, 1, 'pcs')""",
        (recipe_id, egg),
    )
    data = client.get("/api/recipes", params={"mode": "ingredient", "q": "ЯЙЦ"})
    assert set(titles(data)) == {"Омлет із сиром", "Млинці на молоці", "Сирники"}
    ids = [item["id"] for item in data.json()["items"]]
    assert len(ids) == len(set(ids)) == 3
    for text, name in [("%", "100% какао"), ("_", "a_b"), ("\\", "a\\b")]:
        database.execute("UPDATE ingredients SET name = %s WHERE id = %s", (name, egg))
        assert set(
            titles(client.get("/api/recipes", params={"mode": "ingredient", "q": text}))
        ) == {
            "Омлет із сиром",
            "Млинці на молоці",
            "Сирники",
        }


def test_category_strategy_and_combined_filters_use_and(client, search_data):
    breakfast = search_data["categories"]["Сніданки"]
    fast = search_data["tags"]["Швидко"]
    assert set(
        titles(client.get("/api/recipes", params={"mode": "category", "category_id": breakfast}))
    ) == {
        "Омлет із сиром",
        "Млинці на молоці",
    }
    common = {"category_id": breakfast, "tag_id": fast, "max_cooking_time": 15}
    for params in [
        {"mode": "category"},
        {"mode": "title", "q": "ОМ"},
        {"mode": "ingredient", "q": "Яйце"},
    ]:
        assert titles(client.get("/api/recipes", params={**common, **params})) == ["Омлет із сиром"]
    assert titles(client.get("/api/recipes", params={**common, "max_cooking_time": 14})) == []
    assert (
        titles(
            client.get("/api/recipes", params={**common, "tag_id": search_data["tags"]["Святкове"]})
        )
        == []
    )
    for params in [{"category_id": 999999}, {"tag_id": 999999}]:
        assert titles(client.get("/api/recipes", params=params)) == []


@pytest.mark.parametrize("actor", [None, "andriy@example.com", "admin@example.com"])
def test_search_never_exposes_draft_or_hidden_even_to_author_or_admin(
    client, database, search_data, origin, actor
):
    if actor:
        password = (
            "Admin-test-password-123" if actor.startswith("admin") else "User-test-password-123"
        )
        assert (
            client.post(
                "/api/auth/login", json={"email": actor, "password": password}, headers=origin
            ).status_code
            == 200
        )
    for mode, params in [
        ("title", {}),
        ("ingredient", {"q": "Яйце"}),
        ("category", {"category_id": search_data["categories"]["Сніданки"]}),
    ]:
        response = client.get("/api/recipes", params={"mode": mode, **params})
        assert response.status_code == 200
        assert all(item["status"] == "PUBLISHED" for item in response.json()["items"])
        assert "hide_reason" not in response.text and "email" not in response.text
    for private_title in ["Задум овочевої запіканки", "Яєчня з помідорами"]:
        assert titles(client.get("/api/recipes", params={"q": private_title})) == []
    # Changing publication status immediately changes the search result.
    recipe_id = search_data["recipes"]["Омлет із сиром"]
    database.execute("UPDATE recipes SET status = 'DRAFT' WHERE id = %s", (recipe_id,))
    assert titles(client.get("/api/recipes", params={"q": "ОМЛЕТ"})) == []


def test_sort_and_pagination_are_stable_for_matching_titles(client, database, search_data):
    ids = [
        search_data["recipes"][title] for title in ["Омлет із сиром", "Млинці на молоці", "Сирники"]
    ]
    for recipe_id in ids:
        database.execute(
            "UPDATE recipes SET title = 'однакова', created_at = '2026-01-01' WHERE id = %s",
            (recipe_id,),
        )
    for sort, expected in [("newest", sorted(ids, reverse=True)), ("title", sorted(ids))]:
        results = []
        for page in range(1, 4):
            data = client.get(
                "/api/recipes", params={"q": "ОДНАКОВА", "sort": sort, "page_size": 1, "page": page}
            ).json()
            assert len(data["items"]) == 1 and data["has_next"] == (page < 3)
            results.append(data["items"][0]["id"])
        assert results == expected
    assert (
        titles(client.get("/api/recipes", params={"q": "ОДНАКОВА", "page_size": 1, "page": 4}))
        == []
    )
    # Uppercase Ukrainian letters must sort together with their lowercase forms.
    for recipe_id, title in zip(ids, ["Альфа", "бета", "Яблуко"], strict=True):
        database.execute("UPDATE recipes SET title = %s WHERE id = %s", (title, recipe_id))
    ordered = titles(client.get("/api/recipes", params={"sort": "title"}))
    assert ordered.index("Альфа") < ordered.index("бета") < ordered.index("Яблуко")


@pytest.mark.parametrize(
    "params",
    [
        {"mode": "unknown"},
        {"mode": "ingredient"},
        {"mode": "ingredient", "q": "  "},
        {"mode": "category"},
        {"mode": "category", "category_id": 1, "q": "x"},
        {"q": "x" * 101},
        {"category_id": 0},
        {"tag_id": -1},
        {"max_cooking_time": 0},
        {"max_cooking_time": 1441},
        {"max_cooking_time": "abc"},
        {"page": 0},
        {"page": 2**64},
        {"page_size": 51},
        {"sort": "title; DROP TABLE recipes"},
        {"scope": "moderation"},
        {"status": "DRAFT"},
        {"author_id": 1},
    ],
)
def test_invalid_search_criteria_return_422(client, search_data, params):
    response = client.get("/api/recipes", params=params)
    assert response.status_code == 422
    assert response.json()["error"]["code"] in {"VALIDATION_ERROR", "INVALID_SEARCH"}


def test_public_repository_scope_cannot_be_overridden_by_status(database, search_data):
    repository = PostgreSQLRecipeRepository(database)
    assert repository.find(RecipeQuery(scope="public", status="HIDDEN")) == []
    with pytest.raises(ValueError, match="sort"):
        repository.find(RecipeQuery(sort="title; DELETE FROM recipes"))


def test_search_page_and_openapi_expose_filters(client):
    page = client.get("/")
    assert page.status_code == 200 and 'id="search-form"' in page.text
    assert client.get("/static/js/catalog.js").status_code == 200
    parameters = client.get("/openapi.json").json()["paths"]["/api/recipes"]["get"]["parameters"]
    assert {parameter["name"] for parameter in parameters} == {
        "mode",
        "q",
        "category_id",
        "tag_id",
        "max_cooking_time",
        "page",
        "page_size",
        "sort",
    }
