"""
Response File Watcher Service

Watches for JSON response files in the responses directory.
When a file is detected, it automatically processes it and generates reports.

This serves as a fallback when ChatGPT automation fails.
"""

import json
import os
import time
from datetime import date, datetime
from pathlib import Path
from typing import Callable, Optional
import logging

logger = logging.getLogger(__name__)

# Watch configuration
WATCH_FILE = "latest.json"
POLL_INTERVAL = 2  # seconds


def get_response_file_path() -> Path:
    """Get the path to the watched response file."""
    from app.config import RESPONSES_DIR
    return RESPONSES_DIR / WATCH_FILE


def check_for_new_response(last_modified: Optional[float] = None) -> Optional[dict]:
    """
    Check if a new response file exists.
    
    Args:
        last_modified: Previous modification time to compare against
        
    Returns:
        Parsed JSON data if new file detected, None otherwise
    """
    response_file = get_response_file_path()
    
    if not response_file.exists():
        return None
    
    current_mtime = response_file.stat().st_mtime
    
    # Check if file is new or modified
    if last_modified is not None and current_mtime <= last_modified:
        return None
    
    try:
        with open(response_file, "r") as f:
            content = f.read().strip()
        
        if not content:
            return None
        
        # Try to parse JSON
        data = json.loads(content)
        logger.info(f"New response detected: {response_file}")
        return data
        
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in response file: {e}")
        return None
    except Exception as e:
        logger.error(f"Error reading response file: {e}")
        return None


def save_response_for_processing(response_data: dict) -> str:
    """
    Save a response dict to the watched file location.
    This triggers the watcher to process it.
    
    Args:
        response_data: The JSON response data to save
        
    Returns:
        Path to the saved file
    """
    response_file = get_response_file_path()
    response_file.parent.mkdir(parents=True, exist_ok=True)
    
    with open(response_file, "w") as f:
        json.dump(response_data, f, indent=2)
    
    logger.info(f"Response saved to {response_file}")
    return str(response_file)


def archive_response(response_file: Path) -> Optional[str]:
    """
    Move processed response to dated archive file.
    
    Args:
        response_file: Path to the response file
        
    Returns:
        Path to archived file or None
    """
    if not response_file.exists():
        return None
    
    today = date.today().isoformat()
    timestamp = datetime.now().strftime("%H%M%S")
    archive_name = f"{today}_{timestamp}_response.json"
    archive_path = response_file.parent / archive_name
    
    try:
        response_file.rename(archive_path)
        logger.info(f"Archived response to {archive_path}")
        return str(archive_path)
    except Exception as e:
        logger.error(f"Failed to archive response: {e}")
        return None


def process_symbol_response(symbol: str, data: dict) -> bool:
    """
    Process analysis response for a single symbol.
    
    Args:
        symbol: The symbol (e.g., "XAUUSD")
        data: Parsed JSON response data for this symbol
        
    Returns:
        True if processing succeeded
    """
    from app.database import SessionLocal
    from app.agents.report_composer import compose_report
    from app.models import TASignal
    
    logger.info(f"Processing {symbol} response...")
    
    db = SessionLocal()
    today = date.today()
    
    try:
        symbol = symbol.upper()
        
        # Delete existing signal for today
        db.query(TASignal).filter(
            TASignal.date == today,
            TASignal.symbol == symbol,
            TASignal.timeframe.is_(None)
        ).delete()
        
        # Create new signal from response
        ta_signal = TASignal(
            date=today,
            symbol=symbol,
            timeframe=None,  # Aggregate signal
            bias=data.get("bias", "neutral"),
            confidence=data.get("confidence", 50),
            levels_json=data.get("levels"),
            ict_notes=data.get("ict_notes"),
            turtle_soup_json=data.get("turtle_soup"),
            trade_plan_json=data.get("trade_plan"),
        )
        db.add(ta_signal)
        db.commit()
        
        logger.info(f"Stored signal for {symbol}: {data.get('bias')} ({data.get('confidence')}%)")
        
        # Generate report for this symbol
        try:
            report = compose_report(db, today, symbol)
            if report:
                logger.info(f"Generated report for {symbol}")
            else:
                logger.warning(f"Could not generate report for {symbol}")
        except Exception as e:
            logger.error(f"Error generating report for {symbol}: {e}")
        
        return True
        
    except Exception as e:
        logger.error(f"Failed to process {symbol} response: {e}")
        return False
    finally:
        db.close()


