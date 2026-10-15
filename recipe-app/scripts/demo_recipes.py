from dataclasses import dataclass
from decimal import Decimal

from psycopg import Connection, sql

from app.domain.enums import IngredientUnit, RecipeStatus
from app.domain.recipes import InstructionStep, Recipe, RecipeDetails, RecipeIngredient
from app.infrastructure.repositories.recipes import PostgreSQLRecipeRepository


@dataclass(frozen=True)
class DemoRecipe:
    title: str
    category: str
    cooking_time: int
    ingredients: list[tuple[str, str, str]]
    steps: list[str]
    tags: list[str]
    status: RecipeStatus = RecipeStatus.PUBLISHED


DEMO_RECIPES = [
    DemoRecipe(
        "Омлет із сиром",
        "Сніданки",
        15,
        [("Яйце", "3", "pcs"), ("Молоко", "50", "ml"), ("Сир", "60", "g")],
        ["Збийте яйця з молоком.", "Вилийте на сковороду, додайте сир і готуйте під кришкою."],
        ["Швидко", "Вегетаріанське"],
    ),
    DemoRecipe(
        "Млинці на молоці",
        "Сніданки",
        30,
        [
            ("Молоко", "300", "ml"),
            ("Яйце", "2", "pcs"),
            ("Борошно", "150", "g"),
            ("Олія", "1", "tbsp"),
        ],
        [
            "Змішайте яйця, молоко та борошно до однорідності.",
            "Додайте олію. Смажте тонкі млинці з обох боків.",
        ],
        ["Бюджетне"],
    ),
    DemoRecipe(
        "Картопляний суп",
        "Перші страви",
        40,
        [
            ("Картопля", "400", "g"),
            ("Морква", "1", "pcs"),
            ("Цибуля", "1", "pcs"),
            ("Сіль", "1", "pinch"),
        ],
        [
            "Наріжте овочі й залийте літром води.",
            "Варіть до м’якості картоплі, посоліть наприкінці.",
        ],
        ["Бюджетне", "Вегетаріанське"],
    ),
    DemoRecipe(
        "Рис із овочами",
        "Основні страви",
        30,
        [
            ("Рис", "200", "g"),
            ("Морква", "1", "pcs"),
            ("Цибуля", "1", "pcs"),
            ("Олія", "1", "tbsp"),
        ],
        [
            "Промийте й відваріть рис за вказівками на упаковці.",
            "Підсмажте нарізані овочі на олії та змішайте з рисом.",
        ],
        ["Вегетаріанське"],
    ),
    DemoRecipe(
        "Гречка з вершковим маслом",
        "Основні страви",
        25,
        [("Гречка", "200", "g"), ("Вершкове масло", "25", "g"), ("Сіль", "1", "pinch")],
        [
            "Промийте гречку. Додайте 400 мл води та сіль.",
            "Варіть під кришкою до готовності, додайте вершкове масло.",
        ],
        ["Бюджетне"],
    ),
    DemoRecipe(
        "Куряче філе з часником",
        "Основні страви",
        35,
        [("Куряче філе", "400", "g"), ("Часник", "2", "pcs"), ("Олія", "1", "tbsp")],
        [
            "Наріжте філе й подрібніть часник.",
            "Обсмажте філе на олії, додайте часник і доведіть до повної готовності.",
        ],
        ["Без глютену"],
    ),
    DemoRecipe(
        "Салат з огірків і помідорів",
        "Салати",
        10,
        [("Огірок", "2", "pcs"), ("Помідор", "2", "pcs"), ("Олія", "1", "tbsp")],
        ["Помийте та наріжте овочі.", "Заправте олією й перемішайте."],
        ["Швидко", "Вегетаріанське"],
    ),
    DemoRecipe(
        "Морквяний салат зі сметаною",
        "Салати",
        10,
        [("Морква", "2", "pcs"), ("Сметана", "2", "tbsp"), ("Часник", "1", "pcs")],
        ["Натріть моркву та подрібніть часник.", "Додайте сметану і перемішайте."],
        ["Швидко"],
    ),
    DemoRecipe(
        "Сирники",
        "Десерти",
        30,
        [
            ("Сир", "300", "g"),
            ("Яйце", "1", "pcs"),
            ("Борошно", "3", "tbsp"),
            ("Цукор", "1", "tbsp"),
            ("Олія", "1", "tbsp"),
        ],
        [
            "Використайте кисломолочний сир. Змішайте його з яйцем, цукром і борошном.",
            "Сформуйте невеликі сирники та обсмажте з обох боків до готовності.",
        ],
        ["Святкове"],
    ),
    DemoRecipe(
        "Картопляне пюре",
        "Основні страви",
        30,
        [("Картопля", "500", "g"), ("Молоко", "100", "ml"), ("Вершкове масло", "30", "g")],
        [
            "Очистьте картоплю та відваріть до м’якості.",
            "Злийте воду. Розімніть картоплю з теплим молоком і маслом.",
        ],
        ["Вегетаріанське"],
    ),
    DemoRecipe(
        "Задум овочевої запіканки",
        "Основні страви",
        45,
        [("Картопля", "300", "g"), ("Морква", "1", "pcs")],
        [],
        ["Бюджетне"],
        RecipeStatus.DRAFT,
    ),
    DemoRecipe(
        "Яєчня з помідорами",
        "Сніданки",
        15,
        [("Яйце", "2", "pcs"), ("Помідор", "1", "pcs"), ("Олія", "1", "tsp")],
        [
            "Наріжте помідор і прогрійте на сковороді.",
            "Додайте яйця та готуйте до бажаної консистенції.",
        ],
        ["Швидко"],
        RecipeStatus.HIDDEN,
    ),
]


def seed_recipes(connection: Connection) -> None:
    catalogs = {}
    for table in ["categories", "tags", "ingredients"]:
        rows = connection.execute(
            sql.SQL("SELECT id, normalized_name FROM {}").format(sql.Identifier(table))
        ).fetchall()
        catalogs[table] = {row["normalized_name"]: row["id"] for row in rows}
    authors = connection.execute(
        "SELECT id FROM users WHERE email IN ('andriy@example.com', 'viktoriia@example.com') "
        "ORDER BY email"
    ).fetchall()
    repository = PostgreSQLRecipeRepository(connection)
    for index, demo in enumerate(DEMO_RECIPES):
        author_id = authors[index % len(authors)]["id"]
        existing = connection.execute(
            "SELECT id FROM recipes WHERE author_id = %s AND title = %s", (author_id, demo.title)
        ).fetchone()
        if existing:
            continue
        details = RecipeDetails(
            title=demo.title,
            description=f"Домашній рецепт: {demo.title.casefold()}.",
            cooking_time=demo.cooking_time,
            servings=2,
            category_id=catalogs["categories"][demo.category.casefold()],
            tag_ids=[catalogs["tags"][tag.casefold()] for tag in demo.tags],
            ingredients=[
                RecipeIngredient(
                    catalogs["ingredients"][name.casefold()],
                    Decimal(quantity),
                    IngredientUnit(unit),
                    position,
                )
                for position, (name, quantity, unit) in enumerate(demo.ingredients, 1)
            ],
            steps=[InstructionStep(number, text) for number, text in enumerate(demo.steps, 1)],
        )
        recipe = Recipe.create(author_id, details)
        if demo.status != RecipeStatus.DRAFT:
            recipe.publish()
        if demo.status == RecipeStatus.HIDDEN:
            recipe.hide("Демонстрація модерації: уточніть ступінь готовності яєць.")
        repository.save(recipe, None)
