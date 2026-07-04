# YouTube Frame Extractor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a multi-user web app where a signed-in user submits a YouTube URL + interval/timestamps, and gets extracted JPEG frames back in a gallery with individual/zip download.

**Architecture:** FastAPI backend (auth, jobs, frames APIs) + Celery/Redis worker (yt-dlp download + ffmpeg extraction) + PostgreSQL, all dockerized via docker-compose. Next.js frontend deployed separately on Vercel, talking to the backend over HTTP + SSE.

**Tech Stack:** Python 3.12, FastAPI, SQLModel, Alembic, Celery, Redis, PostgreSQL, yt-dlp, ffmpeg, pytest; Next.js (App Router, TypeScript), React, deployed to Vercel.

## Global Constraints

- Frames are JPEG, quality ~90 (per spec).
- Source videos and frames are **not** auto-deleted (manual cleanup only, per spec).
- Auth is email/password with JWT access tokens (per spec).
- No automatic retry of failed jobs (per spec) — user resubmits manually.
- Job processing must go through Celery + Redis, not in-process background tasks (per spec).
- Timestamps must be validated against actual video duration before frame extraction is queued.

---

## File Structure

```
backend/
  app/
    __init__.py
    main.py              # FastAPI app, router registration, CORS
    config.py             # Settings (env vars): DB URL, Redis URL, JWT secret, data dir
    database.py           # SQLModel engine/session
    models.py              # User, Job, Frame SQLModel tables
    schemas.py             # Pydantic request/response models
    security.py             # password hashing, JWT encode/decode
    dependencies.py          # get_session, get_current_user
    video.py                  # yt-dlp/ffmpeg wrapper functions (get_duration, download_video, extract_frame)
    celery_app.py              # Celery app instance
    tasks.py                    # process_job Celery task
    routers/
      auth.py                    # /auth/signup, /auth/login
      jobs.py                      # /jobs (POST/GET), /jobs/{id}, /jobs/{id}/stream, /jobs/{id}/zip
      frames.py                     # /frames/{id}/image
  alembic/
    env.py
    versions/                        # generated migration(s)
  alembic.ini
  tests/
    conftest.py
    test_security.py
    test_video.py
    test_auth_api.py
    test_jobs_api.py
  requirements.txt
  Dockerfile
docker-compose.yml
frontend/
  (Next.js app: app/, lib/api.ts, components/)
```

---

## Task 1: Backend scaffolding + docker-compose skeleton

**Files:**
- Create: `backend/requirements.txt`
- Create: `backend/app/__init__.py`
- Create: `backend/app/config.py`
- Create: `backend/app/main.py`
- Create: `backend/Dockerfile`
- Create: `docker-compose.yml`
- Create: `.env.example`
- Test: `backend/tests/test_main.py`

**Interfaces:**
- Produces: `app.config.settings` (a `Settings` instance with `.database_url`, `.redis_url`, `.jwt_secret`, `.jwt_algorithm`, `.jwt_expire_minutes`, `.data_dir`, `.cors_origins`), and `app.main.app` (the FastAPI instance) used by every later task.

- [ ] **Step 1: Write `requirements.txt`**

```
fastapi==0.115.0
uvicorn[standard]==0.30.6
sqlmodel==0.0.22
psycopg2-binary==2.9.9
alembic==1.13.2
celery==5.4.0
redis==5.0.8
python-jose[cryptography]==3.3.0
passlib[bcrypt]==1.7.4
python-multipart==0.0.9
yt-dlp==2024.8.6
pydantic-settings==2.4.0
pytest==8.3.2
httpx==0.27.2
pytest-asyncio==0.24.0
```

- [ ] **Step 2: Write `app/config.py`**

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql://postgres:postgres@localhost:5432/youtoframe"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24
    data_dir: str = "/data"
    cors_origins: list[str] = ["http://localhost:3000"]

    model_config = SettingsConfigDict(env_file=".env", env_prefix="YTF_")


settings = Settings()
```

- [ ] **Step 3: Write `app/main.py`**

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings

app = FastAPI(title="youtoframe")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
```

- [ ] **Step 4: Write the failing test**

```python
# backend/tests/test_main.py
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [ ] **Step 5: Run test to verify it fails (module not created yet if run before steps 2-3)**

Run: `cd backend && pip install -r requirements.txt && pytest tests/test_main.py -v`
Expected (before steps 2-3 exist): fails with `ModuleNotFoundError`. After steps 2-3 are in place: PASS.

- [ ] **Step 6: Write `Dockerfile`**

```dockerfile
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY alembic.ini .
COPY alembic ./alembic

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 7: Write `docker-compose.yml`**

```yaml
services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: youtoframe
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data

  redis:
    image: redis:7
    ports:
      - "6379:6379"

  api:
    build: ./backend
    env_file: .env
    ports:
      - "8000:8000"
    depends_on:
      - postgres
      - redis
    volumes:
      - videodata:/data

  worker:
    build: ./backend
    command: celery -A app.celery_app.celery_app worker --loglevel=info
    env_file: .env
    depends_on:
      - postgres
      - redis
    volumes:
      - videodata:/data

volumes:
  pgdata:
  videodata:
```

- [ ] **Step 8: Write `.env.example`**

```
YTF_DATABASE_URL=postgresql://postgres:postgres@postgres:5432/youtoframe
YTF_REDIS_URL=redis://redis:6379/0
YTF_JWT_SECRET=change-me-in-production
YTF_DATA_DIR=/data
YTF_CORS_ORIGINS=["http://localhost:3000"]
```

- [ ] **Step 9: Run test to verify it passes**

Run: `cd backend && pytest tests/test_main.py -v`
Expected: `1 passed`

- [ ] **Step 10: Commit**

```bash
git add backend docker-compose.yml .env.example
git commit -m "feat: scaffold FastAPI backend and docker-compose services"
```

---

## Task 2: Database models, session, and Alembic migration

**Files:**
- Create: `backend/app/database.py`
- Create: `backend/app/models.py`
- Create: `backend/alembic.ini`
- Create: `backend/alembic/env.py`
- Create: `backend/alembic/versions/0001_initial.py`
- Test: `backend/tests/test_models.py`

**Interfaces:**
- Consumes: `app.config.settings.database_url` from Task 1.
- Produces: `app.database.engine`, `app.database.get_session()` (a generator yielding a `Session`), and models `User`, `Job`, `Frame` (SQLModel classes) used by every later backend task.

- [ ] **Step 1: Write `app/models.py`**

