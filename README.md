# Signal Bot

Monitors forex / gold / crypto prices for technical indicator signals and sends Telegram alerts. Cross-platform (macOS, Linux, Windows) — uses Yahoo Finance data, no MT5 terminal or broker account needed.

**Signals detected**
- EMA crossover (fast/slow configurable)
- RSI overbought / oversold zones
- MACD signal-line crossover
- Closed-candle evaluation with higher-timeframe trend confirmation
- ATR stop/target and risk-based position-size estimates
- Signal journal with `/performance` win-rate and R-multiple summary
- Daily Telegram health heartbeat

## Setup

Requires Python 3.9+.

```bash
pip install -r requirements.txt
cp .env.example .env
# edit .env with your Telegram credentials
python main.py
```

## Configuration

All settings live in `.env` — see `.env.example` for every option.

| Variable | Default | Description |
|---|---|---|
| `TELEGRAM_TOKEN` | — | BotFather token |
| `TELEGRAM_CHAT_ID` | — | Your chat or channel ID |
| `SYMBOLS` | `EURUSD,GBPUSD,USDJPY,AUDUSD,USDCHF,XAUUSD,BTCUSD` | Comma-separated symbols |
| `TIMEFRAME` | `H1` | M5 M15 M30 H1 H4 D1 |
| `MA_FAST` / `MA_SLOW` | `9` / `21` | EMA periods |
| `RSI_PERIOD` | `14` | RSI lookback |
| `RSI_OVERBOUGHT` / `RSI_OVERSOLD` | `70` / `30` | RSI thresholds |
| `MACD_FAST` / `MACD_SLOW` / `MACD_SIGNAL` | `12` / `26` / `9` | MACD periods |
| `POLL_INTERVAL` | `60` | Seconds between checks |
| `HIGHER_TIMEFRAME` | `H4` | Trend-confirmation timeframe |
| `REQUIRE_HTF_CONFIRMATION` | `true` | Reject signals against the higher-timeframe EMA trend |
| `ACCOUNT_BALANCE` | `10000` | Balance used only for position-size estimates |
| `RISK_PERCENT` | `1` | Estimated account risk per signal |

Supported symbols: EURUSD, GBPUSD, USDJPY, AUDUSD, USDCAD, USDCHF, NZDUSD, XAUUSD (gold), XAGUSD (silver), BTCUSD, ETHUSD. Other Yahoo Finance tickers can be used directly (e.g. `AAPL`, `^GSPC`).

## Telegram setup

1. Message [@BotFather](https://t.me/BotFather) → `/newbot`
2. Copy the token to `TELEGRAM_TOKEN`
3. Message your bot, then open `https://api.telegram.org/bot<TOKEN>/getUpdates` to find your `chat_id`

For GitHub Actions, add `TELEGRAM_TOKEN` and `TELEGRAM_CHAT_ID` as repository
secrets. Add `SYMBOLS`, `ACCOUNT_BALANCE`, `RISK_PERCENT`, `HIGHER_TIMEFRAME`, and
`REQUIRE_HTF_CONFIRMATION` under **Settings → Secrets and variables → Actions →
Variables** when you want values other than the defaults above.

## Notes

- Yahoo Finance intraday data is slightly delayed (~1–15 min depending on market); fine for indicator alerts, not for HFT.
- Identical alerts are rate-limited to once per hour.
- Position sizes are estimates. Confirm contract size, spread, currency conversion,
  and execution price with your broker before trading.
- `/performance` measures later closed-candle SL/TP touches, not actual broker fills.
- A monthly maintenance workflow rotates a GitHub issue to keep public-repository
  scheduled workflows active and visible.
- Logs are written to `bot.log`.
