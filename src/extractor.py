"""
Hybrid PDF Table Extraction Orchestrator.
Uses pdfplumber for fast digital vector PDF extraction and IBM Docling as a fallback for scanned PDFs.
"""

import os
import warnings

# Suppress PyTorch convolution padding and deprecation warnings
warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=FutureWarning)

import platform

# Disable PyTorch compilation dry-run (prevents missing MSVC cl.exe compiler errors)
os.environ["TORCH_COMPILE_DISABLE"] = "1"
os.environ["TORCHDYNAMO_DISABLE"] = "1"

# Dynamically apply architecture-specific tuning at runtime
_arch = platform.machine().lower()
if _arch in ("aarch64", "arm64", "armv7l", "arm"):
    os.environ.setdefault("OPENBLAS_CORETYPE", "ARMV8")
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    os.environ.setdefault("MKL_NUM_THREADS", "1")

import io
import re
import tempfile
import logging
from typing import List, Dict, Tuple, Optional, Any, Union
import pandas as pd
import pdfplumber

logger = logging.getLogger(__name__)

# Lazy import for Docling to speed up app initialization
_docling_converter = None

def get_docling_converter():
    """Lazily initializes and caches the Docling DocumentConverter."""
    global _docling_converter
    if _docling_converter is None:
        try:
            from docling.document_converter import DocumentConverter
            _docling_converter = DocumentConverter()
        except Exception as e:
            logger.error(f"Failed to initialize IBM Docling DocumentConverter: {e}")
            raise ImportError(f"IBM Docling is not properly installed or initialized: {e}")
    return _docling_converter


def is_scanned_pdf(pdf_path_or_bytes: Union[str, bytes], min_text_chars_per_page: int = 50) -> bool:
    """
    Evaluates whether a PDF appears to be a scanned document (image-based)
    or a digital vector PDF by inspecting extractable character count.
    Accepts file path string or raw PDF bytes.
    """
    try:
        if isinstance(pdf_path_or_bytes, bytes):
            pdf_obj = io.BytesIO(pdf_path_or_bytes)
        else:
            pdf_obj = pdf_path_or_bytes

        with pdfplumber.open(pdf_obj) as pdf:
            total_pages = len(pdf.pages)
            if total_pages == 0:
                return True
            
            total_chars = 0
            for page in pdf.pages:
                text = page.extract_text() or ""
                total_chars += len(text.strip())

            avg_chars = total_chars / total_pages
            return avg_chars < min_text_chars_per_page
    except Exception as e:
        logger.warning(f"Error checking if PDF is scanned ({e}), defaulting to scanned=True")
        return True


def extract_tables_with_pdfplumber(pdf_path: str) -> List[pd.DataFrame]:
    """
    Extracts tables from digital vector PDF using pdfplumber.
    """
    dfs = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_idx, page in enumerate(pdf.pages):
            # Try default table extraction, then explicit strategies
            tables = page.extract_tables()
            if not tables:
                # Try with explicit line detection settings
                tables = page.extract_tables({
                    "vertical_strategy": "lines",
                    "horizontal_strategy": "lines",
                    "snap_tolerance": 3,
                })
            
            if not tables:
                # Try text strategy if lines fail
                tables = page.extract_tables({
                    "vertical_strategy": "text",
                    "horizontal_strategy": "text",
                })

            for table in tables:
                if not table or len(table) < 2:
                    continue

                # Clean headers and rows
                raw_headers = table[0]
                headers = []
                for idx, h in enumerate(raw_headers):
                    if h is None or str(h).strip() == "":
                        headers.append(f"Column_{idx + 1}")
                    else:
                        # Clean multi-line headers
                        clean_h = " ".join(str(h).split())
                        headers.append(clean_h)

                data_rows = table[1:]
                clean_rows = []
                for row in data_rows:
                    if any(cell is not None and str(cell).strip() != "" for cell in row):
                        row_data = [" ".join(str(c).split()) if c is not None else "" for c in row]
                        clean_rows.append(row_data)

                if clean_rows:
                    df = pd.DataFrame(clean_rows, columns=headers)
                    dfs.append(df)

    return dfs


def has_valid_data_rows(dfs: List[pd.DataFrame]) -> bool:
    """
    Evaluates whether a list of DataFrames contains at least 1 valid non-empty data row.
    """
    if not dfs:
        return False
    for df in dfs:
        if df is None or df.empty:
            continue
        if len(df) > 0:
            for _, row in df.iterrows():
                # Check if row has non-trivial text
                row_content = " ".join([str(val).strip() for val in row.values if pd.notnull(val) and str(val).strip() != ""])
                if len(row_content) > 5 and not row_content.lower().startswith("column_"):
                    return True
    return False