```python
from datetime import datetime
from enum import Enum
from typing import Optional

from sqlmodel import Field, SQLModel, JSON, Column


class JobStatus(str, Enum):
    pending = "pending"
    downloading = "downloading"
    extracting = "extracting"
    done = "done"
    failed = "failed"


class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(unique=True, index=True)
    hashed_password: str
    created_at: datetime = Field(default_factory=datetime.utcnow)


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
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Frame(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    job_id: int = Field(foreign_key="job.id", index=True)
    timestamp_seconds: float
    file_path: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
```

- [ ] **Step 2: Write `app/database.py`**

```python
from sqlmodel import create_engine, Session

from app.config import settings

engine = create_engine(settings.database_url, echo=False)


def get_session():
    with Session(engine) as session:
        yield session
```

- [ ] **Step 3: Write the failing test (uses an in-memory SQLite engine, not the real Postgres, to test model definitions in isolation)**

```python
# backend/tests/test_models.py
from sqlmodel import SQLModel, Session, create_engine

from app.models import User, Job, Frame, JobStatus


def make_engine():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return engine


def test_job_requires_interval_or_timestamps_default_status_is_pending():
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

        assert job.status == JobStatus.pending
        assert job.frames_done == 0

        frame = Frame(job_id=job.id, timestamp_seconds=5.0, file_path="/data/1/1/frames/5.jpg")
        session.add(frame)
        session.commit()
        session.refresh(frame)

        assert frame.job_id == job.id
```

- [ ] **Step 4: Run test to verify it fails**

Run: `cd backend && pytest tests/test_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.models'` (before Step 1) — after Step 1-2 exist, proceed to Step 5.

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && pytest tests/test_models.py -v`
Expected: `1 passed`

- [ ] **Step 6: Initialize Alembic and write migration**

Run: `cd backend && alembic init alembic`

Edit `backend/alembic/env.py` — replace the `target_metadata = None` line and add imports at the top:

```python
from app.models import SQLModel  # noqa: E402
from app.config import settings  # noqa: E402

target_metadata = SQLModel.metadata
config.set_main_option("sqlalchemy.url", settings.database_url)
```

Run: `cd backend && alembic revision --autogenerate -m "initial tables"`

This generates `backend/alembic/versions/0001_initial.py` (actual filename will include a hash prefix) containing `create_table` calls for `user`, `job`, `frame`. Verify the generated file has no `TODO` markers and includes all three tables before proceeding.

- [ ] **Step 7: Commit**

```bash
git add backend/app/models.py backend/app/database.py backend/alembic backend/alembic.ini backend/tests/test_models.py
git commit -m "feat: add SQLModel models and Alembic migration"
```

---

## Task 3: Password hashing and JWT security utilities

**Files:**
- Create: `backend/app/security.py`
- Test: `backend/tests/test_security.py`

**Interfaces:**
- Produces: `hash_password(password: str) -> str`, `verify_password(password: str, hashed: str) -> bool`, `create_access_token(user_id: int) -> str`, `decode_access_token(token: str) -> int` (returns `user_id`, raises `jose.JWTError` on invalid/expired token). Used by Task 4 (auth routes) and Task 6 (`get_current_user` dependency).

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_security.py
import pytest
from jose import JWTError

from app.security import (
    hash_password,
    verify_password,
    create_access_token,
    decode_access_token,
)


def test_hash_and_verify_password():
    hashed = hash_password("correct-horse")
    assert hashed != "correct-horse"
    assert verify_password("correct-horse", hashed)
    assert not verify_password("wrong", hashed)


def test_create_and_decode_access_token():
    token = create_access_token(user_id=42)
    assert decode_access_token(token) == 42


def test_decode_invalid_token_raises():
    with pytest.raises(JWTError):
        decode_access_token("not-a-real-token")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_security.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.security'`

- [ ] **Step 3: Write `app/security.py`**

```python
from datetime import datetime, timedelta

from jose import jwt
from passlib.context import CryptContext

from app.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return pwd_context.verify(password, hashed)


def create_access_token(user_id: int) -> str:
    expire = datetime.utcnow() + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {"sub": str(user_id), "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> int:
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    return int(payload["sub"])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_security.py -v`
Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/app/security.py backend/tests/test_security.py
git commit -m "feat: add password hashing and JWT utilities"
```

---

## Task 4: Auth API (signup/login) with test DB fixture

**Files:**
- Create: `backend/tests/conftest.py`
- Create: `backend/app/schemas.py` (auth portion)
- Create: `backend/app/dependencies.py`
- Create: `backend/app/routers/auth.py`
- Modify: `backend/app/main.py:1-20` (register router)
- Test: `backend/tests/test_auth_api.py`

**Interfaces:**
- Consumes: `hash_password`, `verify_password`, `create_access_token` from Task 3; `User` model and `get_session` from Task 2.
- Produces: `app.dependencies.get_session_override_for_tests` pattern (via fixture), `POST /auth/signup`, `POST /auth/login` returning `{"access_token": str, "token_type": "bearer"}`. Fixture `client` in `conftest.py` reused by every later API test task.

- [ ] **Step 1: Write `tests/conftest.py`**

```python
# backend/tests/conftest.py
import pytest
from fastapi.testclient import TestClient
from sqlmodel import SQLModel, Session, create_engine
from sqlmodel.pool import StaticPool

from app.main import app
from app.database import get_session


@pytest.fixture(name="session")
def session_fixture():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture(name="client")
def client_fixture(session):
    def get_session_override():
        return session

    app.dependency_overrides[get_session] = get_session_override
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()
```

- [ ] **Step 2: Write the failing tests**

```python
# backend/tests/test_auth_api.py
def test_signup_then_login(client):
    signup = client.post("/auth/signup", json={"email": "a@example.com", "password": "secret123"})
    assert signup.status_code == 201
    assert "access_token" in signup.json()

    login = client.post("/auth/login", json={"email": "a@example.com", "password": "secret123"})
    assert login.status_code == 200
    assert "access_token" in login.json()


def test_signup_duplicate_email_rejected(client):
    client.post("/auth/signup", json={"email": "a@example.com", "password": "secret123"})
    second = client.post("/auth/signup", json={"email": "a@example.com", "password": "other456"})
    assert second.status_code == 400


def test_login_wrong_password_rejected(client):
    client.post("/auth/signup", json={"email": "a@example.com", "password": "secret123"})
    login = client.post("/auth/login", json={"email": "a@example.com", "password": "wrong"})
    assert login.status_code == 401
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd backend && pytest tests/test_auth_api.py -v`
Expected: FAIL (404s / import errors — routes don't exist yet)

- [ ] **Step 4: Write `app/schemas.py`**

```python
from pydantic import BaseModel, EmailStr


