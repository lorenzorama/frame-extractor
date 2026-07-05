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
    real_exists = os.path.exists
    monkeypatch.setattr(
        tasks.os.path,
        "exists",
        lambda p: True if str(p).endswith(".vtt") else real_exists(p),
    )
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


def test_process_job_survives_transcript_db_failure(tmp_path, monkeypatch):
    from app import tasks
    from app.video import Cue

    engine, session = make_session()
    monkeypatch.setattr(tasks, "engine", engine)
    monkeypatch.setattr("app.config.settings.data_dir", str(tmp_path))
    monkeypatch.setattr(tasks, "get_video_info", lambda url: {"duration": 10.0})
    monkeypatch.setattr(tasks, "download_video", lambda url, path: None)
    monkeypatch.setattr(tasks, "extract_frame", lambda v, ts, dest: None)
    monkeypatch.setattr(tasks, "pick_caption_language", lambda info: "en")
    monkeypatch.setattr(tasks, "download_captions", lambda url, lang, stem: f"{stem}.{lang}.vtt")
    real_exists = os.path.exists
    monkeypatch.setattr(tasks.os.path, "exists", lambda p: True if str(p).endswith(".vtt") else real_exists(p))
    # A cue with text=None trips the NOT NULL constraint on TranscriptCue.text
    # at flush/commit time, causing a *real* IntegrityError from the DB -
    # this genuinely poisons the SQLAlchemy session (unlike a plain raised
    # RuntimeError), reproducing the production failure mode.
    monkeypatch.setattr(tasks, "parse_vtt", lambda path: [Cue(0.0, 6.0, None)])

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
    assert job.status == JobStatus.done          # transcript DB failure did NOT fail the job
    assert job.transcript_language is None
    frames = session.query(Frame).filter(Frame.job_id == job.id).all()
    assert len(frames) == 3
    assert all(f.caption is None for f in frames)


def _base_patches(tasks, monkeypatch, tmp_path, engine, duration=10.0):
    monkeypatch.setattr(tasks, "engine", engine)
    monkeypatch.setattr("app.config.settings.data_dir", str(tmp_path))
    monkeypatch.setattr(tasks, "get_video_info", lambda url: {"duration": duration})
    monkeypatch.setattr(tasks, "download_video", lambda url, path: None)
    monkeypatch.setattr(tasks, "extract_frame", lambda v, ts, dest: None)


def test_whisper_fallback_when_no_captions(tmp_path, monkeypatch):
    from app import tasks
    from app.models import TranscriptCue
    from app.video import Cue

    engine, session = make_session()
    _base_patches(tasks, monkeypatch, tmp_path, engine, duration=10.0)
    monkeypatch.setattr(tasks, "pick_caption_language", lambda info: None)   # no captions
    monkeypatch.setattr("app.config.settings.whisper_enabled", True)
    monkeypatch.setattr("app.config.settings.whisper_max_duration_seconds", 3600)
    monkeypatch.setattr(tasks, "extract_audio", lambda src, dest: None)
    monkeypatch.setattr(tasks, "transcribe_audio", lambda p: ("en", [Cue(0.0, 6.0, "hello"), Cue(6.0, 10.0, "world")]))

    user = User(email="a@example.com", hashed_password="x")
    session.add(user); session.commit(); session.refresh(user)
    job = Job(user_id=user.id, youtube_url="https://youtube.com/watch?v=abc", interval_seconds=5.0)
    session.add(job); session.commit(); session.refresh(job)

    tasks.process_job(job.id)

    session.refresh(job)
    assert job.status == JobStatus.done
    assert job.transcript_language == "en"
    assert job.transcript_source == "whisper"
    assert len(session.query(TranscriptCue).filter(TranscriptCue.job_id == job.id).all()) == 2
    frames = session.query(Frame).filter(Frame.job_id == job.id).order_by(Frame.timestamp_seconds).all()
    assert frames[0].caption == "hello"
    assert frames[-1].caption == "world"


