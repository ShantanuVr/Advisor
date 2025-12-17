"""News page route - Fed/FOMC related news."""

from datetime import datetime, timedelta
from fastapi import APIRouter, Request, Depends
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import NewsItem
from app.config import BASE_DIR

router = APIRouter()
templates = Jinja2Templates(directory=BASE_DIR / "app" / "templates")


@router.get("/news")
async def news_view(request: Request, db: Session = Depends(get_db)):
    """Render news page with last 48h of Fed-related news."""
    cutoff = datetime.utcnow() - timedelta(hours=48)
    
    news_items = db.query(NewsItem).filter(
        NewsItem.published_at >= cutoff
    ).order_by(NewsItem.published_at.desc()).all()
    
    # Group by stance for summary
    stance_counts = {"hawkish": 0, "dovish": 0, "neutral": 0, "risk_on": 0, "risk_off": 0}
    for item in news_items:
        if item.stance and item.stance in stance_counts:
            stance_counts[item.stance] += 1
    
    return templates.TemplateResponse("news.html", {
        "request": request,
        "news_items": news_items,
        "stance_counts": stance_counts,
        "cutoff": cutoff,
    })
