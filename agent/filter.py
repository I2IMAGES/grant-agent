import json
import logging
import os
import re
import requests
import traceback

logger = logging.getLogger(__name__)

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_MODEL = "claude-haiku-4-5-20251001"

SYSTEM_PROMPT = """You are a grant research assistant specializing in identifying funding opportunities for small businesses.
Your client is Inward2Onward LLC, a minority-owned, women-owned small business located in Glendale, Arizona that also qualifies for HUBZone certification.
Today's date is June 17, 2026. Any deadline before this date is expired.

You will receive a JSON array of raw search results (each with title, url, snippet). Your job is to:

1. Evaluate each result for relevance to the following eligibility categories:
   - MINORITY-OWNED: grants for minority-owned businesses or MBEs
   - WOMEN-OWNED: grants for women-owned businesses or WOSBs
   - HUBZONE: grants or preferences for businesses in HUBZone designated areas

2. HARD REJECT any result matching ANY of these conditions (assign relevance_score 0 and exclude):
   - Deadline has passed (any date before June 17, 2026)
   - News article, press release, blog post, or recap about a grant - not an application page
   - General informational or overview page with no open application (e.g. sba.gov/programs/* description pages)
   - Loan, line of credit, equity investment, or bond - not a grant or contract set-aside
   - Restricted to non-profits, universities, governments, or large corporations only
   - No connection to minority-owned, women-owned, or HUBZone small businesses

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

BATCH_SIZE = 20
MAX_FIELD_CHARS = 500


def _strip_non_ascii(value: str) -> str:
    return value.encode("ascii", errors="ignore").decode("ascii")


def _clean(obj):
    """Recursively strip non-ASCII from all strings, then truncate to MAX_FIELD_CHARS."""
    if isinstance(obj, str):
        return _strip_non_ascii(obj)[:MAX_FIELD_CHARS]
    if isinstance(obj, list):
        return [_clean(item) for item in obj]
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items()}
    return obj


def _strip_fences(text: str) -> str:
    """Remove markdown code fences Claude sometimes wraps JSON in."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _call_claude(api_key: str, batch: list[dict]) -> list[dict]:
    """Call the Anthropic API directly via requests, avoiding the SDK's
    platform-detection headers which can contain U+2028 on some Linux runners."""
    payload = {
        "model": ANTHROPIC_MODEL,
        "max_tokens": 4096,
        "system": SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": json.dumps(batch, ensure_ascii=True)}],
    }
    resp = requests.post(
        ANTHROPIC_API_URL,
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json=payload,
        timeout=120,
    )
    resp.raise_for_status()
    content = _strip_fences(resp.json()["content"][0]["text"])
    grants = json.loads(content)
    if not isinstance(grants, list):
        raise ValueError("Expected JSON array, got {}".format(type(grants).__name__))
    return [g for g in grants if g.get("relevance_score", 0) >= 0.5]


def run(raw_results: list[dict]) -> list[dict]:
    if not raw_results:
        return []

    api_key = os.environ.get("ANTHROPIC_API_KEY", "").encode("ascii", errors="ignore").decode("ascii").strip()

    cleaned = [_clean(r) for r in raw_results]
    logger.info("filter: cleaned %d results, sending in batches of %d", len(cleaned), BATCH_SIZE)

    all_grants: list[dict] = []
    any_batch_failed = False

    for batch_start in range(0, len(cleaned), BATCH_SIZE):
        batch = cleaned[batch_start : batch_start + BATCH_SIZE]
        batch_num = batch_start // BATCH_SIZE + 1
        last_exc: Exception | None = None
        for attempt in range(1, 4):
            try:
                grants = _call_claude(api_key, batch)
                logger.info("filter: batch %d - %d grants passed threshold", batch_num, len(grants))
                all_grants.extend(grants)
                last_exc = None
                break
            except (json.JSONDecodeError, ValueError) as e:
                logger.warning("filter: batch %d attempt %d parse error - %s", batch_num, attempt, e)
                last_exc = e
            except Exception as e:
                logger.warning("filter: batch %d attempt %d error - %s", batch_num, attempt, e)
                last_exc = e
                break  # non-parse errors are unlikely to recover on retry
        if last_exc is not None:
            if isinstance(last_exc, (json.JSONDecodeError, ValueError)):
                logger.error("filter: batch %d failed after 3 attempts (JSON parse) - %s", batch_num, last_exc)
            else:
                logger.error(
                    "filter: batch %d failed (full traceback below):\n%s",
                    batch_num,
                    traceback.format_exc(),
                )
            any_batch_failed = True

    if any_batch_failed and not all_grants:
        raise RuntimeError("All Claude filter batches failed - see logs above for details")

    logger.info(
        "filter: %d/%d results passed (any_batch_failed=%s)",
        len(all_grants), len(cleaned), any_batch_failed,
    )
    return all_grants
