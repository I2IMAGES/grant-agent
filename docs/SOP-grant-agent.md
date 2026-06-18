# Grant Discovery Agent — Standard Operating Procedure

**Organization:** Inward2Onward LLC, Glendale, AZ  
**System:** Automated daily grant discovery pipeline  
**Last Updated:** June 18, 2026

---

## Overview

The grant agent runs once daily via GitHub Actions at 7:00 AM MST (14:00 UTC). It searches for grant opportunities relevant to Inward2Onward's eligibility profile, filters results using Claude AI, and delivers a formatted email digest.

**Eligibility profile:**
- Minority-owned business (MBE)
- Women-owned small business (WOSB / EDWOSB)
- HUBZone certified (Glendale, AZ)

---

## Pipeline Steps

```
Search (Serper) → Deduplicate (Supabase) → Filter (Claude AI) → Email (Resend) → Log (Supabase)
```

### Step 1 — Search
- **File:** `agent/searcher.py`
- Runs 27 queries against the Serper Google Search API
- Query categories: Arizona/Maricopa local, PTAC/federal programs, corporate/foundation grants
- Deduplicates by URL within a single run; returns up to ~220 unique results

### Step 2 — Deduplicate
- **File:** `agent/deduplicator.py`
- Checks Supabase `seen_grants` table for URLs seen within the last 30 days
- Skips anything already sent; passes only new results forward
- If fewer than 2 new results, sends a "no new grants" email and exits

### Step 3 — Filter (Claude AI)
- **File:** `agent/filter.py`
- Sends new results to Claude Haiku in batches of 20
- Claude scores each result 0.0–1.0 for relevance; only results >= 0.5 pass
- Claude extracts: title, summary, eligibility tags, amount, deadline
- Hard rejects: expired deadlines, news articles, informational overview pages, loans, non-profits only
- Each batch retries up to 3 times on JSON parse errors
- If all batches fail, falls back to sending raw unfiltered results with a warning banner

### Step 4 — Email
- **File:** `agent/emailer.py`, `agent/templates/digest.html`
- Sends HTML digest via Resend to `RECIPIENT_EMAIL`
- Grants grouped by eligibility: MINORITY-OWNED / WOMEN-OWNED / HUBZONE
- Each grant appears in exactly one section (first matching tag)
- Subject: `Grant Digest - {N} New Opportunities - {date}`

### Step 5 — Log
- **File:** `agent/deduplicator.py`
- Upserts filtered grants into `seen_grants` (prevents re-sending for 30 days)
- Inserts all 200+ raw search results into `search_results` for audit

---

## Repository Structure

```
grant-agent/
├── .github/workflows/
│   └── daily_grant_run.yml     # GitHub Actions cron workflow
├── agent/
│   ├── grant_agent.py          # Main orchestrator
│   ├── searcher.py             # Serper API search
│   ├── deduplicator.py         # Supabase read/write
│   ├── filter.py               # Claude AI filtering
│   ├── emailer.py              # Resend email delivery
│   └── templates/
│       └── digest.html         # Jinja2 HTML email template
├── docs/
│   ├── SOP-grant-agent.md      # This file
│   └── session-log-2026-06-17.md
└── requirements.txt
```

---

## Required Secrets (GitHub Repository Settings → Secrets)

| Secret | Description |
|---|---|
| `ANTHROPIC_API_KEY` | Claude API key (Haiku model) |
| `SERPER_API_KEY` | Serper Google Search API key |
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_KEY` | Supabase service_role key (not anon key) |
| `RESEND_API_KEY` | Resend email API key |
| `RECIPIENT_EMAIL` | Delivery address for the digest |

> **Important:** Always use the `service_role` key for Supabase, not the `anon` key. The anon key will be blocked by Row Level Security policies.

---

## Supabase Tables

### `seen_grants`
Prevents re-sending the same grant within 30 days.

| Column | Type | Notes |
|---|---|---|
| `grant_id` | TEXT (PK) | SHA-256 hash of URL |
| `title` | TEXT | |
| `url` | TEXT | |
| `first_seen_at` | TIMESTAMPTZ | |
| `last_seen_at` | TIMESTAMPTZ | Used for 30-day cutoff |
| `eligibility` | TEXT[] | e.g. `{MINORITY-OWNED, WOMEN-OWNED}` |
| `amount` | TEXT | Nullable |
| `deadline` | TEXT | Nullable |

RLS enabled — service_role has full access policy.

### `search_results`
Audit log of every raw search result from every run.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID (PK) | Auto-generated |
| `run_at` | TIMESTAMPTZ | |
| `source_query` | TEXT | Which search query produced this result |
| `title` | TEXT | |
| `url` | TEXT | |
| `snippet` | TEXT | |
| `passed_dedup` | BOOLEAN | True if not seen in last 30 days |
| `passed_filter` | BOOLEAN | True if Claude scored >= 0.5 |

RLS disabled on this table.

---

## Monitoring a Run

### Preferred method (no screenshots needed)
After triggering a run, notify the AI assistant "run's done." It will:
1. Pull GitHub Actions job logs via the GitHub MCP
2. Query Supabase `search_results` and `seen_grants` via the Supabase MCP
3. Report: query count, new results, batch pass/fail counts, grants sent

### What to look for in logs
- `searcher: N unique results from 26 queries` — healthy if N > 100
- `N new (unseen) results after dedup` — low counts mean most results are already seen
- `filter: batch X - N grants passed threshold` — each batch should pass 0–5 grants
- `JSON parse error` on a batch — will auto-retry up to 3 times
- `emailer: sent digest to *** (N grants)` — confirms delivery
- `deduplicator.write: upserted N rows` — confirms Supabase write

### Red flags
- `ANTHROPIC_API_KEY: *** ` in the log — API key has a trailing Unicode character; regenerate and re-add the secret
- `All Claude filter batches failed` — filter fell back to raw results; check API key validity
- `Supabase connection failed` — verify `SUPABASE_URL` and `SUPABASE_KEY` secrets; must be service_role key

---

## Triggering a Manual Run

1. Go to the repository on GitHub
2. Click **Actions** tab
3. Click **Daily Grant Discovery** in the left sidebar
4. Click **Run workflow** dropdown (top right of runs list)
5. Select branch `claude/vigilant-goodall-bq2jmm`
6. Click **Run workflow**

> **Do not use "Re-run"** on an existing run — that re-runs the old commit, not the latest code.

---

## Updating Search Queries

Edit `agent/searcher.py` — the `SEARCH_QUERIES` list. Guidelines:
- Keep queries specific: include year (2026), geography (Arizona/Maricopa/Glendale), and action words ("apply", "open", "deadline")
- Avoid generic queries — they return informational pages Claude will reject anyway
- After editing, run `python3 -c "import ast; ast.parse(open('agent/searcher.py').read()); print('OK')"` locally to check syntax before committing

## Updating the Filter Prompt

Edit `SYSTEM_PROMPT` in `agent/filter.py`. The date `June 17, 2026` is hardcoded — update it periodically or make it dynamic if the agent runs for many months.

---

## Development Branch

All changes are committed and pushed to:
```
claude/vigilant-goodall-bq2jmm
```
This is the default branch. The GitHub Actions workflow checks out this branch on every run.