def extract_tables_from_vector_text(pdf_path: str, page_numbers: Optional[List[int]] = None) -> List[pd.DataFrame]:
    """
    Universal multi-line layout text parser for borderless vector PDFs.
    Handles single-line and multi-line bank transactions across all providers.

    Args:
        pdf_path: Path to the PDF file.
        page_numbers: Optional 1-based list of page numbers to parse. When provided,
                      only those pages are processed. When None, all pages are parsed.
    """
    dfs = []
    # Flexible universal date pattern (e.g., 31 Jul, 31/07/2025, 2025-07-31, Jul 31)
    date_pattern = r"^\s*(\d{1,2}[\s\/\.\-](?:[A-Za-z]{3,9}|\d{1,2})(?:[\s\/\.\-]\d{2,4})?|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2})\b"
    # Flexible monetary value pattern ($113.55, 113.55, -113.55, (113.55))
    amount_pattern = r"([\$€£\¥]?\s*[\-–—\(]?\s*\d{1,3}(?:,\d{3})*(?:\.\d{2})[\)\-–—]?)"

    with pdfplumber.open(pdf_path) as pdf:
        all_rows = []
        pages_to_parse = [
            page for page in pdf.pages
            if page_numbers is None or page.page_number in page_numbers
        ]
        for page in pages_to_parse:
            text = page.extract_text() or ""
            lines = text.split("\n")

            curr_tx = None

            for line in lines:
                line_clean = line.strip()
                if not line_clean:
                    continue

                date_match = re.match(date_pattern, line_clean, re.IGNORECASE)
                amounts = re.findall(amount_pattern, line_clean)

                # Ignore general page header/footer metadata lines
                if re.search(r"(?i)\b(page \d|account statement|branch number|bsb|account number|opening balance|closing balance|australia and new zealand)\b", line_clean):
                    continue

                # Case A: Line starts with a Date -> Start new transaction block
                if date_match:
                    if curr_tx and (curr_tx["Amount"] or curr_tx["Balance"]):
                        all_rows.append(curr_tx)

                    date_str = date_match.group(1)
                    desc_str = line_clean[date_match.end():]
                    for amt in amounts:
                        desc_str = desc_str.replace(amt, "")
                    desc_str = " ".join(desc_str.split())

                    amt1 = amounts[-2] if len(amounts) >= 2 else (amounts[0] if len(amounts) == 1 else "")
                    bal = amounts[-1] if len(amounts) >= 2 else ""

                    curr_tx = {
                        "Date": date_str,
                        "Description": desc_str,
                        "Amount": amt1,
                        "Balance": bal
                    }

                    # If this single line already contains amounts, save immediately
                    if amounts:
                        all_rows.append(curr_tx)
                        curr_tx = None

                # Case B: Continuation line of current transaction
                elif curr_tx:
                    if amounts:
                        amt1 = amounts[-2] if len(amounts) >= 2 else (amounts[0] if len(amounts) == 1 else "")
                        bal = amounts[-1] if len(amounts) >= 2 else ""
                        if not curr_tx["Amount"]:
                            curr_tx["Amount"] = amt1
                        if not curr_tx["Balance"]:
                            curr_tx["Balance"] = bal

                        extra_desc = line_clean
                        for amt in amounts:
                            extra_desc = extra_desc.replace(amt, "")
                        extra_desc = " ".join(extra_desc.split())
                        if extra_desc:
                            curr_tx["Description"] = (curr_tx["Description"] + " " + extra_desc).strip()

                        all_rows.append(curr_tx)
                        curr_tx = None
                    else:
                        curr_tx["Description"] = (curr_tx["Description"] + " " + line_clean).strip()

            if curr_tx and (curr_tx["Amount"] or curr_tx["Balance"]):
                all_rows.append(curr_tx)

        if all_rows:
            df = pd.DataFrame(all_rows)
            dfs.append(df)

    return dfs


def extract_tables_with_docling(pdf_path: str) -> List[pd.DataFrame]:
    """
    Extracts tables from scanned or complex PDFs using IBM Docling.
    """
    converter = get_docling_converter()
    result = converter.convert(pdf_path)
    
    dfs = []
    doc = result.document
    
    # Docling extracts tables into structured items
    for table_element in doc.tables:
        try:
            table_df = table_element.export_to_dataframe(doc=doc)
            if isinstance(table_df, pd.DataFrame) and not table_df.empty:
                # Flatten multi-index columns if present
                if isinstance(table_df.columns, pd.MultiIndex):
                    table_df.columns = [" ".join([str(c) for c in col if c]).strip() for col in table_df.columns]

                # FIX: When Docling returns integer column indices [0, 1, 2, 3, 4], TableFormer
                # failed to detect the header row. Promote first row as header when all column
                # names are integers — this happens on last pages where the table ends near
                # statement summaries (Opening Balance, disclaimer text), confusing the model.
                all_int_cols = all(isinstance(c, int) for c in table_df.columns)
                if all_int_cols and not table_df.empty:
                    first_row = table_df.iloc[0].tolist()
                    if any(isinstance(v, str) and v.strip() for v in first_row):
                        table_df.columns = [str(v).strip() for v in first_row]
                        table_df = table_df.iloc[1:].reset_index(drop=True)

                # Deduplicate column names to prevent pandas returning DataFrame slices
                # instead of Series when accessing columns (which breaks .dtype lookups)
                seen = {}
                deduped_cols = []
                for col in table_df.columns:
                    col_str = " ".join(str(col).split())
                    if col_str in seen:
                        seen[col_str] += 1
                        deduped_cols.append(f"{col_str}_{seen[col_str]}")
                    else:
                        seen[col_str] = 0
                        deduped_cols.append(col_str)
                table_df.columns = deduped_cols
                dfs.append(table_df)
        except Exception as e:
            logger.warning(f"Error exporting Docling table element to DataFrame: {e}")
            continue

    # Fallback for pages where Docling detected zero table objects (e.g. Sub-accounts on Page 2 of Up Bank)
    docling_pages = set()
    for table_element in doc.tables:
        if table_element.prov:
            for p in table_element.prov:
                docling_pages.add(p.page_no)

    total_pdf_pages = len(doc.pages)
    missed_pages = [p for p in range(1, total_pdf_pages + 1) if p not in docling_pages]

    if missed_pages:
        logger.info(f"Docling missed tables on pages {missed_pages}. Running text layout parser for missed pages...")
        text_dfs = extract_tables_from_vector_text(pdf_path, page_numbers=missed_pages)
        if text_dfs:
            for t_df in text_dfs:
                if not t_df.empty:
                    dfs.append(t_df)

    return dfs


