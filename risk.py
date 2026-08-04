"""Risk-based position-size estimates for USD accounts."""
from __future__ import annotations

import config

_CONTRACT_SIZE = {
    "XAUUSD": 100.0,
    "XAGUSD": 5000.0,
    "BTCUSD": 1.0,
    "ETHUSD": 1.0,
}


def estimate(symbol: str, entry: float, stop: float) -> tuple[float, float, float]:
    """Return (risk money, units, lots). This is an estimate, not an order."""
    risk_money = config.ACCOUNT_BALANCE * config.RISK_PERCENT / 100
    distance = abs(entry - stop)
    if distance <= 0 or config.ACCOUNT_CURRENCY != "USD":
        return risk_money, 0.0, 0.0

    # For USD-quoted instruments, P/L per unit is the price movement in USD.
    # USD-base FX pairs (e.g. USDJPY) need quote-currency conversion.
    value_per_unit = distance
    upper = symbol.upper()
    if upper.startswith("USD") and not upper.endswith("USD"):
        value_per_unit = distance / entry

    units = risk_money / value_per_unit
    contract = _CONTRACT_SIZE.get(upper, 100_000.0 if len(upper) == 6 else 1.0)
    return risk_money, units, units / contract
