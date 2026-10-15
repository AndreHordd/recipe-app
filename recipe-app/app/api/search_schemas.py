from typing import Annotated, Literal

from pydantic import BeforeValidator, Field

from app.api.schemas import RequestModel, strip_name
from app.domain.criteria import SearchCriteria


class SearchParams(RequestModel):
    mode: Annotated[
        str,
        Field(
            min_length=1,
            max_length=30,
            description="title — назва, ingredient — інгредієнт, category — категорія",
        ),
    ] = "title"
    q: Annotated[str, BeforeValidator(strip_name), Field(max_length=100)] = ""
    category_id: Annotated[int, Field(gt=0)] | None = None
    tag_id: Annotated[int, Field(gt=0)] | None = None
    max_cooking_time: Annotated[int, Field(ge=1, le=1440)] | None = None
    page: Annotated[int, Field(ge=1)] = 1
    page_size: Annotated[int, Field(ge=1, le=50)] = 20
    sort: Literal["newest", "title"] = "newest"

    def to_criteria(self) -> SearchCriteria:
        return SearchCriteria(**self.model_dump())
