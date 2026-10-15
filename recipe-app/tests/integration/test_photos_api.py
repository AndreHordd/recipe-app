from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.api.recipe_schemas import RecipeCreate
from app.domain.exceptions import VersionConflict
from app.domain.models import User
from app.infrastructure.database import connect
from app.infrastructure.photos import MAX_PHOTO_BYTES, LocalPhotoStorage
from app.infrastructure.repositories.catalog import PostgreSQLCatalogRepository
from app.infrastructure.repositories.recipes import PostgreSQLRecipeRepository
from app.infrastructure.repositories.sessions import SqlSessionRepository
from app.infrastructure.repositories.users import SqlUserRepository
from app.main import create_app
from app.services.moderation import ModerationService
from app.services.recipes import RecipeService

pytestmark = pytest.mark.integration


def image_bytes(format="PNG", size=(800, 400), color="red", **save_options):
    with Image.new("RGB", size, color) as image, BytesIO() as stream:
        image.save(stream, format, **save_options)
        return stream.getvalue()


@pytest.fixture
def photos(client, tmp_path):
    storage = LocalPhotoStorage(tmp_path / "photos")
    client.app.state.photos = storage
    return storage


@pytest.fixture
def headers(register_and_login, origin):
    return {**origin, "X-CSRF-Token": register_and_login["csrf_token"]}


@pytest.fixture
def recipe(client, database, headers, photos):
    category_id = database.execute(
        "INSERT INTO categories (name, normalized_name) VALUES ('Страви', 'страви') RETURNING id"
    ).fetchone()["id"]
    ingredient_id = database.execute(
        "INSERT INTO ingredients (name, normalized_name) VALUES ('Яйце', 'яйце') RETURNING id"
    ).fetchone()["id"]
    tag_id = database.execute(
        "INSERT INTO tags (name, normalized_name) VALUES ('Швидко', 'швидко') RETURNING id"
    ).fetchone()["id"]
    details = {
        "title": "Омлет із фотографією",
        "description": "Опис страви",
        "category_id": category_id,
        "tag_ids": [tag_id],
        "cooking_time": 15,
        "servings": 2,
        "ingredients": [{"ingredient_id": ingredient_id, "quantity": "2.125", "unit": "pcs"}],
        "steps": [{"description": "Приготувати омлет."}],
    }
    response = client.post("/api/recipes", json=details, headers=headers)
    assert response.status_code == 201, response.text
    return response.json(), details


def upload(client, recipe_id, version, headers, content=None, content_type="image/png"):
    return client.put(
        f"/api/recipes/{recipe_id}/photo?version={version}",
        content=image_bytes() if content is None else content,
        headers={**headers, "Content-Type": content_type},
    )


def photo_key(database, recipe_id):
    return database.execute("SELECT photo_key FROM recipes WHERE id = %s", (recipe_id,)).fetchone()[
        "photo_key"
    ]


def assert_error(response, status, code):
    assert response.status_code == status, response.text
    assert response.json()["error"]["code"] == code
    assert response.headers["Cache-Control"] == "no-store"


def assert_pair(storage, key, *, exists=True):
    for thumbnail in [False, True]:
        assert storage.path(key, thumbnail=thumbnail).exists() == exists


def assert_jpeg(response, expected_size):
    assert response.status_code == 200, response.text[:100] if response.status_code != 200 else ""
    assert response.headers["Content-Type"] == "image/jpeg"
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    with Image.open(BytesIO(response.content)) as image:
        image.load()
        assert image.format == "JPEG" and image.mode == "RGB"
        assert image.size == expected_size
        assert not image.getexif()


