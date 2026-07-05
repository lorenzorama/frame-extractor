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
