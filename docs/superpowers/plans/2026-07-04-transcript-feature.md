# Transcript Feature Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fetch a video's captions (best-effort, via yt-dlp), pair each extracted frame with the line spoken at its timestamp, and surface the transcript in the UI as storyboard captions plus a synced full-transcript tab.

**Architecture:** The Celery worker reads available caption tracks from the existing `yt-dlp -j` metadata call, downloads the chosen track as `.vtt`, parses it into cues, stores cues (new `TranscriptCue` table) and denormalizes the per-frame line onto `Frame.caption`. All transcript work is wrapped so it never fails the job. The frontend adds captions under thumbnails, a caption subtitle in the lightbox, and a Transcript tab with click-to-frame sync.

**Tech Stack:** Python 3.12, FastAPI, SQLModel, Alembic, Celery, yt-dlp; Next.js (App Router, TypeScript), React.

## Global Constraints

- Transcript is **best-effort**: any caption download/parse failure is logged and swallowed; the job still completes with frames. A transcript failure must never change the job's success/failure outcome (per spec).
- Language selection: **prefer English (`en` or `en*`); otherwise the first available track** (per spec). One transcript per job.
- Reuse the existing `yt-dlp -j` metadata (already fetched for duration) to pick the language — no extra metadata round-trip (per spec).
- Every backend task must keep the full suite green (`cd backend && pytest -v`); every frontend task must pass `npm run build` and `npm run lint` cleanly (the two existing `@next/next/no-img-element` warnings on `JobGallery.tsx` are expected/accepted).
- Neutral "Frame Extractor" palette and existing component patterns (per spec).

---

## File Structure

```
backend/
  app/
    models.py            # MODIFY: TranscriptCue table, Frame.caption, Job.transcript_language
    video.py              # MODIFY: get_video_info, pick_caption_language, download_captions,
                          #         parse_vtt, caption_for_timestamp, Cue
    tasks.py               # MODIFY: process_job fetches captions best-effort
    schemas.py              # MODIFY: FrameResponse.caption, TranscriptResponse
    routers/jobs.py          # MODIFY: GET /jobs/{id}/transcript, transcript.txt in zip
  alembic/versions/            # NEW migration
  tests/
    test_video.py               # MODIFY: parser/pairing/language tests
    test_tasks.py                # MODIFY: transcript in worker
    test_transcript_api.py        # NEW: transcript endpoint + caption field
frontend/
  lib/jobs.ts                     # MODIFY: Frame.caption, Transcript types, getTranscript
  components/JobGallery.tsx         # MODIFY: captions, lightbox subtitle, tabs, transcript panel
```

---

## Task 1: Schema — TranscriptCue, Frame.caption, Job.transcript_language

**Files:**
- Modify: `backend/app/models.py`
- Create: `backend/alembic/versions/0002_transcript.py` (generated; filename will include a hash)
- Test: `backend/tests/test_models_transcript.py`

**Interfaces:**
- Produces: `Frame.caption: Optional[str]`, `Job.transcript_language: Optional[str]`, and `TranscriptCue` (fields `id`, `job_id`, `start_seconds: float`, `end_seconds: float`, `text: str`). Consumed by Tasks 3 and 4.

- [ ] **Step 1: Add the model changes to `backend/app/models.py`**

Add `transcript_language` to `Job` (after `created_at` is fine, but place with the other fields):

```python
class Job(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    youtube_url: str
    interval_seconds: Optional[float] = None
    manual_timestamps: Optional[list[float]] = Field(default=None, sa_column=Column(JSON))
    status: JobStatus = Field(default=JobStatus.pending)
    error_message: Optional[str] = None
    frames_total: int = Field(default=0)
    frames_done: int = Field(default=0)
    transcript_language: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
```

Add `caption` to `Frame`:

```python
class Frame(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    job_id: int = Field(foreign_key="job.id", index=True)
    timestamp_seconds: float
    file_path: str
    caption: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
```

Add the new table at the end of the file:

```python
class TranscriptCue(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    job_id: int = Field(foreign_key="job.id", index=True)
    start_seconds: float
    end_seconds: float
    text: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
```

- [ ] **Step 2: Write the failing test**

