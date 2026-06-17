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
import deduplicator
import filter as grant_filter
import emailer


def main() -> None:
    run_at = datetime.now(timezone.utc).isoformat()

    # 1. Search
    logger.info("Step 1: running searcher")
    raw_results = searcher.run()
    sources_checked = len(raw_results)
    logger.info("searcher returned %d raw results", sources_checked)

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
