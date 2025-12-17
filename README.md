# Personal Advisor Portal

A local-first trading advisor that generates daily trade plans for **XAUUSD** and **EURUSD** by combining:

- 📸 TradingView chart screenshots (multi-timeframe)
- 📅 ForexFactory economic calendar
- 📰 Fed/FOMC news sentiment
- 🐢 ICT concepts & Turtle Soup pattern analysis

## Quick Start

```bash
# 1. Setup (creates venv, installs deps, runs migrations)
make setup

# 2. Activate virtual environment
source venv/bin/activate

# 3. Start the portal
make run
# → Opens at http://localhost:8000
```

## Daily Workflow

```
Morning routine (~5 minutes):

1. Take TradingView screenshots and drop them in /data/inbox/
   Filename format: XAUUSD_1H_2024-12-17.png

2. Run data collection:
   make prepare

3. Open the generated prompt in Cursor:
   /data/prompts/2024-12-17_analysis.md

4. Drag screenshots into Cursor chat, ask Claude to analyze

5. Copy Claude's JSON response

6. Paste at http://localhost:8000/analyze

7. View your trade plan at http://localhost:8000
```

## Screenshot Naming Convention

```
{SYMBOL}_{TIMEFRAME}_{DATE}.png

Examples:
- XAUUSD_1W_2024-12-17.png
- XAUUSD_1D_2024-12-17.png
- XAUUSD_4H_2024-12-17.png
- EURUSD_1H_2024-12-17.png
```

Supported timeframes: `1W`, `1D`, `4H`, `1H`, `15M`, `5M`

## CLI Commands

```bash
# Start web server
python run.py serve

# Full daily preparation (screenshots + calendar + news + prompt)
python run.py prepare

# Individual commands
python run.py import-snapshots   # Process inbox
python run.py fetch-calendar     # Update ForexFactory data
python run.py fetch-news         # Fetch Fed/FOMC news
python run.py generate-prompt    # Create analysis prompt
python run.py init-db            # Initialize database
```

## Project Structure

```
/Advisor
├── run.py                    # CLI entry point
├── Makefile                  # Shortcuts
├── data/
│   ├── inbox/               # Drop screenshots here
│   ├── screenshots/         # Processed screenshots
│   ├── prompts/             # Generated analysis prompts
│   ├── responses/           # Your Cursor responses
│   ├── reports/             # Final JSON reports
│   └── advisor.db           # SQLite database
└── app/
    ├── main.py              # FastAPI app
    ├── agents/              # Business logic
    ├── routes/              # Web routes
    └── templates/           # Jinja2 templates
```

## Configuration

Edit `.env` to customize:

```bash
TIMEZONE=America/New_York
DATA_DIR=./data
NEWS_SOURCES=fed_official,reuters
DANGER_WINDOW_MINUTES=30
HOST=127.0.0.1
PORT=8000
```

## Tech Stack

- **Backend**: Python 3.11+, FastAPI
- **Database**: SQLite + SQLAlchemy
- **UI**: Jinja2 + Tailwind CSS
- **LLM**: Cursor-in-the-loop (no API keys needed!)

## License

Personal use only. Not for production or redistribution.
