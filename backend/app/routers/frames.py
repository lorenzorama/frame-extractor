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
