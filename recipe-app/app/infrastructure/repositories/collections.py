from psycopg import Connection
from psycopg.pq import TransactionStatus

from app.domain.collections import Collection, CollectionEntry
from app.domain.contracts import ICollectionRepository
from app.infrastructure.repositories.recipes import RECIPE_FIELDS, RECIPE_JOINS, recipe_from_row


class PostgreSQLCollectionRepository(ICollectionRepository):
    def __init__(self, connection: Connection):
        self.connection = connection

    def _require_transaction(self) -> None:
        if self.connection.info.transaction_status != TransactionStatus.INTRANS:
            raise RuntimeError("Collection writes and locks require the service transaction")

    def find_by_id(self, collection_id: int, *, for_update: bool = False) -> Collection | None:
        query = "SELECT * FROM collections WHERE id = %s"
        if for_update:
            self._require_transaction()
            query += " FOR UPDATE"
        row = self.connection.execute(query, (collection_id,)).fetchone()
        return Collection(**row) if row else None

    def list_owned(self, owner_id: int, offset: int, limit: int) -> list[Collection]:
        rows = self.connection.execute(
            "SELECT * FROM collections WHERE owner_id = %s "
            "ORDER BY created_at DESC, id DESC LIMIT %s OFFSET %s",
            (owner_id, limit, offset),
        ).fetchall()
        return [Collection(**row) for row in rows]

    def create(self, collection: Collection) -> None:
        self._require_transaction()
        row = self.connection.execute(
            "INSERT INTO collections (owner_id, name) VALUES (%s, %s) "
            "RETURNING id, created_at, updated_at",
            (collection.owner_id, collection.name),
        ).fetchone()
        collection.id = row["id"]
        collection.created_at = row["created_at"]
        collection.updated_at = row["updated_at"]

    def rename(self, collection: Collection) -> None:
        self._require_transaction()
        row = self.connection.execute(
            "UPDATE collections SET name = %s, updated_at = CURRENT_TIMESTAMP "
            "WHERE id = %s RETURNING updated_at",
            (collection.name, collection.id),
        ).fetchone()
        collection.updated_at = row["updated_at"]

    def delete(self, collection_id: int) -> None:
        self._require_transaction()
        self.connection.execute("DELETE FROM collections WHERE id = %s", (collection_id,))

    def list_entries(self, collection_id: int, offset: int, limit: int) -> list[CollectionEntry]:
        # Only trusted SQL fragments are composed; all request values remain parameters.
        rows = self.connection.execute(
            "SELECT ce.collection_id, ce.recipe_id, ce.saved_at, "
            + RECIPE_FIELDS
            + " FROM collection_entries ce JOIN recipes r ON r.id = ce.recipe_id "
            + RECIPE_JOINS
            + " WHERE ce.collection_id = %s ORDER BY ce.saved_at DESC, ce.recipe_id DESC "
            "LIMIT %s OFFSET %s",
            (collection_id, limit, offset),
        ).fetchall()
        return [
            CollectionEntry(
                row["collection_id"], row["recipe_id"], row["saved_at"], recipe_from_row(row)
            )
            for row in rows
        ]

    def _touch(self, collection_id: int) -> None:
        self.connection.execute(
            "UPDATE collections SET updated_at = CURRENT_TIMESTAMP WHERE id = %s", (collection_id,)
        )

    def add_entry(self, collection_id: int, recipe_id: int) -> None:
        self._require_transaction()
        row = self.connection.execute(
            "INSERT INTO collection_entries (collection_id, recipe_id) VALUES (%s, %s) "
            "ON CONFLICT DO NOTHING RETURNING recipe_id",
            (collection_id, recipe_id),
        ).fetchone()
        if row:
            self._touch(collection_id)

    def remove_entry(self, collection_id: int, recipe_id: int) -> None:
        self._require_transaction()
        row = self.connection.execute(
            "DELETE FROM collection_entries WHERE collection_id = %s AND recipe_id = %s "
            "RETURNING recipe_id",
            (collection_id, recipe_id),
        ).fetchone()
        if row:
            self._touch(collection_id)
