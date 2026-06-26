import os
import hashlib
import logging
import re
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

_client = None


def _get_client():
    global _client
    if _client is not None:
        return _client
    try:
        from supabase import create_client
        url = os.environ["SUPABASE_URL"]
        key = os.environ["SUPABASE_KEY"]
        _client = create_client(url, key)
    except Exception as e:
        logger.error("Supabase connection failed: %s", e)
        _client = None
    return _client


def _grant_id(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()


def _title_key(title: str) -> str:
    """Normalize a grant title for fuzzy duplicate detection."""
    return " ".join(re.sub(r"[^a-z0-9 ]", "", title.lower()).split()[:8])


def read_recent_titles(days: int = 7) -> set[str]:
    """Return normalized title keys for grants sent within the last N days."""
    client = _get_client()
    if client is None:
        return set()
    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        resp = (
            client.table("seen_grants")
            .select("title")
            .gte("last_seen_at", cutoff)
            .execute()
        )
        return {_title_key(row["title"]) for row in (resp.data or []) if row.get("title")}
    except Exception as e:
        logger.error("deduplicator.read_recent_titles failed: %s", e)
        return set()


def read(urls: list[str]) -> set[str]:
    """Return set of grant_ids seen within the last 30 days."""
    client = _get_client()
    if client is None:
        return set()
    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        ids = [_grant_id(u) for u in urls]
        resp = (
            client.table("seen_grants")
            .select("grant_id")
            .in_("grant_id", ids)
            .gte("last_seen_at", cutoff)
            .execute()
        )
        return {row["grant_id"] for row in (resp.data or [])}
    except Exception as e:
        logger.error("deduplicator.read failed: %s", e)
        return set()


def write(grants: list[dict]) -> None:
    """Upsert new grants into seen_grants table."""
    client = _get_client()
    if client is None:
        return
    now = datetime.now(timezone.utc).isoformat()
    rows = []
    for g in grants:
        url = g.get("url", "")
        if not url:
            continue
        rows.append({
            "grant_id": _grant_id(url),
            "title": g.get("title", ""),
            "url": url,
            "first_seen_at": now,
            "last_seen_at": now,
            "eligibility": g.get("eligibility", []),
            "amount": g.get("amount"),
            "deadline": g.get("deadline"),
        })
    if not rows:
        return
    try:
        client.table("seen_grants").upsert(
            rows,
            on_conflict="grant_id",
        ).execute()
        logger.info("deduplicator.write: upserted %d rows", len(rows))
    except Exception as e:
        logger.error("deduplicator.write failed: %s", e)


def log_search_results(
    raw_results: list[dict],
    new_urls: set[str],
    filtered_urls: set[str],
    run_at: str,
) -> None:
    """Insert every raw search result into search_results for audit purposes."""
    client = _get_client()
    if client is None:
        return
    rows = []
    for r in raw_results:
        url = r.get("url", "")
        if not url:
            continue
        rows.append({
            "run_at": run_at,
            "source_query": r.get("source_query", ""),
            "title": r.get("title", ""),
            "url": url,
            "snippet": r.get("snippet", ""),
            "passed_dedup": url in new_urls,
            "passed_filter": url in filtered_urls,
        })
    if not rows:
        return
    try:
        client.table("search_results").insert(rows).execute()
        logger.info("deduplicator.log_search_results: logged %d rows", len(rows))
    except Exception as e:
        logger.error("deduplicator.log_search_results failed: %s", e)