def test_whisper_skipped_when_captions_present(tmp_path, monkeypatch):
    from app import tasks
    from app.video import Cue
    from unittest.mock import MagicMock

    engine, session = make_session()
    _base_patches(tasks, monkeypatch, tmp_path, engine, duration=10.0)
    monkeypatch.setattr(tasks, "pick_caption_language", lambda info: "en")
    monkeypatch.setattr(tasks, "download_captions", lambda url, lang, stem: f"{stem}.{lang}.vtt")
    real_exists = os.path.exists
    monkeypatch.setattr(tasks.os.path, "exists", lambda p: True if str(p).endswith(".vtt") else real_exists(p))
    monkeypatch.setattr(tasks, "parse_vtt", lambda path: [Cue(0.0, 6.0, "caption line")])
    transcribe = MagicMock()
    monkeypatch.setattr(tasks, "transcribe_audio", transcribe)

    user = User(email="a@example.com", hashed_password="x")
    session.add(user); session.commit(); session.refresh(user)
    job = Job(user_id=user.id, youtube_url="https://youtube.com/watch?v=abc", interval_seconds=5.0)
    session.add(job); session.commit(); session.refresh(job)

    tasks.process_job(job.id)

    session.refresh(job)
    assert job.status == JobStatus.done
    assert job.transcript_source == "captions"
    transcribe.assert_not_called()


def test_whisper_skipped_when_over_duration_cap(tmp_path, monkeypatch):
    from app import tasks
    from unittest.mock import MagicMock

    engine, session = make_session()
    _base_patches(tasks, monkeypatch, tmp_path, engine, duration=5000.0)  # over 3600 cap
    monkeypatch.setattr(tasks, "pick_caption_language", lambda info: None)
    monkeypatch.setattr("app.config.settings.whisper_enabled", True)
    monkeypatch.setattr("app.config.settings.whisper_max_duration_seconds", 3600)
    transcribe = MagicMock()
    monkeypatch.setattr(tasks, "transcribe_audio", transcribe)

    user = User(email="a@example.com", hashed_password="x")
    session.add(user); session.commit(); session.refresh(user)
    job = Job(user_id=user.id, youtube_url="https://youtube.com/watch?v=abc", interval_seconds=5.0)
    session.add(job); session.commit(); session.refresh(job)

    tasks.process_job(job.id)

    session.refresh(job)
    assert job.status == JobStatus.done
    assert job.transcript_source is None
    transcribe.assert_not_called()


def test_whisper_failure_does_not_fail_job(tmp_path, monkeypatch):
    from app import tasks

    engine, session = make_session()
    _base_patches(tasks, monkeypatch, tmp_path, engine, duration=10.0)
    monkeypatch.setattr(tasks, "pick_caption_language", lambda info: None)
    monkeypatch.setattr("app.config.settings.whisper_enabled", True)
    monkeypatch.setattr("app.config.settings.whisper_max_duration_seconds", 3600)
    monkeypatch.setattr(tasks, "extract_audio", lambda src, dest: None)

    def boom(p):
        raise RuntimeError("whisper blew up")

    monkeypatch.setattr(tasks, "transcribe_audio", boom)

    user = User(email="a@example.com", hashed_password="x")
    session.add(user); session.commit(); session.refresh(user)
    job = Job(user_id=user.id, youtube_url="https://youtube.com/watch?v=abc", interval_seconds=5.0)
    session.add(job); session.commit(); session.refresh(job)

    tasks.process_job(job.id)

    session.refresh(job)
    assert job.status == JobStatus.done
    assert job.transcript_language is None
    assert job.transcript_source is None
    frames = session.query(Frame).filter(Frame.job_id == job.id).all()
    assert all(f.caption is None for f in frames)


def test_process_job_dispatches_next_on_success(tmp_path, monkeypatch):
    from app import tasks
    from unittest.mock import MagicMock

    engine, session = make_session()
    monkeypatch.setattr(tasks, "engine", engine)
    monkeypatch.setattr("app.config.settings.data_dir", str(tmp_path))
    monkeypatch.setattr(tasks, "get_video_info", lambda url: {"duration": 10.0})
    monkeypatch.setattr(tasks, "download_video", lambda url, path: None)
    monkeypatch.setattr(tasks, "extract_frame", lambda v, ts, dest: None)
    monkeypatch.setattr(tasks, "pick_caption_language", lambda info: None)
    monkeypatch.setattr("app.config.settings.whisper_enabled", False)
    dispatch = MagicMock()
    monkeypatch.setattr(tasks, "dispatch_next", dispatch)

    user = User(email="a@example.com", hashed_password="x")
    session.add(user); session.commit(); session.refresh(user)
    job = Job(user_id=user.id, youtube_url="https://youtube.com/watch?v=abc", interval_seconds=5.0)
    session.add(job); session.commit(); session.refresh(job)

    tasks.process_job(job.id)

    session.refresh(job)
    assert job.status == JobStatus.done
    dispatch.assert_called_once_with(user.id)


