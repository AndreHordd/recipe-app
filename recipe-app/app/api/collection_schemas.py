from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

from app.api.recipe_schemas import RecipeSummary
from app.api.schemas import RequestModel, strip_name
from app.domain.collections import CollectionEntry


class CollectionNameRequest(RequestModel):
    name: Annotated[
        str, BeforeValidator(strip_name), Field(min_length=1, max_length=100, strict=True)
    ]


class CollectionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    created_at: datetime
    updated_at: datetime


class CollectionEntryRead(BaseModel):
    recipe_id: int
    saved_at: datetime
    available: bool
    recipe: RecipeSummary | None

    @classmethod
    def from_entry(cls, entry: CollectionEntry) -> "CollectionEntryRead":
        return cls(
            recipe_id=entry.recipe_id,
            saved_at=entry.saved_at,
            available=entry.available,
            recipe=RecipeSummary.from_recipe(entry.recipe) if entry.recipe else None,
        )
