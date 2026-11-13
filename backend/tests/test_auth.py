"""Real sign-up, sign-in, refresh, sign-out and JWT checks (no test shortcut for the token)."""

import time

import jwt
import pytest
from test_api import PREFIX

from app.core import security
from app.core.config import settings
from app.core.security import verify_token as real_verify_token
from app.services import auth as auth_service

EMAIL, PASSWORD = "Ada@Example.test", "a long enough password"


@pytest.fixture
def client(api, monkeypatch):
    client, _, _ = api
    monkeypatch.setattr(security, "verify_token", real_verify_token)
    auth_service._failures.clear()
    return client


def post(client, path, **kwargs):
    return client.post(PREFIX + path, **kwargs)


def refresh_with(client, cookie):
    client.cookies.set("refresh_token", cookie, path="/api/v1/auth")
    return post(client, "/auth/refresh")


def bearer(body):
    return {"Authorization": "Bearer " + body["access_token"]}


def test_sign_up_sign_in_refresh_and_sign_out(client):
    created = post(client, "/auth/signup", json=dict(email=EMAIL, password=PASSWORD, display_name="Ada"))
    assert created.status_code == 201
    body = created.json()
    assert body["user"]["email"] == "ada@example.test"  # stored lower-case
    assert body["token_type"] == "bearer" and body["expires_in"] == settings().access_token_minutes * 60
    cookie = created.headers["set-cookie"]
    assert "refresh_token=" in cookie and "HttpOnly" in cookie and "Path=/api/v1/auth" in cookie
    assert "samesite=strict" in cookie.lower()
    assert client.get(PREFIX + "/me", headers=bearer(body)).json()["display_name"] == "Ada"

    assert (
        post(client, "/auth/signup", json=dict(email="ada@example.test", password=PASSWORD)).status_code
        == 409
    )
    assert post(client, "/auth/login", json=dict(email=EMAIL, password="wrong password")).status_code == 401
    signed_in = post(client, "/auth/login", json=dict(email="ADA@example.test", password=PASSWORD))
    assert signed_in.status_code == 200

    refreshed = post(client, "/auth/refresh")  # the TestClient sends the cookie back
    assert refreshed.status_code == 200
    assert client.get(PREFIX + "/me", headers=bearer(refreshed.json())).status_code == 200

    assert post(client, "/auth/logout").status_code == 204
    client.cookies.clear()
    assert post(client, "/auth/refresh").status_code == 401


def test_sign_out_ends_the_session_server_side(client):
    post(client, "/auth/signup", json=dict(email=EMAIL, password=PASSWORD))
    stolen = client.cookies.get("refresh_token")
    post(client, "/auth/logout")
    assert refresh_with(client, stolen).status_code == 401


def test_password_change_signs_out_other_browsers(client):
    first = post(client, "/auth/signup", json=dict(email=EMAIL, password=PASSWORD)).json()
    other_browser = client.cookies.get("refresh_token")
    wrong = post(
        client,
        "/auth/password",
        headers=bearer(first),
        json=dict(current_password="wrong", new_password="another long password"),
    )
    assert wrong.status_code == 403
    changed = post(
        client,
        "/auth/password",
        headers=bearer(first),
        json=dict(current_password=PASSWORD, new_password="another long password"),
    )
    assert changed.status_code == 200
    assert refresh_with(client, other_browser).status_code == 401
    assert post(client, "/auth/login", json=dict(email=EMAIL, password=PASSWORD)).status_code == 401
    login = post(client, "/auth/login", json=dict(email=EMAIL, password="another long password"))
    assert login.status_code == 200


@pytest.mark.parametrize(
    "body",
    [
        dict(email="not-an-email", password=PASSWORD),
        dict(email=EMAIL, password="short"),
        dict(email=EMAIL, password=PASSWORD, role="admin"),
    ],
)
def test_sign_up_validation(client, body):
    assert post(client, "/auth/signup", json=body).status_code == 422


def test_repeated_wrong_passwords_are_throttled(client):
    post(client, "/auth/signup", json=dict(email=EMAIL, password=PASSWORD))
    for _ in range(auth_service.LIMITS["email"]):
        assert post(client, "/auth/login", json=dict(email=EMAIL, password="wrong")).status_code == 401
    # Even the right password waits until the window passes.
    assert post(client, "/auth/login", json=dict(email=EMAIL, password=PASSWORD)).status_code == 429


@pytest.mark.parametrize(
    "change",
    [
        dict(type="refresh"),
        dict(exp=1),
        dict(sub=None),
    ],
)
def test_access_token_validation(change):
    now = int(time.time())
    claims = dict(sub="owner", type="access", iat=now, exp=now + 300)
    assert real_verify_token(jwt.encode(claims, settings().jwt_secret, algorithm="HS256"))["sub"] == "owner"
    claims = {k: v for k, v in {**claims, **change}.items() if v is not None}
    with pytest.raises(Exception) as error:
        real_verify_token(jwt.encode(claims, settings().jwt_secret, algorithm="HS256"))
    assert error.value.status_code == 401


def test_tokens_signed_with_another_secret_are_rejected():
    now = int(time.time())
    forged = jwt.encode(dict(sub="owner", type="access", iat=now, exp=now + 300), "x" * 32, algorithm="HS256")
    with pytest.raises(Exception) as error:
        real_verify_token(forged)
    assert error.value.status_code == 401


def test_password_hashes_are_salted_and_verifiable():
    first, second = security.hash_password(PASSWORD), security.hash_password(PASSWORD)
    assert first != second and first.startswith("scrypt$")
    assert security.verify_password(PASSWORD, first)
    assert not security.verify_password("wrong", first)
    assert not security.verify_password(PASSWORD, None)


def test_production_requires_a_jwt_secret(monkeypatch):
    from app.core import config

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("JWT_SECRET", "too-short")
    config.settings.cache_clear()
    try:
        with pytest.raises(RuntimeError):
            config.settings()
    finally:
        config.settings.cache_clear()
