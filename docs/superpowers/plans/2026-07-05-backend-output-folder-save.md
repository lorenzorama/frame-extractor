# Backend Save-to-Output-Folder Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Have the Celery worker write each finished job's result zip to a host output folder (bind-mounted, configured once), as `video_<batch-position>.zip`, opt-in per batch with an optional subfolder — independent of the browser.

**Architecture:** New nullable `Job` columns record the opt-in, subfolder, and 1-based batch position. `POST /jobs` sanitizes the subfolder and stamps those fields. In `process_job`, after a job reaches `done`, a best-effort step builds the same zip the `/zip` endpoint serves (via a shared helper) and writes it into `<output_dir>/<subfolder>/video_<index>.zip` without overwriting. The existing browser File System Access auto-save is left untouched.

**Tech Stack:** FastAPI + SQLModel + Alembic + Celery (Python 3.12), Postgres; Docker Compose bind mount; Next.js/React/TypeScript frontend.

## Global Constraints

- The existing **browser File System Access auto-save is kept as-is** — do not modify `frontend/lib/autosave.ts` or the write loop in `frontend/app/page.tsx`. The new backend save is a **separate, independent opt-in**.
- Backend runs in Docker; the worker writes only to the **mounted** in-container path `settings.output_dir` (default `/data/output`), which the host `OUTPUT_DIR` is bind-mounted onto. No arbitrary per-request host paths.
- **Naming:** `video_<index>.zip` where `<index>` = the job's 1-based position in its submission batch (`output_index`). Numbering is **per-batch**. **Failed jobs write nothing** (only `done` jobs save), so their number is a natural gap. **Never overwrite:** an existing `video_1.zip` → `video_1 (2).zip`, then `(3)`, …
- **Subfolder is sanitized server-side:** a single safe segment (`[A-Za-z0-9 _.-]`), never `.`/`..`/all-dots, no slashes/backslashes/absolute/null byte. Invalid → **422**. Empty/None → base dir.
- **Best-effort save:** any failure writing the zip is caught and logged/swallowed — it must never change a job's `done` outcome or crash the worker.
- Backend has a real pytest suite (run via `.venv/bin/python -m pytest` from `backend/`, SQLite). Frontend has no test runner (Node 20): `npm run build` + `npx eslint`. Read `frontend/AGENTS.md` before touching frontend code.

---

### Task 1: Schema — `Job` output columns + migration 0005 + config

**Files:**
- Modify: `backend/app/models.py` (Job class, after `transcript_source`)
- Modify: `backend/app/config.py` (add `output_dir`)
- Create: `backend/alembic/versions/0005_output_save.py`
- Test: `backend/tests/test_output_save.py` (new)

**Interfaces:**
- Produces: `Job.save_to_output: bool` (default False), `Job.output_subdir: Optional[str]`, `Job.output_index: Optional[int]`; `settings.output_dir: str` (default `"/data/output"`).

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_output_save.py`:

```python
from sqlmodel import SQLModel, Session, create_engine
from sqlmodel.pool import StaticPool

from app.models import Job


def _session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def test_job_output_fields_default_off():
    with _session() as session:
        job = Job(user_id=1, youtube_url="u")
        session.add(job)
        session.commit()
        session.refresh(job)
        assert job.save_to_output is False
        assert job.output_subdir is None
        assert job.output_index is None


def test_job_output_fields_settable():
    with _session() as session:
        job = Job(user_id=1, youtube_url="u", save_to_output=True, output_subdir="proj", output_index=3)
        session.add(job)
        session.commit()
        session.refresh(job)
        assert job.save_to_output is True
        assert job.output_subdir == "proj"
        assert job.output_index == 3
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_output_save.py -q`
Expected: FAIL (`TypeError`/`AttributeError` — `save_to_output` not a Job field yet).

- [ ] **Step 3: Add the model columns**

In `backend/app/models.py`, in `class Job`, immediately after the `transcript_source` line, add:

```python
    save_to_output: bool = Field(default=False)
    output_subdir: Optional[str] = None
    output_index: Optional[int] = None