class SignupRequest(BaseModel):
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
```

- [ ] **Step 5: Write `app/dependencies.py`**

```python
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlmodel import Session

from app.database import get_session
from app.models import User
from app.security import decode_access_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def get_current_user(
    token: str = Depends(oauth2_scheme), session: Session = Depends(get_session)
) -> User:
    try:
        user_id = decode_access_token(token)
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user
```

- [ ] **Step 6: Write `app/routers/auth.py`**

```python
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from app.database import get_session
from app.models import User
from app.schemas import SignupRequest, LoginRequest, TokenResponse
from app.security import hash_password, verify_password, create_access_token

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def signup(payload: SignupRequest, session: Session = Depends(get_session)):
    existing = session.exec(select(User).where(User.email == payload.email)).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    user = User(email=payload.email, hashed_password=hash_password(payload.password))
    session.add(user)
    session.commit()
    session.refresh(user)
    return TokenResponse(access_token=create_access_token(user.id))


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, session: Session = Depends(get_session)):
    user = session.exec(select(User).where(User.email == payload.email)).first()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return TokenResponse(access_token=create_access_token(user.id))
```

- [ ] **Step 7: Register router in `app/main.py`**

```python
# add near the top with other imports
from app.routers import auth

# add after middleware setup
app.include_router(auth.router)
```

- [ ] **Step 8: Run test to verify it passes**

Run: `cd backend && pytest tests/test_auth_api.py -v`
Expected: `3 passed`

- [ ] **Step 9: Commit**

```bash
git add backend/tests/conftest.py backend/tests/test_auth_api.py backend/app/schemas.py backend/app/dependencies.py backend/app/routers/auth.py backend/app/main.py
git commit -m "feat: add signup/login auth API"
```

---

## Task 5: Video module (yt-dlp metadata/download + ffmpeg frame extraction)

**Files:**
- Create: `backend/app/video.py`
- Test: `backend/tests/test_video.py`

**Interfaces:**
- Produces: `get_video_duration(url: str) -> float`, `download_video(url: str, dest_path: str) -> None`, `extract_frame(video_path: str, timestamp: float, dest_path: str) -> None`, and `compute_timestamps(duration: float, interval_seconds: float | None, manual_timestamps: list[float] | None) -> list[float]` (sorted, deduplicated, filtered to `0 <= t <= duration`). Used by Task 6 (Celery task).

- [ ] **Step 1: Write the failing tests (subprocess calls are mocked — no real network/ffmpeg needed)**

```python
# backend/tests/test_video.py
from unittest.mock import patch, MagicMock

import pytest

from app.video import get_video_duration, download_video, extract_frame, compute_timestamps


def test_compute_timestamps_interval_only():
    result = compute_timestamps(duration=10.0, interval_seconds=5.0, manual_timestamps=None)
    assert result == [0.0, 5.0, 10.0]


def test_compute_timestamps_merges_manual_and_dedupes():
    result = compute_timestamps(duration=10.0, interval_seconds=5.0, manual_timestamps=[5.0, 7.5])
    assert result == [0.0, 5.0, 7.5, 10.0]


def test_compute_timestamps_rejects_out_of_range():
    with pytest.raises(ValueError):
        compute_timestamps(duration=10.0, interval_seconds=None, manual_timestamps=[15.0])


def test_compute_timestamps_requires_interval_or_manual():
    with pytest.raises(ValueError):
        compute_timestamps(duration=10.0, interval_seconds=None, manual_timestamps=None)


@patch("app.video.subprocess.run")
def test_get_video_duration_parses_yt_dlp_json(mock_run):
    mock_run.return_value = MagicMock(stdout='{"duration": 123.4}', returncode=0)
    duration = get_video_duration("https://youtube.com/watch?v=abc")
    assert duration == 123.4
    assert mock_run.called


@patch("app.video.subprocess.run")
def test_download_video_invokes_yt_dlp(mock_run):
    mock_run.return_value = MagicMock(returncode=0)
    download_video("https://youtube.com/watch?v=abc", "/data/1/1/source.mp4")
    args = mock_run.call_args[0][0]
    assert "yt-dlp" in args
    assert "/data/1/1/source.mp4" in args


@patch("app.video.subprocess.run")
def test_extract_frame_invokes_ffmpeg(mock_run):
    mock_run.return_value = MagicMock(returncode=0)
    extract_frame("/data/1/1/source.mp4", 5.0, "/data/1/1/frames/5.0.jpg")
    args = mock_run.call_args[0][0]
    assert "ffmpeg" in args
    assert "-q:v" in args
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_video.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.video'`

- [ ] **Step 3: Write `app/video.py`**

```python
import json
import subprocess


def compute_timestamps(
    duration: float,
    interval_seconds: float | None,
    manual_timestamps: list[float] | None,
) -> list[float]:
    if interval_seconds is None and not manual_timestamps:
        raise ValueError("Must provide interval_seconds and/or manual_timestamps")

    timestamps: set[float] = set()

    if interval_seconds is not None:
        t = 0.0
        while t < duration:
            timestamps.add(round(t, 3))
            t += interval_seconds
        timestamps.add(round(duration, 3))

    for t in manual_timestamps or []:
        if t < 0 or t > duration:
            raise ValueError(f"Timestamp {t} is outside video duration {duration}")
        timestamps.add(round(t, 3))

    return sorted(timestamps)


def get_video_duration(url: str) -> float:
    result = subprocess.run(
        ["yt-dlp", "--no-warnings", "-j", url],
        capture_output=True,
        text=True,
        check=True,
    )
    data = json.loads(result.stdout)
    return float(data["duration"])


def download_video(url: str, dest_path: str) -> None:
    subprocess.run(
        ["yt-dlp", "--no-warnings", "-f", "mp4", "-o", dest_path, url],
        check=True,
    )


def extract_frame(video_path: str, timestamp: float, dest_path: str) -> None:
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-ss", str(timestamp),
            "-i", video_path,
            "-frames:v", "1",
            "-q:v", "2",
            dest_path,
        ],
        check=True,
        capture_output=True,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_video.py -v`
Expected: `7 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/app/video.py backend/tests/test_video.py
git commit -m "feat: add yt-dlp/ffmpeg video processing module"
```

---

## Task 6: Celery app + `process_job` task

**Files:**
- Create: `backend/app/celery_app.py`
- Create: `backend/app/tasks.py`
- Test: `backend/tests/test_tasks.py`

