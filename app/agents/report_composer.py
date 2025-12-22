"""Report composer - generates final trade plans from all data."""

import json
from datetime import date, datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models import DailyReport, TASignal, Snapshot, EconomicEvent, NewsItem
from app.config import REPORTS_DIR, DANGER_WINDOW_MINUTES
from app.agents.fundamental import get_danger_windows
from app.agents.news_collector import get_top_drivers


def compose_report(db: Session, target_date: date, symbol: str) -> Optional[DailyReport]:
    """
    Compose a daily report for a symbol by combining TA signals,
    calendar events, and news.
    
    Returns the created DailyReport or None if insufficient data.
    """
    # Get TA signal for this symbol/date
    ta_signal = db.query(TASignal).filter(
        TASignal.date == target_date,
        TASignal.symbol == symbol,
        TASignal.timeframe.is_(None)  # Aggregate signal
    ).first()
    
    if not ta_signal:
        return None
    
    # Get danger windows
    danger_windows = get_danger_windows(db, target_date)
    
    # Get top news drivers
    top_news = get_top_drivers(db, limit=3)
    
    # Get primary screenshot (prefer 1H or 4H)
    today_start = datetime.combine(target_date, datetime.min.time())
    today_end = datetime.combine(target_date, datetime.max.time())
    
    primary_snapshot = db.query(Snapshot).filter(
        Snapshot.symbol == symbol,
        Snapshot.captured_at >= today_start,
        Snapshot.captured_at <= today_end,
        Snapshot.timeframe.in_(["1H", "4H", "1D"])
    ).first()
    
    # Parse data
    turtle_soup = ta_signal.turtle_soup_json or {}
    trade_plan = ta_signal.trade_plan_json or {}
    levels = ta_signal.levels_json or {}
    
    # Build report
    report_data = {
        "direction": "no_trade",
        "entry_zone": None,
        "invalidation": None,
        "tp1": None,
        "tp2": None,
        "stand_down_conditions": [],
        "supporting_evidence": [],
        "missing_data": [],
        "confidence": ta_signal.confidence,
        "bias": ta_signal.bias,
        "ict_notes": ta_signal.ict_notes,
        "levels": levels,
        "turtle_soup": turtle_soup,
    }
    
    # Prioritize trade_plan.direction (main trade plan) over turtle_soup (counter-trend scalp)
    if trade_plan.get("direction") and trade_plan.get("direction") != "no_trade":
        tp_direction = trade_plan.get("direction", "").lower()
        if tp_direction in ["long", "short"]:
            report_data["direction"] = tp_direction
            report_data["entry_zone"] = trade_plan.get("entry_zone")
            report_data["invalidation"] = trade_plan.get("invalidation")
            report_data["tp1"] = trade_plan.get("tp1")
            report_data["tp2"] = trade_plan.get("tp2")
            report_data["stand_down_conditions"] = trade_plan.get("stand_down_if", [])
            report_data["supporting_evidence"].append(
                f"Trade plan: {tp_direction.upper()} bias with {ta_signal.confidence}% confidence"
            )
            # Add turtle soup as context if detected
            if turtle_soup.get("detected"):
                ts_direction = turtle_soup.get("direction", "").lower()
                report_data["supporting_evidence"].append(
                    f"Turtle Soup {ts_direction} setup also detected (counter-trend scalp): {turtle_soup.get('description', 'N/A')[:100]}..."
                )
    elif turtle_soup.get("detected"):
        # Fall back to turtle soup if no trade plan
        ts_direction = turtle_soup.get("direction", "").lower()
        if ts_direction in ["long", "short"]:
            report_data["direction"] = ts_direction
            report_data["entry_zone"] = {"value": turtle_soup.get("entry")}
            report_data["invalidation"] = turtle_soup.get("invalidation")
            report_data["tp1"] = turtle_soup.get("tp1")
            report_data["tp2"] = turtle_soup.get("tp2")
            report_data["supporting_evidence"].append(
                f"Turtle Soup {ts_direction} setup detected: {turtle_soup.get('description', 'N/A')}"
            )
    elif ta_signal.confidence >= 70:
        # Strong directional bias without specific setup
        if ta_signal.bias == "bullish":
            report_data["direction"] = "long"
            report_data["supporting_evidence"].append(
                f"Strong bullish bias ({ta_signal.confidence}% confidence)"
            )
        elif ta_signal.bias == "bearish":
            report_data["direction"] = "short"
            report_data["supporting_evidence"].append(
                f"Strong bearish bias ({ta_signal.confidence}% confidence)"
            )
    
    # Add danger window conditions
    for window in danger_windows:
        event = window["event"]
        start_str = window["start"].strftime("%H:%M")
        end_str = window["end"].strftime("%H:%M")
        report_data["stand_down_conditions"].append(
            f"High-impact event: {event.title} ({event.currency}) - avoid trading {start_str}-{end_str} UTC"
        )
    
    # Add news context
    for item in top_news:
        stance_text = item.stance or "neutral"
        report_data["supporting_evidence"].append(
            f"News ({stance_text}): {item.title[:80]}..."
        )
    
    # Check for missing data
    snapshots = db.query(Snapshot).filter(
        Snapshot.symbol == symbol,
        Snapshot.captured_at >= today_start,
        Snapshot.captured_at <= today_end
    ).all()
    
    timeframes_found = {s.timeframe for s in snapshots}
    required_tfs = {"1W", "1D", "4H", "1H"}
    missing_tfs = required_tfs - timeframes_found
    if missing_tfs:
        report_data["missing_data"].append(f"Missing timeframes: {', '.join(sorted(missing_tfs))}")
        report_data["confidence"] = max(30, report_data["confidence"] - len(missing_tfs) * 10)
    
    # Delete existing report for this date/symbol
    db.query(DailyReport).filter(
        DailyReport.date == target_date,
        DailyReport.symbol == symbol
    ).delete()
    
    # Create new report
    report = DailyReport(
        date=target_date,
        symbol=symbol,
        report_json=report_data,
        primary_snapshot_id=primary_snapshot.id if primary_snapshot else None,
    )
    db.add(report)
    db.commit()
    
    # Export to JSON file
    export_report_to_file(report, target_date, symbol)
    
    return report


def export_report_to_file(report: DailyReport, target_date: date, symbol: str):
    """Export report to JSON file."""
    file_path = REPORTS_DIR / f"{target_date.isoformat()}_{symbol}.json"
    
    export_data = {
        "date": target_date.isoformat(),
        "symbol": symbol,
        "generated_at": datetime.now().isoformat(),
        **report.report_json,
    }
    
    with open(file_path, "w") as f:
        json.dump(export_data, f, indent=2)


def get_report_summary(report: DailyReport) -> dict:
    """Get a summary of the report for display."""
    data = report.report_json or {}
    
    direction = data.get("direction", "no_trade")
    
    summary = {
        "direction": direction,
        "direction_display": {
            "long": "📈 LONG",
            "short": "📉 SHORT", 
            "no_trade": "⏸️ NO TRADE"
        }.get(direction, "⏸️ NO TRADE"),
        "confidence": data.get("confidence", 0),
        "entry_zone": data.get("entry_zone"),
        "invalidation": data.get("invalidation"),
        "tp1": data.get("tp1"),
        "tp2": data.get("tp2"),
        "stand_down_count": len(data.get("stand_down_conditions", [])),
        "has_turtle_soup": bool(data.get("turtle_soup", {}).get("detected")),
    }
    
    return summary
