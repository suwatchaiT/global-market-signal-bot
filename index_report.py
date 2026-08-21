"""Send stock-index price reports near each exchange's open and close."""
from __future__ import annotations

from datetime import date, datetime, time, timezone
import logging
from zoneinfo import ZoneInfo

import pandas as pd

import config
import data_feed
import notifier

log = logging.getLogger(__name__)

# symbol: (exchange timezone, regular-session open, regular-session close)
SESSIONS = {
    "THAISET": ("Asia/Bangkok", time(10, 0), time(16, 40)),
    "NIKKEI225": ("Asia/Tokyo", time(9, 0), time(15, 30)),
    "SHANGHAI": ("Asia/Shanghai", time(9, 30), time(15, 0)),
    "US500": ("America/New_York", time(9, 30), time(16, 0)),
    "NAS100": ("America/New_York", time(9, 30), time(16, 0)),
    "DOW30": ("America/New_York", time(9, 30), time(16, 0)),
    "FTSE100": ("Europe/London", time(8, 0), time(16, 30)),
    "DAX40": ("Europe/Berlin", time(9, 0), time(17, 30)),
    "HANGSENG": ("Asia/Hong_Kong", time(9, 30), time(16, 0)),
    "ASX200": ("Australia/Sydney", time(10, 0), time(16, 0)),
}
INDEX_SYMBOLS = frozenset(SESSIONS)
_EVENT_WINDOW_MINUTES = 75


def is_index(symbol: str) -> bool:
    return symbol.upper() in INDEX_SYMBOLS


def _minutes_after(now: datetime, target: time) -> int:
    return now.hour * 60 + now.minute - (target.hour * 60 + target.minute)


def due_event(now: datetime, opened: time, closed: time) -> str | None:
    """Return OPEN/CLOSE during the post-event delivery window."""
    if now.weekday() >= 5:
        return None
    for name, target in (("OPEN", opened), ("CLOSE", closed)):
        delta = _minutes_after(now, target)
        if 0 <= delta <= _EVENT_WINDOW_MINUTES:
            return name
    return None


def _session_stats(
    df: pd.DataFrame, zone_name: str, session_date: date
) -> tuple[float, float, float] | None:
    """Return session open, latest price, and previous-session close."""
    if df is None or df.empty or not {"time", "open", "close"} <= set(df.columns):
        return None
    local_times = pd.to_datetime(df["time"], utc=True).dt.tz_convert(ZoneInfo(zone_name))
    dates = local_times.dt.date
    today = df[dates == session_date]
    previous_dates = sorted({value for value in dates if value < session_date})
    if today.empty or not previous_dates:
        return None
    previous = df[dates == previous_dates[-1]]
    return (
        float(today["open"].iloc[0]),
        float(today["close"].iloc[-1]),
        float(previous["close"].iloc[-1]),
    )


def _price(value: float) -> str:
    return f"{value:,.2f}"


def maybe_send(state: dict, now_utc: datetime | None = None) -> None:
    """Send each index's open/close report once per exchange-local date."""
    now_utc = now_utc or datetime.now(timezone.utc)
    reports: dict[str, list[str]] = {"OPEN": [], "CLOSE": []}
    pending_keys: dict[str, list[str]] = {"OPEN": [], "CLOSE": []}

    for symbol in config.SYMBOLS:
        session = SESSIONS.get(symbol.upper())
        if not session:
            continue
        zone_name, opened, closed = session
        local_now = now_utc.astimezone(ZoneInfo(zone_name))
        event = due_event(local_now, opened, closed)
        if not event:
            continue
        key = f"index_report|{symbol.upper()}|{event}|{local_now.date().isoformat()}"
        if state.get(key):
            continue

        df = data_feed.get_rates(symbol, count=500, timeframe="M5")
        stats = _session_stats(df, zone_name, local_now.date())
        if not stats:
            log.info("Index %s %s report waiting for session data.", symbol, event)
            continue
        open_price, current_price, previous_close = stats
        report_price = open_price if event == "OPEN" else current_price
        change = ((report_price - previous_close) / previous_close) * 100
        marker = "🟢" if change >= 0 else "🔴"
        price_label = "Open" if event == "OPEN" else "Close"
        reports[event].append(
            f"{marker} <b>{symbol.upper()}</b>: {price_label} {_price(report_price)} "
            f"| Prev close {_price(previous_close)} | {change:+.2f}%"
        )
        pending_keys[event].append(key)

    labels = {
        "OPEN": "🔔 <b>Stock Index Market Open</b>",
        "CLOSE": "🏁 <b>Stock Index Market Close</b>",
    }
    for event in ("OPEN", "CLOSE"):
        if not reports[event]:
            continue
        text = labels[event] + "\n" + "\n".join(reports[event])
        if notifier.send_text(text):
            for key in pending_keys[event]:
                state[key] = True
