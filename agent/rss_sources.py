import logging
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime

import feedparser
import requests

logger = logging.getLogger(__name__)

# Each entry: (label, feed_url)
# Add or remove feeds here — failures are logged and skipped silently.
RSS_FEEDS = [
    # Federal agency NOFA announcements
    ("Grants.gov - New Opportunities",      "https://www.grants.gov/rss/GG_NewOppByCategory.xml"),
    ("SAMHSA Grant Announcements",          "https://www.samhsa.gov/grants/grant-announcements/rss"),
    ("MBDA News & Grants",                  "https://www.mbda.gov/rss.xml"),
    ("SBA News",                            "https://www.sba.gov/rss/news"),
    ("HHS Grants",                          "https://www.hhs.gov/grants/rss/index.html"),
    ("EDA News",                            "https://www.eda.gov/rss.xml"),
    ("USDA Rural Development News",        "https://www.rd.usda.gov/rss/rd-news-releases"),

    # Grant alert blogs and newsletters
    ("Seliger + Associates Grant Alerts",   "https://seliger.com/feed/"),
    ("GrantStation News",                   "https://grantstation.com/feed"),
    ("Hello Alice Small Business Grants",   "https://helloalice.com/feed/"),
    ("Arizona Commerce Authority News",     "https://www.azcommerce.com/feed/"),
]

# Only include items published within this many days
RECENCY_DAYS = 7


def _parse_date(entry) -> datetime | None:
    """Try to extract a publish date from a feed entry."""
    for attr in ("published", "updated"):
        raw = getattr(entry, attr, None)
        if raw:
            try:
                return parsedate_to_datetime(raw).astimezone(timezone.utc)
            except Exception:
                pass
    if hasattr(entry, "published_parsed") and entry.published_parsed:
        try:
            return datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
        except Exception:
            pass
    return None


def _fetch_feed(label: str, url: str, cutoff: datetime) -> list[dict]:
    results = []
    try:
        resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        feed = feedparser.parse(resp.text)
        for entry in feed.entries:
            pub_date = _parse_date(entry)
            if pub_date and pub_date < cutoff:
                continue  # too old

            title = entry.get("title", "").strip()
            link = entry.get("link", "").strip()
            summary = entry.get("summary", "") or entry.get("description", "")
            # Strip basic HTML tags from summary
            import re
            summary = re.sub(r"<[^>]+>", " ", summary).strip()
            summary = " ".join(summary.split())[:400]

            if not title or not link:
                continue

            results.append({
                "title": title,
                "url": link,
                "snippet": summary[:500],
                "source_query": "rss: {}".format(label),
            })
    except Exception as e:
        logger.warning("rss_sources: failed to fetch %r (%s): %s", label, url, e)

    return results


def run() -> list[dict]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=RECENCY_DAYS)
    all_results: list[dict] = []
    seen_urls: set[str] = set()

    for label, url in RSS_FEEDS:
        items = _fetch_feed(label, url, cutoff)
        for item in items:
            if item["url"] not in seen_urls:
                seen_urls.add(item["url"])
                all_results.append(item)

    logger.info("rss_sources: %d items from %d feeds (last %d days)",
                len(all_results), len(RSS_FEEDS), RECENCY_DAYS)
    return all_results
