import io
import zipfile

from sqlmodel import Session, select

from app.models import Frame, TranscriptCue


def _fmt(sec: float) -> str:
    total = int(sec)
    return f"{total // 60}:{total % 60:02d}"


def build_job_zip_bytes(session: Session, job_id: int) -> bytes:
    """Build a job's result zip: one <timestamp>.jpg per frame, plus a
    transcript.txt when the job has transcript cues. Returns the zip bytes."""
    frames = session.exec(
        select(Frame).where(Frame.job_id == job_id).order_by(Frame.timestamp_seconds)
    ).all()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        for frame in frames:
            zf.write(frame.file_path, arcname=f"{frame.timestamp_seconds}.jpg")

    cues = session.exec(
        select(TranscriptCue).where(TranscriptCue.job_id == job_id).order_by(TranscriptCue.start_seconds)
    ).all()
    if cues:
        transcript_text = "\n".join(f"[{_fmt(c.start_seconds)}] {c.text}" for c in cues)
        with zipfile.ZipFile(buffer, "a") as zf:
            zf.writestr("transcript.txt", transcript_text)

    buffer.seek(0)
    return buffer.getvalue()
