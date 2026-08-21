from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

import config
import risk


@dataclass
class Signal:
    symbol: str
    signal_type: str        # comma-joined triggers, e.g. "MA_CROSS+RSI"
    direction: str          # "BUY" or "SELL"
    detail: str             # trigger descriptions
    price: float = 0.0
    candle_time: str = ""
    stars: int = 1          # confluence score 1-3
    sl: float = 0.0
    tp: float = 0.0
    rr: float = 0.0
    context: list[str] = field(default_factory=list)  # indicator readings
    risk_amount: float = 0.0
    position_units: float = 0.0
    lot_size: float = 0.0


def _ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def _rsi(close: pd.Series, period: int) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, float("nan"))
    return 100 - (100 / (1 + rs))


def _macd_confirms(direction: str, macd_state: str) -> bool:
    return not config.REQUIRE_MACD_CONFIRMATION or macd_state == direction


def _atr(df: pd.DataFrame, period: int) -> float:
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    return float(tr.rolling(period).mean().iloc[-1])


def detect(symbol: str, df: pd.DataFrame, higher_df: pd.DataFrame | None = None) -> list[Signal]:
    close = df["close"]
    price = float(close.iloc[-1])

    fast = _ema(close, config.MA_FAST)
    slow = _ema(close, config.MA_SLOW)
    rsi = _rsi(close, config.RSI_PERIOD)
    macd_line = _ema(close, config.MACD_FAST) - _ema(close, config.MACD_SLOW)
    signal_line = _ema(macd_line, config.MACD_SIGNAL)

    curr_rsi = float(rsi.iloc[-1])

    # --- Trigger events: scan the last LOOKBACK_BARS candles, not just the
    # newest one, because scheduled runs may be hours apart and signals on
    # intermediate bars would otherwise be missed. Cooldown dedupes repeats.
    triggers: list[tuple[str, str, str]] = []  # (name, direction, description)

    def bar_label(i: int) -> str:
        if "time" in df.columns and i != -1:
            return f" (candle {df['time'].iloc[i]})"
        return ""

    for i in range(-config.LOOKBACK_BARS, 0):
        p, c = i - 1, i  # previous and current bar of this step

        if fast.iloc[p] < slow.iloc[p] and fast.iloc[c] > slow.iloc[c]:
            triggers.append(("MA_CROSS", "BUY",
                f"EMA{config.MA_FAST} crossed above EMA{config.MA_SLOW}{bar_label(c)}"))
        elif fast.iloc[p] > slow.iloc[p] and fast.iloc[c] < slow.iloc[c]:
            triggers.append(("MA_CROSS", "SELL",
                f"EMA{config.MA_FAST} crossed below EMA{config.MA_SLOW}{bar_label(c)}"))

        r_p, r_c = float(rsi.iloc[p]), float(rsi.iloc[c])
        if r_p <= config.RSI_OVERSOLD and r_c > config.RSI_OVERSOLD:
            triggers.append(("RSI", "BUY", f"RSI exited oversold zone ({r_c:.1f}){bar_label(c)}"))
        elif r_p >= config.RSI_OVERBOUGHT and r_c < config.RSI_OVERBOUGHT:
            triggers.append(("RSI", "SELL", f"RSI exited overbought zone ({r_c:.1f}){bar_label(c)}"))
        # Entering an extreme is not a reversal confirmation. Wait for RSI to
        # leave the zone instead of buying overbought or selling oversold.

        if macd_line.iloc[p] < signal_line.iloc[p] and macd_line.iloc[c] > signal_line.iloc[c]:
            triggers.append(("MACD_CROSS", "BUY", f"MACD crossed above signal line{bar_label(c)}"))
        elif macd_line.iloc[p] > signal_line.iloc[p] and macd_line.iloc[c] < signal_line.iloc[c]:
            triggers.append(("MACD_CROSS", "SELL", f"MACD crossed below signal line{bar_label(c)}"))

    # Keep only the most recent trigger per (indicator, direction)
    seen: dict[tuple[str, str], tuple[str, str, str]] = {}
    for t in triggers:
        seen[(t[0], t[1])] = t
    triggers = list(seen.values())

    if not triggers:
        return []

    # --- Current state of each indicator, used for confluence + context ---
    ma_state = "BUY" if fast.iloc[-1] > slow.iloc[-1] else "SELL"
    rsi_state = "BUY" if curr_rsi < 50 else "SELL"  # room to move up/down
    macd_state = "BUY" if macd_line.iloc[-1] > signal_line.iloc[-1] else "SELL"

    htf_state = ""
    if higher_df is not None and len(higher_df) >= config.MA_SLOW:
        higher_close = higher_df["close"]
        higher_fast = _ema(higher_close, config.MA_FAST).iloc[-1]
        higher_slow = _ema(higher_close, config.MA_SLOW).iloc[-1]
        htf_state = "BUY" if higher_fast > higher_slow else "SELL"
    if config.REQUIRE_HTF_CONFIRMATION and not htf_state:
        return []

    context = [
        f"EMA{config.MA_FAST}/{config.MA_SLOW}: {'bullish' if ma_state == 'BUY' else 'bearish'}",
        f"RSI: {curr_rsi:.1f}",
        f"MACD: {'above' if macd_state == 'BUY' else 'below'} signal line",
    ]
    if htf_state:
        context.append(
            f"{config.HIGHER_TIMEFRAME} trend: {'bullish' if htf_state == 'BUY' else 'bearish'}"
        )

    atr = _atr(df, config.ATR_PERIOD)
    candle_time = str(df["time"].iloc[-1]) if "time" in df.columns else ""

    # --- One combined signal per direction that has at least one trigger ---
    signals: list[Signal] = []
    for direction in ("BUY", "SELL"):
        fired = [t for t in triggers if t[1] == direction]
        if not fired:
            continue
        if config.REQUIRE_HTF_CONFIRMATION and htf_state and htf_state != direction:
            continue
        if not _macd_confirms(direction, macd_state):
            continue

        # Confluence: how many of the three indicators currently agree
        stars = sum(1 for s in (ma_state, rsi_state, macd_state) if s == direction)
        stars = max(stars, 1)

        if direction == "BUY":
            sl = price - config.ATR_SL_MULT * atr
            tp = price + config.ATR_TP_MULT * atr
        else:
            sl = price + config.ATR_SL_MULT * atr
            tp = price - config.ATR_TP_MULT * atr
        rr = config.ATR_TP_MULT / config.ATR_SL_MULT
        risk_amount, position_units, lot_size = risk.estimate(symbol, price, sl)

        signals.append(Signal(
            symbol=symbol,
            signal_type="+".join(sorted(t[0] for t in fired)),
            direction=direction,
            detail="; ".join(t[2] for t in fired),
            price=price,
            candle_time=candle_time,
            stars=stars,
            sl=sl,
            tp=tp,
            rr=rr,
            context=context,
            risk_amount=risk_amount,
            position_units=position_units,
            lot_size=lot_size,
        ))

    return [s for s in signals if s.stars >= config.MIN_STARS]