```python
# backend/tests/test_models_transcript.py
from sqlmodel import SQLModel, Session, create_engine

from app.models import User, Job, Frame, TranscriptCue


def make_engine():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return engine


def test_frame_caption_and_transcript_cue_persist():
    engine = make_engine()
    with Session(engine) as session:
        user = User(email="a@example.com", hashed_password="x")
        session.add(user)
        session.commit()
        session.refresh(user)

        job = Job(user_id=user.id, youtube_url="https://youtube.com/watch?v=abc", interval_seconds=5)
        session.add(job)
        session.commit()
        session.refresh(job)

        job.transcript_language = "en"
        frame = Frame(job_id=job.id, timestamp_seconds=5.0, file_path="/x.jpg", caption="hello world")
        cue = TranscriptCue(job_id=job.id, start_seconds=4.0, end_seconds=6.0, text="hello world")
        session.add(job)
        session.add(frame)
        session.add(cue)
        session.commit()
        session.refresh(job)
        session.refresh(frame)
        session.refresh(cue)

        assert job.transcript_language == "en"
        assert frame.caption == "hello world"
        assert cue.start_seconds == 4.0 and cue.text == "hello world"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd backend && source .venv/bin/activate && pytest tests/test_models_transcript.py -v`
Expected: FAIL with `ImportError: cannot import name 'TranscriptCue'` (before Step 1) — after Step 1, proceed.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_models_transcript.py -v`
Expected: `1 passed`

- [ ] **Step 5: Generate the Alembic migration**

Run (from `backend/`, with a temp SQLite DB so autogenerate has something to diff against — Task 2 of the original build used this same approach):

```bash
cd backend && source .venv/bin/activate
alembic revision --autogenerate -m "transcript cues, frame caption, job transcript_language"
```

Open the generated file in `backend/alembic/versions/`. Verify it:
- creates the `transcriptcue` table (columns `id`, `job_id`, `start_seconds`, `end_seconds`, `text`, `created_at`) with the `ix_transcriptcue_job_id` index and the FK to `job.id`,
- adds `caption` (nullable) to `frame`,
- adds `transcript_language` (nullable) to `job`,
- has `import sqlmodel` at the top if any `sqlmodel.sql.sqltypes.AutoString()` appears (autogenerate sometimes omits it — add it if missing, as in the initial migration),
- and its `downgrade()` reverses all three (drop table, drop the two columns).

Rename the file if needed so it sorts after the initial migration (e.g. prefix `0002_`). Confirm `down_revision` points at the initial migration's revision id.

- [ ] **Step 6: Run the full suite**

Run: `pytest -v`
Expected: all pass (previous tests + the new one).

- [ ] **Step 7: Commit**

```bash
git add backend/app/models.py backend/alembic backend/tests/test_models_transcript.py
git commit -m "feat: add TranscriptCue table, Frame.caption, Job.transcript_language"
```

---

## Task 2: Video module — caption fetching & parsing

**Files:**
- Modify: `backend/app/video.py`
- Test: `backend/tests/test_video.py`

**Interfaces:**
- Consumes: existing `_run` in `video.py`.
- Produces:
  - `Cue` (NamedTuple: `start: float`, `end: float`, `text: str`)
  - `get_video_info(url: str) -> dict`
  - `pick_caption_language(info: dict) -> str | None`
  - `download_captions(url: str, lang: str, dest_stem: str) -> str` (returns the written `.vtt` path)
  - `parse_vtt(path: str) -> list[Cue]`
  - `caption_for_timestamp(cues: list[Cue], t: float) -> str | None`
  - `get_video_duration` remains (refactored to use `get_video_info`).
  Consumed by Task 3.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_video.py`:

```python
import os
import re  # noqa: F401  (may already be needed)

from app.video import (
    Cue,
    get_video_info,
    pick_caption_language,
    parse_vtt,
    caption_for_timestamp,
)


def test_pick_caption_language_prefers_english():
    info = {"subtitles": {"fr": [{}], "en": [{}]}, "automatic_captions": {}}
    assert pick_caption_language(info) == "en"


def test_pick_caption_language_prefers_english_variant():
    info = {"subtitles": {}, "automatic_captions": {"es": [{}], "en-US": [{}]}}
    assert pick_caption_language(info) == "en-US"


def test_pick_caption_language_falls_back_to_first_available():
    info = {"subtitles": {"de": [{}]}, "automatic_captions": {}}
    assert pick_caption_language(info) == "de"


def test_pick_caption_language_none_available():
    assert pick_caption_language({"subtitles": {}, "automatic_captions": {}}) is None
    assert pick_caption_language({}) is None


def test_parse_vtt_well_formed(tmp_path):
    vtt = tmp_path / "cap.en.vtt"
    vtt.write_text(
        "WEBVTT\n\n"
        "1\n"
        "00:00:01.000 --> 00:00:04.000\n"
        "Hello world\n\n"
        "2\n"
        "00:00:04.500 --> 00:00:08.000\n"
        "Second line\n"
    )
    cues = parse_vtt(str(vtt))
    assert cues == [Cue(1.0, 4.0, "Hello world"), Cue(4.5, 8.0, "Second line")]


def test_parse_vtt_strips_tags_and_dedupes_and_handles_cue_settings(tmp_path):
    vtt = tmp_path / "auto.en.vtt"
    vtt.write_text(
        "WEBVTT\n\n"
        "NOTE this is a note block\n\n"
        "00:00:01.000 --> 00:00:03.000 align:start position:0%\n"
        "Hello<00:00:01.500><c> there</c>\n\n"
        "00:00:03.000 --> 00:00:05.000\n"
        "Hello there\n\n"
        "00:00:05.000 --> 00:00:07.000\n"
        "next\n"
    )
    cues = parse_vtt(str(vtt))
    # tags stripped -> "Hello there"; the immediately-repeated identical line is collapsed
    assert cues == [Cue(1.0, 3.0, "Hello there"), Cue(5.0, 7.0, "next")]


def test_caption_for_timestamp_covering_nearest_and_none():
    cues = [Cue(1.0, 4.0, "a"), Cue(4.5, 8.0, "b")]
    assert caption_for_timestamp(cues, 2.0) == "a"        # covered
    assert caption_for_timestamp(cues, 4.2) == "a"        # gap -> nearest preceding
    assert caption_for_timestamp(cues, 6.0) == "b"        # covered
    assert caption_for_timestamp(cues, 0.5) is None       # before first cue
    assert caption_for_timestamp([], 3.0) is None         # no cues
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_video.py -v`
Expected: FAIL with `ImportError: cannot import name 'Cue'` (and friends).

