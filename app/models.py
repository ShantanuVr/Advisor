"""SQLAlchemy ORM models for the advisor database."""

from datetime import datetime, date
from sqlalchemy import Column, Integer, String, Text, DateTime, Date, Float, ForeignKey, JSON
from sqlalchemy.orm import relationship

from app.database import Base


class Snapshot(Base):
    """TradingView chart screenshots."""
    __tablename__ = "snapshots"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String(10), nullable=False, index=True)  # XAUUSD, EURUSD
    timeframe = Column(String(5), nullable=False)  # 1W, 1D, 4H, 1H, 15M, 5M
    captured_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    file_path = Column(String(500), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<Snapshot {self.symbol} {self.timeframe} @ {self.captured_at}>"


class EconomicEvent(Base):
    """ForexFactory calendar events."""
    __tablename__ = "economic_events"

    id = Column(Integer, primary_key=True, index=True)
    event_time_utc = Column(DateTime, nullable=False, index=True)
    currency = Column(String(5), nullable=False, index=True)  # USD, EUR, etc.
    impact = Column(String(10), nullable=False)  # high, medium, low
    title = Column(String(500), nullable=False)
    forecast = Column(String(100), nullable=True)
    previous = Column(String(100), nullable=True)
    actual = Column(String(100), nullable=True)
    source = Column(String(50), default="forexfactory")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<EconomicEvent {self.currency} {self.title} @ {self.event_time_utc}>"


class NewsItem(Base):
    """News articles related to Fed/FOMC."""
    __tablename__ = "news_items"

    id = Column(Integer, primary_key=True, index=True)
    published_at = Column(DateTime, nullable=False, index=True)
    source = Column(String(100), nullable=False)
    title = Column(String(1000), nullable=False)
    url = Column(String(2000), nullable=False, unique=True)
    summary = Column(Text, nullable=True)  # Filled in after Cursor analysis
    stance = Column(String(20), nullable=True)  # hawkish, dovish, neutral, risk_on, risk_off
    confidence = Column(Float, nullable=True)  # 0-100
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<NewsItem {self.source}: {self.title[:50]}>"


class TASignal(Base):
    """Technical analysis signals from Cursor analysis."""
    __tablename__ = "ta_signals"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, nullable=False, index=True)
    symbol = Column(String(10), nullable=False, index=True)
    timeframe = Column(String(5), nullable=True)  # NULL for aggregate signal
    bias = Column(String(20), nullable=False)  # bullish, bearish, neutral
    confidence = Column(Float, nullable=False)  # 0-100
    levels_json = Column(JSON, nullable=True)  # {pdh, pdl, pwh, pwl, session_high, session_low}
    ict_notes = Column(Text, nullable=True)  # Freeform ICT analysis notes
    turtle_soup_json = Column(JSON, nullable=True)  # {detected, entry, invalidation, description}
    trade_plan_json = Column(JSON, nullable=True)  # {direction, entry_zone, invalidation, tp1, tp2, stand_down_if}
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<TASignal {self.symbol} {self.date} {self.bias}>"


class DailyReport(Base):
    """Generated daily trade plans."""
    __tablename__ = "daily_reports"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, nullable=False, index=True)
    symbol = Column(String(10), nullable=False, index=True)
    report_json = Column(JSON, nullable=False)
    # Report structure:
    # {
    #   "direction": "long" | "short" | "no_trade",
    #   "entry_zone": {"low": float, "high": float} | null,
    #   "invalidation": float | null,
    #   "tp1": float | null,
    #   "tp2": float | null,
    #   "stand_down_conditions": [str],
    #   "supporting_evidence": [str],
    #   "missing_data": [str],
    #   "confidence": float
    # }
    primary_snapshot_id = Column(Integer, ForeignKey("snapshots.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    primary_snapshot = relationship("Snapshot")

    def __repr__(self):
        return f"<DailyReport {self.symbol} {self.date}>"