**Interfaces:**
- Consumes: `get_video_duration`, `download_video`, `extract_frame`, `compute_timestamps` from Task 5; `Job`, `Frame`, `JobStatus` from Task 2; `engine` from `app.database`.
- Produces: `celery_app` (Celery instance), `process_job(job_id: int) -> None` (Celery task, called via `.delay(job_id)` from Task 7's job-creation endpoint).

- [ ] **Step 1: Write `app/celery_app.py`**

```python
from celery import Celery

from app.config import settings

celery_app = Celery("youtoframe", broker=settings.redis_url, backend=settings.redis_url)
```

- [ ] **Step 2: Write the failing test (runs the task function directly, without a broker, mocking the video module)**

```python
# backend/tests/test_tasks.py
import os
from unittest.mock import patch

from sqlmodel import SQLModel, Session, create_engine
from sqlmodel.pool import StaticPool

from app.models import User, Job, Frame, JobStatus


def make_session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    return engine, Session(engine)


@patch("app.tasks.extract_frame")
@patch("app.tasks.download_video")
@patch("app.tasks.get_video_duration", return_value=10.0)
def test_process_job_happy_path(mock_duration, mock_download, mock_extract, tmp_path, monkeypatch):
    from app import tasks

    engine, session = make_session()
    monkeypatch.setattr(tasks, "engine", engine)
    monkeypatch.setattr("app.config.settings.data_dir", str(tmp_path))

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
    assert job.frames_total == 3
    assert job.frames_done == 3

    frames = session.query(Frame).filter(Frame.job_id == job.id).all()
    assert len(frames) == 3
    assert mock_extract.call_count == 3


@patch("app.tasks.download_video", side_effect=RuntimeError("network error"))
@patch("app.tasks.get_video_duration", return_value=10.0)
def test_process_job_failure_sets_status_failed(mock_duration, mock_download, tmp_path, monkeypatch):
    from app import tasks

    engine, session = make_session()
    monkeypatch.setattr(tasks, "engine", engine)
    monkeypatch.setattr("app.config.settings.data_dir", str(tmp_path))

    user = User(email="a@example.com", hashed_password="x")
    session.add(user)
    session.commit()
    session.refresh(user)

    job = Job(user_id=user.id, youtube_url="https://youtube.com/watch?v=bad", interval_seconds=5.0)
    session.add(job)
    session.commit()
    session.refresh(job)

    tasks.process_job(job.id)

    session.refresh(job)
    assert job.status == JobStatus.failed
    assert "network error" in job.error_message
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd backend && pytest tests/test_tasks.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.tasks'`

- [ ] **Step 4: Write `app/tasks.py`**

```python
import os

from sqlmodel import Session

from app.celery_app import celery_app
from app.config import settings
from app.database import engine
from app.models import Job, Frame, JobStatus
from app.video import get_video_duration, download_video, extract_frame, compute_timestamps


@celery_app.task(name="process_job")
def process_job(job_id: int) -> None:
    with Session(engine) as session:
        job = session.get(Job, job_id)
        if not job:
            return

        job_dir = os.path.join(settings.data_dir, str(job.user_id), str(job.id))
        frames_dir = os.path.join(job_dir, "frames")
        os.makedirs(frames_dir, exist_ok=True)
        source_path = os.path.join(job_dir, "source.mp4")

        try:
            job.status = JobStatus.downloading
            session.add(job)
            session.commit()

            duration = get_video_duration(job.youtube_url)
            timestamps = compute_timestamps(duration, job.interval_seconds, job.manual_timestamps)

            download_video(job.youtube_url, source_path)

            job.status = JobStatus.extracting
            job.frames_total = len(timestamps)
            job.frames_done = 0
            session.add(job)
            session.commit()

            for ts in timestamps:
                frame_path = os.path.join(frames_dir, f"{ts}.jpg")
                extract_frame(source_path, ts, frame_path)
                frame = Frame(job_id=job.id, timestamp_seconds=ts, file_path=frame_path)
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

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && pytest tests/test_tasks.py -v`
Expected: `2 passed`

- [ ] **Step 6: Commit**

```bash
git add backend/app/celery_app.py backend/app/tasks.py backend/tests/test_tasks.py
git commit -m "feat: add Celery app and process_job task"
```

---

## Task 7: Jobs API (create, list, status, SSE stream)

**Files:**
- Create: `backend/app/routers/jobs.py`
- Modify: `backend/app/schemas.py` (append job schemas)
- Modify: `backend/app/main.py` (register jobs router)
- Test: `backend/tests/test_jobs_api.py`

**Interfaces:**
- Consumes: `get_current_user`, `get_session` from Task 4; `Job`, `JobStatus` from Task 2; `process_job` from Task 6.
- Produces: `POST /jobs`, `GET /jobs`, `GET /jobs/{id}`, `GET /jobs/{id}/stream` (SSE). Used by Task 8 (frames/zip endpoints share the same router file) and by the frontend.

- [ ] **Step 1: Append to `app/schemas.py`**

```python
from typing import Optional
from datetime import datetime


class JobCreateRequest(BaseModel):
    youtube_url: str
    interval_seconds: Optional[float] = None
    manual_timestamps: Optional[list[float]] = None


class JobResponse(BaseModel):
    id: int
    youtube_url: str
    status: str
    error_message: Optional[str] = None
    frames_total: int
    frames_done: int
    created_at: datetime

    class Config:
        from_attributes = True
```

- [ ] **Step 2: Write the failing tests**

```python
# backend/tests/test_jobs_api.py
from unittest.mock import patch


def signup_and_auth_headers(client, email="a@example.com"):
    resp = client.post("/auth/signup", json={"email": email, "password": "secret123"})
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_create_job_requires_auth(client):
    resp = client.post("/jobs", json={"youtube_url": "https://youtube.com/watch?v=abc", "interval_seconds": 5})
    assert resp.status_code == 401


@patch("app.routers.jobs.process_job")
def test_create_job_requires_interval_or_timestamps(mock_task, client):
    headers = signup_and_auth_headers(client)
    resp = client.post("/jobs", json={"youtube_url": "https://youtube.com/watch?v=abc"}, headers=headers)
    assert resp.status_code == 422


@patch("app.routers.jobs.process_job")
def test_create_job_enqueues_task_and_returns_job(mock_task, client):
    headers = signup_and_auth_headers(client)
    resp = client.post(
        "/jobs",
        json={"youtube_url": "https://youtube.com/watch?v=abc", "interval_seconds": 5},
        headers=headers,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "pending"
    mock_task.delay.assert_called_once_with(body["id"])


@patch("app.routers.jobs.process_job")
def test_list_jobs_only_returns_own_jobs(mock_task, client):
    headers_a = signup_and_auth_headers(client, "a@example.com")
    headers_b = signup_and_auth_headers(client, "b@example.com")

    client.post("/jobs", json={"youtube_url": "https://youtube.com/watch?v=1", "interval_seconds": 5}, headers=headers_a)
    client.post("/jobs", json={"youtube_url": "https://youtube.com/watch?v=2", "interval_seconds": 5}, headers=headers_b)

    resp = client.get("/jobs", headers=headers_a)
    assert resp.status_code == 200
    jobs = resp.json()
    assert len(jobs) == 1
    assert jobs[0]["youtube_url"] == "https://youtube.com/watch?v=1"


@patch("app.routers.jobs.process_job")
def test_get_job_not_owned_returns_404(mock_task, client):
    headers_a = signup_and_auth_headers(client, "a@example.com")
    headers_b = signup_and_auth_headers(client, "b@example.com")

    created = client.post(
        "/jobs", json={"youtube_url": "https://youtube.com/watch?v=1", "interval_seconds": 5}, headers=headers_a
    ).json()

    resp = client.get(f"/jobs/{created['id']}", headers=headers_b)
    assert resp.status_code == 404
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd backend && pytest tests/test_jobs_api.py -v`
Expected: FAIL (404s — router not registered / doesn't exist)

- [ ] **Step 4: Write `app/routers/jobs.py`**

```python
import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlmodel import Session, select

from app.database import get_session
from app.dependencies import get_current_user
from app.models import Job, User
from app.schemas import JobCreateRequest, JobResponse
from app.tasks import process_job

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post("", response_model=JobResponse, status_code=201)
def create_job(
    payload: JobCreateRequest,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    if payload.interval_seconds is None and not payload.manual_timestamps:
        raise HTTPException(status_code=422, detail="Provide interval_seconds and/or manual_timestamps")

    job = Job(
        user_id=user.id,
        youtube_url=payload.youtube_url,
        interval_seconds=payload.interval_seconds,
        manual_timestamps=payload.manual_timestamps,
    )
    session.add(job)
    session.commit()
    session.refresh(job)

    process_job.delay(job.id)

    return job


@router.get("", response_model=list[JobResponse])
def list_jobs(session: Session = Depends(get_session), user: User = Depends(get_current_user)):
    jobs = session.exec(select(Job).where(Job.user_id == user.id).order_by(Job.created_at.desc())).all()
    return jobs


def _get_owned_job(job_id: int, session: Session, user: User) -> Job:
    job = session.get(Job, job_id)
    if not job or job.user_id != user.id:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/{job_id}", response_model=JobResponse)
def get_job(job_id: int, session: Session = Depends(get_session), user: User = Depends(get_current_user)):
    return _get_owned_job(job_id, session, user)


@router.get("/{job_id}/stream")
async def stream_job(job_id: int, session: Session = Depends(get_session), user: User = Depends(get_current_user)):
    _get_owned_job(job_id, session, user)

    async def event_generator():
        while True:
            job = session.get(Job, job_id)
            session.refresh(job)
            payload = {
                "status": job.status,
                "frames_done": job.frames_done,
                "frames_total": job.frames_total,
                "error": job.error_message,
            }
            yield f"data: {json.dumps(payload)}\n\n"
            if job.status in ("done", "failed"):
                break
            await asyncio.sleep(1)

    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

- [ ] **Step 5: Register router in `app/main.py`**

```python
# add with other router imports
from app.routers import jobs

# add after app.include_router(auth.router)
app.include_router(jobs.router)
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd backend && pytest tests/test_jobs_api.py -v`
Expected: `5 passed`

- [ ] **Step 7: Commit**

```bash
git add backend/app/routers/jobs.py backend/app/schemas.py backend/app/main.py backend/tests/test_jobs_api.py
git commit -m "feat: add jobs API with create/list/get/SSE stream"
```

---

## Task 8: Frames API (list, image serving, zip download)

**Files:**
- Create: `backend/app/routers/frames.py`
- Modify: `backend/app/routers/jobs.py` (add `/jobs/{id}/frames` and `/jobs/{id}/zip`)
- Modify: `backend/app/schemas.py` (append `FrameResponse`)
- Modify: `backend/app/main.py` (register frames router)
- Test: `backend/tests/test_frames_api.py`

**Interfaces:**
- Consumes: `_get_owned_job` from Task 7's `jobs.py`; `Frame` model from Task 2.
- Produces: `GET /jobs/{id}/frames`, `GET /jobs/{id}/zip`, `GET /frames/{id}/image`. Used by the frontend gallery.

- [ ] **Step 1: Append to `app/schemas.py`**

```python
class FrameResponse(BaseModel):
    id: int
    timestamp_seconds: float

    class Config:
        from_attributes = True
```

- [ ] **Step 2: Write the failing tests**

```python
# backend/tests/test_frames_api.py
import os
from unittest.mock import patch


def signup_and_auth_headers(client, email="a@example.com"):
    resp = client.post("/auth/signup", json={"email": email, "password": "secret123"})
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@patch("app.routers.jobs.process_job")
def test_list_frames_for_job(mock_task, client, session):
    from app.models import Frame

    headers = signup_and_auth_headers(client)
    job = client.post(
        "/jobs", json={"youtube_url": "https://youtube.com/watch?v=abc", "interval_seconds": 5}, headers=headers
    ).json()

    frame = Frame(job_id=job["id"], timestamp_seconds=5.0, file_path="/tmp/does-not-matter.jpg")
    session.add(frame)
    session.commit()

    resp = client.get(f"/jobs/{job['id']}/frames", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == [{"id": frame.id, "timestamp_seconds": 5.0}]


@patch("app.routers.jobs.process_job")
def test_get_frame_image_returns_file(mock_task, client, session, tmp_path):
    from app.models import Frame

    headers = signup_and_auth_headers(client)
    job = client.post(
        "/jobs", json={"youtube_url": "https://youtube.com/watch?v=abc", "interval_seconds": 5}, headers=headers
    ).json()

    image_path = tmp_path / "frame.jpg"
    image_path.write_bytes(b"\xff\xd8\xff\xd9")

    frame = Frame(job_id=job["id"], timestamp_seconds=5.0, file_path=str(image_path))
    session.add(frame)
    session.commit()
    session.refresh(frame)

    resp = client.get(f"/frames/{frame.id}/image", headers=headers)
    assert resp.status_code == 200
    assert resp.content == b"\xff\xd8\xff\xd9"


@patch("app.routers.jobs.process_job")
def test_get_frame_image_not_owned_returns_404(mock_task, client, session, tmp_path):
    from app.models import Frame

    headers_a = signup_and_auth_headers(client, "a@example.com")
    headers_b = signup_and_auth_headers(client, "b@example.com")

    job = client.post(
        "/jobs", json={"youtube_url": "https://youtube.com/watch?v=abc", "interval_seconds": 5}, headers=headers_a
    ).json()

    image_path = tmp_path / "frame.jpg"
    image_path.write_bytes(b"\xff\xd8\xff\xd9")
    frame = Frame(job_id=job["id"], timestamp_seconds=5.0, file_path=str(image_path))
    session.add(frame)
    session.commit()
    session.refresh(frame)

    resp = client.get(f"/frames/{frame.id}/image", headers=headers_b)
    assert resp.status_code == 404
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd backend && pytest tests/test_frames_api.py -v`
Expected: FAIL (404s — routes don't exist yet)

- [ ] **Step 4: Write `app/routers/frames.py`**

```python
import os

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlmodel import Session

from app.database import get_session
from app.dependencies import get_current_user
from app.models import Frame, Job, User

router = APIRouter(prefix="/frames", tags=["frames"])


@router.get("/{frame_id}/image")
def get_frame_image(
    frame_id: int, session: Session = Depends(get_session), user: User = Depends(get_current_user)
):
    frame = session.get(Frame, frame_id)
    if not frame:
        raise HTTPException(status_code=404, detail="Frame not found")
    job = session.get(Job, frame.job_id)
    if not job or job.user_id != user.id:
        raise HTTPException(status_code=404, detail="Frame not found")
    if not os.path.exists(frame.file_path):
        raise HTTPException(status_code=404, detail="Frame file missing")
    return FileResponse(frame.file_path, media_type="image/jpeg")
```

- [ ] **Step 5: Append frame-listing and zip endpoints to `app/routers/jobs.py`**

```python
# add imports at top of jobs.py (StreamingResponse is already imported there from Task 7)
import io
import zipfile

from app.models import Frame
from app.schemas import FrameResponse

# add at bottom of jobs.py
@router.get("/{job_id}/frames", response_model=list[FrameResponse])
def list_frames(job_id: int, session: Session = Depends(get_session), user: User = Depends(get_current_user)):
    _get_owned_job(job_id, session, user)
    frames = session.exec(select(Frame).where(Frame.job_id == job_id).order_by(Frame.timestamp_seconds)).all()
    return frames


@router.get("/{job_id}/zip")
def download_zip(job_id: int, session: Session = Depends(get_session), user: User = Depends(get_current_user)):
    _get_owned_job(job_id, session, user)
    frames = session.exec(select(Frame).where(Frame.job_id == job_id).order_by(Frame.timestamp_seconds)).all()

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        for frame in frames:
            zf.write(frame.file_path, arcname=f"{frame.timestamp_seconds}.jpg")
    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename=job_{job_id}_frames.zip"},
    )
```

- [ ] **Step 6: Register frames router in `app/main.py`**

```python
from app.routers import frames

app.include_router(frames.router)
```

- [ ] **Step 7: Run test to verify it passes**

Run: `cd backend && pytest tests/test_frames_api.py -v`
Expected: `3 passed`

- [ ] **Step 8: Run the full backend test suite**

Run: `cd backend && pytest -v`
Expected: all tests pass (roughly 21 tests across all files)

- [ ] **Step 9: Commit**

```bash
git add backend/app/routers/frames.py backend/app/routers/jobs.py backend/app/schemas.py backend/app/main.py backend/tests/test_frames_api.py
git commit -m "feat: add frame listing, image serving, and zip download endpoints"
```

---

## Task 9: Frontend scaffold + auth pages

**Files:**
- Create: `frontend/` (via `create-next-app`)
- Create: `frontend/lib/api.ts`
- Create: `frontend/app/login/page.tsx`
- Create: `frontend/app/signup/page.tsx`
- Create: `frontend/.env.local.example`

**Interfaces:**
- Produces: `apiFetch(path: string, options?: RequestInit) -> Promise<Response>` (attaches JWT from localStorage, prefixes `NEXT_PUBLIC_API_URL`), `login(email, password)`, `signup(email, password)` (both store the token in `localStorage.access_token` and return void). Used by every later frontend task.

- [ ] **Step 1: Scaffold the app**

Run: `npx create-next-app@latest frontend --typescript --eslint --app --src-dir=false --tailwind --import-alias "@/*"`

- [ ] **Step 2: Write `frontend/.env.local.example`**

```
NEXT_PUBLIC_API_URL=http://localhost:8000
```

- [ ] **Step 3: Write `frontend/lib/api.ts`**

```typescript
const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("access_token");
}

export async function apiFetch(path: string, options: RequestInit = {}): Promise<Response> {
  const token = getToken();
  const headers = new Headers(options.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (options.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  return fetch(`${API_URL}${path}`, { ...options, headers });
}

async function authRequest(path: string, email: string, password: string): Promise<void> {
  const res = await apiFetch(path, {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: "Request failed" }));
    throw new Error(body.detail || "Request failed");
  }
  const data = await res.json();
  localStorage.setItem("access_token", data.access_token);
}

export function login(email: string, password: string): Promise<void> {
  return authRequest("/auth/login", email, password);
}

export function signup(email: string, password: string): Promise<void> {
  return authRequest("/auth/signup", email, password);
}
```

- [ ] **Step 4: Write `frontend/app/login/page.tsx`**

```tsx
"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { login } from "@/lib/api";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const router = useRouter();

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await login(email, password);
      router.push("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    }
  }

  return (
    <main className="max-w-sm mx-auto mt-20">
      <h1 className="text-xl font-semibold mb-4">Log in</h1>
      <form onSubmit={handleSubmit} className="flex flex-col gap-3">
        <input
          type="email"
          placeholder="Email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="border rounded px-3 py-2"
          required
        />
        <input
          type="password"
          placeholder="Password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="border rounded px-3 py-2"
          required
        />
        {error && <p className="text-red-600 text-sm">{error}</p>}
        <button type="submit" className="bg-black text-white rounded px-3 py-2">
          Log in
        </button>
      </form>
    </main>
  );
}
```

- [ ] **Step 5: Write `frontend/app/signup/page.tsx`**

```tsx
"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { signup } from "@/lib/api";

