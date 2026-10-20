from app.storage.database import Database


class PaperSimulator:
    def __init__(self, database: Database): self.database=database
    def open_from_signal(self, signal): return self.database.open_paper_trade(signal)
    def update(self, symbol: str, candle):
        return self.database.mark_paper_trades(symbol,float(candle.high),float(candle.low),str(candle.timestamp))
