from __future__ import annotations

import numpy as np
import pandas as pd


def ema(series: pd.Series, period: int) -> pd.Series:
    if period < 1: raise ValueError("period must be positive")
    return series.astype(float).ewm(span=period, adjust=False, min_periods=period).mean()


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.astype(float).diff()
    gain, loss = delta.clip(lower=0), -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1/period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    out = 100 - 100 / (1 + rs)
    return out.where(avg_loss.ne(0), 100.0).where(avg_gain.ne(0) | avg_loss.ne(0))


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    line = ema(close, fast) - ema(close, slow)
    sig = line.ewm(span=signal, adjust=False, min_periods=signal).mean()
    return pd.DataFrame({"macd": line, "signal": sig, "histogram": line - sig})


def atr(frame: pd.DataFrame, period: int = 14) -> pd.Series:
    prev = frame.close.shift(1)
    tr = pd.concat([frame.high-frame.low, (frame.high-prev).abs(), (frame.low-prev).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1/period, adjust=False, min_periods=period).mean()


def adx(frame: pd.DataFrame, period: int = 14) -> pd.Series:
    up, down = frame.high.diff(), -frame.low.diff()
    plus = up.where((up > down) & (up > 0), 0.0)
    minus = down.where((down > up) & (down > 0), 0.0)
    a = atr(frame, period).replace(0, np.nan)
    pdi = 100 * plus.ewm(alpha=1/period, adjust=False, min_periods=period).mean() / a
    mdi = 100 * minus.ewm(alpha=1/period, adjust=False, min_periods=period).mean() / a
    dx = 100 * (pdi-mdi).abs() / (pdi+mdi).replace(0, np.nan)
    return dx.ewm(alpha=1/period, adjust=False, min_periods=period).mean()


def bollinger(close: pd.Series, period: int = 20, deviations: float = 2) -> pd.DataFrame:
    mid = close.rolling(period, min_periods=period).mean()
    sd = close.rolling(period, min_periods=period).std(ddof=0)
    return pd.DataFrame({"middle": mid, "upper": mid + deviations*sd, "lower": mid - deviations*sd})


def stochastic(frame: pd.DataFrame, period: int = 14, smooth: int = 3) -> pd.DataFrame:
    low, high = frame.low.rolling(period).min(), frame.high.rolling(period).max()
    k = 100 * (frame.close-low) / (high-low).replace(0, np.nan)
    return pd.DataFrame({"k": k, "d": k.rolling(smooth).mean()})


def roc(close: pd.Series, period: int = 12) -> pd.Series:
    return close.pct_change(periods=period) * 100


def historical_volatility(close: pd.Series, period: int = 20) -> pd.Series:
    return np.log(close / close.shift(1)).rolling(period).std(ddof=0) * np.sqrt(period)


def supertrend(frame: pd.DataFrame, period: int = 10, multiplier: float = 3.0) -> pd.DataFrame:
    mid = (frame.high + frame.low) / 2
    a = atr(frame, period)
    upper, lower = mid + multiplier*a, mid - multiplier*a
    trend = pd.Series(index=frame.index, dtype=float)
    direction = pd.Series(index=frame.index, dtype=float)
    for i in range(len(frame)):
        if i == 0 or pd.isna(a.iloc[i]):
            trend.iloc[i], direction.iloc[i] = np.nan, np.nan
            continue
        prev_dir = direction.iloc[i-1]
        direction.iloc[i] = 1 if (frame.close.iloc[i] > upper.iloc[i-1] if prev_dir != -1 else frame.close.iloc[i] >= lower.iloc[i-1]) else -1
        trend.iloc[i] = lower.iloc[i] if direction.iloc[i] == 1 else upper.iloc[i]
    return pd.DataFrame({"supertrend": trend, "direction": direction})


def candle_features(frame: pd.DataFrame) -> pd.DataFrame:
    rng = (frame.high-frame.low).replace(0, np.nan)
    body = (frame.close-frame.open).abs()
    return pd.DataFrame({"range": rng, "body_ratio": body/rng, "upper_wick_ratio": (frame.high-frame[["open","close"]].max(axis=1))/rng, "lower_wick_ratio": (frame[["open","close"]].min(axis=1)-frame.low)/rng})
