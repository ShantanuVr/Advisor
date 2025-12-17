"""API endpoints for n8n and external automation."""

import asyncio
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Snapshot, EconomicEvent, NewsItem, TASignal, DailyReport
from app.config import PROMPTS_DIR, SYMBOLS
from app.agents.snapshot_collector import import_screenshots
from app.agents.fundamental import fetch_and_store_calendar
from app.agents.news_collector import fetch_and_store_news, fetch_and_store_fomc_history
from app.agents.prompt_generator import generate_prompt

router = APIRouter(prefix="/api", tags=["API"])


def get_workflow_status(db: Session, target_date: date) -> dict:
    """Get current workflow status for a date."""
    today_start = datetime.combine(target_date, datetime.min.time())
    today_end = datetime.combine(target_date, datetime.max.time())
    
    screenshot_count = db.query(Snapshot).filter(
        Snapshot.captured_at >= today_start,
        Snapshot.captured_at <= today_end
    ).count()
    
    event_count = db.query(EconomicEvent).filter(
        EconomicEvent.event_time_utc >= today_start,
        EconomicEvent.event_time_utc <= today_end
    ).count()
    
    news_count = db.query(NewsItem).filter(
        NewsItem.published_at >= datetime.utcnow() - asyncio.timedelta(hours=48)
    ).count() if hasattr(asyncio, 'timedelta') else db.query(NewsItem).count()
    
    signal_count = db.query(TASignal).filter(TASignal.date == target_date).count()
    report_count = db.query(DailyReport).filter(DailyReport.date == target_date).count()
    
    prompt_exists = (PROMPTS_DIR / f"{target_date.isoformat()}_analysis.md").exists()
    
    return {
        "date": target_date.isoformat(),
        "screenshots": screenshot_count,
        "calendar_events": event_count,
        "news_items": news_count,
        "ta_signals": signal_count,
        "reports": report_count,
        "prompt_generated": prompt_exists,
        "workflow_complete": report_count >= len(SYMBOLS),
    }


@router.get("/status")
async def api_status(db: Session = Depends(get_db)):
    """
    Get today's workflow status.
    
    Returns the current state of data collection and analysis.
    """
    today = date.today()
    status = get_workflow_status(db, today)
    
    return JSONResponse(content={
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat(),
        **status
    })


@router.post("/prepare")
async def api_prepare(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    include_fomc: bool = False
):
    """
    Trigger the full prepare pipeline.
    
    This endpoint:
    1. Imports screenshots from inbox
    2. Fetches ForexFactory calendar
    3. Fetches Fed/FOMC news
    4. Generates today's analysis prompt
    
    Args:
        include_fomc: If true, also fetch historical FOMC statements
    
    Returns:
        Status and paths to generated files
    """
    results = {
        "status": "success",
        "timestamp": datetime.utcnow().isoformat(),
        "steps": {}
    }
    
    try:
        # Step 1: Import screenshots
        snap_results = import_screenshots(db)
        results["steps"]["screenshots"] = {
            "imported": snap_results["imported"],
            "failed": len(snap_results["failed"])
        }
        
        # Step 2: Fetch calendar
        cal_results = await fetch_and_store_calendar(db)
        results["steps"]["calendar"] = {
            "fetched": cal_results["fetched"],
            "inserted": cal_results["inserted"],
            "updated": cal_results["updated"]
        }
        
        # Step 3: Fetch news
        news_results = await fetch_and_store_news(db, include_historical=include_fomc)
        results["steps"]["news"] = {
            "fetched": news_results["fetched"],
            "inserted": news_results["inserted"]
        }
        
        # Step 4: Generate prompt
        prompt_path = generate_prompt(db)
        results["steps"]["prompt"] = {
            "path": prompt_path,
            "generated": True
        }
        
        results["prompt_path"] = prompt_path
        
    except Exception as e:
        results["status"] = "error"
        results["error"] = str(e)
        raise HTTPException(status_code=500, detail=str(e))
    
    return JSONResponse(content=results)


@router.post("/fetch-calendar")
async def api_fetch_calendar(db: Session = Depends(get_db)):
    """
    Fetch ForexFactory economic calendar.
    
    Fetches current and previous month's calendar data
    and upserts into the database.
    """
    try:
        results = await fetch_and_store_calendar(db)
        
        return JSONResponse(content={
            "status": "success",
            "timestamp": datetime.utcnow().isoformat(),
            "fetched": results["fetched"],
            "inserted": results["inserted"],
            "updated": results["updated"],
            "errors": results.get("errors", [])
        })
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/fetch-news")
async def api_fetch_news(
    db: Session = Depends(get_db),
    include_historical: bool = False
):
    """
    Fetch Fed/FOMC related news.
    
    Args:
        include_historical: If true, also fetch historical FOMC statements
    """
    try:
        results = await fetch_and_store_news(db, include_historical=include_historical)
        
        return JSONResponse(content={
            "status": "success",
            "timestamp": datetime.utcnow().isoformat(),
            "fetched": results["fetched"],
            "inserted": results["inserted"],
            "skipped": results["skipped"],
            "errors": results.get("errors", [])
        })
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/fetch-fomc")
async def api_fetch_fomc(
    db: Session = Depends(get_db),
    years: Optional[str] = None
):
    """
    Fetch historical FOMC statements.
    
    Args:
        years: Comma-separated list of years (e.g., "2024,2025")
               Default: current and previous year
    """
    try:
        years_list = None
        if years:
            years_list = [int(y.strip()) for y in years.split(",")]
        
        results = await fetch_and_store_fomc_history(db, years=years_list)
        
        return JSONResponse(content={
            "status": "success",
            "timestamp": datetime.utcnow().isoformat(),
            "fetched": results["fetched"],
            "inserted": results["inserted"],
            "skipped": results["skipped"],
            "statements_found": len(results.get("statements", [])),
            "errors": results.get("errors", [])
        })
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/generate-prompt")
async def api_generate_prompt(
    db: Session = Depends(get_db),
    target_date: Optional[str] = None
):
    """
    Generate the analysis prompt for Cursor.
    
    Args:
        target_date: Date in YYYY-MM-DD format (default: today)
    """
    try:
        if target_date:
            dt = date.fromisoformat(target_date)
        else:
            dt = date.today()
        
        prompt_path = generate_prompt(db, dt)
        
        return JSONResponse(content={
            "status": "success",
            "timestamp": datetime.utcnow().isoformat(),
            "date": dt.isoformat(),
            "prompt_path": prompt_path
        })
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/import-screenshots")
async def api_import_screenshots(db: Session = Depends(get_db)):
    """
    Import screenshots from the inbox folder.
    
    Processes all images in /data/inbox/ and moves them
    to /data/screenshots/ with proper metadata.
    """
    try:
        results = import_screenshots(db)
        
        return JSONResponse(content={
            "status": "success",
            "timestamp": datetime.utcnow().isoformat(),
            "imported": results["imported"],
            "skipped": results.get("skipped", 0),
            "failed": [
                {"file": f["file"], "reason": f["reason"]}
                for f in results["failed"]
            ]
        })
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def api_health():
    """
    Health check endpoint for Docker/n8n.
    """
    return JSONResponse(content={
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "service": "advisor-portal"
    })
