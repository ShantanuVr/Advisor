#!/usr/bin/env python3
"""CLI entry point for the Personal Advisor Portal."""

import asyncio
import click
from datetime import date

# Ensure app module is importable
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))


@click.group()
def cli():
    """Personal Advisor Portal - Daily trade planning for XAUUSD and EURUSD."""
    pass


@cli.command()
@click.option('--host', default='127.0.0.1', help='Host to bind to')
@click.option('--port', default=8000, help='Port to bind to')
@click.option('--reload', is_flag=True, help='Enable auto-reload')
def serve(host, port, reload):
    """Start the portal web server."""
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        reload=reload,
    )


@cli.command()
def prepare():
    """Run full daily data collection and prompt generation."""
    from app.database import SessionLocal
    from app.agents.snapshot_collector import import_screenshots
    from app.agents.fundamental import fetch_and_store_calendar
    from app.agents.news_collector import fetch_and_store_news
    from app.agents.prompt_generator import generate_prompt
    
    db = SessionLocal()
    
    try:
        click.echo("📸 Importing screenshots from inbox...")
        snap_results = import_screenshots(db)
        click.echo(f"   Imported: {snap_results['imported']}, Failed: {len(snap_results['failed'])}")
        for fail in snap_results['failed']:
            click.echo(f"   ⚠️  {fail['file']}: {fail['reason']}")
        
        click.echo("\n📅 Fetching economic calendar...")
        cal_results = asyncio.run(fetch_and_store_calendar(db))
        click.echo(f"   Fetched: {cal_results['fetched']}, Inserted: {cal_results['inserted']}, Updated: {cal_results['updated']}")
        
        click.echo("\n📰 Fetching news...")
        news_results = asyncio.run(fetch_and_store_news(db))
        click.echo(f"   Fetched: {news_results['fetched']}, Inserted: {news_results['inserted']}")
        
        click.echo("\n📝 Generating analysis prompt...")
        prompt_path = generate_prompt(db)
        click.echo(f"   Saved to: {prompt_path}")
        
        click.echo("\n✅ Preparation complete!")
        click.echo("\nNext steps:")
        click.echo(f"1. Open {prompt_path} in Cursor")
        click.echo("2. Drag in your TradingView screenshots")
        click.echo("3. Ask Claude to analyze and provide JSON output")
        click.echo("4. Paste the response at http://localhost:8000/analyze")
        
    finally:
        db.close()


@cli.command('import-snapshots')
def import_snapshots_cmd():
    """Import screenshots from the inbox folder."""
    from app.database import SessionLocal
    from app.agents.snapshot_collector import import_screenshots
    
    db = SessionLocal()
    try:
        click.echo("📸 Importing screenshots from inbox...")
        results = import_screenshots(db)
        click.echo(f"Imported: {results['imported']}")
        click.echo(f"Skipped: {results['skipped']}")
        if results['failed']:
            click.echo(f"Failed: {len(results['failed'])}")
            for fail in results['failed']:
                click.echo(f"  - {fail['file']}: {fail['reason']}")
    finally:
        db.close()


@cli.command('fetch-calendar')
def fetch_calendar_cmd():
    """Fetch ForexFactory economic calendar."""
    from app.database import SessionLocal
    from app.agents.fundamental import fetch_and_store_calendar
    
    db = SessionLocal()
    try:
        click.echo("📅 Fetching economic calendar...")
        results = asyncio.run(fetch_and_store_calendar(db))
        click.echo(f"Fetched: {results['fetched']}")
        click.echo(f"Inserted: {results['inserted']}")
        click.echo(f"Updated: {results['updated']}")
        if results['errors']:
            click.echo("Errors:")
            for err in results['errors']:
                click.echo(f"  - {err}")
    finally:
        db.close()


@cli.command('fetch-news')
@click.option('--historical', is_flag=True, help='Include historical FOMC statements')
def fetch_news_cmd(historical):
    """Fetch Fed/FOMC related news."""
    from app.database import SessionLocal
    from app.agents.news_collector import fetch_and_store_news
    
    db = SessionLocal()
    try:
        click.echo("📰 Fetching news...")
        if historical:
            click.echo("   Including historical FOMC statements...")
        results = asyncio.run(fetch_and_store_news(db, include_historical=historical))
        click.echo(f"Fetched: {results['fetched']}")
        click.echo(f"Inserted: {results['inserted']}")
        click.echo(f"Skipped (duplicates): {results['skipped']}")
        if results['errors']:
            click.echo("Errors:")
            for err in results['errors']:
                click.echo(f"  - {err}")
    finally:
        db.close()


