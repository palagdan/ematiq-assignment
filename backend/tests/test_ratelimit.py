import asyncio
import time
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from lunch import ratelimit
from lunch.config import get_settings
from lunch.db import SessionLocal
from lunch.main import app
from lunch.models import RateLimitHit
from lunch.ratelimit import Rule, TooManyRequests
from tests.conftest import BASE_URL, ClientFactory


@pytest.fixture(autouse=True)
def limits_on(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(get_settings(), "rate_limits_enabled", True)
    yield


def tighten(monkeypatch: pytest.MonkeyPatch, name: str, limit: int) -> None:
    rule: Rule = getattr(ratelimit, name)
    monkeypatch.setattr(ratelimit, name, Rule(rule.name, limit, rule.window))


def client_from(ip: str) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app, client=(ip, 1234)), base_url=BASE_URL
    )


async def login(client: httpx.AsyncClient, username: str, password: str) -> httpx.Response:
    return await client.post("/api/auth/login", json={"username": username, "password": password})


async def test_failed_logins_are_counted_per_ip_and_account(
    make_user: ClientFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    tighten(monkeypatch, "LOGIN_PER_ACCOUNT", 3)
    await make_user("alice")
    await make_user("bob")
    async with client_from("10.0.0.1") as attacker, client_from("10.0.0.2") as colleague:
        for _ in range(3):
            assert (await login(attacker, "alice", "wrong-password")).status_code == 401
        blocked = await login(attacker, "alice", "password123")  # even the right password now
        assert blocked.status_code == 429
        assert 0 < int(blocked.headers["Retry-After"]) <= 300
        assert "Too many attempts" in blocked.json()["detail"]

        # Alice herself, from another machine, is not locked out ...
        assert (await login(colleague, "alice", "password123")).status_code == 200
        # ... and the attacker can still use other accounts until the per-IP limit.
        assert (await login(attacker, "bob", "password123")).status_code == 200


async def test_login_per_ip_limit(
    make_user: ClientFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    tighten(monkeypatch, "LOGIN_PER_IP", 4)
    await make_user("carol")
    async with client_from("10.0.0.3") as sprayer:
        for name in ("user1", "user2", "user3", "user4"):  # password spraying across accounts
            assert (await login(sprayer, name, "password123")).status_code == 401
        assert (await login(sprayer, "carol", "password123")).status_code == 429


async def test_forgot_password_limited_per_email_without_leaking(
    make_user: ClientFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    tighten(monkeypatch, "FORGOT_PER_EMAIL", 2)
    await make_user("dana")
    async with client_from("10.0.0.4") as client:
        for email in ("dana@example.com", "nobody@example.com"):  # existing and unknown alike
            for _ in range(2):
                assert (
                    await client.post("/api/auth/password/forgot", json={"email": email})
                ).status_code == 204
            assert (
                await client.post("/api/auth/password/forgot", json={"email": email})
            ).status_code == 429
    assert len(app.state.mailer.sent) == 2  # the inbox got at most the allowed emails


async def test_registration_limited_per_ip(monkeypatch: pytest.MonkeyPatch) -> None:
    tighten(monkeypatch, "REGISTER_PER_IP", 2)
    async with client_from("10.0.0.5") as client:
        for i in range(3):
            response = await client.post(
                "/api/auth/register",
                json={
                    "username": f"spam{i}",
                    "email": f"spam{i}@example.com",
                    "password": "password123",
                },
            )
            assert response.status_code == (201 if i < 2 else 429)


async def test_room_creation_limited_per_user(
    make_user: ClientFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    tighten(monkeypatch, "ROOM_CREATE_PER_USER", 2)
    erin = await make_user("erin")
    for _ in range(2):
        code = (await erin.post("/api/rooms")).json()["code"]
        await erin.post(f"/api/rooms/{code}/leave")
    assert (await erin.post("/api/rooms")).status_code == 429


async def test_counting_is_atomic_under_concurrency() -> None:
    rule = Rule("concurrency-test", 5, timedelta(minutes=5))
    results = await asyncio.gather(
        *(ratelimit.enforce((rule, "same-subject")) for _ in range(20)), return_exceptions=True
    )
    assert sum(r is None for r in results) == 5
    assert all(isinstance(r, TooManyRequests) for r in results if r is not None)


async def test_window_rolls_over() -> None:
    rule = Rule("rollover-test", 1, timedelta(seconds=1))
    await asyncio.sleep(1 - time.time() % 1 + 0.05)  # start right after a window boundary
    await ratelimit.enforce((rule, "x"))
    with pytest.raises(TooManyRequests):
        await ratelimit.enforce((rule, "x"))
    await asyncio.sleep(1)
    await ratelimit.enforce((rule, "x"))  # new window


async def test_old_windows_are_purged() -> None:
    async with SessionLocal() as db:
        db.add(RateLimitHit(key="old", window_start=datetime.now(UTC) - timedelta(days=2), hits=3))
        db.add(RateLimitHit(key="recent", window_start=datetime.now(UTC), hits=1))
        await db.commit()
    assert await ratelimit.purge_old_windows() == 1
