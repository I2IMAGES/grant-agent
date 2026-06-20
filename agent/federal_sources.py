import logging
import os
from datetime import datetime, timezone, timedelta

import requests

logger = logging.getLogger(__name__)

GRANTS_GOV_URL = "https://api.grants.gov/v2/api/search"
SAM_GOV_URL = "https://api.sam.gov/opportunities/v2/search"

# Grants.gov eligibility code 11 = Small Businesses
# Note: the v2 API requires a Content-Type header; also try the public search endpoint
# as a fallback since the API has had intermittent 403 issues.
GRANTS_GOV_SEARCHES = [
    {"keyword": "minority women small business transportation", "eligibilities": ["11"]},
    {"keyword": "HUBZone small business set-aside", "eligibilities": ["11"]},
    {"keyword": "women owned small business WOSB grant", "eligibilities": ["11"]},
    {"keyword": "minority owned business development grant", "eligibilities": ["11"]},
    {"keyword": "non-emergency medical transportation NMET grant", "eligibilities": ["11"]},
]

# SAM.gov set-aside codes relevant to Inward2Onward
SAM_SET_ASIDES = "WOSB,EDWOSB,HZC,8AN,SBA"


def _fetch_grants_gov() -> list[dict]:
    results = []
    seen_ids: set[str] = set()
    for search in GRANTS_GOV_SEARCHES:
        try:
            payload = {
                "rows": 20,
                "startRecordNum": 0,
                "oppStatuses": "posted",
                "sortBy": "openDate|desc",
                **search,
            }
            resp = requests.post(
                GRANTS_GOV_URL,
                json=payload,
                headers={"Content-Type": "application/json", "Accept": "application/json"},
                timeout=20,
            )
            resp.raise_for_status()
            data = resp.json()
            opportunities = data.get("data", {}).get("hits", [])
            for opp in opportunities:
                opp_id = opp.get("_id") or opp.get("id", "")
                if opp_id in seen_ids:
                    continue
                seen_ids.add(opp_id)

                title = opp.get("_source", {}).get("title") or opp.get("title", "")
                opp_number = opp.get("_source", {}).get("number") or opp.get("number", "")
                agency = opp.get("_source", {}).get("agencyName") or opp.get("agencyName", "")
                close_date = opp.get("_source", {}).get("closeDate") or opp.get("closeDate", "")
                award_ceiling = opp.get("_source", {}).get("awardCeiling") or opp.get("awardCeiling", "")
                synopsis = opp.get("_source", {}).get("synopsis") or opp.get("synopsis") or opp.get("description", "")

                url = "https://www.grants.gov/search-results-detail/{}".format(opp_number) if opp_number else ""
                if not url or not title:
                    continue

                snippet_parts = [agency] if agency else []
                if close_date:
                    snippet_parts.append("Deadline: {}".format(close_date))
                if award_ceiling:
                    snippet_parts.append("Award up to ${}".format(award_ceiling))
                if synopsis:
                    snippet_parts.append(str(synopsis)[:200])

                results.append({
                    "title": title,
                    "url": url,
                    "snippet": " | ".join(snippet_parts)[:500],
                    "source_query": "grants.gov: {}".format(search["keyword"]),
                })
        except Exception as e:
            logger.warning("grants.gov search failed for %r: %s", search["keyword"], e)

    logger.info("federal_sources: %d results from grants.gov", len(results))
    return results


def _fetch_sam_gov(api_key: str) -> list[dict]:
    results = []
    posted_from = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%m/%d/%Y")
    try:
        resp = requests.get(
            SAM_GOV_URL,
            params={
                "api_key": api_key,
                "limit": 50,
                "postedFrom": posted_from,
                "setAside": SAM_SET_ASIDES,
                "status": "active",
                "sort": "-modifiedDate",
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        opportunities = data.get("opportunitiesData", [])
        for opp in opportunities:
            title = opp.get("title", "")
            url = opp.get("uiLink") or opp.get("link", "")
            dept = opp.get("departmentName") or opp.get("organizationHierarchy", [{}])[0].get("name", "")
            set_aside = opp.get("typeOfSetAsideDescription") or opp.get("typeOfSetAside", "")
            response_deadline = opp.get("responseDeadLine", "")
            naics = opp.get("naicsCode", "")

            if not title or not url:
                continue

            snippet_parts = []
            if dept:
                snippet_parts.append(dept)
            if set_aside:
                snippet_parts.append("Set-aside: {}".format(set_aside))
            if response_deadline:
                snippet_parts.append("Deadline: {}".format(response_deadline))
            if naics:
                snippet_parts.append("NAICS: {}".format(naics))

            results.append({
                "title": title,
                "url": url,
                "snippet": " | ".join(snippet_parts)[:500],
                "source_query": "sam.gov set-asides: {}".format(set_aside or SAM_SET_ASIDES),
            })
    except Exception as e:
        logger.warning("sam.gov search failed: %s", e)

    logger.info("federal_sources: %d results from sam.gov", len(results))
    return results


def run() -> list[dict]:
    results = _fetch_grants_gov()

    sam_key = os.environ.get("SAM_GOV_API_KEY", "").strip()
    if sam_key:
        results.extend(_fetch_sam_gov(sam_key))
    else:
        logger.info("federal_sources: SAM_GOV_API_KEY not set - skipping sam.gov")

    return results
