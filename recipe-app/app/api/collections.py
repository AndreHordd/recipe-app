from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Response

from app.api.collection_schemas import CollectionEntryRead, CollectionNameRequest, CollectionRead
from app.api.recipe_schemas import Page
from app.dependencies import Collections, require_actor, require_csrf, require_json
from app.domain.models import Session, User

router = APIRouter(prefix="/api/collections", tags=["Колекції"])
CollectionId = Annotated[int, Path(gt=0)]
RecipeId = Annotated[int, Path(gt=0)]
PageNumber = Annotated[int, Query(ge=1)]
PageSize = Annotated[int, Query(ge=1, le=50)]
Actor = Annotated[User, Depends(require_actor)]
WriteSession = Annotated[Session, Depends(require_csrf)]


@router.get("", response_model=Page[CollectionRead])
def list_collections(
    service: Collections, actor: Actor, page: PageNumber = 1, page_size: PageSize = 20
):
    items = service.list_owned(actor, page, page_size)
    return Page[CollectionRead](
        items=items[:page_size], page=page, page_size=page_size, has_next=len(items) > page_size
    )


@router.post(
    "", status_code=201, response_model=CollectionRead, dependencies=[Depends(require_json)]
)
def create_collection(data: CollectionNameRequest, session: WriteSession, service: Collections):
    return service.create(session.user, data.name)


@router.get("/{collection_id}", response_model=CollectionRead)
def details(collection_id: CollectionId, actor: Actor, service: Collections):
    return service.get_owned(collection_id, actor)


@router.put("/{collection_id}", response_model=CollectionRead, dependencies=[Depends(require_json)])
def rename(
    collection_id: CollectionId,
    data: CollectionNameRequest,
    session: WriteSession,
    service: Collections,
):
    return service.rename(collection_id, session.user, data.name)


@router.delete("/{collection_id}", status_code=204)
def delete(collection_id: CollectionId, session: WriteSession, service: Collections):
    service.delete(collection_id, session.user)
    return Response(status_code=204)


@router.get("/{collection_id}/recipes", response_model=Page[CollectionEntryRead])
def entries(
    collection_id: CollectionId,
    actor: Actor,
    service: Collections,
    page: PageNumber = 1,
    page_size: PageSize = 20,
):
    items = service.list_entries(collection_id, actor, page, page_size)
    return Page[CollectionEntryRead](
        items=[CollectionEntryRead.from_entry(item) for item in items[:page_size]],
        page=page,
        page_size=page_size,
        has_next=len(items) > page_size,
    )


@router.put("/{collection_id}/recipes/{recipe_id}", status_code=204)
def add_recipe(
    collection_id: CollectionId, recipe_id: RecipeId, session: WriteSession, service: Collections
):
    service.add_entry(collection_id, recipe_id, session.user)
    return Response(status_code=204)


@router.delete("/{collection_id}/recipes/{recipe_id}", status_code=204)
def remove_recipe(
    collection_id: CollectionId, recipe_id: RecipeId, session: WriteSession, service: Collections
):
    service.remove_entry(collection_id, recipe_id, session.user)
    return Response(status_code=204)
