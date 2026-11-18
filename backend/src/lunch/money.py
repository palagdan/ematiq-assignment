from collections.abc import Iterable, Mapping
from decimal import Decimal

from lunch.models import Currency

# CZK price of one unit of a currency.
Rates = Mapping[Currency, Decimal]

_PRECISION = {
    Currency.CZK: Decimal("0.01"),
    Currency.EUR: Decimal("0.01"),
    Currency.BTC: Decimal("0.00000001"),
}


def quantize(amount: Decimal, currency: Currency) -> Decimal:
    return amount.quantize(_PRECISION[currency])


def convert(amount: Decimal, source: Currency, target: Currency, rates: Rates) -> Decimal:
    return amount * rates[source] / rates[target]


def totals(meals: Iterable[tuple[Decimal, Currency]], rates: Rates) -> dict[Currency, Decimal]:
    """Sum meals of mixed currencies, expressed in every supported currency."""
    czk = sum((convert(amount, cur, Currency.CZK, rates) for amount, cur in meals), Decimal(0))
    return {cur: quantize(convert(czk, Currency.CZK, cur, rates), cur) for cur in Currency}


def serialize_rates(rates: Rates) -> dict[str, str]:
    return {cur.value: str(rate) for cur, rate in rates.items()}


def parse_rates(raw: Mapping[str, object]) -> dict[Currency, Decimal]:
    return {Currency(code): Decimal(str(rate)) for code, rate in raw.items() if code in Currency}
