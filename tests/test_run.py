import csv

import run


class FakeWorksheet:
    def __init__(self, records=None, values=None):
        self._records = records or []
        self._values = values or []

    def get_all_records(self):
        return self._records

    def get_all_values(self):
        return self._values


def test_get_year_quarter_range_returns_min_and_max():
    worksheet = FakeWorksheet(
        records=[
            {"Year": 2024, "Quarter": 2},
            {"Year": 2023, "Quarter": 4},
            {"Year": 2024, "Quarter": 1},
            {"Year": 2022, "Quarter": 3},
        ]
    )

    assert run.get_year_quarter_range(worksheet) == ((2022, 3), (2024, 2))


def test_calculate_statistics_for_multiple_values():
    stats = run.calculate_statistics([100000, 110000, 120000, 130000])

    assert stats["average"] == "115,000.00"
    assert stats["min_value"] == "100,000.00"
    assert stats["max_value"] == "130,000.00"
    assert stats["median"] == "115,000.00"
    assert stats["Q1"] == "107,500.00"
    assert stats["Q3"] == "122,500.00"
    assert stats["IQR"] == "15,000.00"


def test_calculate_statistics_for_single_value_keeps_non_applicable_fields():
    stats = run.calculate_statistics([100000])

    assert stats["min_value"] == "100,000.00"
    assert stats["max_value"] == "100,000.00"
    assert stats["median"] == "100,000.00"
    assert stats["average"] == "N/A"
    assert stats["std_dev"] == "N/A"
    assert stats["Q1"] == "N/A"
    assert stats["Q3"] == "N/A"
    assert stats["IQR"] == "N/A"


def test_get_last_year_quarter_reads_last_row():
    worksheet = FakeWorksheet(
        values=[
            ["2024", "3"],
            ["2024", "4"],
        ]
    )

    assert run.get_last_year_quarter(worksheet) == (2024, 4)


def test_save_to_csv_file_writes_sorted_rows_and_summary(tmp_path, monkeypatch):
    monkeypatch.setattr(run, "__file__", str(tmp_path / "run.py"))

    csv_path = run.save_to_csv_file(
        data_rows=[
            {"Year": 2024, "Quarter": 2, "Price": 220000.0},
            {"Year": 2024, "Quarter": 1, "Price": 200000.0},
        ],
        data_values=[200000.0, 220000.0],
        summary_message="Prices have increased by 10.00%",
        start_year=2024,
        start_quarter=1,
        end_year=2024,
        end_quarter=2,
        selected_county="Dublin",
        start_price=200000.0,
        end_price=220000.0,
    )

    assert csv_path.exists()

    with open(csv_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    assert [row["Quarter"] for row in rows] == ["1", "2"]
    assert rows[0]["PercentChange"] == "10.0"
    assert rows[0]["SummaryMessage"] == "Prices have increased by 10.00%"