export default function SignupPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const router = useRouter();

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await signup(email, password);
      router.push("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Signup failed");
    }
  }

  return (
    <main className="max-w-sm mx-auto mt-20">
      <h1 className="text-xl font-semibold mb-4">Sign up</h1>
      <form onSubmit={handleSubmit} className="flex flex-col gap-3">
        <input
          type="email"
          placeholder="Email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="border rounded px-3 py-2"
          required
        />
        <input
          type="password"
          placeholder="Password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="border rounded px-3 py-2"
          required
        />
        {error && <p className="text-red-600 text-sm">{error}</p>}
        <button type="submit" className="bg-black text-white rounded px-3 py-2">
          Sign up
        </button>
      </form>
    </main>
  );
}
```

- [ ] **Step 6: Manually verify**

Run: `cd frontend && npm run dev`, open `http://localhost:3000/signup`, submit a test account (with the backend running via `docker compose up`), confirm `localStorage.access_token` is set (check DevTools) and the page navigates to `/`.

- [ ] **Step 7: Commit**

```bash
git add frontend
git commit -m "feat: scaffold Next.js frontend with login/signup pages"
```

---

## Task 10: Job submission form + job list page

**Files:**
- Create: `frontend/lib/jobs.ts`
- Create: `frontend/app/page.tsx`
- Create: `frontend/components/JobForm.tsx`

