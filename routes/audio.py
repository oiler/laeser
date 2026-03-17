import os
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

router = APIRouter()


def get_library_path() -> Path:
    return Path(os.environ.get("LAESER_LIBRARY_PATH", "library"))


@router.get("/audio/{file_path:path}")
def serve_audio(file_path: str):
    """
    Serve an audio file from the library directory.
    file_path is relative to the library root (e.g. "security-now/sn-1047.mp3").
    """
    full_path = get_library_path() / file_path

    # Security: resolve the path and ensure it stays within library
    try:
        resolved = full_path.resolve()
        library_resolved = get_library_path().resolve()
        resolved.relative_to(library_resolved)
    except ValueError:
        raise HTTPException(status_code=403, detail="Access denied")

    if not resolved.exists() or not resolved.is_file():
        raise HTTPException(status_code=404, detail="Audio file not found")

    return FileResponse(str(resolved), media_type="audio/mpeg")
