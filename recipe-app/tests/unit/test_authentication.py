from contextlib import nullcontext
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from app.domain.contracts import IPasswordHasher, ISessionRepository, IUserRepository
from app.domain.enums import UserRole
from app.domain.exceptions import InactiveUser, InvalidCredentials
from app.domain.models import Session, User, UserCredentials
from app.services.authentication import AuthenticationService, hash_token


class FakeUsers(IUserRepository):
    def __init__(self, user: User | None):
        self.user = user

    def find_by_id(self, user_id, *, for_update=False):
        return self.user if self.user and self.user.id == user_id else None

    def find(self, q, offset, limit):
        users = [self.user] if self.user and q in self.user.email else []
        return users[offset : offset + limit]

    def set_active(self, user_id, is_active):
        self.user = replace(self.user, is_active=is_active)
        return self.user

    def find_by_email(self, email, *, for_update=False):
        if self.user and self.user.email == email:
            return UserCredentials(self.user, "hashed:password-123")
        return None

    def create(self, email, display_name, password_hash):
        self.saved_hash = password_hash
        self.user = User(1, email, display_name, UserRole.USER, True)
        return self.user


class FakeSessions(ISessionRepository):
    def __init__(self):
        self.items = {}

    def delete_for_user(self, user_id):
        self.items = {key: value for key, value in self.items.items() if value.user.id != user_id}

    def find_live(self, token_hash):
        session = self.items.get(token_hash)
        return session if session and session.expires_at > datetime.now(UTC) else None

    def create(self, token_hash, user, csrf_token, expires_at):
        session = Session(token_hash, user, csrf_token, expires_at)
        self.items[token_hash] = session
        return session

    def delete(self, token_hash):
        self.items.pop(token_hash, None)

    def delete_expired(self):
        self.items = {key: value for key, value in self.items.items() if self.find_live(key)}


class FakePasswords(IPasswordHasher):
    def hash(self, password):
        return "hashed:" + password

    def verify(self, password, password_hash):
        self.last_hash = password_hash
        return password_hash == self.hash(password)


@pytest.fixture
def service():
    return AuthenticationService(
        FakeUsers(User(1, "user@example.com", "Ім’я", UserRole.USER, True)),
        FakeSessions(),
        FakePasswords(),
        nullcontext,
        7,
    )


def test_registration_hashes_password_and_assigns_user_role(service):
    user = service.register("new@example.com", "Новий", "password-123")
    assert user.role == UserRole.USER
    assert service.users.saved_hash == "hashed:password-123"


def test_login_rotates_browser_session_but_preserves_other_browsers(service):
    first = service.login("user@example.com", "password-123", None)
    other_browser = service.login("user@example.com", "password-123", None)
    second = service.login("user@example.com", "password-123", first.token)
    assert first.token != second.token
    assert service.get_current_session(first.token) is None
    assert service.get_current_session(second.token) == second.session
    assert service.get_current_session(other_browser.token) == other_browser.session
    assert second.token not in service.sessions.items
    assert second.session.token_hash == hash_token(second.token)


@pytest.mark.parametrize(
    "email,password",
    [
        ("unknown@example.com", "password-123"),
        ("user@example.com", "wrong-password"),
    ],
)
def test_failed_login_creates_no_session(service, email, password):
    with pytest.raises(InvalidCredentials):
        service.login(email, password, None)
    assert service.sessions.items == {}


def test_unknown_email_still_calls_password_verifier(service):
    with pytest.raises(InvalidCredentials):
        service.login("unknown@example.com", "password-123", None)
    assert service.passwords.last_hash is None


def test_blocked_account_cannot_login(service):
    service.users.user = User(1, "user@example.com", "Ім’я", UserRole.USER, False)
    with pytest.raises(InactiveUser):
        service.login("user@example.com", "password-123", None)
    assert not service.sessions.items


def test_expired_session_is_anonymous(service):
    result = service.login("user@example.com", "password-123", None)
    service.sessions.items[result.session.token_hash] = Session(
        result.session.token_hash,
        result.session.user,
        result.session.csrf_token,
        datetime.now(UTC) - timedelta(seconds=1),
    )
    assert service.get_current_session(result.token) is None


def test_session_with_inactive_user_is_anonymous(service):
    result = service.login("user@example.com", "password-123", None)
    blocked = User(1, "user@example.com", "Ім’я", UserRole.USER, False)
    service.sessions.items[result.session.token_hash] = Session(
        result.session.token_hash,
        blocked,
        result.session.csrf_token,
        result.session.expires_at,
    )
    assert service.get_current_session(result.token) is None


def test_logout_revokes_session(service):
    result = service.login("user@example.com", "password-123", None)
    service.logout(result.session)
    assert service.get_current_session(result.token) is None