- [ ] **Step 3: Implement in `backend/app/video.py`**

Add `import re` and `from typing import NamedTuple` at the top (keep existing `import json`, `import subprocess`). Add the `Cue` type and functions; refactor `get_video_duration`:

```python
import json
import re
import subprocess
from typing import NamedTuple
```

```python
class Cue(NamedTuple):
    start: float
    end: float
    text: str


def get_video_info(url: str) -> dict:
    result = _run(["yt-dlp", "--no-warnings", "--no-playlist", "-j", url])
    return json.loads(result.stdout)


def get_video_duration(url: str) -> float:
    return float(get_video_info(url)["duration"])


def pick_caption_language(info: dict) -> str | None:
    subs = info.get("subtitles") or {}
    autos = info.get("automatic_captions") or {}
    available = list(subs.keys()) + list(autos.keys())
    if not available:
        return None
    for lang in available:
        if lang == "en":
            return lang
    for lang in available:
        if lang.startswith("en"):
            return lang
    return available[0]


def download_captions(url: str, lang: str, dest_stem: str) -> str:
    # Best-effort: yt-dlp writes "<dest_stem>.<lang>.vtt". The caller checks the
    # file exists before parsing.
    _run(
        [
            "yt-dlp", "--no-warnings", "--no-playlist",
            "--skip-download",
            "--write-subs", "--write-auto-subs",
            "--sub-langs", lang,
            "--sub-format", "vtt",
            "-o", dest_stem,
            url,
        ]
    )
    return f"{dest_stem}.{lang}.vtt"


def _parse_ts(token: str) -> float:
    token = token.strip().replace(",", ".")
    parts = [float(p) for p in token.split(":")]
    if len(parts) == 3:
        h, m, s = parts
    elif len(parts) == 2:
        h, m, s = 0.0, parts[0], parts[1]
    else:
        raise ValueError(f"bad timestamp {token}")
    return h * 3600 + m * 60 + s


def parse_vtt(path: str) -> list[Cue]:
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()

    cues: list[Cue] = []
    for block in re.split(r"\n\s*\n", content):
        lines = [ln for ln in block.splitlines() if ln.strip() != ""]
        if not lines:
            continue
        timing_idx = next((i for i, ln in enumerate(lines) if "-->" in ln), None)
        if timing_idx is None:
            continue  # WEBVTT header, NOTE block, or id-only block
        left, _, right = lines[timing_idx].partition("-->")
        try:
            start = _parse_ts(left.strip().split()[0])
            end = _parse_ts(right.strip().split()[0])
        except (ValueError, IndexError):
            continue
        text = " ".join(lines[timing_idx + 1:])
        text = re.sub(r"<[^>]+>", "", text)      # strip inline tags
        text = re.sub(r"\s+", " ", text).strip()
        if not text:
            continue
        if cues and cues[-1].text == text:       # collapse consecutive duplicates
            continue
        cues.append(Cue(start, end, text))
    return cues


def caption_for_timestamp(cues: list[Cue], t: float) -> str | None:
    covering = [c for c in cues if c.start <= t <= c.end]
    if covering:
        return covering[0].text
    preceding = [c for c in cues if c.start <= t]
    if preceding:
        return max(preceding, key=lambda c: c.start).text
    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_video.py -v`
Expected: all pass (previous video tests + the new ones).

- [ ] **Step 5: Commit**

```bash
git add backend/app/video.py backend/tests/test_video.py
git commit -m "feat: add caption fetching and VTT parsing to video module"
```

---

