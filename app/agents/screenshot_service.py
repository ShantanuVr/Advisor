"""
TradingView Screenshot Service using Playwright

Automatically captures TradingView chart screenshots for specified symbols and timeframes.
Requires: playwright, playwright install chromium
"""

import asyncio
import os
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict
import logging

logger = logging.getLogger(__name__)

# TradingView chart URL template (public charts, no login required)
TRADINGVIEW_URL = "https://www.tradingview.com/chart/?symbol={symbol}&interval={interval}"

# Timeframe mapping: our format -> TradingView interval
TIMEFRAME_MAP = {
    "1W": "W",      # Weekly
    "1D": "D",      # Daily
    "4H": "240",    # 4 hours
    "1H": "60",     # 1 hour
    "15M": "15",    # 15 minutes
    "5M": "5",      # 5 minutes
}

# Symbol mapping for TradingView format
SYMBOL_MAP = {
    "XAUUSD": "OANDA:XAUUSD",
    "EURUSD": "OANDA:EURUSD",
    "GBPUSD": "OANDA:GBPUSD",
    "USDJPY": "OANDA:USDJPY",
}


async def capture_tradingview_screenshot(
    symbol: str,
    timeframe: str,
    output_dir: Path,
    headless: bool = True,
    wait_seconds: int = 5,
) -> Optional[str]:
    """
    Capture a single TradingView chart screenshot.
    
    Args:
        symbol: Trading symbol (e.g., "XAUUSD")
        timeframe: Timeframe (e.g., "1D", "4H")
        output_dir: Directory to save screenshots
        headless: Run browser in headless mode
        wait_seconds: Seconds to wait for chart to load
        
    Returns:
        Path to saved screenshot or None on failure
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        logger.error("Playwright not installed. Run: pip install playwright && playwright install chromium")
        return None
    
    # Map symbol and timeframe
    tv_symbol = SYMBOL_MAP.get(symbol, symbol)
    tv_interval = TIMEFRAME_MAP.get(timeframe, timeframe)
    
    url = TRADINGVIEW_URL.format(symbol=tv_symbol, interval=tv_interval)
    
    # Generate filename
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    filename = f"{symbol}_{timeframe}_{timestamp}.png"
    filepath = output_dir / filename
    
    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch(headless=headless)
            context = await browser.new_context(
                viewport={"width": 1920, "height": 1080},
                device_scale_factor=2,  # Retina quality
            )
            page = await context.new_page()
            
            logger.info(f"Navigating to {url}")
            await page.goto(url, wait_until="networkidle")
            
            # Wait for chart to fully render
            await asyncio.sleep(wait_seconds)
            
            # Try to close any popups/modals
            try:
                await page.click('[data-name="popup-close-button"]', timeout=2000)
            except:
                pass
            
            try:
                await page.click('button:has-text("Accept")', timeout=2000)
            except:
                pass
            
            # Hide header/toolbars for cleaner screenshot
            await page.evaluate("""
                () => {
                    // Hide various UI elements for cleaner chart
                    const selectors = [
                        '.header-chart-panel-wrapper',
                        '.chart-controls-bar',
                        '.bottom-widgetbar-content',
                    ];
                    selectors.forEach(sel => {
                        const el = document.querySelector(sel);
                        if (el) el.style.display = 'none';
                    });
                }
            """)
            
            await asyncio.sleep(1)
            
            # Capture screenshot
            await page.screenshot(path=str(filepath), full_page=False)
            logger.info(f"Screenshot saved: {filepath}")
            
            await browser.close()
            return str(filepath)
            
        except Exception as e:
            logger.error(f"Failed to capture {symbol} {timeframe}: {e}")
            return None


async def capture_all_charts(
    symbols: List[str] = None,
    timeframes: List[str] = None,
    output_dir: Path = None,
    headless: bool = True,
) -> Dict[str, List[str]]:
    """
    Capture screenshots for all symbol/timeframe combinations.
    
    Args:
        symbols: List of symbols (default: XAUUSD, EURUSD)
        timeframes: List of timeframes (default: all)
        output_dir: Output directory (default: data/screenshots)
        headless: Run browser headless
        
    Returns:
        Dict mapping symbols to list of screenshot paths
    """
    from app.config import SCREENSHOTS_DIR, SYMBOLS, TIMEFRAMES
    
    symbols = symbols or SYMBOLS
    timeframes = timeframes or TIMEFRAMES
    output_dir = output_dir or SCREENSHOTS_DIR
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    results = {symbol: [] for symbol in symbols}
    
    for symbol in symbols:
        for timeframe in timeframes:
            logger.info(f"Capturing {symbol} {timeframe}...")
            path = await capture_tradingview_screenshot(
                symbol=symbol,
                timeframe=timeframe,
                output_dir=output_dir,
                headless=headless,
            )
            if path:
                results[symbol].append(path)
            
            # Small delay between captures to avoid rate limiting
            await asyncio.sleep(2)
    
    return results


async def capture_charts_for_symbol(
    symbol: str,
    timeframes: List[str] = None,
    output_dir: Path = None,
    headless: bool = True,
) -> List[str]:
    """
    Capture all timeframe screenshots for a single symbol.
    """
    from app.config import SCREENSHOTS_DIR, TIMEFRAMES
    
    timeframes = timeframes or TIMEFRAMES
    output_dir = output_dir or SCREENSHOTS_DIR
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    paths = []
    for timeframe in timeframes:
        path = await capture_tradingview_screenshot(
            symbol=symbol,
            timeframe=timeframe,
            output_dir=output_dir,
            headless=headless,
        )
        if path:
            paths.append(path)
        await asyncio.sleep(2)
    
    return paths


# CLI helper for testing
if __name__ == "__main__":
    import sys
    
    logging.basicConfig(level=logging.INFO)
    
    symbol = sys.argv[1] if len(sys.argv) > 1 else "XAUUSD"
    timeframe = sys.argv[2] if len(sys.argv) > 2 else "1D"
    
    from app.config import SCREENSHOTS_DIR
    
    result = asyncio.run(capture_tradingview_screenshot(
        symbol=symbol,
        timeframe=timeframe,
        output_dir=SCREENSHOTS_DIR,
        headless=False,  # Show browser for testing
    ))
    
    print(f"Screenshot: {result}")
