"""Persist and score signals using subsequent closed-candle highs and lows."""
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from signals import Signal

MAX_RECORDS = 500


def records(state: dict) -> list[dict]:
    return state.setdefault("signal_journal", [])


def record(state: dict, signal: Signal) -> None:
    records(state).append({
        "id": f"{signal.symbol}|{signal.direction}|{signal.candle_time}",
        "symbol": signal.symbol,
        "direction": signal.direction,
        "signal_type": signal.signal_type,
        "opened_at": signal.candle_time or datetime.now(timezone.utc).isoformat(),
        "entry": signal.price,
        "sl": signal.sl,
        "tp": signal.tp,
        "risk_amount": signal.risk_amount,
        "lot_size": signal.lot_size,
        "status": "OPEN",
    })
    state["signal_journal"] = records(state)[-MAX_RECORDS:]


def evaluate(state: dict, symbol: str, df: pd.DataFrame) -> None:
    """Close journal entries when a later candle reaches SL or TP.

    If both levels occur within one candle, count SL first (conservative because
    OHLC data cannot reveal which level was touched first).
    """
    if df is None or df.empty or "time" not in df.columns:
        return
    times = pd.to_datetime(df["time"], utc=True)
    for item in records(state):
        if item.get("status") != "OPEN" or item.get("symbol") != symbol:
            continue
        opened = pd.to_datetime(item["opened_at"], utc=True, errors="coerce")
        later = df[times > opened]
        for _, bar in later.iterrows():
            if item["direction"] == "BUY":
                stopped = float(bar["low"]) <= item["sl"]
                won = float(bar["high"]) >= item["tp"]
            else:
                stopped = float(bar["high"]) >= item["sl"]
                won = float(bar["low"]) <= item["tp"]
            if stopped or won:
                item["status"] = "LOSS" if stopped else "WIN"
                item["closed_at"] = str(bar["time"])
                item["r_multiple"] = -1.0 if stopped else abs(
                    (item["tp"] - item["entry"]) / (item["entry"] - item["sl"])
                )
                break


def summary(state: dict) -> str:
    rows = records(state)
    closed = [r for r in rows if r.get("status") in ("WIN", "LOSS")]
    wins = sum(r["status"] == "WIN" for r in closed)
    losses = len(closed) - wins
    open_count = sum(r.get("status") == "OPEN" for r in rows)
    win_rate = wins / len(closed) * 100 if closed else 0.0
    net_r = sum(float(r.get("r_multiple", 0)) for r in closed)
    return (
        "📈 <b>Signal Performance</b>\n"
        f"Recorded: <b>{len(rows)}</b> | Open: <b>{open_count}</b>\n"
        f"Closed: <b>{len(closed)}</b> ({wins} wins / {losses} losses)\n"
        f"Win rate: <b>{win_rate:.1f}%</b>\n"
        f"Net result: <b>{net_r:+.1f}R</b>\n"
        "Based on candle SL/TP touches; not broker execution results."
    )
