"""Sign-in plumbing: password hashing, JWT access tokens and the `current_user` dependency.

Access token: a short-lived JWT (HS256, signed with JWT_SECRET) sent as `Authorization: Bearer`.
The longer-lived refresh token is an opaque random value kept in an httpOnly cookie; see
services/auth.py.
"""

import base64
import hashlib
import hmac
import secrets
import time

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select

from app.core.config import settings
from app.core.database import get_db
from app.models import Deletion, User

bearer = HTTPBearer(auto_error=False)
ALGORITHM = "HS256"

# scrypt: memory-hard password hashing from the standard library (32 MiB, about 0.1 s per hash).
SCRYPT = dict(n=2**15, r=8, p=1)


def _b64(data):
    return base64.b64encode(data).decode()


def hash_password(password):
    """Stored as `scrypt$n$r$p$salt$digest`, so the cost can be raised later without breaking old hashes."""
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, maxmem=64 * 1024 * 1024, **SCRYPT)
    return f"scrypt${SCRYPT['n']}${SCRYPT['r']}${SCRYPT['p']}${_b64(salt)}${_b64(digest)}"


def verify_password(password, stored):
    """True if `password` matches the stored hash. A missing hash still costs one hash, so timing
    does not reveal whether an account exists."""
    if not stored:
        hash_password(password)
        return False
    _, n, r, p, salt, digest = stored.split("$")
    actual = hashlib.scrypt(
        password.encode(), salt=base64.b64decode(salt), n=int(n), r=int(r), p=int(p), maxmem=64 * 1024 * 1024
    )
    return hmac.compare_digest(actual, base64.b64decode(digest))


def issue_access_token(user):
    """Returns (token, lifetime in seconds)."""
    lifetime = settings().access_token_minutes * 60
    issued = int(time.time())
    claims = dict(sub=user.subject, type="access", iat=issued, exp=issued + lifetime)
    return jwt.encode(claims, settings().jwt_secret, algorithm=ALGORITHM), lifetime


def verify_token(token: str):
    try:
        claims = jwt.decode(
            token, settings().jwt_secret, algorithms=[ALGORITHM], options={"require": ["exp", "iat", "sub"]}
        )
    except jwt.PyJWTError:
        raise HTTPException(401, "Invalid or expired access token") from None
    if claims.get("type") != "access":
        raise HTTPException(401, "Invalid or expired access token")
    return claims


def active_user(db, subject):
    """The user with this subject, refusing deleted or deleting accounts."""
    # The journal check also covers a database restored from before the account was deleted.
    if db.scalar(
        select(Deletion.id).where(Deletion.subject == subject, Deletion.resource_type == "account").limit(1)
    ):
        raise HTTPException(403, "Account unavailable")
    user = db.scalar(select(User).where(User.subject == subject))
    if not user:
        raise HTTPException(401, "Invalid or expired access token")
    if user.state != "active":
        raise HTTPException(403, "Account unavailable")
    return user


def current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer), db=Depends(get_db)):
    """FastAPI dependency: the active user behind the bearer token."""
    if not credentials:
        raise HTTPException(401, "Login required")
    return active_user(db, verify_token(credentials.credentials)["sub"])
