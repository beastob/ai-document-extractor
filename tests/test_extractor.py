"""
Integration test for PDF extraction pipeline using synthetic sample PDFs.
"""

import pytest
import pandas as pd
from src.sample_generator import generate_vector_pdf_bytes
from src.extractor import (
    extract_bank_statement_tables,
    is_scanned_pdf,
    has_valid_data_rows,
    extract_tables_from_vector_text
)


def test_vector_pdf_extraction():
    pdf_bytes = generate_vector_pdf_bytes()
    
    # Test vector detection
    scanned = is_scanned_pdf(pdf_bytes)
    assert scanned is False

    # Test pdfplumber extraction
    dfs, engine_used = extract_bank_statement_tables(pdf_bytes, engine="pdfplumber")
    assert len(dfs) > 0
    assert "pdfplumber" in engine_used
    assert has_valid_data_rows(dfs) is True

    df = dfs[0]
    assert not df.empty
    assert len(df) >= 10


def test_has_valid_data_rows():
    empty_df = pd.DataFrame()
    dummy_df = pd.DataFrame(columns=["Column_1", "Column_2"])
    valid_df = pd.DataFrame([{"Date": "2025-07-31", "Description": "VISA PURCHASE", "Amount": "113.55"}])

    assert has_valid_data_rows([empty_df]) is False
    assert has_valid_data_rows([dummy_df]) is False
    assert has_valid_data_rows([valid_df]) is True
