"""Optional accounts, ported from HW4's login system.

Signing in is optional. A signed-in person can keep their hair profile and latest routine on the server
(data/app.db, never committed) and open it from any device. Photos are never stored.

Passwords are hashed with Argon2id. Login sessions are a signed, HttpOnly cookie. Failed logins lock an
account for 15 minutes after 5 tries, whether or not the email has an account.
"""

import hashlib
import hmac
import json
import logging
import re
import secrets
import sqlite3
import time
from collections import defaultdict, deque
from contextlib import closing
from datetime import datetime, timezone

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from app.config import DATA_DIR
from app.schemas import UserProfile

router = APIRouter(prefix="/api")
DB_PATH = DATA_DIR / "app.db"

# Argon2id: deliberately slow and memory-hard, with a random salt stored inside the hash string.
# 128 MiB of memory, 4 passes, 4 lanes: about 80 ms per hash, cheap for one login, costly for mass guessing.
hasher = PasswordHasher(time_cost=4, memory_cost=131072, parallelism=4)
DUMMY_HASH = hasher.hash("not-a-real-password")  # checked when the email is unknown, so timing doesn't reveal accounts

SESSION_COOKIE = "cr_session"
SESSION_TTL_SECONDS = 7 * 24 * 60 * 60
SECRET_PATH = DATA_DIR / ".session_secret"


def _load_session_secret() -> str:
    """A random secret kept in a local file, so logins survive restarts with no setup and no extra key."""
    DATA_DIR.mkdir(exist_ok=True)
    if SECRET_PATH.exists() and SECRET_PATH.read_text().strip():
        return SECRET_PATH.read_text().strip()
    secret = secrets.token_hex(32)
    SECRET_PATH.write_text(secret)
    SECRET_PATH.chmod(0o600)
    return secret


SESSION_SECRET = _load_session_secret()

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MAX_NAME_LENGTH = 60
MAX_EMAIL_LENGTH = 254
MIN_PASSWORD_LENGTH = 10
MAX_PASSWORD_LENGTH = 128
MAX_LOGIN_PASSWORD_LENGTH = 1024
MAX_SAVED_BYTES = 300_000

LOGIN_MAX_ATTEMPTS = 5
LOGIN_LOCK_SECONDS = 15 * 60
LOGIN_IP_MAX_FAILURES = 30  # looser, per network address, to slow guessing across many emails
failed_logins: dict[str, deque[float]] = defaultdict(deque)


# ---------- Database ----------

def connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT, first_name TEXT NOT NULL, last_name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS saved (
            user_id INTEGER PRIMARY KEY REFERENCES users(id), profile_json TEXT NOT NULL,
            routine_json TEXT NOT NULL, updated_at TEXT NOT NULL)"""
    )
    return conn


# ---------- Shapes ----------

class RegisterRequest(BaseModel):
    first_name: str
    last_name: str
    email: str
    password: str
    confirm_password: str


class LoginRequest(BaseModel):
    email: str
    password: str


class User(BaseModel):
    id: int
    first_name: str
    last_name: str
    email: str


class AuthResponse(BaseModel):
    user: User | None
    password_update_required: bool = False  # the password they logged in with no longer meets the rules


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str
    confirm_password: str


class SavedBody(BaseModel):
    profile: UserProfile
    result: dict


def to_user(row: sqlite3.Row) -> User:
    return User(id=row["id"], first_name=row["first_name"], last_name=row["last_name"], email=row["email"])


# ---------- Passwords and sessions ----------

def password_matches(row: sqlite3.Row | None, password: str) -> bool:
    """Check a password against a stored hash, in the same time whether or not the account exists."""
    stored_hash = row["password_hash"] if row else DUMMY_HASH
    try:
        hasher.verify(stored_hash, password)
        return row is not None
    except (VerificationError, InvalidHashError):
        return False


def sign(payload: str) -> str:
    return hmac.new(SESSION_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()


def make_session_token(user_id: int, needs_password_update: bool = False) -> str:
    payload = f"{user_id}.{int(time.time()) + SESSION_TTL_SECONDS}.{int(needs_password_update)}"
    return f"{payload}.{sign(payload)}"


def read_session_token(token: str | None) -> tuple[int, bool] | None:
    """The signed-in user id and whether they still need to update their password, or None if invalid."""
    try:
        user_id, expires, flag, signature = (token or "").split(".")
        if not hmac.compare_digest(signature, sign(f"{user_id}.{expires}.{flag}")) or int(expires) < time.time():
            return None
        return int(user_id), flag == "1"
    except ValueError:
        return None


def start_session(response: Response, user_id: int, needs_password_update: bool = False) -> None:
    response.set_cookie(
        SESSION_COOKIE, make_session_token(user_id, needs_password_update), max_age=SESSION_TTL_SECONDS,
        httponly=True, samesite="lax", secure=False,  # secure=True once served over HTTPS
        path="/",
    )


def bad_request(message: str) -> HTTPException:
    return HTTPException(status_code=400, detail=message)


def normalize_email(email: str) -> str:
    email = email.strip().lower()
    if len(email) > MAX_EMAIL_LENGTH or not EMAIL_PATTERN.match(email):
        raise bad_request("Please enter a valid email address.")
    return email


def password_problems(password: str) -> list[str]:
    """What a new password is missing: at least 10 characters, a letter, a number, and a special character."""
    problems = []
    if len(password) < MIN_PASSWORD_LENGTH:
        problems.append(f"be at least {MIN_PASSWORD_LENGTH} characters")
    if not any(c.isalpha() for c in password):
        problems.append("include a letter")
    if not any(c.isdigit() for c in password):
        problems.append("include a number")
    if not any(not c.isalnum() and not c.isspace() for c in password):
        problems.append("include a special character (like ! ? # $ %)")
    return problems


def join_requirements(problems: list[str]) -> str:
    return problems[0] if len(problems) == 1 else ", ".join(problems[:-1]) + (", and " if len(problems) > 2 else " and ") + problems[-1]


# ---------- Login attempt limit ----------

def lock_seconds_left(key: str, max_failures: int) -> int:
    now = time.time()
    failures = failed_logins.get(key)
    if failures is None:
        return 0
    while failures and failures[0] < now - LOGIN_LOCK_SECONDS:
        failures.popleft()
    if not failures:
        del failed_logins[key]
        return 0
    if len(failures) >= max_failures:
        return max(1, int(failures[-1] + LOGIN_LOCK_SECONDS - now) + 1)
    return 0


def record_failed_login(*keys: str) -> None:
    now = time.time()
    if len(failed_logins) > 10_000:  # keep memory bounded
        for key in [k for k, f in failed_logins.items() if not f or f[-1] < now - LOGIN_LOCK_SECONDS]:
            del failed_logins[key]
    for key in keys:
        failed_logins[key].append(now)


def locked_out(seconds: int) -> HTTPException:
    minutes = -(-seconds // 60)
    return HTTPException(
        status_code=429,
        detail=f"Too many failed login attempts. Please try again in {minutes} minute{'s' if minutes != 1 else ''}.",
        headers={"Retry-After": str(seconds)},
    )


# ---------- Routes ----------

def signed_in_user(request: Request) -> sqlite3.Row | None:
    session = read_session_token(request.cookies.get(SESSION_COOKIE))
    if session is None:
        return None
    with closing(connect()) as conn:
        return conn.execute("SELECT * FROM users WHERE id = ?", (session[0],)).fetchone()


@router.post("/auth/register", response_model=AuthResponse, status_code=201)
def register(body: RegisterRequest, response: Response) -> AuthResponse:
    first, last = body.first_name.strip(), body.last_name.strip()
    if not first or not last:
        raise bad_request("Please enter your first and last name.")
    if len(first) > MAX_NAME_LENGTH or len(last) > MAX_NAME_LENGTH:
        raise bad_request(f"Names can be at most {MAX_NAME_LENGTH} characters.")
    email = normalize_email(body.email)
    if len(body.password) > MAX_PASSWORD_LENGTH:
        raise bad_request(f"Password can be at most {MAX_PASSWORD_LENGTH} characters.")
    problems = password_problems(body.password)
    if problems:
        raise bad_request(f"Password must {join_requirements(problems)}.")
    if body.password != body.confirm_password:
        raise bad_request("Passwords do not match.")

    password_hash = hasher.hash(body.password)
    try:
        with closing(connect()) as conn, conn:
            if conn.execute("SELECT 1 FROM users WHERE lower(email) = ?", (email,)).fetchone():
                raise HTTPException(status_code=409, detail="An account with that email already exists.")
            cursor = conn.execute(
                "INSERT INTO users (first_name, last_name, email, password_hash) VALUES (?, ?, ?, ?)",
                (first, last, email, password_hash),
            )
            row = conn.execute("SELECT * FROM users WHERE id = ?", (cursor.lastrowid,)).fetchone()
    except sqlite3.IntegrityError:  # two sign-ups with the same email at once
        raise HTTPException(status_code=409, detail="An account with that email already exists.")
    start_session(response, row["id"])
    return AuthResponse(user=to_user(row))


@router.post("/auth/login", response_model=AuthResponse)
def login(body: LoginRequest, request: Request, response: Response) -> AuthResponse:
    email = body.email.strip().lower()
    email_key = f"email:{email}"
    ip_key = f"ip:{request.client.host if request.client else 'unknown'}"

    wait = max(lock_seconds_left(email_key, LOGIN_MAX_ATTEMPTS), lock_seconds_left(ip_key, LOGIN_IP_MAX_FAILURES))
    if wait:
        raise locked_out(wait)  # locked: the password is not even checked

    def failed() -> HTTPException:
        record_failed_login(email_key, ip_key)
        attempts_left = LOGIN_MAX_ATTEMPTS - len(failed_logins[email_key])
        if attempts_left <= 0:
            return locked_out(LOGIN_LOCK_SECONDS)
        return HTTPException(
            status_code=401,
            detail=f"Incorrect email or password. You have {attempts_left} attempt{'s' if attempts_left != 1 else ''} left.",
        )

    if len(body.password) > MAX_LOGIN_PASSWORD_LENGTH:
        raise failed()
    with closing(connect()) as conn, conn:
        row = conn.execute("SELECT * FROM users WHERE lower(email) = ?", (email,)).fetchone()
        if not password_matches(row, body.password):
            raise failed()
        if hasher.check_needs_rehash(row["password_hash"]):
            conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (hasher.hash(body.password), row["id"]))
    failed_logins.pop(email_key, None)  # a good login clears this account's failed attempts
    needs_update = bool(password_problems(body.password))  # the only moment the server sees the plain password
    start_session(response, row["id"], needs_update)
    return AuthResponse(user=to_user(row), password_update_required=needs_update)


@router.post("/auth/logout", status_code=204)
def logout(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")


@router.get("/auth/me", response_model=AuthResponse)
def current_user(request: Request) -> AuthResponse:
    row = signed_in_user(request)
    session = read_session_token(request.cookies.get(SESSION_COOKIE))
    return AuthResponse(user=to_user(row) if row else None, password_update_required=bool(row and session and session[1]))


@router.post("/auth/change-password", response_model=AuthResponse)
def change_password(body: ChangePasswordRequest, request: Request, response: Response) -> AuthResponse:
    user = signed_in_user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="Please sign in first.")
    email_key = f"email:{user['email'].lower()}"
    wait = lock_seconds_left(email_key, LOGIN_MAX_ATTEMPTS)
    if wait:
        raise locked_out(wait)  # same limit as logging in, so this can't be used to guess the password
    if len(body.current_password) > MAX_LOGIN_PASSWORD_LENGTH or not password_matches(user, body.current_password):
        record_failed_login(email_key)
        attempts_left = LOGIN_MAX_ATTEMPTS - len(failed_logins[email_key])
        if attempts_left <= 0:
            raise locked_out(LOGIN_LOCK_SECONDS)
        raise HTTPException(
            status_code=401,
            detail=f"Your current password is incorrect. You have {attempts_left} attempt{'s' if attempts_left != 1 else ''} left.",
        )
    if len(body.new_password) > MAX_PASSWORD_LENGTH:
        raise bad_request(f"Password can be at most {MAX_PASSWORD_LENGTH} characters.")
    problems = password_problems(body.new_password)
    if problems:
        raise bad_request(f"Password must {join_requirements(problems)}.")
    if body.new_password != body.confirm_password:
        raise bad_request("Passwords do not match.")
    if body.new_password == body.current_password:
        raise bad_request("Please choose a new password that is different from your current one.")
    with closing(connect()) as conn, conn:
        conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (hasher.hash(body.new_password), user["id"]))
    failed_logins.pop(email_key, None)
    start_session(response, user["id"], needs_password_update=False)
    return AuthResponse(user=to_user(user), password_update_required=False)


# ---------- Saved profile and routine (signed-in only) ----------

@router.get("/account/saved")
def get_saved(request: Request):
    user = signed_in_user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="Please sign in first.")
    with closing(connect()) as conn:
        row = conn.execute("SELECT * FROM saved WHERE user_id = ?", (user["id"],)).fetchone()
    if not row:
        return {"saved": None}
    return {"saved": {"profile": json.loads(row["profile_json"]), "result": json.loads(row["routine_json"]), "updated_at": row["updated_at"]}}


@router.put("/account/saved", status_code=204)
def put_saved(body: SavedBody, request: Request) -> None:
    user = signed_in_user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="Please sign in first.")
    profile_json = body.profile.model_dump_json()
    routine_json = json.dumps(body.result)
    if len(routine_json) > MAX_SAVED_BYTES:
        raise bad_request("That routine is too large to save.")
    with closing(connect()) as conn, conn:
        conn.execute(
            """INSERT INTO saved (user_id, profile_json, routine_json, updated_at) VALUES (?, ?, ?, ?)
               ON CONFLICT(user_id) DO UPDATE SET profile_json = excluded.profile_json,
               routine_json = excluded.routine_json, updated_at = excluded.updated_at""",
            (user["id"], profile_json, routine_json, datetime.now(timezone.utc).isoformat(timespec="seconds")),
        )
