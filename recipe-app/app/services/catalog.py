from collections.abc import Callable
from contextlib import AbstractContextManager

from app.domain.contracts import ICatalogRepository
from app.domain.exceptions import ApplicationError
from app.domain.recipes import CatalogItem


def normalize_catalog_name(name: str) -> tuple[str, str]:
    display_name = " ".join(name.split())
    if not 1 <= len(display_name) <= 80:
        raise ApplicationError("INVALID_NAME", "Назва має містити 1–80 символів.", 422)
    return display_name, display_name.casefold()


class CatalogService:
    def __init__(
        self, catalog: ICatalogRepository, transaction: Callable[[], AbstractContextManager]
    ):
        self.catalog = catalog
        self.transaction = transaction

    def categories(self) -> list[CatalogItem]:
        return self.catalog.list_categories()

    def tags(self) -> list[CatalogItem]:
        return self.catalog.list_tags()

    def ingredients(self, q: str, page: int, page_size: int) -> list[CatalogItem]:
        return self.catalog.find_ingredients(
            " ".join(q.split()).casefold(), (page - 1) * page_size, page_size + 1
        )

    def create_ingredient(self, name: str) -> tuple[CatalogItem, bool]:
        display_name, normalized_name = normalize_catalog_name(name)
        with self.transaction():
            return self.catalog.create_ingredient(display_name, normalized_name)