**Interfaces:**
- Consumes: `apiFetch` from Task 9.
- Produces: `createJob(input)`, `listJobs()`, `Job` TypeScript type — consumed by Task 11 (progress view) and Task 12 (gallery).

- [ ] **Step 1: Write `frontend/lib/jobs.ts`**

```typescript
import { apiFetch } from "@/lib/api";

export interface Job {
  id: number;
  youtube_url: string;
  status: "pending" | "downloading" | "extracting" | "done" | "failed";
  error_message: string | null;
  frames_total: number;
  frames_done: number;
  created_at: string;
}

export interface CreateJobInput {
  youtube_url: string;
  interval_seconds?: number;
  manual_timestamps?: number[];
}

export async function createJob(input: CreateJobInput): Promise<Job> {
  const res = await apiFetch("/jobs", { method: "POST", body: JSON.stringify(input) });
  if (!res.ok) throw new Error((await res.json()).detail || "Failed to create job");
  return res.json();
}

export async function listJobs(): Promise<Job[]> {
  const res = await apiFetch("/jobs");
  if (!res.ok) throw new Error("Failed to list jobs");
  return res.json();
}
```

- [ ] **Step 2: Write `frontend/components/JobForm.tsx`**

```tsx
"use client";

import { useState } from "react";
import { createJob } from "@/lib/jobs";

export default function JobForm({ onCreated }: { onCreated: (jobId: number) => void }) {
  const [url, setUrl] = useState("");
  const [interval, setInterval_] = useState("5");
  const [timestamps, setTimestamps] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const manual = timestamps
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean)
        .map(Number);
      const job = await createJob({
        youtube_url: url,
        interval_seconds: interval ? Number(interval) : undefined,
        manual_timestamps: manual.length ? manual : undefined,
      });
      onCreated(job.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create job");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-3 max-w-md">
      <input
        placeholder="YouTube URL"
        value={url}
        onChange={(e) => setUrl(e.target.value)}
        className="border rounded px-3 py-2"
        required
      />
      <input
        placeholder="Interval seconds (e.g. 5)"
        value={interval}
        onChange={(e) => setInterval_(e.target.value)}
        className="border rounded px-3 py-2"
      />
      <input
        placeholder="Manual timestamps, comma-separated (e.g. 12.5, 30)"
        value={timestamps}
        onChange={(e) => setTimestamps(e.target.value)}
        className="border rounded px-3 py-2"
      />
      {error && <p className="text-red-600 text-sm">{error}</p>}
      <button type="submit" disabled={submitting} className="bg-black text-white rounded px-3 py-2 disabled:opacity-50">
        {submitting ? "Submitting..." : "Extract frames"}
      </button>
    </form>
  );
}
```

