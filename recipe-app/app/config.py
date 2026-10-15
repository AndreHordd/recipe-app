from pathlib import Path
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

APP_ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=APP_ROOT / ".env", extra="ignore")

    database_url: SecretStr
    app_origin: str = "http://localhost:8000"
    cookie_secure: bool = False
    session_days: int = Field(default=7, ge=1, le=30)
    database_timeout: int = Field(default=5, ge=1, le=30)
    uploads_dir: Path = APP_ROOT / "uploads"
    seed_admin_password: SecretStr = SecretStr("")
    seed_user_password: SecretStr = SecretStr("")

    @property
    def allowed_origins(self) -> frozenset[str]:
        origins = {self.app_origin}
        origin = urlsplit(self.app_origin)
        if origin.scheme == "http" and origin.hostname in {"localhost", "127.0.0.1"}:
            # Both addresses reach the local development server on the same port.
            port = origin.port or 80
            suffix = f":{port}" if port != 80 else ""
            origins.update(f"http://{host}{suffix}" for host in ("localhost", "127.0.0.1"))
        return frozenset(origins)

    @model_validator(mode="after")
    def validate_origin(self) -> "Settings":
        origin = urlsplit(self.app_origin)
        if (
            origin.scheme not in {"http", "https"}
            or not origin.hostname
            or origin.path not in {"", "/"}
            or origin.query
            or origin.fragment
            or origin.username
            or origin.password
        ):
            raise ValueError("APP_ORIGIN must be an HTTP(S) origin without a path")
        self.app_origin = self.app_origin.rstrip("/")
        if origin.scheme == "https" and not self.cookie_secure:
            raise ValueError("HTTPS requires COOKIE_SECURE=true")
        return self
