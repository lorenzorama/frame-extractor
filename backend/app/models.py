from datetime import datetime
from enum import Enum
from typing import Optional

from sqlmodel import Field, SQLModel, JSON, Column


class JobStatus(str, Enum):
    pending = "pending"
    downloading = "downloading"
    extracting = "extracting"
    done = "done"
    failed = "failed"


class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(unique=True, index=True)
    hashed_password: str
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Job(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    youtube_url: str
    interval_seconds: Optional[float] = None
    manual_timestamps: Optional[list[float]] = Field(default=None, sa_column=Column(JSON))
    status: JobStatus = Field(default=JobStatus.pending)
    error_message: Optional[str] = None
    frames_total: int = Field(default=0)
    frames_done: int = Field(default=0)
    transcript_language: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Frame(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    job_id: int = Field(foreign_key="job.id", index=True)
    timestamp_seconds: float
    file_path: str
    caption: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class TranscriptCue(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    job_id: int = Field(foreign_key="job.id", index=True)
    start_seconds: float
    end_seconds: float
    text: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
