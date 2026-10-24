# Global Market Signal Bot — Trigger Specification

This document describes the implemented strategy in a model-independent form so another AI or developer can reproduce it. The current strategy version is `v4-mtf-trigger-accuracy`.

## 1. Purpose and scope

Generate informational BUY/SELL alerts for forex, gold, and Bitcoin from closed Yahoo Finance candles. Stock indices are excluded from technical trade signals; they receive separate market-open and market-close price-change reports.

Default technical-signal symbols:

```text
EURUSD, GBPUSD, USDJPY, AUDUSD, USDCHF, XAUUSD, BTCUSD
```

Default index-report symbols:

```text
THAISET, US500, NAS100, DOW30, FTSE100, DAX40,
NIKKEI225, SHANGHAI, HANGSENG, ASX200
```

## 2. Default parameters

| Setting | Default |
|---|---:|
| Primary trigger timeframe | H1 |
| Trigger lookback | 6 closed H1 candles |
| EMA fast / slow | 9 / 21 |
| RSI period | 14 |
| RSI oversold / overbought | 30 / 70 |
| MACD fast / slow / signal | 12 / 26 / 9 |
| Higher timeframe | H4 |
| Require H4 agreement | Yes |
| Require current H1 MACD agreement | Yes |
| Confirmation timeframes | M1, M5, M15, M30, H1 |
| Required timeframe votes | 4 of 5 |
| Minimum confluence | 2 of 3 indicators |
| ATR period | 14 |
| Stop distance | 1.5 × ATR |
| Target distance | 3.0 × ATR |
| Nominal reward:risk | 2.0 |

Only completed candles are used. A currently forming final candle must be discarded.

## 3. Indicator calculations

For close-price series `C`:

```text
EMA_fast = EMA(C, 9)
EMA_slow = EMA(C, 21)

gain = max(C[t] - C[t-1], 0)
loss = max(C[t-1] - C[t], 0)
RS = SMA(gain, 14) / SMA(loss, 14)
RSI = 100 - 100 / (1 + RS)

MACD_line = EMA(C, 12) - EMA(C, 26)
MACD_signal = EMA(MACD_line, 9)
```

ATR uses the 14-period simple mean of true range:

```text
TR = max(high-low, abs(high-previous_close), abs(low-previous_close))
ATR = SMA(TR, 14)
```

## 4. H1 trigger events

Scan each of the latest six closed H1 candles and its preceding candle.

### BUY trigger

At least one of these events must occur:

1. `EMA9` crosses above `EMA21`.
2. RSI exits oversold: previous RSI `<= 30` and current RSI `> 30`.
3. MACD line crosses above its signal line.

### SELL trigger

At least one of these events must occur:

1. `EMA9` crosses below `EMA21`.
2. RSI exits overbought: previous RSI `>= 70` and current RSI `< 70`.
3. MACD line crosses below its signal line.

Entering an RSI extreme is not a trigger. The trigger occurs only when RSI exits the extreme zone.

Keep only the most recent event for each `(indicator, direction)`. For a direction, select its most recent trigger candle and combine only indicators that triggered on that exact candle. Never combine events from different candles.

Store both:

- `trigger_time` and `trigger_price`: the exact H1 candle that generated the event.
- `opened_at` and `entry`: the latest closed H1 candle and close price when the alert is evaluated.

## 5. Current H1 confluence

On the latest closed H1 candle, classify three indicator states:

```text
EMA state  = BUY if EMA9 > EMA21, otherwise SELL
RSI state  = BUY if RSI < 50, otherwise SELL
MACD state = BUY if MACD_line > MACD_signal, otherwise SELL
```

The RSI rule above is intentional: below 50 is treated as room to move upward, while 50 or above is treated as room to move downward.

The confluence score (`stars`) is the number of these three states matching the candidate direction. Reject candidates with fewer than 2 stars.

When MACD confirmation is enabled, the current H1 MACD state must also match the candidate direction.

## 6. H4 trend gate

Calculate `EMA9` and `EMA21` on the latest closed H4 candle:

```text
H4 state = BUY if H4 EMA9 > H4 EMA21, otherwise SELL
```

Reject the candidate if H4 data is unavailable or the H4 state does not match the candidate direction.

## 7. Multi-timeframe confirmation

Only after an H1 candidate survives the preceding checks, load closed candles for M1, M5, M15, M30, and H1.

Each timeframe casts one vote. Within one timeframe, calculate these three states using its latest closed candle:

