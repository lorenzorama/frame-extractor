import io
import json
import time

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import StreamingResponse
from jose import JWTError
from sqlmodel import Session, select

from app.database import engine, get_session
from app.dependencies import get_current_user
from app.dispatch import dispatch_next
from app.models import Frame, Job, JobStatus, TranscriptCue, User
from app.schemas import FrameResponse, JobCreateRequest, JobResponse, TranscriptResponse
from app.security import decode_access_token
from app.zipbuilder import build_job_zip_bytes

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post("", response_model=list[JobResponse], status_code=201)
def create_jobs(
    payload: JobCreateRequest,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    urls = [u.strip() for u in payload.youtube_urls if u.strip()]
    if not urls:
        raise HTTPException(status_code=422, detail="Provide at least one YouTube URL")
    if len(urls) > 50:
        raise HTTPException(status_code=422, detail="Too many URLs (max 50 per batch)")
    if payload.interval_seconds is None and not payload.manual_timestamps:
        raise HTTPException(status_code=422, detail="Provide interval_seconds and/or manual_timestamps")

    jobs = []
    for url in urls:
        job = Job(
            user_id=user.id,
            youtube_url=url,
            interval_seconds=payload.interval_seconds,
            manual_timestamps=payload.manual_timestamps,
            status=JobStatus.waiting,
        )
        session.add(job)
        jobs.append(job)
    session.commit()
    for job in jobs:
        session.refresh(job)

    dispatch_next(user.id)

    return jobs


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


@router.delete("/{job_id}", status_code=204)
def cancel_job(job_id: int, session: Session = Depends(get_session), user: User = Depends(get_current_user)):
    job = _get_owned_job(job_id, session, user)
    if job.status != JobStatus.waiting:
        raise HTTPException(status_code=409, detail="Only waiting jobs can be cancelled")
    session.delete(job)
    session.commit()
    return Response(status_code=204)


@router.get("/{job_id}/stream")
async def stream_job(job_id: int, token: str = Query(...), session: Session = Depends(get_session)):
    try:
        user_id = decode_access_token(token)
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
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


@router.get("/{job_id}/transcript", response_model=TranscriptResponse)
def get_transcript(job_id: int, session: Session = Depends(get_session), user: User = Depends(get_current_user)):
    job = _get_owned_job(job_id, session, user)
    cues = session.exec(
        select(TranscriptCue).where(TranscriptCue.job_id == job_id).order_by(TranscriptCue.start_seconds)
    ).all()
    return TranscriptResponse(language=job.transcript_language, source=job.transcript_source, cues=cues)


@router.get("/{job_id}/zip")
def download_zip(job_id: int, session: Session = Depends(get_session), user: User = Depends(get_current_user)):
    _get_owned_job(job_id, session, user)
    data = build_job_zip_bytes(session, job_id)
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename=job_{job_id}_frames.zip"},
    )
