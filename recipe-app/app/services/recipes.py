import logging
from collections.abc import Callable
from contextlib import AbstractContextManager

from app.domain.contracts import ICatalogRepository, IPhotoStorage, IRecipeReader, IRecipeWriter
from app.domain.criteria import RecipeQuery
from app.domain.enums import RecipeStatus, UserRole
from app.domain.exceptions import AccessDenied, PhotoNotFound, RecipeNotFound, VersionConflict
from app.domain.models import User
from app.domain.recipes import Recipe, RecipeDetails

logger = logging.getLogger(__name__)


class RecipeService:
    def __init__(
        self,
        reader: IRecipeReader,
        writer: IRecipeWriter,
        catalog: ICatalogRepository,
        transaction: Callable[[], AbstractContextManager],
        photos: IPhotoStorage | None = None,
    ):
        self.reader = reader
        self.writer = writer
        self.catalog = catalog
        self.transaction = transaction
        self.photos = photos

    def get_visible(self, recipe_id: int, actor: User | None) -> Recipe:
        recipe = self.reader.find_by_id(recipe_id)
        if not recipe:
            raise RecipeNotFound()
        if recipe.status == RecipeStatus.PUBLISHED:
            return recipe
        if actor and (actor.id == recipe.author_id or actor.has_role(UserRole.ADMIN)):
            return recipe
        raise RecipeNotFound()

    def _owned(self, recipe_id: int, actor: User, version: int) -> Recipe:
        recipe = self.get_visible(recipe_id, actor)
        if recipe.author_id != actor.id:
            raise AccessDenied()
        if recipe.version != version:
            raise VersionConflict()
        return recipe

    def list_owned(
        self, actor: User, status: RecipeStatus | None, page: int, page_size: int
    ) -> list[Recipe]:
        return self.reader.find(
            RecipeQuery(
                scope="author",
                author_id=actor.id,
                status=status,
                offset=(page - 1) * page_size,
                limit=page_size + 1,
            )
        )

    def create(self, actor: User, details: RecipeDetails) -> Recipe:
        with self.transaction():
            details.validate()
            self.catalog.validate_references(details)
            recipe = Recipe.create(actor.id, details)
            self.writer.save(recipe, None)
            return self.reader.find_by_id(recipe.id)

    def update(self, recipe_id: int, actor: User, details: RecipeDetails, version: int) -> Recipe:
        with self.transaction():
            recipe = self._owned(recipe_id, actor, version)
            details.validate()
            self.catalog.validate_references(details)
            recipe.update_details(details)
            self.writer.save(recipe, version)
            return self.reader.find_by_id(recipe.id)

    def publish(self, recipe_id: int, actor: User, version: int) -> Recipe:
        with self.transaction():
            recipe = self._owned(recipe_id, actor, version)
            recipe.publish()
            self.writer.save(recipe, version)
            return self.reader.find_by_id(recipe.id)

    def unpublish(self, recipe_id: int, actor: User, version: int) -> Recipe:
        with self.transaction():
            recipe = self._owned(recipe_id, actor, version)
            recipe.unpublish()
            self.writer.save(recipe, version)
            return self.reader.find_by_id(recipe.id)

    def delete(self, recipe_id: int, actor: User, version: int) -> None:
        with self.transaction():
            recipe = self._owned(recipe_id, actor, version)
            self.writer.delete(recipe_id, version)
        self._remove_photo(recipe.photo_key)

    def _remove_photo(self, key: str | None) -> None:
        if key and self.photos:
            try:
                self.photos.delete(key)
            except OSError:
                # The database already committed; leave an orphan for manual cleanup.
                logger.warning("Photo cleanup deferred")

    def read_photo(self, recipe_id: int, actor: User | None, *, thumbnail: bool = False) -> bytes:
        recipe = self.get_visible(recipe_id, actor)
        if not recipe.photo_key or not self.photos:
            raise PhotoNotFound()
        return self.photos.read(recipe.photo_key, thumbnail=thumbnail)

    def replace_photo(self, recipe_id: int, actor: User, version: int, content: bytes) -> Recipe:
        if self.photos is None:
            raise RuntimeError("Photo storage is not configured")
        # Check ownership before expensive image processing; CAS checks again before commit.
        self._owned(recipe_id, actor, version)
        key = self.photos.store(content)
        try:
            with self.transaction():
                recipe = self._owned(recipe_id, actor, version)
                previous = recipe.photo_key
                recipe.change_photo(key)
                self.writer.save(recipe, version)
                result = self.reader.find_by_id(recipe.id)
        except BaseException:
            self._remove_photo(key)
            raise
        self._remove_photo(previous)
        return result

    def delete_photo(self, recipe_id: int, actor: User, version: int) -> Recipe:
        with self.transaction():
            recipe = self._owned(recipe_id, actor, version)
            key = recipe.photo_key
            if key:
                recipe.change_photo(None)
                self.writer.save(recipe, version)
            result = self.reader.find_by_id(recipe.id)
        self._remove_photo(key)
        return result
