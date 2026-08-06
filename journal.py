"""Persist and score signals using subsequent closed-candle highs and lows."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta

import pandas as pd

from signals import Signal

MAX_RECORDS = 500
_TH_TZ = timezone(timedelta(hours=7))


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


def _time_th(value: str | None) -> str:
    if not value:
        return "—"
    try:
        dt = datetime.fromisoformat(str(value))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(_TH_TZ).strftime("%d/%m %H:%M")
    except (TypeError, ValueError):
        return str(value)


def _price(value: float) -> str:
    return f"{value:.2f}" if abs(value) >= 1000 else f"{value:.5f}"


def performance_table(state: dict, limit: int = 15) -> str:
    """Return recent per-signal results formatted for Telegram HTML."""
    rows = records(state)
    limit = max(1, min(int(limit), 20))
    selected = list(reversed(rows[-limit:]))
    if not selected:
        return "📋 <b>Per-signal Performance</b>\nNo signals recorded yet."

    icons = {"WIN": "✅", "LOSS": "❌", "OPEN": "⏳"}
    lines = [f"📋 <b>Recent Signal Results</b> — newest {len(selected)}"]
    for number, item in enumerate(selected, 1):
        status = item.get("status", "OPEN")
        result = item.get("r_multiple")
        result_text = f" ({float(result):+.1f}R)" if result is not None else ""
        lines.extend([
            "",
            f"<b>{number}. {item['symbol']} {item['direction']} — "
            f"{icons.get(status, '•')} {status}{result_text}</b>",
            f"Entry {_price(float(item['entry']))} | SL {_price(float(item['sl']))} | "
            f"TP {_price(float(item['tp']))}",
            f"{item.get('signal_type', '—')} | Open {_time_th(item.get('opened_at'))}",
        ])
        if status != "OPEN":
            lines.append(f"Closed {_time_th(item.get('closed_at'))}")

    lines.append("\nCandle SL/TP results, not broker fills.")
    return "\n".join(lines)
