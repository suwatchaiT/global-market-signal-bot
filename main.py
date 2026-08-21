import time
import logging
import config
import data_feed
import signals as sig_detector
import notifier
import index_report

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("bot.log"),
    ],
)
log = logging.getLogger(__name__)

# Track last signal per (symbol, type, direction) to avoid duplicate alerts
_last_signals: dict[tuple, float] = {}
COOLDOWN_SECONDS = 3600  # minimum gap between identical alerts


def should_send(signal: sig_detector.Signal) -> bool:
    key = (signal.symbol, signal.signal_type, signal.direction)
    last = _last_signals.get(key, 0)
    if time.time() - last >= COOLDOWN_SECONDS:
        _last_signals[key] = time.time()
        return True
    return False


def run():
    log.info("Monitoring: %s on %s", config.SYMBOLS, config.TIMEFRAME)
    notifier.send_text(
        f"🤖 <b>Global Market Signal Bot started</b>\n"
        f"Symbols: {', '.join(config.SYMBOLS)}\n"
        f"Timeframe: {config.TIMEFRAME}"
    )

    report_state: dict = {}

    try:
        while True:
            index_report.maybe_send(report_state)
            for symbol in config.SYMBOLS:
                if index_report.is_index(symbol):
                    continue
                df = data_feed.get_rates(symbol)
                if df is None or len(df) < 50:
                    log.warning("Not enough data for %s, skipping.", symbol)
                    continue

                higher_df = data_feed.get_rates(symbol, timeframe=config.HIGHER_TIMEFRAME)
                found = sig_detector.detect(symbol, df, higher_df)
                for s in found:
                    if should_send(s):
                        log.info("Signal: %s %s %s — %s", s.symbol, s.signal_type, s.direction, s.detail)
                        ok = notifier.send(s)
                        if not ok:
                            log.warning("Telegram send failed for %s", s.symbol)

            time.sleep(config.POLL_INTERVAL)

    except KeyboardInterrupt:
        log.info("Bot stopped by user.")
        notifier.send_text("🛑 Global Market Signal Bot stopped.")


if __name__ == "__main__":
    run()
