from typing import Annotated

from pydantic import BeforeValidator, Field

from app.api.recipe_schemas import PositiveId
from app.api.schemas import RequestModel, strip_name


class HideRequest(RequestModel):
    version: PositiveId
    reason: Annotated[
        str, BeforeValidator(strip_name), Field(min_length=1, max_length=500, strict=True)
    ]


class UserActivityRequest(RequestModel):
    is_active: Annotated[bool, Field(strict=True)]