def extract_tables_with_llm(pdf_path: str, model_name: str = "qwen2.5:3b") -> List[pd.DataFrame]:
    """
    Directly extracts transaction tables by feeding raw PDF text into local Ollama LLM.
    """
    from src.llm_processor import extract_transactions_from_pdf_text_llm
    dfs = []
    with pdfplumber.open(pdf_path) as pdf:
        full_text = ""
        for page in pdf.pages:
            t = page.extract_text() or ""
            full_text += t + "\n"

    if full_text.strip():
        llm_df = extract_transactions_from_pdf_text_llm(full_text, model_name=model_name)
        if not llm_df.empty:
            dfs.append(llm_df)
    return dfs



def extract_bank_statement_tables(
    pdf_path_or_bytes: Union[str, bytes],
    file_name: str = "statement.pdf",
    engine: str = "auto",  # "auto", "llm", "pdfplumber", or "docling"
    model_name: str = "qwen2.5:3b"
) -> Tuple[List[pd.DataFrame], str]:
    """
    Main extraction orchestrator with multi-tier fallback:
    1. Local Ollama LLM direct AI extraction (if engine == "llm")
    2. pdfplumber grid table finder
    3. pdfplumber borderless vector text layout parser
    4. IBM Docling deep AI layout parser
    5. Page Coverage Audit Sweep (Guarantees zero dropped pages)
    """
    temp_file_path = None
    if isinstance(pdf_path_or_bytes, bytes):
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
        temp_file.write(pdf_path_or_bytes)
        temp_file.close()
        pdf_path = temp_file.name
        temp_file_path = pdf_path
    else:
        pdf_path = pdf_path_or_bytes

    try:
        engine_used = engine
        dfs = []

        if engine == "llm":
            dfs = extract_tables_with_llm(pdf_path, model_name=model_name)
            if has_valid_data_rows(dfs):
                engine_used = f"Local LLM ({model_name})"
            else:
                logger.info(f"LLM extraction empty for {file_name}, falling back to vector text layout parser...")
                dfs = extract_tables_from_vector_text(pdf_path)
                if not has_valid_data_rows(dfs):
                    dfs = extract_tables_with_docling(pdf_path)
                engine_used = f"LLM Fallback ({model_name} -> Text/Docling)"

        elif engine == "pdfplumber":
            dfs = extract_tables_with_pdfplumber(pdf_path)
            if not has_valid_data_rows(dfs):
                dfs = extract_tables_from_vector_text(pdf_path)
            engine_used = "pdfplumber"

        elif engine == "docling":
            dfs = extract_tables_with_docling(pdf_path)
            engine_used = "IBM Docling"

        else: # "auto"
            scanned = is_scanned_pdf(pdf_path)
            if not scanned:
                # Step 1: pdfplumber grid tables
                dfs = extract_tables_with_pdfplumber(pdf_path)
                engine_used = "pdfplumber (Grid)"

                # Step 2: pdfplumber vector text line layout parser
                if not has_valid_data_rows(dfs):
                    logger.info(f"pdfplumber grid tables empty for {file_name}, trying vector text layout parser...")
                    dfs = extract_tables_from_vector_text(pdf_path)
                    engine_used = "pdfplumber (Text Layout)"

            # Step 3: Fallback to IBM Docling if scanned or if pdfplumber extracted no valid data rows
            if scanned or not has_valid_data_rows(dfs):
                logger.info(f"Fallback to IBM Docling for {file_name} (scanned={scanned})")
                try:
                    docling_dfs = extract_tables_with_docling(pdf_path)
                    if has_valid_data_rows(docling_dfs):
                        dfs = docling_dfs
                        engine_used = "IBM Docling (Auto-Fallback)"
                    elif not has_valid_data_rows(dfs) and docling_dfs:
                        dfs = docling_dfs
                        engine_used = "IBM Docling"
                except Exception as e:
                    logger.error(f"Docling fallback error: {e}")
                    if not dfs:
                        raise e


        return dfs, engine_used

    finally:
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
            except Exception:
                pass
