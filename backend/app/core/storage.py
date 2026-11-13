"""Uploaded files and the deletion journal, kept on disk under STORAGE_DIR.

Layout:  STORAGE_DIR/files/documents/<user>/<id>.<ext>      original uploads
         STORAGE_DIR/journal/deletions/<user>/<request>.json  write-once deletion requests
On the server STORAGE_DIR is /data/storage on the data disk; locally it is .local-storage/.
"""

import json
from pathlib import Path

from app.core.config import settings


def local_path(key, journal=False):
    """Absolute path for `key`, refusing anything that would escape the storage folder."""
    root = Path(settings().storage_dir).resolve() / ("journal" if journal else "files")
    path = (root / key).resolve()
    if not path.is_relative_to(root):
        raise ValueError("Unsafe storage key")
    return path


def put(key, data, journal=False, immutable=False):
    """Write a file. With `immutable`, never overwrite: returns False if it already exists."""
    path = local_path(key, journal)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb" if immutable else "wb") as f:
            f.write(data)
    except FileExistsError:
        return False
    return True


def get(key, journal=False):
    return local_path(key, journal).read_bytes()


def remove(key):
    local_path(key).unlink(missing_ok=True)


def journal_entries():
    """Every deletion request ever journaled (replayed by the worker)."""
    root = Path(settings().storage_dir) / "journal" / "deletions"
    for path in root.glob("*/*.json"):
        yield json.loads(path.read_text())
