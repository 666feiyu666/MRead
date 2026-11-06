"""Upload validation and local asset storage.

Images are accepted only when their bytes really are PNG, JPEG, or WebP; articles must
be text-extractable PDF, TXT, or MD. Nothing is logged: not the bytes, not the text.
"""

from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass
from pathlib import Path

from . import config
from .schemas import new_id, utcnow


class UploadError(ValueError):
    """A user-facing problem with an uploaded file."""


@dataclass
class StoredAsset:
    kind: str
    mime: str
    filename: str
    sha256: str
    size: int
    text_content: str
    stored_path: str


def _sniff_image(data: bytes) -> str:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if len(data) >= 12 and data[0:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    raise UploadError("images must be PNG, JPEG, or WebP")


def _decode_text(data: bytes) -> str:
    for encoding in ("utf-8", "utf-16", "gb18030"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise UploadError("the text file is not readable as UTF-8, UTF-16, or GB18030")


def _extract_pdf(data: bytes) -> str:
    from pypdf import PdfReader

    try:
        reader = PdfReader(io.BytesIO(data))
        pages = [(page.extract_text() or "").strip() for page in reader.pages]
    except Exception as exc:  # noqa: BLE001 - surface any parser failure to the user
        raise UploadError(f"could not read this PDF: {exc}") from exc

    text = "\n\n".join(page for page in pages if page)
    if not text.strip():
        raise UploadError(
            "this PDF has no extractable text (it is probably a scan); paste the text instead"
        )
    return text


def store_upload(
    *,
    kind: str,
    filename: str,
    mime: str,
    data: bytes,
    pasted_text: str = "",
) -> StoredAsset:
    """Validate one upload and persist it. Returns metadata for the database row."""
    if not data and not pasted_text.strip():
        raise UploadError("the upload is empty")

    suffix = Path(filename or "").suffix.lower()

    if kind == "image":
        if len(data) > config.MAX_IMAGE_BYTES:
            raise UploadError("the image is larger than 20 MB")
        detected = _sniff_image(data)
        if mime and mime not in config.IMAGE_MIME:
            raise UploadError("images must be PNG, JPEG, or WebP")
        mime = detected
        text_content = ""
    elif kind in {"article", "note"}:
        if len(data) > config.MAX_ARTICLE_BYTES:
            raise UploadError("the article is larger than 10 MB")
        if pasted_text.strip():
            text_content = pasted_text
        elif suffix == ".pdf" or mime == "application/pdf":
            text_content = _extract_pdf(data)
        elif suffix in config.ARTICLE_SUFFIXES:
            text_content = _decode_text(data)
        else:
            raise UploadError("articles must be PDF, TXT, or MD, or pasted as text")
        mime = "text/plain"
    else:
        raise UploadError(f"unknown material kind: {kind}")

    blob = data if data else text_content.encode("utf-8")
    digest = hashlib.sha256(blob).hexdigest()
    config.ensure_dirs()

    if kind == "image":
        extension = config.IMAGE_MIME[mime]
        path = config.ASSET_DIR / f"{digest}.{extension}"
        if not path.exists():
            path.write_bytes(data)
        stored_path = str(path)
    else:
        path = config.ASSET_DIR / f"{digest}.txt"
        if not path.exists():
            path.write_text(text_content, encoding="utf-8")
        stored_path = str(path)

    return StoredAsset(
        kind=kind,
        mime=mime,
        filename=filename or f"{digest[:8]}",
        sha256=digest,
        size=len(blob),
        text_content=text_content,
        stored_path=stored_path,
    )


def asset_bytes(stored_path: str) -> bytes:
    path = Path(stored_path)
    if not path.is_file():
        raise UploadError("the stored file is missing from the asset directory")
    return path.read_bytes()


def insert_asset(conn, *, case_id: str, asset: StoredAsset, title: str, provenance: str) -> dict:
    asset_id = new_id("mat")
    conn.execute(
        """
        INSERT INTO assets (id, case_id, kind, title, provenance, filename, mime, sha256,
                            size, text_content, stored_path, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            asset_id,
            case_id,
            asset.kind,
            title or asset.filename,
            provenance,
            asset.filename,
            asset.mime,
            asset.sha256,
            asset.size,
            asset.text_content,
            asset.stored_path,
            utcnow(),
        ),
    )
    return {"id": asset_id}
