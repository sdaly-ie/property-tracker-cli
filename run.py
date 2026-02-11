# REMINDER: Terminal output target: 80 characters wide & 24 rows high
#
# Property Tracker (CLI)
# - Stores data in a Google Sheet (lightweight datastore)
# - Authenticates using a Google Cloud service account JSON key
#
# Configuration:
#   export PT_CREDS_PATH="$HOME/.secrets/property-tracker-creds.json"
#   export PT_SPREADSHEET_ID="1gdnnmodlkR8CzNAhXfKP90T_VBpnkSQVKvJ2ezjDOX8"
#
# Notes:
# - Do NOT commit credentials to Git.
# - Opening by Spreadsheet ID avoids needing Google Drive API enabled.

# Import OS helpers for environment variables
import os

# Import JSON to read the service account email from the creds file (for helpful errors)
import json

# Import Path to build safe file paths
from pathlib import Path

# Import stats helpers
import statistics

# Import NumPy for percentiles (quartiles / IQR)
import numpy as np

# Import CSV writer for exporting results
import csv

# Import gspread for Google Sheets access
import gspread

# Import Google credentials loader for service accounts
from google.oauth2.service_account import Credentials

# Import specific gspread exception so we can raise a clear message
from gspread.exceptions import SpreadsheetNotFound


# -------------------- Google Sheets connection --------------------

# Sheets-only scope is enough when opening by Spreadsheet ID
SCOPE = ["https://www.googleapis.com/auth/spreadsheets"]

# Default location for creds file (recommended: outside repo)
DEFAULT_CREDS_PATH = Path.home() / ".secrets" / "property-tracker-creds.json"

# Read creds path from environment variable or fall back to default
CREDS_PATH = Path(os.getenv("PT_CREDS_PATH", str(DEFAULT_CREDS_PATH))).expanduser()

# Fail fast if creds file does not exist
if not CREDS_PATH.exists():
    raise FileNotFoundError(
        f"\nCredentials file not found: {CREDS_PATH}\n\n"
        "Fix:\n"
        "  export PT_CREDS_PATH=/full/path/to/service-account-key.json\n"
    )

# Optional default spreadsheet ID for convenience (you can change/remove this later)
DEFAULT_SPREADSHEET_ID = "1gdnnmodlkR8CzNAhXfKP90T_VBpnkSQVKvJ2ezjDOX8"

# Read spreadsheet ID from env var or fall back to default
SPREADSHEET_ID = os.getenv("PT_SPREADSHEET_ID", DEFAULT_SPREADSHEET_ID).strip()

# Catch common placeholders or missing values
PLACEHOLDER_IDS = {
    "",
    "YOUR_REAL_SHEET_ID",
    "PASTE_YOUR_SHEET_ID_HERE",
    "YOUR_SHEET_ID",
    "PASTE_THE_LONG_ID_HERE",
}
if SPREADSHEET_ID in PLACEHOLDER_IDS:
    raise ValueError(
        "\nPT_SPREADSHEET_ID is missing or still set to a placeholder.\n\n"
        "Fix: open your Google Sheet in the browser and copy the ID from the URL:\n"
        "https://docs.google.com/spreadsheets/d/<THIS_PART>/edit\n"
        "Then:\n"
        "  export PT_SPREADSHEET_ID=<THIS_PART>\n"
        "and rerun.\n"
    )

# Try to read the service account email so we can tell you who to share the sheet with
service_account_email = None
try:
    with open(CREDS_PATH, "r", encoding="utf-8") as f:
        service_account_email = json.load(f).get("client_email")
except Exception:
    service_account_email = None

# Load credentials and apply the scope
creds = Credentials.from_service_account_file(str(CREDS_PATH)).with_scopes(SCOPE)

# Authorize gspread client
gspread_client = gspread.authorize(creds)

# Open the spreadsheet by ID with a helpful error if not shared
try:
    SHEET = gspread_client.open_by_key(SPREADSHEET_ID)
except SpreadsheetNotFound as e:
    raise SpreadsheetNotFound(
        "\nSpreadsheetNotFound (404).\n"
        "This almost always means the spreadsheet is NOT shared with your service account.\n\n"
        "Fix:\n"
        "1) Open the Google Sheet in your browser\n"
        "2) Click Share\n"
        "3) Add this email as Editor:\n"
        f"   {service_account_email or '[could not read client_email from creds file]'}\n"
        "4) Save, then rerun: python3 run.py\n"
    ) from e

# Select the first worksheet/tab
worksheet = SHEET.get_worksheet(0)


# -------------------- App logic --------------------

