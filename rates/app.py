"""Mock exchange-rate service.

Returns how many CZK one unit of each supported currency costs. Rates drift
slightly on every request so the app has to deal with values that change.
"""

import random
from decimal import Decimal

from fastapi import FastAPI

app = FastAPI(title="Mock rates service")

_rates: dict[str, Decimal] = {
    "CZK": Decimal("1"),
    "EUR": Decimal("25.10"),
    "BTC": Decimal("2300000"),
}


def _drift(value: Decimal, max_pct: float) -> Decimal:
    factor = Decimal(str(1 + random.uniform(-max_pct, max_pct)))
    return (value * factor).quantize(Decimal("0.0001"))


@app.get("/rates")
async def get_rates() -> dict[str, object]:
    _rates["EUR"] = _drift(_rates["EUR"], 0.002)
    _rates["BTC"] = _drift(_rates["BTC"], 0.01)
    return {"base": "CZK", "rates": {code: str(rate) for code, rate in _rates.items()}}
