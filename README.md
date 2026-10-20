# TradeAssist Forex

Local Forex signal scanner with Twelve Data candle ingestion, SQLite signal history, technical analysis, risk calculations, paper-trade utilities, and Telegram notifications. The application does not place broker orders; `TRADING_MODE=signal` is the default.

## Windows PowerShell setup

1. Install Python 3.12 and create the environment:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

2. Create a Twelve Data account and put the key in `TWELVE_DATA_API_KEY` in `.env`. The scanner uses `GET https://api.twelvedata.com/time_series` with a Forex `BASE/QUOTE` symbol and the `5min`, `15min`, `1h`, and `4h` intervals. Keep `.env` private. `MARKET_DATA_PROVIDER=twelve_data` is the default.

3. Optional Telegram notification setup: create a bot with BotFather, obtain its chat ID, and set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`. Credentials are optional for local scans. Telegram failures are logged without changing a completed analysis result.

4. `FOREX_SYMBOLS` defaults to EUR/USD, GBP/USD, USD/JPY, USD/CHF, AUD/USD, NZD/USD, and USD/CAD. Slash or underscore notation is accepted. The scanner preserves H4/H1 trend confirmation and M15/M5 entry analysis. It uses completed candles only; missing bid/ask spread data continues to reject entries under the existing strategy.

## Commands

```powershell
python -m pytest
python main.py status
python main.py scan
python main.py run
```

`status` shows the active provider and whether a key is configured, without showing its value. `scan` performs one full scan and exits with a failure code if any pair could not be fetched and validated. `run` repeats scans until Ctrl+C. Data failures are reported as `DATA UNAVAILABLE` and cannot create a signal for that pair.

## API allowance and polling

The Twelve Data `/time_series` endpoint costs one API credit per symbol request. The Basic plan currently lists 8 API credits/minute and 800/day; this application makes up to 28 requests for an uncached full scan (seven pairs across four intervals). The defaults pace uncached requests at 7.5 seconds and poll hourly. In-memory candle caching follows each interval's bar duration, so routine hourly scans request only refreshed series. This schedule is designed to stay within the published Basic allowance; account entitlements, coverage, usage, and plan limits can differ, so check your Twelve Data dashboard before increasing scan frequency or disabling pacing. Rate limits and exhausted credits are retried a bounded number of times and reported clearly.

Current Twelve Data docs: [time series](https://twelvedata.com/docs#time-series), [pricing and API credits](https://twelvedata.com/pricing), [Forex coverage](https://twelvedata.com/forex).

## Existing behavior

- Indicators and strategy remain in `app/indicators` and `app/analysis`: H4/H1 trend, M15 structure and momentum, M5 completed-candle trigger, spread qualification, and ATR-derived bracket levels.
- SQLite stores signal/decision history and paper-trade intents. `TRADING_MODE=paper` retains the existing paper-only behavior; no broker execution exists.
- Telegram sends only new BUY/SELL signals, with entry, stop, target, timestamp, and timeframe context when available.
- Twelve Data Forex candles are mid-price candles and do not provide bid/ask quotes. The existing strategy requires spread qualification, so it can remain in WAIT even with complete data; no spread or price is fabricated.
- The conservative bracket simulator does not model spread, slippage, swaps, commissions, or derive historical multi-timeframe signals.

## Configuration

See `.env.example` for all supported variables. The local `.env` is ignored by Git and must not contain committed credentials. Set `SCAN_INTERVAL_SECONDS` and `TWELVE_DATA_MIN_REQUEST_INTERVAL_SECONDS` to values appropriate for your plan. The default interval is deliberately hourly to stay within Basic daily usage for the configured pairs/timeframes. A single full scan still needs up to 28 API credits and takes several minutes with Basic pacing.

Risk settings are guardrails, not recommendations. The strategy needs out-of-sample validation, and sizing helpers require valid account-currency conversion data before practical use.
