from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Response

from app.api.admin_schemas import HideRequest, UserActivityRequest
from app.api.recipe_schemas import (
    CatalogRead,
    NameRequest,
    Page,
    RecipeRead,
    RecipeSummary,
    VersionRequest,
    recipe_page,
)
from app.api.schemas import UserRead
from app.dependencies import Moderation, require_admin, require_csrf, require_json
from app.domain.enums import RecipeStatus
from app.domain.models import Session, User

router = APIRouter(
    prefix="/api/admin", tags=["Адміністрування"], dependencies=[Depends(require_admin)]
)
Admin = Annotated[User, Depends(require_admin)]
WriteSession = Annotated[Session, Depends(require_csrf)]
ItemId = Annotated[int, Path(gt=0, le=2**63 - 1)]
PageNumber = Annotated[int, Query(ge=1)]
PageSize = Annotated[int, Query(ge=1, le=50)]
SearchText = Annotated[str, Query(max_length=100)]


@router.get("/recipes", response_model=Page[RecipeSummary])
def recipes(
    service: Moderation,
    actor: Admin,
    status: RecipeStatus | None = None,
    author_id: Annotated[int | None, Query(gt=0, le=2**63 - 1)] = None,
    q: SearchText = "",
    page: PageNumber = 1,
    page_size: PageSize = 20,
):
    return recipe_page(
        service.list_recipes(actor, status, author_id, q, page, page_size), page, page_size
    )


@router.post(
    "/recipes/{recipe_id}/hide", response_model=RecipeRead, dependencies=[Depends(require_json)]
)
def hide(recipe_id: ItemId, data: HideRequest, session: WriteSession, service: Moderation):
    return RecipeRead.from_recipe(service.hide(session.user, recipe_id, data.version, data.reason))


@router.post(
    "/recipes/{recipe_id}/restore", response_model=RecipeRead, dependencies=[Depends(require_json)]
)
def restore(recipe_id: ItemId, data: VersionRequest, session: WriteSession, service: Moderation):
    return RecipeRead.from_recipe(service.restore(session.user, recipe_id, data.version))


@router.get("/users", response_model=Page[UserRead])
def users(
    service: Moderation,
    actor: Admin,
    q: SearchText = "",
    page: PageNumber = 1,
    page_size: PageSize = 20,
):
    items = service.list_users(actor, q, page, page_size)
    return Page[UserRead](
        items=items[:page_size], page=page, page_size=page_size, has_next=len(items) > page_size
    )


@router.patch("/users/{user_id}", response_model=UserRead, dependencies=[Depends(require_json)])
def activity(
    user_id: ItemId, data: UserActivityRequest, session: WriteSession, service: Moderation
):
    return service.set_active(session.user, user_id, data.is_active)


@router.post(
    "/categories", status_code=201, response_model=CatalogRead, dependencies=[Depends(require_json)]
)
def create_category(data: NameRequest, session: WriteSession, service: Moderation):
    return service.create_catalog_item(session.user, "category", data.name)


@router.put(
    "/categories/{item_id}", response_model=CatalogRead, dependencies=[Depends(require_json)]
)
def rename_category(item_id: ItemId, data: NameRequest, session: WriteSession, service: Moderation):
    return service.rename_catalog_item(session.user, "category", item_id, data.name)


@router.delete("/categories/{item_id}", status_code=204)
def delete_category(item_id: ItemId, session: WriteSession, service: Moderation):
    service.delete_catalog_item(session.user, "category", item_id)
    return Response(status_code=204)


@router.post(
    "/tags", status_code=201, response_model=CatalogRead, dependencies=[Depends(require_json)]
)
def create_tag(data: NameRequest, session: WriteSession, service: Moderation):
    return service.create_catalog_item(session.user, "tag", data.name)


@router.put("/tags/{item_id}", response_model=CatalogRead, dependencies=[Depends(require_json)])
def rename_tag(item_id: ItemId, data: NameRequest, session: WriteSession, service: Moderation):
    return service.rename_catalog_item(session.user, "tag", item_id, data.name)


@router.delete("/tags/{item_id}", status_code=204)
def delete_tag(item_id: ItemId, session: WriteSession, service: Moderation):
    service.delete_catalog_item(session.user, "tag", item_id)
    return Response(status_code=204)