- [ ] **Step 3: Write `frontend/app/page.tsx`**

```tsx
"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import JobForm from "@/components/JobForm";
import { listJobs, Job } from "@/lib/jobs";
import { getToken } from "@/lib/api";

export default function HomePage() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const router = useRouter();

  useEffect(() => {
    if (!getToken()) {
      router.push("/login");
      return;
    }
    listJobs().then(setJobs).catch(() => {});
  }, [router]);

  return (
    <main className="max-w-2xl mx-auto mt-12 px-4">
      <h1 className="text-xl font-semibold mb-6">New extraction job</h1>
      <JobForm onCreated={(jobId) => router.push(`/jobs/${jobId}`)} />

      <h2 className="text-lg font-semibold mt-10 mb-3">Your jobs</h2>
      <ul className="flex flex-col gap-2">
        {jobs.map((job) => (
          <li key={job.id}>
            <a href={`/jobs/${job.id}`} className="underline">
              #{job.id} — {job.youtube_url} — {job.status}
            </a>
          </li>
        ))}
      </ul>
    </main>
  );
}
```

- [ ] **Step 4: Manually verify**

Run: `cd frontend && npm run dev` with backend running, log in, submit a job on `/`, confirm it appears in "Your jobs" (route to `/jobs/{id}` will 404 until Task 11 — that's expected here).

- [ ] **Step 5: Commit**

```bash
git add frontend/lib/jobs.ts frontend/app/page.tsx frontend/components/JobForm.tsx
git commit -m "feat: add job submission form and job list"
```

---

## Task 11: Job progress page (SSE)

**Files:**
- Create: `frontend/app/jobs/[id]/page.tsx`
- Create: `frontend/components/JobProgress.tsx`

**Interfaces:**
- Consumes: `Job` type from Task 10; native browser `EventSource` against `/jobs/{id}/stream`.
- Produces: renders live status; on `status === "done"`, renders the gallery component built in Task 12 (imported here).

- [ ] **Step 1: Write `frontend/components/JobProgress.tsx`**

```tsx
"use client";

import { useEffect, useState } from "react";
import { getToken } from "@/lib/api";

interface StreamEvent {
  status: string;
  frames_done: number;
  frames_total: number;
  error: string | null;
}

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function JobProgress({ jobId, onDone }: { jobId: number; onDone: () => void }) {
  const [event, setEvent] = useState<StreamEvent | null>(null);

  useEffect(() => {
    const token = getToken();
    const source = new EventSource(`${API_URL}/jobs/${jobId}/stream?token=${token}`);

    source.onmessage = (e) => {
      const data: StreamEvent = JSON.parse(e.data);
      setEvent(data);
      if (data.status === "done") {
        source.close();
        onDone();
      } else if (data.status === "failed") {
        source.close();
      }
    };

    return () => source.close();
  }, [jobId, onDone]);

  if (!event) return <p>Connecting...</p>;

  if (event.status === "failed") {
    return <p className="text-red-600">Failed: {event.error}</p>;
  }

  return (
    <p>
      Status: {event.status} — {event.frames_done}/{event.frames_total} frames
    </p>
  );
}
```

> **Note:** `EventSource` cannot set an `Authorization` header, so the SSE endpoint must also accept the token as a query parameter. Add this to `backend/app/routers/jobs.py`'s `stream_job` in this task (not a separate backend task, since it's required for this frontend feature to work):

