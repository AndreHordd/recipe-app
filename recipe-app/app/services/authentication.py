import hashlib
import secrets
from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import UTC, datetime, timedelta

from app.domain.contracts import IPasswordHasher, ISessionRepository, IUserRepository
from app.domain.exceptions import AuthenticationRequired, InactiveUser, InvalidCredentials
from app.domain.models import LoginResult, Session, User


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class AuthenticationService:
    def __init__(
        self,
        users: IUserRepository,
        sessions: ISessionRepository,
        passwords: IPasswordHasher,
        transaction: Callable[[], AbstractContextManager],
        session_days: int,
    ):
        self.users = users
        self.sessions = sessions
        self.passwords = passwords
        self.transaction = transaction
        self.session_days = session_days

    def register(self, email: str, display_name: str, password: str) -> User:
        password_hash = self.passwords.hash(password)
        with self.transaction():
            return self.users.create(email, display_name, password_hash)

    def login(self, email: str, password: str, previous_token: str | None) -> LoginResult:
        with self.transaction():
            credentials = self.users.find_by_email(email, for_update=True)
            password_hash = credentials.password_hash if credentials else None
            # The adapter also verifies a dummy hash when the address does not exist.
            valid_password = self.passwords.verify(password, password_hash)
            if not credentials or not valid_password:
                raise InvalidCredentials()
            if not credentials.user.is_active:
                raise InactiveUser()
            if previous_token and len(previous_token) <= 128:
                self.sessions.delete(hash_token(previous_token))
            self.sessions.delete_expired()
            token = secrets.token_urlsafe(32)
            csrf_token = secrets.token_urlsafe(32)
            expires_at = datetime.now(UTC) + timedelta(days=self.session_days)
            session = self.sessions.create(
                hash_token(token), credentials.user, csrf_token, expires_at
            )
            return LoginResult(session=session, token=token)

    def get_current_session(self, token: str | None) -> Session | None:
        if not token or len(token) > 128:
            return None
        session = self.sessions.find_live(hash_token(token))
        if not session or not session.user.is_active:
            return None
        return session

    def require_session(self, token: str | None) -> Session:
        session = self.get_current_session(token)
        if not session:
            raise AuthenticationRequired()
        return session

    def logout(self, session: Session) -> None:
        with self.transaction():
            self.sessions.delete(session.token_hash)
