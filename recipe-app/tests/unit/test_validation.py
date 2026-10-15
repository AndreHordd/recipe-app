import pytest
from pydantic import ValidationError

from app.api.schemas import RegisterRequest
from app.config import Settings
from app.infrastructure.security import Argon2PasswordHasher


def test_normalization_preserves_password_whitespace():
    data = RegisterRequest(
        email=" USER@EXAMPLE.COM ", display_name="  Андрій  ", password=" password-123 "
    )
    assert data.email == "user@example.com"
    assert data.display_name == "Андрій"
    assert data.password == " password-123 "


@pytest.mark.parametrize(
    "change",
    [
        {"email": "bad"},
        {"display_name": " "},
        {"display_name": "a" * 81},
        {"password": "short"},
        {"password": "a" * 129},
        {"role": "ADMIN"},
        {"password": 12345678},
    ],
)
def test_invalid_registration_is_rejected(change):
    data = {"email": "user@example.com", "display_name": "Ім’я", "password": "password-123"}
    data.update(change)
    with pytest.raises(ValidationError):
        RegisterRequest.model_validate(data)


@pytest.mark.parametrize("origin", ["https://example.com/path", "null", "ftp://example.com"])
def test_origin_must_be_http_origin(origin):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, database_url="postgresql://localhost/unused", app_origin=origin)


def test_https_requires_secure_cookie():
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            database_url="postgresql://localhost/unused",
            app_origin="https://example.com",
            cookie_secure=False,
        )


def test_argon2_hash_and_unknown_address_verification():
    hasher = Argon2PasswordHasher()
    hashed = hasher.hash("password-123")
    assert hashed.startswith("$argon2id$")
    assert hasher.verify("password-123", hashed)
    assert not hasher.verify("wrong-password", hashed)
    assert not hasher.verify("password-123", None)
