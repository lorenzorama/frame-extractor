# Whisper STT Fallback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When a video has no YouTube captions, transcribe its audio locally with faster-whisper (best-effort) so the existing transcript feature still works.

**Architecture:** The Celery worker, after extracting frames, falls back to Whisper only when no captions were found: it sets a new `transcribing` job status, extracts audio (ffmpeg → 16 kHz mono WAV), transcribes with a process-level faster-whisper singleton, then updates each `Frame.caption`, inserts `TranscriptCue` rows, and records `Job.transcript_language` + `Job.transcript_source`. Everything is best-effort — a failure or an over-cap duration leaves the job succeeding with frames and no transcript. The transcript data flows through the existing tables/API/UI.

**Tech Stack:** Python 3.12, FastAPI, SQLModel, Alembic, Celery, faster-whisper (CTranslate2, CPU int8), ffmpeg; Next.js frontend.

## Global Constraints

- Whisper is **best-effort**: any failure, or a duration over `whisper_max_duration_seconds`, leaves the job `done` with frames and no transcript (`transcript_language`/`transcript_source` `null`). Never fail the job. `session.rollback()` on any failure inside the Whisper block (mirrors the existing captions handling).
- Whisper runs **only when no YouTube captions were found** (parsed cues empty). Captions remain the first source.
- Defaults: model `base`, compute type `int8`, max duration `3600` seconds, enabled `true` (per spec).
- `transcript_source` is `"captions"` when captions produced cues, `"whisper"` when Whisper did, `null` when no transcript.
- Do NOT add a short Celery `time_limit`/`soft_time_limit` (a 30-min video can take ~15 min to transcribe).
- Backend suite must stay green (`cd backend && pytest -v`); frontend `npm run build`/`npm run lint` clean (the two `no-img-element` warnings on the gallery are expected/accepted).
- Tests must NOT require faster-whisper to be installed: the heavy `from faster_whisper import WhisperModel` import is lazy (inside `_get_model`), and tests mock `_get_model`/`transcribe_audio`/`extract_audio`.

---

## File Structure

```
backend/
  app/
    models.py            # MODIFY: JobStatus.transcribing, Job.transcript_source
    config.py             # MODIFY: whisper_* settings
    whisper.py             # CREATE: extract_audio, transcribe_audio (+ lazy model singleton)
    tasks.py                # MODIFY: set transcript_source in captions block; Whisper fallback
    schemas.py               # MODIFY: TranscriptResponse.source
    routers/jobs.py           # MODIFY: return job.transcript_source in transcript endpoint
  requirements.txt            # MODIFY: add faster-whisper
  Dockerfile                   # MODIFY: pre-download the whisper model at build
  alembic/versions/0003_*.py    # CREATE: transcribing enum value + transcript_source column
  tests/
    test_models_whisper.py       # CREATE
    test_whisper.py               # CREATE
    test_tasks.py                  # MODIFY: whisper fallback tests
    test_transcript_api.py          # MODIFY: source field
docker-compose.yml                   # MODIFY: lower worker concurrency
README.md                             # MODIFY: whisper notes
frontend/
  lib/jobs.ts                          # MODIFY: Transcript.source
  components/StatusBadge.tsx            # MODIFY: transcribing pill
  components/JobProgress.tsx             # MODIFY: "Transcribing audio…" label
  components/JobGallery.tsx               # MODIFY: "Auto-transcribed" indicator
```

---

## Task 1: Schema — `transcribing` status + `transcript_source`

**Files:**
- Modify: `backend/app/models.py`
- Create: `backend/alembic/versions/0003_whisper.py`
- Test: `backend/tests/test_models_whisper.py`

**Interfaces:**
- Produces: `JobStatus.transcribing` (`"transcribing"`) and `Job.transcript_source: Optional[str]`. Consumed by Tasks 3, 4.

- [ ] **Step 1: Update `backend/app/models.py`**

