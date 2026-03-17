# Property Tracker CLI (Ireland)

**Live demo (desktop/laptop recommended):** https://property.stephendaly.dev

> This demo runs the CLI in a browser-based terminal with a fixed **80×24** layout.
> On **mobile**, the terminal width is very constrained, so the experience can feel cramped and may require zoom/scroll.

A Python **Command-Line Interface (CLI)** app that reads Irish new-house price data from **Google Sheets**, lets you select a **year/quarter range** and **region**, and produces clear, terminal-friendly summary statistics.

This repo also includes a small **Node.js** wrapper that runs the Python CLI inside a browser terminal (useful for Heroku-style deployments).

![Responsive terminal UI screenshot](assets/images/responsive.jpg)

---

## What this project demonstrates

- **API integration**: Google Sheets **Application Programming Interface (API)** access using a service account
- **Data processing**: parsing values, selecting ranges, calculating descriptive stats
- **Defensive programming**: validation, clear error messages, and “fail fast” configuration checks
- **Export tooling**: write analysis results to **TXT** and **Comma-Separated Values (CSV)** files (local runs)
- **Deployment-aware design**: browser terminal wrapper with fixed 80×24 output constraints
- **Automation**: **Continuous Integration (CI)** checks via GitHub Actions, including Python syntax checks, `ruff` linting, core `pytest` tests, and a basic Node wrapper smoke check

---

## Features

### 1) Add the next quarter’s data
- Reads the most recent year/quarter in the sheet
- Prompts you for the next quarter’s values
- Appends a new row to Google Sheets

### 2) Run statistical analysis for a chosen time range
Pick:
- start year + quarter
- end year + quarter
- region (Nationally, Dublin, Cork, Galway, Limerick, Waterford, Other counties)

Outputs (terminal-friendly):
- overall % change (start → end)
- mean and standard deviation
- min, max, range
- quartiles (Q1/median/Q3) and **Interquartile Range (IQR)**

### 3) Export results (local runs)
If you choose “yes” when prompted, the app writes:
- `analysis_results.txt` (append-only)
- `analysis_<start>_<end>_<region>.csv`

> Note: on ephemeral hosts (e.g., Heroku), file writes may not persist between restarts.

---

## Tech stack

- **Python**: `gspread`, `google-auth`, `numpy`, `statistics`, `pytest`
- **Node.js** (demo wrapper): `total4`, `node-pty`, `xterm.js` (via CDN)
- **CI / quality**: GitHub Actions, `ruff`, `pytest`

---

## Repository structure

- `run.py` — main Python CLI program
- `requirements.txt` — Python runtime dependencies
- `requirements-dev.txt` — Python development dependencies (`ruff` + runtime deps)
- `pyproject.toml` — `ruff` configuration
- `index.js`, `controllers/default.js`, `views/` — browser terminal wrapper
- `.github/workflows/ci.yml` — CI checks (syntax, `ruff`, core `pytest`, Node smoke)
- `tests/test_run.py` — core pytest coverage for helper functions
- `.devcontainer/` — optional devcontainer configuration (renamed from inherited template defaults)

---

## Data format expected in Google Sheets

The first worksheet/tab must contain a header row with **exact** column names:

```
Year | Quarter | Nationally | Dublin | Cork | Galway | Limerick | Waterford | Other_counties
```

The app uses `worksheet.get_all_records()` so header names must match exactly (including `Other_counties`).

---

## Local setup (Python CLI)

### Step 1 — Create a virtual environment and install dependencies

macOS / Linux:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Windows PowerShell:

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
py -m pip install -r requirements.txt
```

### Step 2 — Create Google credentials (service account)

In Google Cloud Console:
- Create a Google Cloud project
- Enable **Google Sheets API**
- Create a **Service Account**
- Create/download a **JSON key**

Store the key outside the repo (recommended):

```bash
mkdir -p ~/.secrets
mv /path/to/service-account.json ~/.secrets/property-tracker-creds.json
```

### Step 3 — Create/prepare a Google Sheet

- Create a Google Sheet with the required header row (see above)
- Share the sheet with the service account email (`client_email` inside the JSON) as **Editor**
- Copy the spreadsheet ID from the URL:

```
https://docs.google.com/spreadsheets/d/<SPREADSHEET_ID>/edit
```

### Step 4 — Set environment variables and run

```bash
export PT_CREDS_PATH="$HOME/.secrets/property-tracker-creds.json"
export PT_SPREADSHEET_ID="<YOUR_SPREADSHEET_ID>"
python3 run.py
```

---

## Run the demo wrapper locally (browser terminal)

This runs a small Node server that spawns `python3 run.py` in an 80×24 terminal.

### Step 1 — Install Node dependencies

```bash
npm install
```

### Step 2 — Set required environment variables

```bash
export PORT=8000
export PT_CREDS_PATH="$HOME/.secrets/property-tracker-creds.json"
export PT_SPREADSHEET_ID="<YOUR_SPREADSHEET_ID>"
```

### Step 3 — Start the server

```bash
npm start
```

Open in your browser:

- `http://localhost:8000`

---

## Deploy (Heroku-style)

This repo’s Node wrapper supports a typical “browser terminal” deployment model.

### Required config vars

- `PORT` — set automatically by the hosting platform in deployment; use `8000` for local runs if needed
- `PT_SPREADSHEET_ID` = your Google Sheet ID
- `CREDS` = the **full contents** of your service-account JSON (paste as a single config var)
- `PT_CREDS_PATH` = `creds.json`

Why `PT_CREDS_PATH=creds.json`?
- `controllers/default.js` writes `creds.json` at runtime from `CREDS`
- `run.py` reads credentials from `PT_CREDS_PATH`

> **Security note:** treat the service account key like a password. Don’t commit it to GitHub. Rotate it if exposed.

---

## CI (Continuous Integration)

GitHub Actions runs checks on push/pull request:
- Python syntax compilation (`py_compile`, `compileall`)
- `ruff` linting
- Core `pytest` tests for helper functions
- Node install + basic require check

Workflow file: `.github/workflows/ci.yml`

---

## Project status

This project is currently maintained as a portfolio/demo repository.

The current release focuses on a stable CLI workflow, core automated checks, and practical CI quality gates.

---

## Known limitations

- Browser deployments may not retain exported files between restarts (ephemeral filesystem)
- Data coverage depends on what’s present in the linked Google Sheet
- The live demo is **best on desktop/laptop** due to fixed terminal dimensions

---

## Data source

- Central Statistics Office (CSO) Ireland / data.gov.ie — “Price of New Property by Quarter”

