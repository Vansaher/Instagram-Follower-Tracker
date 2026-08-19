# Instagram Follower Tracker — Project Brief

## 1. Purpose

Track daily follower counts for a list of ~hundreds of public/competitor
Instagram pages (not owned/managed by us), log the history over time, and
compute day-over-day follower change. Output goes into a CSV (source of
truth / history log) and an Excel report (human-readable daily summary
with deltas).

## 2. Why this approach (context for whoever picks this up)

- Meta's official Instagram Graph API **cannot** be used here: it only
  exposes `followers_count` for accounts we own/manage as a
  Business/Creator account via OAuth. It has no endpoint for arbitrary
  public or competitor accounts, and no follower-list endpoint at all.
- Since our target accounts are public/competitor pages we don't control,
  we need a **third-party Instagram data API** that already handles
  scraping, proxy rotation, and anti-ban logic on their infrastructure.
- This is a plain, repetitive, structured data-pull task (one number per
  username, once a day) — **not** a job for an LLM agent or browser
  automation. Agents/browser automation add cost, latency, and fragility
  with zero benefit here. A scheduled script + API call is the right
  shape of solution.

## 3. Data provider

Use a pay-per-request Instagram data API. Recommended starting options
(pick one, start with the free tier to validate before committing):

- **Apify** — "Instagram Profile Scraper" actor. Easiest to start, no
  proxy setup needed, good batch support for hundreds of usernames.
- **HikerAPI** — cheapest per-request (from ~$0.0006/request), 100+
  IG-specific endpoints, 100 free requests to test.
- EnsembleData / RocketAPI — for if volume grows well beyond current
  scale.

At ~300 accounts checked daily, expect roughly $5–30/month depending on
provider — cheap enough that reliability matters more than price.

**Action needed before building:** sign up for the chosen provider, get
an API key, confirm the exact endpoint + response shape (field name for
follower count may differ per provider) by testing on 2–3 accounts.

## 4. Inputs

`accounts.csv` — master list of target usernames, one per row:

```csv
username
natgeo
nasa
nike
```

## 5. Workflow (daily run)

1. Read `accounts.csv` for the current list of usernames to track.
2. For each username, call the provider's profile endpoint to get the
   current follower count. Handle errors/rate limits gracefully (retry
   with backoff; log and skip accounts that fail rather than crashing
   the whole run).
3. Append one row per account to `history.csv` (this file grows forever,
   one row per account per day):

   ```csv
   date,username,follower_count
   2026-08-18,natgeo,280100000
   2026-08-18,nasa,98500000
   ```

4. After the day's pull is appended, generate `daily_report.xlsx` from
   `history.csv`:
   - One row per tracked account
   - Columns: username, today's count, yesterday's count, change
     (absolute), change (%)
   - Sort by absolute change descending, so biggest movers are visible
     at a glance
5. Write the same results to a **Google Sheet** (via the Sheets API) so
   the non-technical operator has one always-current view — see section
   6a for the full operator-facing design. `daily_report.xlsx` can still
   be generated as a local/repo artifact for anyone technical who wants
   the raw file, but the Sheet is the primary interface for the operator.
6. (Optional, later) Post a Slack or email digest of the day's biggest
   movers, so the operator doesn't even need to open the Sheet to catch
   major changes.

## 6. Scheduling & hosting

Run daily, unattended, with zero server maintenance:

- **GitHub Actions** scheduled workflow (`cron` trigger) — free, runs on
  GitHub's infrastructure, survives laptops being off, nobody has to
  remember to run it. This is the default choice.
- Cron job on a small always-on VPS is an alternative only if logic
  outgrows Actions' run-time limits — not needed at current scale.
- Zapier/Make and similar no-code schedulers were considered and
  rejected: looping a paid API call over hundreds of usernames isn't
  what they're built for, and cost scales badly at this call volume.

## 6a. Operator-facing design (the app will not be run by the builder)

