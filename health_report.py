"""Daily operational heartbeat sent through Telegram."""
from __future__ import annotations

from datetime import datetime, timezone

import config
import data_feed
import journal
import notifier

REPORT_HOUR_UTC = 1


def maybe_send(state: dict) -> None:
    now = datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")
    if now.hour < REPORT_HOUR_UTC or state.get("last_heartbeat") == today:
        return

    available: list[str] = []
    unavailable: list[str] = []
    latest: list[str] = []
    for symbol in config.SYMBOLS:
        df = data_feed.get_rates(symbol, count=3)
        if df is None or df.empty:
            unavailable.append(symbol)
            continue
        available.append(symbol)
        latest.append(f"{symbol}: {df['close'].iloc[-1]:.5f}")

    status = "✅ Healthy" if not unavailable else "⚠️ Partial data failure"
    text = (
        f"💓 <b>Global Market Bot Heartbeat — {status}</b>\n"
        f"Timeframe: {config.TIMEFRAME} | Confirmation: {config.HIGHER_TIMEFRAME}\n"
        f"Symbols online: {len(available)}/{len(config.SYMBOLS)}\n"
        + (" | ".join(latest) if latest else "No market data available")
        + (f"\nUnavailable: {', '.join(unavailable)}" if unavailable else "")
        + "\n\n"
        + journal.summary(state)
    )
    if notifier.send_text(text):
        state["last_heartbeat"] = today
