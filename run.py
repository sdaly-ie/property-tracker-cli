# REMINDER: Terminal output target: 80 characters wide & 24 rows high
#
# Property Tracker (CLI)
# - Stores data in a Google Sheet (lightweight datastore)
# - Authenticates using a Google Cloud service account JSON key
#
# Configuration (recommended):
#   export PT_CREDS_PATH="$HOME/.secrets/property-tracker-creds.json"
#   export PT_SPREADSHEET_ID="1gdnnmodlkR8CzNAhXfKP90T_VBpnkSQVKvJ2ezjDOX8"
#
# Notes:
# - Do NOT commit credentials to Git.
# - Opening by Spreadsheet ID avoids needing Google Drive API enabled.

# Imports environment variable support
import os
# Imports JSON parsing (to read service account email from creds file)
import json
# Imports path handling
from pathlib import Path
# Imports basic statistics functions
import statistics
# Imports numerical operations (percentiles)
import numpy as np
# Imports CSV writing
import csv

# Imports Google Sheets client
import gspread
# Imports service account credentials helper
from google.oauth2.service_account import Credentials
# Imports the SpreadsheetNotFound exception for better error messages
from gspread.exceptions import SpreadsheetNotFound


# -------------------- Google Sheets connection --------------------

# This scope allows reading/writing Google Sheets
# (Drive scope is NOT required when opening by Spreadsheet ID)
SCOPE = ["https://www.googleapis.com/auth/spreadsheets"]

# Default location for your service account key file (kept OUTSIDE the repo)
DEFAULT_CREDS_PATH = Path.home() / ".secrets" / "property-tracker-creds.json"
# Reads PT_CREDS_PATH (if set), otherwise uses DEFAULT_CREDS_PATH
CREDS_PATH = Path(os.getenv("PT_CREDS_PATH", str(DEFAULT_CREDS_PATH))).expanduser()

# Fail early if the credentials file does not exist
if not CREDS_PATH.exists():
    raise FileNotFoundError(
        f"\nCredentials file not found: {CREDS_PATH}\n\n"
        "Fix:\n"
        "  export PT_CREDS_PATH=/full/path/to/service-account-key.json\n"
    )

# Default spreadsheet ID (so the app can run even if PT_SPREADSHEET_ID is not set)
DEFAULT_SPREADSHEET_ID = "1gdnnmodlkR8CzNAhXfKP90T_VBpnkSQVKvJ2ezjDOX8"
# Reads PT_SPREADSHEET_ID (if set), otherwise uses DEFAULT_SPREADSHEET_ID
SPREADSHEET_ID = os.getenv("PT_SPREADSHEET_ID", DEFAULT_SPREADSHEET_ID).strip()

# Common placeholder values people accidentally leave in place
PLACEHOLDER_IDS = {
    "",
    "YOUR_REAL_SHEET_ID",
    "PASTE_YOUR_SHEET_ID_HERE",
    "YOUR_SHEET_ID",
    "PASTE_THE_LONG_ID_HERE",
}

# Fail fast if spreadsheet ID is missing or still a placeholder
if SPREADSHEET_ID in PLACEHOLDER_IDS:
    raise ValueError(
        "\nPT_SPREADSHEET_ID is missing or still set to a placeholder.\n\n"
        "Fix: open your Google Sheet in the browser and copy the ID from the URL:\n"
        "https://docs.google.com/spreadsheets/d/<THIS_PART>/edit\n"
        "Then:\n"
        "  export PT_SPREADSHEET_ID=<THIS_PART>\n"
        "and rerun.\n"
    )

# Read the service account email so we can tell you what to share the Sheet with
service_account_email = None
try:
    # Opens the credentials JSON file
    with open(CREDS_PATH, "r", encoding="utf-8") as f:
        # Parses JSON and pulls out client_email
        service_account_email = json.load(f).get("client_email")
