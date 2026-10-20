import pandas as pd
import pytest

from app.data.validation import validate_candles
from app.indicators.core import ema, rsi, atr, macd
from app.risk.calculations import pip_size, spread_pips, stop_and_target, position_units
from app.analysis.support_resistance import swing_levels
from app.backtesting.engine import simulate_bracket_entries


def candles(n=250):
    close=pd.Series([1+i*.001 for i in range(n)])
    return pd.DataFrame({"timestamp":pd.date_range("2025-01-01",periods=n,freq="h",tz="UTC"),"open":close-.0003,"high":close+.001,"low":close-.001,"close":close})


def test_indicator_warmups_and_trend():
    f=candles()
    assert pd.isna(ema(f.close, 50).iloc[48])
    assert ema(f.close,50).iloc[-1] > ema(f.close,200).iloc[-1]
    assert rsi(f.close).iloc[-1] == pytest.approx(100)
    assert atr(f).iloc[-1] > 0
    assert macd(f.close).iloc[-1].notna().all()


def test_validation_rejects_bad_and_duplicates():
    f=candles(5)
    assert len(validate_candles(f))==5
    bad=f.copy(); bad.loc[0,"high"]=0
    with pytest.raises(ValueError): validate_candles(bad)
    dup=pd.concat([f,f.iloc[[0]]])
    with pytest.raises(ValueError): validate_candles(dup)


def test_risk_and_pips():
    assert pip_size("USD_JPY")==.01
    assert spread_pips("EUR_USD",1.1,1.1002)==pytest.approx(2)
    sl,tp=stop_and_target("EUR_USD","BUY",1.1,.001,rr=2)
    assert sl < 1.1 < tp
    assert position_units(10000,.5,.01)>0


def test_structure_and_conservative_backtest():
    f=candles(8)
    assert set(swing_levels(f))=={"support","resistance"}
    res=simulate_bracket_entries(f,[{"direction":"BUY","index":0,"entry":1.1,"stop_loss":1.0,"take_profit":1.2}])
    assert res["trades"]==1 and res["limitations"]
