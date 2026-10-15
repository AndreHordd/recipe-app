from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request, Response
from starlette.concurrency import run_in_threadpool

from app.api.recipe_schemas import (
    Page,
    RecipeCreate,
    RecipeRead,
    RecipeSummary,
    RecipeUpdate,
    VersionRequest,
    recipe_page,
)
from app.dependencies import (
    Recipes,
    RecipeSearch,
    Search,
    optional_actor,
    require_actor,
    require_csrf,
    require_json,
)
from app.domain.enums import RecipeStatus
from app.domain.exceptions import ApplicationError, PhotoTooLarge
from app.domain.models import Session, User
from app.infrastructure.photos import MAX_PHOTO_BYTES

router = APIRouter(prefix="/api/recipes", tags=["Рецепти"])
RecipeId = Annotated[int, Path(gt=0)]
PageNumber = Annotated[int, Query(ge=1)]
PageSize = Annotated[int, Query(ge=1, le=50)]
WriteSession = Annotated[Session, Depends(require_csrf)]
PhotoVersion = Annotated[int, Query(gt=0, le=2_147_483_647)]
PhotoRecipeId = Annotated[int, Path(gt=0, le=9_223_372_036_854_775_807)]


@router.get("", response_model=Page[RecipeSummary])
def public_recipes(service: RecipeSearch, criteria: Search):
    return recipe_page(service.search(criteria), criteria.page, criteria.page_size)


@router.get("/mine", response_model=Page[RecipeSummary])
def mine(
    service: Recipes,
    actor: Annotated[User, Depends(require_actor)],
    status: RecipeStatus | None = None,
    page: PageNumber = 1,
    page_size: PageSize = 20,
):
    return recipe_page(service.list_owned(actor, status, page, page_size), page, page_size)


@router.get("/{recipe_id}", response_model=RecipeRead)
def details(
    recipe_id: RecipeId, service: Recipes, actor: Annotated[User | None, Depends(optional_actor)]
):
    return RecipeRead.from_recipe(service.get_visible(recipe_id, actor))


@router.get("/{recipe_id}/photo", response_class=Response)
def photo(
    recipe_id: PhotoRecipeId,
    service: Recipes,
    actor: Annotated[User | None, Depends(optional_actor)],
    thumbnail: bool = False,
):
    return Response(
        service.read_photo(recipe_id, actor, thumbnail=thumbnail),
        media_type="image/jpeg",
        headers={"Cache-Control": "no-store"},
    )


@router.put(
    "/{recipe_id}/photo",
    response_model=RecipeRead,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                kind: {"schema": {"type": "string", "format": "binary"}}
                for kind in ("image/jpeg", "image/png", "image/webp")
            },
        }
    },
)
async def upload_photo(
    recipe_id: PhotoRecipeId,
    version: PhotoVersion,
    request: Request,
    session: WriteSession,
    service: Recipes,
):
    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type not in {"image/jpeg", "image/png", "image/webp", "application/octet-stream"}:
        raise ApplicationError("PHOTO_FORMAT_REQUIRED", "Надішліть файл JPEG, PNG або WebP.", 415)
    length = request.headers.get("content-length", "")
    if length.isdigit() and int(length) > MAX_PHOTO_BYTES:
        raise PhotoTooLarge()
    content = bytearray()
    async for chunk in request.stream():
        if len(content) + len(chunk) > MAX_PHOTO_BYTES:
            raise PhotoTooLarge()
        content.extend(chunk)
    recipe = await run_in_threadpool(
        service.replace_photo, recipe_id, session.user, version, bytes(content)
    )
    return RecipeRead.from_recipe(recipe)


@router.delete("/{recipe_id}/photo", response_model=RecipeRead)
def remove_photo(
    recipe_id: PhotoRecipeId, version: PhotoVersion, session: WriteSession, service: Recipes
):
    return RecipeRead.from_recipe(service.delete_photo(recipe_id, session.user, version))


@router.post("", status_code=201, response_model=RecipeRead, dependencies=[Depends(require_json)])
def create(data: RecipeCreate, session: WriteSession, service: Recipes):
    return RecipeRead.from_recipe(service.create(session.user, data.to_details()))


@router.put("/{recipe_id}", response_model=RecipeRead, dependencies=[Depends(require_json)])
def update(recipe_id: RecipeId, data: RecipeUpdate, session: WriteSession, service: Recipes):
    return RecipeRead.from_recipe(
        service.update(recipe_id, session.user, data.to_details(), data.version)
    )


@router.post(
    "/{recipe_id}/publish", response_model=RecipeRead, dependencies=[Depends(require_json)]
)
def publish(recipe_id: RecipeId, data: VersionRequest, session: WriteSession, service: Recipes):
    return RecipeRead.from_recipe(service.publish(recipe_id, session.user, data.version))


@router.post(
    "/{recipe_id}/unpublish", response_model=RecipeRead, dependencies=[Depends(require_json)]
)
def unpublish(recipe_id: RecipeId, data: VersionRequest, session: WriteSession, service: Recipes):
    return RecipeRead.from_recipe(service.unpublish(recipe_id, session.user, data.version))


@router.delete("/{recipe_id}", status_code=204)
def delete(
    recipe_id: RecipeId,
    version: Annotated[int, Query(gt=0)],
    session: WriteSession,
    service: Recipes,
):
    service.delete(recipe_id, session.user, version)
    return Response(status_code=204)
