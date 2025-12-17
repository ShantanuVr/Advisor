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


@cli.command('analyze')
@click.option('--headless/--no-headless', default=False, help='Run ChatGPT browser headless')
@click.option('--auto-open/--no-auto-open', default=True, help='Auto-open portal in browser')
@click.option('--skip-screenshots', is_flag=True, help='Skip screenshot capture (use existing)')
@click.option('--manual', is_flag=True, help='Skip ChatGPT automation, use file watcher')
@click.option('--symbol', '-s', default=None, help='Analyze single symbol only')
def analyze_cmd(headless, auto_open, skip_screenshots, manual, symbol):
    """
    Full end-to-end analysis workflow.
    
    This command analyzes ONE SYMBOL AT A TIME (ChatGPT 10-file limit).
    It will run analysis for each symbol sequentially:
    
    1. Fetches calendar + news data (once)
    2. For each symbol:
       - Captures 6 screenshots
       - Generates symbol-specific prompt
       - Submits to ChatGPT
       - Processes response
    3. Opens portal with all results
    
    Example: python run.py analyze
    """
    import webbrowser
    import glob
    from datetime import datetime
    from app.database import SessionLocal
    from app.config import SYMBOLS, TIMEFRAMES, SCREENSHOTS_DIR, HOST, PORT
    
    # Determine which symbols to analyze
    symbols_to_analyze = [symbol.upper()] if symbol else SYMBOLS
    
    click.echo("\n" + "="*60)
    click.echo("🚀 FULL ANALYSIS WORKFLOW")
    click.echo(f"   Symbols: {', '.join(symbols_to_analyze)}")
    click.echo(f"   Mode: {'Manual' if manual else 'ChatGPT Automation'}")
    click.echo("="*60 + "\n")
    
    db = SessionLocal()
    all_responses = {}
    
    try:
        # Step 1: Fetch calendar data (once for all symbols)
        click.echo("📅 Step 1: Fetching economic calendar...")
        from app.agents.fundamental import fetch_and_store_calendar
        cal_results = asyncio.run(fetch_and_store_calendar(db))
        click.echo(f"   ✓ Fetched {cal_results['fetched']} events")
        
        # Step 2: Fetch news data (once for all symbols)
        click.echo("\n📰 Step 2: Fetching Fed/FOMC news...")
        from app.agents.news_collector import fetch_and_store_news
        news_results = asyncio.run(fetch_and_store_news(db))
        click.echo(f"   ✓ Fetched {news_results['fetched']} news items")
        
        # Step 3: Process each symbol
        for idx, current_symbol in enumerate(symbols_to_analyze, 1):
            click.echo("\n" + "-"*60)
            click.echo(f"📊 ANALYZING {current_symbol} ({idx}/{len(symbols_to_analyze)})")
            click.echo("-"*60)
            
            # 3a: Capture screenshots for this symbol
            symbol_screenshots = []
            if not skip_screenshots:
                click.echo(f"\n   📷 Capturing {current_symbol} screenshots...")
                try:
                    from app.agents.screenshot_service import capture_charts_for_symbol
                    from app.agents.snapshot_collector import import_screenshots
                    
                    paths = asyncio.run(capture_charts_for_symbol(
                        symbol=current_symbol,
                        timeframes=TIMEFRAMES,
                        headless=True,
                        clear_old=(idx == 1),  # Only clear on first symbol
                    ))
                    
                    symbol_screenshots = paths
                    click.echo(f"   ✓ Captured {len(paths)} screenshots")
                    
                    # Import to database
                    import_screenshots(db)
                    
                except ImportError:
                    click.echo("   ⚠️  Playwright not installed")
            else:
                click.echo(f"\n   📷 Using existing {current_symbol} screenshots...")
                pattern = str(SCREENSHOTS_DIR / f"{current_symbol}_*.png")
                symbol_screenshots = sorted(glob.glob(pattern))
                click.echo(f"   ✓ Found {len(symbol_screenshots)} screenshots")
            
            # 3b: Generate symbol-specific prompt
            click.echo(f"\n   📝 Generating {current_symbol} prompt...")
            from app.agents.prompt_generator import generate_symbol_prompt
            
            # Include context only for first symbol
            prompt_path = generate_symbol_prompt(
                db, 
                current_symbol, 
                include_context=(idx == 1)
            )
            click.echo(f"   ✓ Saved to: {prompt_path}")
            
            # Read prompt content
            with open(prompt_path, "r") as f:
                prompt_text = f.read()
            
            # 3c: Get AI analysis for this symbol
            click.echo(f"\n   🤖 Getting {current_symbol} analysis...")
            
            symbol_response = None
            use_manual = manual
            
            if not use_manual:
                try:
                    from app.agents.chatgpt_service import analyze_with_chatgpt
                    
                    click.echo("      Submitting to ChatGPT...")
                    click.echo(f"      (Uploading {len(symbol_screenshots)} images)")
                    
                    success, parsed_json, raw_response = asyncio.run(
                        analyze_with_chatgpt(
                            prompt_text=prompt_text,
                            screenshot_paths=symbol_screenshots[:6],  # Max 6 per symbol
                            headless=headless,
                            timeout=0  # No timeout - ChatGPT thinking mode can take time
                        )
                    )
                    
                    if success and parsed_json:
                        click.echo(f"   ✓ {current_symbol} analysis complete!")
                        symbol_response = parsed_json
                        all_responses[current_symbol] = symbol_response
                    else:
                        click.echo("   ⚠️  ChatGPT automation incomplete")
                        if raw_response:
                            from app.config import RESPONSES_DIR
                            raw_file = RESPONSES_DIR / f"{date.today().isoformat()}_{current_symbol}_raw.txt"
                            with open(raw_file, "w") as f:
                                f.write(raw_response)
                            click.echo(f"      Raw response saved to: {raw_file}")
                        use_manual = True
                        
                except ImportError:
                    click.echo("   ⚠️  ChatGPT service not available")
                    use_manual = True
                except Exception as e:
                    click.echo(f"   ⚠️  ChatGPT failed: {e}")
                    use_manual = True
            
            if use_manual and not symbol_response:
                # Manual mode for this symbol
                click.echo(f"\n   📝 Manual mode for {current_symbol}...")
                from app.agents.response_watcher import get_response_file_path
                from app.config import RESPONSES_DIR
                
                # Use symbol-specific response file
                response_file = RESPONSES_DIR / f"{current_symbol}_response.json"
                click.echo(f"\n   📁 Save {current_symbol} response to:")
                click.echo(f"      {response_file}")
                click.echo(f"\n   Copy from ChatGPT and save, then press Enter...")
                
                # Open prompt for reference
                try:
                    import subprocess
                    import platform
                    if platform.system() == "Darwin":
                        subprocess.run(["open", prompt_path])
                except Exception:
                    pass
                
                # Wait for user
                input("   Press Enter when response is saved...")
                
                # Try to read the response
                if response_file.exists():
                    try:
                        import json
                        with open(response_file, "r") as f:
                            symbol_response = json.load(f)
                        click.echo(f"   ✓ Loaded {current_symbol} response")
                        all_responses[current_symbol] = symbol_response
                    except Exception as e:
                        click.echo(f"   ⚠️  Error loading response: {e}")
            
            # 3d: Process this symbol's response
            if symbol_response:
                click.echo(f"\n   📊 Processing {current_symbol} results...")
                from app.agents.response_watcher import process_symbol_response
                
                if process_symbol_response(current_symbol, symbol_response):
                    click.echo(f"   ✓ {current_symbol} report generated!")
                else:
                    click.echo(f"   ⚠️  Issues processing {current_symbol}")
        
        # Step 4: Summary and open portal
        click.echo("\n" + "="*60)
        click.echo("📋 ANALYSIS SUMMARY")
        click.echo("="*60)
        
        for sym in symbols_to_analyze:
            if sym in all_responses:
                resp = all_responses[sym]
                bias = resp.get("bias", "unknown")
                conf = resp.get("confidence", 0)
                click.echo(f"   {sym}: {bias.upper()} ({conf}% confidence)")
            else:
                click.echo(f"   {sym}: ⚠️  No response")
        
        # Open portal
        if auto_open:
            click.echo(f"\n🌐 Opening portal...")
            url = f"http://{HOST}:{PORT}/"
            click.echo(f"   {url}")
            webbrowser.open(url)
        
        click.echo("\n" + "="*60)
        click.echo("✅ ANALYSIS WORKFLOW COMPLETE")
        click.echo("="*60 + "\n")
        
    except Exception as e:
        click.echo(f"\n❌ Error: {e}")
        raise
    finally:
        db.close()


