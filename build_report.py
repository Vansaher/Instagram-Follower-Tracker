"""Turns history.csv into a daily report: username, today, yesterday, change, % change.

Can be run standalone (`python build_report.py`) to regenerate daily_report.xlsx
from the current history.csv, or imported by fetch_followers.py to get the same
rows for writing to the Google Sheet "Report" tab.
"""
import logging
from typing import Optional

import pandas as pd

import config

logger = logging.getLogger(__name__)

REPORT_COLUMNS = ["username", "today_count", "yesterday_count", "change", "pct_change"]


def compute_report(
    history_csv_path: str = config.HISTORY_CSV_PATH,
    accounts: Optional[list[str]] = None,
) -> pd.DataFrame:
    """Read history.csv and compute day-over-day deltas per username.

    Uses each username's two most recent distinct dates present in the
    history, not literally "today" vs "yesterday" by calendar date, so the
    report is still meaningful if a run is skipped for a day.

    If `accounts` is given, the report is limited to just those usernames
    (history.csv itself is append-only and keeps every account ever tracked,
    but the report should only reflect the currently tracked list).
    """
    history = pd.read_csv(history_csv_path, dtype={"username": str})
    if accounts is not None:
        history = history[history["username"].isin(accounts)]
    if history.empty:
        return pd.DataFrame(columns=REPORT_COLUMNS)

    history["date"] = pd.to_datetime(history["date"])
    history = history.sort_values(["username", "date"])

    rows = []
    for username, group in history.groupby("username"):
        group = group.drop_duplicates(subset="date", keep="last")
        today_count = int(group.iloc[-1]["follower_count"])
        if len(group) >= 2:
            yesterday_count = int(group.iloc[-2]["follower_count"])
        else:
            yesterday_count = today_count
        change = today_count - yesterday_count
        pct_change = (change / yesterday_count * 100) if yesterday_count else 0.0
        rows.append(
            {
                "username": username,
                "today_count": today_count,
                "yesterday_count": yesterday_count,
                "change": change,
                "pct_change": round(pct_change, 4),
            }
        )

    report = pd.DataFrame(rows, columns=REPORT_COLUMNS)
    report = report.sort_values("change", key=lambda s: s.abs(), ascending=False).reset_index(drop=True)
    return report


def build_report(
    history_csv_path: str = config.HISTORY_CSV_PATH,
    output_xlsx_path: str = config.REPORT_XLSX_PATH,
    accounts: Optional[list[str]] = None,
) -> pd.DataFrame:
    """Compute the report and write it to daily_report.xlsx. Returns the DataFrame."""
    report = compute_report(history_csv_path, accounts=accounts)
    report.to_excel(output_xlsx_path, index=False, sheet_name="Report")
    logger.info("Wrote %d rows to %s", len(report), output_xlsx_path)
    return report


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    build_report()
