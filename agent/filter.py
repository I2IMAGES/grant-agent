import json
import logging
import os
import re
import requests
import traceback

logger = logging.getLogger(__name__)

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_MODEL = "claude-haiku-4-5-20251001"

_SYSTEM_PROMPT_TEMPLATE = """You are a grant research assistant for Inward2Onward LLC, a minority-owned, women-owned small business in Glendale, Arizona that also qualifies for HUBZone certification.

WHAT INWARD2ONWARD DOES:
Inward2Onward provides Non-Medical Emergency Transportation (NMET) services - transporting clients to medical appointments, treatment programs, social services, job training, and community resources. Their clients are typically referred by nonprofits, government agencies, healthcare providers, and social service organizations.

Today's date is {today}. Any deadline before this date is expired.

You will receive a JSON array of raw search results (each with title, url, snippet). Evaluate each for TWO types of opportunity:

TYPE 1 - DIRECT GRANTS (Inward2Onward applies directly):
Grants, contracts, or set-asides where Inward2Onward itself is an eligible applicant.
Tag with one or more of: MINORITY-OWNED, WOMEN-OWNED, HUBZONE

TYPE 2 - PARTNERSHIP LEADS (Inward2Onward subcontracts):
Grants awarded to nonprofits, public agencies, tribal organizations, or healthcare providers
to run programs that would require transportation for their clients. Examples:
- Substance abuse or mental health treatment programs
- Youth services, foster care, or family support programs
- Workforce development, job training, or reentry programs
- Senior services, disability services, or home health programs
- Housing, homelessness, or refugee resettlement programs
- Healthcare access or community health programs
The strategy: the funded nonprofit becomes a customer for NMET services.
Tag these with: PARTNERSHIP

HARD REJECT (exclude entirely, relevance_score 0):
- Deadline has already passed (before {today})
- The grant cycle shown is from a prior year (2025 or earlier) — e.g. "2025 application", "FY2025 awards", "2024 recipients"
- Award announcements, past winners lists, or "grant awarded to" news — these are done deals
- Pure news articles or press recaps with no actionable open application link
- General program overview pages ("about our grants", "grant history") with no current open application
- Loans, bonds, lines of credit, or equity investments
- Grants only for large corporations, accredited universities, or government agencies with no subcontracting angle
- No plausible connection to NMET services or I2O eligibility
- Results that say "deadline passed", "closed", "not accepting applications", or "next cycle TBD"

BORDERLINE — use lower score (0.5-0.6) for:
- Grant programs that are recurring but the current cycle's opening date is unclear
- PARTNERSHIP leads where the transportation need is indirect or speculative

For each qualifying result, extract:
- title: cleaned program name
- url: original URL unchanged
- snippet: original snippet unchanged
- summary: 2-3 sentences on the opportunity and specifically how Inward2Onward fits - either as direct applicant or as a transportation subcontractor
- eligibility: array of applicable tags from [MINORITY-OWNED, WOMEN-OWNED, HUBZONE, PARTNERSHIP]
- amount: funding amount or range as a string if mentioned, otherwise null
- deadline: application deadline as a string if mentioned, otherwise null
- relevance_score: float 0.0-1.0

Return ONLY a valid JSON array. No markdown fences, no explanation text.
Only include results with relevance_score >= 0.5.
If no results qualify, return an empty array: []"""

BATCH_SIZE = 20


def _build_system_prompt() -> str:
    from datetime import date
    today = date.today().strftime("%B %d, %Y")
    return _SYSTEM_PROMPT_TEMPLATE.format(today=today)
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
        "system": _build_system_prompt(),
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
