def test_signup_then_login(client):
    signup = client.post("/auth/signup", json={"email": "a@example.com", "password": "secret123"})
    assert signup.status_code == 201
    assert "access_token" in signup.json()

    login = client.post("/auth/login", json={"email": "a@example.com", "password": "secret123"})
    assert login.status_code == 200
    assert "access_token" in login.json()


def test_signup_duplicate_email_rejected(client):
    client.post("/auth/signup", json={"email": "a@example.com", "password": "secret123"})
    second = client.post("/auth/signup", json={"email": "a@example.com", "password": "other456"})
    assert second.status_code == 400


def test_login_wrong_password_rejected(client):
    client.post("/auth/signup", json={"email": "a@example.com", "password": "secret123"})
    login = client.post("/auth/login", json={"email": "a@example.com", "password": "wrong"})
    assert login.status_code == 401
