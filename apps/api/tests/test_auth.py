REGISTER_URL = "/api/v1/auth/register"
LOGIN_URL = "/api/v1/auth/login"


async def test_register_login_me_flow(client):
    resp = await client.post(
        REGISTER_URL,
        json={"email": "user@example.com", "password": "secret123", "full_name": "Nifty Trader"},
    )
    assert resp.status_code == 201
    user = resp.json()
    assert user["email"] == "user@example.com"
    assert "hashed_password" not in user

    resp = await client.post(LOGIN_URL, json={"email": "user@example.com", "password": "secret123"})
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.get("/api/v1/auth/me", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["email"] == "user@example.com"


async def test_register_duplicate_email_conflict(client):
    payload = {"email": "dup@example.com", "password": "secret123"}
    assert (await client.post(REGISTER_URL, json=payload)).status_code == 201
    resp = await client.post(REGISTER_URL, json=payload)
    assert resp.status_code == 409


async def test_login_wrong_password_unauthorized(client):
    await client.post(REGISTER_URL, json={"email": "pw@example.com", "password": "correct123"})
    resp = await client.post(LOGIN_URL, json={"email": "pw@example.com", "password": "wrong123"})
    assert resp.status_code == 401


async def test_me_requires_token(client):
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code == 401
