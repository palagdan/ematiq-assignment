import asyncio
import logging
import time
from decimal import Decimal, InvalidOperation
from typing import Protocol

import httpx

from lunch.models import Currency

log = logging.getLogger(__name__)

# Used only if the rates service has never answered since startup.
FALLBACK_RATES: dict[Currency, Decimal] = {
    Currency.CZK: Decimal("1"),
    Currency.EUR: Decimal("25"),
    Currency.BTC: Decimal("2300000"),
}


class InvalidRates(ValueError):
    pass


def validate_rates(raw: object) -> dict[Currency, Decimal]:
    """Parse an untrusted rates payload; every currency must have a positive, finite rate.

    Anything else would end up as a divisor in money.convert(), so it's rejected here.
    """
    if not isinstance(raw, dict):
        raise InvalidRates(f"rates must be an object, got {type(raw).__name__}")
    rates: dict[Currency, Decimal] = {}
    for currency in Currency:
        if currency.value not in raw:
            raise InvalidRates(f"missing rate for {currency.value}")
        try:
            rate = Decimal(str(raw[currency.value]))
        except InvalidOperation:
            raise InvalidRates(
                f"{currency.value} rate is not a number: {raw[currency.value]!r}"
            ) from None
        if not rate.is_finite() or rate <= 0:
            raise InvalidRates(f"{currency.value} rate must be positive and finite, got {rate}")
        rates[currency] = rate
    return rates


class RatesProvider(Protocol):
    async def get_rates(self) -> dict[Currency, Decimal]: ...


class RatesClient:
    """Fetches rates from the rates service, caching them for `ttl` seconds.

    If the service is down, the last known rates are served instead.
    """

    def __init__(self, base_url: str, http: httpx.AsyncClient, ttl: float = 60.0) -> None:
        self._url = f"{base_url.rstrip('/')}/rates"
        self._http = http
        self._ttl = ttl
        self._cached: dict[Currency, Decimal] | None = None
        self._fetched_at = 0.0
        self._lock = asyncio.Lock()

    def _fresh(self) -> bool:
        return self._cached is not None and time.monotonic() - self._fetched_at < self._ttl

    async def get_rates(self) -> dict[Currency, Decimal]:
        if self._fresh() and self._cached is not None:
            return self._cached
        async with self._lock:
            if self._fresh() and self._cached is not None:
                return self._cached
            try:
                response = await self._http.get(self._url)
                response.raise_for_status()
                rates = validate_rates(response.json()["rates"])
            except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
                log.warning("rates service unavailable: %s", exc)
                return self._cached or FALLBACK_RATES
            self._cached = rates
            self._fetched_at = time.monotonic()
            return rates