def test_process_job_dispatches_next_on_failure(tmp_path, monkeypatch):
    from app import tasks
    from unittest.mock import MagicMock

    engine, session = make_session()
    monkeypatch.setattr(tasks, "engine", engine)
    monkeypatch.setattr("app.config.settings.data_dir", str(tmp_path))
    monkeypatch.setattr(tasks, "get_video_info", lambda url: {"duration": 10.0})
    monkeypatch.setattr(tasks, "download_video", lambda url, path: (_ for _ in ()).throw(RuntimeError("boom")))
    dispatch = MagicMock()
    monkeypatch.setattr(tasks, "dispatch_next", dispatch)

    user = User(email="a@example.com", hashed_password="x")
    session.add(user); session.commit(); session.refresh(user)
    job = Job(user_id=user.id, youtube_url="https://youtube.com/watch?v=abc", interval_seconds=5.0)
    session.add(job); session.commit(); session.refresh(job)

    tasks.process_job(job.id)

    session.refresh(job)
    assert job.status == JobStatus.failed
    dispatch.assert_called_once_with(user.id)


def test_process_job_dispatch_failure_does_not_crash(tmp_path, monkeypatch):
    from app import tasks

    engine, session = make_session()
    monkeypatch.setattr(tasks, "engine", engine)
    monkeypatch.setattr("app.config.settings.data_dir", str(tmp_path))
    monkeypatch.setattr(tasks, "get_video_info", lambda url: {"duration": 10.0})
    monkeypatch.setattr(tasks, "download_video", lambda url, path: None)
    monkeypatch.setattr(tasks, "extract_frame", lambda v, ts, dest: None)
    monkeypatch.setattr(tasks, "pick_caption_language", lambda info: None)
    monkeypatch.setattr("app.config.settings.whisper_enabled", False)

    def boom(uid):
        raise RuntimeError("dispatch blew up")

    monkeypatch.setattr(tasks, "dispatch_next", boom)

    user = User(email="a@example.com", hashed_password="x")
    session.add(user); session.commit(); session.refresh(user)
    job = Job(user_id=user.id, youtube_url="https://youtube.com/watch?v=abc", interval_seconds=5.0)
    session.add(job); session.commit(); session.refresh(job)

    tasks.process_job(job.id)  # must not raise

    session.refresh(job)
    assert job.status == JobStatus.done  # job outcome unaffected by dispatch failure


@patch("app.tasks.extract_frame")
@patch("app.tasks.download_video")
@patch("app.tasks.get_video_info", return_value={"duration": 10.0})
def test_process_job_skips_unextractable_frame(mock_info, mock_download, mock_extract, tmp_path, monkeypatch):
    """A single frame that can't be extracted (e.g. a near-EOF seek past the last
    video frame) must not fail the whole job."""
    from app import tasks

    engine, session = make_session()
    monkeypatch.setattr(tasks, "engine", engine)
    monkeypatch.setattr("app.config.settings.data_dir", str(tmp_path))

    def flaky(source, ts, dest):
        if ts == 5.0:
            raise RuntimeError("ffmpeg: No filtered frames for output stream; Conversion failed")

    mock_extract.side_effect = flaky

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
    assert job.frames_done == 2
    frames = session.query(Frame).filter(Frame.job_id == job.id).all()
    assert len(frames) == 2
    assert 5.0 not in [f.timestamp_seconds for f in frames]


@patch("app.tasks.extract_frame", side_effect=RuntimeError("Conversion failed"))
@patch("app.tasks.download_video")
@patch("app.tasks.get_video_info", return_value={"duration": 10.0})
def test_process_job_fails_when_no_frames_extractable(mock_info, mock_download, mock_extract, tmp_path, monkeypatch):
    """If not a single frame can be extracted, the job is a genuine failure."""
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
    assert job.status == JobStatus.failed
    assert job.frames_done == 0
