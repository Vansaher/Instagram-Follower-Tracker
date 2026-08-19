"""Google Sheets sync: "Accounts" (source of usernames), "Report" (daily
snapshot + deltas), and "Log" (one row per run) tabs.

All functions are safe to call even when Sheets isn't configured
(GOOGLE_SHEET_ID / GOOGLE_SERVICE_ACCOUNT_FILE unset) -- they log a warning
and no-op, so the CSV/XLSX pipeline keeps working standalone.
"""
import datetime
import logging
from typing import Optional

import pandas as pd

import config

logger = logging.getLogger(__name__)

ACCOUNTS_TAB = "Accounts"
REPORT_TAB = "Report"
LOG_TAB = "Log"

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

_service = None


def _get_service():
    """Lazily build and cache the Sheets API client. Returns None if unconfigured."""
    global _service
    if not config.SHEETS_ENABLED:
        return None
    if _service is not None:
        return _service

    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    creds = service_account.Credentials.from_service_account_file(
        config.GOOGLE_SERVICE_ACCOUNT_FILE, scopes=SCOPES
    )
    _service = build("sheets", "v4", credentials=creds)
    return _service


def ensure_tabs_exist() -> None:
    """Create Accounts/Report/Log tabs (with headers) if they don't already exist."""
    service = _get_service()
    if service is None:
        logger.warning("Sheets not configured; skipping ensure_tabs_exist().")
        return

    sheet_meta = service.spreadsheets().get(spreadsheetId=config.GOOGLE_SHEET_ID).execute()
    existing_titles = {s["properties"]["title"] for s in sheet_meta.get("sheets", [])}

    missing = [t for t in (ACCOUNTS_TAB, REPORT_TAB, LOG_TAB) if t not in existing_titles]
    if missing:
        requests_body = {
            "requests": [{"addSheet": {"properties": {"title": title}}} for title in missing]
        }
        service.spreadsheets().batchUpdate(
            spreadsheetId=config.GOOGLE_SHEET_ID, body=requests_body
        ).execute()
        logger.info("Created missing tabs: %s", missing)

    if ACCOUNTS_TAB in missing:
        _write_values(f"{ACCOUNTS_TAB}!A1", [["username"]])
    if REPORT_TAB in missing:
        _write_values(f"{REPORT_TAB}!A1", [["username", "today_count", "yesterday_count", "change", "pct_change"]])
    if LOG_TAB in missing:
        _write_values(f"{LOG_TAB}!A1", [["timestamp", "accounts_processed", "errors", "status"]])


def _write_values(range_name: str, values: list) -> None:
    service = _get_service()
    service.spreadsheets().values().update(
        spreadsheetId=config.GOOGLE_SHEET_ID,
        range=range_name,
        valueInputOption="RAW",
        body={"values": values},
    ).execute()


def read_accounts() -> Optional[list[str]]:
    """Read usernames from the Accounts tab. Returns None if Sheets isn't configured."""
    service = _get_service()
    if service is None:
        logger.warning("Sheets not configured; falling back to local accounts.csv.")
        return None

    result = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=config.GOOGLE_SHEET_ID, range=f"{ACCOUNTS_TAB}!A2:A")
        .execute()
    )
    rows = result.get("values", [])
    usernames = [row[0].strip() for row in rows if row and row[0].strip()]
    return usernames


def write_report(report: pd.DataFrame) -> None:
    """Clear and rewrite the Report tab with the given report DataFrame."""
    service = _get_service()
    if service is None:
        logger.warning("Sheets not configured; skipping write_report().")
        return

    service.spreadsheets().values().clear(
        spreadsheetId=config.GOOGLE_SHEET_ID, range=REPORT_TAB
    ).execute()

    values = [list(report.columns)] + report.astype(object).values.tolist()
    _write_values(f"{REPORT_TAB}!A1", values)
    logger.info("Wrote %d report rows to Google Sheet.", len(report))


def _get_sheet_id(title: str) -> int:
    service = _get_service()
    meta = service.spreadsheets().get(
        spreadsheetId=config.GOOGLE_SHEET_ID,
        fields="sheets(properties(sheetId,title),conditionalFormats,bandedRanges)",
    ).execute()
    for sheet in meta.get("sheets", []):
        if sheet["properties"]["title"] == title:
            return sheet
    raise ValueError(f"Tab '{title}' not found in spreadsheet.")


def _clear_existing_formatting(sheet: dict, requests: list) -> None:
    """Queue deletion of any pre-existing conditional formats / banding on a
    tab so re-running format_report_tab() doesn't stack duplicate rules."""
    sheet_id = sheet["properties"]["sheetId"]
    conditional_formats = sheet.get("conditionalFormats", [])
    for index in reversed(range(len(conditional_formats))):
        requests.append({"deleteConditionalFormatRule": {"sheetId": sheet_id, "index": index}})
    for banded_range in sheet.get("bandedRanges", []):
        requests.append({"deleteBanding": {"bandedRangeId": banded_range["bandedRangeId"]}})


