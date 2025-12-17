"""News collector - fetches Fed/FOMC related news from official sources."""

import re
from datetime import datetime, timedelta
from typing import List, Optional
import httpx
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from app.models import NewsItem


# Keywords for hawkish/dovish classification
HAWKISH_KEYWORDS = [
    "rate hike", "raise rates", "raising rates", "tighten", "tightening",
    "inflation concern", "inflation worry", "hot inflation", "sticky inflation",
    "restrictive", "higher for longer", "more hikes", "additional hike",
    "hawkish", "aggressive", "combat inflation", "price stability",
    "elevated inflation", "upside risks"
]

DOVISH_KEYWORDS = [
    "rate cut", "cutting rates", "lower rates", "easing", "pause",
    "soft landing", "cooling inflation", "disinflation", "slowing economy",
    "dovish", "accommodative", "support growth", "economic weakness",
    "recession", "slowdown", "downside risks", "labor market cooling"
]

# Category keywords for Fed releases
FOMC_KEYWORDS = ["fomc", "federal open market", "monetary policy", "interest rate", 
                 "funds rate", "policy decision", "rate decision"]
SPEECH_KEYWORDS = ["speech", "remarks", "testimony", "chair powell", "governor"]
ECONOMIC_KEYWORDS = ["inflation", "employment", "gdp", "economic", "beige book"]


def classify_stance(text: str) -> tuple:
    """
    Simple keyword-based stance classification.
    Returns (stance, confidence) where stance is hawkish/dovish/neutral.
    """
    text_lower = text.lower()
    
    hawkish_count = sum(1 for kw in HAWKISH_KEYWORDS if kw in text_lower)
    dovish_count = sum(1 for kw in DOVISH_KEYWORDS if kw in text_lower)
    
    total = hawkish_count + dovish_count
    if total == 0:
        return ("neutral", 30)
    
    if hawkish_count > dovish_count:
        confidence = min(90, 50 + (hawkish_count - dovish_count) * 10)
        return ("hawkish", confidence)
    elif dovish_count > hawkish_count:
        confidence = min(90, 50 + (dovish_count - hawkish_count) * 10)
        return ("dovish", confidence)
    else:
        return ("neutral", 40)


def categorize_release(title: str) -> str:
    """Categorize a Fed release by type."""
    title_lower = title.lower()
    
    if any(kw in title_lower for kw in FOMC_KEYWORDS):
        return "FOMC"
    elif any(kw in title_lower for kw in SPEECH_KEYWORDS):
        return "Speech"
    elif any(kw in title_lower for kw in ECONOMIC_KEYWORDS):
        return "Economic Data"
    else:
        return "Other"


