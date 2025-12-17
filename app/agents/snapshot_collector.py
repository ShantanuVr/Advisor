"""Snapshot collector - imports TradingView screenshots from inbox."""

import re
import shutil
from datetime import datetime, date
from pathlib import Path
from typing import Optional, Tuple

from sqlalchemy.orm import Session

from app.models import Snapshot
from app.config import INBOX_DIR, SCREENSHOTS_DIR, SYMBOLS, TIMEFRAMES


def parse_filename(filename: str) -> Optional[Tuple[str, str, date]]:
    """
    Parse screenshot filename to extract symbol, timeframe, and date.
    
    Expected formats:
    - XAUUSD_1H_2025-12-17.png
    - EURUSD_4H_2025-12-17.jpg
    - xauusd-1d-2025-12-17.png (flexible separators)
    
    Returns (symbol, timeframe, date) or None if unparseable.
    """
    # Remove extension
    stem = Path(filename).stem.upper()
    
    # Try different patterns
    patterns = [
        # Standard: SYMBOL_TF_DATE
        r'^([A-Z]+)[_\-](\d+[WDHM])[_\-](\d{4}-\d{2}-\d{2})$',
        # Without date: SYMBOL_TF (use today)
        r'^([A-Z]+)[_\-](\d+[WDHM])$',
    ]
    
    for pattern in patterns:
        match = re.match(pattern, stem)
        if match:
            groups = match.groups()
            symbol = groups[0]
            timeframe = groups[1]
            
            # Validate symbol and timeframe
            if symbol not in SYMBOLS:
                continue
            if timeframe not in TIMEFRAMES:
                continue
            
            # Parse date if present, otherwise use today
            if len(groups) > 2:
                try:
                    capture_date = datetime.strptime(groups[2], "%Y-%m-%d").date()
                except ValueError:
                    capture_date = date.today()
            else:
                capture_date = date.today()
            
            return (symbol, timeframe, capture_date)
    
    return None


def import_screenshots(db: Session) -> dict:
    """
    Import all screenshots from inbox directory.
    
    Returns dict with counts of imported, skipped, and failed.
    """
    results = {
        "imported": 0,
        "skipped": 0,
        "failed": [],
    }
    
    # Supported image extensions
    extensions = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
    
    # Get all image files in inbox
    inbox_files = [f for f in INBOX_DIR.iterdir() 
                   if f.is_file() and f.suffix.lower() in extensions]
    
    for file_path in inbox_files:
        parsed = parse_filename(file_path.name)
        
        if parsed is None:
            results["failed"].append({
                "file": file_path.name,
                "reason": "Could not parse filename. Expected format: SYMBOL_TIMEFRAME_DATE.png"
            })
            continue
        
        symbol, timeframe, capture_date = parsed
        
        # Generate standardized filename
        timestamp = datetime.now().strftime("%H%M%S")
        new_filename = f"{symbol}_{timeframe}_{capture_date.isoformat()}_{timestamp}{file_path.suffix.lower()}"
        dest_path = SCREENSHOTS_DIR / new_filename
        
        # Move file
        try:
            shutil.move(str(file_path), str(dest_path))
        except Exception as e:
            results["failed"].append({
                "file": file_path.name,
                "reason": f"Failed to move file: {e}"
            })
            continue
        
        # Create database record
        snapshot = Snapshot(
            symbol=symbol,
            timeframe=timeframe,
            captured_at=datetime.combine(capture_date, datetime.now().time()),
            file_path=str(dest_path.relative_to(SCREENSHOTS_DIR.parent.parent)),
        )
        db.add(snapshot)
        results["imported"] += 1
    
    db.commit()
    return results


def get_snapshots_for_date(db: Session, target_date: date, symbol: Optional[str] = None) -> list:
    """Get all snapshots for a given date, optionally filtered by symbol."""
    query = db.query(Snapshot).filter(
        Snapshot.captured_at >= datetime.combine(target_date, datetime.min.time()),
        Snapshot.captured_at < datetime.combine(target_date, datetime.max.time())
    )
    
    if symbol:
        query = query.filter(Snapshot.symbol == symbol)
    
    return query.order_by(Snapshot.symbol, Snapshot.timeframe).all()
