from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

import httpx
import pandas as pd

from app.config import Settings


class DataUnavailable(RuntimeError):
    """Market data could not be retrieved or validated."""


class TwelveDataProvider:
    """Twelve Data time-series client returning completed UTC OHLC candles."""

    BASE_URL = "https://api.twelvedata.com/time_series"
    INTERVALS = {"M5": "5min", "M15": "15min", "H1": "1h", "H4": "4h"}
    INTERVAL_SECONDS = {"M5": 300, "M15": 900, "H1": 3600, "H4": 14400}
    MAX_OUTPUT_SIZE = 5000

    def __init__(
        self,
        api_key: str,
        timeout: float = 15,
        max_retries: int = 3,
        min_request_interval: float = 7.5,
        *,
        client=None,
        clock=time.monotonic,
        sleeper=time.sleep,
    ):
        if not api_key or not api_key.strip():
            raise DataUnavailable("TWELVE_DATA_API_KEY is not configured; set it in the local .env file")
        if max_retries < 1:
            raise ValueError("max_retries must be at least 1")
        self.api_key = api_key.strip()
        self.timeout = timeout
        self.max_retries = max_retries
        self.min_request_interval = max(0.0, min_request_interval)
        self.client = client or httpx
        self.clock = clock
        self.sleeper = sleeper
        self._last_request_at: float | None = None
        self._cache: dict[tuple[str, str, int], tuple[float, pd.DataFrame]] = {}

    @classmethod
    def from_settings(cls, settings: Settings) -> "TwelveDataProvider":
        if settings.provider not in {"twelve_data", "twelvedata"}:
            raise DataUnavailable(f"Unsupported market data provider {settings.provider!r}; set MARKET_DATA_PROVIDER=twelve_data")
        return cls(settings.twelve_data_api_key, min_request_interval=settings.twelve_data_min_request_interval_seconds)

    def _pace(self) -> None:
        if self._last_request_at is not None:
            delay = self.min_request_interval - (self.clock() - self._last_request_at)
            if delay > 0:
                self.sleeper(delay)
        self._last_request_at = self.clock()

    @staticmethod
    def _symbol(symbol: str) -> str:
        parts = symbol.upper().replace("/", "_").split("_")
        if len(parts) != 2 or any(len(part) != 3 or not part.isalpha() for part in parts):
            raise ValueError(f"Invalid Forex symbol: {symbol!r}")
        return "/".join(parts)

    def fetch_candles(self, symbol: str, timeframe: str, count: int = 300) -> pd.DataFrame:
        timeframe = timeframe.upper()
        if timeframe not in self.INTERVALS:
            raise ValueError(f"Unsupported timeframe: {timeframe}")
        if not isinstance(count, int) or count < 1:
            raise ValueError("count must be a positive integer")
        if count >= self.MAX_OUTPUT_SIZE:
            raise ValueError(f"count must be less than the Twelve Data maximum of {self.MAX_OUTPUT_SIZE}")
        normalized_symbol = self._symbol(symbol)
        cache_key = (normalized_symbol, timeframe, count)
        now_mono = self.clock()
        cached = self._cache.get(cache_key)
        if cached and now_mono - cached[0] < self.INTERVAL_SECONDS[timeframe]:
            return cached[1].copy()

        params = {
            "symbol": normalized_symbol,
            "interval": self.INTERVALS[timeframe],
            "outputsize": count + 1,
            "timezone": "UTC",
            "format": "JSON",
            "apikey": self.api_key,
        }
        last_error: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                self._pace()
                response = self.client.get(self.BASE_URL, params=params, timeout=self.timeout)
                status = response.status_code
                if status in (401, 403):
                    raise DataUnavailable("Twelve Data rejected the API key or account entitlement (HTTP 401/403)")
                if status == 429:
                    raise _RetryableProviderError("Twelve Data rate limit reached (HTTP 429)")
                if status >= 500:
                    raise _RetryableProviderError(f"Twelve Data server error (HTTP {status})")
                response.raise_for_status()
                try:
                    payload = response.json()
                except (ValueError, TypeError) as exc:
                    raise DataUnavailable("Twelve Data returned invalid JSON") from exc
                if not isinstance(payload, dict):
                    raise DataUnavailable("Twelve Data returned an invalid response structure")
                if payload.get("status") == "error" or "code" in payload and "values" not in payload:
                    code = str(payload.get("code", ""))
                    if code == "429" or "API credits" in str(payload.get("message", "")):
                        raise _RetryableProviderError("Twelve Data API credits or rate limit exhausted")
                    if code in {"401", "403"}:
                        raise DataUnavailable("Twelve Data rejected the API key or account entitlement")
                    message = payload.get("message")
                    safe_message = str(message)[:180] if message else "no additional details"
                    raise DataUnavailable(f"Twelve Data request failed (code {code or 'unknown'}): {safe_message}")
                rows = payload.get("values")
                if not isinstance(rows, list) or not rows:
                    raise DataUnavailable("Twelve Data returned no candle values")
                parsed = []
                for row in rows:
                    if not isinstance(row, dict) or not all(k in row for k in ("datetime", "open", "high", "low", "close")):
                        raise DataUnavailable("Twelve Data returned a candle missing required OHLC fields")
                    try:
                        stamp = pd.to_datetime(row["datetime"], utc=True, errors="raise")
                        ohlc = {key: float(row[key]) for key in ("open", "high", "low", "close")}
                    except (ValueError, TypeError, OverflowError) as exc:
                        raise DataUnavailable("Twelve Data returned malformed candle timestamps or OHLC values") from exc
                    if not all(pd.notna(value) and abs(value) != float("inf") for value in ohlc.values()):
                        raise DataUnavailable("Twelve Data returned non-finite OHLC values")
                    parsed.append({"timestamp": stamp, **ohlc})
                frame = pd.DataFrame(parsed)
                frame = frame.sort_values("timestamp").drop_duplicates("timestamp", keep="last").reset_index(drop=True)
                if ((frame.high < frame[["open", "close", "low"]].max(axis=1)) | (frame.low > frame[["open", "close"]].min(axis=1))).any():
                    raise DataUnavailable("Twelve Data returned invalid OHLC relationships")
                now_utc = pd.Timestamp(datetime.now(timezone.utc))
                frame["complete"] = frame.timestamp + pd.to_timedelta(self.INTERVAL_SECONDS[timeframe], unit="s") <= now_utc
                frame = frame[frame.complete].tail(count).reset_index(drop=True)
                if frame.empty:
                    raise DataUnavailable("Twelve Data returned no completed candles")
                self._cache[cache_key] = (self.clock(), frame.copy())
                return frame
            except _RetryableProviderError as exc:
                last_error = exc
                if attempt + 1 < self.max_retries:
                    self.sleeper(min(2 ** attempt, 8))
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 429 or exc.response.status_code >= 500:
                    last_error = _RetryableProviderError(f"Twelve Data HTTP error {exc.response.status_code}")
                    if attempt + 1 < self.max_retries:
                        self.sleeper(min(2 ** attempt, 8))
                else:
                    raise DataUnavailable(f"Twelve Data request failed (HTTP {exc.response.status_code})") from exc
            except httpx.HTTPError as exc:
                last_error = exc
                if attempt + 1 < self.max_retries:
                    self.sleeper(min(2 ** attempt, 8))
            except DataUnavailable:
                raise
            except (KeyError, TypeError, ValueError) as exc:
                raise DataUnavailable("Twelve Data returned malformed candle data") from exc
        logging.warning("Twelve Data request failed for %s %s after bounded retries", normalized_symbol, timeframe)
        error_kind = type(last_error).__name__ if last_error is not None else "unknown error"
        raise DataUnavailable(f"Twelve Data request failed after {self.max_retries} bounded attempts ({error_kind}); check network access, rate limits, and API allowance") from last_error


class _RetryableProviderError(RuntimeError):
    pass


Provider = TwelveDataProvider
