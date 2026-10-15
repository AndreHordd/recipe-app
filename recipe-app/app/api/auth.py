from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response

from app.api.schemas import LoginRequest, RegisterRequest, SessionRead, UserRead
from app.config import Settings
from app.dependencies import (
    COOKIE_NAME,
    Authentication,
    get_settings,
    require_csrf,
    require_json,
    require_session,
)
from app.domain.models import Session

router = APIRouter(prefix="/api/auth", tags=["Обліковий запис"])


@router.post(
    "/register", status_code=201, response_model=UserRead, dependencies=[Depends(require_json)]
)
def register(data: RegisterRequest, service: Authentication):
    return service.register(str(data.email).lower(), data.display_name, data.password)


@router.post("/login", response_model=SessionRead, dependencies=[Depends(require_json)])
def login(
    data: LoginRequest,
    request: Request,
    response: Response,
    service: Authentication,
    settings: Annotated[Settings, Depends(get_settings)],
):
    result = service.login(str(data.email).lower(), data.password, request.cookies.get(COOKIE_NAME))
    response.set_cookie(
        COOKIE_NAME,
        result.token,
        max_age=settings.session_days * 86400,
        expires=result.session.expires_at,
        path="/",
        secure=settings.cookie_secure,
        httponly=True,
        samesite="lax",
    )
    return SessionRead(
        user=UserRead.model_validate(result.session.user), csrf_token=result.session.csrf_token
    )


@router.get("/me", response_model=SessionRead)
def me(session: Annotated[Session, Depends(require_session)]):
    return SessionRead(user=UserRead.model_validate(session.user), csrf_token=session.csrf_token)


@router.post("/logout", status_code=204)
def logout(
    session: Annotated[Session, Depends(require_csrf)],
    service: Authentication,
    settings: Annotated[Settings, Depends(get_settings)],
):
    service.logout(session)
    response = Response(status_code=204)
    response.delete_cookie(
        COOKIE_NAME, path="/", secure=settings.cookie_secure, httponly=True, samesite="lax"
    )
    return response