```text
EMA state  = BUY if EMA9 > EMA21, otherwise SELL
RSI state  = BUY if RSI < 50, otherwise SELL
MACD state = BUY if MACD_line > MACD_signal, otherwise SELL
```

The timeframe votes for the candidate when at least two of its three indicator states match the candidate direction. Missing or insufficient data is a failed vote.

Send the signal only when at least four of the five timeframes vote for it.

> GitHub Actions runs approximately every 15 minutes. M1 is therefore sampled at execution time; it is not continuously monitored every minute.

## 8. Stops, targets, and size estimate

Use the latest closed H1 price as entry snapshot `P` and H1 ATR:

```text
BUY:  SL = P - 1.5 × ATR; TP = P + 3.0 × ATR
SELL: SL = P + 1.5 × ATR; TP = P - 3.0 × ATR
```

The nominal reward:risk ratio is `3.0 / 1.5 = 2.0`.

Position size uses the configured account balance and risk percentage. It is an estimate only and must be checked against broker contract sizes, currency conversion, spread, and execution price.

## 9. Alert timing and duplicate prevention

Technical signals are evaluated only during these Thailand-time windows:

```text
08:30–17:00
20:00–23:00
```

GitHub Actions normally runs every 15 minutes during those windows.

Two duplicate protections apply:

1. Journal identity: `symbol | direction | trigger_time`. The same trigger candle cannot be recorded twice.
2. Cooldown identity: `symbol | signal_type | direction`. The default cooldown is `6 hours` (`LOOKBACK_BARS × 1 hour`).

Record a signal only after notification delivery succeeds.

## 10. Performance scoring

Journal records are tagged with `strategy_version`. Performance for the current strategy must not be mixed with legacy versions. Stock indices are excluded.

For each open signal, examine later closed H1 candles:

- BUY wins when candle high reaches TP; loses when candle low reaches SL.
- SELL wins when candle low reaches TP; loses when candle high reaches SL.
- If one candle touches both SL and TP, score a LOSS because OHLC data cannot reveal which was touched first.
- WIN result: `+2.0R` by default.
- LOSS result: `-1.0R`.

These are candle-touch estimates, not broker fills.

## 11. Stock-index open/close reports

Indices do not generate BUY/SELL technical signals. Near each exchange's regular-session open and close, calculate:

```text
change_percent = (reported_price - previous_session_close)
                 / previous_session_close × 100
```

Use the session open for an OPEN report and the latest session price for a CLOSE report. Deliver each `(symbol, event, local exchange date)` only once. The post-event delivery window is 75 minutes.

## 12. Reference decision flow

```text
for each non-index symbol:
    load closed H1 candles
    evaluate existing open journal records
    load closed H4 candles

    scan last 6 H1 candles for EMA, RSI-exit, or MACD crosses
    keep most recent event per indicator and direction

    for BUY and SELL candidates:
        use only triggers occurring on candidate's latest trigger candle
        require matching H4 EMA trend
        require matching current H1 MACD state
        require at least 2/3 current H1 indicator states

        load M1, M5, M15, M30 (reuse H1)
        require at least 4/5 timeframe votes

        calculate ATR stop, target, and size estimate
        reject duplicate trigger or active cooldown
        send notification
        if delivery succeeds, record versioned signal
```

## 13. Portable implementation prompt

The following can be given to another AI model:

```text
Implement a closed-candle market alert engine exactly as defined in
STRATEGY_TRIGGER_SPEC.md. Keep data retrieval, indicator calculation, trigger
detection, confirmation, notification, state persistence, and performance
scoring as separate modules. Do not use future candles or forming candles.
Preserve exact trigger candle time/price separately from evaluation entry
time/price. Do not combine indicator triggers from different candles. Treat
missing confirmation data as a failed vote. Make every default configurable
through environment variables. Add deterministic unit tests for BUY and SELL
crosses, RSI exits, same-candle grouping, H4 rejection, 4-of-5 confirmation,
duplicate prevention, and conservative same-candle SL/TP scoring.
```

## 14. Limitations

- This specification describes an alert strategy, not guaranteed profitability.
- Yahoo Finance intraday data may be delayed or unavailable.
- Scheduled execution can miss short-lived intrabar conditions.
- M1 confirmation is sampled only when the workflow runs.
- Candle-touch performance ignores spread, slippage, commissions, gaps, and order execution.
- Strategy changes require a new `strategy_version` before comparing future results.