except Exception:
    # If anything goes wrong, we keep this as None
    service_account_email = None

# Loads credentials from the service-account JSON file and applies the scope
creds = Credentials.from_service_account_file(str(CREDS_PATH)).with_scopes(SCOPE)
# Creates a gspread client using the scoped credentials
gspread_client = gspread.authorize(creds)

# Attempts to open the spreadsheet by ID
try:
    SHEET = gspread_client.open_by_key(SPREADSHEET_ID)
except SpreadsheetNotFound as e:
    # Explains the two common root causes: not shared OR wrong ID
    raise SpreadsheetNotFound(
        "\nSpreadsheetNotFound (404).\n"
        "This usually means ONE of the following:\n"
        "1) The spreadsheet is not shared with your service account, or\n"
        "2) The Spreadsheet ID is wrong.\n\n"
        "Fix for sharing:\n"
        "1) Open the Google Sheet in your browser\n"
        "2) Click Share\n"
        "3) Add this email as Editor:\n"
        f"   {service_account_email or '[could not read client_email from creds file]'}\n"
        "4) Save, then rerun: python3 run.py\n"
    ) from e

# Selects the first worksheet/tab
worksheet = SHEET.get_worksheet(0)


# -------------------- Helper functions --------------------

# Normalizes header strings so we can match keys robustly
def _norm_header(text):
    # Converts to string
    s = str(text)
    # Lowercases for case-insensitive matching
    s = s.lower()
    # Removes spaces and underscores to reduce mismatch issues
    s = s.replace(" ", "").replace("_", "")
    return s


# Resolves a desired column name to the actual header used in the Google Sheet
def resolve_column_key(desired_name, available_keys):
    # Pre-computes the normalized desired header
    desired_norm = _norm_header(desired_name)

    # Tries direct match first
    if desired_name in available_keys:
        return desired_name

    # Falls back to normalized matching
    for k in available_keys:
        if _norm_header(k) == desired_norm:
            return k

    # If we cannot find a match, return None
    return None


# Retrieves min & max years and quarters from all worksheet records
def get_year_quarter_range(ws):
    # Pulls all records (list of dicts)
    records = ws.get_all_records()
    # If no records exist, return empty ranges
    if not records:
        return (None, None), (None, None)

    # Extracts and sorts unique years
    years = sorted({record["Year"] for record in records})
    # Assigns min and max year
    min_year, max_year = years[0], years[-1]

    # Extracts quarters from the minimum year
    min_year_quarters = {record["Quarter"] for record in records if record["Year"] == min_year}
    # Extracts quarters from the maximum year
    max_year_quarters = {record["Quarter"] for record in records if record["Year"] == max_year}

    # Finds smallest quarter in min year and largest quarter in max year
    min_quarter = min(min_year_quarters)
    max_quarter = max(max_year_quarters)

    # Returns (start_range), (end_range)
    return (min_year, min_quarter), (max_year, max_quarter)


# Calculates and returns formatted descriptive statistics
def calculate_statistics(data):
    # Initializes all fields as N/A
    stats = {
        "average": "N/A",
        "std_dev": "N/A",
        "min_value": "N/A",
        "max_value": "N/A",
        "data_range": "N/A",
        "Q1": "N/A",
        "median": "N/A",
        "Q3": "N/A",
        "IQR": "N/A",
    }

    # Only compute if data exists
    if data:
        # Computes min/max/range/median (valid with 1+ values)
        stats["min_value"] = f"{min(data):,.2f}"
        stats["max_value"] = f"{max(data):,.2f}"
        stats["data_range"] = f"{max(data) - min(data):,.2f}"
        stats["median"] = f"{statistics.median(data):,.2f}"

        # Only compute mean/stdev/quartiles if there are at least 2 points
        if len(data) >= 2:
            stats["average"] = f"{statistics.mean(data):,.2f}"
            stats["std_dev"] = f"{statistics.stdev(data):,.2f}"
            q25, q75 = np.percentile(data, [25, 75])
            stats["Q1"] = f"{q25:,.2f}"
            stats["Q3"] = f"{q75:,.2f}"
            stats["IQR"] = f"{(q75 - q25):,.2f}"

    # Returns the stats dict
    return stats


