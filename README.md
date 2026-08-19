# Instagram Follower Tracker

Tracks daily follower counts for a list of Instagram accounts, logs history to
CSV, and produces a report (Excel + Google Sheet) showing day-over-day
change. See [instagram-follower-tracker-brief.md](instagram-follower-tracker-brief.md)
for the full design rationale.

## How it works

```
Accounts tab (Google Sheet) or accounts.csv
   → fetch_followers.py calls the configured provider per username
   → appends today's counts to history.csv
   → build_report.py computes deltas -> daily_report.xlsx
   → sheets_sync.py writes the Report tab + appends a row to the Log tab
```

Runs daily via a GitHub Actions cron job, or on-demand via the "▶ Run Scan
Now" button in the Sheet (see [Apps Script setup](#apps-script-run-scan-now-button)
below).

## Local setup

1. Create a virtualenv and install dependencies:
   ```
   python -m venv .venv
   .venv/Scripts/pip install -r requirements.txt      # Windows
   .venv/bin/pip install -r requirements.txt           # macOS/Linux
   ```
2. Copy `.env.example` to `.env` and fill in:
   - `PROVIDER` — `apify`, `hikerapi`, or `mock` (mock needs no API key, useful for testing)
   - `PROVIDER_API_KEY` — your provider's API key
   - `GOOGLE_SHEET_ID` — the Sheet's ID from its URL
   - `GOOGLE_SERVICE_ACCOUNT_FILE` — path to the service account JSON key (see below)
3. Run it:
   ```
   python fetch_followers.py
   ```

## Google Sheets setup

1. Create a Google Cloud project, enable the **Google Sheets API**.
2. Create a service account, download its JSON key.
3. Share your Google Sheet with the service account's email address (Editor access).
4. Set `GOOGLE_SHEET_ID` and `GOOGLE_SERVICE_ACCOUNT_FILE` in `.env`.
5. Create the tabs (one-time):
   ```
   python -c "import sheets_sync; sheets_sync.ensure_tabs_exist()"
   ```
6. Populate the **Accounts** tab with the usernames to track (one per row, column A).
7. (Optional) Re-apply Report tab styling after changes:
   ```
   python -c "import sheets_sync; sheets_sync.format_report_tab()"
   ```

The **Accounts** tab is the live source of truth once Sheets is configured —
`accounts.csv` is only used as a fallback if Sheets isn't set up.

## GitHub Actions (daily automated run)

Runs daily at 09:00 WIB (02:00 UTC) via `.github/workflows/daily_scan.yml`,
and can also be triggered manually from the Actions tab or the Sheet's
"▶ Run Scan Now" button.

Set these in the GitHub repo (Settings → Secrets and variables → Actions):

| Type     | Name                         | Value                                  |
|----------|------------------------------|-----------------------------------------|
| Secret   | `PROVIDER_API_KEY`           | Your provider's API key                |
| Secret   | `GOOGLE_SERVICE_ACCOUNT_JSON`| Full contents of the service account JSON file |
| Variable | `PROVIDER`                   | `apify` (or `hikerapi`)                |
| Variable | `GOOGLE_SHEET_ID`            | The Sheet's ID                         |

## Apps Script "▶ Run Scan Now" button

Lets a non-technical operator trigger a scan on demand, without opening
GitHub. See [apps_script/run_scan_button.gs](apps_script/run_scan_button.gs)
for setup instructions (paste into Extensions → Apps Script in the Sheet,
then set Script Properties for `GITHUB_OWNER`, `GITHUB_REPO`, `GITHUB_TOKEN`,
`GITHUB_WORKFLOW_FILE`).

## Files

| File | Purpose |
|------|---------|
| `config.py` | Loads settings from `.env` |
| `providers.py` | Provider adapters (HikerAPI / Apify / mock) with retry logic |
| `fetch_followers.py` | Main entrypoint — run this daily |
| `build_report.py` | `history.csv` → `daily_report.xlsx` |
| `sheets_sync.py` | Google Sheets read/write + Report tab formatting |
| `accounts.csv` | Seed/backup username list |
| `history.csv` | Append-only log, one row per account per day |
| `daily_report.xlsx` | Generated snapshot + deltas |
| `apps_script/run_scan_button.gs` | Sheet menu button → triggers the GitHub workflow |
| `.github/workflows/daily_scan.yml` | Cron schedule + manual trigger |
