"""Centralized configuration, loaded from environment variables / .env."""
import os

from dotenv import load_dotenv

load_dotenv()

PROVIDER = os.getenv("PROVIDER", "mock").lower()
PROVIDER_API_KEY = os.getenv("PROVIDER_API_KEY", "")

GOOGLE_SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "")
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "")

ACCOUNTS_CSV_PATH = os.getenv("ACCOUNTS_CSV_PATH", "accounts.csv")
HISTORY_CSV_PATH = os.getenv("HISTORY_CSV_PATH", "history.csv")
REPORT_XLSX_PATH = os.getenv("REPORT_XLSX_PATH", "daily_report.xlsx")

SHEETS_ENABLED = bool(GOOGLE_SHEET_ID and GOOGLE_SERVICE_ACCOUNT_FILE)

RETRY_ATTEMPTS = int(os.getenv("RETRY_ATTEMPTS", "3"))
RETRY_BACKOFF_SECONDS = float(os.getenv("RETRY_BACKOFF_SECONDS", "2"))
