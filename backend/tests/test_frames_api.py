import os
from unittest.mock import patch


def signup_and_auth_headers(client, email="a@example.com"):
    resp = client.post("/auth/signup", json={"email": email, "password": "secret123"})
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@patch("app.routers.jobs.process_job")
def test_list_frames_for_job(mock_task, client, session):
    from app.models import Frame

    headers = signup_and_auth_headers(client)
    job = client.post(
        "/jobs", json={"youtube_url": "https://youtube.com/watch?v=abc", "interval_seconds": 5}, headers=headers
    ).json()

    frame = Frame(job_id=job["id"], timestamp_seconds=5.0, file_path="/tmp/does-not-matter.jpg")
    session.add(frame)
    session.commit()

    resp = client.get(f"/jobs/{job['id']}/frames", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == [{"id": frame.id, "timestamp_seconds": 5.0}]


@patch("app.routers.jobs.process_job")
def test_get_frame_image_returns_file(mock_task, client, session, tmp_path):
    from app.models import Frame

    headers = signup_and_auth_headers(client)
    job = client.post(
        "/jobs", json={"youtube_url": "https://youtube.com/watch?v=abc", "interval_seconds": 5}, headers=headers
    ).json()

    image_path = tmp_path / "frame.jpg"
    image_path.write_bytes(b"\xff\xd8\xff\xd9")

    frame = Frame(job_id=job["id"], timestamp_seconds=5.0, file_path=str(image_path))
    session.add(frame)
    session.commit()
    session.refresh(frame)

    resp = client.get(f"/frames/{frame.id}/image", headers=headers)
    assert resp.status_code == 200
    assert resp.content == b"\xff\xd8\xff\xd9"


@patch("app.routers.jobs.process_job")
def test_get_frame_image_not_owned_returns_404(mock_task, client, session, tmp_path):
    from app.models import Frame

    headers_a = signup_and_auth_headers(client, "a@example.com")
    headers_b = signup_and_auth_headers(client, "b@example.com")

    job = client.post(
        "/jobs", json={"youtube_url": "https://youtube.com/watch?v=abc", "interval_seconds": 5}, headers=headers_a
    ).json()

    image_path = tmp_path / "frame.jpg"
    image_path.write_bytes(b"\xff\xd8\xff\xd9")
    frame = Frame(job_id=job["id"], timestamp_seconds=5.0, file_path=str(image_path))
    session.add(frame)
    session.commit()
    session.refresh(frame)

    resp = client.get(f"/frames/{frame.id}/image", headers=headers_b)
    assert resp.status_code == 404