def process_response_data(data: dict) -> bool:
    """
    Process the response data and generate reports.
    Handles both old multi-symbol format and new single-symbol format.
    
    Args:
        data: Parsed JSON response data
        
    Returns:
        True if processing succeeded
    """
    from app.database import SessionLocal
    from app.agents.response_parser import parse_cursor_response
    from app.agents.report_composer import compose_report
    from app.models import TASignal
    from app.config import SYMBOLS
    
    logger.info("Processing response data...")
    
    try:
        # Check if this is single-symbol format (new)
        if "symbol" in data and "bias" in data:
            symbol = data.get("symbol", "").upper()
            return process_symbol_response(symbol, data)
        
        # Otherwise, parse as multi-symbol format (old)
        parsed = parse_cursor_response(json.dumps(data))
        signals = parsed.get("signals", {})
        
        db = SessionLocal()
        today = date.today()
        
        try:
            # Store signals for each symbol
            for symbol, signal_data in signals.items():
                if symbol.upper() not in [s.upper() for s in SYMBOLS]:
                    logger.warning(f"Skipping unknown symbol: {symbol}")
                    continue
                
                symbol = symbol.upper()
                
                # Delete existing signal for today
                db.query(TASignal).filter(
                    TASignal.date == today,
                    TASignal.symbol == symbol,
                    TASignal.timeframe.is_(None)
                ).delete()
                
                # Create new signal
                ta_signal = TASignal(
                    date=today,
                    symbol=symbol,
                    timeframe=None,  # Aggregate signal
                    bias=signal_data.get("bias", "neutral"),
                    confidence=signal_data.get("confidence", 50),
                    levels_json=signal_data.get("levels"),
                    ict_notes=signal_data.get("ict_notes"),
                    turtle_soup_json=signal_data.get("turtle_soup"),
                )
                db.add(ta_signal)
                
                logger.info(f"Stored signal for {symbol}: {signal_data.get('bias')} ({signal_data.get('confidence')}%)")
            
            db.commit()
            
            # Generate reports for each symbol
            for symbol in SYMBOLS:
                try:
                    report = compose_report(db, today, symbol)
                    if report:
                        logger.info(f"Generated report for {symbol}")
                    else:
                        logger.warning(f"Could not generate report for {symbol}")
                except Exception as e:
                    logger.error(f"Error generating report for {symbol}: {e}")
            
            return True
            
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"Failed to process response: {e}")
        return False


def watch_for_response(
    timeout: int = 300,
    callback: Optional[Callable[[dict], bool]] = None
) -> Optional[dict]:
    """
    Watch for new response files and process them.
    
    Args:
        timeout: Maximum time to wait in seconds (default 5 minutes)
        callback: Optional callback function to process data (default: process_response_data)
        
    Returns:
        The processed response data, or None if timeout
    """
    if callback is None:
        callback = process_response_data
    
    response_file = get_response_file_path()
    start_time = time.time()
    
    # Get initial modification time if file exists
    initial_mtime = None
    if response_file.exists():
        initial_mtime = response_file.stat().st_mtime
    
    logger.info(f"Watching for response file: {response_file}")
    logger.info(f"Timeout: {timeout} seconds")
    print("\n" + "="*60)
    print(f"📁 Watching for response file...")
    print(f"   Save ChatGPT response to: {response_file}")
    print(f"   Timeout: {timeout // 60} minutes")
    print("="*60 + "\n")
    
    while time.time() - start_time < timeout:
        data = check_for_new_response(initial_mtime)
        
        if data:
            print("\n✅ Response detected! Processing...")
            
            # Process the response
            success = callback(data)
            
            if success:
                # Archive the processed file
                archive_response(response_file)
                print("✅ Response processed successfully!")
                return data
            else:
                print("❌ Failed to process response")
                return None
        
        # Show progress
        elapsed = int(time.time() - start_time)
        remaining = timeout - elapsed
        if elapsed % 30 == 0 and elapsed > 0:
            print(f"⏳ Still waiting... ({remaining}s remaining)")
        
        time.sleep(POLL_INTERVAL)
    
    print("\n⏰ Timeout - no response received")
    logger.warning("Response watcher timeout")
    return None


def clear_pending_response():
    """Clear any pending response file."""
    response_file = get_response_file_path()
    if response_file.exists():
        try:
            response_file.unlink()
            logger.info(f"Cleared pending response: {response_file}")
        except Exception as e:
            logger.error(f"Failed to clear response file: {e}")


# CLI helper for testing
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    print("Response Watcher Test")
    print("="*40)
    
    # Clear any existing file
    clear_pending_response()
    
    # Start watching (30 second timeout for testing)
    result = watch_for_response(timeout=30)
    
    if result:
        print(f"\nReceived: {json.dumps(result, indent=2)[:500]}...")
    else:
        print("\nNo response received")