## Task 3: Worker integration — best-effort transcript in `process_job`

**Files:**
- Modify: `backend/app/tasks.py`
- Test: `backend/tests/test_tasks.py`

**Interfaces:**
- Consumes: `get_video_info`, `pick_caption_language`, `download_captions`, `parse_vtt`, `caption_for_timestamp`, `Cue` from Task 2; `TranscriptCue` from Task 1.
- Produces: `Frame.caption` populated per frame, `TranscriptCue` rows inserted, `Job.transcript_language` set — when captions are available; job unaffected when not.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_tasks.py`:

```python
def test_process_job_populates_transcript(tmp_path, monkeypatch):
    from app import tasks
    from app.models import TranscriptCue
    from app.video import Cue

    engine, session = make_session()
    monkeypatch.setattr(tasks, "engine", engine)
    monkeypatch.setattr("app.config.settings.data_dir", str(tmp_path))

    monkeypatch.setattr(tasks, "get_video_info", lambda url: {"duration": 10.0})
    monkeypatch.setattr(tasks, "download_video", lambda url, path: None)
    monkeypatch.setattr(tasks, "extract_frame", lambda v, ts, dest: None)
    monkeypatch.setattr(tasks, "pick_caption_language", lambda info: "en")
    monkeypatch.setattr(tasks, "download_captions", lambda url, lang, stem: f"{stem}.{lang}.vtt")
    monkeypatch.setattr(tasks.os.path, "exists", lambda p: True)
    monkeypatch.setattr(tasks, "parse_vtt", lambda path: [Cue(0.0, 6.0, "hello"), Cue(6.0, 10.0, "world")])

    user = User(email="a@example.com", hashed_password="x")
    session.add(user)
    session.commit()
    session.refresh(user)
    job = Job(user_id=user.id, youtube_url="https://youtube.com/watch?v=abc", interval_seconds=5.0)
    session.add(job)
    session.commit()
    session.refresh(job)

    tasks.process_job(job.id)

    session.refresh(job)
    assert job.status == JobStatus.done
    assert job.transcript_language == "en"

    cues = session.query(TranscriptCue).filter(TranscriptCue.job_id == job.id).all()
    assert len(cues) == 2

    frames = session.query(Frame).filter(Frame.job_id == job.id).order_by(Frame.timestamp_seconds).all()
    # timestamps for duration 10, interval 5 -> [0.0, 5.0, 9.5] (last capped below duration)
    assert frames[0].caption == "hello"
    assert frames[-1].caption == "world"


def test_process_job_succeeds_when_transcript_fails(tmp_path, monkeypatch):
    from app import tasks

    engine, session = make_session()
    monkeypatch.setattr(tasks, "engine", engine)
    monkeypatch.setattr("app.config.settings.data_dir", str(tmp_path))

    monkeypatch.setattr(tasks, "get_video_info", lambda url: {"duration": 10.0})
    monkeypatch.setattr(tasks, "download_video", lambda url, path: None)
    monkeypatch.setattr(tasks, "extract_frame", lambda v, ts, dest: None)

    def boom(info):
        raise RuntimeError("caption lookup blew up")

    monkeypatch.setattr(tasks, "pick_caption_language", boom)

    user = User(email="a@example.com", hashed_password="x")
    session.add(user)
    session.commit()
    session.refresh(user)
    job = Job(user_id=user.id, youtube_url="https://youtube.com/watch?v=abc", interval_seconds=5.0)
    session.add(job)
    session.commit()
    session.refresh(job)

    tasks.process_job(job.id)

    session.refresh(job)
    assert job.status == JobStatus.done            # transcript failure did NOT fail the job
    assert job.transcript_language is None
    frames = session.query(Frame).filter(Frame.job_id == job.id).all()
    assert all(f.caption is None for f in frames)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_tasks.py -v`
Expected: FAIL (`get_video_info` not importable in `app.tasks`, and captions not populated).

- [ ] **Step 3: Rewrite `backend/app/tasks.py`**

```python
import os

from sqlmodel import Session

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


