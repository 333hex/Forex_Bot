from __future__ import annotations

from dataclasses import dataclass


def pip_size(symbol: str) -> float:
    return 0.01 if symbol.upper().endswith("_JPY") else 0.0001


def spread_pips(symbol: str, bid: float, ask: float) -> float:
    if ask < bid: raise ValueError("ask cannot be below bid")
    return (ask-bid)/pip_size(symbol)


def stop_and_target(symbol: str, direction: str, entry: float, atr_value: float, structure_level: float | None = None, rr: float = 2.0) -> tuple[float,float]:
    if atr_value <= 0 or rr < 1: raise ValueError("ATR must be positive and reward/risk at least 1")
    distance = max(1.5*atr_value, abs(entry-structure_level) if structure_level is not None else 0)
    if direction == "BUY": return entry-distance, entry+distance*rr
    if direction == "SELL": return entry+distance, entry-distance*rr
    raise ValueError("direction must be BUY or SELL")


def position_units(equity: float, risk_percent: float, stop_distance: float, quote_to_account_rate: float = 1.0) -> float:
    """Approximate units for quote-currency accounts; caller must supply a valid conversion rate."""
    if equity <= 0 or not 0 < risk_percent <= 2 or stop_distance <= 0 or quote_to_account_rate <= 0:
        raise ValueError("equity, risk, stop distance, and conversion rate must be valid")
    return equity*risk_percent/100/(stop_distance*quote_to_account_rate)


@dataclass
class RiskState:
    trades_today: int = 0
    open_paper_trades: int = 0
    daily_loss_percent: float = 0.0

    def allows(self, max_trades: int, max_open: int, max_daily_loss: float) -> bool:
        return self.trades_today < max_trades and self.open_paper_trades < max_open and self.daily_loss_percent < max_daily_loss