# Retrieves min & max years and quarters from all records in worksheet
def get_year_quarter_range(worksheet_obj):
    records = worksheet_obj.get_all_records()
    if not records:
        return (None, None), (None, None)

    years = sorted({record["Year"] for record in records})
    min_year, max_year = years[0], years[-1]

    min_year_quarters = {
        record["Quarter"] for record in records if record["Year"] == min_year
    }
    max_year_quarters = {
        record["Quarter"] for record in records if record["Year"] == max_year
    }

    min_quarter = min(min_year_quarters)
    max_quarter = max(max_year_quarters)

    return (min_year, min_quarter), (max_year, max_quarter)


# Calculates and returns statistical measures for dataset,
# defaulting to "N/A" when data is insufficient
def calculate_statistics(data_values):
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

    if data_values:
        stats["min_value"] = f"{min(data_values):,.2f}"
        stats["max_value"] = f"{max(data_values):,.2f}"
        stats["data_range"] = f"{max(data_values) - min(data_values):,.2f}"
        stats["median"] = f"{statistics.median(data_values):,.2f}"

        if len(data_values) >= 2:
            stats["average"] = f"{statistics.mean(data_values):,.2f}"
            stats["std_dev"] = f"{statistics.stdev(data_values):,.2f}"
            q25, q75 = np.percentile(data_values, [25, 75])
            stats["Q1"] = f"{q25:,.2f}"
            stats["Q3"] = f"{q75:,.2f}"
            stats["IQR"] = f"{q75 - q25:,.2f}"

    return stats


# Prompts the user to input valid integers, optionally constrained to a range
def get_integer_input(prompt, range_min=None, range_max=None):
    while True:
        try:
            value = int(input(prompt))

            if (range_min is not None and value < range_min) or (
                range_max is not None and value > range_max
            ):
                print(
                    f"\n Please enter a numeric value between {range_min}"
                    f" and {range_max}.\n"
                )
            else:
                return value

        except ValueError:
            print(
                "\n Invalid input. Please enter a valid integer "
                "(i.e. whole number).\n"
            )


# Save analysis summary and stats to a local text file
def save_to_text_file(
    data_values, summary_message, start_year, start_quarter, end_year, end_quarter, selected_county
):
    output_path = Path(__file__).resolve().parent / "analysis_results.txt"

    average_formatted = "N/A"
    std_dev_formatted = "N/A"
    min_value_formatted = "N/A"
    max_value_formatted = "N/A"
    data_range_formatted = "N/A"
    Q1_formatted = "N/A"
    median_formatted = "N/A"
    Q3_formatted = "N/A"
    IQR_formatted = "N/A"

    if data_values:
        min_value = min(data_values)
        max_value = max(data_values)
        data_range = max_value - min_value
        median = statistics.median(data_values)

        min_value_formatted = f"{min_value:8,.2f}"
        max_value_formatted = f"{max_value:8,.2f}"
        data_range_formatted = f"{data_range:8,.2f}"
        median_formatted = f"{median:8,.2f}"

        if len(data_values) >= 2:
            average = statistics.mean(data_values)
            std_dev = statistics.stdev(data_values)
            Q1 = np.percentile(data_values, 25)
            Q3 = np.percentile(data_values, 75)
            IQR = Q3 - Q1

            average_formatted = f"{average:8,.2f}"
            std_dev_formatted = f"{std_dev:8,.2f}"
            Q1_formatted = f"{Q1:8,.2f}"
            Q3_formatted = f"{Q3:8,.2f}"
            IQR_formatted = f"{IQR:8,.2f}"

    with open(output_path, "a", encoding="utf-8") as file:
        file.write("\n +--------------------------------------------------+\n")
        file.write(" |              Summary of Price Changes            |\n")
        file.write(" +--------------------------------------------------+\n")
        file.write(
            f"\n                From {start_year} Q{start_quarter} to "
            f"{end_year} Q{end_quarter}\n"
        )
        file.write(f"            {summary_message}\n")
        file.write(f"               New Property - {selected_county}\n")
        file.write("\n +--------------------------------------------------+\n")

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

    return output_path


