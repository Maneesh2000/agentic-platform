"""document.read / document.parse — over uploads stored in Postgres.

Files arrive through the web client (POST /api/uploads writes bytes into
app_uploads) and are addressed here by id, so nothing depends on a shared
filesystem between the Next.js container and this one — which is also what
lets this work in Kubernetes without a ReadWriteMany volume.

TWO THINGS ARE LOAD-BEARING:

1. Parsing runs in `asyncio.to_thread`. pypdf and BeautifulSoup are
   synchronous and CPU-bound; run inline they would block the event loop of
   a LiveKit worker holding up to 25 live calls, and the gateway's
   `asyncio.wait_for` could not interrupt them because the coroutine never
   yields. The timeout is only real if the work is off the loop.
2. The size cap is checked BEFORE parsing, not after. A 200MB PDF must be
   refused, not decoded and then measured.

Output is UNTRUSTED content — callers wrap it with provenance.wrap_untrusted
before it nears a prompt.
"""

import asyncio
from pathlib import PurePosixPath

from ...config import settings
from ...vectordb import get_pool

_TEXT = (".txt", ".md")
_HTML = (".html", ".htm")


async def _fetch(attachment_id: str) -> tuple[str, bytes]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT filename, content FROM app_uploads WHERE id = $1::uuid", attachment_id
        )
    if row is None:
        raise FileNotFoundError(f"no such attachment: {attachment_id!r}")
    return row["filename"], bytes(row["content"])


def _extract(filename: str, content: bytes) -> str:
    """Synchronous and CPU-bound — always called via asyncio.to_thread."""
    suffix = PurePosixPath(filename).suffix.lower()
    if suffix in _TEXT:
        return content.decode("utf-8", errors="replace")
    if suffix == ".pdf":
        import io

        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(content))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    if suffix in _HTML:
        from bs4 import BeautifulSoup

        return BeautifulSoup(content.decode("utf-8", errors="replace"), "html.parser").get_text(" ")
    raise ValueError(f"unsupported document type {suffix!r} (txt, md, pdf, html)")


async def document_read(attachment_id: str) -> dict:
    """Metadata only — cheap existence check before committing to a parse."""
    filename, content = await _fetch(attachment_id)
    return {
        "name": filename,
        "bytes": len(content),
        "suffix": PurePosixPath(filename).suffix.lower(),
    }


async def document_parse(attachment_id: str) -> dict:
    filename, content = await _fetch(attachment_id)
    if len(content) > settings.max_document_bytes:
        raise ValueError(
            f"document is {len(content)} bytes, over the {settings.max_document_bytes} limit"
        )
    text = await asyncio.to_thread(_extract, filename, content)
    return {"name": filename, "text": text}
