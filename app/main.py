"""FastAPI application entry point."""

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path

from app.config import BASE_DIR, SCREENSHOTS_DIR
from app.database import init_db

# Initialize FastAPI app
app = FastAPI(
    title="Personal Advisor Portal",
    description="Daily trade planning for XAUUSD and EURUSD",
    version="0.1.0",
)

# Templates
templates = Jinja2Templates(directory=BASE_DIR / "app" / "templates")

# Mount static files for screenshots
app.mount("/screenshots", StaticFiles(directory=SCREENSHOTS_DIR), name="screenshots")


@app.on_event("startup")
async def startup_event():
    """Initialize database on startup."""
    init_db()


# Import and include routers
from app.routes import home, symbol, calendar, news, analyze, api

app.include_router(home.router)
app.include_router(symbol.router)
app.include_router(calendar.router)
app.include_router(news.router)
app.include_router(analyze.router)
app.include_router(api.router)  # API endpoints for n8n automation