# Save detailed rows + summary columns to a CSV for Excel-friendly analysis
def save_to_csv_file(
    data_rows,
    data_values,
    summary_message,
    start_year,
    start_quarter,
    end_year,
    end_quarter,
    selected_county,
    start_price,
    end_price,
):
    safe_county = str(selected_county).lower().replace(" ", "_")
    csv_path = (
        Path(__file__).resolve().parent
        / f"analysis_{start_year}Q{start_quarter}_{end_year}Q{end_quarter}_{safe_county}.csv"
    )

    mean_v = statistics.mean(data_values) if len(data_values) >= 2 else None
    std_v = statistics.stdev(data_values) if len(data_values) >= 2 else None
    min_v = min(data_values) if data_values else None
    max_v = max(data_values) if data_values else None
    range_v = (max_v - min_v) if (min_v is not None and max_v is not None) else None
    median_v = statistics.median(data_values) if data_values else None

    q1_v = q3_v = iqr_v = None
    if len(data_values) >= 2:
        q25, q75 = np.percentile(data_values, [25, 75])
        q1_v, q3_v = float(q25), float(q75)
        iqr_v = q3_v - q1_v

    pct_change = None
    if start_price is not None and end_price is not None and start_price != 0:
        pct_change = ((end_price - start_price) / start_price) * 100.0

    fieldnames = [
        "StartYear",
        "StartQuarter",
        "EndYear",
        "EndQuarter",
        "County",
        "Year",
        "Quarter",
        "Price",
        "StartPrice",
        "EndPrice",
        "PercentChange",
        "Mean",
        "StdDev",
        "Min",
        "Max",
        "Range",
        "Q1",
        "Median",
        "Q3",
        "IQR",
        "SummaryMessage",
    ]

    data_rows_sorted = sorted(data_rows, key=lambda r: (r["Year"], r["Quarter"]))

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for r in data_rows_sorted:
            writer.writerow(
                {
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
                }
            )

        if not data_rows_sorted:
            writer.writerow(
                {
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
                }
            )

    return csv_path


# Ask user whether to export, then write both TXT and CSV if yes
def save_results(
    data_rows,
    data_values,
    summary_message,
    start_year,
    start_quarter,
    end_year,
    end_quarter,
    selected_county,
    start_price,
    end_price,
):
    save_choice = input("        Like to export results? (yes/no): ").lower()

    if save_choice.startswith("y"):
        txt_path = save_to_text_file(
            data_values,
            summary_message,
            start_year,
            start_quarter,
            end_year,
            end_quarter,
            selected_county,
        )
        csv_path = save_to_csv_file(
            data_rows,
            data_values,
            summary_message,
            start_year,
            start_quarter,
            end_year,
            end_quarter,
            selected_county,
            start_price,
            end_price,
        )
        print(f"\n Results saved to:\n  {txt_path}\n  {csv_path}\n")
    else:
        print("\n         These results have not been saved.\n")


# Get the last row (latest year/quarter) from the sheet
def get_last_year_quarter(worksheet_obj):
    last_row = worksheet_obj.get_all_values()[-1]
    last_year = int(last_row[0])
    last_quarter = int(last_row[1])
    return last_year, last_quarter


# -------------------- Main Menu Loop --------------------