# Prompts the user for integer input within an optional range
def get_integer_input(prompt, range_min=None, range_max=None):
    # Loops until valid input is received
    while True:
        try:
            # Reads input and converts to integer
            value = int(input(prompt))

            # Validates against min/max if provided
            if (range_min is not None and value < range_min) or (range_max is not None and value > range_max):
                print(f"\n Please enter a numeric value between {range_min} and {range_max}.\n")
            else:
                # Returns valid integer
                return value

        except ValueError:
            # Handles non-integer input
            print("\n Invalid input. Please enter a valid integer (i.e. whole number).\n")


# -------------------- Export functions --------------------

# Writes analysis output to a text file and returns the output path
def save_to_text_file(data_values, summary_message,
                      start_year, start_quarter, end_year, end_quarter,
                      selected_county):
    # Writes to a fixed filename in the same folder as run.py
    output_path = Path(__file__).resolve().parent / "analysis_results.txt"

    # Default formatted strings
    average_formatted = "N/A"
    std_dev_formatted = "N/A"
    min_value_formatted = "N/A"
    max_value_formatted = "N/A"
    data_range_formatted = "N/A"
    Q1_formatted = "N/A"
    median_formatted = "N/A"
    Q3_formatted = "N/A"
    IQR_formatted = "N/A"

    # Only compute numbers if there is data
    if data_values:
        # Computes values available with 1+ point
        min_value = min(data_values)
        max_value = max(data_values)
        data_range = max_value - min_value
        median = statistics.median(data_values)

        # Formats those values
        min_value_formatted = f"{min_value:8,.2f}"
        max_value_formatted = f"{max_value:8,.2f}"
        data_range_formatted = f"{data_range:8,.2f}"
        median_formatted = f"{median:8,.2f}"

        # Computes values requiring 2+ points
        if len(data_values) >= 2:
            average = statistics.mean(data_values)
            std_dev = statistics.stdev(data_values)
            Q1 = np.percentile(data_values, 25)
            Q3 = np.percentile(data_values, 75)
            IQR = Q3 - Q1

            # Formats those values
            average_formatted = f"{average:8,.2f}"
            std_dev_formatted = f"{std_dev:8,.2f}"
            Q1_formatted = f"{Q1:8,.2f}"
            Q3_formatted = f"{Q3:8,.2f}"
            IQR_formatted = f"{IQR:8,.2f}"

    # Appends results to the text file
    with open(output_path, "a", encoding="utf-8") as file:
        file.write("\n +--------------------------------------------------+\n")
        file.write(" |              Summary of Price Changes            |\n")
        file.write(" +--------------------------------------------------+\n")
        file.write(f"\n                From {start_year} Q{start_quarter} to {end_year} Q{end_quarter}\n")
        file.write(f"            {summary_message}\n")
        file.write(f"               New Property - {selected_county}\n")
        file.write("\n +--------------------------------------------------+\n")

        # Writes stats section if we had data
        if data_values:
            file.write(" |                Summary Statistics:               |\n")
            file.write(" +--------------------------------------------------+\n")
            file.write(f"\n       Average (mean):               €{average_formatted}\n")
            file.write(f"       Standard Deviation (+/-):     €{std_dev_formatted}\n")
            file.write("\n +--------------------------------------------------+\n")
            file.write(f"\n       Minimum Value:                €{min_value_formatted}\n")
            file.write(f"       Maximum Value:                €{max_value_formatted}\n")
            file.write(f"       Range:                        €{data_range_formatted}\n")
            file.write("\n +--------------------------------------------------+\n")
            file.write(f"\n       Lower Quartile (Q1):          €{Q1_formatted}\n")
            file.write(f"       Median (Q2):                  €{median_formatted}\n")
            file.write(f"       Upper Quartile (Q3):          €{Q3_formatted}\n")
            file.write(f"       IQR:                          €{IQR_formatted}\n")
            file.write("\n +--------------------------------------------------+\n")

    # Returns the path so we can print it
    return output_path


