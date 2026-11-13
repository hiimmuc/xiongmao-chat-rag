"""Accounts and sign-in sessions: sign up, sign in, refresh, sign out and change password.

A session is one signed-in browser. Its refresh token is a random value sent only in an httpOnly
cookie; the database keeps just its SHA-256 hash, so a database leak does not leak sessions.
Signing out or changing the password deletes session rows, which ends them at once.
"""

import hashlib
import secrets
import time
from collections import defaultdict, deque
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.core.security import active_user, hash_password, issue_access_token, verify_password
from app.models import LoginSession, User, now, uid

# Failed sign-ins allowed per email and per client address in WINDOW seconds.
# Kept in memory, which is enough for the single API process.
WINDOW = 15 * 60
LIMITS = {"email": 5, "ip": 20}
_failures = defaultdict(deque)


def _too_many(keys):
    cutoff = time.monotonic() - WINDOW
    for key in keys:
        attempts = _failures[key]
        while attempts and attempts[0] < cutoff:
            attempts.popleft()
        if not attempts:
            del _failures[key]
        elif len(attempts) >= LIMITS[key[0]]:
            return True
    return False


def _hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def _expiry():
    return now() + timedelta(days=settings().refresh_token_days)


def account_json(user):
    return dict(id=user.id, email=user.email, display_name=user.display_name)


def tokens(user):
    access, lifetime = issue_access_token(user)
    return dict(access_token=access, token_type="bearer", expires_in=lifetime, user=account_json(user))


def start_session(db, user):
    """Returns (response body, raw refresh token for the cookie)."""
    raw = secrets.token_urlsafe(32)
    db.execute(delete(LoginSession).where(LoginSession.expires_at < now()))  # tidy expired ones
    db.add(LoginSession(user_id=user.id, token_hash=_hash(raw), expires_at=_expiry()))
    db.commit()
    return tokens(user), raw


def sign_up(db, body):
    user = User(
        subject=uid(),
        email=body.email,
        password_hash=hash_password(body.password),
        display_name=body.display_name or "",
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "An account with this email already exists") from None
    return start_session(db, user)


def sign_in(db, body, client_ip):
    keys = [("email", body.email), ("ip", client_ip or "unknown")]
    if _too_many(keys):
        raise HTTPException(429, "Too many failed sign-ins. Try again in 15 minutes.")
    user = db.scalar(select(User).where(User.email == body.email))
    if not verify_password(body.password, user.password_hash if user else None):
        for key in keys:
            _failures[key].append(time.monotonic())
        raise HTTPException(401, "Wrong email or password")
    active_user(db, user.subject)
    _failures.pop(keys[0], None)
    return start_session(db, user)


def refresh(db, raw):
    """A new access token for a valid refresh token; also extends the session."""
    session = raw and db.scalar(select(LoginSession).where(LoginSession.token_hash == _hash(raw)))
    if not session or session.expires_at < now():
        raise HTTPException(401, "Session expired; sign in again")
    user = active_user(db, db.get(User, session.user_id).subject)
    session.expires_at = _expiry()
    db.commit()
    return tokens(user), raw


def sign_out(db, raw):
    if raw:
        db.execute(delete(LoginSession).where(LoginSession.token_hash == _hash(raw)))
        db.commit()


def end_all_sessions(db, user):
    db.execute(delete(LoginSession).where(LoginSession.user_id == user.id))
    db.commit()


def check_password(user, password):
    if not verify_password(password, user.password_hash):
        raise HTTPException(403, dict(code="wrong_password", message="The password is not correct"))


def change_password(db, user, body):
    """Sets the new password, signs out every browser and starts a new session for this one."""
    check_password(user, body.current_password)
    user.password_hash = hash_password(body.new_password)
    end_all_sessions(db, user)
    return start_session(db, user)
