from psycopg import Connection, sql
from psycopg.errors import ForeignKeyViolation, UniqueViolation
from psycopg.pq import TransactionStatus

from app.domain.contracts import ICatalogRepository
from app.domain.exceptions import (
    CatalogItemInUse,
    CatalogItemNotFound,
    CatalogNameExists,
    InvalidReference,
)
from app.domain.recipes import CatalogItem, RecipeDetails
from app.infrastructure.sql_patterns import escape_like


class PostgreSQLCatalogRepository(ICatalogRepository):
    TABLES = {"category": "categories", "tag": "tags"}

    def __init__(self, connection: Connection):
        self.connection = connection

    def _require_transaction(self) -> None:
        if self.connection.info.transaction_status != TransactionStatus.INTRANS:
            raise RuntimeError("Catalog writes require the service transaction")

    def create_item(self, kind: str, name: str, normalized_name: str) -> CatalogItem:
        self._require_transaction()
        table = self.TABLES[kind]
        try:
            row = self.connection.execute(
                sql.SQL(
                    "INSERT INTO {} (name, normalized_name) VALUES (%s, %s) RETURNING id, name"
                ).format(sql.Identifier(table)),
                (name, normalized_name),
            ).fetchone()
        except UniqueViolation as error:
            if error.diag.constraint_name == f"{table}_normalized_name_key":
                raise CatalogNameExists() from error
            raise
        return CatalogItem(**row)

    def rename_item(self, kind: str, item_id: int, name: str, normalized_name: str) -> CatalogItem:
        self._require_transaction()
        table = self.TABLES[kind]
        try:
            row = self.connection.execute(
                sql.SQL(
                    "UPDATE {} SET name = %s, normalized_name = %s WHERE id = %s RETURNING id, name"
                ).format(sql.Identifier(table)),
                (name, normalized_name, item_id),
            ).fetchone()
        except UniqueViolation as error:
            if error.diag.constraint_name == f"{table}_normalized_name_key":
                raise CatalogNameExists() from error
            raise
        if row is None:
            raise CatalogItemNotFound()
        return CatalogItem(**row)

    def delete_item(self, kind: str, item_id: int) -> None:
        self._require_transaction()
        table = self.TABLES[kind]
        try:
            row = self.connection.execute(
                sql.SQL("DELETE FROM {} WHERE id = %s RETURNING id").format(sql.Identifier(table)),
                (item_id,),
            ).fetchone()
        except ForeignKeyViolation as error:
            constraint = (
                "recipes_category_id_fkey" if kind == "category" else "recipe_tags_tag_id_fkey"
            )
            if error.diag.constraint_name == constraint:
                raise CatalogItemInUse() from error
            raise
        if row is None:
            raise CatalogItemNotFound()

    def list_categories(self) -> list[CatalogItem]:
        rows = self.connection.execute(
            "SELECT id, name FROM categories ORDER BY normalized_name, id"
        ).fetchall()
        return [CatalogItem(**row) for row in rows]

    def list_tags(self) -> list[CatalogItem]:
        rows = self.connection.execute(
            "SELECT id, name FROM tags ORDER BY normalized_name, id"
        ).fetchall()
        return [CatalogItem(**row) for row in rows]

    def find_ingredients(self, q: str, offset: int, limit: int) -> list[CatalogItem]:
        rows = self.connection.execute(
            "SELECT id, name FROM ingredients WHERE normalized_name LIKE %s "
            "ORDER BY normalized_name, id LIMIT %s OFFSET %s",
            ("%" + escape_like(q) + "%", limit, offset),
        ).fetchall()
        return [CatalogItem(**row) for row in rows]

    def create_ingredient(self, name: str, normalized_name: str) -> tuple[CatalogItem, bool]:
        row = self.connection.execute(
            """INSERT INTO ingredients (name, normalized_name) VALUES (%s, %s)
               ON CONFLICT (normalized_name) DO NOTHING RETURNING id, name""",
            (name, normalized_name),
        ).fetchone()
        created = row is not None
        if row is None:
            row = self.connection.execute(
                "SELECT id, name FROM ingredients WHERE normalized_name = %s", (normalized_name,)
            ).fetchone()
        return CatalogItem(**row), created

    def validate_references(self, details: RecipeDetails) -> None:
        references = {
            "categories": [details.category_id] if details.category_id is not None else [],
            "tags": details.tag_ids,
            "ingredients": [item.ingredient_id for item in details.ingredients],
        }
        for table, ids in references.items():
            if not ids:
                continue
            rows = self.connection.execute(
                sql.SQL("SELECT id FROM {} WHERE id = ANY(%s) ORDER BY id FOR KEY SHARE").format(
                    sql.Identifier(table)
                ),
                (ids,),
            ).fetchall()
            if {row["id"] for row in rows} != set(ids):
                raise InvalidReference()
