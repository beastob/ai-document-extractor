"""
Data Normalizer and Header Mapper for Bank Statements.
Handles date formatting, currency cleaning, negative sign standardization,
and intelligent column mapping to standard headers.
"""

import io
import os
import re
from typing import Dict, List, Optional, Any, Tuple, Union
import pandas as pd
from datetime import datetime

STANDARD_HEADERS = ["Date", "Description", "Debit", "Credit", "Amount", "Balance"]

# Regular expressions for header matching
HEADER_PATTERNS = {
    "Date": r"(?i)\b(date|trans(action)?\s*date|posting\s*date|effective\s*date|val(ue)?\s*date|datum|t-date)\b",
    "Description": r"(?i)\b(desc(ription)?|details?|narrative|particulars|payee|memo|remark|transaction|ref(erence)?)\b",
    "Debit": r"(?i)\b(debit|withdrawal|out|charge|spent|paid\s*out|money\s*out|dr)\b",
    "Credit": r"(?i)\b(credit|deposit|in|received|paid\s*in|money\s*in|cr)\b",
    "Amount": r"(?i)\b(amount|sum|value|total|txn\s*amount)\b",
    "Balance": r"(?i)\b(balance|running\s*balance|bal|ending\s*balance|account\s*balance)\b",
}


def clean_currency_str(val: Any) -> Optional[float]:
    """
    Cleans string representation of monetary values into floats.
    Handles currency symbols ($ € £ ¥ ₹ USD EUR AUD CAD), parenthetical negatives (100.00),
    trailing negatives 100.00-, space separation, and DR/CR suffixes.
    """
    if pd.isna(val) or val is None:
        return None

    if isinstance(val, (int, float)):
        return float(val)

    val_str = str(val).strip()
    if not val_str:
        return None

    # Check for negative indicators
    is_negative = False
    
    # Check parenthetical negative like (100.00)
    if val_str.startswith("(") and val_str.endswith(")"):
        is_negative = True
        val_str = val_str[1:-1].strip()

    # Check trailing negative or DR flag like "100.00-" or "100.00 DR"
    elif re.search(r"[-–—]\s*$", val_str) or re.search(r"(?i)\bDR\b", val_str):
        is_negative = True
        val_str = re.sub(r"[-–—]\s*$", "", val_str)
        val_str = re.sub(r"(?i)\bDR\b", "", val_str).strip()

    # Check leading negative like "-100.00" or "- $100.00"
    elif re.search(r"^[-–—]", val_str):
        is_negative = True
        val_str = re.sub(r"^[-–—]\s*", "", val_str).strip()

    # Clean out currency symbols, codes, commas, and excess whitespace
    val_str = re.sub(r"[^\d.,]", "", val_str)

    if not val_str:
        return None

    # Handle European format where dot is thousand separator and comma is decimal (e.g. 1.234,56)
    if re.match(r"^\d{1,3}(\.\d{3})+,\d{2}$", val_str):
        val_str = val_str.replace(".", "").replace(",", ".")
    else:
        # Standard format 1,234.56 -> 1234.56
        val_str = val_str.replace(",", "")

    try:
        num = float(val_str)
        return -num if is_negative else num
    except ValueError:
        return None


