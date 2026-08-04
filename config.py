import os
from dotenv import load_dotenv

load_dotenv()

# Telegram
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# Symbols to monitor
SYMBOLS = os.getenv(
    "SYMBOLS",
    "EURUSD,GBPUSD,USDJPY,AUDUSD,USDCHF,XAUUSD,BTCUSD,"
    "THAISET,US500,NAS100,NIKKEI225,SHANGHAI",
).split(",")

# Timeframe (M5, M15, M30, H1, H4, D1)
TIMEFRAME = os.getenv("TIMEFRAME", "H1")

# Indicator settings
MA_FAST = int(os.getenv("MA_FAST", "9"))
MA_SLOW = int(os.getenv("MA_SLOW", "21"))
RSI_PERIOD = int(os.getenv("RSI_PERIOD", "14"))
RSI_OVERBOUGHT = float(os.getenv("RSI_OVERBOUGHT", "70"))
RSI_OVERSOLD = float(os.getenv("RSI_OVERSOLD", "30"))
MACD_FAST = int(os.getenv("MACD_FAST", "12"))
MACD_SLOW = int(os.getenv("MACD_SLOW", "26"))
MACD_SIGNAL = int(os.getenv("MACD_SIGNAL", "9"))

# ATR-based SL/TP suggestion
ATR_PERIOD = int(os.getenv("ATR_PERIOD", "14"))
ATR_SL_MULT = float(os.getenv("ATR_SL_MULT", "1.5"))
ATR_TP_MULT = float(os.getenv("ATR_TP_MULT", "3.0"))

# Minimum confluence stars (1-3) required to send an alert
MIN_STARS = int(os.getenv("MIN_STARS", "1"))

# Alert window in local time (TZ_OFFSET hours from UTC). Alerts are only
# sent between ALERT_START_HOUR and ALERT_END_HOUR; /status and the daily
# report still work outside the window.
TZ_OFFSET = int(os.getenv("TZ_OFFSET", "7"))  # Thailand
ALERT_START_HOUR = int(os.getenv("ALERT_START_HOUR", "9"))
ALERT_END_HOUR = int(os.getenv("ALERT_END_HOUR", "17"))
# Additional window for US indices. This range wraps across midnight.
US_ALERT_START_HOUR = int(os.getenv("US_ALERT_START_HOUR", "20"))
US_ALERT_END_HOUR = int(os.getenv("US_ALERT_END_HOUR", "4"))

# How many recent bars to scan for trigger events. Covers gaps between
# scheduled runs (GitHub may delay cron by hours); cooldown dedupes repeats.
LOOKBACK_BARS = int(os.getenv("LOOKBACK_BARS", "6"))

# Signal-quality filters. Signals are calculated from closed candles only.
HIGHER_TIMEFRAME = os.getenv("HIGHER_TIMEFRAME", "H4")
REQUIRE_HTF_CONFIRMATION = os.getenv("REQUIRE_HTF_CONFIRMATION", "true").lower() in (
    "1", "true", "yes", "on"
)

# Risk-based position sizing. Estimates assume ACCOUNT_CURRENCY=USD and the
# standard contract sizes defined in risk.py; confirm the lot size with broker specs.
ACCOUNT_BALANCE = float(os.getenv("ACCOUNT_BALANCE", "10000"))
RISK_PERCENT = float(os.getenv("RISK_PERCENT", "1"))
ACCOUNT_CURRENCY = os.getenv("ACCOUNT_CURRENCY", "USD").upper()

# Poll interval in seconds
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "60"))
