"""Google sign-in, driven through the real endpoints with a fake Google client."""

from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from authlib.integrations.starlette_client import OAuthError
from fastapi import Request
from fastapi.responses import RedirectResponse

from lunch.auth import router as auth_router
from lunch.main import app
from tests.conftest import BASE_URL, ClientFactory


class FakeGoogle:
    def __init__(self) -> None:
        self.claims: dict[str, Any] = {"sub": "google-1", "email": "Grace@Gmail.com"}
        self.fail = False
        self.redirect_uri = ""

    async def authorize_redirect(self, request: Request, redirect_uri: str) -> RedirectResponse:
        self.redirect_uri = redirect_uri
        return RedirectResponse(f"https://accounts.google.test/auth?redirect_uri={redirect_uri}")

    async def authorize_access_token(self, request: Request) -> dict[str, Any]:
        if self.fail:
            raise OAuthError(error="access_denied")
        return {"userinfo": self.claims}


class FakeOAuth:
    def __init__(self) -> None:
        self.google = FakeGoogle()


@pytest.fixture
def google(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeGoogle]:
    fake = FakeOAuth()
    monkeypatch.setattr(auth_router.settings, "google_client_id", "client-id")
    monkeypatch.setattr(auth_router.settings, "google_client_secret", "client-secret")
    monkeypatch.setattr(auth_router, "oauth", fake)
    yield fake.google


def anonymous() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url=BASE_URL)


async def sign_in_with_google(client: httpx.AsyncClient, *, link: bool = False) -> httpx.Response:
    start = await client.get("/api/auth/google/login", params={"link": link})
    if start.headers["location"] == "/login":
        return start
    assert start.headers["location"].startswith("https://accounts.google.test/")
    return await client.get("/api/auth/google/callback")


async def test_providers_report_google(google: FakeGoogle) -> None:
    async with anonymous() as client:
        assert (await client.get("/api/auth/providers")).json() == {
            "password": True,
            "google": True,
        }


async def test_sign_in_creates_account_once(google: FakeGoogle) -> None:
    async with anonymous() as client:
        callback = await sign_in_with_google(client)
        assert callback.headers["location"] == "/"
        assert google.redirect_uri == f"{BASE_URL}/api/auth/google/callback"
        account = (await client.get("/api/auth/account")).json()
        assert account["username"] == "grace"
        assert account["email"] == "grace@gmail.com"
        assert account["google_linked"] is True
        assert account["has_password"] is False

    async with anonymous() as again:
        await sign_in_with_google(again)
        assert (await again.get("/api/auth/account")).json()["id"] == account["id"]


async def test_username_clashes_and_short_names(
    google: FakeGoogle, make_user: ClientFactory
) -> None:
    await make_user("grace")
    async with anonymous() as client:
        await sign_in_with_google(client)
        assert (await client.get("/api/auth/me")).json()["username"] == "grace2"

    google.claims = {"sub": "google-2", "email": "al@x.example"}
    async with anonymous() as client:
        await sign_in_with_google(client)
        assert (await client.get("/api/auth/me")).json()["username"] == "al_player"


async def test_google_only_account_needs_a_password_before_unlinking(google: FakeGoogle) -> None:
    async with anonymous() as client:
        await sign_in_with_google(client)
        assert (await client.delete("/api/auth/google")).status_code == 400
        # No password yet: the login endpoint must reject it like any wrong password.
        login = await client.post(
            "/api/auth/login", json={"username": "grace", "password": "whatever123"}
        )
        assert login.status_code == 401

        set_pw = await client.put("/api/auth/password", json={"new_password": "now-i-have-one"})
        assert set_pw.status_code == 204
        assert (await client.delete("/api/auth/google")).status_code == 204
        assert (await client.get("/api/auth/account")).json()["google_linked"] is False


async def test_link_google_to_password_account(
    google: FakeGoogle, make_user: ClientFactory
) -> None:
    henry = await make_user("henry")
    linked = await sign_in_with_google(henry, link=True)
    assert linked.headers["location"] == "/settings?google=linked"
    assert (await henry.get("/api/auth/account")).json()["google_email"] == "grace@gmail.com"

    # The same Google account can't be attached to a second player ...
    ivy = await make_user("ivy")
    taken = await sign_in_with_google(ivy, link=True)
    assert taken.headers["location"] == "/settings?google=taken"

    # ... and a player can't attach a second Google account.
    google.claims = {"sub": "google-other", "email": "other@gmail.com"}
    second = await sign_in_with_google(henry, link=True)
    assert second.headers["location"] == "/settings?google=taken"


async def test_link_requires_login(google: FakeGoogle) -> None:
    async with anonymous() as client:
        response = await sign_in_with_google(client, link=True)
        assert response.headers["location"] == "/login"


async def test_google_error_redirects_to_login(google: FakeGoogle) -> None:
    google.fail = True
    async with anonymous() as client:
        response = await sign_in_with_google(client)
        assert response.headers["location"] == "/login?error=google"
        assert (await client.get("/api/auth/me")).status_code == 401