def test_photo_lifecycle_publish_replace_remove_and_recipe_delete(
    client, database, headers, photos, recipe
):
    original, details = recipe
    recipe_id = original["id"]
    path = f"/api/recipes/{recipe_id}"
    assert original["photo_url"] is original["thumbnail_url"] is None
    assert_error(client.get(path + "/photo"), 404, "PHOTO_NOT_FOUND")
    response = upload(client, recipe_id, 1, headers)
    assert response.status_code == 200, response.text
    uploaded = response.json()
    assert uploaded["version"] == 2 and uploaded["status"] == "DRAFT"
    assert "photo_key" not in uploaded
    assert uploaded["photo_url"] and uploaded["thumbnail_url"]
    first_key = photo_key(database, recipe_id)
    assert first_key not in response.text
    assert_pair(photos, first_key)
    assert_jpeg(client.get(uploaded["photo_url"]), (800, 400))
    assert_jpeg(client.get(uploaded["thumbnail_url"]), (480, 240))
    assert client.get(f"/uploads/{first_key}.jpg").status_code == 404
    assert client.get(f"/static/{first_key}.jpg").status_code == 404
    for field in ["title", "description", "ingredients", "steps", "tags", "category", "author"]:
        assert uploaded[field] == original[field]
    published = client.post(path + "/publish", json={"version": 2}, headers=headers)
    assert published.status_code == 200, published.text
    assert photo_key(database, recipe_id) == first_key
    saved_cookie = client.cookies.get("recipe_session")
    client.cookies.clear()
    assert_jpeg(client.get(published.json()["photo_url"]), (800, 400))
    assert_jpeg(client.get(published.json()["thumbnail_url"]), (480, 240))
    summary = client.get("/api/recipes").json()["items"][0]
    assert summary["photo_url"] == published.json()["photo_url"]
    client.cookies.set("recipe_session", saved_cookie)
    replaced = upload(client, recipe_id, 3, headers, image_bytes(color="blue"))
    assert replaced.status_code == 200, replaced.text
    assert replaced.json()["status"] == "DRAFT" and replaced.json()["version"] == 4
    assert replaced.json()["published_at"] == published.json()["published_at"]
    second_key = photo_key(database, recipe_id)
    assert second_key != first_key
    assert_pair(photos, first_key, exists=False)
    assert_pair(photos, second_key)
    # Ordinary aggregate edits must preserve the photo as well.
    edited = client.put(
        path, json={**details, "title": "Змінена назва", "version": 4}, headers=headers
    )
    assert edited.status_code == 200 and edited.json()["photo_url"]
    assert photo_key(database, recipe_id) == second_key
    assert client.post(path + "/publish", json={"version": 5}, headers=headers).status_code == 200
    removed = client.delete(path + "/photo?version=6", headers=headers)
    assert removed.status_code == 200, removed.text
    assert removed.json()["version"] == 7 and removed.json()["status"] == "DRAFT"
    assert removed.json()["photo_url"] is removed.json()["thumbnail_url"] is None
    assert photo_key(database, recipe_id) is None
    assert_pair(photos, second_key, exists=False)
    assert_error(client.get(path + "/photo"), 404, "PHOTO_NOT_FOUND")
    assert_error(client.get(path + "/photo?thumbnail=true"), 404, "PHOTO_NOT_FOUND")
    repeated = client.delete(path + "/photo?version=7", headers=headers)
    assert repeated.status_code == 200 and repeated.json() == removed.json()
    assert upload(client, recipe_id, 7, headers).status_code == 200
    last_key = photo_key(database, recipe_id)
    assert client.delete(path + "?version=8", headers=headers).status_code == 204
    assert_pair(photos, last_key, exists=False)
    assert_error(client.get(path + "/photo"), 404, "RECIPE_NOT_FOUND")