def extract_statement_metadata(pdf_path_or_bytes: Union[str, bytes, None] = None, pdf_text: Optional[str] = None) -> Dict[str, str]:
    """
    Extracts statement metadata (Bank Name, Client Name, BSB Number, Account Number)
    from PDF file or text content.
    """
    meta = {
        "Bank Name": "Unknown Bank",
        "Client Name": "N/A",
        "BSB Number": "N/A",
        "Account Number": "N/A"
    }

    full_text = pdf_text or ""
    if not full_text and pdf_path_or_bytes:
        try:
            import pdfplumber
            if isinstance(pdf_path_or_bytes, bytes):
                with pdfplumber.open(io.BytesIO(pdf_path_or_bytes)) as pdf:
                    if pdf.pages:
                        full_text = pdf.pages[0].extract_text() or ""
            elif isinstance(pdf_path_or_bytes, str) and os.path.exists(pdf_path_or_bytes):
                with pdfplumber.open(pdf_path_or_bytes) as pdf:
                    if pdf.pages:
                        full_text = pdf.pages[0].extract_text() or ""
        except Exception:
            pass

    if not full_text:
        return meta

    # 1. Bank Name detection
    if re.search(r"(?i)\b(Up\s*Bank|Up\s+is\s+a\s+brand)\b", full_text):
        meta["Bank Name"] = "Up Bank"
    elif re.search(r"(?i)\b(ANZ\s*Plus|ANZ\s*Everyday|Australia\s+and\s+New\s+Zealand\s+Banking)\b", full_text):
        meta["Bank Name"] = "ANZ Plus"
    elif re.search(r"(?i)\b(ANZ|Australia\s+and\s+New\s+Zealand)\b", full_text):
        meta["Bank Name"] = "ANZ Bank"
    elif re.search(r"(?i)\b(Commonwealth\s*Bank|CBA|CommBank)\b", full_text):
        meta["Bank Name"] = "Commonwealth Bank"
    elif re.search(r"(?i)\b(National\s+Australia\s+Bank|NAB)\b", full_text):
        meta["Bank Name"] = "NAB"
    elif re.search(r"(?i)\b(Westpac)\b", full_text):
        meta["Bank Name"] = "Westpac"
    elif re.search(r"(?i)\b(Macquarie)\b", full_text):
        meta["Bank Name"] = "Macquarie Bank"
    elif re.search(r"(?i)\b(Bendigo\s*Bank)\b", full_text):
        meta["Bank Name"] = "Bendigo Bank"

    # 2. BSB & Account Number detection
    hdr_bsb = re.search(r"(?i)Branch\s*Number\s*\(BSB\)\s*Account\s*Number.*?\n\s*(\d{3}\s*\d{3})\s+(\d[\d\s]{5,15}\d)", full_text, re.DOTALL)
    if hdr_bsb:
        digits = re.sub(r"\D", "", hdr_bsb.group(1))
        meta["BSB Number"] = f"{digits[:3]}-{digits[3:]}"
        meta["Account Number"] = " ".join(hdr_bsb.group(2).split())
    else:
        bsb_match = re.search(r"(?i)\b(?:BSB|Branch\s*(?:Number|No)?\.?)\s*[:\s]*(\d{3}[\s-]?\d{3})\b", full_text)
        if bsb_match:
            digits = re.sub(r"\D", "", bsb_match.group(1))
            meta["BSB Number"] = f"{digits[:3]}-{digits[3:]}"
        else:
            generic_bsb = re.search(r"\b(\d{3}-\d{3})\b", full_text)
            if generic_bsb:
                meta["BSB Number"] = generic_bsb.group(1)

    if meta["Account Number"] == "N/A":
        acc_match = re.search(r"(?i)\b(?:Account\s*(?:Number|No)?\.?|Acc\s*No\.?)\s*[:\s]*(\d[\d\s-]{5,14}\d)\b", full_text)
        if acc_match:
            raw_acc = acc_match.group(1).strip()
            meta["Account Number"] = " ".join(raw_acc.split())

    # 3. Client / Account Name detection
    name_match = re.search(r"(?i)\bAccount\s+Name\s*\n\s*([A-Z\s\n]{3,60})\n\s*(?:Transactions|Date|Statement|Opening|\n)", full_text)
    if name_match:
        raw_name = name_match.group(1)
        name_lines = [line.strip() for line in raw_name.splitlines() if line.strip()]
        meta["Client Name"] = " / ".join(name_lines)

    if meta["Client Name"] == "N/A":
        single_name = re.search(r"(?i)\bAccount\s+Name\s*[:\s]*([A-Za-z\s]{3,40})", full_text)
        if single_name:
            meta["Client Name"] = single_name.group(1).strip()
        else:
            addr_name_match = re.search(r"([A-Z][a-z]+\s+[A-Z][a-z]+)\s*\n.*(?:\d{1,4}\s+[A-Za-z\s]+(?:Rd|St|Ave|Dr|Way|Ct|Pl|Pde|VIC|NSW|QLD|WA|SA|TAS|ACT))", full_text)
            if addr_name_match:
                meta["Client Name"] = addr_name_match.group(1).strip()

    return meta


