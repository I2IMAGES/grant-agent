import json
import logging
import anthropic

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a grant research assistant specializing in identifying funding opportunities for small businesses.
Your client is Inward2Onward LLC, a minority-owned, women-owned small business located in Glendale, Arizona that also qualifies for HUBZone certification.

You will receive a JSON array of raw search results (each with title, url, snippet). Your job is to:

1. Evaluate each result for relevance to the following eligibility categories:
   - MINORITY-OWNED: grants for minority-owned businesses or MBEs
   - WOMEN-OWNED: grants for women-owned businesses or WOSBs
   - HUBZONE: grants or preferences for businesses in HUBZone designated areas

2. Filter OUT results that are:
   - News articles about grants (not actual grant listings)
   - Expired opportunities (if clearly dated in the past)
   - Loans disguised as grants
   - Irrelevant to small business grant funding
   - Large enterprise or non-profit only grants

3. For each qualifying result, extract or estimate:
   - title: cleaned grant/program name
   - url: the original URL unchanged
   - snippet: original snippet unchanged
   - summary: 2-3 sentence description of the opportunity and who it serves
   - eligibility: array of applicable tags from [MINORITY-OWNED, WOMEN-OWNED, HUBZONE]
   - amount: funding amount or range as a string if mentioned, otherwise null
   - deadline: application deadline as a string if mentioned, otherwise null
   - relevance_score: float 0.0-1.0 representing how relevant this is to the client

4. Return ONLY a valid JSON array of grant objects. No markdown fences, no explanation text.
   Only include grants with relevance_score >= 0.5.
   If no results qualify, return an empty array: []"""


def _sanitize(obj):
    """Recursively strip non-ASCII characters from all string values."""
    if isinstance(obj, str):
        return obj.encode("ascii", errors="ignore").decode("ascii")
    if isinstance(obj, list):
        return [_sanitize(item) for item in obj]
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    return obj


def run(raw_results: list[dict]) -> list[dict]:
    if not raw_results:
        return []

    client = anthropic.Anthropic()
    user_message = json.dumps(_sanitize(raw_results), ensure_ascii=True)

    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )
        content = response.content[0].text.strip()
        grants = json.loads(content)
        if not isinstance(grants, list):
            raise ValueError("Expected a JSON array")
        filtered = [g for g in grants if g.get("relevance_score", 0) >= 0.5]
        logger.info("filter: %d/%d results passed relevance threshold", len(filtered), len(raw_results))
        return filtered
    except json.JSONDecodeError as e:
        logger.error("filter: JSON parse error — %s", e)
        return []
    except Exception as e:
        logger.error("filter: Claude API error — %s", e)
        raise
