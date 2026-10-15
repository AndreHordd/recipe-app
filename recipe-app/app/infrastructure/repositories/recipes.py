from decimal import Decimal

from psycopg import Connection
from psycopg.pq import TransactionStatus

from app.domain.contracts import IRecipeReader, IRecipeWriter
from app.domain.criteria import RecipeQuery
from app.domain.enums import IngredientUnit, RecipeStatus
from app.domain.exceptions import VersionConflict
from app.domain.recipes import CatalogItem, InstructionStep, Recipe, RecipeIngredient
from app.infrastructure.sql_patterns import escape_like

SORT_ORDERS = {
    "newest": "r.created_at DESC, r.id DESC",
    "title": "lower(r.title COLLATE pg_catalog.pg_c_utf8) ASC, r.id ASC",
}

RECIPE_FIELDS = """
r.*, u.display_name AS author_name, c.name AS category_name,
  COALESCE((SELECT jsonb_agg(jsonb_build_object(
      'ingredient_id', ri.ingredient_id, 'name', i.name, 'quantity', ri.quantity::text,
      'unit', ri.unit, 'position', ri.position) ORDER BY ri.position)
    FROM recipe_ingredients ri JOIN ingredients i ON i.id = ri.ingredient_id
    WHERE ri.recipe_id = r.id), '[]'::jsonb) AS ingredients,
  COALESCE((SELECT jsonb_agg(jsonb_build_object(
      'number', s.number, 'description', s.description) ORDER BY s.number)
    FROM instruction_steps s WHERE s.recipe_id = r.id), '[]'::jsonb) AS steps,
  COALESCE((SELECT jsonb_agg(jsonb_build_object('id', t.id, 'name', t.name) ORDER BY t.id)
    FROM recipe_tags rt JOIN tags t ON t.id = rt.tag_id
    WHERE rt.recipe_id = r.id), '[]'::jsonb) AS tags
"""
RECIPE_JOINS = """
JOIN users u ON u.id = r.author_id
LEFT JOIN categories c ON c.id = r.category_id
"""
RECIPE_SELECT = "SELECT " + RECIPE_FIELDS + " FROM recipes r " + RECIPE_JOINS


