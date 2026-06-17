import os
import hashlib
import logging
import requests

logger = logging.getLogger(__name__)

SEARCH_QUERIES = [
    "small business grants minority-owned 2025 Arizona",
    "SBA grants minority-owned business Arizona 2025",
    "women-owned small business grants Arizona 2025",
    "HUBZone grants small business 2025 federal",
    "minority business enterprise grant opportunity 2025",
    "MBDA grants minority business development 2025",
    "women-owned business federal grants 2025",
    "8(a) program grants minority small business 2025",
    "WOSB grants women-owned small business federal 2025",
    "Arizona Commerce Authority small business grants 2025",
    "Maricopa County small business grant program 2025",
    "Glendale Arizona business grant opportunity 2025",
    "USDA rural business development grant minority 2025",
    "EDA economic development grant minority-owned 2025",
    "community development grant minority business 2025",
    "HUD grant minority business enterprise 2025",
    "DOT disadvantaged business enterprise grant 2025",
    "NSF small business innovation grant minority 2025",
    "EPA environmental justice grant minority business 2025",
    "corporate foundation grant minority women-owned business 2025",
]

SERPER_URL = "https://google.serper.dev/search"


def fetch_query(query: str, api_key: str) -> list[dict]:
    try:
        resp = requests.post(
            SERPER_URL,
            headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
            json={"q": query, "num": 10},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        results = []
        for item in data.get("organic", [])[:10]:
            results.append({
                "title": item.get("title", ""),
                "url": item.get("link", ""),
                "snippet": item.get("snippet", ""),
            })
        return results
    except Exception as e:
        logger.warning("Query failed: %r — %s", query, e)
        return []


def run() -> list[dict]:
    api_key = os.environ["SERPER_API_KEY"]
    seen_urls: set[str] = set()
    combined: list[dict] = []

    for query in SEARCH_QUERIES:
        results = fetch_query(query, api_key)
        for r in results:
            url = r.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                combined.append(r)

    logger.info("searcher: %d unique results from %d queries", len(combined), len(SEARCH_QUERIES))
    return combined
