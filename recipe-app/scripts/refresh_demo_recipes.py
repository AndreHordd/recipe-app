"""Refresh the local demonstration recipes with complete, concrete instructions."""

from decimal import Decimal

from psycopg import Connection, sql

from app.config import Settings
from app.domain.enums import IngredientUnit
from app.domain.recipes import InstructionStep, RecipeIngredient
from app.infrastructure.database import connect
from app.infrastructure.repositories.recipes import PostgreSQLRecipeRepository
from scripts.demo_recipes import DEMO_RECIPES


def catalog_ids(connection: Connection, table: str) -> dict[str, int]:
    rows = connection.execute(
        sql.SQL("SELECT id, normalized_name FROM {} ").format(sql.Identifier(table))
    ).fetchall()
    return {row["normalized_name"]: row["id"] for row in rows}


def refresh(connection: Connection) -> int:
    categories = catalog_ids(connection, "categories")
    tags = catalog_ids(connection, "tags")
    ingredients = catalog_ids(connection, "ingredients")
    authors = connection.execute(
        "SELECT id FROM users WHERE email IN ('andriy@example.com', 'viktoriia@example.com') "
        "ORDER BY email"
    ).fetchall()
    repository = PostgreSQLRecipeRepository(connection)
    refreshed = 0
    with connection.transaction():
        for index, demo in enumerate(DEMO_RECIPES):
            author_id = authors[index % len(authors)]["id"]
            row = connection.execute(
                "SELECT id FROM recipes WHERE author_id = %s AND title = %s",
                (author_id, demo.title),
            ).fetchone()
            if not row:
                continue
            recipe = repository.find_by_id(row["id"])
            if recipe is None:
                continue
            recipe.description = demo.description
            recipe.cooking_time = demo.cooking_time
            recipe.servings = demo.servings
            recipe.category_id = categories[demo.category.casefold()]
            recipe.tag_ids = [tags[tag.casefold()] for tag in demo.tags]
            recipe.ingredients = [
                RecipeIngredient(
                    ingredient_id=ingredients[name.casefold()],
                    quantity=Decimal(quantity),
                    unit=IngredientUnit(unit),
                    position=position,
                    name=name,
                )
                for position, (name, quantity, unit) in enumerate(demo.ingredients, 1)
            ]
            recipe.steps = [InstructionStep(number, text) for number, text in enumerate(demo.steps, 1)]
            repository.save(recipe, recipe.version)
            refreshed += 1
        refreshed += refresh_legacy_recipe(
            connection,
            repository,
            categories,
            tags,
            ingredients,
            ["Омлет із зеленню для демонстрації"],
            title="Омлет із зеленню",
            description="Пухкий омлет із молоком, кропом і вершковим маслом на дві порції.",
            cooking_time=12,
            servings=2,
            category="Сніданки",
            recipe_tags=["Швидко", "Вегетаріанське"],
            recipe_ingredients=[
                ("Яйце", "3", "pcs"),
                ("Молоко", "45", "ml"),
                ("Кріп", "10", "g"),
                ("Вершкове масло", "5", "g"),
                ("Сіль", "1", "g"),
            ],
            steps=[
                "Збийте 3 яйця з 45 мл молока та 1 г солі протягом 30 секунд.",
                "Розтопіть 5 г масла на сковороді 20 см, влийте суміш і готуйте під кришкою 4 хвилини на слабкому вогні.",
                "Посипте 10 г подрібненого кропу, складіть омлет навпіл і прогрійте ще 1 хвилину перед подачею.",
            ],
        )
        refreshed += refresh_legacy_recipe(
            connection,
            repository,
            categories,
            tags,
            ingredients,
            ["ugy"],
            title="Салат з огірків і помідорів",
            description="Свіжий овочевий салат із простою олійною заправкою на дві порції.",
            cooking_time=10,
            servings=2,
            category="Салати",
            recipe_tags=["Швидко", "Вегетаріанське", "Без глютену"],
            recipe_ingredients=[
                ("Огірок", "2", "pcs"),
                ("Помідор", "2", "pcs"),
                ("Олія", "15", "ml"),
                ("Сіль", "2", "g"),
            ],
            steps=[
                "Помийте 2 огірки та 2 помідори й наріжте шматочками 1–2 см.",
                "Додайте 2 г солі та 15 мл олії, перемішайте і залиште на 3 хвилини.",
                "Подавайте салат одразу, щоб овочі залишилися хрусткими.",
            ],
        )
    return refreshed


def refresh_legacy_recipe(
    connection: Connection,
    repository: PostgreSQLRecipeRepository,
    categories: dict[str, int],
    tags: dict[str, int],
    ingredients: dict[str, int],
    source_titles: list[str],
    *,
    title: str,
    description: str,
    cooking_time: int,
    servings: int,
    category: str,
    recipe_tags: list[str],
    recipe_ingredients: list[tuple[str, str, str]],
    steps: list[str],
) -> int:
    row = connection.execute(
        "SELECT id FROM recipes WHERE title = ANY(%s) ORDER BY id LIMIT 1", (source_titles,)
    ).fetchone()
    if not row:
        return 0
    recipe = repository.find_by_id(row["id"])
    if recipe is None:
        return 0
    recipe.title = title
    recipe.description = description
    recipe.cooking_time = cooking_time
    recipe.servings = servings
    recipe.category_id = categories[category.casefold()]
    recipe.tag_ids = [tags[tag.casefold()] for tag in recipe_tags]
    recipe.ingredients = [
        RecipeIngredient(
            ingredient_id=ingredients[name.casefold()],
            quantity=Decimal(quantity),
            unit=IngredientUnit(unit),
            position=position,
            name=name,
        )
        for position, (name, quantity, unit) in enumerate(recipe_ingredients, 1)
    ]
    recipe.steps = [InstructionStep(number, text) for number, text in enumerate(steps, 1)]
    repository.save(recipe, recipe.version)
    return 1


def main() -> None:
    with connect(Settings()) as connection:
        count = refresh(connection)
    print(f"Оновлено демонстраційних рецептів: {count}")


if __name__ == "__main__":
    main()
