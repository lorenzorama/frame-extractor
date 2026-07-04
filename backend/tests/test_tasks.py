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
@patch("app.tasks.get_video_info", return_value={"duration": 10.0})
def test_process_job_happy_path(mock_info, mock_download, mock_extract, tmp_path, monkeypatch):
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
@patch("app.tasks.get_video_info", return_value={"duration": 10.0})
def test_process_job_failure_sets_status_failed(mock_info, mock_download, tmp_path, monkeypatch):
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


@patch("app.tasks.os.makedirs", side_effect=OSError("permission denied"))
def test_process_job_makedirs_failure_sets_status_failed(mock_makedirs, tmp_path, monkeypatch):
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
    assert job.error_message
    assert "permission denied" in job.error_message


def test_process_job_populates_transcript(tmp_path, monkeypatch):
    from app import tasks
    from app.models import TranscriptCue
    from app.video import Cue

    engine, session = make_session()
    monkeypatch.setattr(tasks, "engine", engine)
    monkeypatch.setattr("app.config.settings.data_dir", str(tmp_path))

    monkeypatch.setattr(tasks, "get_video_info", lambda url: {"duration": 10.0})
    monkeypatch.setattr(tasks, "download_video", lambda url, path: None)
    monkeypatch.setattr(tasks, "extract_frame", lambda v, ts, dest: None)
    monkeypatch.setattr(tasks, "pick_caption_language", lambda info: "en")
    monkeypatch.setattr(tasks, "download_captions", lambda url, lang, stem: f"{stem}.{lang}.vtt")
    monkeypatch.setattr(tasks.os.path, "exists", lambda p: True)
    monkeypatch.setattr(tasks, "parse_vtt", lambda path: [Cue(0.0, 6.0, "hello"), Cue(6.0, 10.0, "world")])

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
    assert job.transcript_language == "en"

    cues = session.query(TranscriptCue).filter(TranscriptCue.job_id == job.id).all()
    assert len(cues) == 2

    frames = session.query(Frame).filter(Frame.job_id == job.id).order_by(Frame.timestamp_seconds).all()
    # timestamps for duration 10, interval 5 -> [0.0, 5.0, 9.5] (last capped below duration)
    assert frames[0].caption == "hello"
    assert frames[-1].caption == "world"


def test_process_job_succeeds_when_transcript_fails(tmp_path, monkeypatch):
    from app import tasks

    engine, session = make_session()
    monkeypatch.setattr(tasks, "engine", engine)
    monkeypatch.setattr("app.config.settings.data_dir", str(tmp_path))

    monkeypatch.setattr(tasks, "get_video_info", lambda url: {"duration": 10.0})
    monkeypatch.setattr(tasks, "download_video", lambda url, path: None)
    monkeypatch.setattr(tasks, "extract_frame", lambda v, ts, dest: None)

    def boom(info):
        raise RuntimeError("caption lookup blew up")

    monkeypatch.setattr(tasks, "pick_caption_language", boom)

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
    assert job.status == JobStatus.done            # transcript failure did NOT fail the job
    assert job.transcript_language is None
    frames = session.query(Frame).filter(Frame.job_id == job.id).all()
    assert all(f.caption is None for f in frames)
