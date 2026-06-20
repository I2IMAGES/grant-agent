#!/usr/bin/env python3
"""Main orchestrator for the Inward2Onward daily grant discovery agent."""

import hashlib
import logging
import sys
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

import searcher
import federal_sources
import rss_sources
import deduplicator
import filter as grant_filter
import emailer


def main() -> None:
    run_at = datetime.now(timezone.utc).isoformat()

    # 1. Search — Serper (Google) + Grants.gov + SAM.gov
    logger.info("Step 1: running searcher")
    raw_results = searcher.run()
    logger.info("searcher returned %d raw results", len(raw_results))

    logger.info("Step 1b: fetching federal sources (grants.gov / sam.gov)")
    federal_results = federal_sources.run()
    logger.info("federal sources returned %d results", len(federal_results))

    logger.info("Step 1c: fetching RSS feeds")
    rss_results = rss_sources.run()
    logger.info("rss sources returned %d results", len(rss_results))

    # Merge all sources, deduplicating by URL
    seen_urls: set[str] = {r["url"] for r in raw_results if r.get("url")}
    for r in federal_results + rss_results:
        if r.get("url") and r["url"] not in seen_urls:
            seen_urls.add(r["url"])
            raw_results.append(r)

    sources_checked = len(raw_results)
    logger.info("total raw results after merge: %d", sources_checked)

    # 2. Deduplicate against Supabase
    logger.info("Step 2: deduplicating")
    urls = [r["url"] for r in raw_results if r.get("url")]
    seen_ids = deduplicator.read(urls)

    new_results = [
        r for r in raw_results
        if hashlib.sha256(r.get("url", "").encode()).hexdigest() not in seen_ids
    ]
    new_urls = {r["url"] for r in new_results if r.get("url")}
    logger.info("%d new (unseen) results after dedup", len(new_results))

    # 3. Early exit if fewer than 2 new results
    if len(new_results) < 2:
        logger.info("Fewer than 2 new results - sending no-new-grants email")
        deduplicator.log_search_results(raw_results, new_urls, set(), run_at)
        emailer.send_no_new_grants()
        sys.exit(0)

    # 4. Filter with Claude
    logger.info("Step 4: filtering with Claude")
    filter_note = ""
    filter_failed = False
    try:
        filtered_grants = grant_filter.run(new_results)
    except Exception as e:
        logger.error("Claude filter failed: %s - sending raw results", e)
        filtered_grants = new_results
        filter_note = "AI filtering was unavailable. Results below are unfiltered raw search results."
        filter_failed = True

    if not filtered_grants:
        logger.info("No grants passed filter - sending no-new-grants email")
        deduplicator.log_search_results(raw_results, new_urls, set(), run_at)
        emailer.send_no_new_grants()
        sys.exit(0)

    # 4b. Within-run title dedup: if two grants share the same normalized title key,
    # keep only the first (they're the same program at different URLs).
    if not filter_failed:
        seen_title_keys: set[str] = set()
        deduped: list[dict] = []
        for g in filtered_grants:
            key = deduplicator._title_key(g.get("title", ""))
            if key not in seen_title_keys:
                seen_title_keys.add(key)
                deduped.append(g)
        intra_run_suppressed = len(filtered_grants) - len(deduped)
        if intra_run_suppressed:
            logger.info("Step 4b: removed %d intra-run duplicate title(s)", intra_run_suppressed)
        filtered_grants = deduped

    # 4c. Suppress grants whose title was already sent in the last 30 days
    if not filter_failed:
        recent_titles = deduplicator.read_recent_titles(days=30)
        before = len(filtered_grants)
        filtered_grants = [
            g for g in filtered_grants
            if deduplicator._title_key(g.get("title", "")) not in recent_titles
        ]
        suppressed = before - len(filtered_grants)
        if suppressed:
            logger.info("Step 4c: suppressed %d repeat grant(s) seen in last 30 days", suppressed)

    if not filtered_grants:
        logger.info("All grants suppressed as recent or intra-run repeats - sending no-new-grants email")
        deduplicator.log_search_results(raw_results, new_urls, set(), run_at)
        emailer.send_no_new_grants()
        sys.exit(0)

    filtered_urls = {g["url"] for g in filtered_grants if g.get("url")}

    # 5. Send email digest
    logger.info("Step 5: sending email with %d grants", len(filtered_grants))
    try:
        emailer.send(
            filtered_grants,
            sources_checked=sources_checked,
            note=filter_note,
            filter_failed=filter_failed,
        )
    except Exception as e:
        logger.critical("Resend failed: %s", e, exc_info=True)
        sys.exit(1)

    # 6. Write new grants to Supabase and log all search results for audit
    logger.info("Step 6: writing %d grants to Supabase", len(filtered_grants))
    deduplicator.write(filtered_grants)
    deduplicator.log_search_results(raw_results, new_urls, filtered_urls, run_at)

    logger.info("Done - %d grants sent in digest", len(filtered_grants))


if __name__ == "__main__":
    main()