def extract_year_from_document(df: pd.DataFrame, file_name: Optional[str] = None) -> int:
    """
    Derives the statement document year from the file name or document header text.
    E.g., "April 2026(1).pdf" -> 2026, "1 July 2025 - 31 July 2025" -> 2025.
    """
    if file_name:
        fn_match = re.search(r"\b(20\d{2})\b", file_name)
        if fn_match:
            return int(fn_match.group(1))

    if df is not None and not df.empty:
        # Check column names and top 10 rows for 4-digit years
        text_samples = list(df.columns)
        for _, row in df.head(10).iterrows():
            text_samples.extend([str(v) for v in row if pd.notnull(v)])
        
        full_text = " ".join(text_samples)
        year_matches = re.findall(r"\b(20\d{2})\b", full_text)
        if year_matches:
            # Return the first encountered year (e.g. 2026 from "April 2026 Statement")
            return int(year_matches[0])

    return datetime.now().year


def clean_date_str(val: Any, default_year: Optional[int] = None) -> Optional[str]:
    """
    Standardizes date strings to YYYY-MM-DD.
    Supports DD/MM/YYYY, MM/DD/YYYY, YYYY-MM-DD, Month DD YYYY, 27th Apr, etc.
    """
    if pd.isna(val) or val is None:
        return None

    val_str = str(val).strip()
    if not val_str:
        return None

    # Clean multi-line or extra whitespace
    val_str = re.sub(r"\s+", " ", val_str)

    # Strip ordinal suffixes e.g., "27th Apr" -> "27 Apr", "22nd Apr" -> "22 Apr", "1st Jan" -> "1 Jan"
    val_str = re.sub(r"\b(\d{1,2})(st|nd|rd|th)\b", r"\1", val_str, flags=re.IGNORECASE)

    # Common date formats to attempt parsing
    date_formats = [
        "%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d",
        "%m/%d/%Y", "%m-%d-%Y", "%m.%d.%Y",
        "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y",
        "%d %b %Y", "%d-%b-%Y", "%d/%b/%Y",
        "%b %d, %Y", "%b %d %Y", "%d %B %Y",
        "%B %d, %Y", "%Y%m%d"
    ]

    for fmt in date_formats:
        try:
            dt = datetime.strptime(val_str, fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            pass

    curr_year = default_year or datetime.now().year

    # Short date formats without year (e.g. 31 Jul, Jul 31, 27 Apr, Apr 27)
    short_date_formats = [
        "%d %b", "%d-%b", "%d/%b",
        "%b %d", "%b-%d", "%b/%d",
        "%d %B", "%B %d"
    ]
    for fmt in short_date_formats:
        try:
            dt = datetime.strptime(val_str, fmt)
            return dt.replace(year=curr_year).strftime("%Y-%m-%d")
        except ValueError:
            pass

    # Try regex extractions for dates buried in text
    # e.g., "15 Jan 2024" or "2024-01-15"
    iso_match = re.search(r"\b(\d{4})[-/.](0?[1-9]|1[0-2])[-/.](0?[1-9]|[12]\d|3[01])\b", val_str)
    if iso_match:
        y, m, d = iso_match.groups()
        return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"

    dmy_match = re.search(r"\b(0?[1-9]|[12]\d|3[01])[-/.](0?[1-9]|1[0-2])[-/.](20\d{2}|\d{2})\b", val_str)
    if dmy_match:
        d, m, y = dmy_match.groups()
        if len(y) == 2:
            y = f"20{y}"
        return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"

    text_month_match = re.search(
        r"\b(0?[1-9]|[12]\d|3[01])\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(20\d{2})\b",
        val_str, re.IGNORECASE
    )
    if text_month_match:
        d, m_str, y = text_month_match.groups()
        for fmt in ["%d %b %Y", "%d %B %Y"]:
            try:
                dt = datetime.strptime(f"{d} {m_str} {y}", fmt)
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                pass

    short_text_month_match = re.search(
        r"\b(0?[1-9]|[12]\d|3[01])\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\b",
        val_str, re.IGNORECASE
    )
    if short_text_month_match:
        d, m_str = short_text_month_match.groups()
        for fmt in ["%d %b", "%d %B"]:
            try:
                dt = datetime.strptime(f"{d} {m_str}", fmt)
                return dt.replace(year=curr_year).strftime("%Y-%m-%d")
            except ValueError:
                pass

    return str(val)  # Return original if parsing fails


def auto_map_columns(columns: List[str]) -> Dict[str, Optional[str]]:
    """
    Intelligently maps raw extracted dataframe column names to standard headers.
    Returns dictionary mapping standard headers to detected column names.
    """
    mapping: Dict[str, Optional[str]] = {h: None for h in STANDARD_HEADERS}
    used_cols = set()

    # Match each standard header against columns
    for std_h, pattern in HEADER_PATTERNS.items():
        for col in columns:
            if col in used_cols:
                continue
            col_clean = str(col).strip()
            if re.search(pattern, col_clean):
                mapping[std_h] = col
                used_cols.add(col)
                break

    return mapping


def parse_card_layout_dataframe(clean_df: pd.DataFrame, default_year: Optional[int] = None) -> pd.DataFrame:
    """
    Parses modern card-style bank statements (e.g. Up Bank) where transactions
    are laid out with day headers, timestamps, and multi-line descriptions.
    """
    rows_data = []
    current_date = None

    for idx, row in clean_df.iterrows():
        row_str = " ".join([str(val) for val in row if pd.notnull(val)]).strip()
        if not row_str:
            continue

        # Ignore page summary rows & saver section headers
        if re.search(r"(?i)\b(Opening Balance|Closing Balance|Money In|Money Out|Base interest rate|Flow rate|Grow rate|Savers|5\.10% p\.a\.|1\.75% p\.a\.)\b", row_str):
            continue

        # 1. Check if row is a Date Banner (e.g., "Monday, 27th Apr" or "Thursday, 2nd Apr")
        date_banner_match = re.search(r"\b(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)?,?\s*(\d{1,2}(?:st|nd|rd|th)?\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*)\b", row_str, re.IGNORECASE)
        if date_banner_match:
            parsed_d = clean_date_str(date_banner_match.group(2), default_year=default_year)
            if parsed_d:
                current_date = parsed_d
            if not re.search(r"\$\d+\.\d{2}", row_str):
                continue

        # 2. Extract transaction fields from row cells
        money_matches = re.findall(r"([+-]?\$\d{1,3}(?:,\d{3})*\.\d{2})", row_str)
        if not money_matches:
            continue

        balance = None
        if len(money_matches) >= 2:
            balance = clean_currency_str(money_matches[-1])
            txn_amounts = money_matches[:-1]
        else:
            txn_amounts = money_matches

        debit = None
        credit = None
        amount = None

        for m in txn_amounts:
            clean_num = clean_currency_str(m)
            if m.startswith("+"):
                credit = abs(clean_num)
                amount = credit
            else:
                debit = abs(clean_num)
                amount = -debit

        desc = row_str
        for m in money_matches:
            desc = desc.replace(m, "")
        desc = re.sub(r"\b\d{1,2}:\d{2}\s*(?:am|pm)\b", "", desc, flags=re.IGNORECASE)
        if date_banner_match:
            desc = desc.replace(date_banner_match.group(0), "")

        # Deduplicate repeated adjacent words caused by multi-cell spans
        words = desc.split()
        dedup_words = []
        for w in words:
            if not dedup_words or w != dedup_words[-1]:
                dedup_words.append(w)
        desc = " ".join(dedup_words).strip()

        rows_data.append({
            "Date": current_date,
            "Description": desc,
            "Debit": debit,
            "Credit": credit,
            "Amount": amount,
            "Balance": balance
        })

    return pd.DataFrame(rows_data)


def normalize_statement_dataframe(
    df: pd.DataFrame,
    column_mapping: Optional[Dict[str, str]] = None,
    file_name: Optional[str] = None
) -> pd.DataFrame:
    """
    Normalizes raw extracted bank statement DataFrame into standardized format:
    Date | Description | Debit | Credit | Amount | Balance
    Clean dates, numbers, negative values.
    """
    if df.empty:
        return pd.DataFrame(columns=STANDARD_HEADERS)

    clean_df = df.copy()

    # Clean string representation of column names
    clean_df.columns = [str(c).strip() for c in clean_df.columns]

    # Derive document year from filename or document header text
    doc_year = extract_year_from_document(clean_df, file_name=file_name)

    # If column mapping is not provided, auto map
    if not column_mapping:
        mapped_dict = auto_map_columns(list(clean_df.columns))
    else:
        mapped_dict = column_mapping

    out_df = pd.DataFrame()

    # 1. Date
    date_col = mapped_dict.get("Date")
    if date_col and date_col in clean_df.columns:
        out_df["Date"] = clean_df[date_col].apply(lambda v: clean_date_str(v, default_year=doc_year))
    else:
        out_df["Date"] = None

    # 2. Description
    desc_col = mapped_dict.get("Description")
    if desc_col and desc_col in clean_df.columns:
        out_df["Description"] = clean_df[desc_col].astype(str).str.strip()
    else:
        # Fallback to any unmapped string column
        unmapped_str_cols = []
        for c in clean_df.columns:
            if c in mapped_dict.values():
                continue
            try:
                # Duplicate column names cause clean_df[c] to return a DataFrame
                # instead of a Series, which would crash on .dtype — guard against it
                col_series = clean_df[c]
                if isinstance(col_series, pd.DataFrame):
                    continue
                if col_series.dtype == "object":
                    unmapped_str_cols.append(c)
            except Exception:
                continue
        if unmapped_str_cols:
            out_df["Description"] = clean_df[unmapped_str_cols[0]].astype(str).str.strip()
        else:
            out_df["Description"] = ""

    # 3. Debit, Credit, Amount, Balance
    for num_header in ["Debit", "Credit", "Amount", "Balance"]:
        target_col = mapped_dict.get(num_header)
        if target_col and target_col in clean_df.columns:
            out_df[num_header] = clean_df[target_col].apply(clean_currency_str)
        else:
            out_df[num_header] = None

    # Synthesize Amount if Debit/Credit present but Amount missing
    if out_df["Amount"].isnull().all():
        def calc_amount(row):
            if pd.notnull(row["Credit"]) and row["Credit"] != 0:
                return abs(row["Credit"])
            elif pd.notnull(row["Debit"]) and row["Debit"] != 0:
                return -abs(row["Debit"])
            return None
        
        if not (out_df["Debit"].isnull().all() and out_df["Credit"].isnull().all()):
            out_df["Amount"] = out_df.apply(calc_amount, axis=1)

    # Reorder to standard headers plus any tax columns if present
    extra_cols = [c for c in clean_df.columns if c in ["ATO Tax Category", "Deductibility", "Tax Notes"]]
    for col in extra_cols:
        out_df[col] = clean_df[col]

    target_headers = [h for h in STANDARD_HEADERS]
    for col in ["ATO Tax Category", "Deductibility", "Tax Notes"]:
        if col in out_df.columns and col not in target_headers:
            target_headers.append(col)

    out_df = out_df.reindex(columns=target_headers)

    # Filter out rows that have no Date and no numeric values (likely table footer/header junk)
    valid_rows = out_df.apply(
        lambda r: pd.notnull(r["Date"]) or any(pd.notnull(r[c]) for c in ["Debit", "Credit", "Amount", "Balance"]),
        axis=1
    )
    out_df = out_df[valid_rows].reset_index(drop=True)

    # Fallback to card layout parser if standard mapping yielded zero valid dates or amounts
    if out_df.empty or out_df["Date"].isnull().all() or (out_df["Debit"].isnull().all() and out_df["Credit"].isnull().all() and out_df["Amount"].isnull().all()):
        card_df = parse_card_layout_dataframe(clean_df, default_year=doc_year)
        if not card_df.empty:
            out_df = card_df

    return out_df