def format_report_tab() -> None:
    """Apply one-time visual styling to the Report tab: frozen bold header,
    number formatting, alternating row colors, and green/red highlighting
    on the change column. Idempotent -- safe to re-run after re-styling.
    """
    service = _get_service()
    if service is None:
        logger.warning("Sheets not configured; skipping format_report_tab().")
        return

    report_sheet = _get_sheet_id(REPORT_TAB)
    sheet_id = report_sheet["properties"]["sheetId"]

    requests: list = []
    _clear_existing_formatting(report_sheet, requests)

    requests += [
        # Freeze header row
        {
            "updateSheetProperties": {
                "properties": {"sheetId": sheet_id, "gridProperties": {"frozenRowCount": 1}},
                "fields": "gridProperties.frozenRowCount",
            }
        },
        # Bold white-on-dark header
        {
            "repeatCell": {
                "range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1},
                "cell": {
                    "userEnteredFormat": {
                        "backgroundColor": {"red": 0.13, "green": 0.16, "blue": 0.2},
                        "textFormat": {
                            "bold": True,
                            "foregroundColor": {"red": 1, "green": 1, "blue": 1},
                        },
                        "horizontalAlignment": "CENTER",
                    }
                },
                "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)",
            }
        },
        # Thousands separators on the count columns (B, C)
        {
            "repeatCell": {
                "range": {"sheetId": sheet_id, "startRowIndex": 1, "startColumnIndex": 1, "endColumnIndex": 3},
                "cell": {"userEnteredFormat": {"numberFormat": {"type": "NUMBER", "pattern": "#,##0"}}},
                "fields": "userEnteredFormat.numberFormat",
            }
        },
        # Signed thousands separator on the change column (D)
        {
            "repeatCell": {
                "range": {"sheetId": sheet_id, "startRowIndex": 1, "startColumnIndex": 3, "endColumnIndex": 4},
                "cell": {
                    "userEnteredFormat": {"numberFormat": {"type": "NUMBER", "pattern": "+#,##0;-#,##0;0"}}
                },
                "fields": "userEnteredFormat.numberFormat",
            }
        },
        # Signed percent-style display on pct_change (E) -- values are already *100
        {
            "repeatCell": {
                "range": {"sheetId": sheet_id, "startRowIndex": 1, "startColumnIndex": 4, "endColumnIndex": 5},
                "cell": {
                    "userEnteredFormat": {
                        "numberFormat": {"type": "NUMBER", "pattern": "+0.00\"%\";-0.00\"%\";0.00\"%\""}
                    }
                },
                "fields": "userEnteredFormat.numberFormat",
            }
        },
        # Alternating row shading for readability
        {
            "addBanding": {
                "bandedRange": {
                    "range": {"sheetId": sheet_id, "startRowIndex": 1, "startColumnIndex": 0, "endColumnIndex": 5},
                    "rowProperties": {
                        "headerColorStyle": {"rgbColor": {"red": 0.13, "green": 0.16, "blue": 0.2}},
                        "firstBandColorStyle": {"rgbColor": {"red": 1, "green": 1, "blue": 1}},
                        "secondBandColorStyle": {"rgbColor": {"red": 0.95, "green": 0.96, "blue": 0.98}},
                    },
                }
            }
        },
        # Green text when change > 0
        {
            "addConditionalFormatRule": {
                "rule": {
                    "ranges": [{"sheetId": sheet_id, "startRowIndex": 1, "startColumnIndex": 3, "endColumnIndex": 4}],
                    "booleanRule": {
                        "condition": {"type": "NUMBER_GREATER", "values": [{"userEnteredValue": "0"}]},
                        "format": {"textFormat": {"foregroundColor": {"red": 0.0, "green": 0.5, "blue": 0.13}}},
                    },
                },
                "index": 0,
            }
        },
        # Red text when change < 0
        {
            "addConditionalFormatRule": {
                "rule": {
                    "ranges": [{"sheetId": sheet_id, "startRowIndex": 1, "startColumnIndex": 3, "endColumnIndex": 4}],
                    "booleanRule": {
                        "condition": {"type": "NUMBER_LESS", "values": [{"userEnteredValue": "0"}]},
                        "format": {"textFormat": {"foregroundColor": {"red": 0.7, "green": 0.0, "blue": 0.0}}},
                    },
                },
                "index": 0,
            }
        },
        # Auto-resize all columns to fit content
        {
            "autoResizeDimensions": {
                "dimensions": {"sheetId": sheet_id, "dimension": "COLUMNS", "startIndex": 0, "endIndex": 5}
            }
        },
    ]

    service.spreadsheets().batchUpdate(
        spreadsheetId=config.GOOGLE_SHEET_ID, body={"requests": requests}
    ).execute()
    logger.info("Applied formatting to the Report tab.")


def append_log(accounts_processed: int, errors: int, status: str) -> None:
    """Append one row to the Log tab summarizing this run."""
    service = _get_service()
    if service is None:
        logger.warning("Sheets not configured; skipping append_log().")
        return

    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    row = [[timestamp, accounts_processed, errors, status]]
    service.spreadsheets().values().append(
        spreadsheetId=config.GOOGLE_SHEET_ID,
        range=f"{LOG_TAB}!A1",
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body={"values": row},
    ).execute()
    logger.info("Appended log row to Google Sheet: %s", row[0])
