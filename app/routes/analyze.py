"""Analysis workflow page - paste Cursor response here."""

import json
from datetime import date, datetime
from fastapi import APIRouter, Request, Depends, Form
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import TASignal, DailyReport, Snapshot
from app.config import BASE_DIR, PROMPTS_DIR, SYMBOLS
from app.agents.response_parser import parse_cursor_response
from app.agents.report_composer import compose_report

router = APIRouter()
templates = Jinja2Templates(directory=BASE_DIR / "app" / "templates")


def get_todays_prompt_path() -> str:
    """Get path to today's prompt file."""
    today = date.today()
    prompt_file = PROMPTS_DIR / f"{today.isoformat()}_analysis.md"
    return str(prompt_file)


def check_prompt_exists() -> bool:
    """Check if today's prompt file exists."""
    from pathlib import Path
    return Path(get_todays_prompt_path()).exists()


@router.get("/analyze")
async def analyze_page(request: Request, db: Session = Depends(get_db)):
    """Render the analysis workflow page."""
    today = date.today()
    prompt_path = get_todays_prompt_path()
    prompt_exists = check_prompt_exists()
    
    # Check if we already have analysis for today
    existing_signals = db.query(TASignal).filter(TASignal.date == today).count()
    existing_reports = db.query(DailyReport).filter(DailyReport.date == today).count()
    
    # Read prompt content if exists
    prompt_content = None
    if prompt_exists:
        with open(prompt_path, "r") as f:
            prompt_content = f.read()
    
    return templates.TemplateResponse("analyze.html", {
        "request": request,
        "today": today,
        "prompt_path": prompt_path,
        "prompt_exists": prompt_exists,
        "prompt_content": prompt_content,
        "existing_signals": existing_signals,
        "existing_reports": existing_reports,
        "symbols": SYMBOLS,
        "error": request.query_params.get("error"),
        "success": request.query_params.get("success"),
    })


@router.post("/analyze")
async def submit_analysis(
    request: Request,
    response_json: str = Form(...),
    db: Session = Depends(get_db)
):
    """Process submitted Cursor analysis response."""
    today = date.today()
    
    try:
        # Parse the response
        parsed = parse_cursor_response(response_json)
        
        # Store TA signals
        for symbol, signal_data in parsed.get("signals", {}).items():
            # Delete existing signals for today/symbol
            db.query(TASignal).filter(
                TASignal.date == today,
                TASignal.symbol == symbol
            ).delete()
            
            # Create new signal
            signal = TASignal(
                date=today,
                symbol=symbol,
                timeframe=None,  # Aggregate signal
                bias=signal_data.get("bias", "neutral"),
                confidence=signal_data.get("confidence", 50),
                levels_json=signal_data.get("levels"),
                ict_notes=signal_data.get("ict_notes"),
                turtle_soup_json=signal_data.get("turtle_soup"),
            )
            db.add(signal)
        
        db.commit()
        
        # Generate reports
        for symbol in SYMBOLS:
            if symbol in parsed.get("signals", {}):
                compose_report(db, today, symbol)
        
        return RedirectResponse(
            url="/analyze?success=Analysis+saved+successfully",
            status_code=303
        )
        
    except json.JSONDecodeError as e:
        return RedirectResponse(
            url=f"/analyze?error=Invalid+JSON:+{str(e)}",
            status_code=303
        )
    except Exception as e:
        return RedirectResponse(
            url=f"/analyze?error={str(e)}",
            status_code=303
        )
