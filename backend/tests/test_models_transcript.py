# backend/tests/test_models_transcript.py
from sqlmodel import SQLModel, Session, create_engine

from app.models import User, Job, Frame, TranscriptCue


def make_engine():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return engine


def test_frame_caption_and_transcript_cue_persist():
    engine = make_engine()
    with Session(engine) as session:
        user = User(email="a@example.com", hashed_password="x")
        session.add(user)
        session.commit()
        session.refresh(user)

        job = Job(user_id=user.id, youtube_url="https://youtube.com/watch?v=abc", interval_seconds=5)
        session.add(job)
        session.commit()
        session.refresh(job)

        job.transcript_language = "en"
        frame = Frame(job_id=job.id, timestamp_seconds=5.0, file_path="/x.jpg", caption="hello world")
        cue = TranscriptCue(job_id=job.id, start_seconds=4.0, end_seconds=6.0, text="hello world")
        session.add(job)
        session.add(frame)
        session.add(cue)
        session.commit()
        session.refresh(job)
        session.refresh(frame)
        session.refresh(cue)

        assert job.transcript_language == "en"
        assert frame.caption == "hello world"
        assert cue.start_seconds == 4.0 and cue.text == "hello world"
