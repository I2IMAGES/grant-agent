# Session Log — Grant Agent Build & Debug

**Date:** June 17–18, 2026  
**Project:** Inward2Onward LLC Daily Grant Discovery Agent  
**Branch:** `claude/vigilant-goodall-bq2jmm`

---

## What Was Built

A fully automated Python pipeline that runs daily on GitHub Actions to find, filter, and deliver grant opportunities to Inward2Onward LLC — a minority-owned, women-owned, HUBZone-eligible small business in Glendale, AZ.

**Stack:**
- Search: Serper API (Google Search)
- AI filtering: Anthropic Claude Haiku (`claude-haiku-4-5-20251001`) via direct HTTP
- Deduplication + audit log: Supabase (PostgreSQL)
- Email delivery: Resend
- Template: Jinja2 HTML
- Orchestration: GitHub Actions cron (7 AM MST daily)

---

## Bugs Encountered and Fixed

### 1. `UnicodeEncodeError: 'ascii' codec can't encode character ' '`
**Root cause:** GitHub Actions Ubuntu runner embeds a Unicode LINE SEPARATOR (` `) in its platform version string. The Anthropic Python SDK reads this into `x-stainless-*` headers. The `httpx` library (used internally by the SDK) encodes header values as ASCII, crashing on the non-ASCII character.

**Attempts that did NOT work:**
- `PYTHONIOENCODING=utf-8` env var
- Pinning `httpx>=0.27.0`
- Monkey-patching `httpx._models._normalize_header_value`
- Sanitizing the API key string

**Fix that worked:** Replaced the Anthropic SDK entirely with a direct `requests.post()` call to `https://api.anthropic.com/v1/messages`. No SDK = no stainless headers = no crash.

**File:** `agent/filter.py`

---

### 2. `searcher.py` Syntax Error (IndentationError)
**Root cause:** A previous edit closed the `SEARCH_QUERIES` list early (stray `]` on line 34), then left three orphaned strings before a second `]`. Python threw `IndentationError` on import, crashing the entire agent before filter.py ever ran — making it look like a filter problem.

**Fix:** Merged the orphaned queries into the main list and removed the duplicate closing bracket.

**File:** `agent/searcher.py`

---

