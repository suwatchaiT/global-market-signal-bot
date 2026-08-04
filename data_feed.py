from __future__ import annotations

import logging
from datetime import datetime, timezone
import pandas as pd
import yfinance as yf
import config

log = logging.getLogger(__name__)

# Map MT5-style symbols to Yahoo Finance tickers
_SYMBOL_MAP = {
    "EURUSD": "EURUSD=X",
    "GBPUSD": "GBPUSD=X",
    "USDJPY": "USDJPY=X",
    "AUDUSD": "AUDUSD=X",
    "USDCAD": "USDCAD=X",
    "USDCHF": "USDCHF=X",
    "NZDUSD": "NZDUSD=X",
    "XAUUSD": "GC=F",   # gold futures
    "XAGUSD": "SI=F",   # silver futures
    "BTCUSD": "BTC-USD",
    "ETHUSD": "ETH-USD",
}

# Map MT5-style timeframes to yfinance (interval, period) pairs.
# Period is sized to return ~200 bars for the indicators.
_TIMEFRAME_MAP = {
    "M5": ("5m", "5d"),
    "M15": ("15m", "10d"),
    "M30": ("30m", "20d"),
    "H1": ("1h", "40d"),
    # Yahoo has no native 4h interval; download 1h and resample below.
    "H4": ("1h", "150d"),
    "D1": ("1d", "1y"),
}


def yahoo_ticker(symbol: str) -> str:
    return _SYMBOL_MAP.get(symbol.upper(), symbol)


_CANDLE_MINUTES = {"M5": 5, "M15": 15, "M30": 30, "H1": 60, "H4": 240, "D1": 1440}


def _closed_only(df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    """Remove a currently-forming final candle."""
    if df.empty or "time" not in df.columns:
        return df
    last_open = pd.Timestamp(df["time"].iloc[-1])
    if last_open.tzinfo is None:
        last_open = last_open.tz_localize("UTC")
    close_at = last_open + pd.Timedelta(minutes=_CANDLE_MINUTES.get(timeframe, 60))
    now = pd.Timestamp(datetime.now(timezone.utc))
    return df.iloc[:-1] if now < close_at else df


def _resample_h4(df: pd.DataFrame) -> pd.DataFrame:
    indexed = df.set_index(pd.to_datetime(df["time"], utc=True))
    out = indexed.resample("4h").agg({
        "open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"
    }).dropna(subset=["open", "high", "low", "close"])
    out["time"] = out.index
    return out.reset_index(drop=True)


def get_rates(symbol: str, count: int = 200, timeframe: str | None = None) -> pd.DataFrame | None:
    selected_timeframe = (timeframe or config.TIMEFRAME).upper()
    interval, period = _TIMEFRAME_MAP.get(selected_timeframe, ("1h", "40d"))
    try:
        df = yf.download(
            yahoo_ticker(symbol),
            interval=interval,
            period=period,
            progress=False,
            auto_adjust=True,
        )
    except Exception as e:
        log.warning("Data fetch failed for %s: %s", symbol, e)
        return None

    if df is None or df.empty:
        return None

    # yfinance may return MultiIndex columns when fetching a single ticker
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df.reset_index().rename(columns=str.lower)
    df = df.rename(columns={"datetime": "time", "date": "time"})
    df = df.dropna(subset=["close"])
    if selected_timeframe == "H4":
        df = _resample_h4(df)
    df = _closed_only(df, selected_timeframe)
    return df.tail(count).reset_index(drop=True)
