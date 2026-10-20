from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd
import pytest

from app.config import Settings
from app.data.provider import DataUnavailable, TwelveDataProvider
from app.data.validation import validate_candles
from app.analysis.signal_engine import Signal
from app.notifications.telegram_bot import format_signal
from app.storage.database import Database


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def json(self):
        return self.payload

    def raise_for_status(self):
        if self.status_code >= 400:
            import httpx
            raise httpx.HTTPStatusError("request failed", request=None, response=httpx.Response(self.status_code))


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, *, params, timeout):
        self.calls.append((url, params.copy(), timeout))
        result = self.responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def valid_payload(times=None):
    stamps = times or ["2026-10-17 10:00:00", "2026-10-17 10:05:00"]
    return {"meta": {"symbol": "EUR/USD"}, "values": [
        {"datetime": stamp, "open": "1.1000", "high": "1.1010", "low": "1.0990", "close": "1.1005"}
        for stamp in stamps
    ]}


def provider(client, **kwargs):
    return TwelveDataProvider("test-secret", min_request_interval=0, client=client, sleeper=lambda _: None, **kwargs)


def test_timeframe_symbol_and_request_mapping():
    client = FakeClient([FakeResponse(valid_payload())])
    p = provider(client)
    p.fetch_candles("EUR_USD", "M5", count=10)
    params = client.calls[0][1]
    assert params["symbol"] == "EUR/USD"
    assert params["interval"] == "5min"
    assert params["outputsize"] == 11
    assert params["timezone"] == "UTC"
    assert params["apikey"] == "test-secret"
    assert TwelveDataProvider.INTERVALS == {"M5": "5min", "M15": "15min", "H1": "1h", "H4": "4h"}


def test_settings_select_twelve_data_and_missing_key_is_actionable():
    settings = Settings(provider="twelve_data", twelve_data_api_key="")
    with pytest.raises(DataUnavailable, match="TWELVE_DATA_API_KEY"):
        TwelveDataProvider.from_settings(settings)
    settings = Settings(provider="unsupported", twelve_data_api_key="x")
    with pytest.raises(DataUnavailable, match="Unsupported"):
        TwelveDataProvider.from_settings(settings)


def test_settings_load_twelve_data_key_and_preserve_symbols(monkeypatch):
    monkeypatch.setenv("TWELVE_DATA_API_KEY", "configured-secret")
    monkeypatch.setenv("MARKET_DATA_PROVIDER", "twelve_data")
    monkeypatch.setenv("FOREX_SYMBOLS", "EUR/USD,GBP_USD")
    settings = Settings.load()
    assert settings.twelve_data_api_key == "configured-secret"
    assert settings.provider == "twelve_data"
    assert settings.symbols == ("EUR_USD", "GBP_USD")
    assert settings.mode == "signal"


def test_settings_load_ignores_unrecognized_api_key_environment_variables(monkeypatch):
    monkeypatch.setenv("TWELVE_DATA_API_KEY", "")
    monkeypatch.setenv("MARKET_DATA_PROVIDER", "twelve_data")
    settings = Settings.load()
    assert settings.twelve_data_api_key == ""


def test_successful_candles_are_numeric_sorted_utc_and_deduplicated():
    payload = valid_payload(["2026-10-17 10:05:00", "2026-10-17 10:00:00", "2026-10-17 10:00:00"])
    frame = provider(FakeClient([FakeResponse(payload)])).fetch_candles("EUR/USD", "M5")
    assert frame.timestamp.is_monotonic_increasing
    assert not frame.timestamp.duplicated().any()
    assert str(frame.timestamp.dtype) == "datetime64[ns, UTC]"
    assert frame.close.dtype.kind == "f"
    assert validate_candles(frame).equals(frame)


def test_incomplete_latest_candle_is_filtered():
    now = pd.Timestamp.now(tz="UTC").floor("5min")
    payload = valid_payload([str(now - pd.Timedelta(minutes=5)), str(now)])
    frame = provider(FakeClient([FakeResponse(payload)])).fetch_candles("EUR_USD", "M5")
    assert len(frame) == 1
    assert frame.timestamp.iloc[-1] == now - pd.Timedelta(minutes=5)
    assert frame.complete.all()


