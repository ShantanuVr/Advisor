"""Home page route - daily summary for both symbols."""

from datetime import date, datetime
from fastapi import APIRouter, Request, Depends
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pathlib import Path

from app.database import get_db
from app.models import DailyReport, Snapshot, EconomicEvent, TASignal
from app.config import BASE_DIR, SYMBOLS, TIMEZONE

router = APIRouter()
templates = Jinja2Templates(directory=BASE_DIR / "app" / "templates")


def get_workflow_status(db: Session, target_date: date) -> dict:
    """Determine current workflow status for the day."""
    status = {
        "screenshots_collected": False,
        "calendar_fetched": False,
        "news_fetched": False,
        "analysis_complete": False,
        "report_generated": False,
    }
    
    # Check for screenshots today
    screenshot_count = db.query(Snapshot).filter(
        Snapshot.captured_at >= datetime.combine(target_date, datetime.min.time()),
        Snapshot.captured_at < datetime.combine(target_date, datetime.max.time())
    ).count()
    status["screenshots_collected"] = screenshot_count > 0
    
    # Check for calendar events (any recent fetch)
    event_count = db.query(EconomicEvent).filter(
        EconomicEvent.event_time_utc >= datetime.combine(target_date, datetime.min.time())
    ).count()
    status["calendar_fetched"] = event_count > 0
    
    # Check for TA signals today
    signal_count = db.query(TASignal).filter(TASignal.date == target_date).count()
    status["analysis_complete"] = signal_count > 0
    
    # Check for reports today
    report_count = db.query(DailyReport).filter(DailyReport.date == target_date).count()
    status["report_generated"] = report_count > 0
    
    return status


@router.get("/")
async def home(request: Request, db: Session = Depends(get_db)):
    """Render home page with today's summary."""
    today = date.today()
    
    # Get workflow status
    workflow_status = get_workflow_status(db, today)
    
    # Get today's reports for each symbol
    reports = {}
    for symbol in SYMBOLS:
        report = db.query(DailyReport).filter(
            DailyReport.date == today,
            DailyReport.symbol == symbol
        ).first()
        reports[symbol] = report
    
    # Get today's high-impact events
    today_start = datetime.combine(today, datetime.min.time())
    today_end = datetime.combine(today, datetime.max.time())
    high_impact_events = db.query(EconomicEvent).filter(
        EconomicEvent.event_time_utc >= today_start,
        EconomicEvent.event_time_utc <= today_end,
        EconomicEvent.impact == "high",
        EconomicEvent.currency.in_(["USD", "EUR"])
    ).order_by(EconomicEvent.event_time_utc).all()
    
    return templates.TemplateResponse("home.html", {
        "request": request,
        "today": today,
        "symbols": SYMBOLS,
        "reports": reports,
        "workflow_status": workflow_status,
        "high_impact_events": high_impact_events,
        "timezone": TIMEZONE,
    })
