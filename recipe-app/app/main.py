import logging
from typing import Annotated

import psycopg
from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException

from app.api import admin, auth, catalog, collections, recipes
from app.config import APP_ROOT, Settings
from app.dependencies import get_connection
from app.domain.exceptions import ApplicationError
from app.infrastructure.photos import LocalPhotoStorage
from app.infrastructure.security import Argon2PasswordHasher
from app.web import routes

logger = logging.getLogger(__name__)


def error_response(code: str, message: str, status: int, fields: list | None = None):
    return JSONResponse(
        {"error": {"code": code, "message": message, "fields": fields or []}},
        status_code=status,
        headers={"Cache-Control": "no-store"},
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    application = FastAPI(title="Кулінарні рецепти", version="0.6.1")
    application.state.settings = settings or Settings()
    application.state.passwords = Argon2PasswordHasher()
    application.state.photos = LocalPhotoStorage(application.state.settings.uploads_dir)

    @application.middleware("http")
    async def request_security(request: Request, call_next):
        if request.url.path.startswith("/api/") and request.method in {
            "POST",
            "PUT",
            "PATCH",
            "DELETE",
        }:
            if request.headers.get("origin") not in application.state.settings.allowed_origins:
                return error_response("ORIGIN_INVALID", "Запит надійшов із невідомого сайту.", 403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        if request.url.path.startswith(
            ("/api/auth/", "/api/recipes", "/api/collections", "/api/admin")
        ):
            response.headers["Cache-Control"] = "no-store"
        return response

    @application.exception_handler(ApplicationError)
    async def application_error(request: Request, error: ApplicationError):
        return error_response(error.code, error.message, error.status_code)

    @application.exception_handler(RequestValidationError)
    async def validation_error(request: Request, error: RequestValidationError):
        fields = [
            {
                "field": ".".join(str(part) for part in item["loc"][1:]),
                "message": "Некоректне значення.",
            }
            for item in error.errors()
        ]
        return error_response("VALIDATION_ERROR", "Перевірте заповнені поля.", 422, fields)

    @application.exception_handler(psycopg.OperationalError)
    async def database_unavailable(request: Request, error: psycopg.OperationalError):
        logger.warning("Database connection unavailable")
        return error_response("DATABASE_UNAVAILABLE", "База даних тимчасово недоступна.", 503)

    @application.exception_handler(psycopg.errors.DeadlockDetected)
    @application.exception_handler(psycopg.errors.SerializationFailure)
    async def retry_operation(request: Request, error: psycopg.Error):
        return error_response("RETRY_OPERATION", "Повторіть дію: дані змінюються одночасно.", 409)

    @application.exception_handler(HTTPException)
    async def http_error(request: Request, error: HTTPException):
        return error_response("HTTP_ERROR", "Сторінку або дію не знайдено.", error.status_code)

    @application.exception_handler(Exception)
    async def unexpected_error(request: Request, error: Exception):
        # Do not log request bodies, credentials, SQL parameters or database DSNs.
        logger.error("Unhandled application error: %s", type(error).__name__)
        return error_response("INTERNAL_ERROR", "Сталася помилка. Спробуйте пізніше.", 500)

    @application.get("/api/health", tags=["Стан застосунку"])
    def health(connection: Annotated[psycopg.Connection, Depends(get_connection)]):
        connection.execute("SELECT 1")
        return {"status": "ok"}

    application.include_router(auth.router)
    application.include_router(recipes.router)
    application.include_router(catalog.router)
    application.include_router(collections.router)
    application.include_router(admin.router)
    application.include_router(routes.router)
    application.mount(
        "/static", StaticFiles(directory=APP_ROOT / "app" / "web" / "static"), name="static"
    )
    return application
