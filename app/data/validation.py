from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd


def validate_candles(frame: pd.DataFrame, *, max_age_seconds: int | None = None, now: datetime | None = None) -> pd.DataFrame:
    required = {"timestamp", "open", "high", "low", "close"}
    if not isinstance(frame, pd.DataFrame) or not required.issubset(frame.columns) or frame.empty:
        raise ValueError("Candle data is empty or missing required OHLC fields")
    data = frame.copy()
    data["timestamp"] = pd.to_datetime(data.timestamp, utc=True, errors="coerce")
    if data.timestamp.isna().any() or data.timestamp.duplicated().any():
        raise ValueError("Candle timestamps are invalid or duplicated")
    data = data.sort_values("timestamp").reset_index(drop=True)
    for col in ("open", "high", "low", "close"):
        data[col] = pd.to_numeric(data[col], errors="coerce")
    vals = data[["open", "high", "low", "close"]].to_numpy()
    if not np.isfinite(vals).all():
        raise ValueError("Candle has missing or non-finite OHLC prices")
    if ((data.high < data[["open", "close", "low"]].max(axis=1)) | (data.low > data[["open", "close"]].min(axis=1))).any():
        raise ValueError("Invalid OHLC relationship")
    if "complete" in data.columns:
        data = data[data.complete.astype(bool)].reset_index(drop=True)
    if data.empty:
        raise ValueError("No completed candles are available")
    if max_age_seconds is not None:
        current = pd.Timestamp(now or datetime.now(timezone.utc))
        age = (current - data.timestamp.iloc[-1]).total_seconds()
        if age > max_age_seconds:
            raise ValueError(f"Market data is stale ({int(age)} seconds old)")
    return data
