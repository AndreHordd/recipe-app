from collections.abc import Callable
from contextlib import AbstractContextManager

from app.domain.collections import Collection, CollectionEntry
from app.domain.contracts import ICollectionRepository, IRecipeReader
from app.domain.enums import RecipeStatus
from app.domain.exceptions import (
    CollectionNotFound,
    InvalidCollection,
    RecipeNotFound,
    RecipeNotPublished,
)
from app.domain.models import User


class CollectionService:
    def __init__(
        self,
        collections: ICollectionRepository,
        recipes: IRecipeReader,
        transaction: Callable[[], AbstractContextManager],
    ):
        self.collections = collections
        self.recipes = recipes
        self.transaction = transaction

    def _owned(self, collection_id: int, actor: User, *, for_update: bool = False) -> Collection:
        collection = self.collections.find_by_id(collection_id, for_update=for_update)
        if collection is None or collection.owner_id != actor.id:
            raise CollectionNotFound()
        return collection

    def _offset(self, page: int, page_size: int) -> int:
        offset = (page - 1) * page_size
        if page < 1 or not 1 <= page_size <= 50 or offset > 2**63 - 1:
            raise InvalidCollection("Перевірте номер і розмір сторінки.")
        return offset

    def get_owned(self, collection_id: int, actor: User) -> Collection:
        return self._owned(collection_id, actor)

    def list_owned(self, actor: User, page: int, page_size: int) -> list[Collection]:
        return self.collections.list_owned(actor.id, self._offset(page, page_size), page_size + 1)

    def create(self, actor: User, name: str) -> Collection:
        collection = Collection.create(actor.id, name)
        with self.transaction():
            self.collections.create(collection)
        return collection

    def rename(self, collection_id: int, actor: User, name: str) -> Collection:
        with self.transaction():
            collection = self._owned(collection_id, actor, for_update=True)
            collection.rename(name)
            self.collections.rename(collection)
        return collection

    def delete(self, collection_id: int, actor: User) -> None:
        with self.transaction():
            self._owned(collection_id, actor, for_update=True)
            self.collections.delete(collection_id)

    def list_entries(
        self, collection_id: int, actor: User, page: int, page_size: int
    ) -> list[CollectionEntry]:
        self._owned(collection_id, actor)
        entries = self.collections.list_entries(
            collection_id, self._offset(page, page_size), page_size + 1
        )
        return [entry.for_owner(actor.id) for entry in entries]

    def add_entry(self, collection_id: int, recipe_id: int, actor: User) -> None:
        with self.transaction():
            self._owned(collection_id, actor, for_update=True)
            recipe = self.recipes.find_by_id(recipe_id, for_share=True)
            if recipe is None:
                raise RecipeNotFound()
            if recipe.status != RecipeStatus.PUBLISHED:
                if recipe.author_id != actor.id:
                    raise RecipeNotFound()
                raise RecipeNotPublished()
            self.collections.add_entry(collection_id, recipe_id)

    def remove_entry(self, collection_id: int, recipe_id: int, actor: User) -> None:
        with self.transaction():
            self._owned(collection_id, actor, for_update=True)
            self.collections.remove_entry(collection_id, recipe_id)
