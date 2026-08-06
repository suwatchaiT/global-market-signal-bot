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


def _minute_in_window(minute: int, start: int, end: int) -> bool:
    if start <= end:
        return start <= minute <= end
    return minute >= start or minute <= end


def in_alert_window() -> bool:
    utc = time.gmtime()
    local_minute = (((utc.tm_hour + config.TZ_OFFSET) % 24) * 60) + utc.tm_min
    daytime_start = config.ALERT_START_HOUR * 60 + config.ALERT_START_MINUTE
    daytime_end = config.ALERT_END_HOUR * 60 + config.ALERT_END_MINUTE
    evening_start = config.US_ALERT_START_HOUR * 60 + config.US_ALERT_START_MINUTE
    evening_end = config.US_ALERT_END_HOUR * 60 + config.US_ALERT_END_MINUTE
    return _minute_in_window(local_minute, daytime_start, daytime_end) or _minute_in_window(
        local_minute, evening_start, evening_end
    )


def main():
    state = load_state()
    now = time.time()
    sent = 0

    if not in_alert_window():
        log.info(
            "Outside alert windows (%02d:%02d-%02d:%02d and %02d:%02d-%02d:%02d local) "
            "— skipping signal checks.",
            config.ALERT_START_HOUR, config.ALERT_START_MINUTE,
            config.ALERT_END_HOUR, config.ALERT_END_MINUTE,
            config.US_ALERT_START_HOUR, config.US_ALERT_START_MINUTE,
            config.US_ALERT_END_HOUR, config.US_ALERT_END_MINUTE,
        )
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
