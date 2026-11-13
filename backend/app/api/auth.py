"""/auth: sign up, sign in, refresh, sign out and change password.

Sign-up, sign-in and refresh return a JSON access token (the browser keeps it in memory and sends
it as `Authorization: Bearer`) and set the refresh token as an httpOnly cookie that only these
routes receive.
"""

from fastapi import APIRouter, Cookie, Depends, Request, Response

from app.core.config import settings
from app.core.database import get_db
from app.core.security import current_user
from app.schemas import PasswordChange, SignIn, SignUp
from app.services import auth

router = APIRouter(prefix="/auth", tags=["auth"])
COOKIE = "refresh_token"
COOKIE_PATH = "/api/v1/auth"


def _cookie_options():
    # SameSite=Strict: the site and api.<site> are the same site, so the cookie still flows to the API,
    # while other sites can never send it. Secure (HTTPS only) everywhere except local http.
    return dict(path=COOKIE_PATH, httponly=True, samesite="strict", secure=settings().app_env == "production")


def _with_cookie(response, result):
    body, raw = result
    response.set_cookie(COOKIE, raw, max_age=settings().refresh_token_days * 86400, **_cookie_options())
    return body


@router.post("/signup", status_code=201)
def sign_up(body: SignUp, response: Response, db=Depends(get_db)):
    return _with_cookie(response, auth.sign_up(db, body))


@router.post("/login")
def sign_in(body: SignIn, request: Request, response: Response, db=Depends(get_db)):
    client_ip = request.client.host if request.client else None
    return _with_cookie(response, auth.sign_in(db, body, client_ip))


@router.post("/refresh")
def refresh(response: Response, refresh_token: str | None = Cookie(default=None), db=Depends(get_db)):
    return _with_cookie(response, auth.refresh(db, refresh_token))


@router.post("/logout", status_code=204)
def sign_out(response: Response, refresh_token: str | None = Cookie(default=None), db=Depends(get_db)):
    auth.sign_out(db, refresh_token)
    response.delete_cookie(COOKIE, **_cookie_options())


@router.post("/password")
def change_password(body: PasswordChange, response: Response, user=Depends(current_user), db=Depends(get_db)):
    return _with_cookie(response, auth.change_password(db, user, body))
