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
- When deploying, set `YTF_CORS_ORIGINS` to the frontend's exact production origin (e.g. the Vercel deployment URL) instead of leaving it at the localhost default.
