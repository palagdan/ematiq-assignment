import httpx
import pytest

from lunch.mailer import SmtpMailer
from lunch.main import app, lifespan
from lunch.rates_client import RatesClient
from lunch.rooms.hub import RoomHub
from tests.conftest import BASE_URL, ClientFactory


async def test_lifespan_wires_services() -> None:
    async with lifespan(app):
        assert isinstance(app.state.rates, RatesClient)
        assert isinstance(app.state.hub, RoomHub)
        assert isinstance(app.state.mailer, SmtpMailer)


async def test_health_and_rates(make_user: ClientFactory) -> None:
    client = await make_user("alice")
    assert (await client.get("/api/health")).json() == {"status": "ok"}
    assert (await client.get("/api/rates")).json() == {"CZK": "1", "EUR": "25", "BTC": "2000000"}


async def test_logout_without_session() -> None:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url=BASE_URL) as client:
        assert (await client.post("/api/auth/logout")).status_code == 204


async def test_reset_email_failure_is_not_shown_to_the_user(
    make_user: ClientFactory, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    await make_user("ann")

    async def broken_send(*args: object) -> None:
        raise ConnectionRefusedError("smtp down")

    monkeypatch.setattr(app.state.mailer, "send", broken_send)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url=BASE_URL) as client:
        response = await client.post("/api/auth/password/forgot", json={"email": "ann@example.com"})
    assert response.status_code == 204
    assert "could not send password reset email" in caplog.text
