# Frame Extractor

Extract frames from a video (e.g. a YouTube URL) at a fixed interval and/or specific timestamps, via a web app. See the [Legal & disclaimer](#legal--disclaimer) section before using.

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
- When deploying, set `YTF_CORS_ORIGINS` to the frontend's exact production origin (e.g. the Vercel deployment URL) instead of leaving it at the localhost default.
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

## Legal & disclaimer

This project is provided as-is, for extracting frames from videos you own or are
otherwise authorized to use.

- **No affiliation.** This tool is independent and is **not** affiliated with, endorsed
  by, or sponsored by YouTube or Google LLC. "YouTube" is a trademark of Google LLC; it
  is referenced only to describe compatibility.
- **Your responsibility.** Downloading videos may violate the source platform's Terms of
  Service, and videos and their individual frames are typically protected by copyright.
  You are solely responsible for ensuring you have the rights to process any content you
  submit and for complying with applicable law and platform terms. Do not use this tool to
  download or redistribute content you do not own or are not licensed to use.
- **Not legal advice.** If you intend to operate this as a public or commercial service,
  consult a qualified lawyer first — facilitating third-party downloads of copyrighted
  content carries real legal risk.
