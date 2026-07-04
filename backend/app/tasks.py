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
