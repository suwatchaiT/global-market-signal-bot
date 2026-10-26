"""Send a manual Discord test signal with a live M15 chart."""
from __future__ import annotations

import sys

import data_feed
import notifier
from signals import Signal


def main() -> int:
    df = data_feed.get_rates("EURUSD", count=60, timeframe="M15")
    if df is None or df.empty:
        print("Unable to load EURUSD M15 data for the test chart.")
        return 1

    price = float(df["close"].iloc[-1])
    candle_time = str(df["time"].iloc[-1])
    signal = Signal(
        symbol="EURUSD",
        signal_type="MA_CROSS",
        direction="BUY",
        detail="Manual Discord delivery and chart test",
        price=price,
        candle_time=candle_time,
        trigger_price=price,
        trigger_time=candle_time,
        stars=3,
        sl=price - 0.005,
        tp=price + 0.010,
        rr=2.0,
        context=["Test only — not a trading recommendation"],
    )
    return 0 if notifier.send(signal) else 1


if __name__ == "__main__":
    sys.exit(main())
