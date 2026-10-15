from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, field_validator

from app.api.schemas import RequestModel, collapse_name, strip_name
from app.domain.enums import IngredientUnit, RecipeStatus
from app.domain.recipes import InstructionStep, Recipe, RecipeDetails, RecipeIngredient

PositiveId = Annotated[int, Field(gt=0, strict=True)]


def quantity_string(value: object) -> object:
    if not isinstance(value, str):
        raise ValueError("quantity must be a decimal string")
    return value


class IngredientInput(RequestModel):
    ingredient_id: PositiveId
    quantity: Annotated[
        Decimal,
        BeforeValidator(quantity_string),
        Field(
            gt=0,
            le=Decimal("999999.999"),
            max_digits=9,
            decimal_places=3,
            allow_inf_nan=False,
        ),
    ]
    unit: IngredientUnit


class StepInput(RequestModel):
    description: Annotated[
        str,
        BeforeValidator(strip_name),
        Field(
            min_length=1,
            max_length=2000,
            strict=True,
        ),
    ]


class RecipeCreate(RequestModel):
    title: Annotated[
        str, BeforeValidator(strip_name), Field(min_length=1, max_length=150, strict=True)
    ]
    description: Annotated[str, Field(max_length=3000, strict=True)] = ""
    cooking_time: Annotated[int, Field(ge=1, le=1440, strict=True)] | None = None
    servings: Annotated[int, Field(ge=1, le=100, strict=True)] = 1
    category_id: PositiveId | None = None
    tag_ids: Annotated[list[PositiveId], Field(max_length=10)] = Field(default_factory=list)
    ingredients: Annotated[list[IngredientInput], Field(max_length=50)] = Field(
        default_factory=list
    )
    steps: Annotated[list[StepInput], Field(max_length=50)] = Field(default_factory=list)

    @field_validator("tag_ids")
    @classmethod
    def unique_tags(cls, value: list[int]) -> list[int]:
        if len(value) != len(set(value)):
            raise ValueError("tag_ids must be unique")
        return value

    def to_details(self) -> RecipeDetails:
        return RecipeDetails(
            title=self.title,
            description=self.description,
            cooking_time=self.cooking_time,
            servings=self.servings,
            category_id=self.category_id,
            tag_ids=self.tag_ids,
            ingredients=[
                RecipeIngredient(item.ingredient_id, item.quantity, item.unit, position)
                for position, item in enumerate(self.ingredients, 1)
            ],
            steps=[
                InstructionStep(number, step.description)
                for number, step in enumerate(self.steps, 1)
            ],
        )


class RecipeUpdate(RecipeCreate):
    version: PositiveId


class VersionRequest(RequestModel):
    version: PositiveId


class NameRequest(RequestModel):
    name: Annotated[
        str, BeforeValidator(collapse_name), Field(min_length=1, max_length=80, strict=True)
    ]


class CatalogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str


class AuthorRead(BaseModel):
    id: int
    display_name: str


class IngredientRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    ingredient_id: int
    name: str
    quantity: Decimal
    unit: IngredientUnit
    position: int


class StepRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    number: int
    description: str


class RecipeSummary(BaseModel):
    id: int
    title: str
    description: str
    author: AuthorRead
    category: CatalogRead | None
    tags: list[CatalogRead]
    cooking_time: int | None
    servings: int
    status: RecipeStatus
    version: int
    created_at: datetime
    updated_at: datetime
    photo_url: str | None = None
    thumbnail_url: str | None = None

    @classmethod
    def from_recipe(cls, recipe: Recipe) -> "RecipeSummary":
        return cls(
            id=recipe.id,
            title=recipe.title,
            description=recipe.description,
            author=AuthorRead(id=recipe.author_id, display_name=recipe.author_name),
            category=CatalogRead(id=recipe.category_id, name=recipe.category_name)
            if recipe.category_id is not None
            else None,
            tags=[CatalogRead.model_validate(item) for item in recipe.tags],
            cooking_time=recipe.cooking_time,
            servings=recipe.servings,
            status=recipe.status,
            version=recipe.version,
            created_at=recipe.created_at,
            updated_at=recipe.updated_at,
            photo_url=f"/api/recipes/{recipe.id}/photo?v={recipe.version}"
            if recipe.photo_key
            else None,
            thumbnail_url=f"/api/recipes/{recipe.id}/photo?thumbnail=true&v={recipe.version}"
            if recipe.photo_key
            else None,
        )


class RecipeRead(RecipeSummary):
    ingredients: list[IngredientRead]
    steps: list[StepRead]
    hide_reason: str | None
    published_at: datetime | None

    @classmethod
    def from_recipe(cls, recipe: Recipe) -> "RecipeRead":
        summary = RecipeSummary.from_recipe(recipe)
        return cls(
            **summary.model_dump(),
            ingredients=[IngredientRead.model_validate(item) for item in recipe.ingredients],
            steps=[StepRead.model_validate(step) for step in recipe.steps],
            hide_reason=recipe.hide_reason,
            published_at=recipe.published_at,
        )


class Page[T](BaseModel):
    items: list[T]
    page: int
    page_size: int
    has_next: bool


def recipe_page(recipes: list[Recipe], page: int, page_size: int) -> Page[RecipeSummary]:
    return Page[RecipeSummary](
        items=[RecipeSummary.from_recipe(recipe) for recipe in recipes[:page_size]],
        page=page,
        page_size=page_size,
        has_next=len(recipes) > page_size,
    )
