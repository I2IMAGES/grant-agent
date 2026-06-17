import os
import hashlib
import logging
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
