import asyncio
import os
from collections.abc import AsyncIterator, Awaitable, Callable
from decimal import Decimal

os.environ["LUNCH_DATABASE_URL"] = os.environ.get(
    "LUNCH_TEST_DATABASE_URL", "postgresql+asyncpg://lunch:lunch@localhost:5433/lunch_test"
)
os.environ["LUNCH_DATABASE_NULL_POOL"] = "true"
# Tests register many users from one client; test_ratelimit.py turns limits back on.
os.environ["LUNCH_RATE_LIMITS_ENABLED"] = "false"

import asyncpg
import httpx
import pytest
from sqlalchemy import text

from lunch.db import SessionLocal, engine
from lunch.main import app
from lunch.models import Base, Currency
from lunch.rooms.events import RoomEventListener, asyncpg_dsn
from lunch.rooms.hub import RoomHub

TEST_RATES = {Currency.CZK: Decimal(1), Currency.EUR: Decimal(25), Currency.BTC: Decimal(2_000_000)}


class FakeMailer:
    def __init__(self) -> None:
        self.sent: list[dict[str, str]] = []

    async def send(self, to: str, subject: str, text: str, html: str) -> None:
        self.sent.append({"to": to, "subject": subject, "text": text, "html": html})


class FakeRates:
    async def get_rates(self) -> dict[Currency, Decimal]:
        return TEST_RATES


async def _prepare_database() -> None:
    url = os.environ["LUNCH_DATABASE_URL"].replace("+asyncpg", "")
    admin_url, db_name = url.rsplit("/", 1)
    conn = await asyncpg.connect(f"{admin_url}/postgres")
    try:
        if not await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", db_name):
            await conn.execute(f'CREATE DATABASE "{db_name}"')
    finally:
        await conn.close()
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)


@pytest.fixture(scope="session", autouse=True)
def database() -> None:
    asyncio.run(_prepare_database())


@pytest.fixture(autouse=True)
async def clean_tables() -> AsyncIterator[None]:
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    async with SessionLocal() as db:
        await db.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
        await db.commit()
    app.state.hub = RoomHub()
    app.state.rates = FakeRates()
    app.state.mailer = FakeMailer()
    # Like a real worker: room changes reach sockets through Postgres LISTEN/NOTIFY.
    events = RoomEventListener(asyncpg_dsn(os.environ["LUNCH_DATABASE_URL"]), app.state.hub)
    await events.start()
    yield
    await events.stop()


BASE_URL = "http://testserver"

ClientFactory = Callable[[str], Awaitable[httpx.AsyncClient]]


@pytest.fixture
async def make_user() -> AsyncIterator[ClientFactory]:
    """Returns a factory creating a registered, logged-in client per username."""
    clients: list[httpx.AsyncClient] = []

    async def factory(username: str) -> httpx.AsyncClient:
        client = httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url=BASE_URL)
        clients.append(client)
        response = await client.post(
            "/api/auth/register",
            json={
                "username": username,
                "email": f"{username}@example.com",
                "password": "password123",
            },
        )
        assert response.status_code == 201, response.text
        return client

    yield factory
    for client in clients:
        await client.aclose()