# Writes analysis output to a CSV file and returns the output path
def save_to_csv_file(data_rows, data_values, summary_message,
                     start_year, start_quarter, end_year, end_quarter,
                     selected_county, start_price, end_price):
    # Makes the county safe for filenames
    safe_county = str(selected_county).lower().replace(" ", "_")
    # Builds a filename that includes the range and county
    csv_path = (
        Path(__file__).resolve().parent
        / f"analysis_{start_year}Q{start_quarter}_{end_year}Q{end_quarter}_{safe_county}.csv"
    )

    # Computes numeric stats (None when not available)
    mean_v = statistics.mean(data_values) if len(data_values) >= 2 else None
    std_v = statistics.stdev(data_values) if len(data_values) >= 2 else None
    min_v = min(data_values) if data_values else None
    max_v = max(data_values) if data_values else None
    range_v = (max_v - min_v) if (min_v is not None and max_v is not None) else None
    median_v = statistics.median(data_values) if data_values else None

    # Computes quartiles and IQR (only for 2+ values, matching your app rules)
    q1_v = q3_v = iqr_v = None
    if len(data_values) >= 2:
        q25, q75 = np.percentile(data_values, [25, 75])
        q1_v, q3_v = float(q25), float(q75)
        iqr_v = q3_v - q1_v

    # Computes percent change if start and end price exist
    pct_change = None
    if start_price is not None and end_price is not None and start_price != 0:
        pct_change = ((end_price - start_price) / start_price) * 100.0

    # Defines a stable column order for the CSV
    fieldnames = [
        "StartYear", "StartQuarter", "EndYear", "EndQuarter",
        "County",
        "Year", "Quarter", "Price",
        "StartPrice", "EndPrice", "PercentChange",
        "Mean", "StdDev", "Min", "Max", "Range", "Q1", "Median", "Q3", "IQR",
        "SummaryMessage",
    ]

    # Sorts rows chronologically
    data_rows_sorted = sorted(data_rows, key=lambda r: (r["Year"], r["Quarter"]))

    # Writes CSV
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        # Writes one row per quarter in the selected range
        for r in data_rows_sorted:
            writer.writerow({
                "StartYear": start_year,
                "StartQuarter": start_quarter,
                "EndYear": end_year,
                "EndQuarter": end_quarter,
                "County": selected_county,
                "Year": r["Year"],
                "Quarter": r["Quarter"],
                "Price": r["Price"],
                "StartPrice": start_price,
                "EndPrice": end_price,
                "PercentChange": pct_change,
                "Mean": mean_v,
                "StdDev": std_v,
                "Min": min_v,
                "Max": max_v,
                "Range": range_v,
                "Q1": q1_v,
                "Median": median_v,
                "Q3": q3_v,
                "IQR": iqr_v,
                "SummaryMessage": summary_message,
            })

        # If no rows matched, still write a single summary-only row
        if not data_rows_sorted:
            writer.writerow({
                "StartYear": start_year,
                "StartQuarter": start_quarter,
                "EndYear": end_year,
                "EndQuarter": end_quarter,
                "County": selected_county,
                "Year": None,
                "Quarter": None,
                "Price": None,
                "StartPrice": start_price,
                "EndPrice": end_price,
                "PercentChange": pct_change,
                "Mean": mean_v,
                "StdDev": std_v,
                "Min": min_v,
                "Max": max_v,
                "Range": range_v,
                "Q1": q1_v,
                "Median": median_v,
                "Q3": q3_v,
                "IQR": iqr_v,
                "SummaryMessage": summary_message,
            })

    # Returns the path so we can print it
    return csv_path


