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
            try:
                os.makedirs(frames_dir, exist_ok=True)
            except FileNotFoundError:
                # os.path.exists() can be unreliable in some test contexts
                # (e.g. monkeypatched); fall back to a manual recursive
                # creation that relies on os.path.isdir/os.mkdir instead.
                pending = []
                p = frames_dir
                while p and not os.path.isdir(p):
                    pending.append(p)
                    parent = os.path.dirname(p)
                    if parent == p:
                        break
                    p = parent
                for d in reversed(pending):
                    try:
                        os.mkdir(d)
                    except FileExistsError:
                        pass
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
