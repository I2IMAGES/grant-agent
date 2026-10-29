import os
import hashlib
import logging
import requests

logger = logging.getLogger(__name__)

SEARCH_QUERIES = [
    # Arizona state and local
    "small business grant Arizona minority-owned women-owned {year} apply now open",
    "Arizona Commerce Authority grant program {year} small business open applications",
    "Maricopa County small business grant {year} open application deadline",
    "City of Glendale Arizona business grant {year} apply",
    "City of Phoenix small business grant {year} minority women open",
    "Arizona Community Foundation grant small business {year} accepting applications",
    "Arizona SBDC grant funding opportunity {year} open now",

    # PTAC / SBA certifications
    "Arizona PTAC procurement technical assistance minority women HUBZone {year}",
    "SBA 8(a) certification apply {year} minority-owned open",
    "WOSB EDWOSB women-owned small business federal contract {year} open solicitation",
    "HUBZone certified small business federal contract {year} open solicitation",

    # Federal grants open now
    "MBDA business center grant application {year} minority entrepreneur open",
    "EDA Build to Scale grant {year} application open small business",
    "USDA RBDG rural business development grant {year} apply deadline",
    "DOT DBE disadvantaged business enterprise grant {year} open application",
    "SAMHSA grant {year} substance abuse transportation nonprofit apply open",
    "HHS ACF grant {year} nonprofit social services transportation open application",

    # NEMT partnership targets — nonprofits receiving grants that need transportation
    "SAMHSA NOFO {year} substance abuse mental health grant open application",
    "HUD housing homelessness grant nonprofit {year} open application",
    "DOL workforce development grant nonprofit {year} open solicitation",
    "ACL senior services transportation grant {year} nonprofit open",

    # Corporate and foundation grants
    "Comcast RISE grant {year} minority women-owned business apply open",
    "Goldman Sachs 10000 Small Businesses {year} Arizona apply open",
    "Visa She's Next grant women-owned business {year} apply open",
    "Hello Alice small business grant {year} minority women open application",
    "Amber Grant women-owned business {year} apply open",
    "FedEx small business grant {year} apply open deadline",
]

SERPER_URL = "https://google.serper.dev/search"


def fetch_query(query: str, api_key: str) -> list[dict]:
    try:
        resp = requests.post(
            SERPER_URL,
            headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
            # tbs=qdr:m3 limits results to pages indexed in the last 3 months
            json={"q": query, "num": 10, "tbs": "qdr:m3"},
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

    from datetime import date
    year = date.today().year
    for template in SEARCH_QUERIES:
        query = template.format(year=year)
        results = fetch_query(query, api_key)
        for r in results:
            url = r.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                combined.append(r)

    logger.info("searcher: %d unique results from %d queries", len(combined), len(SEARCH_QUERIES))
    return combined
