from decimal import Decimal

import httpx
import pytest

from lunch.models import Currency
from lunch.rates_client import FALLBACK_RATES, RatesClient

GOOD = {"base": "CZK", "rates": {"CZK": "1", "EUR": "25.5", "BTC": "2000000"}}


def client_with(handler: httpx.MockTransport, ttl: float = 60.0) -> RatesClient:
    return RatesClient("http://rates.test/", httpx.AsyncClient(transport=handler), ttl=ttl)


async def test_fetches_and_caches() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert request.url == "http://rates.test/rates"
        return httpx.Response(200, json=GOOD)

    rates = client_with(httpx.MockTransport(handler))
    first = await rates.get_rates()
    second = await rates.get_rates()
    assert first == {Currency.CZK: 1, Currency.EUR: Decimal("25.5"), Currency.BTC: 2_000_000}
    assert second is first
    assert calls == 1


async def test_refetches_after_ttl() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json=GOOD)

    rates = client_with(httpx.MockTransport(handler), ttl=0)
    await rates.get_rates()
    await rates.get_rates()
    assert calls == 2


async def test_keeps_last_rates_when_service_goes_down() -> None:
    up = True

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=GOOD) if up else httpx.Response(503)

    rates = client_with(httpx.MockTransport(handler), ttl=0)
    known = await rates.get_rates()
    up = False
    assert await rates.get_rates() == known


async def test_falls_back_without_any_answer() -> None:
    def unreachable(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    assert await client_with(httpx.MockTransport(unreachable)).get_rates() == FALLBACK_RATES


async def test_rejects_incomplete_rates() -> None:
    def partial(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"rates": {"CZK": "1", "EUR": "25"}})

    assert await client_with(httpx.MockTransport(partial)).get_rates() == FALLBACK_RATES


@pytest.mark.parametrize(
    "bad",
    [
        {"CZK": "1", "EUR": "0", "BTC": "2000000"},  # would divide by zero
        {"CZK": "1", "EUR": "-25", "BTC": "2000000"},  # negative
        {"CZK": "1", "EUR": "NaN", "BTC": "2000000"},  # parses, but not finite
        {"CZK": "1", "EUR": "Infinity", "BTC": "2000000"},
        {"CZK": "1", "EUR": "abc", "BTC": "2000000"},  # InvalidOperation, not ValueError
        {"CZK": "1", "EUR": None, "BTC": "2000000"},
        ["not", "an", "object"],
    ],
)
async def test_rejects_unusable_rates_and_keeps_last_good_ones(bad: object) -> None:
    serve_bad = False

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"rates": bad} if serve_bad else GOOD)

    rates = client_with(httpx.MockTransport(handler), ttl=0)
    good = await rates.get_rates()
    serve_bad = True
    assert await rates.get_rates() == good
    assert await client_with(httpx.MockTransport(handler)).get_rates() == FALLBACK_RATES