async def fetch_fed_press_releases(year: int = None) -> List[dict]:
    """
    Fetch press releases from Federal Reserve official website.
    Source: https://www.federalreserve.gov/newsevents/pressreleases.htm
    
    The page uses server-side rendering, we parse the HTML directly.
    """
    news_items = []
    
    if year is None:
        year = datetime.now().year
    
    # Fetch the main press releases page and year-specific pages
    urls = [
        "https://www.federalreserve.gov/newsevents/pressreleases.htm",
        f"https://www.federalreserve.gov/newsevents/pressreleases/{year}-all.htm",
        f"https://www.federalreserve.gov/newsevents/pressreleases/{year}-monetary.htm",
    ]
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }
    
    async with httpx.AsyncClient(follow_redirects=True) as client:
        for url in urls:
            try:
                response = await client.get(url, headers=headers, timeout=30.0)
                if response.status_code != 200:
                    continue
                
                soup = BeautifulSoup(response.text, "lxml")
                
                # Method 1: Look for press release list items
                # Fed website typically uses div.row or similar for each release
                items = soup.select("div.row")
                
                for item in items:
                    try:
                        # Look for date - Fed uses various formats
                        date_elem = item.select_one("time") or item.select_one(".itemDate") or item.select_one("p.news-date")
                        link_elem = item.select_one("a")
                        
                        if not link_elem:
                            continue
                        
                        title = link_elem.get_text(strip=True)
                        if not title or len(title) < 10:
                            continue
                        
                        href = link_elem.get("href", "")
                        if not href:
                            continue
                        if not href.startswith("http"):
                            href = f"https://www.federalreserve.gov{href}"
                        
                        # Skip non-press-release links
                        if "/pressreleases/" not in href and "/newsevents/" not in href:
                            continue
                        
                        # Parse date
                        pub_date = None
                        if date_elem:
                            date_str = date_elem.get("datetime") or date_elem.get_text(strip=True)
                            pub_date = parse_fed_date(date_str)
                        
                        if not pub_date:
                            # Try to extract date from URL (format: monetary20251217a.htm)
                            date_match = re.search(r'(\d{4})(\d{2})(\d{2})', href)
                            if date_match:
                                try:
                                    pub_date = datetime(
                                        int(date_match.group(1)),
                                        int(date_match.group(2)),
                                        int(date_match.group(3))
                                    )
                                except ValueError:
                                    pass
                        
                        if not pub_date:
                            pub_date = datetime.now()
                        
                        # Categorize the release
                        category = categorize_release(title)
                        
                        news_items.append({
                            "published_at": pub_date,
                            "source": f"Federal Reserve ({category})",
                            "title": title,
                            "url": href,
                        })
                        
                    except Exception:
                        continue
                
                # Method 2: Look for news-item divs
                news_divs = soup.select("div.news-item, div.eventlist, .panel-body")
                for item in news_divs:
                    try:
                        link_elem = item.select_one("a")
                        if not link_elem:
                            continue
                        
                        title = link_elem.get_text(strip=True)
                        href = link_elem.get("href", "")
                        
                        if not title or not href or len(title) < 10:
                            continue
                        
                        if not href.startswith("http"):
                            href = f"https://www.federalreserve.gov{href}"
                        
                        # Extract date from surrounding text or URL
                        pub_date = None
                        date_text = item.get_text()
                        date_patterns = [
                            r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}",
                            r"\d{1,2}/\d{1,2}/\d{4}",
                        ]
                        for pattern in date_patterns:
                            match = re.search(pattern, date_text)
                            if match:
                                pub_date = parse_fed_date(match.group())
                                break
                        
                        if not pub_date:
                            date_match = re.search(r'(\d{4})(\d{2})(\d{2})', href)
                            if date_match:
                                try:
                                    pub_date = datetime(
                                        int(date_match.group(1)),
                                        int(date_match.group(2)),
                                        int(date_match.group(3))
                                    )
                                except ValueError:
                                    pub_date = datetime.now()
                        
                        if not pub_date:
                            pub_date = datetime.now()
                        
                        category = categorize_release(title)
                        
                        news_items.append({
                            "published_at": pub_date,
                            "source": f"Federal Reserve ({category})",
                            "title": title,
                            "url": href,
                        })
                        
                    except Exception:
                        continue
                        
            except Exception as e:
                print(f"Error fetching {url}: {e}")
                continue
    
    # Remove duplicates based on URL
    seen_urls = set()
    unique_items = []
    for item in news_items:
        if item["url"] not in seen_urls:
            seen_urls.add(item["url"])
            unique_items.append(item)
    
    return unique_items


def parse_fed_date(date_str: str) -> Optional[datetime]:
    """Parse various date formats used by the Fed."""
    if not date_str:
        return None
    
    date_str = date_str.strip()
    
    formats = [
        "%B %d, %Y",      # December 17, 2025
        "%B %d %Y",       # December 17 2025
        "%b %d, %Y",      # Dec 17, 2025
        "%m/%d/%Y",       # 12/17/2025
        "%Y-%m-%d",       # 2025-12-17
        "%Y-%m-%dT%H:%M:%S",  # ISO format
    ]
    
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    
    # Try ISO format with timezone
    try:
        return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except ValueError:
        pass
    
    return None


async def fetch_fed_rss_feeds() -> List[dict]:
    """
    Fetch from Federal Reserve RSS feeds if available.
    """
    news_items = []
    
    # Fed RSS feed URLs (these may change)
    rss_urls = [
        "https://www.federalreserve.gov/feeds/press_all.xml",
        "https://www.federalreserve.gov/feeds/press_monetary.xml",
    ]
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    }
    
    async with httpx.AsyncClient() as client:
        for url in rss_urls:
            try:
                response = await client.get(url, headers=headers, timeout=30.0)
                if response.status_code != 200:
                    continue
                
                soup = BeautifulSoup(response.text, "xml")
                items = soup.find_all("item")[:30]
                
                for item in items:
                    try:
                        title_elem = item.find("title")
                        link_elem = item.find("link")
                        pub_date_elem = item.find("pubDate")
                        
                        if not title_elem or not link_elem:
                            continue
                        
                        title = title_elem.get_text(strip=True)
                        link = link_elem.get_text(strip=True)
                        
                        # Parse date
                        pub_date = datetime.now()
                        if pub_date_elem:
                            try:
                                date_str = pub_date_elem.get_text(strip=True)
                                # RSS format: Wed, 18 Dec 2024 15:00:00 GMT
                                pub_date = datetime.strptime(date_str, "%a, %d %b %Y %H:%M:%S %Z")
                            except ValueError:
                                try:
                                    pub_date = datetime.strptime(date_str, "%a, %d %b %Y %H:%M:%S %z")
                                except ValueError:
                                    pass
                        
                        category = categorize_release(title)
                        
                        news_items.append({
                            "published_at": pub_date,
                            "source": f"Federal Reserve ({category})",
                            "title": title,
                            "url": link,
                        })
                        
                    except Exception:
                        continue
                        
            except Exception as e:
                print(f"Error fetching RSS {url}: {e}")
                continue
    
    return news_items


