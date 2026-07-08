# Inward2Onward Grant Discovery Agent — SOP & Technical Documentation

**Version:** 2.0  
**Last Updated:** June 19, 2026  
**Owner:** Inward2Onward LLC — ai@inward2onward.com  
**Repository:** `I2IMAGES/grant-agent`  
**Active Branch:** `claude/vigilant-goodall-bq2jmm`

---

## Table of Contents

1. [Business Context](#1-business-context)
2. [System Overview](#2-system-overview)
3. [Pipeline Architecture](#3-pipeline-architecture)
4. [File Reference](#4-file-reference)
5. [Secrets & Environment Variables](#5-secrets--environment-variables)
6. [Supabase Database Schema](#6-supabase-database-schema)
7. [GitHub Actions Workflow](#7-github-actions-workflow)
8. [Email Digest Format](#8-email-digest-format)
9. [Monitoring & Troubleshooting](#9-monitoring--troubleshooting)
10. [How to Update Search Queries](#10-how-to-update-search-queries)
11. [How to Update the AI Filter Prompt](#11-how-to-update-the-ai-filter-prompt)
12. [How to Add or Remove RSS Feeds](#12-how-to-add-or-remove-rss-feeds)
13. [How to Trigger a Manual Run](#13-how-to-trigger-a-manual-run)
14. [How to Add Recipients](#14-how-to-add-recipients)
15. [External Service Accounts](#15-external-service-accounts)
16. [Dependency Reference](#16-dependency-reference)
17. [Commit & Deployment History](#17-commit--deployment-history)

---

## 1. Business Context

**Who:** Inward2Onward LLC, Glendale, AZ — minority-owned, women-owned small business. Qualifies for HUBZone certification.

**What:** Non-Medical Emergency Transportation (NMET) — transporting clients to medical appointments, treatment programs, social services, job training, and community resources.

**Why this agent exists:** Grant discovery is time-consuming manual work. This agent automates daily monitoring across federal, state, local, and private funding sources and delivers a curated digest every morning at 7 AM MST.

**Two opportunity types the agent looks for:**

| Type | Description | Email Section |
|------|-------------|---------------|
| **Direct Grants** | Inward2Onward applies directly as a minority-owned, women-owned, or HUBZone small business | MINORITY-OWNED / WOMEN-OWNED / HUBZONE |
| **Partnership Leads** | Grants awarded to nonprofits or agencies running programs that need client transportation — I2O subcontracts as the NMET provider | PARTNERSHIP |

---

## 2. System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    GITHUB ACTIONS (7 AM MST)                    │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │  searcher.py  │  │federal_sources│  │   rss_sources.py     │  │
│  │  (Serper /   │  │ grants.gov   │  │  14 RSS/Atom feeds   │  │
│  │  Google — 27 │  │ sam.gov APIs │  │  (gov + blogs)       │  │
│  │  queries)    │  │              │  │                      │  │
│  └──────┬───────┘  └──────┬───────┘  └──────────┬───────────┘  │
│         └─────────────────┴──────────────────────┘             │
│                           │ merge by URL                        │
│                    ┌──────▼──────┐                              │
│                    │deduplicator │  <- reads seen_grants (30d)  │
│                    │   .read()   │                              │
│                    └──────┬──────┘                              │
│                           │ new URLs only                       │
│                    ┌──────▼──────┐                              │
│                    │  filter.py  │  <- Claude Haiku AI          │
│                    │ (batches of │    scores relevance,         │
│                    │    20)      │    assigns tags,             │
│                    └──────┬──────┘    extracts amount/deadline  │
│                           │                                     │
│                    ┌──────▼──────┐                              │
│                    │title suppress│ <- dedup by title (7d)      │
│                    └──────┬──────┘                              │
│                           │                                     │
│                    ┌──────▼──────┐                              │
│                    │  emailer.py  │ -> HTML digest via Resend   │
│                    └──────┬──────┘                              │
│                           │                                     │
│                    ┌──────▼──────┐                              │
│                    │deduplicator │ -> writes seen_grants        │
│                    │  .write()   │    logs search_results       │
│                    └─────────────┘                              │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. Pipeline Architecture

### Step 1 — Search (Three Arms)

**1a. Serper (Google Search) — `searcher.py`**
- 27 targeted queries covering: Arizona local, PTAC, federal programs (SBA, MBDA, EDA, USDA, DOT, SBIR), corporate grants (Comcast RISE, FedEx, Goldman Sachs, Visa She's Next, Hello Alice, Amber Grant)
- Returns up to 10 organic results per query
- Deduplicates by URL within the run
- Requires: `SERPER_API_KEY`

**1b. Federal APIs — `federal_sources.py`**
- **Grants.gov v2 API** (`https://api.grants.gov/v2/api/search`) — 4 keyword searches, eligibility code 11 (Small Businesses), posted status only, sorted by openDate desc. No API key required.
- **SAM.gov v2 API** (`https://api.sam.gov/opportunities/v2/search`) — filters by set-aside codes: WOSB, EDWOSB, HZC (HUBZone), 8AN (8a), SBA. Last 30 days. Requires: `SAM_GOV_API_KEY` (optional — skipped if not set).

**1c. RSS Feeds — `rss_sources.py`**
- 14 RSS/Atom feeds covering government agencies, grant alert blogs, and Arizona sources
- Items published within last 30 days only
- HTML stripped from summaries; feed failures logged as WARNING and skipped silently
- Requires no API keys

**Feed list:**

| Feed | URL |
|------|-----|
| Grants.gov - Transportation | `grants.gov/rss/GG_NewOppByCategory.xml?category=TP` |
| Grants.gov - Health | `grants.gov/rss/GG_NewOppByCategory.xml?category=HL` |
| Grants.gov - Community Development | `grants.gov/rss/GG_NewOppByCategory.xml?category=CD` |
| SAMHSA Grant Announcements | `samhsa.gov/grants/grant-announcements/rss` |
| MBDA News & Grants | `mbda.gov/rss.xml` |
| SBA News | `sba.gov/rss/news` |
| HHS Grants | `hhs.gov/grants/rss/index.html` |
| USDA Rural Development | `rd.usda.gov/rss/rd-news-releases` |
| Seliger + Associates | `seliger.com/feed/` |
| Hello Alice | `helloalice.com/feed/` |
| Arizona Commerce Authority | `azcommerce.com/feed/` |
| GrantWatch Transportation | `grantwatch.com/cat/47/transportation-grants.html/feed/rss2/` |
| NonProfit Source | `nonprofitsource.com/feed/` |
| Arizona Foundation for Women | `azfw.org/feed/` |

All three arms are merged by URL before deduplication. Total raw results typically 150-250 per run.

---

### Step 2 — URL Deduplication (`deduplicator.read`)

- Computes SHA-256 hash of each URL
- Queries `seen_grants` table for hashes seen within last **30 days**
- Filters out already-seen URLs
- If fewer than 2 new results remain → sends "no new grants" email and exits

---

### Step 3 — AI Filter (`filter.py`)

- Sends batches of 20 results to **Claude Haiku** (`claude-haiku-4-5-20251001`) via direct `requests.post()` to `https://api.anthropic.com/v1/messages`
  - Note: Uses direct HTTP (not Anthropic SDK) to avoid U+2028 UnicodeEncodeError in httpx platform-detection headers on Linux runners
- System prompt instructs Claude to evaluate each result for:
  - TYPE 1 (Direct): minority-owned, women-owned, HUBZone direct applicant opportunities
  - TYPE 2 (Partnership): grants to nonprofits/agencies running programs that need NMET subcontractors
- Claude returns for each qualifying result: `title`, `url`, `snippet`, `summary`, `eligibility[]`, `amount`, `deadline`, `relevance_score`
- Only results with `relevance_score >= 0.5` are kept
- JSON parse errors retry up to 3 times; non-parse errors fail fast
- Today's date is injected dynamically so expired deadlines are rejected
- Requires: `ANTHROPIC_API_KEY`

**Eligibility tags:**

| Tag | Meaning |
|-----|---------|
| `MINORITY-OWNED` | Direct grant for minority-owned businesses |
| `WOMEN-OWNED` | Direct grant for women-owned businesses |
| `HUBZONE` | Direct grant/contract for HUBZone certified businesses |
| `PARTNERSHIP` | Nonprofit/agency grant where I2O can subcontract NMET |

---

### Step 4 — Title Suppression (`deduplicator.read_recent_titles`)

- Queries `seen_grants` for titles from last **7 days**
- Normalizes titles: lowercase, strip non-alphanumeric, take first 8 words
- Any grant whose normalized title matches a recent entry is suppressed
- Prevents the same opportunity from appearing on consecutive days even if the URL changed
- Only runs when Claude filtering succeeded (not when `filter_failed=True`)

---

### Step 5 — Email (`emailer.send`)

- Renders Jinja2 HTML template (`templates/digest.html`)
- Sends via Resend SDK from `grants@inward2onward.com`
- Subject: `Grant Digest - N New Opportunities - [Date]`
- Grants appear in exactly ONE section based on first matching tag
- Section order: MINORITY-OWNED → WOMEN-OWNED → HUBZONE → PARTNERSHIP
- If Claude filter failed: shows flat "ALL RESULTS (UNFILTERED)" list with warning banner
- Requires: `RESEND_API_KEY`, `RECIPIENT_EMAIL`

---

### Step 6 — Write to Supabase

- `deduplicator.write(filtered_grants)` — upserts final grants to `seen_grants`
- `deduplicator.log_search_results(...)` — inserts all raw results to `search_results` audit table with flags for which passed dedup and filter

---

## 4. File Reference

```
grant-agent/
├── agent/
│   ├── grant_agent.py        # Main orchestrator — runs Steps 1-6
│   ├── searcher.py           # Serper/Google search (27 queries)
│   ├── federal_sources.py    # Grants.gov + SAM.gov API calls
│   ├── rss_sources.py        # RSS/Atom feed ingestion (14 feeds)
│   ├── filter.py             # Claude Haiku AI filter
│   ├── deduplicator.py       # Supabase read/write/dedup
│   ├── emailer.py            # Resend email + Jinja2 template rendering
│   └── templates/
│       └── digest.html       # HTML email template
├── requirements.txt          # Python dependencies
├── .github/
│   └── workflows/
│       └── daily_grant_run.yml   # GitHub Actions cron job
└── docs/
    └── SOP-grant-agent.md    # This document
```

### Key constants (quick reference)

| File | Constant | Value | Purpose |
|------|----------|-------|---------|
| `filter.py` | `ANTHROPIC_MODEL` | `claude-haiku-4-5-20251001` | AI model used |
| `filter.py` | `BATCH_SIZE` | 20 | Results per Claude API call |
| `filter.py` | `MAX_FIELD_CHARS` | 500 | Max chars per field sent to Claude |
| `rss_sources.py` | `RECENCY_DAYS` | 30 | Max age of RSS items to include |
| `deduplicator.py` | (in `read()`) | 30 days | URL dedup window |
| `grant_agent.py` | (in Step 4b) | 7 days | Title suppression window |
| `emailer.py` | `ELIGIBILITY_GROUPS` | 4 tags | Order of email sections |

---

## 5. Secrets & Environment Variables

All secrets are stored in **GitHub → Settings → Secrets and variables → Actions**.

| Secret Name | Required | Description |
|-------------|----------|-------------|
| `ANTHROPIC_API_KEY` | Yes | Claude API key for AI filtering |
| `SERPER_API_KEY` | Yes | Serper.dev key for Google Search |
| `SUPABASE_URL` | Yes | Supabase project URL (e.g. `https://xxx.supabase.co`) |
| `SUPABASE_KEY` | Yes | Supabase service role key (anon key also works if RLS allows) |
| `RESEND_API_KEY` | Yes | Resend.com API key for email delivery |
| `RECIPIENT_EMAIL` | Yes | Email address(es) to receive the digest |
| `SAM_GOV_API_KEY` | No | SAM.gov free API key — skipped if not set. Register at sam.gov/profile/Details |
| `GRANTS_GOV_PROXY_URL` | No | Cloudflare Worker URL that proxies requests to api.grants.gov. GitHub Actions runner IPs are blocked by Grants.gov; this routes around the block. See §Grants.gov Proxy below. |

**To rotate a secret:** Go to GitHub repo → Settings → Secrets → click the secret → Update.

---

## 6. Supabase Database Schema

### Table: `seen_grants`

Tracks every grant sent in a digest. Used for URL deduplication (30-day) and title suppression (7-day).

```sql
CREATE TABLE seen_grants (
    grant_id       TEXT PRIMARY KEY,   -- SHA-256 of URL
    title          TEXT,
    url            TEXT,
    first_seen_at  TIMESTAMPTZ,
    last_seen_at   TIMESTAMPTZ,
    eligibility    TEXT[],             -- e.g. {MINORITY-OWNED, WOMEN-OWNED}
    amount         TEXT,
    deadline       TEXT
);
```

### Table: `search_results`

Audit log of every raw result from every run — useful for understanding what the agent found, even if it was filtered out.

```sql
CREATE TABLE search_results (
    id              BIGSERIAL PRIMARY KEY,
    run_at          TIMESTAMPTZ,
    source_query    TEXT,              -- which query or feed produced this result
    title           TEXT,
    url             TEXT,
    snippet         TEXT,
    passed_dedup    BOOLEAN,           -- true if URL was new (not seen in 30 days)
    passed_filter   BOOLEAN            -- true if Claude scored it >= 0.5 and it was emailed
);
```

**Useful audit queries:**

```sql
-- See what was sent in the last 7 days
SELECT title, url, eligibility, deadline
FROM seen_grants
WHERE last_seen_at > now() - interval '7 days'
ORDER BY last_seen_at DESC;

-- See what was found but rejected by filter on a specific run
SELECT title, url, source_query, snippet
FROM search_results
WHERE run_at::date = '2026-06-19'
  AND passed_dedup = true
  AND passed_filter = false;

-- See how many results each source produces over time
SELECT source_query, COUNT(*) as total,
       SUM(CASE WHEN passed_filter THEN 1 ELSE 0 END) as sent
FROM search_results
GROUP BY source_query
ORDER BY sent DESC;
```

---

## 7. GitHub Actions Workflow

**File:** `.github/workflows/daily_grant_run.yml`

**Schedule:** `0 14 * * *` = 7:00 AM MST (14:00 UTC) every day

**Manual trigger:** GitHub → Actions → "Daily Grant Discovery" → "Run workflow"

**Steps:**
1. Checkout repo
2. Set up Python 3.11
3. `pip install -r requirements.txt`
4. `python grant_agent.py` (working-directory: `agent/`)

**Environment variables passed:** All secrets listed in Section 5.

**PYTHONIOENCODING:** Set to `utf-8` to prevent encoding errors on Linux runners.

**There must be exactly ONE workflow file.** A duplicate `main.yml` was deleted in June 2026 — it was causing double runs. Never add a second workflow that calls the same script.

---

## 8. Email Digest Format

**Sender:** `grants@inward2onward.com`
**Subject:** `Grant Digest - N New Opportunities - [Date]`
**Platform:** Resend.com

### Sections (in order)

1. **Header** — "Daily Grant Digest" + date
2. **Stats bar** — "N new grants found | N sources checked"
3. **Note banner** (if filter failed) — yellow warning about unfiltered results
4. **MINORITY-OWNED** — Direct grants for minority-owned businesses (blue heading)
5. **WOMEN-OWNED** — Direct grants for women-owned businesses (blue heading)
6. **HUBZONE** — HUBZone set-asides and federal contracts (blue heading)
7. **PARTNERSHIP** — Nonprofit/agency grants needing NMET subcontractors (purple heading)
   - Subhead: "Grants awarded to nonprofits or agencies that may need NMET subcontractors — contact the awardee organization to offer transportation services."
8. **Footer** — Inward2Onward contact info

### Grant card contents
- Title (linked to grant URL)
- Amount pill (green)
- Deadline pill (yellow)
- Summary (2-3 sentences on fit for I2O)
- "View Grant" button

### Fallback mode
If Claude filtering fails entirely, the email shows all raw results in a flat "ALL RESULTS (UNFILTERED)" list with a warning banner. This ensures something is always delivered even when the AI is unavailable.

### "No new grants" email
Sent when: fewer than 2 new URLs after dedup, or all results fail Claude filter, or all results suppressed as recent repeats.
Subject: `Grant Digest - No New Results - [Date]`

---

## 9. Monitoring & Troubleshooting

### Where to check run status

**GitHub Actions logs:**
`github.com/I2IMAGES/grant-agent/actions` → click latest "Daily Grant Discovery" run

### Key log lines to look for

```
searcher: N unique results from 27 queries
federal_sources: N results from grants.gov
rss_sources: "Feed Name" HTTP 200, N entries       <- per-feed status (new)
rss_sources: N unique items from 14 feeds (last 30 days)
total raw results after merge: N
N new (unseen) results after dedup
filter: cleaned N results, sending in batches of 20
filter: batch 1 - N grants passed threshold
filter: N/N results passed (any_batch_failed=False)
Step 4b: suppressed N repeat grant(s) seen in last 7 days
emailer: sent digest to *** (N grants)
deduplicator.write: upserted N rows
deduplicator.log_search_results: logged N rows
Done - N grants sent in digest
```

### Common issues

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| `filter: batch N attempt N error` | Expired/invalid ANTHROPIC_API_KEY | Rotate key in GitHub Secrets |
| `emailer` step fails | Expired RESEND_API_KEY | Rotate key in Resend dashboard |
| `Supabase connection failed` | Bad SUPABASE_URL or SUPABASE_KEY | Check secrets; URL must not have trailing slash |
| RSS feeds all return 0 items | Recency too strict or feeds quiet | RECENCY_DAYS is now 30; check per-feed HTTP log lines |
| `rss_sources: "X" HTTP 404` | Dead feed URL | Update or remove that feed in `rss_sources.py` |
| Digest arrives twice | Duplicate workflow files | Only one `.yml` should exist in `.github/workflows/` |
| All results filtered out | Prompt too strict or API quota hit | Check Claude API dashboard; review prompt |
| Same grants repeating daily | Title suppression not catching them | Check `seen_grants` table; may need to widen title key |
| `grants.gov search failed` | API structure changed | Check `https://api.grants.gov/v2/api/search` response format |

### Checking Supabase directly

Go to `app.supabase.com` → your project → Table Editor → `seen_grants` or `search_results`.

---

## 10. How to Update Search Queries

**File:** `agent/searcher.py` — `SEARCH_QUERIES` list

To add a query:
```python
SEARCH_QUERIES = [
    ...
    "new search term here 2026 apply open",
]
```

Rules for good queries:
- Include the year (e.g., `2026`) to get current results
- Include action words (`apply`, `open`, `deadline`, `application open`)
- Scope to geography where relevant (`Arizona`, `Maricopa County`, `Glendale`)
- Include eligibility terms (`minority-owned`, `women-owned`, `HUBZone`, `WOSB`)
- Keep to ~27 queries max — each costs 1 Serper API credit (~$0.001)

After editing, commit and push. The change takes effect on the next scheduled run.

---

## 11. How to Update the AI Filter Prompt

**File:** `agent/filter.py` — `_SYSTEM_PROMPT_TEMPLATE` string

Today's date is injected automatically via `{today}` — do not hardcode a date.

**Key things you can adjust:**

**Change the relevance threshold** (line in `_call_claude`):
```python
return [g for g in grants if g.get("relevance_score", 0) >= 0.5]
```
Raise to `0.6` → fewer, higher-confidence results. Lower to `0.4` → wider net.

**Add a new direct grant category:**
Add a new eligibility tag and describe it in the TYPE 1 section. Then:
1. Add the tag to `ELIGIBILITY_GROUPS` in `emailer.py`
2. Add a corresponding section in `digest.html`

**Change the AI model:**
```python
ANTHROPIC_MODEL = "claude-haiku-4-5-20251001"
```
Switch to `claude-sonnet-4-6` for higher quality (costs ~5x more, runs slower). Haiku is sufficient for structured extraction tasks.

**Add explicit program examples to the PARTNERSHIP section:**
This helps Claude recognize more subcontracting opportunities. Add bullet points like:
- "Emergency transportation programs funded by FEMA or state emergency management"
- "Immigrant integration programs (transportation to ESL classes, benefits offices)"

---

## 12. How to Add or Remove RSS Feeds

**File:** `agent/rss_sources.py` — `RSS_FEEDS` list

```python
RSS_FEEDS = [
    ("Feed Label", "https://example.com/feed.xml"),
    ...
]
```

- Each entry is `(label, url)` — label appears in logs and the `source_query` field in Supabase
- To remove a feed: delete its line
- To test if a URL is valid: open it in a browser — it should return XML
- Feed failures are silent (logged as WARNING, skipped) so bad URLs will not break the run
- `RECENCY_DAYS = 30` — items older than 30 days are excluded; the deduplicator prevents re-sending

**Good sources to consider adding:**
- State foundation newsletters that publish RSS
- Local government news feeds (City of Glendale, Maricopa County)
- Industry association grant alerts (CTAA — Community Transportation Association of America)
- Corporate foundation news feeds (Annie E. Casey Foundation, Robert Wood Johnson Foundation)

---

## 13. How to Trigger a Manual Run

**Option A — GitHub UI (recommended):**
1. Go to `github.com/I2IMAGES/grant-agent/actions`
2. Click "Daily Grant Discovery" in the left sidebar
3. Click "Run workflow" button (top right) → "Run workflow"
4. Starts within 30 seconds

**Option B — Push any commit to the branch:**
Any push to `claude/vigilant-goodall-bq2jmm` also triggers the workflow.

---

## 14. How to Add Recipients

**Current setup:** Single recipient via `RECIPIENT_EMAIL` secret.

**To add multiple recipients**, update the secret to a comma-separated list:
```
ej@inward2onward.com,ai@inward2onward.com
```

Then update `emailer.py` to split on commas:
```python
recipient = os.environ["RECIPIENT_EMAIL"]
to_list = [addr.strip() for addr in recipient.split(",") if addr.strip()]
params = {
    "from": "grants@inward2onward.com",
    "to": to_list,
    ...
}
```

For a full subscriber list with unsubscribe links, consider Resend's Audiences feature (Resend Pro plan).

---

## 15. External Service Accounts

| Service | Purpose | Cost Estimate | Notes |
|---------|---------|---------------|-------|
| Anthropic | Claude Haiku AI filtering | ~$0.01-0.05/run | `claude-haiku-4-5-20251001` |
| Serper.dev | Google Search API (27 queries/run) | ~$0.03/run | 2,500 free searches/month |
| Resend.com | Email delivery | Free (3,000/month) | 1 email per run |
| Supabase | Deduplication + audit database | Free (up to 500MB) | Grows ~10KB/day |
| SAM.gov | Federal contract set-asides | Free | Register at sam.gov/profile/Details |
| GitHub | Actions runner + repo hosting | Free (public repo) | 2,000 min/month free |

**Monthly cost estimate:** $2-5/month at daily runs with typical result volumes.

---

## 16. Dependency Reference

**File:** `requirements.txt`

| Package | Version | Purpose |
|---------|---------|---------|
| `httpx` | >=0.27.0 | HTTP client (used by supabase SDK) |
| `supabase` | latest | Supabase Python client for database operations |
| `resend` | latest | Resend email delivery SDK |
| `requests` | latest | HTTP for Serper, Grants.gov, SAM.gov, RSS |
| `python-dotenv` | latest | `.env` file loading for local development |
| `jinja2` | latest | HTML email template rendering |
| `feedparser` | latest | RSS/Atom feed parsing |

**Note:** The `anthropic` Python SDK is intentionally NOT installed. `filter.py` calls the Anthropic API directly via `requests.post()` to avoid a U+2028 UnicodeEncodeError that occurs in the SDK's httpx-based platform detection headers on Linux GitHub Actions runners.

---

## 17. Commit & Deployment History

| Date | Commit | Description |
|------|--------|-------------|
| 2026-06-17 | — | Initial pipeline: Serper → Claude SDK → Resend |
| 2026-06-17 | — | Fix: UnicodeEncodeError — switched from Anthropic SDK to direct `requests.post()` |
| 2026-06-17 | — | Fix: AI filter returning 0 results — rewrote system prompt with specific I2O profile |
| 2026-06-17 | — | Add: batch retry logic (3 attempts on JSON parse errors, fail-fast on others) |
| 2026-06-17 | — | Add: 27 Serper search queries; Supabase audit logging (`search_results` table) |
| 2026-06-18 | — | Add: title-based repeat suppression (7-day normalized key matching) |
| 2026-06-18 | — | Add: Grants.gov v2 API + SAM.gov v2 API (`federal_sources.py`) |
| 2026-06-18 | — | Add: RSS/Atom feed ingestion (`rss_sources.py`, 11 feeds initially) |
| 2026-06-18 | — | Add: PARTNERSHIP lane — new eligibility tag, purple email section, updated AI prompt |
| 2026-06-19 | `97cc365` | Fix: deleted duplicate `main.yml` workflow (was causing double runs at 6:22 and 8:05) |
| 2026-06-19 | `b4facba` | Fix: RSS RECENCY_DAYS 7→30; per-feed HTTP logging; 3 category Grants.gov feeds; GrantWatch; NonProfit Source added; filter date now dynamic |

---

## Appendix A: Local Development Setup

To run the agent locally for testing:

```bash
# Clone the repo
git clone https://github.com/I2IMAGES/grant-agent.git
cd grant-agent

# Create .env file in agent/ directory
cat > agent/.env << EOF
ANTHROPIC_API_KEY=sk-ant-...
SERPER_API_KEY=...
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_KEY=...
RESEND_API_KEY=re_...
RECIPIENT_EMAIL=your@email.com
SAM_GOV_API_KEY=...
EOF

# Install dependencies
pip install -r requirements.txt

# Run
cd agent
python grant_agent.py
```

Logs print to stdout. The email will be sent to `RECIPIENT_EMAIL`.

---

## Appendix B: NMET Partnership Strategy

The PARTNERSHIP lane is designed around this business logic:

> Inward2Onward cannot always apply directly for every grant. But when a nonprofit, government agency, or healthcare provider receives a grant to run a client services program — substance abuse treatment, workforce development, senior services, etc. — they need transportation for their clients. That is the I2O entry point: subcontract as the NMET provider.

**How to act on a PARTNERSHIP lead:**
1. Read the summary in the email — it explains what program is funded and how I2O fits
2. Identify the awardee organization (check USASPENDING.gov or SAM.gov awards if needed)
3. Contact the awardee's program director to offer NMET subcontracting
4. Lead with I2O's certifications (minority-owned, women-owned, HUBZone-eligible) — these help the awardee meet their own diversity/inclusion requirements

**Best PARTNERSHIP target program types:**

| Program Type | Typical Funder | Transportation Need |
|-------------|---------------|-------------------|
| Substance abuse / mental health treatment | SAMHSA | Daily transport to treatment sites |
| Workforce development / job training | DOL, EDA | Transport to training centers |
| Foster care / family support | HHS, ACF | Transport to services and visitation |
| Senior services / home health | ACL, CMS | Medical and errand transport |
| Housing / homelessness services | HUD | Transport to shelters and appointments |
| Refugee resettlement | ORR, State Dept | Transport to schools, agencies, jobs |
| Community health / healthcare access | HRSA, FQHC | Transport to clinics and pharmacies |

---

---

## Appendix C: Grants.gov Proxy Setup

GitHub Actions runner IPs (hosted on Azure/AWS data centers) are blocked by `api.grants.gov` with a 403 Forbidden response. The fix is to route the 5 daily Grants.gov API calls through a Cloudflare Worker, which runs on Cloudflare's IP range and is not blocked.

### Why Cloudflare Workers

- **Free tier** — 100,000 requests/day; the agent uses 5/day
- **No server to maintain** — serverless, always on
- **Sub-10ms overhead** — Cloudflare edge is fast
- **Cloudflare IPs are not blocked** by Grants.gov

---

### Step 1 — Create a Cloudflare account

Go to [cloudflare.com](https://cloudflare.com) → Sign Up → Free plan. No credit card required for the Workers free tier.

---

### Step 2 — Create the Worker

1. In the Cloudflare dashboard, go to **Workers & Pages** → **Create** → **Create Worker**
2. Name it `grants-gov-proxy`
3. Click **Deploy**
4. Click **Edit Code** and replace all contents with:

```javascript
export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    // Only proxy POST requests to /v2/api/ — block everything else
    if (request.method !== "POST" || !url.pathname.startsWith("/v2/api/")) {
      return new Response("Not found", { status: 404 });
    }

    const target = "https://api.grants.gov" + url.pathname + url.search;

    const proxied = new Request(target, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0",
      },
      body: request.body,
    });

    const resp = await fetch(proxied);
    return new Response(resp.body, {
      status: resp.status,
      headers: { "Content-Type": "application/json" },
    });
  },
};
```

5. Click **Save and Deploy**
6. Copy the Worker URL — it looks like:  
   `https://grants-gov-proxy.YOUR-SUBDOMAIN.workers.dev`

---

### Step 3 — Add the secret to GitHub Actions

1. In the `i2images/grant-agent` repository → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**
2. Name: `GRANTS_GOV_PROXY_URL`
3. Value: your Worker URL (e.g. `https://grants-gov-proxy.abc123.workers.dev`)
4. Click **Add secret**

---

### Step 4 — Verify it's working

On the next scheduled run (or trigger a manual run), the logs should show:

```
federal_sources: N results from grants.gov
```

instead of the previous:

```
grants.gov search failed for '...': 403 Client Error: Forbidden
```

If you still see 403 after adding the proxy, check the Worker's **Logs** tab in the Cloudflare dashboard to confirm requests are arriving. If they are but Grants.gov is still returning 403, Grants.gov may have also blocked Cloudflare's IP range in your region — in that case, use Option B below.

---

### Option B — Self-Hosted VPS Proxy (Fallback)

If Cloudflare Workers also gets blocked, spin up a $6/month VPS with a static residential-class IP:

**Providers:** DigitalOcean Droplet, Linode Nanode, Vultr Cloud Compute (all ~$6/month)

**On the VPS, install a simple HTTP proxy:**

```bash
# Ubuntu/Debian
sudo apt-get install -y tinyproxy
sudo sed -i 's/^Allow 127.0.0.1/Allow 0.0.0.0/' /etc/tinyproxy/tinyproxy.conf
sudo systemctl restart tinyproxy
```

**Add to GitHub Actions secrets:**
- Name: `HTTPS_PROXY`
- Value: `http://YOUR_VPS_IP:8888`

The `requests` library in Python automatically uses `HTTPS_PROXY` if it is set in the environment — no code changes required.

**Note:** A self-hosted VPS requires monthly payment and occasional OS maintenance. Cloudflare Workers is preferred for a zero-maintenance setup.

---

### Option C — GitHub Actions Self-Hosted Runner (Most Reliable)

If you have a computer at the I2O office with a residential internet connection, you can run the GitHub Actions job on that machine instead of GitHub's hosted runners. Residential IPs are not blocked by Grants.gov.

**Steps:**
1. In the repository → **Settings** → **Actions** → **Runners** → **New self-hosted runner**
2. Follow the installation instructions for your OS (Linux/macOS/Windows)
3. In `.github/workflows/daily_grant_run.yml`, change:
   ```yaml
   runs-on: ubuntu-latest
   ```
   to:
   ```yaml
   runs-on: self-hosted
   ```
4. The runner must be online at 7 AM MST daily for the cron to execute

**Tradeoff:** Zero proxy cost and the most reliable IP solution, but the office computer must be on and connected. A dedicated Raspberry Pi ($35 one-time) works well for this.

---

*For questions or to request changes to this document, contact ai@inward2onward.com.*
