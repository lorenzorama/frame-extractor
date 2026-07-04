import os
from unittest.mock import patch

from sqlmodel import SQLModel, Session, create_engine
from sqlmodel.pool import StaticPool

from app.models import User, Job, Frame, JobStatus


def make_session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    return engine, Session(engine)


@patch("app.tasks.extract_frame")
@patch("app.tasks.download_video")
@patch("app.tasks.get_video_duration", return_value=10.0)
def test_process_job_happy_path(mock_duration, mock_download, mock_extract, tmp_path, monkeypatch):
    from app import tasks

    engine, session = make_session()
    monkeypatch.setattr(tasks, "engine", engine)
    monkeypatch.setattr("app.config.settings.data_dir", str(tmp_path))

    user = User(email="a@example.com", hashed_password="x")
    session.add(user)
    session.commit()
    session.refresh(user)

    job = Job(user_id=user.id, youtube_url="https://youtube.com/watch?v=abc", interval_seconds=5.0)
    session.add(job)
    session.commit()
    session.refresh(job)

    tasks.process_job(job.id)

    session.refresh(job)
    assert job.status == JobStatus.done
    assert job.frames_total == 3
    assert job.frames_done == 3

    frames = session.query(Frame).filter(Frame.job_id == job.id).all()
    assert len(frames) == 3
    assert mock_extract.call_count == 3


@patch("app.tasks.download_video", side_effect=RuntimeError("network error"))
@patch("app.tasks.get_video_duration", return_value=10.0)
def test_process_job_failure_sets_status_failed(mock_duration, mock_download, tmp_path, monkeypatch):
    from app import tasks

    engine, session = make_session()
    monkeypatch.setattr(tasks, "engine", engine)
    monkeypatch.setattr("app.config.settings.data_dir", str(tmp_path))

    user = User(email="a@example.com", hashed_password="x")
    session.add(user)
    session.commit()
    session.refresh(user)

    job = Job(user_id=user.id, youtube_url="https://youtube.com/watch?v=bad", interval_seconds=5.0)
    session.add(job)
    session.commit()
    session.refresh(job)

    tasks.process_job(job.id)

    session.refresh(job)
    assert job.status == JobStatus.failed
    assert "network error" in job.error_message