def recipe_from_row(row: dict) -> Recipe:
    return Recipe(
        id=row["id"],
        author_id=row["author_id"],
        author_name=row["author_name"],
        title=row["title"],
        description=row["description"],
        cooking_time=row["cooking_time"],
        servings=row["servings"],
        category_id=row["category_id"],
        category_name=row["category_name"],
        tag_ids=[tag["id"] for tag in row["tags"]],
        tags=[CatalogItem(**tag) for tag in row["tags"]],
        ingredients=[
            RecipeIngredient(
                ingredient_id=item["ingredient_id"],
                name=item["name"],
                quantity=Decimal(item["quantity"]),
                unit=IngredientUnit(item["unit"]),
                position=item["position"],
            )
            for item in row["ingredients"]
        ],
        steps=[InstructionStep(**step) for step in row["steps"]],
        status=RecipeStatus(row["status"]),
        version=row["version"],
        hide_reason=row["hide_reason"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        published_at=row["published_at"],
        photo_key=row["photo_key"],
    )


class PostgreSQLRecipeRepository(IRecipeReader, IRecipeWriter):
    def __init__(self, connection: Connection):
        self.connection = connection

    def find_by_id(self, recipe_id: int, *, for_share: bool = False) -> Recipe | None:
        query = RECIPE_SELECT + " WHERE r.id = %s"
        if for_share:
            self._require_transaction()
            query += " FOR SHARE OF r"
        row = self.connection.execute(query, (recipe_id,)).fetchone()
        return recipe_from_row(row) if row else None

    def find(self, criteria: RecipeQuery) -> list[Recipe]:
        conditions = []
        values = []
        if criteria.scope == "public":
            conditions.append("r.status = 'PUBLISHED'")
        elif criteria.scope == "author" and criteria.author_id is not None:
            conditions.append("r.author_id = %s")
            values.append(criteria.author_id)
        elif criteria.scope == "moderation":
            if criteria.author_id is not None:
                conditions.append("r.author_id = %s")
                values.append(criteria.author_id)
        else:
            raise ValueError("Unsupported recipe scope or missing author")
        if criteria.status is not None:
            conditions.append("r.status = %s")
            values.append(criteria.status)
        if criteria.title_substring is not None:
            # PostgreSQL 17's Unicode collation also works when Windows initdb used locale C.
            conditions.append("r.title COLLATE pg_catalog.pg_c_utf8 ILIKE %s")
            values.append("%" + escape_like(criteria.title_substring) + "%")
        if criteria.ingredient_substring is not None:
            conditions.append("""EXISTS (
                SELECT 1 FROM recipe_ingredients filter_ri
                JOIN ingredients filter_i ON filter_i.id = filter_ri.ingredient_id
                WHERE filter_ri.recipe_id = r.id
                  AND filter_i.name COLLATE pg_catalog.pg_c_utf8 ILIKE %s
            )""")
            values.append("%" + escape_like(criteria.ingredient_substring) + "%")
        if criteria.category_id is not None:
            conditions.append("r.category_id = %s")
            values.append(criteria.category_id)
        if criteria.tag_id is not None:
            conditions.append("""EXISTS (
                SELECT 1 FROM recipe_tags filter_rt
                WHERE filter_rt.recipe_id = r.id AND filter_rt.tag_id = %s
            )""")
            values.append(criteria.tag_id)
        if criteria.max_cooking_time is not None:
            conditions.append("r.cooking_time <= %s")
            values.append(criteria.max_cooking_time)
        if criteria.sort not in SORT_ORDERS:
            raise ValueError("Unsupported recipe sort")
        if criteria.offset < 0 or criteria.limit < 1:
            raise ValueError("Invalid recipe pagination")
        where = " WHERE " + " AND ".join(conditions) if conditions else ""
        values.extend([criteria.limit, criteria.offset])
        rows = self.connection.execute(
            RECIPE_SELECT
            + where
            + " ORDER BY "
            + SORT_ORDERS[criteria.sort]
            + " LIMIT %s OFFSET %s",
            values,
        ).fetchall()
        return [recipe_from_row(row) for row in rows]

    def _require_transaction(self) -> None:
        if self.connection.info.transaction_status != TransactionStatus.INTRANS:
            raise RuntimeError("Recipe writes require the service transaction")

    def save(self, recipe: Recipe, expected_version: int | None) -> None:
        self._require_transaction()
        values = (
            recipe.title,
            recipe.description,
            recipe.cooking_time,
            recipe.servings,
            recipe.category_id,
            recipe.status,
            recipe.hide_reason,
            recipe.published_at,
            recipe.photo_key,
        )
        if recipe.id is None and expected_version is None:
            row = self.connection.execute(
                """INSERT INTO recipes (
                    title, description, cooking_time, servings, category_id, status,
                    hide_reason, published_at, photo_key, author_id
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id, version, created_at, updated_at, published_at""",
                (*values, recipe.author_id),
            ).fetchone()
        elif recipe.id is not None and expected_version is not None:
            row = self.connection.execute(
                """UPDATE recipes SET title = %s, description = %s, cooking_time = %s,
                    servings = %s, category_id = %s, status = %s, hide_reason = %s,
                    published_at = %s, photo_key = %s,
                    updated_at = CURRENT_TIMESTAMP, version = version + 1
                WHERE id = %s AND version = %s
                RETURNING id, version, created_at, updated_at, published_at""",
                (*values, recipe.id, expected_version),
            ).fetchone()
            if row is None:
                raise VersionConflict()
        else:
            raise ValueError(
                "A new recipe has no expected version; an existing recipe requires one"
            )
        recipe.id = row["id"]
        recipe.version = row["version"]
        recipe.created_at = row["created_at"]
        recipe.updated_at = row["updated_at"]
        recipe.published_at = row["published_at"]
        self.connection.execute("DELETE FROM recipe_ingredients WHERE recipe_id = %s", (recipe.id,))
        self.connection.execute("DELETE FROM instruction_steps WHERE recipe_id = %s", (recipe.id,))
        self.connection.execute("DELETE FROM recipe_tags WHERE recipe_id = %s", (recipe.id,))
        with self.connection.cursor() as cursor:
            cursor.executemany(
                """INSERT INTO recipe_ingredients
                   (recipe_id, position, ingredient_id, quantity, unit)
                   VALUES (%s, %s, %s, %s, %s)""",
                [
                    (recipe.id, item.position, item.ingredient_id, item.quantity, item.unit)
                    for item in recipe.ingredients
                ],
            )
            cursor.executemany(
                "INSERT INTO instruction_steps (recipe_id, number, description) "
                "VALUES (%s, %s, %s)",
                [(recipe.id, step.number, step.description) for step in recipe.steps],
            )
            cursor.executemany(
                "INSERT INTO recipe_tags (recipe_id, tag_id) VALUES (%s, %s)",
                [(recipe.id, tag_id) for tag_id in recipe.tag_ids],
            )

    def delete(self, recipe_id: int, expected_version: int) -> None:
        self._require_transaction()
        row = self.connection.execute(
            "DELETE FROM recipes WHERE id = %s AND version = %s RETURNING id",
            (recipe_id, expected_version),
        ).fetchone()
        if not row:
            raise VersionConflict()