- [ ] **Step 2: Modify `backend/app/routers/jobs.py`'s `stream_job` to accept a query-param token**

```python
# replace the stream_job signature and its auth line
from fastapi import Query
from app.security import decode_access_token
from app.models import User


@router.get("/{job_id}/stream")
async def stream_job(
    job_id: int,
    token: str = Query(...),
    session: Session = Depends(get_session),
):
    user_id = decode_access_token(token)
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid token")
    _get_owned_job(job_id, session, user)
    # ... rest unchanged
```

- [ ] **Step 3: Write `frontend/app/jobs/[id]/page.tsx`**

```tsx
"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import JobProgress from "@/components/JobProgress";
import JobGallery from "@/components/JobGallery";

export default function JobPage() {
  const params = useParams();
  const jobId = Number(params.id);
  const [done, setDone] = useState(false);

  return (
    <main className="max-w-2xl mx-auto mt-12 px-4">
      <h1 className="text-xl font-semibold mb-6">Job #{jobId}</h1>
      {!done && <JobProgress jobId={jobId} onDone={() => setDone(true)} />}
      {done && <JobGallery jobId={jobId} />}
    </main>
  );
}
```

(`JobGallery` is built in Task 12 — this task's manual verification will show a "module not found" until then; that's expected.)

- [ ] **Step 4: Manually verify the backend change**

Run: `cd backend && pytest tests/test_jobs_api.py -v` (confirm the `Depends(get_current_user)` removal from `stream_job` didn't break other job tests, since `stream_job` now authenticates manually via query param)

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/jobs.py frontend/app/jobs frontend/components/JobProgress.tsx
git commit -m "feat: add SSE-based job progress page"
```

---

## Task 12: Frame gallery + downloads

**Files:**
- Create: `frontend/components/JobGallery.tsx`
- Modify: `frontend/lib/jobs.ts` (append `listFrames`, image/zip URL helpers)

**Interfaces:**
- Consumes: `apiFetch`, `getToken` from Task 9; `GET /jobs/{id}/frames`, `GET /frames/{id}/image`, `GET /jobs/{id}/zip` from Task 8.
- Produces: `JobGallery` component, consumed by Task 11's `app/jobs/[id]/page.tsx`.

- [ ] **Step 1: Append to `frontend/lib/jobs.ts`**

```typescript
export interface Frame {
  id: number;
  timestamp_seconds: number;
}

export async function listFrames(jobId: number): Promise<Frame[]> {
  const res = await apiFetch(`/jobs/${jobId}/frames`);
  if (!res.ok) throw new Error("Failed to list frames");
  return res.json();
}
```

- [ ] **Step 2: Write `frontend/components/JobGallery.tsx`**

```tsx
"use client";

import { useEffect, useState } from "react";
import { listFrames, Frame } from "@/lib/jobs";
import { getToken } from "@/lib/api";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function JobGallery({ jobId }: { jobId: number }) {
  const [frames, setFrames] = useState<Frame[]>([]);
  const [imageUrls, setImageUrls] = useState<Record<number, string>>({});

  useEffect(() => {
    listFrames(jobId).then(setFrames).catch(() => {});
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

  return (
    <div>
      <button onClick={downloadZip} className="bg-black text-white rounded px-3 py-2 mb-4">
        Download all as ZIP
      </button>
      <div className="grid grid-cols-3 gap-3">
        {frames.map((frame) => (
          <div key={frame.id} className="flex flex-col items-center">
            {imageUrls[frame.id] ? (
              <img src={imageUrls[frame.id]} alt={`Frame at ${frame.timestamp_seconds}s`} className="rounded" />
            ) : (
              <div className="bg-gray-200 w-full aspect-video rounded animate-pulse" />
            )}
            <a href={imageUrls[frame.id]} download={`${frame.timestamp_seconds}.jpg`} className="text-sm underline mt-1">
              {frame.timestamp_seconds}s
            </a>
          </div>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Manually verify end-to-end**

Run: `docker compose up --build` (backend + worker + postgres + redis), then `cd frontend && npm run dev`. Sign up, submit a short real YouTube video URL with `interval_seconds=5`, watch the progress update via SSE, confirm the gallery renders thumbnails once done, and confirm both individual image download and "Download all as ZIP" work.

- [ ] **Step 4: Commit**

```bash
git add frontend/lib/jobs.ts frontend/components/JobGallery.tsx
git commit -m "feat: add frame gallery with individual and zip downloads"
```

---

## Task 13: README and end-to-end docker-compose verification

**Files:**
- Create: `README.md` (replace placeholder content)

**Interfaces:**
- None — this task documents and verifies the system built in Tasks 1-12.

- [ ] **Step 1: Write `README.md`**

```markdown
# youtoframe

Extract frames from YouTube videos at a fixed interval and/or specific timestamps, via a web app.

## Architecture

- `backend/` — FastAPI + Celery + PostgreSQL + Redis (see `docker-compose.yml`)
- `frontend/` — Next.js app, deployable to Vercel

## Local development

1. Copy env files: `cp .env.example .env` and `cp frontend/.env.local.example frontend/.env.local`
2. Start the backend stack: `docker compose up --build`
3. Run migrations: `docker compose exec api alembic upgrade head`
4. Start the frontend: `cd frontend && npm install && npm run dev`
5. Open `http://localhost:3000`, sign up, and submit a YouTube URL with an interval (seconds) and/or comma-separated manual timestamps.

## Backend tests

```bash
cd backend
pip install -r requirements.txt
pytest -v
```

## Notes

- Extracted frames and source videos are kept on disk (`videodata` Docker volume) until manually cleared.
- Failed jobs are not automatically retried — resubmit from the UI.
```

- [ ] **Step 2: Run full backend test suite one more time**

Run: `cd backend && pytest -v`
Expected: all tests pass

- [ ] **Step 3: Run the full stack manually**

Run: `docker compose up --build`, then `docker compose exec api alembic upgrade head`, then start the frontend and do a full manual pass (signup → login → submit job with a short real video → watch SSE progress → view gallery → download zip → download single image).

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: add setup and usage instructions"
```
