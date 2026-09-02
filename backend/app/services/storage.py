from __future__ import annotations

import base64
import hashlib
import mimetypes
import shutil
from pathlib import Path
from urllib.parse import urlparse

import httpx

from app.config import get_settings
from app.schemas import StorageStatus


def file_data_url(path: str | None, max_bytes: int = 15 * 1024**2) -> str | None:
    if not path:
        return None
    source = Path(path)
    if not source.is_file() or source.stat().st_size > max_bytes:
        return None
    mime_type = mimetypes.guess_type(source.name)[0] or "application/octet-stream"
    encoded = base64.b64encode(source.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _extension_from_content_type(content_type: str, fallback: str) -> str:
    mapping = {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/webp": ".webp",
        "image/svg+xml": ".svg",
        "video/mp4": ".mp4",
        "video/webm": ".webm",
    }
    return mapping.get(content_type.split(";")[0].strip(), fallback)


async def persist_remote_media(url: str, kind: str, stem: str) -> tuple[Path, str, int]:
    settings = get_settings()
    target_dir = settings.media_dir / ("images" if kind == "image" else "videos")
    fallback = ".png" if kind == "image" else ".mp4"

    if url.startswith("data:"):
        header, encoded = url.split(",", 1)
        content_type = header.split(":", 1)[1].split(";", 1)[0]
        data = base64.b64decode(encoded)
        suffix = _extension_from_content_type(content_type, fallback)
    else:
        async with httpx.AsyncClient(timeout=300, follow_redirects=True) as client:
            response = await client.get(url)
        response.raise_for_status()
        data = response.content
        content_type = response.headers.get("content-type", "")
        suffix = _extension_from_content_type(
            content_type, Path(urlparse(url).path).suffix or fallback
        )

    digest = hashlib.sha256(data).hexdigest()
    path = target_dir / f"{stem}-{digest[:12]}{suffix}"
    if not path.exists():
        path.write_bytes(data)
    return path, digest, len(data)


def media_url(path: str | None) -> str | None:
    if not path:
        return None
    settings = get_settings()
    try:
        relative = Path(path).resolve().relative_to(settings.media_dir.resolve())
    except ValueError:
        return None
    return f"/media/{relative.as_posix()}"


def storage_status() -> StorageStatus:
    settings = get_settings()
    media_bytes = sum(
        path.stat().st_size for path in settings.media_dir.rglob("*") if path.is_file()
    )
    free_bytes = shutil.disk_usage(settings.data_dir).free
    warnings: list[str] = []
    if media_bytes >= settings.media_warning_bytes:
        warnings.append("媒体文件已超过 10GB")
    if free_bytes <= settings.disk_free_warning_bytes:
        warnings.append("磁盘剩余空间不足 5GB")
    return StorageStatus(
        media_bytes=media_bytes,
        free_bytes=free_bytes,
        warning="；".join(warnings) if warnings else None,
    )