async def fetch_fomc_calendar() -> List[dict]:
    """
    Fetch FOMC meeting dates and statements from current year.
    """
    news_items = []
    url = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers, timeout=30.0)
            if response.status_code != 200:
                return news_items
            
            soup = BeautifulSoup(response.text, "lxml")
            
            # Find all meeting rows
            for row in soup.select("div.panel, div.fomc-meeting, tr"):
                try:
                    # Look for links to statements or minutes
                    links = row.select("a")
                    for link in links:
                        href = link.get("href", "")
                        text = link.get_text(strip=True).lower()
                        
                        if "statement" in text or "minutes" in text or "press conference" in text:
                            if not href.startswith("http"):
                                href = f"https://www.federalreserve.gov{href}"
                            
                            # Try to extract date from URL
                            date_match = re.search(r'(\d{4})(\d{2})(\d{2})', href)
                            if date_match:
                                pub_date = datetime(
                                    int(date_match.group(1)),
                                    int(date_match.group(2)),
                                    int(date_match.group(3))
                                )
                            else:
                                pub_date = datetime.now()
                            
                            title = f"FOMC {text.title()}"
                            
                            news_items.append({
                                "published_at": pub_date,
                                "source": "Federal Reserve (FOMC)",
                                "title": title,
                                "url": href,
                            })
                            
                except Exception:
                    continue
                    
    except Exception as e:
        print(f"Error fetching FOMC calendar: {e}")
    
    return news_items


async def fetch_fomc_statements(years: List[int] = None) -> List[dict]:
    """
    Fetch FOMC statements and meeting materials from specified years.
    This provides access to historical FOMC decisions.
    
    Source: https://www.federalreserve.gov/monetarypolicy/fomchistorical{year}.htm
    """
    if years is None:
        current_year = datetime.now().year
        years = [current_year, current_year - 1]  # Current and previous year
    
    news_items = []
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    }
    
    async with httpx.AsyncClient(follow_redirects=True) as client:
        for year in years:
            # Try different URL patterns for FOMC historical data
            urls = [
                f"https://www.federalreserve.gov/monetarypolicy/fomchistorical{year}.htm",
                f"https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
            ]
            
            for url in urls:
                try:
                    response = await client.get(url, headers=headers, timeout=30.0)
                    if response.status_code != 200:
                        continue
                    
                    soup = BeautifulSoup(response.text, "lxml")
                    
                    # Find all links on the page
                    all_links = soup.find_all("a", href=True)
                    
                    for link in all_links:
                        href = link.get("href", "")
                        text = link.get_text(strip=True)
                        
                        # Filter for FOMC-related documents
                        if not href:
                            continue
                        
                        # Match FOMC statement URLs
                        # Format: /newsevents/pressreleases/monetary20251218a.htm
                        # Or: /monetarypolicy/fomcprojtabl20251218.htm
                        is_fomc_doc = any([
                            "/monetary" in href and str(year) in href,
                            "fomcprojtabl" in href,
                            "statement" in text.lower(),
                            "minutes" in text.lower(),
                            "press conference" in text.lower(),
                            "projection" in text.lower(),
                            "implementation note" in text.lower(),
                        ])
                        
                        if not is_fomc_doc:
                            continue
                        
                        # Build full URL
                        if not href.startswith("http"):
                            href = f"https://www.federalreserve.gov{href}"
                        
                        # Skip PDFs for now (we want HTML statements)
                        if href.endswith(".pdf"):
                            continue
                        
                        # Extract date from URL
                        date_match = re.search(r'(\d{4})(\d{2})(\d{2})', href)
                        if date_match:
                            try:
                                pub_date = datetime(
                                    int(date_match.group(1)),
                                    int(date_match.group(2)),
                                    int(date_match.group(3))
                                )
                            except ValueError:
                                continue
                        else:
                            continue
                        
                        # Determine document type
                        text_lower = text.lower()
                        if "statement" in text_lower or "monetary" in href:
                            doc_type = "Statement"
                        elif "minutes" in text_lower:
                            doc_type = "Minutes"
                        elif "press conference" in text_lower or "presconf" in href:
                            doc_type = "Press Conference"
                        elif "projection" in text_lower or "projtabl" in href:
                            doc_type = "Projections"
                        elif "implementation" in text_lower:
                            doc_type = "Implementation Note"
                        else:
                            doc_type = "Document"
                        
                        # Create title
                        date_str = pub_date.strftime("%B %d, %Y")
                        title = f"FOMC {doc_type} - {date_str}"
                        
                        news_items.append({
                            "published_at": pub_date,
                            "source": "Federal Reserve (FOMC)",
                            "title": title,
                            "url": href,
                            "doc_type": doc_type,
                        })
                        
                except Exception as e:
                    print(f"Error fetching {url}: {e}")
                    continue
    
    # Remove duplicates based on URL
    seen_urls = set()
    unique_items = []
    for item in news_items:
        if item["url"] not in seen_urls:
            seen_urls.add(item["url"])
            unique_items.append(item)
    
    # Sort by date descending
    unique_items.sort(key=lambda x: x["published_at"], reverse=True)
    
    return unique_items


