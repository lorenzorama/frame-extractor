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
import pytest


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


def test_sanitize_output_subdir_ok():
    from app.output_save import sanitize_output_subdir
    assert sanitize_output_subdir(None) == ""
    assert sanitize_output_subdir("") == ""
    assert sanitize_output_subdir("   ") == ""
    assert sanitize_output_subdir("my-project") == "my-project"
    assert sanitize_output_subdir("Batch_01") == "Batch_01"
    assert sanitize_output_subdir(" spaced name ") == "spaced name"


@pytest.mark.parametrize("bad", ["..", ".", "...", "/abs", "\\abs", "a/b", "a\\b", "x\x00y", "a*b", "a:b"])
def test_sanitize_output_subdir_rejects(bad):
    from app.output_save import sanitize_output_subdir, InvalidSubdir
    with pytest.raises(InvalidSubdir):
        sanitize_output_subdir(bad)


def test_save_job_zip_no_overwrite(tmp_path):
    from app.output_save import save_job_zip
    p1 = save_job_zip(str(tmp_path), "sub", 2, b"one")
    p2 = save_job_zip(str(tmp_path), "sub", 2, b"two")
    p3 = save_job_zip(str(tmp_path), "sub", 2, b"three")
    assert os.path.basename(p1) == "video_2.zip"
    assert os.path.basename(p2) == "video_2 (2).zip"
    assert os.path.basename(p3) == "video_2 (3).zip"
    assert os.path.isdir(os.path.join(str(tmp_path), "sub"))
    with open(p1, "rb") as f:
        assert f.read() == b"one"


def test_save_job_zip_base_dir_when_no_subdir(tmp_path):
    from app.output_save import save_job_zip
    p = save_job_zip(str(tmp_path), "", 1, b"x")
    assert p == os.path.join(str(tmp_path), "video_1.zip")


def test_maybe_save_output_writes_for_done_optin(tmp_path):
    from app.output_save import maybe_save_output
    from app.models import Frame

    with _session() as session:
        job = Job(user_id=1, youtube_url="u", status="done",
                  save_to_output=True, output_subdir="sub", output_index=1)
        session.add(job)
        session.commit()
        session.refresh(job)
        img = tmp_path / "f.jpg"
        img.write_bytes(b"jpeg")
        session.add(Frame(job_id=job.id, timestamp_seconds=0.0, file_path=str(img)))
        session.commit()

        out = tmp_path / "out"
        path = maybe_save_output(session, job, str(out))

    assert path is not None
    assert os.path.basename(path) == "video_1.zip"
    assert os.path.isfile(os.path.join(str(out), "sub", "video_1.zip"))


def test_maybe_save_output_noop_when_optout(tmp_path):
    from app.output_save import maybe_save_output
    with _session() as session:
        job = Job(user_id=1, youtube_url="u", status="done", save_to_output=False)
        session.add(job)
        session.commit()
        session.refresh(job)
        out = tmp_path / "out"
        assert maybe_save_output(session, job, str(out)) is None
    assert not (tmp_path / "out").exists()
