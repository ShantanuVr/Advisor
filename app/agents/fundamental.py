"""Fundamental data ingestion - ForexFactory calendar scraper."""

import re
from datetime import datetime, timedelta
from typing import List, Optional
import httpx
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from app.models import EconomicEvent
from app.config import DANGER_WINDOW_MINUTES


# ForexFactory calendar URL pattern
FF_CALENDAR_URL = "https://www.forexfactory.com/calendar"


def get_month_url(year: int, month: int) -> str:
    """Generate ForexFactory URL for a specific month."""
    month_names = ["jan", "feb", "mar", "apr", "may", "jun", 
                   "jul", "aug", "sep", "oct", "nov", "dec"]
    month_str = month_names[month - 1]
    return f"{FF_CALENDAR_URL}?month={month_str}.{year}"


async def fetch_calendar_page(url: str) -> Optional[str]:
    """Fetch calendar page HTML."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers, timeout=30.0)
            response.raise_for_status()
            return response.text
    except Exception as e:
        print(f"Error fetching {url}: {e}")
        return None


def parse_calendar_html(html: str, year: int) -> List[dict]:
    """
    Parse ForexFactory calendar HTML to extract events.
    
    Note: ForexFactory's HTML structure may change. This parser attempts
    to extract the key fields but may need updates if the site changes.
    """
    events = []
    soup = BeautifulSoup(html, "lxml")
    
    # Find calendar table rows
    rows = soup.select("tr.calendar__row")
    
    current_date = None
    
    for row in rows:
        try:
            # Check for date cell
            date_cell = row.select_one("td.calendar__date")
            if date_cell:
                date_text = date_cell.get_text(strip=True)
                if date_text:
                    # Parse date (format varies: "Mon Dec 16" or similar)
                    try:
                        # Try to parse the date
                        parsed = datetime.strptime(f"{date_text} {year}", "%a%b %d %Y")
                        current_date = parsed.date()
                    except ValueError:
                        try:
                            parsed = datetime.strptime(f"{date_text} {year}", "%b %d %Y")
                            current_date = parsed.date()
                        except ValueError:
                            pass
            
            if not current_date:
                continue
            
            # Get currency
            currency_cell = row.select_one("td.calendar__currency")
            if not currency_cell:
                continue
            currency = currency_cell.get_text(strip=True).upper()
            
            # Only interested in USD and EUR
            if currency not in ["USD", "EUR"]:
                continue
            
            # Get impact
            impact_cell = row.select_one("td.calendar__impact")
            impact = "low"
            if impact_cell:
                impact_span = impact_cell.select_one("span")
                if impact_span:
                    classes = impact_span.get("class", [])
                    if any("high" in c for c in classes):
                        impact = "high"
                    elif any("medium" in c for c in classes):
                        impact = "medium"
            
            # Get time
            time_cell = row.select_one("td.calendar__time")
            event_time = None
            if time_cell:
                time_text = time_cell.get_text(strip=True)
                if time_text and time_text not in ["", "All Day", "Tentative"]:
                    try:
                        # Parse time (format: "8:30am" or "2:00pm")
                        time_parsed = datetime.strptime(time_text.lower(), "%I:%M%p")
                        event_time = datetime.combine(current_date, time_parsed.time())
                    except ValueError:
                        event_time = datetime.combine(current_date, datetime.min.time())
                else:
                    event_time = datetime.combine(current_date, datetime.min.time())
            
            if not event_time:
                event_time = datetime.combine(current_date, datetime.min.time())
            
            # Get event title
            event_cell = row.select_one("td.calendar__event")
            if not event_cell:
                continue
            title = event_cell.get_text(strip=True)
            if not title:
                continue
            
            # Get forecast, previous, actual
            forecast_cell = row.select_one("td.calendar__forecast")
            forecast = forecast_cell.get_text(strip=True) if forecast_cell else None
            
            previous_cell = row.select_one("td.calendar__previous")
            previous = previous_cell.get_text(strip=True) if previous_cell else None
            
            actual_cell = row.select_one("td.calendar__actual")
            actual = actual_cell.get_text(strip=True) if actual_cell else None
            
            events.append({
                "event_time_utc": event_time,
                "currency": currency,
                "impact": impact,
                "title": title,
                "forecast": forecast or None,
                "previous": previous or None,
                "actual": actual or None,
            })
            
        except Exception as e:
            # Skip problematic rows
            continue
    
    return events


async def fetch_and_store_calendar(db: Session) -> dict:
    """
    Fetch ForexFactory calendar for current and previous month.
    Upsert events into database.
    """
    results = {
        "fetched": 0,
        "inserted": 0,
        "updated": 0,
        "errors": [],
    }
    
    now = datetime.now()
    current_month = (now.year, now.month)
    
    # Calculate previous month
    if now.month == 1:
        prev_month = (now.year - 1, 12)
    else:
        prev_month = (now.year, now.month - 1)
    
    months_to_fetch = [prev_month, current_month]
    
    for year, month in months_to_fetch:
        url = get_month_url(year, month)
        html = await fetch_calendar_page(url)
        
        if not html:
            results["errors"].append(f"Failed to fetch {url}")
            continue
        
        events = parse_calendar_html(html, year)
        results["fetched"] += len(events)
        
        for event_data in events:
            # Check if event already exists
            existing = db.query(EconomicEvent).filter(
                EconomicEvent.event_time_utc == event_data["event_time_utc"],
                EconomicEvent.currency == event_data["currency"],
                EconomicEvent.title == event_data["title"]
            ).first()
            
            if existing:
                # Update if actual value changed
                if event_data["actual"] and existing.actual != event_data["actual"]:
                    existing.actual = event_data["actual"]
                    existing.updated_at = datetime.utcnow()
                    results["updated"] += 1
            else:
                # Insert new event
                event = EconomicEvent(**event_data, source="forexfactory")
                db.add(event)
                results["inserted"] += 1
    
    db.commit()
    return results


def get_todays_events(db: Session, currencies: List[str] = None) -> List[EconomicEvent]:
    """Get today's economic events, optionally filtered by currency."""
    today = datetime.now().date()
    start = datetime.combine(today, datetime.min.time())
    end = datetime.combine(today, datetime.max.time())
    
    query = db.query(EconomicEvent).filter(
        EconomicEvent.event_time_utc >= start,
        EconomicEvent.event_time_utc <= end
    )
    
    if currencies:
        query = query.filter(EconomicEvent.currency.in_(currencies))
    
    return query.order_by(EconomicEvent.event_time_utc).all()


def get_danger_windows(db: Session, target_date: datetime.date = None) -> List[dict]:
    """
    Get danger windows around high-impact events.
    Returns list of {start, end, event} dicts.
    """
    if target_date is None:
        target_date = datetime.now().date()
    
    start = datetime.combine(target_date, datetime.min.time())
    end = datetime.combine(target_date, datetime.max.time())
    
    high_impact = db.query(EconomicEvent).filter(
        EconomicEvent.event_time_utc >= start,
        EconomicEvent.event_time_utc <= end,
        EconomicEvent.impact == "high",
        EconomicEvent.currency.in_(["USD", "EUR"])
    ).all()
    
    windows = []
    delta = timedelta(minutes=DANGER_WINDOW_MINUTES)
    
    for event in high_impact:
        windows.append({
            "start": event.event_time_utc - delta,
            "end": event.event_time_utc + delta,
            "event": event,
        })
    
    return windows