@celery_app.task(name="process_job")
def process_job(job_id: int) -> None:
    with Session(engine) as session:
        job = session.get(Job, job_id)
        if not job:
            return

        try:
            job_dir = os.path.join(settings.data_dir, str(job.user_id), str(job.id))
            frames_dir = os.path.join(job_dir, "frames")
            os.makedirs(frames_dir, exist_ok=True)
            source_path = os.path.join(job_dir, "source.mp4")

            job.status = JobStatus.downloading
            session.add(job)
            session.commit()

            info = get_video_info(job.youtube_url)
            duration = float(info["duration"])
            timestamps = compute_timestamps(duration, job.interval_seconds, job.manual_timestamps)

            download_video(job.youtube_url, source_path)

            # Best-effort transcript: never let a caption failure fail the job.
            cues = []
            try:
                lang = pick_caption_language(info)
                if lang:
                    cap_stem = os.path.join(job_dir, "captions")
                    cap_path = download_captions(job.youtube_url, lang, cap_stem)
                    if os.path.exists(cap_path):
                        cues = parse_vtt(cap_path)
                        for c in cues:
                            session.add(
                                TranscriptCue(
                                    job_id=job.id,
                                    start_seconds=c.start,
                                    end_seconds=c.end,
                                    text=c.text,
                                )
                            )
                        job.transcript_language = lang
                        session.add(job)
                        session.commit()
            except Exception:
                cues = []

            job.status = JobStatus.extracting
            job.frames_total = len(timestamps)
            job.frames_done = 0
            session.add(job)
            session.commit()

            for ts in timestamps:
                frame_path = os.path.join(frames_dir, f"{ts}.jpg")
                extract_frame(source_path, ts, frame_path)
                frame = Frame(
                    job_id=job.id,
                    timestamp_seconds=ts,
                    file_path=frame_path,
                    caption=caption_for_timestamp(cues, ts),
                )
                session.add(frame)
                job.frames_done += 1
                session.add(job)
                session.commit()

            job.status = JobStatus.done
            session.add(job)
            session.commit()
        except Exception as exc:
            job.status = JobStatus.failed
            job.error_message = str(exc)
            session.add(job)
            session.commit()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_tasks.py -v`
Expected: all pass (previous task tests + the two new ones).

- [ ] **Step 5: Run the full suite**

Run: `pytest -v`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/tasks.py backend/tests/test_tasks.py
git commit -m "feat: fetch and store transcript best-effort in process_job"
```

---

## Task 4: API — caption field, transcript endpoint, transcript.txt in zip

**Files:**
- Modify: `backend/app/schemas.py`
- Modify: `backend/app/routers/jobs.py`
- Test: `backend/tests/test_transcript_api.py`

**Interfaces:**
- Consumes: `TranscriptCue`, `Frame`, `Job` from Tasks 1/3; `_get_owned_job` in `jobs.py`.
- Produces: `caption` on `GET /jobs/{id}/frames`; `GET /jobs/{id}/transcript` returning `{language, cues}`; a `transcript.txt` entry in `GET /jobs/{id}/zip` when cues exist.

- [ ] **Step 1: Append schemas to `backend/app/schemas.py`**

Add `caption` to `FrameResponse` and add the transcript schemas:

```python
class FrameResponse(BaseModel):
    id: int
    timestamp_seconds: float
    caption: Optional[str] = None

    class Config:
        from_attributes = True


class TranscriptCueResponse(BaseModel):
    start_seconds: float
    end_seconds: float
    text: str

    class Config:
        from_attributes = True


class TranscriptResponse(BaseModel):
    language: Optional[str] = None
    cues: list[TranscriptCueResponse]
```

(Replace the existing `FrameResponse` class with the version above; append the two new classes after it.)

- [ ] **Step 2: Write the failing tests**

```python
# backend/tests/test_transcript_api.py
from unittest.mock import patch


def signup_and_auth_headers(client, email="a@example.com"):
    resp = client.post("/auth/signup", json={"email": email, "password": "secret123"})
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@patch("app.routers.jobs.process_job")
def test_frames_include_caption(mock_task, client, session):
    from app.models import Frame

    headers = signup_and_auth_headers(client)
    job = client.post(
        "/jobs", json={"youtube_url": "https://youtube.com/watch?v=abc", "interval_seconds": 5}, headers=headers
    ).json()

    session.add(Frame(job_id=job["id"], timestamp_seconds=5.0, file_path="/x.jpg", caption="hello"))
    session.commit()

    resp = client.get(f"/jobs/{job['id']}/frames", headers=headers)
    assert resp.status_code == 200
    assert resp.json()[0]["caption"] == "hello"


@patch("app.routers.jobs.process_job")
def test_transcript_endpoint_returns_cues(mock_task, client, session):
    from app.models import Job, TranscriptCue

    headers = signup_and_auth_headers(client)
    job = client.post(
        "/jobs", json={"youtube_url": "https://youtube.com/watch?v=abc", "interval_seconds": 5}, headers=headers
    ).json()

    db_job = session.get(Job, job["id"])
    db_job.transcript_language = "en"
    session.add(db_job)
    session.add(TranscriptCue(job_id=job["id"], start_seconds=1.0, end_seconds=4.0, text="hello"))
    session.add(TranscriptCue(job_id=job["id"], start_seconds=4.0, end_seconds=8.0, text="world"))
    session.commit()

    resp = client.get(f"/jobs/{job['id']}/transcript", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["language"] == "en"
    assert [c["text"] for c in body["cues"]] == ["hello", "world"]


@patch("app.routers.jobs.process_job")
def test_transcript_endpoint_empty_when_none(mock_task, client, session):
    headers = signup_and_auth_headers(client)
    job = client.post(
        "/jobs", json={"youtube_url": "https://youtube.com/watch?v=abc", "interval_seconds": 5}, headers=headers
    ).json()

    resp = client.get(f"/jobs/{job['id']}/transcript", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == {"language": None, "cues": []}


@patch("app.routers.jobs.process_job")
def test_transcript_endpoint_not_owned_returns_404(mock_task, client):
    headers_a = signup_and_auth_headers(client, "a@example.com")
    headers_b = signup_and_auth_headers(client, "b@example.com")
    job = client.post(
        "/jobs", json={"youtube_url": "https://youtube.com/watch?v=abc", "interval_seconds": 5}, headers=headers_a
    ).json()

    resp = client.get(f"/jobs/{job['id']}/transcript", headers=headers_b)
    assert resp.status_code == 404
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_transcript_api.py -v`
Expected: FAIL (transcript route 404s / caption field missing).

