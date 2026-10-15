from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict, EmailStr, Field

from app.domain.enums import UserRole


def normalize_email(value: object) -> object:
    return value.strip().lower() if isinstance(value, str) else value


def strip_name(value: object) -> object:
    return value.strip() if isinstance(value, str) else value


def collapse_name(value: object) -> object:
    return " ".join(value.split()) if isinstance(value, str) else value


NormalizedEmail = Annotated[EmailStr, BeforeValidator(normalize_email), Field(max_length=254)]
Password = Annotated[str, Field(min_length=8, max_length=128, strict=True)]


class RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RegisterRequest(RequestModel):
    email: NormalizedEmail
    display_name: Annotated[
        str, BeforeValidator(strip_name), Field(min_length=1, max_length=80, strict=True)
    ]
    password: Password


class LoginRequest(RequestModel):
    # Keep the existing API field while allowing provisioned accounts with a short login.
    email: Annotated[
        str, BeforeValidator(normalize_email), Field(min_length=1, max_length=254, strict=True)
    ]
    password: Annotated[str, Field(min_length=1, max_length=128, strict=True)]


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    display_name: str
    role: UserRole
    is_active: bool


class SessionRead(BaseModel):
    user: UserRead
    csrf_token: str
