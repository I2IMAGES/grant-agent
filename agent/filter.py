import json
import logging
import re
import traceback
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


def _call_claude(client: anthropic.Anthropic, batch: list[dict]) -> list[dict]:
    user_message = json.dumps(batch, ensure_ascii=True)
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )
    content = _strip_fences(response.content[0].text)
    grants = json.loads(content)
    if not isinstance(grants, list):
        raise ValueError("Expected JSON array, got {}".format(type(grants).__name__))
    return [g for g in grants if g.get("relevance_score", 0) >= 0.5]


def run(raw_results: list[dict]) -> list[dict]:
    if not raw_results:
        return []

    cleaned = [_clean(r) for r in raw_results]
    logger.info("filter: cleaned %d results, sending in batches of %d", len(cleaned), BATCH_SIZE)

    client = anthropic.Anthropic()
    all_grants: list[dict] = []
    any_batch_failed = False

    for batch_start in range(0, len(cleaned), BATCH_SIZE):
        batch = cleaned[batch_start : batch_start + BATCH_SIZE]
        batch_num = batch_start // BATCH_SIZE + 1
        try:
            grants = _call_claude(client, batch)
            logger.info("filter: batch %d - %d grants passed threshold", batch_num, len(grants))
            all_grants.extend(grants)
        except json.JSONDecodeError as e:
            logger.error("filter: batch %d JSON parse error - %s", batch_num, e)
            any_batch_failed = True
        except Exception:
            logger.error(
                "filter: batch %d error (full traceback below):\n%s",
                batch_num,
                traceback.format_exc(),
            )
            any_batch_failed = True

    if any_batch_failed and not all_grants:
        # Every batch failed - signal to the caller to use raw fallback
        raise RuntimeError("All Claude filter batches failed - see logs above for details")

    logger.info(
        "filter: %d/%d results passed (any_batch_failed=%s)",
        len(all_grants), len(cleaned), any_batch_failed,
    )
    return all_grants
