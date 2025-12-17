"""Prompt generator - creates analysis prompts for Cursor."""

from datetime import date, datetime
from pathlib import Path
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models import Snapshot, EconomicEvent, NewsItem
from app.config import PROMPTS_DIR, SYMBOLS, TIMEFRAMES, SCREENSHOTS_DIR
from app.agents.snapshot_collector import get_snapshots_for_date
from app.agents.fundamental import get_todays_events, get_danger_windows
from app.agents.news_collector import get_recent_news, get_fomc_related_news, get_all_recent_news


def generate_symbol_prompt(
    db: Session, 
    symbol: str,
    target_date: date = None,
    include_context: bool = True
) -> str:
    """
    Generate an analysis prompt for a single symbol.
    Returns the path to the generated file.
    
    Args:
        db: Database session
        symbol: Symbol to analyze (e.g., "XAUUSD")
        target_date: Date for analysis (default: today)
        include_context: Include calendar/news context (set False for second symbol)
    """
    if target_date is None:
        target_date = date.today()
    
    # Collect data
    snapshots = get_snapshots_for_date(db, target_date)
    
    # Filter snapshots for this symbol only
    symbol_snapshots = {
        snap.timeframe: snap 
        for snap in snapshots 
        if snap.symbol.upper() == symbol.upper()
    }
    
    # Build the prompt
    lines = []
    lines.append(f"# {symbol} Analysis Request - {target_date.isoformat()}")
    lines.append("")
    lines.append("## Instructions")
    lines.append("")
    lines.append(f"Please analyze the attached TradingView screenshots for **{symbol}** using ICT concepts and the Turtle Soup pattern.")
    lines.append("Provide your analysis in the JSON format specified at the end of this document.")
    lines.append("")
    
    # Screenshots section (single symbol - max 6 files)
    lines.append("## Screenshots to Analyze")
    lines.append("")
    lines.append(f"### {symbol} (6 timeframes)")
    
    if not symbol_snapshots:
        lines.append("- **No screenshots found** - please capture charts first")
    else:
        for tf in TIMEFRAMES:
            if tf in symbol_snapshots:
                snap = symbol_snapshots[tf]
                abs_path = SCREENSHOTS_DIR / Path(snap.file_path).name
                lines.append(f"- {tf}: `{abs_path}`")
            else:
                lines.append(f"- {tf}: **Missing**")
    lines.append("")
    
    # Only include context for first symbol to save space
    if include_context:
        # Economic calendar section
        events = get_todays_events(db, currencies=["USD", "EUR"])
        danger_windows = get_danger_windows(db, target_date)
        
        lines.append("## Today's Economic Calendar (USD/EUR)")
        lines.append("")
        
        if events:
            high_impact = [e for e in events if e.impact == "high"]
            
            if high_impact:
                lines.append("### High Impact Events ⚠️")
                lines.append("")
                lines.append("| Time (UTC) | Currency | Event | Forecast | Previous |")
                lines.append("|------------|----------|-------|----------|----------|")
                for event in high_impact:
                    time_str = event.event_time_utc.strftime("%H:%M")
                    lines.append(f"| {time_str} | {event.currency} | {event.title} | {event.forecast or '-'} | {event.previous or '-'} |")
                lines.append("")
        else:
            lines.append("No high-impact USD/EUR events scheduled for today.")
            lines.append("")
        
        # Danger windows
        if danger_windows:
            lines.append("### Danger Windows (±30 min around high-impact events)")
            lines.append("")
            for window in danger_windows:
                start = window["start"].strftime("%H:%M")
                end = window["end"].strftime("%H:%M")
                lines.append(f"- {start} - {end} UTC: {window['event'].title}")
            lines.append("")
        
        # Recent FOMC
        fomc_news = get_fomc_related_news(db, days=60)
        if fomc_news:
            lines.append("## Recent FOMC Context")
            lines.append("")
            for item in fomc_news[:5]:  # Top 5 only
                stance_emoji = {"hawkish": "🔴", "dovish": "🟢", "neutral": "⚪"}.get(item.stance, "⚪")
                date_str = item.published_at.strftime("%Y-%m-%d")
                lines.append(f"- {stance_emoji} {date_str}: {item.title}")
            lines.append("")
    
    # Analysis framework (condensed)
    lines.append("## Analysis Framework")
    lines.append("")
    lines.append("### ICT Concepts")
    lines.append("- Liquidity Sweeps (stops taken above/below highs/lows)")
    lines.append("- Market Structure Shift (MSS)")
    lines.append("- Fair Value Gaps (FVG) & Order Blocks (OB)")
    lines.append("- Premium/Discount zones")
    lines.append("")
    lines.append("### Turtle Soup Pattern")
    lines.append("- Fake breakout → quick rejection → reversal entry")
    lines.append("")
    
    # Output format (single symbol)
    lines.append("## Required Output Format")
    lines.append("")
    lines.append("Please respond with ONLY valid JSON in this exact structure:")
    lines.append("")
    lines.append("```json")
    lines.append(f"""{{
  "symbol": "{symbol}",
  "bias": "bullish | bearish | neutral",
  "confidence": 75,
  "levels": {{
    "pdh": 0.00,
    "pdl": 0.00,
    "pwh": 0.00,
    "pwl": 0.00,
    "key_support": 0.00,
    "key_resistance": 0.00
  }},
  "ict_notes": "Markdown notes about ICT analysis...",
  "turtle_soup": {{
    "detected": true,
    "direction": "long | short | none",
    "entry": 0.00,
    "invalidation": 0.00,
    "tp1": 0.00,
    "tp2": 0.00,
    "description": "Description of the setup..."
  }},
  "trade_plan": {{
    "direction": "long | short | no_trade",
    "entry_zone": {{"low": 0.00, "high": 0.00}},
    "invalidation": 0.00,
    "tp1": 0.00,
    "tp2": 0.00,
    "stand_down_if": ["condition1", "condition2"]
  }},
  "market_context": "Brief market sentiment"
}}""")
    lines.append("```")
    lines.append("")
    lines.append("---")
    lines.append(f"*Generated at {datetime.now().isoformat()}*")
    
    # Write to file
    prompt_content = "\n".join(lines)
    prompt_path = PROMPTS_DIR / f"{target_date.isoformat()}_{symbol}_analysis.md"
    
    with open(prompt_path, "w") as f:
        f.write(prompt_content)
    
    return str(prompt_path)