@cli.command('fetch-fomc')
@click.option('--years', '-y', multiple=True, type=int, help='Years to fetch (default: current and previous)')
def fetch_fomc_cmd(years):
    """Fetch historical FOMC statements and meeting materials."""
    from app.database import SessionLocal
    from app.agents.news_collector import fetch_and_store_fomc_history
    
    db = SessionLocal()
    try:
        years_list = list(years) if years else None
        if years_list:
            click.echo(f"📜 Fetching FOMC statements for years: {', '.join(map(str, years_list))}")
        else:
            current_year = date.today().year
            click.echo(f"📜 Fetching FOMC statements for {current_year-1}-{current_year}...")
        
        results = asyncio.run(fetch_and_store_fomc_history(db, years=years_list))
        
        click.echo(f"\nFetched: {results['fetched']}")
        click.echo(f"Inserted: {results['inserted']}")
        click.echo(f"Skipped (duplicates): {results['skipped']}")
        
        if results['statements']:
            click.echo("\n📋 FOMC Statements Found:")
            for stmt in results['statements'][:10]:  # Show first 10
                stance_emoji = {"hawkish": "🔴", "dovish": "🟢", "neutral": "⚪"}.get(stmt['stance'], "⚪")
                click.echo(f"  {stmt['date']}: {stance_emoji} {stmt['title']} ({stmt['confidence']}%)")
            if len(results['statements']) > 10:
                click.echo(f"  ... and {len(results['statements']) - 10} more")
        
        if results['errors']:
            click.echo("\nErrors:")
            for err in results['errors']:
                click.echo(f"  - {err}")
    finally:
        db.close()


@cli.command('generate-prompt')
@click.option('--date', 'target_date', default=None, help='Date in YYYY-MM-DD format (default: today)')
def generate_prompt_cmd(target_date):
    """Generate the analysis prompt for Cursor."""
    from app.database import SessionLocal
    from app.agents.prompt_generator import generate_prompt
    
    if target_date:
        target_date = date.fromisoformat(target_date)
    
    db = SessionLocal()
    try:
        click.echo("📝 Generating analysis prompt...")
        prompt_path = generate_prompt(db, target_date)
        click.echo(f"Saved to: {prompt_path}")
        click.echo("\nOpen this file in Cursor and follow the instructions.")
    finally:
        db.close()


@cli.command('init-db')
def init_db_cmd():
    """Initialize the database tables."""
    from app.database import init_db
    click.echo("🗄️  Initializing database...")
    init_db()
    click.echo("Done!")


@cli.command('capture-screenshots')
@click.option('--symbols', '-s', default=None, help='Comma-separated symbols (default: XAUUSD,EURUSD)')
@click.option('--timeframes', '-t', default=None, help='Comma-separated timeframes (default: all)')
@click.option('--headless/--no-headless', default=True, help='Run browser headless (default: true)')
def capture_screenshots_cmd(symbols, timeframes, headless):
    """Capture TradingView screenshots using Playwright.
    
    Requires: pip install playwright && playwright install chromium
    """
    try:
        from app.agents.screenshot_service import capture_all_charts
        from app.config import SYMBOLS, TIMEFRAMES
    except ImportError as e:
        click.echo("❌ Playwright not installed. Run:")
        click.echo("   pip install playwright && playwright install chromium")
        return
    
    from app.database import SessionLocal
    from app.agents.snapshot_collector import import_screenshots
    
    symbol_list = symbols.split(",") if symbols else SYMBOLS
    timeframe_list = timeframes.split(",") if timeframes else TIMEFRAMES
    
    click.echo(f"📷 Capturing TradingView charts...")
    click.echo(f"   Symbols: {', '.join(symbol_list)}")
    click.echo(f"   Timeframes: {', '.join(timeframe_list)}")
    click.echo(f"   Headless: {headless}")
    
    results = asyncio.run(capture_all_charts(
        symbols=symbol_list,
        timeframes=timeframe_list,
        headless=headless,
    ))
    
    total = sum(len(paths) for paths in results.values())
    click.echo(f"\n✅ Captured {total} screenshots:")
    for symbol, paths in results.items():
        click.echo(f"   {symbol}: {len(paths)} charts")
    
    # Import to database
    db = SessionLocal()
    try:
        click.echo("\n📸 Importing to database...")
        import_results = import_screenshots(db)
        click.echo(f"   Imported: {import_results['imported']}")
    finally:
        db.close()


@cli.command('capture-symbol')
@click.argument('symbol', default='XAUUSD')
@click.option('--timeframes', '-t', default=None, help='Comma-separated timeframes (default: all)')
@click.option('--headless/--no-headless', default=True, help='Run browser headless')
def capture_symbol_cmd(symbol, timeframes, headless):
    """Capture TradingView screenshots for a single symbol.
    
    Example: python run.py capture-symbol XAUUSD --timeframes 1D,4H,1H
    """
    try:
        from app.agents.screenshot_service import capture_charts_for_symbol
        from app.config import TIMEFRAMES
    except ImportError:
        click.echo("❌ Playwright not installed. Run:")
        click.echo("   pip install playwright && playwright install chromium")
        return
    
    from app.database import SessionLocal
    from app.agents.snapshot_collector import import_screenshots
    
    timeframe_list = timeframes.split(",") if timeframes else TIMEFRAMES
    
    click.echo(f"📷 Capturing {symbol} charts...")
    click.echo(f"   Timeframes: {', '.join(timeframe_list)}")
    
    paths = asyncio.run(capture_charts_for_symbol(
        symbol=symbol,
        timeframes=timeframe_list,
        headless=headless,
    ))
    
    click.echo(f"\n✅ Captured {len(paths)} screenshots for {symbol}")
    for path in paths:
        click.echo(f"   {path}")
    
    # Import to database
    db = SessionLocal()
    try:
        import_results = import_screenshots(db)
        click.echo(f"\n📸 Imported: {import_results['imported']}")
    finally:
        db.close()


if __name__ == '__main__':
    cli()
