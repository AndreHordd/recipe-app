from dataclasses import dataclass
from datetime import datetime

from app.domain.enums import UserRole


@dataclass(frozen=True)
class User:
    id: int
    email: str
    display_name: str
    role: UserRole
    is_active: bool

    def has_role(self, role: UserRole) -> bool:
        return self.role == role


@dataclass(frozen=True)
class UserCredentials:
    user: User
    password_hash: str


@dataclass(frozen=True)
class Session:
    token_hash: str
    user: User
    csrf_token: str
    expires_at: datetime


@dataclass(frozen=True)
class LoginResult:
    session: Session
    token: str
