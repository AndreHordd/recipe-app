import secrets
from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Query, Request
from psycopg import Connection

from app.api.search_schemas import SearchParams
from app.config import Settings
from app.domain.criteria import SearchCriteria
from app.domain.enums import UserRole
from app.domain.exceptions import AccessDenied, ApplicationError, InvalidSearch
from app.domain.models import Session, User
from app.infrastructure.database import connect
from app.infrastructure.repositories.catalog import PostgreSQLCatalogRepository
from app.infrastructure.repositories.collections import PostgreSQLCollectionRepository
from app.infrastructure.repositories.recipes import PostgreSQLRecipeRepository
from app.infrastructure.repositories.sessions import SqlSessionRepository
from app.infrastructure.repositories.users import SqlUserRepository
from app.services.authentication import AuthenticationService
from app.services.catalog import CatalogService
from app.services.collections import CollectionService
from app.services.moderation import ModerationService
from app.services.recipes import RecipeService
from app.services.search import (
    BaseSearchStrategy,
    RecipeSearchService,
    SearchByCategoryStrategy,
    SearchByIngredientStrategy,
    SearchByTitleStrategy,
)

COOKIE_NAME = "recipe_session"


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_connection(settings: Annotated[Settings, Depends(get_settings)]) -> Iterator[Connection]:
    with connect(settings) as connection:
        yield connection


def get_authentication_service(
    request: Request,
    connection: Annotated[Connection, Depends(get_connection)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AuthenticationService:
    return AuthenticationService(
        SqlUserRepository(connection),
        SqlSessionRepository(connection),
        request.app.state.passwords,
        connection.transaction,
        settings.session_days,
    )


Authentication = Annotated[AuthenticationService, Depends(get_authentication_service)]


def optional_actor(request: Request, service: Authentication) -> User | None:
    session = service.get_current_session(request.cookies.get(COOKIE_NAME))
    return session.user if session else None


def require_session(request: Request, service: Authentication) -> Session:
    return service.require_session(request.cookies.get(COOKIE_NAME))


def require_actor(session: Annotated[Session, Depends(require_session)]) -> User:
    return session.user


def require_admin(user: Annotated[User, Depends(require_actor)]) -> User:
    if not user.has_role(UserRole.ADMIN):
        raise AccessDenied()
    return user


def require_json(request: Request) -> None:
    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type != "application/json":
        raise ApplicationError("JSON_REQUIRED", "Надішліть дані у форматі JSON.", 415)


def require_csrf(
    request: Request, session: Annotated[Session, Depends(require_session)]
) -> Session:
    token = request.headers.get("x-csrf-token", "")
    if (
        not token
        or len(token) > 128
        or not token.isascii()
        or not secrets.compare_digest(token, session.csrf_token)
    ):
        raise ApplicationError("CSRF_INVALID", "Оновіть сторінку й повторіть дію.", 403)
    return session


def get_recipe_service(
    request: Request, connection: Annotated[Connection, Depends(get_connection)]
) -> RecipeService:
    repository = PostgreSQLRecipeRepository(connection)
    return RecipeService(
        repository,
        repository,
        PostgreSQLCatalogRepository(connection),
        connection.transaction,
        request.app.state.photos,
    )


def get_catalog_service(
    connection: Annotated[Connection, Depends(get_connection)],
) -> CatalogService:
    return CatalogService(PostgreSQLCatalogRepository(connection), connection.transaction)


Recipes = Annotated[RecipeService, Depends(get_recipe_service)]
Catalog = Annotated[CatalogService, Depends(get_catalog_service)]

SEARCH_STRATEGIES: dict[str, type[BaseSearchStrategy]] = {
    "title": SearchByTitleStrategy,
    "ingredient": SearchByIngredientStrategy,
    "category": SearchByCategoryStrategy,
}


def get_search_criteria(params: Annotated[SearchParams, Query()]) -> SearchCriteria:
    return params.to_criteria()


Search = Annotated[SearchCriteria, Depends(get_search_criteria)]


def get_search_service(
    criteria: Search, connection: Annotated[Connection, Depends(get_connection)]
) -> RecipeSearchService:
    strategy_class = SEARCH_STRATEGIES.get(criteria.mode)
    if strategy_class is None:
        raise InvalidSearch("Невідомий спосіб пошуку.")
    return RecipeSearchService(strategy_class(PostgreSQLRecipeRepository(connection)))


RecipeSearch = Annotated[RecipeSearchService, Depends(get_search_service)]


def get_collection_service(
    connection: Annotated[Connection, Depends(get_connection)],
) -> CollectionService:
    return CollectionService(
        PostgreSQLCollectionRepository(connection),
        PostgreSQLRecipeRepository(connection),
        connection.transaction,
    )


Collections = Annotated[CollectionService, Depends(get_collection_service)]


def get_moderation_service(
    connection: Annotated[Connection, Depends(get_connection)],
) -> ModerationService:
    recipes = PostgreSQLRecipeRepository(connection)
    return ModerationService(
        recipes,
        recipes,
        SqlUserRepository(connection),
        SqlSessionRepository(connection),
        PostgreSQLCatalogRepository(connection),
        connection.transaction,
    )


Moderation = Annotated[ModerationService, Depends(get_moderation_service)]