### 3. CI Running Old Code Despite New Pushes
**Root cause:** The user was clicking "Re-run" on an existing GitHub Actions run. Re-runs always execute against the original commit SHA of that run, not the latest branch HEAD. The run in question (run #3) was first triggered against commit `632da477`, which predated the SDK-to-requests rewrite.

**Fix:** Always trigger a brand new run via **Actions → Run workflow → select branch → Run workflow**. Never re-run an old job when testing new code.

---

### 4. Supabase 401 Unauthorized
**Root cause:** The project has an `rls_auto_enable()` trigger that automatically enables Row Level Security on every new table. The initial `seen_grants` table was created with no RLS policies, so all operations were rejected.

**Fix:** Applied migration to create a service_role full-access policy:
```sql
CREATE POLICY "service_role full access" ON public.seen_grants
FOR ALL TO service_role USING (true) WITH CHECK (true);
```
Also changed the `deadline` column from `DATE` to `TEXT` (Claude returns free-form strings like "June 30, 2026", not ISO dates).

---

### 5. Non-ASCII Characters in Python Source Files
**Root cause:** Source files contained em dashes (`—`), middle dots (`·`), arrows, and emoji. On the GitHub Actions runner with ASCII stdout, the logging module itself crashed when trying to format messages containing these characters.

**Fix:** Replaced all non-ASCII literals across all `.py` files and the Jinja2 template with ASCII equivalents.

---

### 6. Fallback Email Showed Empty Sections
**Root cause:** When Claude filtering failed, the fallback showed raw results grouped by eligibility tags — but raw results have no eligibility tags, so all three sections (MINORITY-OWNED, WOMEN-OWNED, HUBZONE) showed "No new results."

**Fix:** Added a `filter_failed` boolean flag. When true, the template renders a flat "ALL RESULTS (UNFILTERED)" list instead of attempting grouped sections.

**Files:** `agent/emailer.py`, `agent/templates/digest.html`

---

### 7. Duplicate Grants Across Email Sections
**Root cause:** `_group_grants()` added each grant to every section whose tag appeared in the grant's eligibility list. A grant tagged `[MINORITY-OWNED, WOMEN-OWNED]` appeared twice in the email.

**Fix:** Rewrote `_group_grants()` to track seen URLs and assign each grant to the first matching section only.

**File:** `agent/emailer.py`

---

### 8. Expired Results and Informational Pages Passing Filter
**Root cause:** The original filter prompt said "filter OUT expired opportunities" without defining what expired means, and "filter OUT news articles" without distinguishing informational program pages.

**Fix:** Rewrote the prompt with:
- Explicit today's date (`June 17, 2026`)
- `HARD REJECT` language with concrete examples for each reject condition
- Explicit rejection of SBA.gov-style program description pages

**File:** `agent/filter.py`

---

### 9. Intermittent JSON Parse Error on One Batch
**Root cause:** Claude occasionally returns malformed JSON (two arrays concatenated, or trailing text after `]`). This caused one batch per run to be silently dropped.

**Fix:** Added retry logic — JSON parse errors retry up to 3 times before marking the batch as failed. Non-parse errors (network, auth) fail immediately since retrying won't help.

**File:** `agent/filter.py`

---

### 10. `anthropic` Package Still Installed Despite SDK Removal
**Root cause:** `anthropic` remained in `requirements.txt` after the SDK was replaced with direct `requests` calls. The pip cache (`cache: "pip"` in the workflow) was serving the cached package on every run.

**Fix:** Removed `anthropic` from `requirements.txt` and removed `cache: "pip"` from the workflow to guarantee a clean install.

**Files:** `requirements.txt`, `.github/workflows/daily_grant_run.yml`

---

## Search Query Evolution

**Initial:** Generic queries like "small business grant minority 2025" — returned results from Texas, South Carolina, Illinois, etc.

**Tightened to:**
- Arizona/Maricopa/Glendale geography explicit in every local query
- 2026 dates in every query
- Named federal programs (MBDA, EDA, USDA RBDG, DOT DBE)
- PTAC queries added (Procurement Technical Assistance Centers — helps with 8(a)/WOSB/HUBZone federal contracting)
- More Maricopa cities: Mesa, Tempe, Scottsdale, Chandler
- Added: Hello Alice, Amber Grant, Visa She's Next

---

## Monitoring Process Established

Going forward: after triggering a run, notify the AI assistant "run's done." It pulls:
1. GitHub Actions job logs via GitHub MCP (`get_job_logs`)
2. Supabase data via Supabase MCP

No screenshots required for debugging.

---

## Final State — Commit History

| Commit | Description |
|---|---|
| `b915795` | Retry batch up to 3x on JSON parse errors |
| `d5036bd` | Tighten filter, fix cross-section duplication, expand search queries |
| `4afd1f0` | Fix searcher.py syntax error, remove anthropic SDK, disable pip cache |
| `e52be55` | Sanitize API key with ASCII encoding |
| `7e8779e` | Add search_results audit log to Supabase |
| `0789f66` | Replace Anthropic SDK with direct requests call |
| `7b3bae4` | Fix UnicodeEncodeError: patch httpx header encoder |
| `84f328a` | Tighten search queries: Arizona-specific, 2026-dated |
| `78376b9` | Sanitize ANTHROPIC_API_KEY before use |
| `632da47` | Pin httpx>=0.27.0 |
| `04e5d27` | Fix filter.py batch error handling, add PYTHONIOENCODING |
| `f137f03` | Purge all non-ASCII from Python source files, fix fallback display |

---

## Open Items at Session End

- **ANTHROPIC_API_KEY secret:** Had a trailing ` ` character. User is replacing with a fresh key.
- **Filter prompt date:** `June 17, 2026` is hardcoded in `filter.py`. Should be updated periodically or made dynamic.
- **`any_batch_failed` flag:** When set, the fallback still sends filtered results (not fully unfiltered) — the partial results from successful batches are used. The warning email condition `if any_batch_failed and not all_grants` only raises an error if ALL batches failed.
