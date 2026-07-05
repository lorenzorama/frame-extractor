import os

from sqlmodel import Session, select

from app.celery_app import celery_app
from app.config import settings
from app.database import engine
from app.dispatch import dispatch_next
from app.models import Job, Frame, JobStatus, TranscriptCue
from app.output_save import maybe_save_output
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


@celery_app.task(name="process_job")
def process_job(job_id: int) -> None:
    user_id = None
    try:
        with Session(engine) as session:
            job = session.get(Job, job_id)
            if not job:
                return
            user_id = job.user_id

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
                            job.transcript_source = "captions"
                            session.add(job)
                            session.commit()
                except Exception:
                    cues = []
                    session.rollback()

                job.status = JobStatus.extracting
                job.frames_total = len(timestamps)
                job.frames_done = 0
                session.add(job)
                session.commit()

                for ts in timestamps:
                    frame_path = os.path.join(frames_dir, f"{ts}.jpg")
                    try:
                        extract_frame(source_path, ts, frame_path)
                    except Exception:
                        # A single frame that can't be extracted (e.g. a seek
                        # landing past the last decodable video frame near EOF)
                        # must not fail the whole job — skip it and continue.
                        continue
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

                if job.frames_done == 0:
                    raise RuntimeError("No frames could be extracted from the video")

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
                # Best-effort: write the result zip to the output folder if opted
                # in. maybe_save_output swallows its own errors and returns None,
                # so it can never flip the just-finished job to failed.
                maybe_save_output(session, job, settings.output_dir)
            except Exception as exc:
                job.status = JobStatus.failed
                job.error_message = str(exc)
                session.add(job)
                session.commit()
    finally:
        if user_id is not None:
            try:
                dispatch_next(user_id)
            except Exception:
                pass  # best-effort: chaining failure must not crash the worker
