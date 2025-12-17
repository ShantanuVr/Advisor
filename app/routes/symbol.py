"""Symbol detail page route."""

from datetime import date, datetime, timedelta
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import DailyReport, Snapshot, TASignal
from app.config import BASE_DIR, SYMBOLS, TIMEFRAMES

router = APIRouter()
templates = Jinja2Templates(directory=BASE_DIR / "app" / "templates")


@router.get("/symbol/{symbol}")
async def symbol_detail(symbol: str, request: Request, db: Session = Depends(get_db)):
    """Render symbol detail page with full breakdown."""
    symbol = symbol.upper()
    if symbol not in SYMBOLS:
        raise HTTPException(status_code=404, detail=f"Symbol {symbol} not found")
    
    today = date.today()
    today_start = datetime.combine(today, datetime.min.time())
    today_end = datetime.combine(today, datetime.max.time())
    
    # Get today's report
    report = db.query(DailyReport).filter(
        DailyReport.date == today,
        DailyReport.symbol == symbol
    ).first()
    
    # Get today's screenshots for this symbol
    screenshots = db.query(Snapshot).filter(
        Snapshot.symbol == symbol,
        Snapshot.captured_at >= today_start,
        Snapshot.captured_at <= today_end
    ).order_by(Snapshot.timeframe).all()
    
    # Organize screenshots by timeframe
    screenshots_by_tf = {tf: None for tf in TIMEFRAMES}
    for snap in screenshots:
        if snap.timeframe in screenshots_by_tf:
            screenshots_by_tf[snap.timeframe] = snap
    
    # Get today's TA signals
    ta_signals = db.query(TASignal).filter(
        TASignal.date == today,
        TASignal.symbol == symbol
    ).all()
    
    # Get aggregate signal (timeframe=NULL)
    aggregate_signal = next((s for s in ta_signals if s.timeframe is None), None)
    
    return templates.TemplateResponse("symbol.html", {
        "request": request,
        "symbol": symbol,
        "today": today,
        "report": report,
        "screenshots": screenshots,
        "screenshots_by_tf": screenshots_by_tf,
        "timeframes": TIMEFRAMES,
        "ta_signals": ta_signals,
        "aggregate_signal": aggregate_signal,
    })
