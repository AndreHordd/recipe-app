from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal

from app.domain.enums import IngredientUnit, RecipeStatus
from app.domain.exceptions import InvalidRecipe, InvalidTransition


@dataclass(frozen=True)
class CatalogItem:
    id: int
    name: str


@dataclass(frozen=True)
class RecipeIngredient:
    ingredient_id: int
    quantity: Decimal
    unit: IngredientUnit
    position: int
    name: str = ""

    def validate(self) -> None:
        if self.ingredient_id < 1 or not 1 <= self.position <= 50:
            raise InvalidRecipe("Некоректний інгредієнт або його позиція.")
        if (
            not self.quantity.is_finite()
            or not Decimal("0") < self.quantity <= Decimal("999999.999")
            or self.quantity.normalize().as_tuple().exponent < -3
        ):
            raise InvalidRecipe("Кількість має бути додатною і містити до трьох десяткових знаків.")
        if self.unit not in IngredientUnit:
            raise InvalidRecipe("Оберіть одиницю вимірювання.")


@dataclass(frozen=True)
class InstructionStep:
    number: int
    description: str

    def validate(self) -> None:
        if not 1 <= self.number <= 50 or not 1 <= len(self.description.strip()) <= 2000:
            raise InvalidRecipe("Крок приготування має містити від 1 до 2000 символів.")


@dataclass
class RecipeDetails:
    title: str
    description: str = ""
    cooking_time: int | None = None
    servings: int = 1
    category_id: int | None = None
    tag_ids: list[int] = field(default_factory=list)
    ingredients: list[RecipeIngredient] = field(default_factory=list)
    steps: list[InstructionStep] = field(default_factory=list)

    def validate(self) -> None:
        if not 1 <= len(self.title.strip()) <= 150 or len(self.description) > 3000:
            raise InvalidRecipe("Назва має містити 1–150 символів, опис — до 3000.")
        if self.cooking_time is not None and not 1 <= self.cooking_time <= 1440:
            raise InvalidRecipe("Час приготування має бути від 1 до 1440 хвилин.")
        if not 1 <= self.servings <= 100:
            raise InvalidRecipe("Кількість порцій має бути від 1 до 100.")
        if self.category_id is not None and self.category_id < 1:
            raise InvalidRecipe("Некоректна категорія.")
        if len(self.tag_ids) > 10 or len(set(self.tag_ids)) != len(self.tag_ids):
            raise InvalidRecipe("Оберіть до десяти різних тегів.")
        if any(tag_id < 1 for tag_id in self.tag_ids):
            raise InvalidRecipe("Некоректний тег.")
        if len(self.ingredients) > 50 or len(self.steps) > 50:
            raise InvalidRecipe("Рецепт може містити до 50 інгредієнтів і до 50 кроків.")
        for position, ingredient in enumerate(self.ingredients, 1):
            ingredient.validate()
            if ingredient.position != position:
                raise InvalidRecipe("Позиції інгредієнтів мають бути послідовними.")
        for number, step in enumerate(self.steps, 1):
            step.validate()
            if step.number != number:
                raise InvalidRecipe("Номери кроків мають бути послідовними.")


@dataclass
class Recipe:
    author_id: int
    title: str
    id: int | None = None
    description: str = ""
    cooking_time: int | None = None
    servings: int = 1
    category_id: int | None = None
    tag_ids: list[int] = field(default_factory=list)
    ingredients: list[RecipeIngredient] = field(default_factory=list)
    steps: list[InstructionStep] = field(default_factory=list)
    status: RecipeStatus = RecipeStatus.DRAFT
    version: int = 1
    hide_reason: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    published_at: datetime | None = None
    # Display values are hydrated by the reader together with the aggregate.
    author_name: str = ""
    category_name: str | None = None
    tags: list[CatalogItem] = field(default_factory=list)
    photo_key: str | None = None

    @classmethod
    def create(cls, author_id: int, details: RecipeDetails) -> "Recipe":
        recipe = cls(author_id=author_id, title=details.title)
        recipe.update_details(details)
        return recipe

    def update_details(self, details: RecipeDetails) -> None:
        details.validate()
        if self.status == RecipeStatus.PUBLISHED:
            self.unpublish()
        self.title = details.title.strip()
        self.description = details.description
        self.cooking_time = details.cooking_time
        self.servings = details.servings
        self.category_id = details.category_id
        self.tag_ids = list(details.tag_ids)
        self.ingredients = list(details.ingredients)
        self.steps = list(details.steps)

    def add_ingredient(self, ingredient: RecipeIngredient) -> None:
        ingredient.validate()
        if len(self.ingredients) >= 50 or ingredient.position != len(self.ingredients) + 1:
            raise InvalidRecipe("Не вдалося додати інгредієнт: перевірте кількість і позицію.")
        if self.status == RecipeStatus.PUBLISHED:
            self.unpublish()
        self.ingredients.append(ingredient)

    def change_photo(self, key: str | None) -> None:
        if self.status == RecipeStatus.PUBLISHED:
            self.unpublish()
        self.photo_key = key

    def add_step(self, step: InstructionStep) -> None:
        step.validate()
        if len(self.steps) >= 50 or step.number != len(self.steps) + 1:
            raise InvalidRecipe("Не вдалося додати крок: перевірте кількість і номер.")
        if self.status == RecipeStatus.PUBLISHED:
            self.unpublish()
        self.steps.append(step)

    def publish(self) -> None:
        if self.status != RecipeStatus.DRAFT:
            raise InvalidTransition()
        if not self.category_id or not self.cooking_time or not self.ingredients or not self.steps:
            raise InvalidRecipe("Для публікації потрібні категорія, час, інгредієнти та кроки.")
        RecipeDetails(
            self.title,
            self.description,
            self.cooking_time,
            self.servings,
            self.category_id,
            self.tag_ids,
            self.ingredients,
            self.steps,
        ).validate()
        self.status = RecipeStatus.PUBLISHED
        self.published_at = datetime.now(UTC)

    def unpublish(self) -> None:
        if self.status != RecipeStatus.PUBLISHED:
            raise InvalidTransition()
        self.status = RecipeStatus.DRAFT

    def hide(self, reason: str) -> None:
        if self.status != RecipeStatus.PUBLISHED:
            raise InvalidTransition()
        if not 1 <= len(reason.strip()) <= 500:
            raise InvalidRecipe("Причина приховування має містити 1–500 символів.")
        self.status = RecipeStatus.HIDDEN
        self.hide_reason = reason.strip()

    def restore_to_draft(self) -> None:
        if self.status != RecipeStatus.HIDDEN:
            raise InvalidTransition()
        self.status = RecipeStatus.DRAFT
        self.hide_reason = None
