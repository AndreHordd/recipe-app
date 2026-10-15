from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response

from app.api.recipe_schemas import CatalogRead, NameRequest, Page
from app.dependencies import Catalog, require_csrf, require_json
from app.domain.models import Session

router = APIRouter(prefix="/api", tags=["Довідники"])


@router.get("/categories", response_model=list[CatalogRead])
def categories(service: Catalog):
    return service.categories()


@router.get("/tags", response_model=list[CatalogRead])
def tags(service: Catalog):
    return service.tags()


@router.get("/ingredients", response_model=Page[CatalogRead])
def ingredients(
    service: Catalog,
    q: Annotated[str, Query(max_length=100)] = "",
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=50)] = 20,
):
    items = service.ingredients(q, page, page_size)
    return Page[CatalogRead](
        items=[CatalogRead.model_validate(item) for item in items[:page_size]],
        page=page,
        page_size=page_size,
        has_next=len(items) > page_size,
    )


@router.post("/ingredients", response_model=CatalogRead, dependencies=[Depends(require_json)])
def create_ingredient(
    data: NameRequest,
    response: Response,
    service: Catalog,
    session: Annotated[Session, Depends(require_csrf)],
):
    item, created = service.create_ingredient(data.name)
    response.status_code = 201 if created else 200
    return item