Add the enum value:

```python
class JobStatus(str, Enum):
    pending = "pending"
    downloading = "downloading"
    extracting = "extracting"
    transcribing = "transcribing"
    done = "done"
    failed = "failed"
```

Add the column to `Job` (next to `transcript_language`):

```python
    transcript_language: Optional[str] = None
    transcript_source: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
```

- [ ] **Step 2: Write the failing test**

```python
# backend/tests/test_models_whisper.py
from sqlmodel import SQLModel, Session, create_engine

from app.models import User, Job, JobStatus


def make_engine():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return engine


def test_transcribing_status_and_transcript_source_persist():
    engine = make_engine()
    with Session(engine) as session:
        user = User(email="a@example.com", hashed_password="x")
        session.add(user)
        session.commit()
        session.refresh(user)

        job = Job(user_id=user.id, youtube_url="https://youtube.com/watch?v=abc", interval_seconds=5)
        job.status = JobStatus.transcribing
        job.transcript_source = "whisper"
        session.add(job)
        session.commit()
        session.refresh(job)

        assert job.status == JobStatus.transcribing
        assert job.transcript_source == "whisper"
        assert JobStatus.transcribing.value == "transcribing"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd backend && source .venv/bin/activate && pytest tests/test_models_whisper.py -v`
Expected: FAIL with `AttributeError: transcribing` (before Step 1). After Step 1: PASS.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_models_whisper.py -v`
Expected: `1 passed`

- [ ] **Step 5: Write the migration `backend/alembic/versions/0003_whisper.py`**

Hand-write it (autogenerate does not reliably detect enum-value additions):

```python
"""whisper: transcribing status + transcript_source

Revision ID: 0003
Revises: 0002
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    # ALTER TYPE ... ADD VALUE cannot run inside a transaction block on some
    # Postgres/Alembic configs; run it in an autocommit block.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE jobstatus ADD VALUE IF NOT EXISTS 'transcribing'")
    op.add_column("job", sa.Column("transcript_source", sa.String(), nullable=True))


def downgrade():
    op.drop_column("job", "transcript_source")
    # NOTE: Postgres cannot easily DROP an enum value, so 'transcribing' is left
    # in the jobstatus type on downgrade (harmless).
```

Confirm `down_revision = "0002"` chains off the transcript migration.

- [ ] **Step 6: Run the full suite**

Run: `pytest -v`
Expected: all pass (SQLite tests build the schema from models, so they exercise the new enum member without running the Postgres-only migration).

- [ ] **Step 7: Commit**

```bash
git add backend/app/models.py backend/alembic/versions/0003_whisper.py backend/tests/test_models_whisper.py
git commit -m "feat: add transcribing status and transcript_source column"
```

---

## Task 2: Whisper module + config

**Files:**
- Modify: `backend/app/config.py`
- Create: `backend/app/whisper.py`
- Modify: `backend/requirements.txt`
- Test: `backend/tests/test_whisper.py`

**Interfaces:**
- Consumes: `_run` and `Cue` from `app/video.py`; `settings` from `app/config.py`.
- Produces: `extract_audio(video_path: str, dest_wav: str) -> None`; `transcribe_audio(wav_path: str) -> tuple[str | None, list[Cue]]`; `_get_model()` (lazy singleton). Consumed by Task 3.

- [ ] **Step 1: Add whisper settings to `backend/app/config.py`**

Add these fields inside `Settings` (after `cors_origins`):

```python
    cors_origins: list[str] = ["http://localhost:3000"]
    whisper_enabled: bool = True
    whisper_model: str = "base"
    whisper_max_duration_seconds: int = 3600
    whisper_compute_type: str = "int8"
```

- [ ] **Step 2: Add the dependency to `backend/requirements.txt`**

Append:

```
faster-whisper==1.0.3
```

(Note: the module imports `faster_whisper` lazily, so local tests do not require it installed. It is needed at Docker build/runtime — Task 6 bakes the model.)

- [ ] **Step 3: Write the failing tests**

```python
# backend/tests/test_whisper.py
from unittest.mock import patch, MagicMock

from app.video import Cue
from app.whisper import extract_audio, transcribe_audio


# extract_audio calls `_run` (which lives in app.video), so patch subprocess
# in app.video's namespace — that is where the call resolves.
@patch("app.video.subprocess.run")
def test_extract_audio_invokes_ffmpeg(mock_run):
    mock_run.return_value = MagicMock(returncode=0)
    extract_audio("/data/1/1/source.mp4", "/data/1/1/audio.wav")
    args = mock_run.call_args[0][0]
    assert "ffmpeg" in args
    assert "-ac" in args and "1" in args        # mono
    assert "-ar" in args and "16000" in args     # 16 kHz
    assert "-vn" in args                          # drop video
    assert "/data/1/1/audio.wav" in args


def test_transcribe_audio_maps_segments_to_cues(monkeypatch):
    seg1 = MagicMock(start=0.0, end=4.0, text=" Hello world ")
    seg2 = MagicMock(start=4.0, end=8.0, text="Second line")
    info = MagicMock(language="en")

    fake_model = MagicMock()
    fake_model.transcribe.return_value = ([seg1, seg2], info)
    monkeypatch.setattr("app.whisper._get_model", lambda: fake_model)

    language, cues = transcribe_audio("/data/1/1/audio.wav")
    assert language == "en"
    assert cues == [Cue(0.0, 4.0, "Hello world"), Cue(4.0, 8.0, "Second line")]
    fake_model.transcribe.assert_called_once_with("/data/1/1/audio.wav")
```

- [ ] **Step 4: Run test to verify it fails**

Run: `pytest tests/test_whisper.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.whisper'`.

- [ ] **Step 5: Create `backend/app/whisper.py`**

```python
from app.config import settings
from app.video import Cue, _run

# Loaded lazily, once per worker process. The faster_whisper import is heavy
# and is deferred so the module (and its non-model functions) import without
# the package present, and tests can mock _get_model.
_model = None


def _get_model():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel

        _model = WhisperModel(settings.whisper_model, compute_type=settings.whisper_compute_type)
    return _model


def extract_audio(video_path: str, dest_wav: str) -> None:
    _run(
        [
            "ffmpeg", "-y",
            "-i", video_path,
            "-vn",
            "-ac", "1",
            "-ar", "16000",
            dest_wav,
        ]
    )


def transcribe_audio(wav_path: str) -> tuple[str | None, list[Cue]]:
    model = _get_model()
    segments, info = model.transcribe(wav_path)
    cues = [Cue(seg.start, seg.end, (seg.text or "").strip()) for seg in segments]
    return getattr(info, "language", None), cues
```

- [ ] **Step 6: Run test to verify it passes**

Run: `pytest tests/test_whisper.py -v`
Expected: `2 passed`

- [ ] **Step 7: Run the full suite**

Run: `pytest -v`
Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add backend/app/config.py backend/app/whisper.py backend/requirements.txt backend/tests/test_whisper.py
git commit -m "feat: add whisper module (audio extraction + transcription) and config"
```

---

## Task 3: Worker integration — Whisper fallback

**Files:**
- Modify: `backend/app/tasks.py`
- Test: `backend/tests/test_tasks.py`

**Interfaces:**
- Consumes: `extract_audio`, `transcribe_audio` from `app/whisper.py`; `JobStatus.transcribing`, `Job.transcript_source` from Task 1; existing `Cue`/`caption_for_timestamp`/`TranscriptCue`/`Frame`.
- Produces: the worker fallback behavior; `transcript_source` set in both the captions and whisper paths.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_tasks.py`:

```python
def _base_patches(tasks, monkeypatch, tmp_path, engine, duration=10.0):
    monkeypatch.setattr(tasks, "engine", engine)
    monkeypatch.setattr("app.config.settings.data_dir", str(tmp_path))
    monkeypatch.setattr(tasks, "get_video_info", lambda url: {"duration": duration})
    monkeypatch.setattr(tasks, "download_video", lambda url, path: None)
    monkeypatch.setattr(tasks, "extract_frame", lambda v, ts, dest: None)


def test_whisper_fallback_when_no_captions(tmp_path, monkeypatch):
    from app import tasks
    from app.models import TranscriptCue
    from app.video import Cue

    engine, session = make_session()
    _base_patches(tasks, monkeypatch, tmp_path, engine, duration=10.0)
    monkeypatch.setattr(tasks, "pick_caption_language", lambda info: None)   # no captions
    monkeypatch.setattr("app.config.settings.whisper_enabled", True)
    monkeypatch.setattr("app.config.settings.whisper_max_duration_seconds", 3600)
    monkeypatch.setattr(tasks, "extract_audio", lambda src, dest: None)
    monkeypatch.setattr(tasks, "transcribe_audio", lambda p: ("en", [Cue(0.0, 6.0, "hello"), Cue(6.0, 10.0, "world")]))

    user = User(email="a@example.com", hashed_password="x")
    session.add(user); session.commit(); session.refresh(user)
    job = Job(user_id=user.id, youtube_url="https://youtube.com/watch?v=abc", interval_seconds=5.0)
    session.add(job); session.commit(); session.refresh(job)

    tasks.process_job(job.id)

    session.refresh(job)
    assert job.status == JobStatus.done
    assert job.transcript_language == "en"
    assert job.transcript_source == "whisper"
    assert len(session.query(TranscriptCue).filter(TranscriptCue.job_id == job.id).all()) == 2
    frames = session.query(Frame).filter(Frame.job_id == job.id).order_by(Frame.timestamp_seconds).all()
    assert frames[0].caption == "hello"
    assert frames[-1].caption == "world"


def test_whisper_skipped_when_captions_present(tmp_path, monkeypatch):
    from app import tasks
    from app.video import Cue
    from unittest.mock import MagicMock

    engine, session = make_session()
    _base_patches(tasks, monkeypatch, tmp_path, engine, duration=10.0)
    monkeypatch.setattr(tasks, "pick_caption_language", lambda info: "en")
    monkeypatch.setattr(tasks, "download_captions", lambda url, lang, stem: f"{stem}.{lang}.vtt")
    real_exists = os.path.exists
    monkeypatch.setattr(tasks.os.path, "exists", lambda p: True if str(p).endswith(".vtt") else real_exists(p))
    monkeypatch.setattr(tasks, "parse_vtt", lambda path: [Cue(0.0, 6.0, "caption line")])
    transcribe = MagicMock()
    monkeypatch.setattr(tasks, "transcribe_audio", transcribe)

    user = User(email="a@example.com", hashed_password="x")
    session.add(user); session.commit(); session.refresh(user)
    job = Job(user_id=user.id, youtube_url="https://youtube.com/watch?v=abc", interval_seconds=5.0)
    session.add(job); session.commit(); session.refresh(job)

    tasks.process_job(job.id)

    session.refresh(job)
    assert job.status == JobStatus.done
    assert job.transcript_source == "captions"
    transcribe.assert_not_called()


def test_whisper_skipped_when_over_duration_cap(tmp_path, monkeypatch):
    from app import tasks
    from unittest.mock import MagicMock

    engine, session = make_session()
    _base_patches(tasks, monkeypatch, tmp_path, engine, duration=5000.0)  # over 3600 cap
    monkeypatch.setattr(tasks, "pick_caption_language", lambda info: None)
    monkeypatch.setattr("app.config.settings.whisper_enabled", True)
    monkeypatch.setattr("app.config.settings.whisper_max_duration_seconds", 3600)
    transcribe = MagicMock()
    monkeypatch.setattr(tasks, "transcribe_audio", transcribe)

    user = User(email="a@example.com", hashed_password="x")
    session.add(user); session.commit(); session.refresh(user)
    job = Job(user_id=user.id, youtube_url="https://youtube.com/watch?v=abc", interval_seconds=5.0)
    session.add(job); session.commit(); session.refresh(job)

    tasks.process_job(job.id)

    session.refresh(job)
    assert job.status == JobStatus.done
    assert job.transcript_source is None
    transcribe.assert_not_called()


def test_whisper_failure_does_not_fail_job(tmp_path, monkeypatch):
    from app import tasks

    engine, session = make_session()
    _base_patches(tasks, monkeypatch, tmp_path, engine, duration=10.0)
    monkeypatch.setattr(tasks, "pick_caption_language", lambda info: None)
    monkeypatch.setattr("app.config.settings.whisper_enabled", True)
    monkeypatch.setattr("app.config.settings.whisper_max_duration_seconds", 3600)
    monkeypatch.setattr(tasks, "extract_audio", lambda src, dest: None)

    def boom(p):
        raise RuntimeError("whisper blew up")

    monkeypatch.setattr(tasks, "transcribe_audio", boom)

    user = User(email="a@example.com", hashed_password="x")
    session.add(user); session.commit(); session.refresh(user)
    job = Job(user_id=user.id, youtube_url="https://youtube.com/watch?v=abc", interval_seconds=5.0)
    session.add(job); session.commit(); session.refresh(job)

    tasks.process_job(job.id)

    session.refresh(job)
    assert job.status == JobStatus.done
    assert job.transcript_language is None
    assert job.transcript_source is None
    frames = session.query(Frame).filter(Frame.job_id == job.id).all()
    assert all(f.caption is None for f in frames)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_tasks.py -v`
Expected: FAIL (`transcribe_audio` not importable in `app.tasks`; `transcript_source` never set).

- [ ] **Step 3: Update `backend/app/tasks.py`**

Change the imports block:

```python
import os

from sqlmodel import Session, select

from app.celery_app import celery_app
from app.config import settings
from app.database import engine
from app.models import Job, Frame, JobStatus, TranscriptCue
from app.video import (
    get_video_info,
    download_video,
    extract_frame,
    compute_timestamps,
    pick_caption_language,
    download_captions,
    parse_vtt,
    caption_for_timestamp,
)
from app.whisper import extract_audio, transcribe_audio
```

In the captions block, set the source when cues are stored — change:

```python
                        job.transcript_language = lang
                        session.add(job)
                        session.commit()
```

to:

```python
                        job.transcript_language = lang
                        job.transcript_source = "captions"
                        session.add(job)
                        session.commit()
```

Then, after the frame-extraction `for` loop and BEFORE `job.status = JobStatus.done`, insert the Whisper fallback:

```python
            # Best-effort Whisper fallback: only when no captions were found.
            if (
                not cues
                and settings.whisper_enabled
                and duration <= settings.whisper_max_duration_seconds
            ):
                try:
                    job.status = JobStatus.transcribing
                    session.add(job)
                    session.commit()

                    audio_path = os.path.join(job_dir, "audio.wav")
                    extract_audio(source_path, audio_path)
                    wlang, wcues = transcribe_audio(audio_path)
                    if wcues:
                        for c in wcues:
                            session.add(
                                TranscriptCue(
                                    job_id=job.id,
                                    start_seconds=c.start,
                                    end_seconds=c.end,
                                    text=c.text,
                                )
                            )
                        job.transcript_language = wlang
                        job.transcript_source = "whisper"
                        frames = session.exec(select(Frame).where(Frame.job_id == job.id)).all()
                        for frame in frames:
                            frame.caption = caption_for_timestamp(wcues, frame.timestamp_seconds)
                            session.add(frame)
                        session.add(job)
                        session.commit()
                except Exception:
                    session.rollback()

            job.status = JobStatus.done
            session.add(job)
            session.commit()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_tasks.py -v`
Expected: all pass (existing task tests + the 4 new ones).

- [ ] **Step 5: Run the full suite**

Run: `pytest -v`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/tasks.py backend/tests/test_tasks.py
git commit -m "feat: Whisper fallback in process_job when no captions"
```

---

## Task 4: API — `source` on transcript response

**Files:**
- Modify: `backend/app/schemas.py`
- Modify: `backend/app/routers/jobs.py`
- Test: `backend/tests/test_transcript_api.py`

**Interfaces:**
- Consumes: `Job.transcript_source` from Task 1.
- Produces: `TranscriptResponse.source` exposed on `GET /jobs/{id}/transcript`.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_transcript_api.py`:

```python
@patch("app.routers.jobs.process_job")
def test_transcript_endpoint_returns_source(mock_task, client, session):
    from app.models import Job, TranscriptCue

    headers = signup_and_auth_headers(client)
    job = client.post(
        "/jobs", json={"youtube_url": "https://youtube.com/watch?v=abc", "interval_seconds": 5}, headers=headers
    ).json()

    db_job = session.get(Job, job["id"])
    db_job.transcript_language = "en"
    db_job.transcript_source = "whisper"
    session.add(db_job)
    session.add(TranscriptCue(job_id=job["id"], start_seconds=1.0, end_seconds=4.0, text="hi"))
    session.commit()

    resp = client.get(f"/jobs/{job['id']}/transcript", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["source"] == "whisper"


@patch("app.routers.jobs.process_job")
def test_transcript_endpoint_source_null_when_none(mock_task, client):
    headers = signup_and_auth_headers(client)
    job = client.post(
        "/jobs", json={"youtube_url": "https://youtube.com/watch?v=abc", "interval_seconds": 5}, headers=headers
    ).json()
    resp = client.get(f"/jobs/{job['id']}/transcript", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["source"] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_transcript_api.py -v`
Expected: FAIL (`source` key missing from the response).

- [ ] **Step 3: Add `source` to `TranscriptResponse` in `backend/app/schemas.py`**

```python
class TranscriptResponse(BaseModel):
    language: Optional[str] = None
    source: Optional[str] = None
    cues: list[TranscriptCueResponse]
```

- [ ] **Step 4: Return it from the endpoint in `backend/app/routers/jobs.py`**

Change the transcript endpoint's return:

```python
    return TranscriptResponse(language=job.transcript_language, source=job.transcript_source, cues=cues)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_transcript_api.py -v`
Expected: all pass.

- [ ] **Step 6: Run the full suite**

Run: `pytest -v`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas.py backend/app/routers/jobs.py backend/tests/test_transcript_api.py
git commit -m "feat: expose transcript source on the transcript endpoint"
```

---

## Task 5: Frontend — transcribing status + Auto-transcribed indicator

**Files:**
- Modify: `frontend/lib/jobs.ts`
- Modify: `frontend/components/StatusBadge.tsx`
- Modify: `frontend/components/JobProgress.tsx`
- Modify: `frontend/components/JobGallery.tsx`

**Interfaces:**
- Consumes: `Job.status` may now be `"transcribing"`; `GET /jobs/{id}/transcript` now returns `source`.
- Produces: the `transcribing` badge/label and the "Auto-transcribed" indicator.

- [ ] **Step 1: Add `source` to the `Transcript` type in `frontend/lib/jobs.ts`**

```typescript
export interface Transcript {
  language: string | null;
  source: string | null;
  cues: TranscriptCue[];
}
```

(`getTranscript` returns the parsed JSON as-is, so `source` flows through automatically.)

- [ ] **Step 2: Add the `transcribing` pill to `frontend/components/StatusBadge.tsx`**

```typescript
const STATUS_STYLES: Record<string, string> = {
  pending: "bg-chip text-muted",
  downloading: "bg-blue-50 text-blue-700",
  extracting: "bg-blue-50 text-blue-700",
  transcribing: "bg-blue-50 text-blue-700",
  done: "bg-green-50 text-green-700",
  failed: "bg-red-50 text-red-700",
};
```

- [ ] **Step 3: Show a clear label for transcribing in `frontend/components/JobProgress.tsx`**

Replace the status label line:

```tsx
        <span className="font-medium capitalize text-ink">{event.status}…</span>
```

with:

```tsx
        <span className="font-medium text-ink">
          {event.status === "transcribing" ? "Transcribing audio…" : `${event.status}…`}
        </span>
```

(The rest of `JobProgress` is unchanged. During `transcribing`, `frames_done === frames_total` so the bar sits full with the "Transcribing audio…" label — expected.)

- [ ] **Step 4: Add the "Auto-transcribed" indicator in `frontend/components/JobGallery.tsx`**

In the Transcript tab, replace the `hasTranscript` `<ul>` branch so the indicator renders above the cue list. Change:

```tsx
          ) : (
            <ul className="flex flex-col divide-y divide-line rounded-xl border border-line">
              {transcript!.cues.map((cue, i) => (
```

to:

```tsx
          ) : (
            <div>
              {transcript!.source === "whisper" && (
                <p className="mb-2 text-xs text-muted">Auto-transcribed</p>
              )}
              <ul className="flex flex-col divide-y divide-line rounded-xl border border-line">
                {transcript!.cues.map((cue, i) => (
```

and close the added `<div>` after the `</ul>` (add a `</div>` after the existing `</ul>` that ends the list, before the `)}` that closes the `hasTranscript` ternary). The final structure of that branch:

```tsx
          ) : (
            <div>
              {transcript!.source === "whisper" && (
                <p className="mb-2 text-xs text-muted">Auto-transcribed</p>
              )}
              <ul className="flex flex-col divide-y divide-line rounded-xl border border-line">
                {transcript!.cues.map((cue, i) => (
                  <li key={i}>
                    <button
                      onClick={() => openNearestFrame(cue.start_seconds)}
                      className="flex w-full items-start gap-3 px-4 py-2.5 text-left transition-colors hover:bg-surface"
                    >
                      <span className="mt-0.5 shrink-0 font-mono text-xs text-muted">
                        {formatTime(cue.start_seconds)}
                      </span>
                      <span className="text-sm text-ink">{cue.text}</span>
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}
```

- [ ] **Step 5: Verify build and lint**

Run: `cd frontend && npm run build`
Expected: builds successfully.

Run: `npm run lint`
Expected: no errors (only the two expected `@next/next/no-img-element` warnings on `JobGallery.tsx`).

- [ ] **Step 6: Commit**

```bash
git add frontend/lib/jobs.ts frontend/components/StatusBadge.tsx frontend/components/JobProgress.tsx frontend/components/JobGallery.tsx
git commit -m "feat: transcribing status UI and Auto-transcribed indicator"
```

---

## Task 6: Docker, compose & README

**Files:**
- Modify: `backend/Dockerfile`
- Modify: `docker-compose.yml`
- Modify: `README.md`

**Interfaces:**
- None — deployment/config/docs so the feature runs and is documented.

- [ ] **Step 1: Pre-download the model in `backend/Dockerfile`**

After the `pip install` line, add a build step that downloads the model into the image (so the first job doesn't pay a download):

```dockerfile
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download the faster-whisper model so the first transcription job doesn't
# have to fetch it at runtime. Adjust the model name if YTF_WHISPER_MODEL changes.
RUN python -c "from faster_whisper import WhisperModel; WhisperModel('base', compute_type='int8')"

COPY app ./app
COPY alembic.ini .
COPY alembic ./alembic

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 2: Lower worker concurrency in `docker-compose.yml`**

Change the `worker` service `command` so concurrent Whisper transcriptions don't multiply RAM (each prefork process loads its own model):

```yaml
  worker:
    build: ./backend
    command: celery -A app.celery_app.celery_app worker --loglevel=info --concurrency=2
    env_file: .env
```

(Leave the rest of the `worker` service unchanged.)

- [ ] **Step 3: Document Whisper in `README.md`**

Add a subsection under "## Notes":

```markdown
- **Transcripts.** If a video has YouTube captions, they're used directly. If not, the
  worker falls back to local speech-to-text with faster-whisper (`base`, CPU int8),
  shown as a `transcribing` status. This is best-effort — a failure or a video longer
  than `YTF_WHISPER_MAX_DURATION_SECONDS` (default 3600 s) leaves the job succeeding with
  frames and no transcript.
- **Whisper config** (env, `YTF_` prefix): `WHISPER_ENABLED` (default `true`),
  `WHISPER_MODEL` (default `base`), `WHISPER_MAX_DURATION_SECONDS` (default `3600`),
  `WHISPER_COMPUTE_TYPE` (default `int8`). The worker image pre-bakes the `base` model;
  if you change `WHISPER_MODEL`, update the pre-download line in `backend/Dockerfile`.
- **Worker resources.** Each worker process loads its own Whisper model (~150 MB for
  `base`). The compose file runs the worker at `--concurrency=2`; raise/lower it to suit
  your host. Do not set a short Celery task time limit — a 30-minute video can take
  ~15 min to transcribe on CPU.
```

- [ ] **Step 4: Commit**

```bash
git add backend/Dockerfile docker-compose.yml README.md
git commit -m "chore: pre-bake whisper model, lower worker concurrency, document transcripts"
```

---

## Task 7: Full manual walkthrough

**Files:**
- None — verification only.

- [ ] **Step 1: Rebuild the stack and migrate**

From the repo root:

```bash
docker compose up -d --build
docker compose exec api alembic upgrade head
```

Confirm the `0003` migration applies (adds the `transcribing` enum value and `transcript_source` column) — e.g.:

```bash
docker compose exec postgres psql -U postgres -d youtoframe -c "SELECT unnest(enum_range(NULL::jobstatus));"
docker compose exec postgres psql -U postgres -d youtoframe -c "SELECT column_name FROM information_schema.columns WHERE table_name='job' AND column_name='transcript_source';"
```

- [ ] **Step 2: End-to-end on a caption-less video**

Start the frontend (`cd frontend && npm run dev`), log in, and submit a URL for a video that has **no** captions (so the Whisper path triggers). Confirm:
- the job goes through `transcribing` (badge + "Transcribing audio…" in the progress bar),
- when done, the Storyboard shows captions under frames and the lightbox shows the subtitle,
- the Transcript tab lists cues with an **"Auto-transcribed"** label,
- `GET /jobs/{id}/transcript` returns `"source": "whisper"`, and the ZIP contains `transcript.txt`.

(If real YouTube downloads are blocked in your environment, verify the Whisper module against a local audio/video file by invoking `extract_audio` + `transcribe_audio` directly, and verify the UI paths by inspecting a job whose `transcript_source='whisper'`.)

- [ ] **Step 3: Confirm captioned videos are unaffected**

Submit a video that **has** captions; confirm it never enters `transcribing`, the transcript still appears, and `"source": "captions"` (no "Auto-transcribed" label).

- [ ] **Step 4: Final checks**

Run: `cd backend && source .venv/bin/activate && pytest -v` → all pass.
Run: `cd frontend && npm run build && npm run lint` → clean (only the expected `no-img-element` warnings).

- [ ] **Step 5: Commit (only if the walkthrough required fixes)**

```bash
git add -A
git commit -m "fix: whisper walkthrough adjustments"
```
