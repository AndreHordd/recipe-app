import os
import time
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from app.domain.enums import RecipeStatus
from app.domain.exceptions import (
    InvalidPhoto,
    PhotoNotFound,
    PhotoStorageUnavailable,
    PhotoTooLarge,
)
from app.domain.recipes import Recipe
from app.infrastructure import photos
from app.infrastructure.photos import LocalPhotoStorage, prepare_photo
from scripts.cleanup_photos import find_orphans


def picture(format="PNG", *, size=(120, 80), mode="RGB", **options):
    stream = BytesIO()
    Image.new(mode, size, (40, 120, 60, 0) if mode == "RGBA" else (40, 120, 60)).save(
        stream, format, **options
    )
    return stream.getvalue()


@pytest.mark.parametrize("format", ["JPEG", "PNG", "WEBP"])
def test_supported_formats_are_reencoded_as_jpeg(format):
    for data in prepare_photo(picture(format)):
        with Image.open(BytesIO(data)) as image:
            assert image.format == "JPEG" and image.mode == "RGB"
            assert image.getexif() == {}


def test_exif_orientation_is_applied_and_metadata_removed():
    exif = Image.Exif()
    exif[274] = 6
    exif[315] = "Private camera owner"
    full, _ = prepare_photo(picture("JPEG", exif=exif))
    with Image.open(BytesIO(full)) as result:
        assert result.size == (80, 120)
        assert not result.getexif()
        assert b"Private camera owner" not in full


def test_transparent_pixels_use_white_background_and_dimensions_are_limited():
    full, thumbnail = prepare_photo(picture(size=(3000, 1000), mode="RGBA"))
    with Image.open(BytesIO(full)) as image:
        assert image.size == (1920, 640)
        assert image.getpixel((0, 0)) == (255, 255, 255)
    with Image.open(BytesIO(thumbnail)) as image:
        assert image.size == (480, 160)


@pytest.mark.parametrize("data", [b"", b"<svg></svg>", b"<html>fake.jpg</html>", b"\xff\xd8broken"])
def test_invalid_files_are_rejected(data):
    with pytest.raises(InvalidPhoto):
        prepare_photo(data)


@pytest.mark.parametrize("format", ["PNG", "WEBP"])
def test_animated_images_are_rejected(format):
    data = picture(format, save_all=True, append_images=[Image.new("RGB", (120, 80), "red")])
    with pytest.raises(InvalidPhoto):
        prepare_photo(data)


def test_pixel_limit_is_checked_before_decoding(monkeypatch):
    data = picture(size=(11, 10))
    monkeypatch.setattr(photos, "MAX_PHOTO_PIXELS", 100)
    monkeypatch.setattr(Image.Image, "load", lambda *args: pytest.fail("Oversized image decoded"))
    with pytest.raises(InvalidPhoto):
        prepare_photo(data)


def test_byte_limit_is_checked_before_parsing():
    with pytest.raises(PhotoTooLarge):
        prepare_photo(b"x" * (photos.MAX_PHOTO_BYTES + 1))


def test_storage_uses_its_own_keys_and_missing_files_return_404(tmp_path):
    storage = LocalPhotoStorage(tmp_path / "uploads")
    key = storage.store(picture())
    assert len(key) == 32
    assert sorted(path.name for path in storage.directory.iterdir()) == [
        key + ".jpg",
        key + ".thumb.jpg",
    ]
    assert storage.read(key) != storage.read(key, thumbnail=True)
    storage.delete(key)
    assert not list(storage.directory.iterdir())
    with pytest.raises(PhotoNotFound):
        storage.read(key)
    for unsafe in ("../outside", "a" * 31, "A" * 32):
        with pytest.raises(ValueError):
            storage.read(unsafe)


def test_storage_failure_does_not_leave_half_of_a_photo(tmp_path, monkeypatch):
    storage = LocalPhotoStorage(tmp_path)
    original = Path.open

    def fail_thumbnail(path, mode="r", *args, **kwargs):
        if mode == "xb" and path.name.endswith(".thumb.jpg"):
            raise OSError("Simulated full disk")
        return original(path, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", fail_thumbnail)
    with pytest.raises(PhotoStorageUnavailable):
        storage.store(picture())
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("status", list(RecipeStatus))
def test_photo_edit_obeys_existing_moderation_states(status):
    recipe = Recipe(
        1,
        "Рецепт",
        status=status,
        hide_reason="Уточніть" if status == RecipeStatus.HIDDEN else None,
    )
    recipe.change_photo("a" * 32)
    assert recipe.photo_key == "a" * 32
    assert recipe.status == (RecipeStatus.DRAFT if status == RecipeStatus.PUBLISHED else status)
    if status == RecipeStatus.HIDDEN:
        assert recipe.hide_reason == "Уточніть"


def test_orphan_scan_keeps_live_recent_and_unrelated_files(tmp_path):
    storage = LocalPhotoStorage(tmp_path)
    live = storage.store(picture())
    old = storage.store(picture())
    recent = storage.store(picture())
    unrelated = tmp_path / "notes.txt"
    unrelated.write_text("Keep", encoding="utf-8")
    cutoff = time.time() - 24 * 3600
    for key in (live, old):
        for small in (False, True):
            os.utime(storage.path(key, thumbnail=small), (cutoff - 1, cutoff - 1))
    result = find_orphans(storage, {live}, older_than=cutoff)
    assert {path.name for path in result} == {old + ".jpg", old + ".thumb.jpg"}
    assert storage.path(recent).exists() and unrelated.exists()