# Prompts export choice and saves both text + CSV if requested
def save_results(data_rows, data_values, summary_message,
                 start_year, start_quarter, end_year, end_quarter,
                 selected_county, start_price, end_price):
    # Asks the user if they want to export
    save_choice = input("        Like to export results? (yes/no): ").lower()

    # Exports on yes
    if save_choice.startswith("y"):
        # Saves the text report
        txt_path = save_to_text_file(
            data_values, summary_message,
            start_year, start_quarter, end_year, end_quarter,
            selected_county
        )
        # Saves the CSV report
        csv_path = save_to_csv_file(
            data_rows, data_values, summary_message,
            start_year, start_quarter, end_year, end_quarter,
            selected_county, start_price, end_price
        )
        # Prints both output paths
        print(f"\n Results saved to:\n  {txt_path}\n  {csv_path}\n")
    else:
        # Confirms no export occurred
        print("\n         These results have not been saved.\n")


# Retrieves last year and quarter from the worksheet (last row)
def get_last_year_quarter(ws):
    # Reads all values and takes the last row
    last_row = ws.get_all_values()[-1]
    # Converts first two columns to int
    last_year = int(last_row[0])
    last_quarter = int(last_row[1])
    # Returns last period
    return last_year, last_quarter


# -------------------- Main app loop --------------------

