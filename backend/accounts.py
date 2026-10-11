"""Local accounts with hashed passwords and revocable, expiring sessions."""
import hashlib
import hmac
import secrets
import sqlite3
import time

from fastapi import HTTPException, Request, Response
from pydantic import BaseModel, Field, field_validator

from . import db

SESSION_SECONDS = 7 * 24 * 60 * 60
COOKIE = "rxcompare_session"


class Credentials(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=10, max_length=128)

    @field_validator("email")
    @classmethod
    def valid_email(cls, value):
        value = value.strip().lower()
        if value.count("@") != 1 or "." not in value.split("@")[1] or any(c.isspace() for c in value):
            raise ValueError("Enter a valid email address")
        return value


def password_hash(password, salt):
    return hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 600_000).hex()


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def current_user(request: Request):
    token = request.cookies.get(COOKIE, "")
    with db.conn() as c:
        row = c.execute("SELECT u.id,u.email FROM users u JOIN sessions s ON s.user_id=u.id "
                        "WHERE s.token_hash=? AND s.expires_at>?", (token_hash(token), time.time())).fetchone()
    if not row:
        raise HTTPException(401, "Please log in to continue")
    return dict(row)


def set_session(user, request, response):
    token = secrets.token_urlsafe(32)
    with db.conn() as c:
        c.execute("DELETE FROM sessions WHERE expires_at<=?", (time.time(),))
        c.execute("INSERT INTO sessions(token_hash,user_id,expires_at) VALUES(?,?,?)",
                  (token_hash(token), user["id"], time.time() + SESSION_SECONDS))
    response.set_cookie(COOKIE, token, max_age=SESSION_SECONDS, httponly=True,
                        secure=request.url.scheme == "https", samesite="strict", path="/")
    response.headers["Cache-Control"] = "no-store"
    return user


def register(credentials, request, response):
    salt = secrets.token_hex(16)
    hashed = password_hash(credentials.password, salt)
    try:
        with db.conn() as c:
            cursor = c.execute("INSERT INTO users(email,password_hash,salt) VALUES(?,?,?)",
                               (credentials.email, hashed, salt))
            user = {"id": cursor.lastrowid, "email": credentials.email}
    except sqlite3.IntegrityError:
        raise HTTPException(409, "An account with this email already exists")
    return set_session(user, request, response)


def login(credentials, request, response):
    # Persist failed-attempt throttling; generic errors do not disclose account existence.
    key = token_hash(credentials.email + "|" + (request.client.host if request.client else "unknown"))
    with db.conn() as c:
        c.execute("DELETE FROM login_attempts WHERE attempted_at<?", (time.time() - 900,))
        count = c.execute("SELECT COUNT(*) FROM login_attempts WHERE attempt_key=?", (key,)).fetchone()[0]
        if count >= 10:
            raise HTTPException(429, "Too many attempts. Try again in 15 minutes")
        c.execute("INSERT INTO login_attempts(attempt_key,attempted_at) VALUES(?,?)", (key, time.time()))
        row = c.execute("SELECT * FROM users WHERE email=?", (credentials.email,)).fetchone()
    hashed = password_hash(credentials.password, row["salt"] if row else "00" * 16)
    if not row or not hmac.compare_digest(hashed, row["password_hash"]):
        raise HTTPException(401, "Incorrect email or password")
    with db.conn() as c:
        c.execute("DELETE FROM login_attempts WHERE attempt_key=?", (key,))
    return set_session({"id": row["id"], "email": row["email"]}, request, response)


def logout(request, response):
    with db.conn() as c:
        c.execute("DELETE FROM sessions WHERE token_hash=?", (token_hash(request.cookies.get(COOKIE, "")),))
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}