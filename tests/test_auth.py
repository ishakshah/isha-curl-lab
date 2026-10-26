"""Accounts: registration rules, login lockout, sessions, and saved routines (uses a throwaway database)."""

import pytest
from fastapi.testclient import TestClient

from app import auth
from app.main import app

GOOD = "Curly#Hair2026"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(auth, "DB_PATH", tmp_path / "test.db")
    auth.failed_logins.clear()
    return TestClient(app)


def register(client, email="ada@example.com", password=GOOD, confirm=None):
    return client.post("/api/auth/register", json={
        "first_name": "Ada", "last_name": "Lovelace", "email": email, "password": password, "confirm_password": confirm or password})


def test_register_signs_in_and_hashes_password(client, tmp_path):
    r = register(client)
    assert r.status_code == 201 and r.json()["user"]["email"] == "ada@example.com"
    assert client.get("/api/auth/me").json()["user"]["first_name"] == "Ada"
    import sqlite3
    stored = sqlite3.connect(tmp_path / "test.db").execute("select password_hash from users").fetchone()[0]
    assert stored.startswith("$argon2id$") and GOOD not in stored


@pytest.mark.parametrize("pw,missing", [("short1!", "10 characters"), ("onlyletters!!", "number"), ("1234567890!!", "letter"), ("Letters12345", "special")])
def test_password_rules(client, pw, missing):
    r = register(client, password=pw)
    assert r.status_code == 400 and missing in r.json()["detail"]


def test_duplicate_email_and_mismatched_passwords(client):
    assert register(client).status_code == 201
    assert register(client).status_code == 409
    assert register(client, email="b@example.com", confirm="Different#1234").status_code == 400


def test_login_message_is_the_same_for_unknown_email_and_wrong_password(client):
    register(client)
    client.post("/api/auth/logout")
    wrong = client.post("/api/auth/login", json={"email": "ada@example.com", "password": "Wrong#Pass123"})
    unknown = client.post("/api/auth/login", json={"email": "nobody@example.com", "password": "Wrong#Pass123"})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["detail"].startswith("Incorrect email or password") and unknown.json()["detail"].startswith("Incorrect email or password")


def test_five_failures_lock_the_account_even_for_the_right_password(client):
    register(client)
    client.post("/api/auth/logout")
    codes = [client.post("/api/auth/login", json={"email": "ada@example.com", "password": "Wrong#Pass123"}).status_code for _ in range(5)]
    assert codes == [401, 401, 401, 401, 429]
    locked = client.post("/api/auth/login", json={"email": "ada@example.com", "password": GOOD})
    assert locked.status_code == 429 and "Retry-After" in locked.headers


def test_unknown_emails_lock_too(client):
    codes = [client.post("/api/auth/login", json={"email": "ghost@example.com", "password": "Wrong#Pass123"}).status_code for _ in range(5)]
    assert codes[-1] == 429  # so the limit cannot reveal who is registered


def test_tampered_or_missing_cookie_is_signed_out(client):
    register(client)
    token = client.cookies.get(auth.SESSION_COOKIE)
    client.cookies.clear()  # drop the real cookie first so only the forged one is sent
    client.cookies.set(auth.SESSION_COOKIE, "999" + token[1:])
    assert client.get("/api/auth/me").json()["user"] is None
    client.cookies.clear()
    assert client.get("/api/account/saved").status_code == 401


def test_change_password(client):
    register(client)
    r = client.post("/api/auth/change-password", json={"current_password": "Wrong#Pass123", "new_password": "New#Passw0rd!", "confirm_password": "New#Passw0rd!"})
    assert r.status_code == 401
    same = client.post("/api/auth/change-password", json={"current_password": GOOD, "new_password": GOOD, "confirm_password": GOOD})
    assert same.status_code == 400
    ok = client.post("/api/auth/change-password", json={"current_password": GOOD, "new_password": "New#Passw0rd!", "confirm_password": "New#Passw0rd!"})
    assert ok.status_code == 200
    client.post("/api/auth/logout")
    assert client.post("/api/auth/login", json={"email": "ada@example.com", "password": "New#Passw0rd!"}).status_code == 200


def test_saved_routine_round_trip_and_stays_private(client):
    register(client)
    profile = {"zip_code": "06511", "curl_pattern": "4B", "monthly_budget_usd": 30}
    assert client.put("/api/account/saved", json={"profile": profile, "result": {"headline": "Hi"}}).status_code == 204
    saved = client.get("/api/account/saved").json()["saved"]
    assert saved["profile"]["curl_pattern"] == "4B" and saved["result"]["headline"] == "Hi"
    other = TestClient(app)
    assert other.get("/api/account/saved").status_code == 401  # a different visitor sees nothing
    bad = client.put("/api/account/saved", json={"profile": {"zip_code": "nope"}, "result": {}})
    assert bad.status_code == 422
