"""Endpoint to download the Chrome extension as a ZIP file."""

import io
import zipfile
from pathlib import Path
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from ..models.database import User
from ..services.auth import get_current_user

router = APIRouter()

# Try multiple paths: Docker (/app/chrome-extension) and local dev (project root)
_base = Path(__file__).resolve().parent.parent.parent  # backend/
EXTENSION_DIR = _base / "chrome-extension"  # Docker: /app/chrome-extension
if not EXTENSION_DIR.exists():
    EXTENSION_DIR = _base.parent / "chrome-extension"  # Local dev: project_root/chrome-extension


@router.get("/version")
async def extension_version(
    current_user: User = Depends(get_current_user),
):
    """Версия расширения на сервере — попап сверяет со своей и предлагает
    обновиться (22.10.2026). Расширение ставят из zip, само оно не обновляется:
    до этого рекрутёры годами сидели на той версии, что когда-то скачали."""
    import json
    from fastapi import HTTPException
    try:
        manifest = json.loads((EXTENSION_DIR / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise HTTPException(404, "Extension files not found on server")
    return {"version": manifest.get("version"), "page": "/extension"}


@router.get("/download")
async def download_extension(
    current_user: User = Depends(get_current_user),
):
    """Package chrome-extension/ folder into a ZIP and return it."""
    if not EXTENSION_DIR.exists():
        from fastapi import HTTPException
        raise HTTPException(404, "Extension files not found on server")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in sorted(EXTENSION_DIR.rglob("*")):
            if file_path.is_file() and not file_path.name.startswith("."):
                arcname = f"enceladus-magic-button/{file_path.relative_to(EXTENSION_DIR)}"
                zf.write(file_path, arcname)

    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={
            "Content-Disposition": "attachment; filename=enceladus-magic-button.zip",
        },
    )
