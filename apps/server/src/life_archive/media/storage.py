"""Exclusive private files, bounded reads and verification against immutable metadata."""

import hashlib
import os
import re
import stat
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path

from life_archive.media.models import Asset
from life_archive.settings import get_media_settings

MAX_UPLOAD_BYTES = 5 * 1024 * 1024


class MediaStorageError(Exception):
    """Always safe to display: never attach filesystem paths or underlying OS errors."""


@contextmanager
def _directory(root: Path | None, *, create: bool = False) -> Iterator[int]:
    directory = root if root is not None else get_media_settings().media_root
    try:
        if not directory.is_absolute():
            raise MediaStorageError("Private media storage is unavailable")
        if create:
            directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0))
    except OSError:
        raise MediaStorageError("Private media storage is unavailable") from None
    try:
        yield descriptor
    finally:
        os.close(descriptor)


def _key(value: object) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{32}", value) is None:
        raise MediaStorageError("Invalid private media metadata")
    return value


def write_original(storage_key: str, data: bytes, root: Path | None = None) -> None:
    """Keep any failed exclusive write for inspection; never replace existing originals."""
    key = _key(storage_key)
    if not 0 < len(data) <= MAX_UPLOAD_BYTES:
        raise MediaStorageError("Invalid original size")
    try:
        with _directory(root, create=True) as directory:
            descriptor = os.open(
                key,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0),
                0o600,
                dir_fd=directory,
            )
            with os.fdopen(descriptor, "wb") as file:
                os.fchmod(file.fileno(), 0o600)
                file.write(data)
                file.flush()
                os.fsync(file.fileno())
            os.fsync(directory)
    except OSError:
        raise MediaStorageError("Private media storage is unavailable") from None


def read_original(asset: Asset | Mapping[str, object], root: Path | None = None) -> bytes:
    def field(name: str) -> object:
        return asset[name] if isinstance(asset, Mapping) else getattr(asset, name)

    try:
        key, size, digest = _key(field("storage_key")), field("byte_size"), field("sha256")
        if (
            type(size) is not int
            or not 0 < size <= MAX_UPLOAD_BYTES
            or not isinstance(digest, str)
            or re.fullmatch(r"[0-9a-f]{64}", digest) is None
        ):
            raise MediaStorageError("Invalid private media metadata")
        with _directory(root) as directory:
            descriptor = os.open(
                key,
                os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0),
                dir_fd=directory,
            )
            with os.fdopen(descriptor, "rb") as file:
                info = os.fstat(file.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_size != size:
                    raise MediaStorageError("Private media integrity check failed")
                data = file.read(MAX_UPLOAD_BYTES + 1)
        if len(data) != size or hashlib.sha256(data).hexdigest() != digest:
            raise MediaStorageError("Private media integrity check failed")
        return data
    except (OSError, KeyError, AttributeError):
        raise MediaStorageError("Private media storage is unavailable") from None