- [ ] **Step 4: Add the transcript endpoint and zip change to `backend/app/routers/jobs.py`**

Add imports near the top (with the existing model/schema imports):

```python
from app.models import Frame, TranscriptCue
from app.schemas import FrameResponse, TranscriptResponse
```

(If `Frame` / `FrameResponse` are already imported, just add `TranscriptCue` and `TranscriptResponse`.)

Add this endpoint alongside the other `/{job_id}/...` routes:

```python
@router.get("/{job_id}/transcript", response_model=TranscriptResponse)
def get_transcript(job_id: int, session: Session = Depends(get_session), user: User = Depends(get_current_user)):
    job = _get_owned_job(job_id, session, user)
    cues = session.exec(
        select(TranscriptCue).where(TranscriptCue.job_id == job_id).order_by(TranscriptCue.start_seconds)
    ).all()
    return TranscriptResponse(language=job.transcript_language, cues=cues)
```

In `download_zip`, after writing the frames and before `buffer.seek(0)`, add the transcript file when cues exist:

```python
    cues = session.exec(
        select(TranscriptCue).where(TranscriptCue.job_id == job_id).order_by(TranscriptCue.start_seconds)
    ).all()
    if cues:
        def _fmt(sec: float) -> str:
            total = int(sec)
            return f"{total // 60}:{total % 60:02d}"

        transcript_text = "\n".join(f"[{_fmt(c.start_seconds)}] {c.text}" for c in cues)
        with zipfile.ZipFile(buffer, "a") as zf:
            zf.writestr("transcript.txt", transcript_text)
```

(Place this block after the existing `with zipfile.ZipFile(buffer, "w") as zf:` frame-writing block closes and before `buffer.seek(0)`. Re-opening the same buffer in append mode adds `transcript.txt` to the archive.)

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_transcript_api.py -v`
Expected: `4 passed`

- [ ] **Step 6: Run the full suite**

Run: `pytest -v`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas.py backend/app/routers/jobs.py backend/tests/test_transcript_api.py
git commit -m "feat: expose caption on frames, transcript endpoint, transcript.txt in zip"
```

---

## Task 5: Frontend lib — caption field + transcript fetch

**Files:**
- Modify: `frontend/lib/jobs.ts`

**Interfaces:**
- Consumes: `apiFetch` from `lib/api.ts`.
- Produces: `Frame.caption`, `TranscriptCue`, `Transcript` types, and `getTranscript(jobId)`. Consumed by Task 6.

- [ ] **Step 1: Update `frontend/lib/jobs.ts`**

Add `caption` to the `Frame` interface and append the transcript pieces (leave `createJob`/`listJobs`/`listFrames` unchanged):

```typescript
export interface Frame {
  id: number;
  timestamp_seconds: number;
  caption: string | null;
}

export interface TranscriptCue {
  start_seconds: number;
  end_seconds: number;
  text: string;
}

export interface Transcript {
  language: string | null;
  cues: TranscriptCue[];
}

export async function getTranscript(jobId: number): Promise<Transcript> {
  const res = await apiFetch(`/jobs/${jobId}/transcript`);
  if (!res.ok) throw new Error("Failed to load transcript");
  return res.json();
}
```

- [ ] **Step 2: Verify build and lint**

Run: `cd frontend && npm run build`
Expected: builds successfully (the `caption` field is additive; existing `Frame` consumers still compile).

Run: `npm run lint`
Expected: no errors (only the pre-existing `no-img-element` warnings).

- [ ] **Step 3: Commit**

```bash
git add frontend/lib/jobs.ts
git commit -m "feat: add caption field and transcript fetch to frontend lib"
```

---

## Task 6: Frontend gallery — storyboard captions, lightbox subtitle, transcript tab

