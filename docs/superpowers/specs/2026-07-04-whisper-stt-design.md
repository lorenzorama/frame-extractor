# Whisper STT Fallback — Design

## Purpose

When a video has no YouTube captions, transcribe its audio locally with Whisper
(speech-to-text) so the transcript feature still works. This extends the existing
best-effort transcript feature: captions remain the first source; Whisper is a
fallback. It never blocks or fails frame extraction.

## Trigger & flow (worker)

Whisper is a **best-effort fallback, after frame extraction**. In `process_job`:

1. Download video → fetch YouTube captions (existing logic, unchanged).
2. Extract frames.
3. **If no captions were found** (parsed cues empty) AND `whisper_enabled` AND the
   video duration ≤ `whisper_max_duration_seconds`: set job status to the new
   **`transcribing`** state, extract the audio (ffmpeg → 16 kHz mono WAV), transcribe
   with faster-whisper, then **update each `Frame.caption`** from the produced cues,
   insert `TranscriptCue` rows, and set `Job.transcript_language` to the language
   Whisper detected. Then `done`.
4. If captions already existed, Whisper is skipped entirely (no cost).

The entire Whisper block is wrapped in try/except (like the captions block): any
failure, or a duration over the cap, leaves the job succeeding with frames and no
transcript (`transcript_language` stays `null`). `session.rollback()` is called on any
failure inside the block so a failed DB write cannot cascade and fail the job
(consistent with the existing captions best-effort handling).

**Ordering note:** because Whisper runs *after* frame extraction, frames are first
created without captions (when no YouTube captions exist); the Whisper pass then
updates `Frame.caption` for each frame via `caption_for_timestamp(cues, ts)` before the
job reaches `done`. So by the time the frontend loads frames, captions are present.

## Runtime & operational notes

- On CPU, faster-whisper `base` (int8) runs roughly 2–4× faster than real time, so a
  30-minute video takes ~8–15 min. This is a background Celery task; the `transcribing`
  status keeps the user informed and nothing else is blocked.
- The Celery worker must **not** have a short `time_limit`/`soft_time_limit` that would
  kill a ~15-min transcription. Default Celery has no task time limit; this will be
  documented explicitly (do not add one).
- Each Celery prefork process lazy-loads its own model instance (~150 MB for `base`
  int8). With the default concurrency (8), up to 8 concurrent transcriptions ≈ ~1.2 GB
  RAM. Recommend running the worker with lower concurrency (configurable via the
  compose `command`), tuned to the host — documented in the README.

## Schema & config

- **`JobStatus`** gains a `transcribing` value. On Postgres this requires
  `ALTER TYPE jobstatus ADD VALUE 'transcribing'`.
- **`Job.transcript_source`** — new nullable `str` column (`"captions"` | `"whisper"` |
  `null`) so the frontend can show an "Auto-transcribed" indicator. Set to `"captions"`
  when YouTube captions produced cues, `"whisper"` when Whisper did, `null` when no
  transcript.
- Both changes go in one new Alembic migration (`0003`). Otherwise the feature reuses
  `TranscriptCue`, `Frame.caption`, `Job.transcript_language`.

  Note: the existing captions block in `process_job` must also set
  `job.transcript_source = "captions"` when it stores cues, so the indicator is accurate
  for caption-sourced transcripts too.
- **Config** (`app/config.py`, env prefix `YTF_`):
  - `whisper_enabled: bool = True`
  - `whisper_model: str = "base"`
  - `whisper_max_duration_seconds: int = 3600`
  - `whisper_compute_type: str = "int8"`

## New module: `app/whisper.py`

Single responsibility: turn a downloaded video into transcript cues.

- `extract_audio(video_path: str, dest_wav: str) -> None` — ffmpeg extracts a 16 kHz
  mono WAV (`-ac 1 -ar 16000 -vn`), via the shared `_run` helper pattern (raises a
  descriptive error on failure).
- `transcribe_audio(wav_path: str) -> tuple[str | None, list[Cue]]` — lazily loads a
  process-level singleton `WhisperModel(settings.whisper_model,
  compute_type=settings.whisper_compute_type)` (loaded once per worker process, not per
  job), transcribes, and returns `(detected_language, cues)` where each faster-whisper
  segment maps to a `Cue(start, end, text)` — the **same `Cue` NamedTuple** already
  defined in `app/video.py` (imported/reused, not redefined). `text` is stripped.