while True:
    options = {
        "1": "Add new information to database",
        "2": "Perform analysis on existing database",
        "3": "Exit",
    }

    print(" +--------------------------------------------------+")
    print("\n     Welcome to 'P r o p e r t y  T r a c k e r'\n")
    print("  Keeping you up-to-date with Irish property trends")

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
    choice = input("    Please select your choice and hit 'Enter': ")
    print("\n +--------------------------------------------------+")

    # -------- Option 1: Add new information --------
    if choice == "1":
        (min_year, min_quarter), (max_year, max_quarter) = get_year_quarter_range(worksheet)

        last_year, last_quarter = get_last_year_quarter(worksheet)
        next_year, next_quarter = last_year, last_quarter

        if last_quarter < 4:
            next_quarter += 1
        else:
            next_year += 1
            next_quarter = 1

        print("\n   Current data available from imported CSO dataset")
        print(
            f"    Quarter {min_quarter}, Year {min_year} to Quarter "
            f"{last_quarter}, Year {last_year}"
        )
        print(f" Please enter new data for next Quarter {next_quarter}, Year {next_year}:")
        print("\n +--------------------------------------------------+\n")

        nationally = get_integer_input("      Avg Price Nationally:      €")
        dublin = get_integer_input("      Avg Price Dublin:          €")
        cork = get_integer_input("      Avg Price Cork:            €")
        galway = get_integer_input("      Avg Price Galway:          €")
        limerick = get_integer_input("      Avg Price Limerick:        €")
        waterford = get_integer_input("      Avg Price Waterford:       €")
        other_counties = get_integer_input("      Avg Price Other Counties:  €")

        row = [
            next_year,
            next_quarter,
            nationally,
            dublin,
            cork,
            galway,
            limerick,
            waterford,
            other_counties,
        ]

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

        confirm = input("     Is the entered data correct? (yes/no): ")
        if confirm.lower().startswith("y"):
            worksheet.append_row(row)
            print("\n    New information has been added to database.\n")
        else:
            print("\n       Data entry cancelled - no data added.\n")
            continue

    # -------- Option 2: Perform analysis --------
    elif choice == "2":
        (min_year, min_quarter), (max_year, max_quarter) = get_year_quarter_range(worksheet)

        if not min_year or not max_year:
            print("\n No data available in the database to perform analysis.")
            continue

        data_values = []
        data_rows = []
        start_price = None
        end_price = None
        summary_message = "No data available for that range!"

        print("\n Welcome to Statistical and Price Summary Analysis")

        start_year = get_integer_input(
            f"\n Enter the start Year (YYYY) [Range: {min_year}-{max_year}]: ",
            min_year,
            max_year,
        )

        start_quarter_range = max_quarter if start_year == max_year else 4
        start_quarter = get_integer_input(
            f" Enter the start Quarter (1-4) [Range: 1-{start_quarter_range}]: ",
            1,
            start_quarter_range,
        )

        end_year = get_integer_input(
            f" Enter the end Year (YYYY) [Range: {start_year}-{max_year}]: ",
            start_year,
            max_year,
        )

        end_quarter_range = max_quarter if end_year == max_year else 4
        end_quarter = get_integer_input(
            f" Enter the end Quarter (1-4) [Range: 1-{end_quarter_range}]: ",
            1,
            end_quarter_range,
        )

        print("\n Select the county for analysis:")
        print(" 1: Nationally")
        print(" 2: Dublin")
        print(" 3: Cork")
        print(" 4: Galway")
        print(" 5: Limerick")
        print(" 6: Waterford")
        print(" 7: Other counties")
        county_choice = get_integer_input("\n Enter the number for selected county: ", 1, 7)

        county_column_mapping = {
            1: "Nationally",
            2: "Dublin",
            3: "Cork",
            4: "Galway",
            5: "Limerick",
            6: "Waterford",
            7: "Other_counties",
        }
        selected_county = county_column_mapping[county_choice]

        try:
            records = worksheet.get_all_records()

            start_period = int(f"{start_year}{start_quarter}")
            end_period = int(f"{end_year}{end_quarter}")

            for record in records:
                record_year = int(record.get("Year"))
                record_quarter = int(record.get("Quarter"))
                record_period = int(f"{record_year}{record_quarter}")

                if start_period <= record_period <= end_period:
                    value = record.get(selected_county)

                    if isinstance(value, str):
                        value = value.replace("€", "").replace(",", "")

                    if value is not None and value != "":
                        float_value = float(value)
                        data_values.append(float_value)

                        data_rows.append(
                            {"Year": record_year, "Quarter": record_quarter, "Price": float_value}
                        )

                        if record_year == start_year and record_quarter == start_quarter:
                            start_price = float_value
                        if record_year == end_year and record_quarter == end_quarter:
                            end_price = float_value

            if not data_values:
                print("\n +--------------------------------------------------+")
                print("       No data available for the range chosen\n")
                print("                  Please try again!")
                print(" +--------------------------------------------------+\n")
            else:
                if start_price is not None and end_price is not None and start_price != 0:
                    percentage_change = ((end_price - start_price) / start_price) * 100
                    change_description = "increased" if percentage_change >= 0 else "decreased"
                    summary_message = f"Prices have {change_description} by {abs(percentage_change):.2f}%"
                else:
                    summary_message = "Unable to calculate overall price changes (incomplete data)."

                print("\n +--------------------------------------------------+")
                print(" |              Summary of Price Changes:           |")
                print(" +--------------------------------------------------+")
                print(f"                From {start_year} Q{start_quarter} to {end_year} Q{end_quarter}")
                print(f"            {summary_message}")
                print(f"               New Property - {selected_county}")
                print(" +--------------------------------------------------+")

                stats = calculate_statistics(data_values)

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
            print(f"\n An error occurred: {e}")

        save_results(
            data_rows,
            data_values,
            summary_message,
            start_year,
            start_quarter,
            end_year,
            end_quarter,
            selected_county,
            start_price,
            end_price,
        )

    # -------- Option 3: Exit --------
    elif choice == "3":
        print("\n Exiting program...\n\n Thanks for using this app, bye!")
        print("\n +--------------------------------------------------+")
        break

    # -------- Invalid choice --------
    else:
        print("\n Invalid choice, numbers can only be 1 to 3, please try again.\n")