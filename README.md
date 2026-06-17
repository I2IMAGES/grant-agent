# Inward2Onward Grant Discovery Agent

Automated daily agent that discovers grant opportunities for minority-owned, women-owned, and HUBZone-eligible small businesses. Runs searches via Serper, filters results with Claude AI, deduplicates via Supabase, and delivers a branded HTML digest via Resend.

## Architecture

```
grant_agent.py        # orchestrator
├── searcher.py       # Serper API → raw results
├── deduplicator.py   # Supabase seen_grants table
├── filter.py         # Claude Haiku relevance scoring
└── emailer.py        # Resend HTML digest
    └── templates/digest.html
```

## Setup

### 1. Clone and install dependencies

```bash
git clone <repo-url>
cd grant-agent
pip install -r requirements.txt
```

### 2. Configure environment variables

```bash
cp .env.example .env
# Edit .env and fill in all values
```

| Variable | Description |
|---|---|
| `ANTHROPIC_API_KEY` | From console.anthropic.com |
| `SERPER_API_KEY` | From serper.dev |
| `SUPABASE_URL` | Your Supabase project URL |
| `SUPABASE_KEY` | Supabase service role key (or anon key with RLS off) |
| `RESEND_API_KEY` | From resend.com |
| `RECIPIENT_EMAIL` | Email address to receive digests |

### 3. Create the Supabase table

Run this SQL in your Supabase SQL editor:

```sql
CREATE TABLE seen_grants (
  grant_id    TEXT PRIMARY KEY,
  title       TEXT,
  url         TEXT,
  first_seen_at TIMESTAMPTZ DEFAULT now(),
  last_seen_at  TIMESTAMPTZ DEFAULT now(),
  eligibility TEXT[],
  amount      TEXT,
  deadline    TEXT
);
```

### 4. Verify your Resend sending domain

Ensure `grants@inward2onward.com` is a verified sending address in your Resend dashboard.

## Running Locally

```bash
cd agent
python grant_agent.py
```

Logs stream to stdout. The agent will:
1. Run 20 Serper search queries
2. Deduplicate against Supabase (skipped gracefully if unavailable)
3. Filter results with Claude Haiku
4. Send an HTML digest email
5. Write new grants back to Supabase

## GitHub Actions

The workflow at `.github/workflows/daily_grant_run.yml` runs automatically at **7:00 AM MST** every day.

### Add GitHub Secrets

Go to `Settings → Secrets and variables → Actions → New repository secret` and add:

- `ANTHROPIC_API_KEY`
- `SERPER_API_KEY`
- `SUPABASE_URL`
- `SUPABASE_KEY`
- `RESEND_API_KEY`
- `RECIPIENT_EMAIL`

### Manual Trigger

Go to `Actions → Daily Grant Discovery → Run workflow` to trigger immediately.

## Error Handling

| Failure | Behavior |
|---|---|
| Individual search query fails | Logged, continues with remaining queries |
| Supabase unavailable | Logged, deduplication skipped, agent continues |
| Claude API fails | Logged, raw results used with warning note in email |
| Resend fails | Full traceback logged, exit code 1 (fails the CI job) |
| Fewer than 2 new grants | "No new grants" email sent, clean exit |