The person running this day-to-day is non-technical and should never
need to touch code, GitHub, or a CSV file directly. The **Google Sheet
becomes the control panel**, not just an output:

- **"Accounts" tab** — operator adds/removes usernames by editing rows
  directly in the sheet. This *replaces* `accounts.csv` as the live
  source of truth for which usernames get tracked (the repo copy, if
  kept, is just a backup/seed list).
- **"Report" tab** — today's snapshot + deltas, auto-refreshed daily.
  This is the same output described in section 5.
- **"Log" tab** — one row appended per run: timestamp, number of
  accounts processed, any errors, success/fail status. Gives the
  operator visibility with no logs or code to read.

**Manual on-demand runs — "▶ Run Scan Now" button:**

Add a custom menu item inside the Sheet via Google Apps Script. When
clicked, it calls the GitHub API (`workflow_dispatch` /
`repository_dispatch`, using an access token scoped only to this
workflow) to trigger the same script immediately, outside the daily
schedule. The operator never sees GitHub, YAML, or code — just a button
in a spreadsheet they already know how to use.

```
Operator clicks "Run Scan Now" in Google Sheet
   → Apps Script calls GitHub API to trigger the workflow immediately
   → fetch_followers.py runs (identical logic to the daily cron run)
   → reads usernames from the "Accounts" tab
   → writes results to "Report" tab + appends a row to "Log" tab
```

The daily cron trigger and the manual button call the same underlying
script — no duplicate logic to maintain.

**Simpler fallback (if a Sheets button is more than needed):** use
GitHub Actions' built-in `workflow_dispatch` "Run workflow" button
directly in the Actions tab. Zero extra setup, but requires the
operator to have a GitHub account and be comfortable in GitHub's UI —
better suited to a semi-technical operator than a fully non-technical
one. Decide based on who the actual operator turns out to be.

## 7. Suggested file/folder structure

```
ig-follower-tracker/
├── accounts.csv          # seed/backup list only — live list lives in the
│                          # Sheet's "Accounts" tab once operator is set up
├── history.csv           # append-only log, one row per account per day
├── daily_report.xlsx     # generated each run — snapshot + deltas (backup
│                          # artifact; operator uses the Sheet instead)
├── config.py / .env      # API key, provider config, Google Sheets creds
├── fetch_followers.py    # pulls data, appends to history.csv, writes to
│                          # the Sheet's "Report" + "Log" tabs
├── build_report.py       # turns history.csv into daily_report.xlsx
├── apps_script/
│   └── run_scan_button.gs  # adds "▶ Run Scan Now" menu to the Sheet,
│                            # calls GitHub API to trigger workflow_dispatch
├── .github/workflows/
│   └── daily_scan.yml      # cron schedule + workflow_dispatch trigger
└── requirements.txt      # requests/httpx, pandas, openpyxl, python-dotenv,
                           # google-api-python-client
```

## 8. Non-goals / explicit exclusions

- No browser automation, no LangChain/agent framework — plain scheduled
  script calling a REST API.
- No use of the official Instagram Graph API (not viable for
  non-owned accounts).
- No scraping directly against instagram.com from our own IP — go
  through the chosen third-party provider so their infrastructure
  absorbs the ban/rate-limit risk, not ours.

## 9. Open items to resolve while building

- Which provider (Apify vs HikerAPI vs other) — confirm pricing at
  actual account-list size and test response format.
- Where accounts.csv gets its initial ~hundreds of usernames from
  (manual list vs import from somewhere else).
- Whether historical data should ever be pruned/archived, or kept
  indefinitely in `history.csv`.
- Who the actual operator is and how technical they are — determines
  whether to build the Sheets-button trigger (section 6a) or just rely
  on GitHub Actions' built-in manual "Run workflow" button.
- Google Cloud project + service account setup for Sheets API access
  (needed regardless of which manual-trigger option is chosen).
- Scope of the GitHub access token used by the Apps Script trigger —
  keep it restricted to `workflow_dispatch` on this one repo/workflow
  only, not a general-purpose token.
