"""
Unit tests for data normalization, currency cleaning, date parsing, and column auto-mapping.
"""

import pytest
import pandas as pd
from src.parser import (
    clean_currency_str,
    clean_date_str,
    auto_map_columns,
    normalize_statement_dataframe,
    STANDARD_HEADERS
)


def test_clean_currency_str():
    # Standard positive currency strings
    assert clean_currency_str("$1,234.56") == 1234.56
    assert clean_currency_str("€ 500.00") == 500.00
    assert clean_currency_str("£12.99") == 12.99
    assert clean_currency_str(" 4,250.00 ") == 4250.00

    # Negative signs
    assert clean_currency_str("-$100.00") == -100.00
    assert clean_currency_str("(150.75)") == -150.75
    assert clean_currency_str("250.00-") == -250.00
    assert clean_currency_str("75.00 DR") == -75.00
    assert clean_currency_str("100.00 CR") == 100.00

    # None and NaN
    assert clean_currency_str(None) is None
    assert clean_currency_str("") is None
    assert clean_currency_str("   ") is None


def test_clean_date_str():
    assert clean_date_str("2024-01-15") == "2024-01-15"
    assert clean_date_str("01/15/2024") == "2024-01-15"
    assert clean_date_str("15-Jan-2024") == "2024-01-15"
    assert clean_date_str("15 Jan 2024") == "2024-01-15"
    assert clean_date_str("Jan 15, 2024") == "2024-01-15"
    assert clean_date_str("2024.01.15") == "2024-01-15"
    assert clean_date_str(None) is None
    assert clean_date_str("") is None


def test_auto_map_columns():
    cols = ["Txn Date", "Details", "Withdrawal ($)", "Deposit ($)", "Running Bal"]
    mapping = auto_map_columns(cols)

    assert mapping["Date"] == "Txn Date"
    assert mapping["Description"] == "Details"
    assert mapping["Debit"] == "Withdrawal ($)"
    assert mapping["Credit"] == "Deposit ($)"
    assert mapping["Balance"] == "Running Bal"


def test_normalize_statement_dataframe():
    raw_data = {
        "Date": ["01/02/2024", "01/03/2024"],
        "Transaction Details": ["Salary", "Coffee Shop"],
        "Debit": ["", "$6.75"],
        "Credit": ["$4,250.00", ""],
        "Balance": ["$4,250.00", "$4,243.25"]
    }
    raw_df = pd.DataFrame(raw_data)
    norm_df = normalize_statement_dataframe(raw_df)

    assert list(norm_df.columns) == STANDARD_HEADERS
    assert norm_df["Date"].tolist() == ["2024-01-02", "2024-01-03"]
    assert norm_df["Description"].tolist() == ["Salary", "Coffee Shop"]
    assert norm_df["Credit"].tolist()[0] == 4250.00
    assert norm_df["Debit"].tolist()[1] == 6.75
    assert norm_df["Amount"].tolist() == [4250.00, -6.75]
