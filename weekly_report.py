"""Send the previous Thailand-time week's versioned signal performance."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, time, timedelta, timezone

import config
import journal
import notifier

_TH_TZ = timezone(timedelta(hours=config.TZ_OFFSET))
_REPORT_TIME = time(8, 30)


def _previous_week(now: datetime) -> tuple[datetime, datetime]:
    local = now.astimezone(_TH_TZ)
    this_monday = (local - timedelta(days=local.weekday())).date()
    end = datetime.combine(this_monday, time.min, tzinfo=_TH_TZ)
    return end - timedelta(days=7), end


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(_TH_TZ)


def _session(row: dict) -> str:
    opened = _parse_time(row.get("opened_at"))
    if opened is None:
        return "Unknown"
    minute = opened.hour * 60 + opened.minute
    if 8 * 60 + 30 <= minute <= 17 * 60:
        return "Day 08:30–17:00"
    if 20 * 60 <= minute <= 23 * 60:
        return "Evening 20:00–23:00"
    return "Other"


def _stats(rows: list[dict]) -> str:
    wins = sum(row.get("status") == "WIN" for row in rows)
    losses = sum(row.get("status") == "LOSS" for row in rows)
    total = wins + losses
    rate = wins / total * 100 if total else 0.0
    net_r = sum(float(row.get("r_multiple", 0.0)) for row in rows)
    return f"{wins}W/{losses}L | {rate:.1f}% | {net_r:+.1f}R"


def _groups(rows: list[dict], key) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        grouped[str(key(row))].append(row)
    return dict(grouped)


def build_report(state: dict, now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    start, end = _previous_week(now)
    rows = []
    for row in journal.analysis_records(state):
        closed = _parse_time(row.get("closed_at"))
        if row.get("status") in ("WIN", "LOSS") and closed and start <= closed < end:
            rows.append(row)

    lines = [
        "📊 <b>Weekly Technical Signal Performance</b>",
        f"{start:%d %b}–{(end - timedelta(days=1)):%d %b %Y} (Thailand)",
        f"Strategy: <b>{config.STRATEGY_VERSION}</b>",
        f"Overall: <b>{_stats(rows)}</b>",
    ]
    if not rows:
        lines.append("\nNo signals closed during this week.")
        return "\n".join(lines)

    sections = (
        ("By symbol", _groups(rows, lambda row: row.get("symbol", "Unknown"))),
        ("BUY vs SELL", _groups(rows, lambda row: row.get("direction", "Unknown"))),
        ("By trigger", _groups(rows, lambda row: row.get("signal_type", "Unknown"))),
        ("By session", _groups(rows, _session)),
    )
    for title, groups in sections:
        lines.append(f"\n<b>{title}</b>")
        for name in sorted(groups):
            lines.append(f"• {name}: {_stats(groups[name])}")
    lines.append("\nClosed-candle SL/TP touches; not broker fills.")
    return "\n".join(lines)


def maybe_send(state: dict, now: datetime | None = None) -> None:
    now = now or datetime.now(timezone.utc)
    local = now.astimezone(_TH_TZ)
    if local.weekday() != 0 or local.time() < _REPORT_TIME:
        return
    start, end = _previous_week(now)
    report_key = f"{start.date()}|{end.date()}|{config.STRATEGY_VERSION}"
    if state.get("last_weekly_performance") == report_key:
        return
    if notifier.send_text(build_report(state, now)):
        state["last_weekly_performance"] = report_key