async def fetch_fomc_statement_content(url: str) -> Optional[str]:
    """
    Fetch the actual content of an FOMC statement for analysis.
    Returns the text content of the statement.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers, timeout=30.0)
            if response.status_code != 200:
                return None
            
            soup = BeautifulSoup(response.text, "lxml")
            
            # Find the main content area
            content_selectors = [
                "div.col-xs-12.col-sm-8.col-md-8",
                "div#article",
                "article",
                "div.content",
                "main",
            ]
            
            for selector in content_selectors:
                content = soup.select_one(selector)
                if content:
                    # Remove script and style elements
                    for elem in content.find_all(["script", "style", "nav", "footer"]):
                        elem.decompose()
                    
                    text = content.get_text(separator="\n", strip=True)
                    if len(text) > 200:  # Ensure we got meaningful content
                        return text
            
            # Fallback to body text
            body = soup.find("body")
            if body:
                for elem in body.find_all(["script", "style", "nav", "footer", "header"]):
                    elem.decompose()
                return body.get_text(separator="\n", strip=True)
                
    except Exception as e:
        print(f"Error fetching statement content from {url}: {e}")
    
    return None


async def fetch_and_store_news(db: Session, include_historical: bool = False) -> dict:
    """
    Fetch news from all Federal Reserve sources and store in database.
    
    Args:
        db: Database session
        include_historical: If True, fetch FOMC statements from previous months/years
    """
    results = {
        "fetched": 0,
        "inserted": 0,
        "skipped": 0,
        "errors": [],
    }
    
    all_news = []
    
    # Fetch from multiple sources
    try:
        press_releases = await fetch_fed_press_releases()
        all_news.extend(press_releases)
        print(f"  Fetched {len(press_releases)} from press releases page")
    except Exception as e:
        results["errors"].append(f"Press releases: {e}")
    
    try:
        rss_news = await fetch_fed_rss_feeds()
        all_news.extend(rss_news)
        print(f"  Fetched {len(rss_news)} from RSS feeds")
    except Exception as e:
        results["errors"].append(f"RSS feeds: {e}")
    
    try:
        fomc_news = await fetch_fomc_calendar()
        all_news.extend(fomc_news)
        print(f"  Fetched {len(fomc_news)} from FOMC calendar")
    except Exception as e:
        results["errors"].append(f"FOMC calendar: {e}")
    
    # Fetch historical FOMC statements if requested
    if include_historical:
        try:
            current_year = datetime.now().year
            fomc_statements = await fetch_fomc_statements(years=[current_year, current_year - 1])
            all_news.extend(fomc_statements)
            print(f"  Fetched {len(fomc_statements)} FOMC statements from {current_year-1}-{current_year}")
        except Exception as e:
            results["errors"].append(f"FOMC statements: {e}")
    
    # Remove duplicates
    seen_urls = set()
    unique_news = []
    for item in all_news:
        if item["url"] not in seen_urls:
            seen_urls.add(item["url"])
            unique_news.append(item)
    
    results["fetched"] = len(unique_news)
    
    # For historical mode, don't filter by date
    if include_historical:
        cutoff = datetime.utcnow() - timedelta(days=365)  # Last year
    else:
        cutoff = datetime.utcnow() - timedelta(days=7)
    
    for item in unique_news:
        pub_at = item["published_at"]
        if pub_at.tzinfo is not None:
            pub_at = pub_at.replace(tzinfo=None)
        
        # Skip old items
        if pub_at < cutoff:
            continue
        
        # Check if already exists
        existing = db.query(NewsItem).filter(NewsItem.url == item["url"]).first()
        if existing:
            results["skipped"] += 1
            continue
        
        # Classify stance based on title
        stance, confidence = classify_stance(item["title"])
        
        news_item = NewsItem(
            published_at=pub_at,
            source=item["source"],
            title=item["title"],
            url=item["url"],
            stance=stance,
            confidence=confidence,
        )
        db.add(news_item)
        results["inserted"] += 1
    
    db.commit()
    return results


async def fetch_and_store_fomc_history(db: Session, years: List[int] = None) -> dict:
    """
    Fetch and store historical FOMC statements specifically.
    
    Args:
        db: Database session
        years: List of years to fetch (default: current and previous year)
    """
    results = {
        "fetched": 0,
        "inserted": 0,
        "skipped": 0,
        "statements": [],
        "errors": [],
    }
    
    if years is None:
        current_year = datetime.now().year
        years = [current_year, current_year - 1]
    
    try:
        fomc_statements = await fetch_fomc_statements(years=years)
        results["fetched"] = len(fomc_statements)
        
        for item in fomc_statements:
            pub_at = item["published_at"]
            if pub_at.tzinfo is not None:
                pub_at = pub_at.replace(tzinfo=None)
            
            # Check if already exists
            existing = db.query(NewsItem).filter(NewsItem.url == item["url"]).first()
            if existing:
                results["skipped"] += 1
                continue
            
            # Classify stance based on title
            stance, confidence = classify_stance(item["title"])
            
            # For statements, try to fetch and analyze the content
            doc_type = item.get("doc_type", "Document")
            if doc_type == "Statement":
                content = await fetch_fomc_statement_content(item["url"])
                if content:
                    # Classify based on full content
                    stance, confidence = classify_stance(content)
                    # Boost confidence for full content analysis
                    confidence = min(95, confidence + 10)
            
            news_item = NewsItem(
                published_at=pub_at,
                source=item["source"],
                title=item["title"],
                url=item["url"],
                stance=stance,
                confidence=confidence,
            )
            db.add(news_item)
            results["inserted"] += 1
            results["statements"].append({
                "date": pub_at.strftime("%Y-%m-%d"),
                "title": item["title"],
                "stance": stance,
                "confidence": confidence,
            })
        
        db.commit()
        
    except Exception as e:
        results["errors"].append(str(e))
    
    return results


def get_recent_news(db: Session, hours: int = 48) -> List[NewsItem]:
    """Get news items from the last N hours."""
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    return db.query(NewsItem).filter(
        NewsItem.published_at >= cutoff
    ).order_by(NewsItem.published_at.desc()).all()


def get_all_recent_news(db: Session, days: int = 7) -> List[NewsItem]:
    """Get all news items from the last N days."""
    cutoff = datetime.utcnow() - timedelta(days=days)
    return db.query(NewsItem).filter(
        NewsItem.published_at >= cutoff
    ).order_by(NewsItem.published_at.desc()).all()


def get_top_drivers(db: Session, limit: int = 3) -> List[NewsItem]:
    """Get top news drivers by confidence score."""
    cutoff = datetime.utcnow() - timedelta(hours=48)
    return db.query(NewsItem).filter(
        NewsItem.published_at >= cutoff,
        NewsItem.confidence.isnot(None)
    ).order_by(NewsItem.confidence.desc()).limit(limit).all()


def get_fomc_related_news(db: Session, days: int = 7) -> List[NewsItem]:
    """Get FOMC-specific news items."""
    cutoff = datetime.utcnow() - timedelta(days=days)
    return db.query(NewsItem).filter(
        NewsItem.published_at >= cutoff,
        NewsItem.source.contains("FOMC")
    ).order_by(NewsItem.published_at.desc()).all()