def generate_prompt(db: Session, target_date: date = None) -> str:
    """
    Generate the daily analysis prompt markdown file.
    Returns the path to the generated file.
    """
    if target_date is None:
        target_date = date.today()
    
    # Collect all data
    snapshots = get_snapshots_for_date(db, target_date)
    events = get_todays_events(db, currencies=["USD", "EUR"])
    danger_windows = get_danger_windows(db, target_date)
    news = get_recent_news(db, hours=48)
    
    # Organize snapshots by symbol and timeframe
    snapshots_by_symbol = {symbol: {} for symbol in SYMBOLS}
    for snap in snapshots:
        if snap.symbol in snapshots_by_symbol:
            snapshots_by_symbol[snap.symbol][snap.timeframe] = snap
    
    # Build the prompt
    lines = []
    lines.append(f"# Daily Analysis Request - {target_date.isoformat()}")
    lines.append("")
    lines.append("## Instructions")
    lines.append("")
    lines.append("Please analyze the attached TradingView screenshots using ICT concepts and the Turtle Soup pattern.")
    lines.append("Provide your analysis in the JSON format specified at the end of this document.")
    lines.append("")
    
    # Screenshots section
    lines.append("## Screenshots to Analyze")
    lines.append("")
    
    for symbol in SYMBOLS:
        lines.append(f"### {symbol}")
        symbol_snaps = snapshots_by_symbol[symbol]
        
        if not symbol_snaps:
            lines.append("- **No screenshots found** - please add to /data/inbox/")
        else:
            for tf in TIMEFRAMES:
                if tf in symbol_snaps:
                    snap = symbol_snaps[tf]
                    # Get absolute path for Cursor
                    abs_path = SCREENSHOTS_DIR / Path(snap.file_path).name
                    lines.append(f"- {tf}: `{abs_path}`")
                else:
                    lines.append(f"- {tf}: **Missing**")
        lines.append("")
    
    # Economic calendar section
    lines.append("## Today's Economic Calendar (USD/EUR)")
    lines.append("")
    
    if events:
        # High impact first
        high_impact = [e for e in events if e.impact == "high"]
        other_events = [e for e in events if e.impact != "high"]
        
        if high_impact:
            lines.append("### High Impact Events ⚠️")
            lines.append("")
            lines.append("| Time (UTC) | Currency | Event | Forecast | Previous |")
            lines.append("|------------|----------|-------|----------|----------|")
            for event in high_impact:
                time_str = event.event_time_utc.strftime("%H:%M")
                lines.append(f"| {time_str} | {event.currency} | {event.title} | {event.forecast or '-'} | {event.previous or '-'} |")
            lines.append("")
        
        if other_events:
            lines.append("### Other Events")
            lines.append("")
            lines.append("| Time (UTC) | Currency | Impact | Event |")
            lines.append("|------------|----------|--------|-------|")
            for event in other_events:
                time_str = event.event_time_utc.strftime("%H:%M")
                lines.append(f"| {time_str} | {event.currency} | {event.impact} | {event.title} |")
            lines.append("")
    else:
        lines.append("No USD/EUR events scheduled for today.")
        lines.append("")
    
    # Danger windows
    if danger_windows:
        lines.append("### Danger Windows (±30 min around high-impact events)")
        lines.append("")
        for window in danger_windows:
            start = window["start"].strftime("%H:%M")
            end = window["end"].strftime("%H:%M")
            lines.append(f"- {start} - {end} UTC: {window['event'].title}")
        lines.append("")
    
    # FOMC Statements section (recent meetings)
    fomc_news = get_fomc_related_news(db, days=60)  # Last 2 months of FOMC
    if fomc_news:
        lines.append("## Recent FOMC Statements & Meetings")
        lines.append("")
        lines.append("| Date | Document | Stance |")
        lines.append("|------|----------|--------|")
        seen_dates = set()
        for item in fomc_news[:15]:  # Last 15 FOMC items
            date_str = item.published_at.strftime("%Y-%m-%d")
            # Dedupe by date+title combo
            key = f"{date_str}-{item.title[:30]}"
            if key in seen_dates:
                continue
            seen_dates.add(key)
            stance_emoji = {"hawkish": "🔴", "dovish": "🟢", "neutral": "⚪"}.get(item.stance, "⚪")
            lines.append(f"| {date_str} | [{item.title}]({item.url}) | {stance_emoji} {item.stance or 'neutral'} ({item.confidence or 0}%) |")
        lines.append("")
    
    # Recent news section
    lines.append("## Recent Fed News (Last 48h)")
    lines.append("")
    
    if news:
        for item in news[:10]:  # Top 10
            stance_emoji = {"hawkish": "🔴", "dovish": "🟢", "neutral": "⚪"}.get(item.stance, "⚪")
            lines.append(f"- {stance_emoji} [{item.title}]({item.url}) - {item.source}")
        lines.append("")
    else:
        lines.append("No recent Fed-related news found.")
        lines.append("")
    
    # Analysis framework
    lines.append("## Analysis Framework")
    lines.append("")
    lines.append("### ICT Concepts to Identify")
    lines.append("- **Liquidity Sweeps**: Look for stops taken above/below recent highs/lows")
    lines.append("- **Market Structure Shift (MSS)**: Break of structure indicating potential reversal")
    lines.append("- **Fair Value Gaps (FVG)**: Imbalanced price action leaving gaps")
    lines.append("- **Order Blocks (OB)**: Last candle before impulsive move")
    lines.append("- **Premium/Discount**: Where is price relative to range?")
    lines.append("")
    lines.append("### Turtle Soup Pattern")
    lines.append("Look for:")
    lines.append("1. Price breaks above/below a significant level (fake breakout)")
    lines.append("2. Quick rejection back into range")
    lines.append("3. Entry on the reversal, stop beyond the fake breakout")
    lines.append("")
    lines.append("### Key Levels to Identify")
    lines.append("- Previous Day High (PDH) / Previous Day Low (PDL)")
    lines.append("- Previous Week High (PWH) / Previous Week Low (PWL)")
    lines.append("- Session highs/lows (Asian, London, NY)")
    lines.append("")
    
    # Output format
    lines.append("## Required Output Format")
    lines.append("")
    lines.append("Please respond with ONLY valid JSON in this exact structure:")
    lines.append("")
    lines.append("```json")
    lines.append("""{
  "signals": {
    "XAUUSD": {
      "bias": "bullish | bearish | neutral",
      "confidence": 75,
      "levels": {
        "pdh": 2650.00,
        "pdl": 2620.00,
        "pwh": 2680.00,
        "pwl": 2580.00,
        "key_support": 2615.00,
        "key_resistance": 2660.00
      },
      "ict_notes": "Markdown notes about ICT analysis...",
      "turtle_soup": {
        "detected": true,
        "direction": "long",
        "entry": 2625.00,
        "invalidation": 2615.00,
        "tp1": 2650.00,
        "tp2": 2680.00,
        "description": "Sweep of PDL followed by MSS..."
      },
      "trade_plan": {
        "direction": "long | short | no_trade",
        "entry_zone": {"low": 2620.00, "high": 2630.00},
        "invalidation": 2610.00,
        "tp1": 2650.00,
        "tp2": 2680.00,
        "stand_down_if": ["NFP in next 2 hours", "Price above 2665"]
      }
    },
    "EURUSD": {
      "bias": "bearish | bullish | neutral",
      "confidence": 60,
      "levels": { ... },
      "ict_notes": "...",
      "turtle_soup": { ... },
      "trade_plan": { ... }
    }
  },
  "market_context": "Brief overall market sentiment summary",
  "news_impact": "How the news/calendar affects bias"
}
```""")
    lines.append("")
    lines.append("---")
    lines.append(f"*Generated at {datetime.now().isoformat()}*")
    
    # Write to file
    prompt_content = "\n".join(lines)
    prompt_path = PROMPTS_DIR / f"{target_date.isoformat()}_analysis.md"
    
    with open(prompt_path, "w") as f:
        f.write(prompt_content)
    
    return str(prompt_path)
