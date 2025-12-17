"""Economic calendar page route."""

from datetime import date, datetime, timedelta
from fastapi import APIRouter, Request, Depends
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import EconomicEvent
from app.config import BASE_DIR, TIMEZONE, DANGER_WINDOW_MINUTES

router = APIRouter()
templates = Jinja2Templates(directory=BASE_DIR / "app" / "templates")


@router.get("/calendar")
async def calendar_view(request: Request, db: Session = Depends(get_db)):
    """Render calendar page with today + next 7 days events."""
    today = date.today()
    end_date = today + timedelta(days=7)
    
    start_dt = datetime.combine(today, datetime.min.time())
    end_dt = datetime.combine(end_date, datetime.max.time())
    
    # Get all USD/EUR events for the period
    events = db.query(EconomicEvent).filter(
        EconomicEvent.event_time_utc >= start_dt,
        EconomicEvent.event_time_utc <= end_dt,
        EconomicEvent.currency.in_(["USD", "EUR"])
    ).order_by(EconomicEvent.event_time_utc).all()
    
    # Group events by date
    events_by_date = {}
    for event in events:
        event_date = event.event_time_utc.date()
        if event_date not in events_by_date:
            events_by_date[event_date] = []
        events_by_date[event_date].append(event)
    
    # Generate list of dates
    dates = []
    current = today
    while current <= end_date:
        dates.append(current)
        current += timedelta(days=1)
    
    return templates.TemplateResponse("calendar.html", {
        "request": request,
        "today": today,
        "dates": dates,
        "events_by_date": events_by_date,
        "timezone": TIMEZONE,
        "danger_window": DANGER_WINDOW_MINUTES,
    })
