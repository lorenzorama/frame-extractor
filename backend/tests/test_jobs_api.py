# backend/tests/test_jobs_api.py
from unittest.mock import patch

from app.models import JobStatus


def signup_and_auth_headers(client, email="a@example.com"):
    resp = client.post("/auth/signup", json={"email": email, "password": "secret123"})
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def signup_and_get_token(client, email="a@example.com"):
    resp = client.post("/auth/signup", json={"email": email, "password": "secret123"})
    return resp.json()["access_token"]


def test_create_job_requires_auth(client):
    resp = client.post("/jobs", json={"youtube_urls": ["https://youtube.com/watch?v=abc"], "interval_seconds": 5})
    assert resp.status_code == 401


@patch("app.routers.jobs.dispatch_next")
def test_create_jobs_requires_interval_or_timestamps(mock_dispatch, client):
    headers = signup_and_auth_headers(client)
    resp = client.post("/jobs", json={"youtube_urls": ["https://youtube.com/watch?v=abc"]}, headers=headers)
    assert resp.status_code == 422


@patch("app.routers.jobs.dispatch_next")
def test_create_jobs_creates_waiting_and_dispatches(mock_dispatch, client):
    headers = signup_and_auth_headers(client)
    resp = client.post(
        "/jobs",
        json={"youtube_urls": ["https://youtube.com/watch?v=a", "https://youtube.com/watch?v=b"], "interval_seconds": 5},
        headers=headers,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert len(body) == 2
    assert all(j["status"] == "waiting" for j in body)
    mock_dispatch.assert_called_once()


@patch("app.routers.jobs.dispatch_next")
def test_create_jobs_empty_list_rejected(mock_dispatch, client):
    headers = signup_and_auth_headers(client)
    resp = client.post("/jobs", json={"youtube_urls": ["   ", ""], "interval_seconds": 5}, headers=headers)
    assert resp.status_code == 422


@patch("app.routers.jobs.dispatch_next")
def test_create_jobs_over_limit_rejected(mock_dispatch, client):
    headers = signup_and_auth_headers(client)
    urls = [f"https://youtube.com/watch?v={i}" for i in range(51)]
    resp = client.post("/jobs", json={"youtube_urls": urls, "interval_seconds": 5}, headers=headers)
    assert resp.status_code == 422


@patch("app.routers.jobs.dispatch_next")
def test_list_jobs_only_returns_own_jobs(mock_dispatch, client):
    headers_a = signup_and_auth_headers(client, "a@example.com")
    headers_b = signup_and_auth_headers(client, "b@example.com")

    client.post("/jobs", json={"youtube_urls": ["https://youtube.com/watch?v=1"], "interval_seconds": 5}, headers=headers_a)
    client.post("/jobs", json={"youtube_urls": ["https://youtube.com/watch?v=2"], "interval_seconds": 5}, headers=headers_b)

    resp = client.get("/jobs", headers=headers_a)
    assert resp.status_code == 200
    jobs = resp.json()
    assert len(jobs) == 1
    assert jobs[0]["youtube_url"] == "https://youtube.com/watch?v=1"


@patch("app.routers.jobs.dispatch_next")
def test_get_job_not_owned_returns_404(mock_dispatch, client):
    headers_a = signup_and_auth_headers(client, "a@example.com")
    headers_b = signup_and_auth_headers(client, "b@example.com")

    created = client.post(
        "/jobs", json={"youtube_urls": ["https://youtube.com/watch?v=1"], "interval_seconds": 5}, headers=headers_a
    ).json()[0]

    resp = client.get(f"/jobs/{created['id']}", headers=headers_b)
    assert resp.status_code == 404


@patch("app.routers.jobs.dispatch_next")
def test_stream_job_terminal_state_yields_event_and_closes(mock_dispatch, client, session, monkeypatch):
    from app import routers

    # event_generator opens its own DB session against app.routers.jobs.engine,
    # independent of the request-scoped session dependency override. Point it at
    # the same in-memory engine the test session/client use.
    monkeypatch.setattr(routers.jobs, "engine", session.get_bind())

    token = signup_and_get_token(client)
    headers = {"Authorization": f"Bearer {token}"}
    created = client.post(
        "/jobs", json={"youtube_urls": ["https://youtube.com/watch?v=abc"], "interval_seconds": 5}, headers=headers
    ).json()[0]

    from app.models import Job

    job = session.get(Job, created["id"])
    job.status = JobStatus.done
    job.frames_done = 3
    job.frames_total = 3
    session.add(job)
    session.commit()

    with client.stream("GET", f"/jobs/{created['id']}/stream", params={"token": token}) as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")

        events = []
        for line in resp.iter_lines():
            if line:
                events.append(line)
            if events:
                break

    assert len(events) >= 1
    assert events[0].startswith("data: ")
    assert '"status": "done"' in events[0] or '"status":"done"' in events[0]


@patch("app.routers.jobs.dispatch_next")
def test_stream_job_invalid_token_returns_401(mock_dispatch, client):
    headers = signup_and_auth_headers(client)
    created = client.post(
        "/jobs", json={"youtube_urls": ["https://youtube.com/watch?v=abc"], "interval_seconds": 5}, headers=headers
    ).json()[0]

    resp = client.get(f"/jobs/{created['id']}/stream", params={"token": "not-a-real-token"})

    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid token"


@patch("app.routers.jobs.dispatch_next")
def test_cancel_waiting_job(mock_dispatch, client, session):
    from app.models import Job, JobStatus

    headers = signup_and_auth_headers(client)
    created = client.post(
        "/jobs", json={"youtube_urls": ["https://youtube.com/watch?v=a"], "interval_seconds": 5}, headers=headers
    ).json()[0]

    # ensure it's waiting (dispatch is mocked, so it stays waiting)
    job = session.get(Job, created["id"])
    job.status = JobStatus.waiting
    session.add(job)
    session.commit()

    resp = client.delete(f"/jobs/{created['id']}", headers=headers)
    assert resp.status_code == 204
    assert session.get(Job, created["id"]) is None


@patch("app.routers.jobs.dispatch_next")
def test_cancel_non_waiting_job_conflict(mock_dispatch, client, session):
    from app.models import Job, JobStatus

    headers = signup_and_auth_headers(client)
    created = client.post(
        "/jobs", json={"youtube_urls": ["https://youtube.com/watch?v=a"], "interval_seconds": 5}, headers=headers
    ).json()[0]

    job = session.get(Job, created["id"])
    job.status = JobStatus.downloading
    session.add(job)
    session.commit()

    resp = client.delete(f"/jobs/{created['id']}", headers=headers)
    assert resp.status_code == 409
    assert session.get(Job, created["id"]) is not None


@patch("app.routers.jobs.dispatch_next")
def test_cancel_other_users_job_404(mock_dispatch, client):
    headers_a = signup_and_auth_headers(client, "a@example.com")
    headers_b = signup_and_auth_headers(client, "b@example.com")
    created = client.post(
        "/jobs", json={"youtube_urls": ["https://youtube.com/watch?v=a"], "interval_seconds": 5}, headers=headers_a
    ).json()[0]

    resp = client.delete(f"/jobs/{created['id']}", headers=headers_b)
    assert resp.status_code == 404