@pytest.mark.parametrize("role", ["USER", "ADMIN"])
@pytest.mark.parametrize("state", ["DRAFT", "PUBLISHED", "HIDDEN"])
def test_photo_visibility_and_owner_only_mutation(
    client, database, test_settings, headers, origin, photos, recipe, role, state
):
    original, _ = recipe
    recipe_id = original["id"]
    assert upload(client, recipe_id, 1, headers).status_code == 200
    if state in {"PUBLISHED", "HIDDEN"}:
        assert (
            client.post(
                f"/api/recipes/{recipe_id}/publish", json={"version": 2}, headers=headers
            ).status_code
            == 200
        )
    if state == "HIDDEN":
        database.execute(
            "UPDATE recipes SET status = 'HIDDEN', hide_reason = 'Перевірка', "
            "version = version + 1 WHERE id = %s",
            (recipe_id,),
        )
    before = client.get(f"/api/recipes/{recipe_id}").json()
    old_key = photo_key(database, recipe_id)
    with TestClient(create_app(test_settings)) as other:
        other.app.state.photos = photos
        assert (
            other.post(
                "/api/auth/register",
                json={
                    "email": "other@example.com",
                    "display_name": "Інший",
                    "password": "other-password",
                },
                headers=origin,
            ).status_code
            == 201
        )
        database.execute("UPDATE users SET role = %s WHERE email = 'other@example.com'", (role,))
        for suffix in ["", "?thumbnail=true"]:
            guest = other.get(f"/api/recipes/{recipe_id}/photo" + suffix)
            assert guest.status_code == (200 if state == "PUBLISHED" else 404)
            assert guest.headers["Cache-Control"] == "no-store"
        login = other.post(
            "/api/auth/login",
            json={"email": "other@example.com", "password": "other-password"},
            headers=origin,
        ).json()
        other_headers = {**origin, "X-CSRF-Token": login["csrf_token"]}
        visible = state == "PUBLISHED" or role == "ADMIN"
        for suffix in ["", "?thumbnail=true"]:
            response = other.get(f"/api/recipes/{recipe_id}/photo" + suffix)
            assert response.status_code == (200 if visible else 404)
            assert response.headers["Cache-Control"] == "no-store"
        assert upload(other, recipe_id, before["version"], other_headers).status_code == (
            403 if visible else 404
        )
        assert other.delete(
            f"/api/recipes/{recipe_id}/photo?version={before['version']}", headers=other_headers
        ).status_code == (403 if visible else 404)
    assert client.get(f"/api/recipes/{recipe_id}").json() == before
    assert photo_key(database, recipe_id) == old_key
    assert_pair(photos, old_key)
    assert len(list(photos.directory.iterdir())) == 2
    assert_jpeg(client.get(before["photo_url"]), (800, 400))
    if state == "HIDDEN":
        replaced = upload(client, recipe_id, before["version"], headers, image_bytes(color="blue"))
        assert replaced.status_code == 200
        assert replaced.json()["status"] == "HIDDEN"
        assert replaced.json()["hide_reason"] == "Перевірка"
        removed = client.delete(
            f"/api/recipes/{recipe_id}/photo?version={replaced.json()['version']}", headers=headers
        )
        assert removed.status_code == 200 and removed.json()["status"] == "HIDDEN"
        assert removed.json()["hide_reason"] == "Перевірка"


def test_photo_requests_require_origin_session_csrf_and_version(
    client, database, headers, origin, photos, recipe
):
    original, _ = recipe
    recipe_id = original["id"]
    assert upload(client, recipe_id, 1, headers).status_code == 200
    before = client.get(f"/api/recipes/{recipe_id}").json()
    old_key = photo_key(database, recipe_id)
    path = f"/api/recipes/{recipe_id}/photo"
    for method in ["PUT", "DELETE"]:
        kwargs = {"content": image_bytes()} if method == "PUT" else {}
        for extra_headers in [
            {},
            origin,
            {**headers, "X-CSRF-Token": "bad"},
            {**headers, "Origin": "https://other.example"},
        ]:
            response = client.request(
                method,
                path + "?version=2",
                headers={**extra_headers, "Content-Type": "image/png"},
                **kwargs,
            )
            assert response.status_code == 403
        for query in ["", "?version=0", "?version=-1", "?version=true", "?version=2147483648"]:
            assert (
                client.request(
                    method, path + query, headers={**headers, "Content-Type": "image/png"}, **kwargs
                ).status_code
                == 422
            )
        stale = client.request(
            method, path + "?version=1", headers={**headers, "Content-Type": "image/png"}, **kwargs
        )
        assert_error(stale, 409, "VERSION_CONFLICT")
    assert client.get(f"/api/recipes/{recipe_id}").json() == before
    assert photo_key(database, recipe_id) == old_key
    assert len(list(photos.directory.iterdir())) == 2
    client.cookies.clear()
    assert_error(upload(client, recipe_id, 2, headers), 401, "AUTH_REQUIRED")
    assert_error(client.delete(path + "?version=2", headers=headers), 401, "AUTH_REQUIRED")


