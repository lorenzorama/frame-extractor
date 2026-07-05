import os
import re

from sqlmodel import Session

from app.zipbuilder import build_job_zip_bytes

_SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9 _.\-]+$")


class InvalidSubdir(ValueError):
    """Raised when a requested output subfolder name is unsafe."""


def sanitize_output_subdir(raw):
    """Return a safe single-segment subfolder name, or "" for the base dir.
    Raises InvalidSubdir on traversal or otherwise unsafe input."""
    if raw is None:
        return ""
    s = raw.strip()
    if s == "":
        return ""
    if "\x00" in s:
        raise InvalidSubdir("Invalid subfolder name")
    if s.startswith("/") or s.startswith("\\"):
        raise InvalidSubdir("Subfolder must not be an absolute path")
    if "/" in s or "\\" in s:
        raise InvalidSubdir("Subfolder must be a single folder name")
    if set(s) <= {"."}:  # ".", "..", "..." → current/parent dir
        raise InvalidSubdir("Invalid subfolder name")
    if not _SAFE_SEGMENT.match(s):
        raise InvalidSubdir("Subfolder contains invalid characters")
    return s


def resolve_output_path(base_dir: str, subdir: str, index: int) -> str:
    """Create base_dir/subdir and return a non-colliding path for
    video_<index>.zip inside it: video_<index>.zip, else video_<index> (2).zip,
    (3).zip, … Never returns a path to an existing file."""
    target_dir = os.path.join(base_dir, subdir) if subdir else base_dir
    os.makedirs(target_dir, exist_ok=True)
    i = 1
    while True:
        name = f"video_{index}.zip" if i == 1 else f"video_{index} ({i}).zip"
        path = os.path.join(target_dir, name)
        if not os.path.exists(path):
            return path
        i += 1


def save_job_zip(base_dir: str, subdir: str, index: int, data: bytes) -> str:
    """Write zip bytes to a fresh video_<index>.zip under base_dir/subdir.
    Returns the written path."""
    path = resolve_output_path(base_dir, subdir, index)
    with open(path, "wb") as f:
        f.write(data)
    return path


def maybe_save_output(session: Session, job, base_dir: str):
    """Best-effort: if the job opted into output saving, build its zip and write
    it. Returns the written path, or None (opted out, or any failure — saving
    must never affect the job outcome)."""
    if not job.save_to_output or job.output_index is None:
        return None
    try:
        data = build_job_zip_bytes(session, job.id)
        return save_job_zip(base_dir, job.output_subdir or "", job.output_index, data)
    except Exception:
        return None
