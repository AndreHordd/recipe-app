from datetime import datetime

from psycopg import Connection
from psycopg.pq import TransactionStatus

from app.domain.contracts import ISessionRepository
from app.domain.models import Session, User
from app.infrastructure.repositories.users import user_from_row


class SqlSessionRepository(ISessionRepository):
    def __init__(self, connection: Connection):
        self.connection = connection

    def delete_for_user(self, user_id: int) -> None:
        if self.connection.info.transaction_status != TransactionStatus.INTRANS:
            raise RuntimeError("Revoking user sessions requires the service transaction")
        self.connection.execute("DELETE FROM user_sessions WHERE user_id = %s", (user_id,))

    def find_live(self, token_hash: str) -> Session | None:
        row = self.connection.execute(
            """SELECT u.*, s.token_hash, s.csrf_token, s.expires_at
               FROM user_sessions s JOIN users u ON u.id = s.user_id
               WHERE s.token_hash = %s AND s.expires_at > CURRENT_TIMESTAMP""",
            (token_hash,),
        ).fetchone()
        if not row:
            return None
        return Session(row["token_hash"], user_from_row(row), row["csrf_token"], row["expires_at"])

    def create(self, token_hash: str, user: User, csrf_token: str, expires_at: datetime) -> Session:
        self.connection.execute(
            """INSERT INTO user_sessions (token_hash, user_id, csrf_token, expires_at)
               VALUES (%s, %s, %s, %s)""",
            (token_hash, user.id, csrf_token, expires_at),
        )
        return Session(token_hash, user, csrf_token, expires_at)

    def delete(self, token_hash: str) -> None:
        self.connection.execute("DELETE FROM user_sessions WHERE token_hash = %s", (token_hash,))

    def delete_expired(self) -> None:
        self.connection.execute("DELETE FROM user_sessions WHERE expires_at <= CURRENT_TIMESTAMP")
