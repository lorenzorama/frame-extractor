from sqlalchemy import text
from sqlmodel import Session, select

from app.celery_app import celery_app
from app.database import engine
from app.models import Job, JobStatus

# A user is "busy" while any of their jobs is claimed or in progress.
ACTIVE_STATUSES = (
    JobStatus.pending,
    JobStatus.downloading,
    JobStatus.extracting,
    JobStatus.transcribing,
)


def dispatch_next(user_id: int) -> None:
    """Promote the user's oldest waiting job to pending and enqueue it, but only
    if the user has no active/claimed job. Opens its own session so the advisory
    lock scopes to a single self-contained transaction. Serialized per user via a
    Postgres advisory lock (skipped on non-Postgres, e.g. SQLite in tests)."""
    job_id = None
    with Session(engine) as session:
        if session.get_bind().dialect.name == "postgresql":
            session.execute(text("SELECT pg_advisory_xact_lock(:uid)"), {"uid": user_id})

        active = session.exec(
            select(Job).where(Job.user_id == user_id, Job.status.in_(ACTIVE_STATUSES))
        ).first()
        if active is not None:
            return  # user already busy; the running job will chain the next one

        nxt = session.exec(
            select(Job)
            .where(Job.user_id == user_id, Job.status == JobStatus.waiting)
            .order_by(Job.created_at, Job.id)
        ).first()
        if nxt is None:
            return

        nxt.status = JobStatus.pending
        session.add(nxt)
        session.commit()
        job_id = nxt.id

    # Enqueue after the transaction commits (and the advisory lock is released).
    celery_app.send_task("process_job", args=[job_id])
