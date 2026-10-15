from abc import ABC, abstractmethod
from datetime import datetime
from typing import Literal

from app.domain.collections import Collection, CollectionEntry
from app.domain.criteria import RecipeQuery, SearchCriteria
from app.domain.models import Session, User, UserCredentials
from app.domain.recipes import CatalogItem, Recipe, RecipeDetails


class IUserRepository(ABC):
    @abstractmethod
    def find_by_id(self, user_id: int, *, for_update: bool = False) -> User | None:
        pass

    @abstractmethod
    def find(self, q: str, offset: int, limit: int) -> list[User]:
        pass

    @abstractmethod
    def set_active(self, user_id: int, is_active: bool) -> User:
        pass

    @abstractmethod
    def find_by_email(self, email: str, *, for_update: bool = False) -> UserCredentials | None:
        pass

    @abstractmethod
    def create(self, email: str, display_name: str, password_hash: str) -> User:
        pass


class ISessionRepository(ABC):
    @abstractmethod
    def delete_for_user(self, user_id: int) -> None:
        pass

    @abstractmethod
    def find_live(self, token_hash: str) -> Session | None:
        pass

    @abstractmethod
    def create(self, token_hash: str, user: User, csrf_token: str, expires_at: datetime) -> Session:
        pass

    @abstractmethod
    def delete(self, token_hash: str) -> None:
        pass

    @abstractmethod
    def delete_expired(self) -> None:
        pass


class IPasswordHasher(ABC):
    @abstractmethod
    def hash(self, password: str) -> str:
        pass

    @abstractmethod
    def verify(self, password: str, password_hash: str | None) -> bool:
        pass


class IRecipeReader(ABC):
    @abstractmethod
    def find_by_id(self, recipe_id: int, *, for_share: bool = False) -> Recipe | None:
        pass

    @abstractmethod
    def find(self, criteria: RecipeQuery) -> list[Recipe]:
        pass


class IRecipeWriter(ABC):
    @abstractmethod
    def save(self, recipe: Recipe, expected_version: int | None) -> None:
        pass

    @abstractmethod
    def delete(self, recipe_id: int, expected_version: int) -> None:
        pass


class IPhotoStorage(ABC):
    @abstractmethod
    def store(self, content: bytes) -> str:
        pass

    @abstractmethod
    def read(self, key: str, *, thumbnail: bool = False) -> bytes:
        pass

    @abstractmethod
    def delete(self, key: str) -> None:
        pass


class SearchStrategy(ABC):
    @abstractmethod
    def search(self, criteria: SearchCriteria) -> list[Recipe]:
        pass


class ICatalogRepository(ABC):
    @abstractmethod
    def create_item(
        self, kind: Literal["category", "tag"], name: str, normalized_name: str
    ) -> CatalogItem:
        pass

    @abstractmethod
    def rename_item(
        self, kind: Literal["category", "tag"], item_id: int, name: str, normalized_name: str
    ) -> CatalogItem:
        pass

    @abstractmethod
    def delete_item(self, kind: Literal["category", "tag"], item_id: int) -> None:
        pass

    @abstractmethod
    def list_categories(self) -> list[CatalogItem]:
        pass

    @abstractmethod
    def list_tags(self) -> list[CatalogItem]:
        pass

    @abstractmethod
    def find_ingredients(self, q: str, offset: int, limit: int) -> list[CatalogItem]:
        pass

    @abstractmethod
    def create_ingredient(self, name: str, normalized_name: str) -> tuple[CatalogItem, bool]:
        pass

    @abstractmethod
    def validate_references(self, details: RecipeDetails) -> None:
        pass


class ICollectionRepository(ABC):
    @abstractmethod
    def find_by_id(self, collection_id: int, *, for_update: bool = False) -> Collection | None:
        pass

    @abstractmethod
    def list_owned(self, owner_id: int, offset: int, limit: int) -> list[Collection]:
        pass

    @abstractmethod
    def create(self, collection: Collection) -> None:
        pass

    @abstractmethod
    def rename(self, collection: Collection) -> None:
        pass

    @abstractmethod
    def delete(self, collection_id: int) -> None:
        pass

    @abstractmethod
    def list_entries(self, collection_id: int, offset: int, limit: int) -> list[CollectionEntry]:
        pass

    @abstractmethod
    def add_entry(self, collection_id: int, recipe_id: int) -> None:
        pass

    @abstractmethod
    def remove_entry(self, collection_id: int, recipe_id: int) -> None:
        pass
