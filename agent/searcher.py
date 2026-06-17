import os
import hashlib
import logging
import requests

logger = logging.getLogger(__name__)

SEARCH_QUERIES = [
    # Arizona state and local
    "small business grant Arizona minority-owned women-owned 2026 apply now",
    "Arizona Commerce Authority grant program 2026 small business open",
    "Maricopa County small business grant 2026 open application",
    "City of Glendale Arizona business grant 2026",
    "City of Phoenix small business grant 2026 minority women apply",
    "Mesa Tempe Scottsdale Chandler small business grant 2026",
    "Arizona Community Foundation grant small business 2026 apply",
    "Arizona SBDC grant funding opportunity 2026 open",
    "Arizona Office of Economic Opportunity grant minority business 2026",

    # PTAC - Procurement Technical Assistance
    "Arizona PTAC procurement technical assistance minority women HUBZone 2026",
    "APTAC small business federal contracting help minority women-owned 2026",

    # Federal programs open now
    "SBA 8(a) certification apply 2026 minority-owned socially disadvantaged",
    "WOSB EDWOSB women-owned small business certification 2026 apply",
    "HUBZone certified small business federal contract 2026 open solicitation",
    "MBDA business center grant application 2026 minority entrepreneur",
    "EDA Build to Scale grant 2026 application open small business",
    "USDA RBDG rural business development grant 2026 apply deadline",
    "DOT DBE disadvantaged business enterprise grant 2026 open application",
    "SBA SBIR small business innovation research 2026 open solicitation",

    # Corporate and foundation grants
    "corporate foundation grant minority women-owned small business 2026 apply open",
    "Comcast RISE grant 2026 minority women-owned business apply",
    "FedEx small business grant 2026 apply open",
    "Goldman Sachs 10000 Small Businesses 2026 Arizona apply",
    "Visa She's Next grant women-owned business 2026 apply",
    "Hello Alice small business grant 2026 minority women apply",
    "Amber Grant women-owned business 2026 apply",
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
                "source_query": query,
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