**Files:**
- Modify: `frontend/components/JobGallery.tsx`

**Interfaces:**
- Consumes: `listFrames`, `getTranscript`, `Frame`, `Transcript` from Task 5; `getToken` from `lib/api.ts`.
- Produces: the full transcript UI. No prop change (`{ jobId: number }`), so `app/jobs/[id]/page.tsx` is untouched.

- [ ] **Step 1: Rewrite `frontend/components/JobGallery.tsx`**

```tsx
"use client";

import { useEffect, useState } from "react";
import { listFrames, getTranscript, Frame, Transcript } from "@/lib/jobs";
import { getToken } from "@/lib/api";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

function formatTime(seconds: number): string {
  const total = Math.floor(seconds);
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

type Tab = "storyboard" | "transcript";

export default function JobGallery({ jobId }: { jobId: number }) {
  const [frames, setFrames] = useState<Frame[]>([]);
  const [imageUrls, setImageUrls] = useState<Record<number, string>>({});
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);
  const [tab, setTab] = useState<Tab>("storyboard");
  const [transcript, setTranscript] = useState<Transcript | null>(null);

  useEffect(() => {
    listFrames(jobId).then(setFrames).catch(() => {});
    getTranscript(jobId).then(setTranscript).catch(() => {});
  }, [jobId]);

  useEffect(() => {
    const token = getToken();
    let cancelled = false;
    const urls: Record<number, string> = {};

    Promise.all(
      frames.map(async (frame) => {
        const res = await fetch(`${API_URL}/frames/${frame.id}/image`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        const blob = await res.blob();
        urls[frame.id] = URL.createObjectURL(blob);
      })
    ).then(() => {
      if (!cancelled) setImageUrls(urls);
    });

    return () => {
      cancelled = true;
      Object.values(urls).forEach(URL.revokeObjectURL);
    };
  }, [frames]);

  useEffect(() => {
    if (selectedIndex === null) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setSelectedIndex(null);
      else if (e.key === "ArrowLeft") setSelectedIndex((i) => (i !== null && i > 0 ? i - 1 : i));
      else if (e.key === "ArrowRight")
        setSelectedIndex((i) => (i !== null && i < frames.length - 1 ? i + 1 : i));
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [selectedIndex, frames.length]);

  async function downloadZip() {
    const token = getToken();
    const res = await fetch(`${API_URL}/jobs/${jobId}/zip`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `job_${jobId}_frames.zip`;
    a.click();
    URL.revokeObjectURL(url);
  }

  function downloadFrame(frame: Frame) {
    const url = imageUrls[frame.id];
    if (!url) return;
    const a = document.createElement("a");
    a.href = url;
    a.download = `${frame.timestamp_seconds}.jpg`;
    a.click();
  }

  // Open the frame whose timestamp is closest to a transcript cue's start.
  function openNearestFrame(startSeconds: number) {
    if (frames.length === 0) return;
    let best = 0;
    let bestDist = Infinity;
    frames.forEach((f, i) => {
      const d = Math.abs(f.timestamp_seconds - startSeconds);
      if (d < bestDist) {
        bestDist = d;
        best = i;
      }
    });
    setSelectedIndex(best);
  }

  const selectedFrame = selectedIndex !== null ? frames[selectedIndex] : null;
  const hasTranscript = !!transcript && transcript.cues.length > 0;

  function tabButton(value: Tab, label: string) {
    const active = tab === value;
    return (
      <button
        onClick={() => setTab(value)}
        className={`rounded-full px-4 py-1.5 text-sm font-medium transition-colors ${
          active ? "bg-ink text-white" : "text-muted hover:bg-chip"
        }`}
      >
        {label}
      </button>
    );
  }

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <div className="flex gap-2">
          {tabButton("storyboard", "Storyboard")}
          {tabButton("transcript", "Transcript")}
        </div>
        <button
          onClick={downloadZip}
          className="rounded-full bg-brand px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-brand-hover"
        >
          Download all as ZIP
        </button>
      </div>

      {tab === "storyboard" && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          {frames.map((frame, index) => (
            <div key={frame.id} className="flex flex-col gap-1.5">
              <button
                onClick={() => setSelectedIndex(index)}
                className="group relative overflow-hidden rounded-xl border border-line bg-chip"
              >
                {imageUrls[frame.id] ? (
                  <img
                    src={imageUrls[frame.id]}
                    alt={`Frame at ${frame.timestamp_seconds}s`}
                    className="aspect-video w-full object-cover transition-transform duration-200 group-hover:scale-[1.03]"
                  />
                ) : (
                  <div className="aspect-video w-full animate-pulse bg-chip" />
                )}
                <span className="absolute bottom-1.5 right-1.5 rounded bg-black/80 px-1.5 py-0.5 text-[11px] font-medium text-white">
                  {formatTime(frame.timestamp_seconds)}
                </span>
              </button>
              {frame.caption && (
                <p className="line-clamp-2 text-xs leading-snug text-muted">{frame.caption}</p>
              )}
            </div>
          ))}
        </div>
      )}

      {tab === "transcript" && (
        <div>
          {!hasTranscript ? (
            <div className="rounded-xl border border-dashed border-line px-4 py-10 text-center">
              <p className="text-sm text-muted">No transcript available for this video.</p>
            </div>
          ) : (
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
          )}
        </div>
      )}

      {selectedFrame && selectedIndex !== null && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/90 p-4"
          onClick={() => setSelectedIndex(null)}
        >
          <button
            onClick={(e) => {
              e.stopPropagation();
              setSelectedIndex(null);
            }}
            className="absolute right-4 top-4 flex h-10 w-10 items-center justify-center rounded-full bg-white/10 text-2xl leading-none text-white transition-colors hover:bg-white/20"
            aria-label="Close"
          >
            &times;
          </button>

          {selectedIndex > 0 && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                setSelectedIndex(selectedIndex - 1);
              }}
              className="absolute left-4 flex h-11 w-11 items-center justify-center rounded-full bg-white/10 text-3xl leading-none text-white transition-colors hover:bg-white/20"
              aria-label="Previous frame"
            >
              &#8249;
            </button>
          )}

          <div className="flex max-w-[85vw] flex-col items-center gap-4" onClick={(e) => e.stopPropagation()}>
            <img
              src={imageUrls[selectedFrame.id]}
              alt={`Frame at ${selectedFrame.timestamp_seconds}s`}
              className="max-h-[70vh] max-w-full rounded-lg"
            />
            {selectedFrame.caption && (
              <p className="max-w-2xl text-center text-sm text-white/90">{selectedFrame.caption}</p>
            )}
            <div className="flex items-center gap-4">
              <span className="text-sm text-white/70">
                {formatTime(selectedFrame.timestamp_seconds)} · {selectedFrame.timestamp_seconds}s
              </span>
              <button
                onClick={() => downloadFrame(selectedFrame)}
                className="rounded-full bg-brand px-5 py-2 text-sm font-semibold text-white transition-colors hover:bg-brand-hover"
              >
                Download
              </button>
            </div>
          </div>

          {selectedIndex < frames.length - 1 && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                setSelectedIndex(selectedIndex + 1);
              }}
              className="absolute right-4 flex h-11 w-11 items-center justify-center rounded-full bg-white/10 text-3xl leading-none text-white transition-colors hover:bg-white/20"
              aria-label="Next frame"
            >
              &#8250;
            </button>
          )}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Verify build and lint**

Run: `cd frontend && npm run build`
Expected: builds successfully.

Run: `npm run lint`
Expected: no errors (only the two expected `@next/next/no-img-element` warnings on the `<img>` tags).

- [ ] **Step 3: Commit**

```bash
git add frontend/components/JobGallery.tsx
git commit -m "feat: add storyboard captions, lightbox subtitle, and transcript tab"
```

---

## Task 7: Full manual walkthrough

**Files:**
- None — verification only.

- [ ] **Step 1: Rebuild the backend stack with the transcript code**

From the repo root:

```bash
docker compose up -d --build
docker compose exec api alembic upgrade head
```

Confirm `alembic upgrade head` applies the new migration cleanly against the running Postgres (adds `transcriptcue`, `frame.caption`, `job.transcript_language`).

- [ ] **Step 2: End-to-end pass with a captioned video**

Start the frontend (`cd frontend && npm run dev`), log in, and submit a URL for a video that has captions (most popular talks/music videos do). When it finishes:
- Confirm the **Storyboard** tab shows caption text under thumbnails.
- Open a frame and confirm the **lightbox shows the caption subtitle** under the image.
- Switch to the **Transcript** tab, confirm the full transcript lists with timestamps, and clicking a line **opens the nearest frame** in the lightbox.
- Download the ZIP and confirm it contains `transcript.txt` alongside the frames.

- [ ] **Step 3: Pass with a caption-less video (best-effort behavior)**

Submit a video with no captions (or one where caption download fails). Confirm:
- The job still **succeeds with frames** (not `failed`).
- The Storyboard shows frames **without** caption text.
- The Transcript tab shows **"No transcript available for this video."**

- [ ] **Step 4: Final checks**

Run: `cd backend && source .venv/bin/activate && pytest -v` → all pass.
Run: `cd frontend && npm run build && npm run lint` → clean (only the expected `no-img-element` warnings).

- [ ] **Step 5: Commit (only if the walkthrough required fixes)**

```bash
git add -A
git commit -m "fix: transcript feature walkthrough adjustments"
```
