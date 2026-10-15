from psycopg import Connection
from psycopg.errors import UniqueViolation
from psycopg.pq import TransactionStatus

from app.domain.contracts import IUserRepository
from app.domain.enums import UserRole
from app.domain.exceptions import EmailAlreadyExists
from app.domain.models import User, UserCredentials
from app.infrastructure.sql_patterns import escape_like


def user_from_row(row: dict) -> User:
    return User(
        id=row["id"],
        email=row["email"],
        display_name=row["display_name"],
        role=UserRole(row["role"]),
        is_active=row["is_active"],
    )


class SqlUserRepository(IUserRepository):
    def __init__(self, connection: Connection):
        self.connection = connection

    def _require_transaction(self) -> None:
        if self.connection.info.transaction_status != TransactionStatus.INTRANS:
            raise RuntimeError("User writes and locks require the service transaction")

    def find_by_id(self, user_id: int, *, for_update: bool = False) -> User | None:
        query = "SELECT id, email, display_name, role, is_active FROM users WHERE id = %s"
        if for_update:
            self._require_transaction()
            query += " FOR UPDATE"
        row = self.connection.execute(query, (user_id,)).fetchone()
        return user_from_row(row) if row else None

    def find(self, q: str, offset: int, limit: int) -> list[User]:
        pattern = "%" + escape_like(q) + "%"
        rows = self.connection.execute(
            "SELECT id, email, display_name, role, is_active FROM users "
            "WHERE email COLLATE pg_catalog.pg_c_utf8 ILIKE %s "
            "OR display_name COLLATE pg_catalog.pg_c_utf8 ILIKE %s "
            "ORDER BY id LIMIT %s OFFSET %s",
            (pattern, pattern, limit, offset),
        ).fetchall()
        return [user_from_row(row) for row in rows]

    def set_active(self, user_id: int, is_active: bool) -> User:
        self._require_transaction()
        row = self.connection.execute(
            "UPDATE users SET is_active = %s WHERE id = %s "
            "RETURNING id, email, display_name, role, is_active",
            (is_active, user_id),
        ).fetchone()
        return user_from_row(row)

    def find_by_email(self, email: str, *, for_update: bool = False) -> UserCredentials | None:
        query = "SELECT * FROM users WHERE email = %s"
        if for_update:
            self._require_transaction()
            query += " FOR UPDATE"
        row = self.connection.execute(query, (email,)).fetchone()
        if not row:
            return None
        return UserCredentials(user_from_row(row), row["password_hash"])

    def create(self, email: str, display_name: str, password_hash: str) -> User:
        try:
            row = self.connection.execute(
                """INSERT INTO users (email, display_name, password_hash)
                   VALUES (%s, %s, %s) RETURNING *""",
                (email, display_name, password_hash),
            ).fetchone()
        except UniqueViolation as error:
            if error.diag.constraint_name == "users_email_key":
                raise EmailAlreadyExists() from error
            raise
        return user_from_row(row)
