import io
import json
import time
import zipfile

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlmodel import Session, select

from app.database import engine, get_session
from app.dependencies import get_current_user
from app.models import Frame, Job, User
from app.schemas import FrameResponse, JobCreateRequest, JobResponse
from app.security import decode_access_token
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
async def stream_job(job_id: int, token: str = Query(...), session: Session = Depends(get_session)):
    user_id = decode_access_token(token)
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid token")
    _get_owned_job(job_id, session, user)

    def event_generator():
        with Session(engine) as gen_session:
            while True:
                job = gen_session.get(Job, job_id)
                gen_session.refresh(job)
                payload = {
                    "status": job.status,
                    "frames_done": job.frames_done,
                    "frames_total": job.frames_total,
                    "error": job.error_message,
                }
                yield f"data: {json.dumps(payload)}\n\n"
                if job.status in ("done", "failed"):
                    break
                time.sleep(1)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


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
