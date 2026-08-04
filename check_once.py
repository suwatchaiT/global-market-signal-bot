"""Single-pass signal check for scheduled runners (GitHub Actions).

Unlike main.py, this checks every symbol once and exits. Alert cooldown
state is persisted to state.json so repeated runs don't duplicate alerts.
"""
import json
import logging
import time
from pathlib import Path

import bot_commands
import config
import data_feed
import notifier
import signals as sig_detector
import usage_report
import health_report
import journal

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

STATE_FILE = Path("state.json")
# Must cover the LOOKBACK_BARS scan window, or a trigger already alerted
# on an old bar would re-alert on the next run.
COOLDOWN_SECONDS = config.LOOKBACK_BARS * 3600


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except json.JSONDecodeError:
            pass
    return {}


def _hour_in_window(hour: int, start: int, end: int) -> bool:
    if start <= end:
        return start <= hour <= end
    return hour >= start or hour <= end


def in_alert_window() -> bool:
    local_hour = (time.gmtime().tm_hour + config.TZ_OFFSET) % 24
    return _hour_in_window(
        local_hour, config.ALERT_START_HOUR, config.ALERT_END_HOUR
    ) or _hour_in_window(
        local_hour, config.US_ALERT_START_HOUR, config.US_ALERT_END_HOUR
    )


def main():
    state = load_state()
    now = time.time()
    sent = 0

    if not in_alert_window():
        log.info("Outside alert window (%d:00-%d:00 local) — skipping signal checks.",
                 config.ALERT_START_HOUR, config.ALERT_END_HOUR)
        bot_commands.handle_commands(state)
        health_report.maybe_send(state)
        usage_report.maybe_send_daily_report(state)
        STATE_FILE.write_text(json.dumps(state))
        return

    for symbol in config.SYMBOLS:
        df = data_feed.get_rates(symbol)
        if df is None or len(df) < 50:
            log.warning("Not enough data for %s, skipping.", symbol)
            continue

        journal.evaluate(state, symbol, df)
        higher_df = data_feed.get_rates(symbol, timeframe=config.HIGHER_TIMEFRAME)
        if config.REQUIRE_HTF_CONFIRMATION and (higher_df is None or len(higher_df) < 50):
            log.warning("Not enough %s confirmation data for %s, skipping.",
                        config.HIGHER_TIMEFRAME, symbol)
            continue

        for s in sig_detector.detect(symbol, df, higher_df):
            key = f"{s.symbol}|{s.signal_type}|{s.direction}"
            if now - state.get(key, 0) < COOLDOWN_SECONDS:
                log.info("Cooldown active, skipping: %s", key)
                continue
            log.info("Signal: %s — %s", key, s.detail)
            if notifier.send(s):
                state[key] = now
                journal.record(state, s)
                sent += 1
            else:
                log.warning("Telegram send failed for %s", key)

    bot_commands.handle_commands(state)
    health_report.maybe_send(state)
    usage_report.maybe_send_daily_report(state)

    STATE_FILE.write_text(json.dumps(state))
    log.info("Check complete. Alerts sent: %d", sent)


if __name__ == "__main__":
    main()
