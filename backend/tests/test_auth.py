import re
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import update

from lunch.db import SessionLocal
from lunch.main import app
from lunch.models import PasswordResetToken
from tests.conftest import ClientFactory


async def test_register_me_logout_login(make_user: ClientFactory) -> None:
    client = await make_user("alice")
    me = await client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["username"] == "alice"

    assert (await client.post("/api/auth/logout")).status_code == 204
    assert (await client.get("/api/auth/me")).status_code == 401

    bad = await client.post("/api/auth/login", json={"username": "alice", "password": "wrong-pass"})
    assert bad.status_code == 401

    ok = await client.post("/api/auth/login", json={"username": "alice", "password": "password123"})
    assert ok.status_code == 200
    assert (await client.get("/api/auth/me")).json()["username"] == "alice"


async def test_duplicate_username(make_user: ClientFactory) -> None:
    client = await make_user("bob")
    again = await client.post(
        "/api/auth/register",
        json={"username": "bob", "email": "other@example.com", "password": "password123"},
    )
    assert again.status_code == 409
    same_email = await client.post(
        "/api/auth/register",
        json={"username": "bobby", "email": "BOB@example.com", "password": "password123"},
    )
    assert same_email.status_code == 409
    no_email = await client.post(
        "/api/auth/register", json={"username": "bobby", "password": "password123"}
    )
    assert no_email.status_code == 422


async def test_anonymous_is_rejected() -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://testserver"
    ) as client:
        assert (await client.post("/api/rooms")).status_code == 401
        assert (await client.get("/api/history")).status_code == 401
        providers = await client.get("/api/auth/providers")
        assert providers.json() == {"password": True, "google": False}


async def test_account_rename_and_password_change(make_user: ClientFactory) -> None:
    client = await make_user("carol")
    account = (await client.get("/api/auth/account")).json()
    assert account == {
        "id": account["id"],
        "username": "carol",
        "email": "carol@example.com",
        "has_password": True,
        "google_email": None,
        "google_linked": False,
    }

    await make_user("dave")
    taken = await client.patch("/api/auth/account", json={"username": "dave"})
    assert taken.status_code == 409
    renamed = await client.patch("/api/auth/account", json={"username": "carol_2"})
    assert renamed.json()["username"] == "carol_2"
    dup_email = await client.patch("/api/auth/account", json={"email": "dave@example.com"})
    assert dup_email.status_code == 409
    new_email = await client.patch("/api/auth/account", json={"email": "Carol@Work.example"})
    assert new_email.json()["email"] == "carol@work.example"

    wrong = await client.put(
        "/api/auth/password",
        json={"current_password": "nope-nope", "new_password": "brand-new-pass"},
    )
    assert wrong.status_code == 401

    # A second session that should be signed out by the password change.
    other = httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://testserver")
    await other.post("/api/auth/login", json={"username": "carol_2", "password": "password123"})
    assert (await other.get("/api/auth/me")).status_code == 200

    ok = await client.put(
        "/api/auth/password",
        json={"current_password": "password123", "new_password": "brand-new-pass"},
    )
    assert ok.status_code == 204
    assert (await client.get("/api/auth/me")).status_code == 200
    assert (await other.get("/api/auth/me")).status_code == 401
    await other.aclose()

    old = await client.post(
        "/api/auth/login", json={"username": "carol_2", "password": "password123"}
    )
    assert old.status_code == 401
    new = await client.post(
        "/api/auth/login", json={"username": "carol_2", "password": "brand-new-pass"}
    )
    assert new.status_code == 200


async def test_google_unconfigured(make_user: ClientFactory) -> None:
    client = await make_user("erin")
    assert (await client.get("/api/auth/google/login")).status_code == 404
    # Without a password, unlinking Google would lock the account out; here a password exists.
    assert (await client.delete("/api/auth/google")).status_code == 204


def mailer_outbox() -> list[dict[str, str]]:
    return app.state.mailer.sent  # type: ignore[no-any-return]


def token_from(mail: dict[str, str]) -> str:
    match = re.search(r"/reset-password\?token=([\w-]+)", mail["text"])
    assert match, mail["text"]
    return match.group(1)


async def test_forgot_password_unknown_email_reveals_nothing(make_user: ClientFactory) -> None:
    client = await make_user("frank")
    response = await client.post("/api/auth/password/forgot", json={"email": "nobody@example.com"})
    assert response.status_code == 204
    assert mailer_outbox() == []


async def test_password_reset_flow(make_user: ClientFactory) -> None:
    client = await make_user("gina")
    response = await client.post("/api/auth/password/forgot", json={"email": "GINA@example.com"})
    assert response.status_code == 204
    [mail] = mailer_outbox()
    assert mail["to"] == "gina@example.com"
    assert "http://testserver/reset-password?token=" in mail["text"]
    token = token_from(mail)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://testserver"
    ) as browser:
        reset = await browser.post(
            "/api/auth/password/reset", json={"token": token, "new_password": "fresh-password"}
        )
        assert reset.status_code == 200
        assert reset.json()["username"] == "gina"
        # The reset logs this browser in ...
        assert (await browser.get("/api/auth/me")).status_code == 200
    # ... and signs out every older session.
    assert (await client.get("/api/auth/me")).status_code == 401

    again = await client.post(
        "/api/auth/password/reset", json={"token": token, "new_password": "another-password"}
    )
    assert again.status_code == 400
    login = await client.post(
        "/api/auth/login", json={"username": "gina", "password": "fresh-password"}
    )
    assert login.status_code == 200


async def test_only_newest_unexpired_link_works(make_user: ClientFactory) -> None:
    client = await make_user("hank")
    await client.post("/api/auth/password/forgot", json={"email": "hank@example.com"})
    await client.post("/api/auth/password/forgot", json={"email": "hank@example.com"})
    first, second = (token_from(m) for m in mailer_outbox())

    stale = await client.post(
        "/api/auth/password/reset", json={"token": first, "new_password": "fresh-password"}
    )
    assert stale.status_code == 400

    async with SessionLocal() as db:
        await db.execute(
            update(PasswordResetToken).values(expires_at=datetime.now(UTC) - timedelta(minutes=1))
        )
        await db.commit()
    expired = await client.post(
        "/api/auth/password/reset", json={"token": second, "new_password": "fresh-password"}
    )
    assert expired.status_code == 400
