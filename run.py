"""
Property Tracker (CLI)

This script uses a Google Sheet as a lightweight datastore.
Authentication is done via a Google Cloud *service account* JSON key file.

Configuration
- PT_CREDS_PATH: path to the service-account JSON file (default: creds.json)

Security notes:
- Never commit credentials to Git.
- To keep the JSON key file outside the repo (e.g., ~/.secrets/) and point to it using PT_CREDS_PATH.
"""
import os
from pathlib import Path

import gspread
from google.oauth2.service_account import Credentials


# -------- Google Sheets access (service account) --------
# This app reads/writes a Google Sheet using a Google Cloud service account.
# Credentials are kept OUTSIDE the repo and passed in via an environment variable.

# Required permissions for this app:
# - Google Sheets: read/write spreadsheet content
# - Google Drive: locate the spreadsheet by name (not needed if you use Spreadsheet ID)
SCOPE = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# Where the service-account JSON key lives on my computer (and not committed to repo) 
DEFAULT_CREDS_PATH = Path.home() / ".secrets" / "property-tracker-creds.json"
CREDS_PATH = Path(os.getenv("PT_CREDS_PATH", str(DEFAULT_CREDS_PATH)))

if not CREDS_PATH.exists():
    raise FileNotFoundError(
        f"Credentials file not found: {CREDS_PATH}\n"
        "Fix: set PT_CREDS_PATH to the full path of your service-account JSON key."
    )

SPREADSHEET_ID = os.getenv("PT_SPREADSHEET_ID")
SPREADSHEET_NAME = os.getenv("PT_SPREADSHEET_NAME", "new_property_price")

creds = Credentials.from_service_account_file(str(CREDS_PATH)).with_scopes(SCOPE)
gspread_client = gspread.authorize(creds)

if SPREADSHEET_ID:
    sheet = gspread_client.open_by_key(SPREADSHEET_ID)
else:
    sheet = gspread_client.open(SPREADSHEET_NAME)

worksheet = sheet.get_worksheet(0)
