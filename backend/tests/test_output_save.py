from sqlmodel import SQLModel, Session, create_engine
from sqlmodel.pool import StaticPool

from app.models import Job


def _session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def test_job_output_fields_default_off():
    with _session() as session:
        job = Job(user_id=1, youtube_url="u")
        session.add(job)
        session.commit()
        session.refresh(job)
        assert job.save_to_output is False
        assert job.output_subdir is None
        assert job.output_index is None


def test_job_output_fields_settable():
    with _session() as session:
        job = Job(user_id=1, youtube_url="u", save_to_output=True, output_subdir="proj", output_index=3)
        session.add(job)
        session.commit()
        session.refresh(job)
        assert job.save_to_output is True
        assert job.output_subdir == "proj"
        assert job.output_index == 3


import zipfile
import io
import os


def test_build_job_zip_bytes(tmp_path):
    from app.zipbuilder import build_job_zip_bytes
    from app.models import Frame, TranscriptCue

    with _session() as session:
        job = Job(user_id=1, youtube_url="u")
        session.add(job)
        session.commit()
        session.refresh(job)

        img = tmp_path / "f.jpg"
        img.write_bytes(b"jpegdata")
        session.add(Frame(job_id=job.id, timestamp_seconds=1.0, file_path=str(img)))
        session.add(TranscriptCue(job_id=job.id, start_seconds=1.0, end_seconds=2.0, text="hi"))
        session.commit()

        data = build_job_zip_bytes(session, job.id)

    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = set(zf.namelist())
        assert "1.0.jpg" in names
        assert "transcript.txt" in names
        assert zf.read("transcript.txt").decode() == "[0:01] hi"
