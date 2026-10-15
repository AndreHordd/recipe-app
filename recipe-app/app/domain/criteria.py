from dataclasses import dataclass
from typing import Literal

from app.domain.enums import RecipeStatus
from app.domain.exceptions import InvalidSearch


@dataclass(frozen=True)
class SearchCriteria:
    mode: str = "title"
    q: str = ""
    category_id: int | None = None
    tag_id: int | None = None
    max_cooking_time: int | None = None
    page: int = 1
    page_size: int = 20
    sort: Literal["newest", "title"] = "newest"

    def validate(self) -> None:
        if len(self.q) > 100:
            raise InvalidSearch("Пошуковий запит має містити до 100 символів.")
        if (
            self.page < 1
            or not 1 <= self.page_size <= 50
            or (self.page - 1) * self.page_size > 2**63 - 1
        ):
            raise InvalidSearch("Перевірте номер і розмір сторінки.")
        if any(value is not None and value < 1 for value in [self.category_id, self.tag_id]):
            raise InvalidSearch("Некоректна категорія або тег.")
        if self.max_cooking_time is not None and not 1 <= self.max_cooking_time <= 1440:
            raise InvalidSearch("Час має бути від 1 до 1440 хвилин.")
        if self.sort not in {"newest", "title"}:
            raise InvalidSearch("Невідомий спосіб сортування.")


@dataclass(frozen=True)
class RecipeQuery:
    scope: Literal["public", "author", "moderation"] = "public"
    author_id: int | None = None
    status: RecipeStatus | None = None
    title_substring: str | None = None
    ingredient_substring: str | None = None
    category_id: int | None = None
    tag_id: int | None = None
    max_cooking_time: int | None = None
    sort: Literal["newest", "title"] = "newest"
    offset: int = 0
    limit: int = 20
