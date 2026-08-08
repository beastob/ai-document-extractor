"""
Unit tests for Australian ATO Tax Categorization, merchant keyword rules, and JSON repair helper.
"""

import pytest
import pandas as pd
from src.llm_processor import (
    categorize_transaction_offline_rules,
    categorize_transactions_df,
    clean_and_parse_json,
    ATO_TAX_CATEGORIES,
    DEDUCTIBILITY_STATUSES
)


def test_clean_and_parse_json():
    # Test markdown fences and trailing comma repair
    raw_llm_output = """
    ```json
    {
        "transactions": [
            {"Date": "2025-07-31", "Description": "VISA DEBIT", "Amount": 113.55,},
        ],
    }
    ```
    """
    parsed = clean_and_parse_json(raw_llm_output)
    assert parsed is not None
    assert "transactions" in parsed
    assert len(parsed["transactions"]) == 1
    assert parsed["transactions"][0]["Amount"] == 113.55


def test_categorize_transaction_offline_rules():
    # Test Motor Vehicle
    cat, status, _ = categorize_transaction_offline_rules("SHELL COLES EXPRESS FUEL")
    assert cat == "Motor Vehicle & Travel"
    assert status == "Tax Deductible"

    # Test Work Equipment
    cat, status, _ = categorize_transaction_offline_rules("BUNNINGS 3045 CHATSWOOD")
    assert cat == "Work Equipment & Supplies"
    assert status == "Tax Deductible"

    # Test Software & Subscriptions
    cat, status, _ = categorize_transaction_offline_rules("XERO MONTHLY SUBSCRIPTION")
    assert cat == "Software & Subscriptions"
    assert status == "Tax Deductible"

    # Test Home Office & Tech
    cat, status, _ = categorize_transaction_offline_rules("OFFICEWORKS SYDNEY CBD")
    assert cat == "Home Office & Tech"
    assert status == "Potentially Deductible"

    # Test Personal Groceries
    cat, status, _ = categorize_transaction_offline_rules("WOOLWORTHS SUPERMARKET")
    assert cat == "Personal / Non-Deductible"
    assert status == "Non-Deductible"


def test_categorize_transactions_df():
    data = {
        "Date": ["2024-01-03", "2024-01-05"],
        "Description": ["BUNNINGS CHATSWOOD", "WOOLWORTHS METRO"],
        "Amount": [-185.50, -42.30]
    }
    df = pd.DataFrame(data)
    cat_df = categorize_transactions_df(df, provider="offline")

    assert "ATO Tax Category" in cat_df.columns
    assert "Deductibility" in cat_df.columns
    assert cat_df["ATO Tax Category"].iloc[0] == "Work Equipment & Supplies"
    assert cat_df["ATO Tax Category"].iloc[1] == "Personal / Non-Deductible"
