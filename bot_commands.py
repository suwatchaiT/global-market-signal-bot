"""Handle incoming Telegram commands (processed once per scheduled run).

Supported: /status — replies with current price and indicator readings.
"""
from __future__ import annotations

import logging

import requests

import config
import data_feed
import notifier
import journal
from signals import _ema, _rsi

log = logging.getLogger(__name__)


def _build_status() -> str:
    lines = ["📊 <b>Signal Bot Status</b>", f"Timeframe: {config.TIMEFRAME}", ""]
    for symbol in config.SYMBOLS:
        df = data_feed.get_rates(symbol)
        if df is None or len(df) < 50:
            lines.append(f"⚠️ <b>{symbol}</b>: no data")
            continue
        close = df["close"]
        fast = _ema(close, config.MA_FAST).iloc[-1]
        slow = _ema(close, config.MA_SLOW).iloc[-1]
        rsi = _rsi(close, config.RSI_PERIOD).iloc[-1]
        trend = "🟢 bullish" if fast > slow else "🔴 bearish"
        lines.append(
            f"<b>{symbol}</b>: {close.iloc[-1]:.5f}\n"
            f"  EMA{config.MA_FAST}/{config.MA_SLOW}: {trend}  |  RSI: {rsi:.1f}"
        )
    return "\n".join(lines)


def handle_commands(state: dict) -> None:
    """Poll pending Telegram messages and answer /status commands."""
    if not config.TELEGRAM_TOKEN:
        return
    offset = int(state.get("last_update_id", 0)) + 1
    url = f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}/getUpdates"
    try:
        r = requests.get(url, params={"offset": offset, "timeout": 0}, timeout=15)
        updates = r.json().get("result", [])
    except (requests.RequestException, ValueError) as e:
        log.warning("getUpdates failed: %s", e)
        return

    status_requested = False
    performance_limit: int | None = None
    for u in updates:
        state["last_update_id"] = u["update_id"]
        msg = u.get("message") or {}
        text = (msg.get("text") or "").strip().lower()
        # Only respond to the configured chat
        if str(msg.get("chat", {}).get("id")) != str(config.TELEGRAM_CHAT_ID):
            continue
        if text.startswith("/status") or text.startswith("/start"):
            status_requested = True
        elif text.startswith("/performance"):
            parts = text.split()
            try:
                performance_limit = int(parts[1]) if len(parts) > 1 else 15
            except ValueError:
                performance_limit = 15

    if status_requested:
        log.info("Status requested — sending report.")
        if not notifier.send_text(_build_status()):
            log.warning("Status report delivery failed.")

    if performance_limit is not None:
        performance_limit = max(1, min(performance_limit, 20))
        log.info("Performance requested — sending summary and %d recent rows.",
                 performance_limit)
        summary_ok = notifier.send_text(journal.summary(state))
        table_ok = notifier.send_text(journal.performance_table(state, performance_limit))
        if summary_ok and table_ok:
            log.info("Performance summary and table delivered successfully.")
        else:
            log.warning("Performance delivery failed (summary=%s, table=%s).",
                        summary_ok, table_ok)
