"""Application configuration loaded from environment variables."""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file
load_dotenv()

# Base paths
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("DATA_DIR", "./data"))
if not DATA_DIR.is_absolute():
    DATA_DIR = BASE_DIR / DATA_DIR

# Data subdirectories
INBOX_DIR = DATA_DIR / "inbox"
SCREENSHOTS_DIR = DATA_DIR / "screenshots"
PROMPTS_DIR = DATA_DIR / "prompts"
RESPONSES_DIR = DATA_DIR / "responses"
REPORTS_DIR = DATA_DIR / "reports"

# Database
DATABASE_URL = f"sqlite:///{DATA_DIR / 'advisor.db'}"
DATABASE_PATH = DATA_DIR / "advisor.db"

# Timezone
TIMEZONE = os.getenv("TIMEZONE", "America/New_York")

# News sources
NEWS_SOURCES = os.getenv("NEWS_SOURCES", "fed_official,reuters").split(",")

# Danger window around high-impact events (minutes before and after)
DANGER_WINDOW_MINUTES = int(os.getenv("DANGER_WINDOW_MINUTES", "30"))

# Server settings
HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8000"))

# Supported symbols and timeframes
SYMBOLS = ["XAUUSD", "EURUSD"]
TIMEFRAMES = ["1W", "1D", "4H", "1H", "15M", "5M"]

# Ensure data directories exist
for dir_path in [INBOX_DIR, SCREENSHOTS_DIR, PROMPTS_DIR, RESPONSES_DIR, REPORTS_DIR]:
    dir_path.mkdir(parents=True, exist_ok=True)