@cli.command('reanalyze')
@click.option('--headless/--no-headless', default=False, help='Run ChatGPT browser headless')
@click.option('--auto-open/--no-auto-open', default=True, help='Auto-open portal in browser')
@click.pass_context
def reanalyze_cmd(ctx, headless, auto_open):
    """
    Clear today's data and run fresh analysis.
    
    This command:
    1. Clears today's screenshots, signals, and reports
    2. Runs the full analyze workflow
    
    Example: python run.py reanalyze
    """
    from datetime import datetime
    from app.database import SessionLocal
    from app.models import Snapshot, TASignal, DailyReport
    from app.config import SCREENSHOTS_DIR
    from app.agents.screenshot_service import clear_old_screenshots
    from app.agents.response_watcher import clear_pending_response
    import glob
    
    today = date.today()
    
    click.echo("\n" + "="*60)
    click.echo("🔄 REANALYZE - Clearing old data and starting fresh")
    click.echo("="*60 + "\n")
    
    db = SessionLocal()
    
    try:
        # Clear today's signals
        click.echo("🗑️  Clearing today's signals...")
        deleted_signals = db.query(TASignal).filter(TASignal.date == today).delete()
        click.echo(f"   ✓ Deleted {deleted_signals} signals")
        
        # Clear today's reports
        click.echo("🗑️  Clearing today's reports...")
        deleted_reports = db.query(DailyReport).filter(DailyReport.date == today).delete()
        click.echo(f"   ✓ Deleted {deleted_reports} reports")
        
        # Clear today's snapshots from database
        click.echo("🗑️  Clearing today's snapshots...")
        today_start = datetime.combine(today, datetime.min.time())
        today_end = datetime.combine(today, datetime.max.time())
        deleted_snaps = db.query(Snapshot).filter(
            Snapshot.captured_at >= today_start,
            Snapshot.captured_at <= today_end
        ).delete()
        click.echo(f"   ✓ Deleted {deleted_snaps} snapshot records")
        
        db.commit()
        
        # Clear screenshot files
        click.echo("🗑️  Clearing screenshot files...")
        deleted_files = clear_old_screenshots()
        total_files = sum(deleted_files.values())
        click.echo(f"   ✓ Deleted {total_files} files")
        
        # Clear pending response file
        click.echo("🗑️  Clearing pending response...")
        clear_pending_response()
        click.echo("   ✓ Done")
        
    finally:
        db.close()
    
    click.echo("\n" + "-"*60 + "\n")
    
    # Now run the full analyze workflow
    ctx.invoke(analyze_cmd, headless=headless, auto_open=auto_open, skip_screenshots=False, manual=False)


@cli.command('watch-responses')
@click.option('--timeout', default=600, help='Timeout in seconds (default: 600)')
def watch_responses_cmd(timeout):
    """
    Watch for response files and auto-process them.
    
    This is useful as a fallback when ChatGPT automation fails.
    Save your ChatGPT response to data/responses/latest.json
    
    Example: python run.py watch-responses
    """
    from app.agents.response_watcher import watch_for_response
    
    click.echo("\n" + "="*60)
    click.echo("👁️  RESPONSE WATCHER")
    click.echo("="*60 + "\n")
    
    result = watch_for_response(timeout=timeout)
    
    if result:
        click.echo("\n✅ Response processed successfully!")
    else:
        click.echo("\n⏰ No response received within timeout")


if __name__ == '__main__':
    cli()
