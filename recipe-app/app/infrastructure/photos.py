import logging
import re
import uuid
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from app.domain.contracts import IPhotoStorage
from app.domain.exceptions import (
    InvalidPhoto,
    PhotoNotFound,
    PhotoStorageUnavailable,
    PhotoTooLarge,
)

MAX_PHOTO_BYTES = 5 * 1024 * 1024
MAX_PHOTO_PIXELS = 20_000_000
logger = logging.getLogger(__name__)


def prepare_photo(content: bytes) -> tuple[bytes, bytes]:
    if len(content) > MAX_PHOTO_BYTES:
        raise PhotoTooLarge()
    try:
        with Image.open(BytesIO(content), formats=["JPEG", "PNG", "WEBP"]) as source:
            if (
                source.width * source.height > MAX_PHOTO_PIXELS
                or getattr(source, "n_frames", 1) != 1
            ):
                raise InvalidPhoto()
            source.verify()
        with Image.open(BytesIO(content), formats=["JPEG", "PNG", "WEBP"]) as source:
            source.load()
            oriented = ImageOps.exif_transpose(source)
            rgba = oriented.convert("RGBA")
            image = Image.new("RGB", rgba.size, "white")
            image.paste(rgba, mask=rgba.getchannel("A"))
            # New RGB pixels deliberately discard EXIF, comments and original metadata.
            image.thumbnail((1920, 1920), Image.Resampling.LANCZOS)
            full = BytesIO()
            image.save(full, "JPEG", quality=85, optimize=True)
            image.thumbnail((480, 480), Image.Resampling.LANCZOS)
            thumbnail = BytesIO()
            image.save(thumbnail, "JPEG", quality=80, optimize=True)
            return full.getvalue(), thumbnail.getvalue()
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError, Image.DecompressionBombError):
        raise InvalidPhoto() from None


class LocalPhotoStorage(IPhotoStorage):
    def __init__(self, directory: Path):
        self.directory = directory.resolve()

    def path(self, key: str, *, thumbnail: bool = False) -> Path:
        if not re.fullmatch(r"[a-f0-9]{32}", key):
            raise ValueError("Invalid photo key")
        path = self.directory / (key + (".thumb.jpg" if thumbnail else ".jpg"))
        if path.resolve().parent != self.directory:
            raise ValueError("Photo path leaves its storage directory")
        return path

    def store(self, content: bytes) -> str:
        full, thumbnail = prepare_photo(content)
        key = uuid.uuid4().hex
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            for small, data in [(False, full), (True, thumbnail)]:
                with self.path(key, thumbnail=small).open("xb") as stream:
                    stream.write(data)
        except OSError:
            try:
                self.delete(key)
            except OSError:
                logger.warning("Could not clean up an incomplete photo")
            raise PhotoStorageUnavailable() from None
        return key

    def read(self, key: str, *, thumbnail: bool = False) -> bytes:
        try:
            return self.path(key, thumbnail=thumbnail).read_bytes()
        except FileNotFoundError:
            raise PhotoNotFound() from None
        except OSError:
            raise PhotoStorageUnavailable() from None

    def delete(self, key: str) -> None:
        for small in (False, True):
            self.path(key, thumbnail=small).unlink(missing_ok=True)