@pytest.mark.parametrize(
    "format,content_type",
    [
        ("JPEG", "image/jpeg"),
        ("PNG", "image/png"),
        ("WEBP", "image/webp"),
        ("PNG", "application/octet-stream"),
    ],
)
def test_supported_formats_are_decoded_and_served_as_jpeg(
    client, headers, recipe, format, content_type
):
    original, _ = recipe
    response = upload(client, original["id"], 1, headers, image_bytes(format=format), content_type)
    assert response.status_code == 200, response.text
    assert_jpeg(client.get(response.json()["photo_url"]), (800, 400))
    assert_jpeg(client.get(response.json()["thumbnail_url"]), (480, 240))


def test_photo_orientation_downsampling_and_metadata_removal(client, headers, recipe):
    exif = Image.Exif()
    exif[274] = 6
    exif[315] = "Private camera owner"
    content = image_bytes("JPEG", (2400, 1200), exif=exif)
    response = upload(client, recipe[0]["id"], 1, headers, content, "image/jpeg")
    assert response.status_code == 200, response.text
    full = client.get(response.json()["photo_url"])
    assert_jpeg(full, (960, 1920))
    assert b"Private camera owner" not in full.content
    assert_jpeg(client.get(response.json()["thumbnail_url"]), (240, 480))


def test_all_recipe_transitions_preserve_photo_files_and_link(
    client, database, headers, photos, recipe, register_and_login
):
    original, details = recipe
    recipe_id = original["id"]
    database.execute(
        "UPDATE users SET role = 'ADMIN' WHERE id = %s", (register_and_login["user"]["id"],)
    )
    assert upload(client, recipe_id, 1, headers).status_code == 200
    key = photo_key(database, recipe_id)
    for path, body, expected_status in [
        (f"/api/recipes/{recipe_id}/publish", {"version": 2}, "PUBLISHED"),
        (f"/api/recipes/{recipe_id}/unpublish", {"version": 3}, "DRAFT"),
        (f"/api/recipes/{recipe_id}/publish", {"version": 4}, "PUBLISHED"),
        (f"/api/admin/recipes/{recipe_id}/hide", {"version": 5, "reason": "Причина"}, "HIDDEN"),
        (f"/api/admin/recipes/{recipe_id}/restore", {"version": 6}, "DRAFT"),
    ]:
        response = client.post(path, json=body, headers=headers)
        assert response.status_code == 200, response.text
        assert response.json()["status"] == expected_status
        assert response.json()["version"] == body["version"] + 1
        assert photo_key(database, recipe_id) == key
        assert_pair(photos, key)
        assert_jpeg(client.get(response.json()["photo_url"]), (800, 400))
    updated = client.put(
        f"/api/recipes/{recipe_id}", json={**details, "version": 7}, headers=headers
    )
    assert updated.status_code == 200 and updated.json()["version"] == 8
    assert photo_key(database, recipe_id) == key
    assert len(list(photos.directory.iterdir())) == 2


@pytest.mark.parametrize("bad_content", ["empty", "text", "truncated", "gif", "animated", "pixels"])
def test_invalid_images_do_not_change_existing_photo(
    client, database, headers, photos, recipe, bad_content
):
    recipe_id = recipe[0]["id"]
    assert upload(client, recipe_id, 1, headers).status_code == 200
    before = client.get(f"/api/recipes/{recipe_id}").json()
    key = photo_key(database, recipe_id)
    if bad_content == "empty":
        content = b""
    elif bad_content == "text":
        content = b"<svg><script>not an image</script></svg>"
    elif bad_content == "truncated":
        content = image_bytes("JPEG")[:100]
    elif bad_content == "gif":
        content = image_bytes("GIF")
    elif bad_content == "pixels":
        content = image_bytes(size=(4500, 4500))
        assert len(content) < MAX_PHOTO_BYTES
    else:
        with (
            Image.new("RGB", (10, 10), "red") as first,
            Image.new("RGB", (10, 10), "blue") as second,
        ):
            stream = BytesIO()
            first.save(stream, "PNG", save_all=True, append_images=[second], duration=50, loop=0)
            content = stream.getvalue()
    assert_error(upload(client, recipe_id, 2, headers, content), 422, "INVALID_PHOTO")
    assert client.get(f"/api/recipes/{recipe_id}").json() == before
    assert photo_key(database, recipe_id) == key
    assert_pair(photos, key)
    assert len(list(photos.directory.iterdir())) == 2