@pytest.mark.parametrize("bad_payload", [
    {"status": "error", "code": 400, "message": "Invalid interval"},
    {"values": []},
    {"values": [{"datetime": "2026-10-17 10:00:00", "open": "1", "high": "2", "low": "0"}]},
    {"values": [{"datetime": "bad-time", "open": "1", "high": "2", "low": "0", "close": "1"}]},
    {"values": [{"datetime": "2026-10-17 10:00:00", "open": "bad", "high": "2", "low": "0", "close": "1"}]},
])
def test_empty_error_and_malformed_responses_fail_closed(bad_payload):
    with pytest.raises(DataUnavailable):
        provider(FakeClient([FakeResponse(bad_payload)])).fetch_candles("EUR_USD", "M5")


def test_invalid_credentials_and_usage_exhaustion_are_clear():
    unauthorized = FakeResponse({"status": "error", "code": 401, "message": "bad key"})
    with pytest.raises(DataUnavailable, match="rejected"):
        provider(FakeClient([unauthorized])).fetch_candles("EUR_USD", "M5")
    exhausted = FakeResponse({"status": "error", "code": 429, "message": "credits"})
    p = provider(FakeClient([exhausted, exhausted]), max_retries=2)
    with pytest.raises(DataUnavailable, match="bounded attempts"):
        p.fetch_candles("EUR_USD", "M5")


def test_retry_limit_and_http_429():
    client = FakeClient([FakeResponse({}, 429), FakeResponse({}, 429), FakeResponse({}, 429), FakeResponse(valid_payload())])
    with pytest.raises(DataUnavailable, match="bounded attempts"):
        provider(client, max_retries=3).fetch_candles("EUR_USD", "M5")
    assert len(client.calls) == 3


def test_interval_cache_returns_copy_and_expires():
    now = [100.0]
    client = FakeClient([FakeResponse(valid_payload()), FakeResponse(valid_payload())])
    p = TwelveDataProvider("secret", min_request_interval=0, client=client, clock=lambda: now[0], sleeper=lambda _: None)
    first = p.fetch_candles("EUR_USD", "M5")
    first.loc[0, "close"] = 999
    second = p.fetch_candles("EUR_USD", "M5")
    assert len(client.calls) == 1
    assert second.close.iloc[0] != 999
    now[0] += 300
    p.fetch_candles("EUR_USD", "M5")
    assert len(client.calls) == 2


def test_unsupported_interval_symbol_and_count_rejected_before_request():
    client = FakeClient([])
    p = provider(client)
    with pytest.raises(ValueError, match="Unsupported timeframe"):
        p.fetch_candles("EUR_USD", "M1")
    with pytest.raises(ValueError, match="Invalid Forex symbol"):
        p.fetch_candles("EURUSD", "M5")
    with pytest.raises(ValueError, match="maximum"):
        p.fetch_candles("EUR_USD", "M5", 5000)
    assert client.calls == []


def test_invalid_data_cannot_pass_validation_to_strategy():
    frame = pd.DataFrame({"timestamp": [datetime.now(timezone.utc)], "open": [1.1], "high": [1.0], "low": [1.0], "close": [1.1]})
    with pytest.raises(ValueError, match="OHLC"):
        validate_candles(frame)


def test_stale_data_rejected_before_analysis():
    frame = pd.DataFrame({
        "timestamp": pd.date_range("2020-01-01", periods=2, freq="5min", tz="UTC"),
        "open": [1.1, 1.1], "high": [1.2, 1.2], "low": [1.0, 1.0], "close": [1.1, 1.1],
    })
    with pytest.raises(ValueError, match="stale"):
        validate_candles(frame, max_age_seconds=300, now=datetime(2026, 10, 17, tzinfo=timezone.utc))


def test_telegram_format_compatibility_and_duplicate_signal_prevention():
    signal = Signal(
        "signal-1", "EUR_USD", "2026-10-17T10:00:00+00:00", "BUY", "BUY", 1.1,
        1.09, 1.12, 2.0, {"H4": "BULLISH", "H1": "BULLISH", "M15": "BULLISH STRUCTURE", "M5": "ENTRY CONFIRMED"},
        "Confirmed setup", ["bullish_engulfing"],
    )
    message = format_signal(signal)
    assert "BUY" in message and "EUR/USD" in message
    assert "Entry: 1.10000" in message and "Stop loss: 1.09000" in message and "Take profit: 1.12000" in message
    with TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as temp_dir:
        db = Database(Path(temp_dir) / "signals.sqlite3")
        assert db.save_signal(signal) is True
        assert db.save_signal(signal) is False
