from __future__ import annotations

import math
from datetime import datetime, timezone, timedelta

import requests

import config
from signals import Signal

_TH_TZ = timezone(timedelta(hours=config.TZ_OFFSET))
_DIRECTION_EMOJI = {"BUY": "🟢", "SELL": "🔴"}
_TYPE_LABEL = {
    "MA_CROSS": "MA Crossover",
    "RSI": "RSI Alert",
    "MACD_CROSS": "MACD Crossover",
}


def _to_th(ts: str) -> str:
    """Convert any timestamp string to Thailand time HH:MM DD/MM."""
    try:
        dt = datetime.fromisoformat(str(ts))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        dt_th = dt.astimezone(_TH_TZ)
        return dt_th.strftime("%H:%M %d/%m")
    except (ValueError, TypeError):
        return str(ts)


def _staleness(candle_time: str) -> str:
    """Human-readable age of the signal candle."""
    try:
        dt = datetime.fromisoformat(str(candle_time))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        minutes = (datetime.now(timezone.utc) - dt).total_seconds() / 60
        if minutes < 60:
            return f"{int(minutes)}m ago"
        hours = minutes / 60
        return f"{math.floor(hours)}h {int(minutes % 60)}m ago"
    except (ValueError, TypeError):
        return ""


def _format(signal: Signal) -> str:
    emoji = _DIRECTION_EMOJI.get(signal.direction, "⚪")
    labels = " + ".join(_TYPE_LABEL.get(t, t) for t in signal.signal_type.split("+"))
    stars = "⭐" * signal.stars
    strength = {1: "weak", 2: "moderate", 3: "strong"}.get(signal.stars, "")

    now_th = datetime.now(_TH_TZ).strftime("%H:%M %d/%m")
    lines = [
        f"{emoji} <b>{signal.symbol} {signal.direction}</b> — {labels}",
        f"{stars} {strength} signal  |  Sent: {now_th} TH",
        "",
        f"Trigger: {signal.detail}",
    ]

    if signal.price:
        price_line = f"Price: <b>{signal.price:.5f}</b>"
        if signal.candle_time:
            th_time = _to_th(signal.candle_time)
            age = _staleness(signal.candle_time)
            price_line += f" | Signal candle: {th_time} TH"
            if age:
                price_line += f" ({age})"
        lines.append(price_line)

    if signal.context:
        lines.append(" | ".join(signal.context))

    if signal.sl and signal.tp:
        lines.append("")
        lines.append(
            f"Suggested SL: {signal.sl:.5f} | TP: {signal.tp:.5f} | R:R {signal.rr:.1f}"
        )
    if signal.lot_size:
        lines.append(
            f"Estimated size: <b>{signal.lot_size:.3f} lots</b> "
            f"({signal.position_units:,.0f} units) | Risk: ${signal.risk_amount:,.2f}"
        )
        lines.append("⚠️ Estimate only — confirm contract size and price with your broker.")

    return "\n".join(lines)


def send(signal: Signal) -> bool:
    if not config.TELEGRAM_TOKEN or not config.TELEGRAM_CHAT_ID:
        return False
    url = f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": config.TELEGRAM_CHAT_ID,
        "text": _format(signal),
        "parse_mode": "HTML",
    }
    try:
        r = requests.post(url, json=payload, timeout=10)
        ok = r.status_code == 200
    except requests.RequestException:
        return False

    if ok:
        _send_chart(signal)
    return ok


def _send_chart(signal: Signal) -> None:
    try:
        import chart
        png = chart.render(signal)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("Chart render failed: %s", e)
        return
    if not png:
        return
    url = f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}/sendPhoto"
    caption = f"{signal.symbol} M15 — last 24h"
    if signal.candle_time:
        caption += f" | Signal: {_to_th(signal.candle_time)} TH"
    try:
        requests.post(
            url,
            data={"chat_id": config.TELEGRAM_CHAT_ID, "caption": caption},
            files={"photo": (f"{signal.symbol}_m15.png", png, "image/png")},
            timeout=30,
        )
    except requests.RequestException:
        pass


def send_text(text: str) -> bool:
    if not config.TELEGRAM_TOKEN or not config.TELEGRAM_CHAT_ID:
        return False
    url = f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": config.TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
    }
    try:
        r = requests.post(url, json=payload, timeout=10)
        return r.status_code == 200
    except requests.RequestException:
        return False
