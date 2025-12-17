"""News collector - fetches Fed/FOMC related news."""

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
    "hawkish", "aggressive", "combat inflation"
]

DOVISH_KEYWORDS = [
    "rate cut", "cutting rates", "lower rates", "easing", "pause",
    "soft landing", "cooling inflation", "disinflation", "slowing economy",
    "dovish", "accommodative", "support growth", "economic weakness",
    "recession", "slowdown"
]


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


async def fetch_fed_official_news() -> List[dict]:
    """
    Fetch news from Federal Reserve official press releases.
    """
    news_items = []
    url = "https://www.federalreserve.gov/newsevents/pressreleases.htm"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers, timeout=30.0)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, "lxml")
            
            # Find press release items
            items = soup.select("div.row.ng-scope")[:20]  # Last 20 items
            
            for item in items:
                try:
                    # Get date
                    date_elem = item.select_one("time")
                    if not date_elem:
                        continue
                    date_str = date_elem.get("datetime", "")
                    if date_str:
                        pub_date = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                    else:
                        continue
                    
                    # Get title and link
                    link_elem = item.select_one("a")
                    if not link_elem:
                        continue
                    
                    title = link_elem.get_text(strip=True)
                    href = link_elem.get("href", "")
                    if href and not href.startswith("http"):
                        href = f"https://www.federalreserve.gov{href}"
                    
                    # Filter for relevant content
                    relevant_terms = ["fomc", "federal open market", "monetary policy", 
                                    "interest rate", "inflation", "economic"]
                    if not any(term in title.lower() for term in relevant_terms):
                        continue
                    
                    news_items.append({
                        "published_at": pub_date,
                        "source": "Federal Reserve",
                        "title": title,
                        "url": href,
                    })
                    
                except Exception:
                    continue
                    
    except Exception as e:
        print(f"Error fetching Fed news: {e}")
    
    return news_items


async def fetch_reuters_fed_news() -> List[dict]:
    """
    Fetch Fed-related news from Reuters RSS.
    Note: Reuters may have changed their RSS structure.
    """
    news_items = []
    
    # Reuters business news RSS
    url = "https://www.reutersagency.com/feed/?best-topics=business-finance&post_type=best"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers, timeout=30.0)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, "xml")
            
            items = soup.find_all("item")[:30]
            
            for item in items:
                try:
                    title = item.find("title")
                    if not title:
                        continue
                    title_text = title.get_text(strip=True)
                    
                    # Filter for Fed-related content
                    relevant_terms = ["fed", "fomc", "powell", "federal reserve", 
                                    "interest rate", "monetary policy", "inflation"]
                    if not any(term in title_text.lower() for term in relevant_terms):
                        continue
                    
                    link = item.find("link")
                    pub_date = item.find("pubDate")
                    
                    if pub_date:
                        # Parse RSS date format
                        try:
                            date_str = pub_date.get_text(strip=True)
                            pub_datetime = datetime.strptime(
                                date_str, "%a, %d %b %Y %H:%M:%S %z"
                            )
                        except ValueError:
                            pub_datetime = datetime.utcnow()
                    else:
                        pub_datetime = datetime.utcnow()
                    
                    news_items.append({
                        "published_at": pub_datetime,
                        "source": "Reuters",
                        "title": title_text,
                        "url": link.get_text(strip=True) if link else "",
                    })
                    
                except Exception:
                    continue
                    
    except Exception as e:
        print(f"Error fetching Reuters news: {e}")
    
    return news_items


async def fetch_and_store_news(db: Session) -> dict:
    """
    Fetch news from all configured sources and store in database.
    """
    results = {
        "fetched": 0,
        "inserted": 0,
        "skipped": 0,
        "errors": [],
    }
    
    # Collect from all sources
    all_news = []
    
    try:
        fed_news = await fetch_fed_official_news()
        all_news.extend(fed_news)
    except Exception as e:
        results["errors"].append(f"Fed official: {e}")
    
    try:
        reuters_news = await fetch_reuters_fed_news()
        all_news.extend(reuters_news)
    except Exception as e:
        results["errors"].append(f"Reuters: {e}")
    
    results["fetched"] = len(all_news)
    
    # Filter to last 48 hours
    cutoff = datetime.utcnow() - timedelta(hours=48)
    
    for item in all_news:
        # Make datetime offset-naive for comparison
        pub_at = item["published_at"]
        if pub_at.tzinfo is not None:
            pub_at = pub_at.replace(tzinfo=None)
        
        if pub_at < cutoff:
            continue
        
        # Check if already exists
        existing = db.query(NewsItem).filter(NewsItem.url == item["url"]).first()
        if existing:
            results["skipped"] += 1
            continue
        
        # Classify stance
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


def get_recent_news(db: Session, hours: int = 48) -> List[NewsItem]:
    """Get news items from the last N hours."""
    cutoff = datetime.utcnow() - timedelta(hours=hours)
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