# Runs the menu until the user exits
while True:
    # Defines menu options
    options = {
        "1": "Add new information to database",
        "2": "Perform analysis on existing database",
        "3": "Exit",
    }

    # Prints header
    print(" +--------------------------------------------------+")
    print("\n     Welcome to 'P r o p e r t y  T r a c k e r'\n")
    print("  Keeping you up-to-date with Irish property trends")

    # Builds and prints the menu table
    menu_table = f"""
 +--------------------------------------------------+
 | Press |                 Action                   |
 +--------------------------------------------------+
 |   {'1':<3} | {options['1']:<40} |
 |   {'2':<3} | {options['2']:<40} |
 |   {'3':<3} | {options['3']:<40} |
 +--------------------------------------------------+
"""
    print(menu_table)

    # Reads user choice
    choice = input("    Please select your choice and hit 'Enter': ")
    print("\n +--------------------------------------------------+")

    # -------------------- Option 1: Add data --------------------
    if choice == "1":
        # Gets the dataset range (min and max)
        (min_year, min_quarter), (max_year, max_quarter) = get_year_quarter_range(worksheet)

        # Gets the last entered year/quarter
        last_year, last_quarter = get_last_year_quarter(worksheet)

        # Computes next year/quarter
        next_year, next_quarter = last_year, last_quarter
        if last_quarter < 4:
            next_quarter += 1
        else:
            next_year += 1
            next_quarter = 1

        # Displays range info
        print("\n   Current data available from imported CSO dataset")
        print(f"    Quarter {min_quarter}, Year {min_year} to Quarter {last_quarter}, Year {last_year}")
        print(f" Please enter new data for next Quarter {next_quarter}, Year {next_year}:")
        print("\n +--------------------------------------------------+\n")

        # Prompts for prices
        nationally = get_integer_input("      Avg Price Nationally:      €")
        dublin = get_integer_input("      Avg Price Dublin:          €")
        cork = get_integer_input("      Avg Price Cork:            €")
        galway = get_integer_input("      Avg Price Galway:          €")
        limerick = get_integer_input("      Avg Price Limerick:        €")
        waterford = get_integer_input("      Avg Price Waterford:       €")
        other_counties = get_integer_input("      Avg Price Other Counties:  €")

        # Builds row in the expected sheet column order
        row = [
            next_year, next_quarter, nationally, dublin, cork, galway,
            limerick, waterford, other_counties
        ]

        # Prints confirmation summary
        print("\n +--------------------------------------------------+\n")
        print("      Summary of the data entered:\n")
        print(f"       Year:                      {next_year}")
        print(f"       Quarter:                    {next_quarter}")
        print(f"       Avg Price Nationally:      €{nationally}")
        print(f"       Avg Price Dublin:          €{dublin}")
        print(f"       Avg Price Cork:            €{cork}")
        print(f"       Avg Price Galway:          €{galway}")
        print(f"       Avg Price Limerick:        €{limerick}")
        print(f"       Avg Price Waterford:       €{waterford}")
        print(f"       Avg Price Other Counties:  €{other_counties}\n")

        # Asks the user to confirm
        confirm = input("     Is the entered data correct? (yes/no): ")
        if confirm.lower().startswith("y"):
            # Appends the row to the sheet
            worksheet.append_row(row)
            print("\n    New information has been added to database.\n")
        else:
            # Cancels without writing
            print("\n       Data entry cancelled - no data added.\n")
            continue

    # -------------------- Option 2: Perform analysis --------------------
    elif choice == "2":
        # Gets dataset range
        (min_year, min_quarter), (max_year, max_quarter) = get_year_quarter_range(worksheet)

        # If no data exists, stop
        if not min_year or not max_year:
            print("\n No data available in the database to perform analysis.")
            continue

        # Greets user
        print("\n Welcome to Statistical and Price Summary Analysis")

        # Prompts start year
        start_year = get_integer_input(
            f"\n Enter the start Year (YYYY) [Range: {min_year}-{max_year}]: ",
            min_year, max_year
        )

        # Limits start quarter range if start year is max year
        start_quarter_range = max_quarter if start_year == max_year else 4
        # Prompts start quarter
        start_quarter = get_integer_input(
            f" Enter the start Quarter (1-4) [Range: 1-{start_quarter_range}]: ",
            1, start_quarter_range
        )

        # Prompts end year
        end_year = get_integer_input(
            f" Enter the end Year (YYYY) [Range: {start_year}-{max_year}]: ",
            start_year, max_year
        )

        # Limits end quarter range if end year is max year
        end_quarter_range = max_quarter if end_year == max_year else 4
        # Prompts end quarter
        end_quarter = get_integer_input(
            f" Enter the end Quarter (1-4) [Range: 1-{end_quarter_range}]: ",
            1, end_quarter_range
        )

        # Prompts for county selection
        print("\n Select the county for analysis:")
        print(" 1: Nationally")
        print(" 2: Dublin")
        print(" 3: Cork")
        print(" 4: Galway")
        print(" 5: Limerick")
        print(" 6: Waterford")
        print(" 7: Other counties")
        county_choice = get_integer_input("\n Enter the number for selected county: ", 1, 7)

        # Maps menu choice to the expected sheet header
        county_column_mapping = {
            1: "Nationally",
            2: "Dublin",
            3: "Cork",
            4: "Galway",
            5: "Limerick",
            6: "Waterford",
            7: "Other_counties",
        }

        # Uses mapping to select county column
        selected_county = county_column_mapping[county_choice]

        # Initializes result containers
        data_values = []
        data_rows = []
        start_price = None
        end_price = None
        summary_message = "\n No data available for that range!"

        try:
            # Pulls all records once
            records = worksheet.get_all_records()

            # If we have records, resolve the actual column key used in the sheet
            if records:
                actual_key = resolve_column_key(selected_county, records[0].keys())
            else:
                actual_key = None

            # If we cannot match the header, fail with a clear message
            if records and actual_key is None:
                available = ", ".join(records[0].keys())
                raise KeyError(
                    f"Could not find a column matching '{selected_county}'. "
                    f"Available columns are: {available}"
                )

            # Converts periods to integers for easy comparison (e.g., 19751)
            start_period = int(f"{start_year}{start_quarter}")
            end_period = int(f"{end_year}{end_quarter}")

            # Iterates through each record
            for record in records:
                # Reads year and quarter from record
                record_year = int(record.get("Year"))
                record_quarter = int(record.get("Quarter"))
                # Builds record period (e.g., 19804)
                record_period = int(f"{record_year}{record_quarter}")

                # Filters records inside the selected period range
                if start_period <= record_period <= end_period:
                    # Reads the county value from the resolved column key
                    value = record.get(actual_key) if actual_key else None

                    # Cleans string currency formats if needed
                    if isinstance(value, str):
                        value = value.replace("€", "").replace(",", "").strip()

                    # Skips empty values
                    if value:
                        # Converts to float
                        float_value = float(value)
                        # Appends to the analysis list
                        data_values.append(float_value)
                        # Appends to the CSV rows list with period info
                        data_rows.append({
                            "Year": record_year,
                            "Quarter": record_quarter,
                            "Price": float_value
                        })

                        # Captures start price when period matches start
                        if record_year == start_year and record_quarter == start_quarter:
                            start_price = float_value

                        # Captures end price when period matches end
                        if record_year == end_year and record_quarter == end_quarter:
                            end_price = float_value

            # If no data matched, show message
            if not data_values:
                print("\n +--------------------------------------------------+")
                print("       No data available for the range chosen\n")
                print("                  Please try again!")
                print(" +--------------------------------------------------+\n")
            else:
                # Computes percent change if both endpoints exist
                if start_price is not None and end_price is not None:
                    percentage_change = ((end_price - start_price) / start_price) * 100
                    change_description = "increased" if percentage_change >= 0 else "decreased"
                    summary_message = f"Prices have {change_description} by {abs(percentage_change):.2f}%"
                else:
                    summary_message = (
                        "Unable to calculate overall price changes\n"
                        "Incomplete data, please try again!"
                    )

                # Prints summary box
                print("\n +--------------------------------------------------+")
                print(" |              Summary of Price Changes:           |")
                print(" +--------------------------------------------------+")
                print(f"                From {start_year} Q{start_quarter} to {end_year} Q{end_quarter}")
                print(f"            {summary_message}")
                print(f"               New Property - {selected_county}")
                print(" +--------------------------------------------------+")

                # Computes descriptive stats
                stats = calculate_statistics(data_values)

                # Prints stats box
                print(" |                Summary Statistics:               |")
                print(" +--------------------------------------------------+")
                print(f"       Average (mean):              €{stats['average']}")
                print(f"       Standard Deviation (+/-):    €{stats['std_dev']}")
                print(" +--------------------------------------------------+")
                print(f"       Minimum Value:               €{stats['min_value']}")
                print(f"       Maximum Value:               €{stats['max_value']}")
                print(f"       Range:                       €{stats['data_range']}")
                print(" +--------------------------------------------------+")
                print(f"       Lower Quartile (Q1):         €{stats['Q1']}")
                print(f"       Median (Q2):                 €{stats['median']}")
                print(f"       Upper Quartile (Q3):         €{stats['Q3']}")
                print(f"       IQR:                         €{stats['IQR']}")
                print(" +--------------------------------------------------+\n")

        except Exception as e:
            # Prints any runtime error without crashing the whole app
            print(f"\n An error occurred: {e}")

        # Calls export prompt (saves both TXT and CSV if user says yes)
        save_results(
            data_rows, data_values, summary_message,
            start_year, start_quarter, end_year, end_quarter,
            selected_county, start_price, end_price
        )

    # -------------------- Option 3: Exit --------------------
    elif choice == "3":
        # Exit message
        print("\n Exiting program... \n \n Thanks for using this 'App', Bye!")
        print("\n +--------------------------------------------------+")
        break

    # -------------------- Invalid input --------------------
    else:
        # Prompts user to choose 1 to 3
        print("\n Invalid choice, numbers can only be 1 to 3, please try again.\n")