```

- [ ] **Step 4: Add the config setting**

In `backend/app/config.py`, after the `data_dir` line, add:

```python
    output_dir: str = "/data/output"
```

- [ ] **Step 5: Create the migration**

Create `backend/alembic/versions/0005_output_save.py`:

```python
"""output save: save_to_output, output_subdir, output_index

Revision ID: 0005
Revises: 0004
"""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "job",
        sa.Column("save_to_output", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("job", sa.Column("output_subdir", sa.String(), nullable=True))
    op.add_column("job", sa.Column("output_index", sa.Integer(), nullable=True))


def downgrade():
    op.drop_column("job", "output_index")
    op.drop_column("job", "output_subdir")
    op.drop_column("job", "save_to_output")
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/test_output_save.py -q`
Expected: PASS (2 passed).

- [ ] **Step 7: Commit**

```bash
git add backend/app/models.py backend/app/config.py backend/alembic/versions/0005_output_save.py backend/tests/test_output_save.py
git commit -m "feat: add Job output-save columns, config, migration 0005"
```

---

### Task 2: Shared job-zip builder + refactor `/zip` endpoint

**Files:**
- Create: `backend/app/zipbuilder.py`
- Modify: `backend/app/routers/jobs.py` (`download_zip`, imports)
- Test: `backend/tests/test_output_save.py` (append)

**Interfaces:**
- Consumes: `Frame`, `TranscriptCue` from `app.models`.
- Produces: `build_job_zip_bytes(session: Session, job_id: int) -> bytes` — zip with `<timestamp>.jpg` per frame plus `transcript.txt` when cues exist.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_output_save.py`:

```python
import zipfile
import io
import os


def test_build_job_zip_bytes(tmp_path):
    from app.zipbuilder import build_job_zip_bytes
    from app.models import Frame, TranscriptCue

    with _session() as session:
        job = Job(user_id=1, youtube_url="u")
        session.add(job)
        session.commit()
        session.refresh(job)

        img = tmp_path / "f.jpg"
        img.write_bytes(b"jpegdata")
        session.add(Frame(job_id=job.id, timestamp_seconds=1.0, file_path=str(img)))
        session.add(TranscriptCue(job_id=job.id, start_seconds=1.0, end_seconds=2.0, text="hi"))
        session.commit()

        data = build_job_zip_bytes(session, job.id)

    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = set(zf.namelist())
        assert "1.0.jpg" in names
        assert "transcript.txt" in names
        assert zf.read("transcript.txt").decode() == "[0:01] hi"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_output_save.py::test_build_job_zip_bytes -q`
Expected: FAIL (`ModuleNotFoundError: app.zipbuilder`).

- [ ] **Step 3: Create the builder module**

Create `backend/app/zipbuilder.py`:

```python
import io
import zipfile

from sqlmodel import Session, select

from app.models import Frame, TranscriptCue


def _fmt(sec: float) -> str:
    total = int(sec)
    return f"{total // 60}:{total % 60:02d}"


def build_job_zip_bytes(session: Session, job_id: int) -> bytes:
    """Build a job's result zip: one <timestamp>.jpg per frame, plus a
    transcript.txt when the job has transcript cues. Returns the zip bytes."""
    frames = session.exec(
        select(Frame).where(Frame.job_id == job_id).order_by(Frame.timestamp_seconds)
    ).all()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        for frame in frames:
            zf.write(frame.file_path, arcname=f"{frame.timestamp_seconds}.jpg")

    cues = session.exec(
        select(TranscriptCue).where(TranscriptCue.job_id == job_id).order_by(TranscriptCue.start_seconds)
    ).all()
    if cues:
        transcript_text = "\n".join(f"[{_fmt(c.start_seconds)}] {c.text}" for c in cues)
        with zipfile.ZipFile(buffer, "a") as zf:
            zf.writestr("transcript.txt", transcript_text)

    buffer.seek(0)
    return buffer.getvalue()
```

- [ ] **Step 4: Refactor the `/zip` endpoint to use it**

In `backend/app/routers/jobs.py`, replace the entire `download_zip` function body (the `@router.get("/{job_id}/zip")` handler, currently lines ~129-157) with:

```python
@router.get("/{job_id}/zip")
def download_zip(job_id: int, session: Session = Depends(get_session), user: User = Depends(get_current_user)):
    _get_owned_job(job_id, session, user)
    data = build_job_zip_bytes(session, job_id)
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename=job_{job_id}_frames.zip"},
    )
```

Then update imports at the top of `backend/app/routers/jobs.py`:
- Remove `import zipfile` (no longer used in this file).
- Add `from app.zipbuilder import build_job_zip_bytes`.
- Keep `import io` (still used for `io.BytesIO`).

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && .venv/bin/python -m pytest tests/test_output_save.py tests/test_frames_api.py -q`
Expected: PASS (the new builder test plus the existing `/zip` endpoint tests still green — proving the refactor kept behavior).

- [ ] **Step 6: Commit**

```bash
git add backend/app/zipbuilder.py backend/app/routers/jobs.py backend/tests/test_output_save.py
git commit -m "refactor: extract shared build_job_zip_bytes, reuse in /zip endpoint"
```

---

### Task 3: Output-save module — sanitize + collision-safe write

**Files:**
- Create: `backend/app/output_save.py`
- Test: `backend/tests/test_output_save.py` (append)

**Interfaces:**
- Consumes: `build_job_zip_bytes` from `app.zipbuilder` (used by `maybe_save_output` in Task 5; imported here).
- Produces:
  - `class InvalidSubdir(ValueError)`
  - `sanitize_output_subdir(raw: str | None) -> str` (returns `""` for base dir; raises `InvalidSubdir`)
  - `resolve_output_path(base_dir: str, subdir: str, index: int) -> str` (creates dir, returns non-colliding path)
  - `save_job_zip(base_dir: str, subdir: str, index: int, data: bytes) -> str` (writes file, returns path)

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_output_save.py`:

```python
import pytest


def test_sanitize_output_subdir_ok():
    from app.output_save import sanitize_output_subdir
    assert sanitize_output_subdir(None) == ""
    assert sanitize_output_subdir("") == ""
    assert sanitize_output_subdir("   ") == ""
    assert sanitize_output_subdir("my-project") == "my-project"
    assert sanitize_output_subdir("Batch_01") == "Batch_01"
    assert sanitize_output_subdir(" spaced name ") == "spaced name"


@pytest.mark.parametrize("bad", ["..", ".", "...", "/abs", "\\abs", "a/b", "a\\b", "x\x00y", "a*b", "a:b"])
def test_sanitize_output_subdir_rejects(bad):
    from app.output_save import sanitize_output_subdir, InvalidSubdir
    with pytest.raises(InvalidSubdir):
        sanitize_output_subdir(bad)


def test_save_job_zip_no_overwrite(tmp_path):
    from app.output_save import save_job_zip
    p1 = save_job_zip(str(tmp_path), "sub", 2, b"one")
    p2 = save_job_zip(str(tmp_path), "sub", 2, b"two")
    p3 = save_job_zip(str(tmp_path), "sub", 2, b"three")
    assert os.path.basename(p1) == "video_2.zip"
    assert os.path.basename(p2) == "video_2 (2).zip"
    assert os.path.basename(p3) == "video_2 (3).zip"
    assert os.path.isdir(os.path.join(str(tmp_path), "sub"))
    with open(p1, "rb") as f:
        assert f.read() == b"one"


def test_save_job_zip_base_dir_when_no_subdir(tmp_path):
    from app.output_save import save_job_zip
    p = save_job_zip(str(tmp_path), "", 1, b"x")
    assert p == os.path.join(str(tmp_path), "video_1.zip")


def test_maybe_save_output_writes_for_done_optin(tmp_path):
    from app.output_save import maybe_save_output
    from app.models import Frame

    with _session() as session:
        job = Job(user_id=1, youtube_url="u", status="done",
                  save_to_output=True, output_subdir="sub", output_index=1)
        session.add(job)
        session.commit()
        session.refresh(job)
        img = tmp_path / "f.jpg"
        img.write_bytes(b"jpeg")
        session.add(Frame(job_id=job.id, timestamp_seconds=0.0, file_path=str(img)))
        session.commit()

        out = tmp_path / "out"
        path = maybe_save_output(session, job, str(out))

    assert path is not None
    assert os.path.basename(path) == "video_1.zip"
    assert os.path.isfile(os.path.join(str(out), "sub", "video_1.zip"))


def test_maybe_save_output_noop_when_optout(tmp_path):
    from app.output_save import maybe_save_output
    with _session() as session:
        job = Job(user_id=1, youtube_url="u", status="done", save_to_output=False)
        session.add(job)
        session.commit()
        session.refresh(job)
        out = tmp_path / "out"
        assert maybe_save_output(session, job, str(out)) is None
    assert not (tmp_path / "out").exists()
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd backend && .venv/bin/python -m pytest tests/test_output_save.py -k "sanitize or save_job_zip or maybe_save_output" -q`
Expected: FAIL (`ModuleNotFoundError: app.output_save`).

- [ ] **Step 3: Create the module**

Create `backend/app/output_save.py`:

```python
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
```

- [ ] **Step 4: Run to verify they pass**

Run: `cd backend && .venv/bin/python -m pytest tests/test_output_save.py -q`
Expected: PASS (all output-save tests, including `maybe_save_output`).

- [ ] **Step 5: Commit**

```bash
git add backend/app/output_save.py backend/tests/test_output_save.py
git commit -m "feat: output_save module (sanitize subdir, collision-safe write, maybe_save_output)"
```

---

### Task 4: API — request fields + bulk-create wiring

**Files:**
- Modify: `backend/app/schemas.py` (`JobCreateRequest`)
- Modify: `backend/app/routers/jobs.py` (`create_jobs`, imports)
- Test: `backend/tests/test_jobs_api.py` (append)

**Interfaces:**
- Consumes: `sanitize_output_subdir`, `InvalidSubdir` from `app.output_save`.
- Produces: `POST /jobs` accepts `save_to_output: bool = False`, `output_subdir: str | None = None`; stamps `save_to_output` / `output_subdir` / `output_index` (1-based) on each created job.

- [ ] **Step 1: Write the failing tests**

Append these tests to `backend/tests/test_jobs_api.py`. They use the file's existing `client` fixture and its `signup_and_auth_headers(client)` helper, and patch `app.routers.jobs.dispatch_next` exactly like the other create-jobs tests in that file (both `patch` and `signup_and_auth_headers` are already imported/defined there):

```python
@patch("app.routers.jobs.dispatch_next")
def test_create_jobs_with_output_save(mock_dispatch, client):
    headers = signup_and_auth_headers(client)
    resp = client.post(
        "/jobs",
        json={"youtube_urls": ["a", "b"], "interval_seconds": 5,
              "save_to_output": True, "output_subdir": "proj"},
        headers=headers,
    )
    assert resp.status_code == 201
    jobs = resp.json()
    assert [j["output_index"] for j in jobs] == [1, 2]
    assert all(j["save_to_output"] is True for j in jobs)
    assert all(j["output_subdir"] == "proj" for j in jobs)


@patch("app.routers.jobs.dispatch_next")
def test_create_jobs_output_save_off_by_default(mock_dispatch, client):
    headers = signup_and_auth_headers(client)
    resp = client.post("/jobs", json={"youtube_urls": ["a"], "interval_seconds": 5}, headers=headers)
    assert resp.status_code == 201
    job = resp.json()[0]
    assert job["save_to_output"] is False
    assert job["output_index"] is None
    assert job["output_subdir"] is None


@patch("app.routers.jobs.dispatch_next")
def test_create_jobs_rejects_bad_subdir(mock_dispatch, client):
    headers = signup_and_auth_headers(client)
    resp = client.post(
        "/jobs",
        json={"youtube_urls": ["a"], "interval_seconds": 5,
              "save_to_output": True, "output_subdir": ".."},
        headers=headers,
    )
    assert resp.status_code == 422
```

Note: the assertions read `output_index` / `save_to_output` / `output_subdir` from the response, so `JobResponse` must expose them — add the three fields to `JobResponse` in `backend/app/schemas.py` (see Step 3).

- [ ] **Step 2: Run to verify they fail**

Run: `cd backend && .venv/bin/python -m pytest tests/test_jobs_api.py -k output -q`
Expected: FAIL (fields not accepted/returned yet).

- [ ] **Step 3: Add the schema fields**

In `backend/app/schemas.py`:

In `JobCreateRequest`, after `manual_timestamps`, add:

```python
    save_to_output: bool = False
    output_subdir: Optional[str] = None
```

In `JobResponse`, add these three fields (so tests and the frontend can read them back):

```python
    save_to_output: bool
    output_subdir: Optional[str]
    output_index: Optional[int]
```

(`Optional` is already imported in `schemas.py`; if not, add `from typing import Optional`.)

- [ ] **Step 4: Wire bulk create**

In `backend/app/routers/jobs.py`:

Add to the imports: `from app.output_save import sanitize_output_subdir, InvalidSubdir`.

In `create_jobs`, after the existing `interval_seconds`/`manual_timestamps` validation (the line that raises "Provide interval_seconds and/or manual_timestamps") and before `jobs = []`, add:

```python
    if payload.save_to_output:
        try:
            output_subdir = sanitize_output_subdir(payload.output_subdir)
        except InvalidSubdir as exc:
            raise HTTPException(status_code=422, detail=str(exc))
    else:
        output_subdir = None
```

Then change the job-creation loop from `for url in urls:` to `for i, url in enumerate(urls):` and add the three fields to the `Job(...)` constructor:

```python
    jobs = []
    for i, url in enumerate(urls):
        job = Job(
            user_id=user.id,
            youtube_url=url,
            interval_seconds=payload.interval_seconds,
            manual_timestamps=payload.manual_timestamps,
            status=JobStatus.waiting,
            save_to_output=payload.save_to_output,
            output_subdir=output_subdir if payload.save_to_output else None,
            output_index=(i + 1) if payload.save_to_output else None,
        )
        session.add(job)
        jobs.append(job)
```

- [ ] **Step 5: Run to verify they pass**

Run: `cd backend && .venv/bin/python -m pytest tests/test_jobs_api.py -q`
Expected: PASS (new output tests plus all existing jobs-API tests).

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas.py backend/app/routers/jobs.py backend/tests/test_jobs_api.py
git commit -m "feat: accept save_to_output + output_subdir on POST /jobs, stamp per-job index"
```

---

### Task 5: Worker — write the zip when a job finishes

**Files:**
- Modify: `backend/app/tasks.py` (`process_job`, imports)

**Interfaces:**
- Consumes: `maybe_save_output` from `app.output_save` (defined and unit-tested in Task 3); `settings.output_dir`.

This task wires the already-tested `maybe_save_output` into the worker's completion path. The function's behavior is covered by Task 3's unit tests; the worker wiring itself (a single call site inside `process_job`, which performs a real download) is verified by the full suite staying green here and by the manual walkthrough in Task 8.

- [ ] **Step 1: Wire the save into `process_job`**

In `backend/app/tasks.py`:

Add to imports: `from app.output_save import maybe_save_output`.

In `process_job`, find the block that sets the job done (inside the inner `try`):

```python
                job.status = JobStatus.done
                session.add(job)
                session.commit()
```

Immediately after that `session.commit()` (still inside the inner `try`, before the `except Exception as exc:`), add:

```python
                # Best-effort: write the result zip to the output folder if opted
                # in. maybe_save_output swallows its own errors and returns None,
                # so it can never flip the just-finished job to failed.
                maybe_save_output(session, job, settings.output_dir)
```

- [ ] **Step 2: Run the suite to verify nothing broke**

Run: `cd backend && .venv/bin/python -m pytest tests/test_output_save.py tests/test_tasks.py -q`
Expected: PASS (output-save tests plus the existing worker/task tests — the new call site did not break `process_job`).

- [ ] **Step 3: Commit**

```bash
git add backend/app/tasks.py
git commit -m "feat: worker writes finished job zip to output folder (best-effort)"
```

---

### Task 6: Docker mount + env + docs

**Files:**
- Modify: `docker-compose.yml` (worker `volumes`)
- Modify: `.env.example` (add `OUTPUT_DIR`) — create if absent
- Modify: `README.md` (document the output folder)
- Modify: `.gitignore` (ignore default `output/`)

**Interfaces:** none (infra/docs).

- [ ] **Step 1: Add the bind mount to the worker**

In `docker-compose.yml`, change the `worker` service `volumes` from:

```yaml
    volumes:
      - videodata:/data
```

to:

```yaml
    volumes:
      - videodata:/data
      - ${OUTPUT_DIR:-./output}:/data/output
```

(Leave the `api` service volumes unchanged — only the worker writes output.)

- [ ] **Step 2: Document the env var**

In `.env.example` (create it if it does not exist), add:

```dotenv
# Host folder where finished job zips are saved when "save to output folder" is
# checked. Bind-mounted into the worker at /data/output. Defaults to ./output.
OUTPUT_DIR=./output
```

- [ ] **Step 3: Ignore the default output dir**

Add a line to `.gitignore`:

```gitignore
/output/
```

- [ ] **Step 4: Document in the README**

In `README.md`, add a short subsection under the existing usage/configuration area:

```markdown
### Saving results to a folder (server-side)

Check **"Also save finished results to the server output folder"** on the job
form to have the worker write each finished job's zip to a host folder as
`video_<n>.zip` (numbered by the link's position in the batch). Set the host
folder with `OUTPUT_DIR` in `.env` (default `./output`); it is bind-mounted into
the worker. An optional **Subfolder** field writes into `OUTPUT_DIR/<subfolder>/`.
Existing files are never overwritten (`video_1 (2).zip`). This is independent of
the in-browser "auto-save to a folder" option.
```

- [ ] **Step 5: Validate compose interpolation**

Run: `docker compose config >/dev/null && echo OK`
Expected: `OK` (compose parses; `${OUTPUT_DIR:-./output}` resolves).

- [ ] **Step 6: Commit**

```bash
git add docker-compose.yml .env.example README.md .gitignore
git commit -m "chore: bind-mount OUTPUT_DIR into worker, document output folder"
```

---

### Task 7: Frontend — opt-in checkbox + subfolder field

**Files:**
- Modify: `frontend/lib/jobs.ts` (`CreateJobsInput`)
- Modify: `frontend/components/JobForm.tsx`

**Interfaces:**
- Consumes: nothing new. Sends `save_to_output` + `output_subdir` in the create payload.

**Context:** `CreateJobsInput` currently is `{ youtube_urls: string[]; interval_seconds?: number; manual_timestamps?: number[] }` and `createJobs` sends it as the JSON body. `JobForm` builds that object in `handleSubmit`. Do NOT touch the existing browser-auto-save checkbox/logic in `JobForm` or `page.tsx` — only add the new fields alongside.

- [ ] **Step 1: Extend the create input type**

In `frontend/lib/jobs.ts`, add two optional fields to `CreateJobsInput`:

```ts
export interface CreateJobsInput {
  youtube_urls: string[];
  interval_seconds?: number;
  manual_timestamps?: number[];
  save_to_output?: boolean;
  output_subdir?: string;
}
```

(No change to `createJobs` itself — it already serializes the whole input object.)

- [ ] **Step 2: Add the checkbox + subfolder state and UI to `JobForm`**

In `frontend/components/JobForm.tsx`:

Add two state hooks alongside the existing ones (near `const [autoSave, setAutoSave] = useState(false);`):

```tsx
  const [saveToOutput, setSaveToOutput] = useState(false);
  const [outputSubdir, setOutputSubdir] = useState("");
```

In `handleSubmit`, extend the `createJobs({ ... })` call to include the two new fields (add them to the existing object literal — do not remove the auto-save `dirHandle` handling):

```tsx
      const jobs = await createJobs({
        youtube_urls: urlList,
        interval_seconds: interval ? Number(interval) : undefined,
        manual_timestamps: manual.length ? manual : undefined,
        save_to_output: saveToOutput,
        output_subdir: saveToOutput && outputSubdir.trim() ? outputSubdir.trim() : undefined,
      });
```

Add this UI block immediately after the existing browser-auto-save `{supported ? (...) : (...)}` block and before the rights-acknowledgment checkbox:

```tsx
      <div className="flex flex-col gap-2">
        <label className="flex items-start gap-2.5 text-xs leading-relaxed text-muted">
          <input
            type="checkbox"
            checked={saveToOutput}
            onChange={(e) => setSaveToOutput(e.target.checked)}
            className="mt-0.5 h-4 w-4 shrink-0 accent-ink"
          />
          <span>
            Also save finished results to the server output folder (set by
            <code className="mx-1">OUTPUT_DIR</code>). Works without keeping this tab open.
          </span>
        </label>
        {saveToOutput && (
          <input
            placeholder="Subfolder (optional), e.g. my-project"
            value={outputSubdir}
            onChange={(e) => setOutputSubdir(e.target.value)}
            className={`${fieldClass} ml-7 w-auto`}
          />
        )}
      </div>
```

- [ ] **Step 3: Type-check with the build**

Run: `cd frontend && npm run build`
Expected: build succeeds.

- [ ] **Step 4: Lint**

Run: `cd frontend && npx eslint components/JobForm.tsx lib/jobs.ts`
Expected: no errors, no warnings.

- [ ] **Step 5: Commit**

```bash
git add frontend/lib/jobs.ts frontend/components/JobForm.tsx
git commit -m "feat: server-output-folder checkbox + subfolder field in job form"
```

---

### Task 8: Full verification (backend suite + migration + real save)

**Files:** none (verification only).

**Context:** Real YouTube downloads fail from this environment's IP, so a freshly-submitted job usually ends `failed`. To prove a real file lands on the host, exercise the worker save path against a job that already has frames — either a seeded `done` job or by directly calling `maybe_save_output` in-container against such a job with `settings.output_dir` pointed at the mounted folder.

- [ ] **Step 1: Full backend suite**

Run: `cd backend && .venv/bin/python -m pytest -q`
Expected: all pass (existing + new output-save tests).

- [ ] **Step 2: Migration applies on a real Postgres**

Run: `docker compose down -v && docker compose up -d --build` then, once up, `docker compose exec -T postgres psql -U postgres -d youtoframe -c "\d job"`.
Expected: the `job` table shows `save_to_output`, `output_subdir`, `output_index` columns (migrations `0001`→`0005` ran).

- [ ] **Step 3: Frontend build + lint**

Run: `cd frontend && npm run build && npx eslint components/JobForm.tsx lib/jobs.ts`
Expected: build succeeds, lint clean.

- [ ] **Step 4: Real save to the host folder**

With `OUTPUT_DIR` set (or default `./output`), pick or seed a `done` job that has frames, then in the worker container run a short Python snippet that opens a DB session, loads that job, and calls `maybe_save_output(session, job, settings.output_dir)`; confirm `video_<index>.zip` appears in `OUTPUT_DIR` (or its subfolder) on the host. Also verify a second call produces `video_<index> (2).zip`.
Expected: real zip file(s) present on the host, openable, containing the frames.

- [ ] **Step 5: Record the walkthrough result**

No commit. Note pass/fail per step in the progress ledger.
