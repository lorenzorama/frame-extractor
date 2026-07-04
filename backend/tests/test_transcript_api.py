from unittest.mock import patch


def signup_and_auth_headers(client, email="a@example.com"):
    resp = client.post("/auth/signup", json={"email": email, "password": "secret123"})
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@patch("app.routers.jobs.dispatch_next")
def test_frames_include_caption(mock_dispatch, client, session):
    from app.models import Frame

    headers = signup_and_auth_headers(client)
    job = client.post(
        "/jobs", json={"youtube_urls": ["https://youtube.com/watch?v=abc"], "interval_seconds": 5}, headers=headers
    ).json()[0]

    session.add(Frame(job_id=job["id"], timestamp_seconds=5.0, file_path="/x.jpg", caption="hello"))
    session.commit()

    resp = client.get(f"/jobs/{job['id']}/frames", headers=headers)
    assert resp.status_code == 200
    assert resp.json()[0]["caption"] == "hello"


@patch("app.routers.jobs.dispatch_next")
def test_transcript_endpoint_returns_cues(mock_dispatch, client, session):
    from app.models import Job, TranscriptCue

    headers = signup_and_auth_headers(client)
    job = client.post(
        "/jobs", json={"youtube_urls": ["https://youtube.com/watch?v=abc"], "interval_seconds": 5}, headers=headers
    ).json()[0]

    db_job = session.get(Job, job["id"])
    db_job.transcript_language = "en"
    session.add(db_job)
    session.add(TranscriptCue(job_id=job["id"], start_seconds=1.0, end_seconds=4.0, text="hello"))
    session.add(TranscriptCue(job_id=job["id"], start_seconds=4.0, end_seconds=8.0, text="world"))
    session.commit()

    resp = client.get(f"/jobs/{job['id']}/transcript", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["language"] == "en"
    assert [c["text"] for c in body["cues"]] == ["hello", "world"]


@patch("app.routers.jobs.dispatch_next")
def test_transcript_endpoint_empty_when_none(mock_dispatch, client, session):
    headers = signup_and_auth_headers(client)
    job = client.post(
        "/jobs", json={"youtube_urls": ["https://youtube.com/watch?v=abc"], "interval_seconds": 5}, headers=headers
    ).json()[0]

    resp = client.get(f"/jobs/{job['id']}/transcript", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == {"language": None, "source": None, "cues": []}


@patch("app.routers.jobs.dispatch_next")
def test_transcript_endpoint_not_owned_returns_404(mock_dispatch, client):
    headers_a = signup_and_auth_headers(client, "a@example.com")
    headers_b = signup_and_auth_headers(client, "b@example.com")
    job = client.post(
        "/jobs", json={"youtube_urls": ["https://youtube.com/watch?v=abc"], "interval_seconds": 5}, headers=headers_a
    ).json()[0]

    resp = client.get(f"/jobs/{job['id']}/transcript", headers=headers_b)
    assert resp.status_code == 404


@patch("app.routers.jobs.dispatch_next")
def test_transcript_endpoint_returns_source(mock_dispatch, client, session):
    from app.models import Job, TranscriptCue

    headers = signup_and_auth_headers(client)
    job = client.post(
        "/jobs", json={"youtube_urls": ["https://youtube.com/watch?v=abc"], "interval_seconds": 5}, headers=headers
    ).json()[0]

    db_job = session.get(Job, job["id"])
    db_job.transcript_language = "en"
    db_job.transcript_source = "whisper"
    session.add(db_job)
    session.add(TranscriptCue(job_id=job["id"], start_seconds=1.0, end_seconds=4.0, text="hi"))
    session.commit()

    resp = client.get(f"/jobs/{job['id']}/transcript", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["source"] == "whisper"


@patch("app.routers.jobs.dispatch_next")
def test_transcript_endpoint_source_null_when_none(mock_dispatch, client):
    headers = signup_and_auth_headers(client)
    job = client.post(
        "/jobs", json={"youtube_urls": ["https://youtube.com/watch?v=abc"], "interval_seconds": 5}, headers=headers
    ).json()[0]
    resp = client.get(f"/jobs/{job['id']}/transcript", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["source"] is None
