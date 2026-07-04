# YouTube Frame Extractor — Design

## Purpose

A web app where a signed-in user pastes a YouTube URL, specifies a frame interval and/or manual timestamps, and gets back the extracted frames as JPEG images they can browse and download individually or as a zip.

## Architecture

- **Frontend**: Next.js, deployed on Vercel. Handles auth (login/signup), job submission (YouTube URL + interval/timestamps), live job progress via SSE, and a results gallery with per-image and bulk (zip) download.
- **Backend**: FastAPI, dockerized, run via docker-compose alongside:
  - **PostgreSQL** — users, jobs, frame metadata
  - **Redis** — Celery broker/result backend
  - **Celery worker(s)** — run yt-dlp download + ffmpeg frame extraction as background tasks
- **Frame delivery**: extracted frames stored on a shared disk volume (mounted into both API and worker containers), served to the frontend via authenticated FastAPI endpoints (never directly from disk).
- **Auth**: email/password, JWT access tokens. FastAPI issues and validates them; Next.js stores the token and attaches it to API calls.

## Data model

- **User**: `id`, `email`, `hashed_password`, `created_at`
- **Job**: `id`, `user_id` (FK), `youtube_url`, `interval_seconds` (nullable), `manual_timestamps` (JSON array of seconds, nullable), `status` (`pending` / `downloading` / `extracting` / `done` / `failed`), `error_message`, `created_at`
  - At least one of `interval_seconds` or `manual_timestamps` must be set; both can be combined (interval grid plus extra manual points).
- **Frame**: `id`, `job_id` (FK), `timestamp_seconds`, `file_path`, `created_at`

## Job flow

1. User submits URL + interval/timestamps. API creates a `Job` (status `pending`), enqueues a Celery task, returns `job_id`.
2. Frontend opens an SSE connection to `/jobs/{id}/stream` for live status updates.
3. Celery worker:
   - `downloading` — yt-dlp fetches the video into a per-job temp path (`/data/{user_id}/{job_id}/source.mp4`), and reads video duration for timestamp validation.
   - `extracting` — ffmpeg pulls each computed timestamp as a JPEG into `/data/{user_id}/{job_id}/frames/`, inserting a `Frame` row per output; progress emitted as each frame completes.
   - `done` — job marked complete. Per user preference, the source video and frames are **not** auto-deleted; cleanup is manual (may be revisited later).
   - `failed` — error captured and surfaced via SSE.
4. Frontend gallery calls `/jobs/{id}/frames` for the list, renders thumbnails from `/frames/{frame_id}/image`, and offers `/jobs/{id}/zip` for bulk download.

## API surface

- `POST /auth/signup`, `POST /auth/login` → JWT
- `POST /jobs` — `{youtube_url, interval_seconds?, manual_timestamps?}` → `{job_id}`
- `GET /jobs/{id}/stream` — SSE progress (`status`, `frames_done/total`, `error`)
- `GET /jobs/{id}` — job status snapshot (fallback for non-SSE clients)
- `GET /jobs/{id}/frames` — list of frame metadata
- `GET /frames/{id}/image` — serves one JPEG (auth-checked against job owner)
- `GET /jobs/{id}/zip` — streams a zip of all frames
- `GET /jobs` — list current user's jobs/history

## Error handling

- Invalid/unreachable YouTube URL → job fails fast with a clear `error_message` (e.g. "video unavailable/private"), surfaced over SSE.
- Timestamps beyond video duration → validated against video length (from yt-dlp metadata) before creating frame tasks; out-of-range timestamps are rejected with a message rather than silently skipped.
- Worker crash mid-job → Celery task failure sets job to `failed` with the exception message. No automatic retry (avoids silently re-downloading large videos) — user resubmits manually.
- Auth errors → standard 401 responses; frontend redirects to login.

## Testing

- Backend: pytest for API endpoints (auth, job creation/validation) and for the ffmpeg/yt-dlp wrapper functions (mockable), using a test Postgres via docker-compose.
- Frontend: component tests for the job form and gallery; a manual smoke test of the full flow against a short real YouTube video.

## Deployment

- Backend (FastAPI + Celery worker + Postgres + Redis) via `docker-compose`.
- Frontend (Next.js) deployed to Vercel, configured with the backend's public API URL.

## Out of scope (for this iteration)

- Automatic cleanup/expiry of stored videos and frames.
- OAuth login providers.
- Horizontal scaling / multi-replica API (single API + worker container is sufficient for now).