def test_unsupported_content_type_and_actual_upload_limit_including_chunked_body(
    client, headers, photos, recipe
):
    recipe_id = recipe[0]["id"]
    assert_error(
        upload(client, recipe_id, 1, headers, content_type="text/plain"),
        415,
        "PHOTO_FORMAT_REQUIRED",
    )
    assert_error(
        upload(client, recipe_id, 1, headers, b"x" * (MAX_PHOTO_BYTES + 1)), 413, "PHOTO_TOO_LARGE"
    )

    def chunks():
        for _ in range(6):
            yield b"x" * (1024 * 1024)

    request = client.build_request(
        "PUT",
        f"/api/recipes/{recipe_id}/photo?version=1",
        content=chunks(),
        headers={**headers, "Content-Type": "image/png"},
    )
    assert "Content-Length" not in request.headers
    assert_error(client.send(request), 413, "PHOTO_TOO_LARGE")
    # A valid chunked upload must still work; rejecting all unknown lengths is not sufficient.
    content = image_bytes()
    request = client.build_request(
        "PUT",
        f"/api/recipes/{recipe_id}/photo?version=1",
        content=iter([content[:20], content[20:]]),
        headers={**headers, "Content-Type": "image/png"},
    )
    assert "Content-Length" not in request.headers
    response = client.send(request)
    assert response.status_code == 200, response.text
    assert len(list(photos.directory.iterdir())) == 2


@pytest.mark.parametrize("winner", ["edit", "hide"])
def test_photo_written_before_lost_cas_is_removed_and_winning_change_survives(
    client, database, test_settings, headers, register_and_login, photos, recipe, winner
):
    original, details = recipe
    recipe_id = original["id"]
    assert upload(client, recipe_id, 1, headers).status_code == 200
    assert (
        client.post(
            f"/api/recipes/{recipe_id}/publish", json={"version": 2}, headers=headers
        ).status_code
        == 200
    )
    old_key = photo_key(database, recipe_id)
    actor = User(**register_and_login["user"])
    admin_id = database.execute(
        "INSERT INTO users (email, display_name, password_hash, role) "
        "VALUES ('admin@example.com', 'Admin', 'unused', 'ADMIN') "
        "RETURNING id"
    ).fetchone()["id"]
    admin = SqlUserRepository(database).find_by_id(admin_id)
    stored_keys = []

    class LosingWriter(PostgreSQLRecipeRepository):
        def save(self, aggregate, expected_version):
            # The upload has stored files and read version 3, but has not acquired its UPDATE lock.
            stored_keys.append(aggregate.photo_key)
            assert_pair(photos, aggregate.photo_key)
            with connect(test_settings) as second:
                second.execute("SET statement_timeout = '5s'")
                repository = PostgreSQLRecipeRepository(second)
                catalog = PostgreSQLCatalogRepository(second)
                if winner == "edit":
                    service = RecipeService(
                        repository, repository, catalog, second.transaction, photos
                    )
                    change = RecipeCreate.model_validate({**details, "title": "Актуальна зміна"})
                    service.update(recipe_id, actor, change.to_details(), 3)
                else:
                    service = ModerationService(
                        repository,
                        repository,
                        SqlUserRepository(second),
                        SqlSessionRepository(second),
                        catalog,
                        second.transaction,
                    )
                    service.hide(admin, recipe_id, 3, "Модерація виграла")
            return super().save(aggregate, expected_version)

    with connect(test_settings) as connection:
        repository = LosingWriter(connection)
        service = RecipeService(
            repository,
            repository,
            PostgreSQLCatalogRepository(connection),
            connection.transaction,
            photos,
        )
        with pytest.raises(VersionConflict):
            service.replace_photo(recipe_id, actor, 3, image_bytes(color="blue"))
    assert len(stored_keys) == 1 and stored_keys[0] != old_key
    assert_pair(photos, stored_keys[0], exists=False)
    assert_pair(photos, old_key)
    assert len(list(photos.directory.iterdir())) == 2
    current = client.get(f"/api/recipes/{recipe_id}").json()
    assert current["version"] == 4
    assert photo_key(database, recipe_id) == old_key
    if winner == "edit":
        assert current["title"] == "Актуальна зміна" and current["status"] == "DRAFT"
    else:
        assert current["status"] == "HIDDEN" and current["hide_reason"] == "Модерація виграла"
    for field in ["ingredients", "steps", "tags", "category", "author"]:
        assert current[field] == original[field]


