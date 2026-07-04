from unittest.mock import MagicMock

from sqlmodel import SQLModel, Session, create_engine
from sqlmodel.pool import StaticPool

from app.models import User, Job, JobStatus


def make_engine():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    return engine


def _user_and_jobs(session, statuses):
    user = User(email="a@example.com", hashed_password="x")
    session.add(user)
    session.commit()
    session.refresh(user)
    jobs = []
    for i, st in enumerate(statuses):
        j = Job(user_id=user.id, youtube_url=f"u{i}", interval_seconds=5, status=st)
        session.add(j)
        session.commit()
        session.refresh(j)
        jobs.append(j)
    return user, jobs


def test_dispatch_promotes_oldest_waiting_when_idle(monkeypatch):
    from app import dispatch

    engine = make_engine()
    monkeypatch.setattr(dispatch, "engine", engine)
    fake_celery = MagicMock()
    monkeypatch.setattr(dispatch, "celery_app", fake_celery)

    with Session(engine) as session:
        user, jobs = _user_and_jobs(session, [JobStatus.waiting, JobStatus.waiting])
        user_id = user.id
        first_id = jobs[0].id

    dispatch.dispatch_next(user_id)

    with Session(engine) as session:
        first = session.get(Job, first_id)
        assert first.status == JobStatus.pending
    fake_celery.send_task.assert_called_once_with("process_job", args=[first_id])


def test_dispatch_noop_when_user_has_active_job(monkeypatch):
    from app import dispatch

    engine = make_engine()
    monkeypatch.setattr(dispatch, "engine", engine)
    fake_celery = MagicMock()
    monkeypatch.setattr(dispatch, "celery_app", fake_celery)

    with Session(engine) as session:
        user, jobs = _user_and_jobs(session, [JobStatus.downloading, JobStatus.waiting])
        user_id = user.id
        waiting_id = jobs[1].id

    dispatch.dispatch_next(user_id)

    with Session(engine) as session:
        assert session.get(Job, waiting_id).status == JobStatus.waiting  # untouched
    fake_celery.send_task.assert_not_called()


def test_dispatch_noop_when_no_waiting(monkeypatch):
    from app import dispatch

    engine = make_engine()
    monkeypatch.setattr(dispatch, "engine", engine)
    fake_celery = MagicMock()
    monkeypatch.setattr(dispatch, "celery_app", fake_celery)

    with Session(engine) as session:
        user, _ = _user_and_jobs(session, [JobStatus.done])
        user_id = user.id

    dispatch.dispatch_next(user_id)
    fake_celery.send_task.assert_not_called()
