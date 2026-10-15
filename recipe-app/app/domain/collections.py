from dataclasses import dataclass, replace
from datetime import datetime

from app.domain.enums import RecipeStatus
from app.domain.exceptions import InvalidCollection
from app.domain.recipes import Recipe


@dataclass
class Collection:
    owner_id: int
    name: str
    id: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @classmethod
    def create(cls, owner_id: int, name: str) -> "Collection":
        collection = cls(owner_id, "")
        collection.rename(name)
        return collection

    def rename(self, name: str) -> None:
        clean_name = name.strip()
        if not 1 <= len(clean_name) <= 100:
            raise InvalidCollection("Назва колекції має містити від 1 до 100 символів.")
        self.name = clean_name


@dataclass(frozen=True)
class CollectionEntry:
    collection_id: int
    recipe_id: int
    saved_at: datetime
    recipe: Recipe | None

    @property
    def available(self) -> bool:
        return self.recipe is not None

    def for_owner(self, owner_id: int) -> "CollectionEntry":
        if self.recipe and (
            self.recipe.status == RecipeStatus.PUBLISHED or self.recipe.author_id == owner_id
        ):
            return self
        return replace(self, recipe=None)