def test_database_failure_after_photo_store_rolls_back_and_removes_new_files(
    client, database, test_settings, headers, photos, recipe, monkeypatch
):
    recipe_id = recipe[0]["id"]
    assert upload(client, recipe_id, 1, headers).status_code == 200
    before = client.get(f"/api/recipes/{recipe_id}").json()
    old_key = photo_key(database, recipe_id)
    saved = []
    original_store = photos.store

    def record_store(content):
        key = original_store(content)
        assert_pair(photos, key)
        saved.append(key)
        return key

    monkeypatch.setattr(photos, "store", record_store)
    database.execute(
        "CREATE FUNCTION reject_photo_step() RETURNS trigger LANGUAGE plpgsql "
        "AS $$ BEGIN RAISE EXCEPTION 'injected photo rollback'; END $$"
    )
    database.execute(
        "CREATE TRIGGER reject_photo_step BEFORE INSERT ON instruction_steps "
        "FOR EACH ROW EXECUTE FUNCTION reject_photo_step()"
    )
    try:
        with TestClient(create_app(test_settings), raise_server_exceptions=False) as failing:
            failing.app.state.photos = photos
            failing.cookies.update(client.cookies)
            response = upload(failing, recipe_id, 2, headers, image_bytes(color="blue"))
        assert_error(response, 500, "INTERNAL_ERROR")
        assert "injected" not in response.text
    finally:
        database.execute("DROP TRIGGER reject_photo_step ON instruction_steps")
        database.execute("DROP FUNCTION reject_photo_step()")
    assert len(saved) == 1
    assert_pair(photos, saved[0], exists=False)
    assert_pair(photos, old_key)
    assert photo_key(database, recipe_id) == old_key
    assert client.get(f"/api/recipes/{recipe_id}").json() == before
    assert_jpeg(client.get(before["photo_url"]), (800, 400))


@pytest.mark.parametrize("operation", ["replace", "delete_photo", "delete_recipe"])
def test_cleanup_failure_after_commit_does_not_fail_request_or_remove_current_photo(
    client, database, headers, photos, recipe, monkeypatch, caplog, operation
):
    recipe_id = recipe[0]["id"]
    assert upload(client, recipe_id, 1, headers).status_code == 200
    old_key = photo_key(database, recipe_id)
    original_delete = photos.delete

    def fail_old_delete(key):
        if key == old_key:
            raise PermissionError("injected old photo cleanup failure")
        original_delete(key)

    monkeypatch.setattr(photos, "delete", fail_old_delete)
    path = f"/api/recipes/{recipe_id}"
    if operation == "replace":
        response = upload(client, recipe_id, 2, headers, image_bytes(color="blue"))
        assert response.status_code == 200, response.text
        assert response.json()["version"] == 3
        current_key = photo_key(database, recipe_id)
        assert current_key != old_key
        assert_pair(photos, current_key)
        assert_jpeg(client.get(response.json()["photo_url"]), (800, 400))
        assert_jpeg(client.get(response.json()["thumbnail_url"]), (480, 240))
    elif operation == "delete_photo":
        response = client.delete(path + "/photo?version=2", headers=headers)
        assert response.status_code == 200, response.text
        assert response.json()["version"] == 3 and response.json()["photo_url"] is None
        assert photo_key(database, recipe_id) is None
        assert_error(client.get(path + "/photo"), 404, "PHOTO_NOT_FOUND")
    else:
        response = client.delete(path + "?version=2", headers=headers)
        assert response.status_code == 204, response.text
        assert_error(client.get(path + "/photo"), 404, "RECIPE_NOT_FOUND")
        assert (
            database.execute("SELECT id FROM recipes WHERE id = %s", (recipe_id,)).fetchone()
            is None
        )
    assert_pair(photos, old_key)
    assert "Photo cleanup deferred" in caplog.text
    assert "injected" not in response.text
