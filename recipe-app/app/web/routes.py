from typing import Annotated

from fastapi import APIRouter, Path, Request
from fastapi.templating import Jinja2Templates

from app.config import APP_ROOT

router = APIRouter(include_in_schema=False)
templates = Jinja2Templates(directory=APP_ROOT / "app" / "web" / "templates")


@router.get("/")
def home(request: Request):
    return templates.TemplateResponse(request=request, name="home.html")


@router.get("/login")
def login(request: Request):
    return templates.TemplateResponse(request=request, name="auth.html", context={"mode": "login"})


@router.get("/register")
def register(request: Request):
    return templates.TemplateResponse(
        request=request, name="auth.html", context={"mode": "register"}
    )


@router.get("/my-recipes")
def my_recipes(request: Request):
    return templates.TemplateResponse(request=request, name="my_recipes.html")


@router.get("/recipes/new")
def new_recipe(request: Request):
    return templates.TemplateResponse(
        request=request, name="recipe_form.html", context={"recipe_id": None}
    )


@router.get("/recipes/{recipe_id}/edit")
def edit_recipe(request: Request, recipe_id: Annotated[int, Path(gt=0)]):
    return templates.TemplateResponse(
        request=request, name="recipe_form.html", context={"recipe_id": recipe_id}
    )


@router.get("/recipes/{recipe_id}")
def recipe(request: Request, recipe_id: Annotated[int, Path(gt=0)]):
    return templates.TemplateResponse(
        request=request, name="recipe.html", context={"recipe_id": recipe_id}
    )


@router.get("/collections")
def collections(request: Request):
    return templates.TemplateResponse(request=request, name="collections.html")


@router.get("/admin")
def administration(request: Request):
    return templates.TemplateResponse(request=request, name="admin.html")


@router.get("/collections/{collection_id}")
def collection(request: Request, collection_id: Annotated[int, Path(gt=0)]):
    return templates.TemplateResponse(
        request=request, name="collection.html", context={"collection_id": collection_id}
    )
