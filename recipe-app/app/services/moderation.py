from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Literal

from app.domain.contracts import (
    ICatalogRepository,
    IRecipeReader,
    IRecipeWriter,
    ISessionRepository,
    IUserRepository,
)
from app.domain.criteria import RecipeQuery
from app.domain.enums import RecipeStatus, UserRole
from app.domain.exceptions import (
    AccessDenied,
    ApplicationError,
    RecipeNotFound,
    UserNotFound,
    VersionConflict,
)
from app.domain.models import User
from app.domain.recipes import CatalogItem, Recipe
from app.services.catalog import normalize_catalog_name


class ModerationService:
    def __init__(
        self,
        reader: IRecipeReader,
        writer: IRecipeWriter,
        users: IUserRepository,
        sessions: ISessionRepository,
        catalog: ICatalogRepository,
        transaction: Callable[[], AbstractContextManager],
    ):
        self.reader, self.writer = reader, writer
        self.users, self.sessions, self.catalog = users, sessions, catalog
        self.transaction = transaction

    def _admin(self, actor: User) -> None:
        if not actor.has_role(UserRole.ADMIN):
            raise AccessDenied()

    def _offset(self, page: int, page_size: int) -> int:
        offset = (page - 1) * page_size
        if page < 1 or not 1 <= page_size <= 50 or offset > 2**63 - 1:
            raise ApplicationError("INVALID_PAGE", "Перевірте номер і розмір сторінки.", 422)
        return offset

    def list_recipes(
        self,
        actor: User,
        status: RecipeStatus | None,
        author_id: int | None,
        q: str,
        page: int,
        page_size: int,
    ) -> list[Recipe]:
        self._admin(actor)
        return self.reader.find(
            RecipeQuery(
                scope="moderation",
                status=status,
                author_id=author_id,
                title_substring=q.strip() or None,
                offset=self._offset(page, page_size),
                limit=page_size + 1,
            )
        )

    def _recipe(self, recipe_id: int, version: int) -> Recipe:
        recipe = self.reader.find_by_id(recipe_id)
        if recipe is None:
            raise RecipeNotFound()
        if recipe.version != version:
            raise VersionConflict()
        return recipe

    def hide(self, actor: User, recipe_id: int, version: int, reason: str) -> Recipe:
        self._admin(actor)
        with self.transaction():
            recipe = self._recipe(recipe_id, version)
            recipe.hide(reason)
            self.writer.save(recipe, version)
            return self.reader.find_by_id(recipe_id)

    def restore(self, actor: User, recipe_id: int, version: int) -> Recipe:
        self._admin(actor)
        with self.transaction():
            recipe = self._recipe(recipe_id, version)
            recipe.restore_to_draft()
            self.writer.save(recipe, version)
            return self.reader.find_by_id(recipe_id)

    def list_users(self, actor: User, q: str, page: int, page_size: int) -> list[User]:
        self._admin(actor)
        return self.users.find(q.strip(), self._offset(page, page_size), page_size + 1)

    def set_active(self, actor: User, user_id: int, is_active: bool) -> User:
        self._admin(actor)
        with self.transaction():
            user = self.users.find_by_id(user_id, for_update=True)
            if user is None:
                raise UserNotFound()
            if not is_active and (user.id == actor.id or user.has_role(UserRole.ADMIN)):
                raise AccessDenied()
            result = self.users.set_active(user_id, is_active)
            if not is_active:
                self.sessions.delete_for_user(user_id)
            return result

    def create_catalog_item(
        self, actor: User, kind: Literal["category", "tag"], name: str
    ) -> CatalogItem:
        self._admin(actor)
        display, normalized = normalize_catalog_name(name)
        with self.transaction():
            return self.catalog.create_item(kind, display, normalized)

    def rename_catalog_item(
        self, actor: User, kind: Literal["category", "tag"], item_id: int, name: str
    ) -> CatalogItem:
        self._admin(actor)
        display, normalized = normalize_catalog_name(name)
        with self.transaction():
            return self.catalog.rename_item(kind, item_id, display, normalized)

    def delete_catalog_item(
        self, actor: User, kind: Literal["category", "tag"], item_id: int
    ) -> None:
        self._admin(actor)
        with self.transaction():
            self.catalog.delete_item(kind, item_id)
