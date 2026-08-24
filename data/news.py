"""
data/news.py
------------
Fetches recent news headlines for a stock ticker using yfinance.
Returns a clean list of dicts. Never raises — returns [] on any error.
"""

from typing import Any
import yfinance as yf


def _extract_article(raw: dict[str, Any]) -> dict[str, str]:
    """
    Turn one raw yfinance news item into a clean, consistent dict.
    Handles both the modern nested "content" structure and the older flat format.
    """
    # --- Modern nested structure (most common in recent yfinance) ---
    if "content" in raw and isinstance(raw["content"], dict):
        content = raw["content"]

        title = content.get("title") or ""
        summary = content.get("summary") or ""

        # Publisher lives under provider.displayName
        provider = content.get("provider") or {}
        publisher = provider.get("displayName") or "Unknown"

        # Link can be under canonicalUrl or clickThroughUrl
        url_obj = content.get("canonicalUrl") or content.get("clickThroughUrl") or {}
        link = url_obj.get("url") or ""

        published = content.get("pubDate") or ""

    # --- Older / flat structure (fallback) ---
    else:
        title = raw.get("title") or ""
        summary = raw.get("summary") or ""
        publisher = raw.get("publisher") or "Unknown"
        link = raw.get("link") or ""
        # Older format used Unix timestamp
        ts = raw.get("providerPublishTime")
        published = str(ts) if ts else ""

    return {
        "title": title.strip(),
        "publisher": publisher.strip(),
        "link": link.strip(),
        "published": published.strip(),
        "summary": summary.strip(),
    }


def get_news(ticker: str, limit: int = 8) -> list[dict]:
    """
    Fetch up to `limit` recent news articles for the given ticker.

    Only returns articles that mention the ticker in the title or summary.

    Parameters
    ----------
    ticker : str
        Stock symbol, e.g. "AAPL", "MSFT", "TSLA"
    limit : int, optional
        Maximum number of articles to return (default 8)

    Returns
    -------
    list[dict]
        Clean list of relevant news dicts. Empty list on any failure.
    """
    if not ticker or not isinstance(ticker, str):
        print("[news] Invalid ticker provided.")
        return []

    ticker = ticker.strip().upper()

    try:
        stock = yf.Ticker(ticker)

        # Ask for extra articles so we still have enough after filtering
        raw_news = stock.get_news(count=limit * 4)

        # Fallback for older yfinance versions
        if not raw_news:
            raw_news = getattr(stock, "news", None) or []

        if not isinstance(raw_news, list):
            print(f"[news] Unexpected response type for {ticker}.")
            return []

        # Clean, filter, and keep only relevant articles
        cleaned = []
        for item in raw_news:                    # ← look at all of them
            if not isinstance(item, dict):
                continue
            article = _extract_article(item)

            if article["title"] and _is_relevant(article, ticker):
                cleaned.append(article)

            # Stop early once we have enough
            if len(cleaned) >= limit:
                break

        return cleaned

    except Exception as e:
        print(f"[news] Failed to fetch news for {ticker}: {e}")
        return []

def _is_relevant(article: dict, ticker: str) -> bool:
    """
    Return True if the ticker appears in the title or summary.
    Simple but effective relevance check.
    """
    text = f"{article.get('title', '')} {article.get('summary', '')}".lower()
    return ticker.lower() in text


# ------------------------------------------------------------------
# Quick manual test (run this file directly)
# ------------------------------------------------------------------
if __name__ == "__main__":
    print("Testing get_news('AAPL') ...")
    articles = get_news("AAPL", limit=5)

    if not articles:
        print("No articles returned (possible rate-limit or network issue).")
    else:
        for i, a in enumerate(articles, 1):
            print(f"\n--- Article {i} ---")
            print(f"Title    : {a['title']}")
            print(f"Publisher: {a['publisher']}")
            print(f"Published: {a['published']}")
            print(f"Link     : {a['link'][:80]}..." if a['link'] else "Link     : (none)")
            if a["summary"]:
                print(f"Summary  : {a['summary'][:100]}...")
