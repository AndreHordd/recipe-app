from contextlib import nullcontext

import pytest
from pydantic import ValidationError

from app.api.admin_schemas import HideRequest, UserActivityRequest
from app.domain.enums import UserRole
from app.domain.exceptions import AccessDenied, ApplicationError
from app.domain.models import User
from app.services.catalog import normalize_catalog_name
from app.services.moderation import ModerationService


@pytest.mark.parametrize(
    "action,args",
    [
        ("list_recipes", (None, None, "", 1, 20)),
        ("hide", (1, 1, "Причина")),
        ("restore", (1, 1)),
        ("list_users", ("", 1, 20)),
        ("set_active", (2, False)),
        ("create_catalog_item", ("category", "Сніданки")),
        ("rename_catalog_item", ("tag", 1, "Швидко")),
        ("delete_catalog_item", ("tag", 1)),
    ],
)
def test_service_requires_admin_before_accessing_any_repository(action, args):
    service = ModerationService(None, None, None, None, None, nullcontext)
    actor = User(1, "user@example.com", "Автор", UserRole.USER, True)
    with pytest.raises(AccessDenied):
        getattr(service, action)(actor, *args)


def test_catalog_names_share_unicode_and_whitespace_normalization():
    assert normalize_catalog_name(" \tЇЖА   НА\nЩОДЕНЬ  ") == ("ЇЖА НА ЩОДЕНЬ", "їжа на щодень")
    assert normalize_catalog_name("Ї" * 80) == ("Ї" * 80, "ї" * 80)
    for invalid in [" \t\n", "Ї" * 81]:
        with pytest.raises(ApplicationError) as error:
            normalize_catalog_name(invalid)
        assert error.value.code == "INVALID_NAME"


@pytest.mark.parametrize(
    "data",
    [
        {"version": True, "reason": "Причина"},
        {"version": "1", "reason": "Причина"},
        {"version": 1, "reason": " \n "},
        {"version": 1, "reason": "Ї" * 501},
        {"version": 1, "reason": 7},
        {"version": 1, "reason": "Причина", "status": "HIDDEN"},
    ],
)
def test_hide_payload_rejects_invalid_fields(data):
    with pytest.raises(ValidationError):
        HideRequest.model_validate(data)


@pytest.mark.parametrize(
    "data", [{"is_active": "false"}, {"is_active": 0}, {"is_active": True, "role": "ADMIN"}]
)
def test_activity_payload_does_not_coerce_values_or_accept_role(data):
    with pytest.raises(ValidationError):
        UserActivityRequest.model_validate(data)
