"""Salted scrypt passwords, revocable opaque sessions, owner-scoped dependencies."""

import hashlib
import hmac
import secrets
from datetime import timedelta
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.database import session_dependency
from app.models import LoginSession, User, now

DB = Annotated[Session, Depends(session_dependency)]


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1)
    return f"scrypt-v1${salt}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        version, salt, _ = encoded.split("$")
        return version == "scrypt-v1" and hmac.compare_digest(
            hash_password(password, salt), encoded
        )
    except (ValueError, TypeError):
        return False


def new_session(db: Session, user: User, hours: int) -> str:
    token = secrets.token_urlsafe(32)
    db.add(
        LoginSession(
            token_hash=token_hash(token), user_id=user.id, expires_at=now() + timedelta(hours=hours)
        )
    )
    return token


def require_user(request: Request, db: DB) -> User:
    authorization = request.headers.get("authorization", "")
    bearer = authorization.removeprefix("Bearer ") if authorization.startswith("Bearer ") else None
    token = bearer or request.cookies.get("circuitpilot_session")
    if not token:
        raise HTTPException(401, "Authentication required.")
    if not bearer and request.method not in {"GET", "HEAD", "OPTIONS"}:
        origin = request.headers.get("origin")
        if origin not in request.app.state.settings.allowed_origins:
            raise HTTPException(403, "Cookie-authenticated writes require an allowed Origin.")
    login = db.get(LoginSession, token_hash(token))
    if login is None or login.expires_at <= now():
        raise HTTPException(401, "Session expired or invalid.")
    user = db.get(User, login.user_id)
    if user is None:
        raise HTTPException(401, "Session user no longer exists.")
    return user


CurrentUser = Annotated[User, Depends(require_user)]