## Worker integration (`app/tasks.py`)

Reuses `Cue` and `caption_for_timestamp` from `app/video.py`. After the existing frame
loop, add a best-effort Whisper fallback:

```
if not cues and settings.whisper_enabled and duration <= settings.whisper_max_duration_seconds:
    try:
        job.status = JobStatus.transcribing; commit
        extract_audio(source_path, audio_path)
        lang, wcues = transcribe_audio(audio_path)
        if wcues:
            for c in wcues: session.add(TranscriptCue(job_id, c.start, c.end, c.text))
            job.transcript_language = lang
            # update existing frames' captions
            for frame in session frames of this job:
                frame.caption = caption_for_timestamp(wcues, frame.timestamp_seconds)
                session.add(frame)
            commit
    except Exception:
        session.rollback()
then job.status = done; commit
```

`duration` and `cues` are already in scope from the earlier part of `process_job`.

## API

`Frame.caption`, `GET /jobs/{id}/transcript`, and `transcript.txt` in the ZIP already
work regardless of transcript source — a Whisper transcript populates the exact same
tables and endpoints. The only change: `TranscriptResponse` gains a
`source: str | None` field (from `Job.transcript_source`) so the frontend can render the
"Auto-transcribed" indicator.

## Frontend

- **`transcribing` status**: `StatusBadge` gets a blue pill for `transcribing` (same
  family as `downloading`/`extracting`). `JobProgress` shows a "Transcribing audio…"
  label; there is no per-item counter during this phase, so the bar stays full with that
  label. The SSE stream keeps streaming since the status is neither `done` nor `failed`
  (already the terminal-only break condition).
- **Source indicator**: on the Transcript tab, when `source === "whisper"`, show a small
  muted "Auto-transcribed" label; for `"captions"` (or `null`), no special label. The
  frontend `Transcript` type gains `source: string | null` to read the new response
  field.
- Storyboard captions, lightbox subtitle, and transcript list are otherwise unchanged.

## Error handling

- Audio extraction, model load, and transcription are all inside the best-effort
  try/except: any failure, or duration over the cap, → job `done` with frames and no
  transcript (`transcript_language`/`transcript_source` `null`).
- `session.rollback()` on any failure within the Whisper block (mirrors the captions fix)
  so a failed write can't cascade into failing the job.
- Whisper is skipped entirely when captions already produced cues.

## Testing

- **Backend unit tests** (faster-whisper and subprocess mocked — no real model/audio):
  - `transcribe_audio`: mocked `WhisperModel` returning fake segments → correct
    `(language, cues)` mapping with stripped text.
  - `extract_audio`: mocked subprocess → asserts the ffmpeg args (`-ac 1 -ar 16000 -vn`).
  - Worker fallback logic: (a) no captions → Whisper called, `Frame.caption` updated,
    cues + `transcript_language` + `transcript_source="whisper"` set; (b) captions present
    → Whisper skipped; (c) duration over cap → Whisper skipped; (d) Whisper raises → job
    still reaches `done` with null transcript.
- **Frontend**: `transcribing` badge + "Transcribing audio…" label; "Auto-transcribed"
  indicator shows for a Whisper-sourced transcript.
- **Manual verification**: rebuild the worker image (faster-whisper + pre-baked `base`
  model), apply migration `0003`, and run a real job on a video **without** captions to
  see Whisper transcribe end-to-end (status `transcribing` → `done`, captions/transcript
  populated).

## Docker

- Add `faster-whisper` to `backend/requirements.txt`.
- In `backend/Dockerfile`, pre-download the model at build time
  (`RUN python -c "from faster_whisper import WhisperModel; WhisperModel('base', compute_type='int8')"`)
  so the first job doesn't pay a download. Note: this increases the worker image size by
  a few hundred MB.
- Document the recommended lower worker concurrency and the "no short task time-limit"
  note in the README.

## Out of scope

- GPU acceleration (CPU int8 only for this iteration).
- Per-job model-size or language override in the UI (model size is env-configured;
  language is auto-detected).
- Transcribing when captions already exist, or replacing captions with Whisper.
