import os
import hashlib
import logging
import requests

logger = logging.getLogger(__name__)

SEARCH_QUERIES = [
    # Arizona-specific
    "small business grant Arizona minority-owned women-owned 2026 apply now",
    "Arizona Commerce Authority grant program 2026 small business",
    "Maricopa County small business grant 2026 open application",
    "Glendale Arizona business grant 2026",
    "City of Phoenix small business grant 2026 minority women",
    "Arizona Community Foundation grant small business 2026",
    "Arizona SBDC grant funding opportunity 2026",

    # Federal programs open now
    "SBA 8(a) program application open 2026 minority-owned",
    "WOSB women-owned small business federal contract set-aside 2026",
    "HUBZone certification benefit federal contract 2026 apply",
    "MBDA business center grant application 2026",
    "SBA Community Advantage grant 2026 minority small business",
    "EDA Build to Scale grant 2026 application open",
    "USDA RBDG rural business development grant 2026 apply",
    "DOT DBE disadvantaged business enterprise grant 2026 open",

    # Corporate and foundation grants open now
    "corporate foundation grant minority women-owned small business 2026 apply",
    "Comcast RISE grant 2026 minority women-owned business",
    "FedEx small business grant 2026 apply",
    "Goldman Sachs 10000 Small Businesses grant 2026 Arizona",
    "Visa Practical Business Skills grant minority-owned 2026",
]
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
        logger.warning("Query failed: %r - %s", query, e)
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
