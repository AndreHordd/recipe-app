"""List old unreferenced photo files; delete only with --delete, with the app stopped."""

import argparse
import re
import time

from app.config import Settings
from app.infrastructure.database import connect
from app.infrastructure.photos import LocalPhotoStorage


def find_orphans(storage: LocalPhotoStorage, live_keys: set[str], *, older_than: float) -> list:
    if not storage.directory.is_dir():
        return []
    result = []
    for path in storage.directory.iterdir():
        match = re.fullmatch(r"([a-f0-9]{32})(\.thumb)?\.jpg", path.name)
        if not match or path.is_symlink() or not path.is_file():
            continue
        if match[1] not in live_keys and path.stat().st_mtime < older_than:
            # Re-check the resolved path before offering it for deletion.
            if path.resolve().parent == storage.directory:
                result.append(path)
    return sorted(result)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Прибирання старих фото без рецепта; сайт має бути зупинений"
    )
    parser.add_argument(
        "--delete", action="store_true", help="Видалити знайдені файли; типово тільки список"
    )
    arguments = parser.parse_args()
    settings = Settings()
    storage = LocalPhotoStorage(settings.uploads_dir)
    with connect(settings) as connection:
        keys = {
            row["photo_key"]
            for row in connection.execute(
                "SELECT photo_key FROM recipes WHERE photo_key IS NOT NULL"
            ).fetchall()
        }
    paths = find_orphans(storage, keys, older_than=time.time() - 24 * 3600)
    for path in paths:
        print(path.name)
        if arguments.delete:
            if path.resolve().parent != storage.directory or path.is_symlink():
                raise RuntimeError("Photo path changed; deletion refused")
            path.unlink()
    print(f"{'Видалено' if arguments.delete else 'Знайдено'} файлів: {len(paths)}")


if __name__ == "__main__":
    main()
