"""Daily entrypoint: read accounts, fetch follower counts, append history.csv,
regenerate daily_report.xlsx, and sync results to Google Sheets (if configured).

Usage: python fetch_followers.py
"""
import csv
import datetime
import logging
import os

import config
import sheets_sync
from build_report import build_report
from providers import ProviderError, get_provider

logger = logging.getLogger(__name__)


def read_local_accounts(path: str) -> list[str]:
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return [row["username"].strip() for row in reader if row.get("username", "").strip()]


def load_accounts() -> list[str]:
    """Prefer the Google Sheet's Accounts tab; fall back to local accounts.csv."""
    if config.SHEETS_ENABLED:
        sheet_accounts = sheets_sync.read_accounts()
        if sheet_accounts is not None:
            return sheet_accounts
    return read_local_accounts(config.ACCOUNTS_CSV_PATH)


def append_history(path: str, date: str, results: list[tuple[str, int]]) -> None:
    file_exists = os.path.isfile(path)
    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["date", "username", "follower_count"])
        for username, count in results:
            writer.writerow([date, username, count])


def run() -> None:
    accounts = load_accounts()
    if not accounts:
        logger.warning("No accounts to process. Check accounts.csv or the Sheet's Accounts tab.")
        return

    logger.info("Fetching follower counts for %d accounts via provider '%s'.", len(accounts), config.PROVIDER)
    fetch = get_provider()

    today = datetime.date.today().isoformat()
    results: list[tuple[str, int]] = []
    errors = 0

    for username in accounts:
        try:
            count = fetch(username)
            results.append((username, count))
            logger.info("%s: %d followers", username, count)
        except ProviderError as exc:
            errors += 1
            logger.error("Skipping %s after retries exhausted: %s", username, exc)

    if results:
        append_history(config.HISTORY_CSV_PATH, today, results)
        logger.info("Appended %d rows to %s", len(results), config.HISTORY_CSV_PATH)
    else:
        logger.warning("No successful results this run; history.csv not updated.")

    report = build_report(accounts=accounts)

    status = "ok" if errors == 0 else ("partial" if results else "failed")
    if config.SHEETS_ENABLED:
        sheets_sync.write_report(report)
    sheets_sync.append_log(accounts_processed=len(results), errors=errors, status=status)

    logger.info("Run complete: %d succeeded, %d failed, status=%s", len(results), errors, status)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run()
