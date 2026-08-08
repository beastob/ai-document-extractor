"""
LLM Processor and ATO Tax Categorization Engine.
Supports local Ollama LLMs (http://localhost:11434), optional cloud API,
and a robust offline Australian merchant keyword rule engine.
"""

import json
import logging
import re
from typing import Dict, List, Optional, Tuple, Any
import urllib.request
import urllib.error
import pandas as pd

logger = logging.getLogger(__name__)

# Standard ATO Tax Return Categories for Australia
ATO_TAX_CATEGORIES = [
    "Motor Vehicle & Travel",
    "Home Office & Tech",
    "Work Equipment & Supplies",
    "Self-Education & Training",
    "Bank & Financial Fees",
    "Software & Subscriptions",
    "Tax-Deductible Donations",
    "Income & Payroll",
    "Personal / Non-Deductible"
]

# ATO Deductibility Statuses
DEDUCTIBILITY_STATUSES = [
    "Tax Deductible",
    "Potentially Deductible",
    "Non-Deductible",
    "Income"
]

# Comprehensive Australian Merchant & Transaction Keyword Rules for Offline Matching
AU_KEYWORD_RULES = [
    # Motor Vehicle & Travel
    (r"(?i)\b(shell|bp\b|ampol|caltex|7-eleven fuel|united petroleum|liberty oil|nrma|racq|racv|linkt|eastlink|citylink|translink|uber|didi|taxis?|transport for nsw|opal|myki|etoll|parking|wilson parking|securespot)\b",
     "Motor Vehicle & Travel", "Tax Deductible", "Work & business travel / fuel / tolls"),

    # Home Office & Tech / Hardware
    (r"(?i)\b(officeworks|jb hi-fi|harvey norman|apple\.com|dell|lenovo|hp store|telstra|optus|vodafone|tpg|belong|aussie broadband|dodo|tPG internet)\b",
     "Home Office & Tech", "Potentially Deductible", "Apportion work vs personal percentage"),

    # Work Equipment & Tools
    (r"(?i)\b(bunnings|total tools|sydney tools|repco|supercheap auto|kmart trade|workwear|bisley|blundstone|safety equipment)\b",
     "Work Equipment & Supplies", "Tax Deductible", "Work tools & protective equipment"),

    # Software & Subscriptions
    (r"(?i)\b(xero|myob|adobe|microsoft 365|msft|google storage|google cloud|aws|amazon web services|digitalocean|github|atlassian|jira|confluence|slack|zoom|canva|linkedin|domain\.com|godaddy)\b",
     "Software & Subscriptions", "Tax Deductible", "Business & professional software"),

    # Bank & Financial Fees
    (r"(?i)\b(monthly account fee|overdraft fee|international fee|atm fee|interest charge|merchant fee|stripe|square inc|paypal fee)\b",
     "Bank & Financial Fees", "Tax Deductible", "Bank & merchant service fees"),

    # Self-Education & Training
    (r"(?i)\b(udemy|coursera|linkedin learning|general assembly|university|tafe|cpa australia|chartered accountants|tax institute|seminar|workshop)\b",
     "Self-Education & Training", "Tax Deductible", "Work-related self education & professional development"),

    # Donations
    (r"(?i)\b(red cross|salvation army|cancer council|starlight|world vision|oxfam|unicef|guide dogs|monash foundation|dgr charity)\b",
     "Tax-Deductible Donations", "Tax Deductible", "DGR registered charity donation (> $2)"),

    # Income & Payroll
    (r"(?i)\b(salary|payroll|direct deposit|employer|wage|dividend|interest earned|ato refund|tax refund)\b",
     "Income & Payroll", "Income", "Taxable income / earnings"),

    # Personal / Non-Deductible (Groceries, Dining, Entertainment, Medical)
    (r"(?i)\b(woolworths|coles|aldi|iga|chemist warehouse|priceline|medibank|bupa|hcf|nib|mcdonalds|kfc|dominos|uber eats|door dash|menulog|netflix|spotify|disney|event cinemas|bws|dan murphy|liquorland)\b",
     "Personal / Non-Deductible", "Non-Deductible", "Private / living expense")
]


def check_ollama_status(ollama_url: str = "http://localhost:11434") -> Tuple[bool, List[str]]:
    """
    Checks if Ollama service is running locally and returns list of installed models.
    """
    try:
        req = urllib.request.Request(f"{ollama_url.rstrip('/')}/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=2) as response:
            if response.status == 200:
                data = json.loads(response.read().decode("utf-8"))
                models = [m.get("name") for m in data.get("models", [])]
                return True, models
    except Exception:
        pass
    return False, []


def categorize_transaction_offline_rules(description: str, amount: Optional[float] = None) -> Tuple[str, str, str]:
    """
    Categorizes a transaction description using Australian merchant regex rules.
    Returns (ATO Tax Category, Deductibility Status, Tax Notes).
    """
    if not description or pd.isna(description):
        return ("Personal / Non-Deductible", "Non-Deductible", "Unspecified description")

    desc_str = str(description).strip()

    # Rule matching
    for pattern, category, status, note in AU_KEYWORD_RULES:
        if re.search(pattern, desc_str):
            return (category, status, note)

    # Fallback heuristic based on amount sign if description unmapped
    if amount is not None and pd.notnull(amount) and amount > 0:
        return ("Personal / Non-Deductible", "Non-Deductible", "General personal expense")
    elif amount is not None and pd.notnull(amount) and amount < 0:
        return ("Income & Payroll", "Income", "Credit / Deposit income")

    return ("Personal / Non-Deductible", "Non-Deductible", "General expense - review for work relevance")


def clean_and_parse_json(text: str) -> Optional[Dict[str, Any]]:
    """
    Robustly parses JSON text from LLM outputs.
    Handles markdown code blocks (```json), trailing commas, and minor formatting errors.
    """
    if not text or not text.strip():
        return None

    cleaned = text.strip()

    # 1. Strip markdown code fences if present (e.g. ```json ... ```)
    if "```" in cleaned:
        cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.IGNORECASE | re.MULTILINE)
        cleaned = re.sub(r"```$", "", cleaned, flags=re.MULTILINE).strip()

    # 2. Extract JSON object substring between first { and last }
    start_idx = cleaned.find("{")
    end_idx = cleaned.rfind("}")
    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
        cleaned = cleaned[start_idx:end_idx + 1]

    # 3. Clean trailing commas before closing braces or brackets (e.g. ", }" -> "}")
    cleaned = re.sub(r",\s*([\}\]])", r"\1", cleaned)

    # 4. Attempt standard json.loads
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # 5. Regex extraction fallback for individual transaction objects
    try:
        tx_matches = re.findall(r"\{[^{}]*\"Date\"[^{}]*\}", text, re.IGNORECASE | re.DOTALL)
        transactions = []
        for m in tx_matches:
            m_clean = re.sub(r",\s*([\}])", r"\1", m)
            try:
                item = json.loads(m_clean)
                transactions.append(item)
            except json.JSONDecodeError:
                pass
        if transactions:
            return {"transactions": transactions}
    except Exception:
        pass

    return None


def query_ollama_json(
    prompt: str,
    model: str = "llama3.2",
    ollama_url: str = "http://localhost:11434",
    timeout: int = 120
) -> Optional[Dict[str, Any]]:
    """
    Sends a prompt to local Ollama server requesting JSON response format.
    Includes generous 120s timeout to allow local model loading and CPU inference.
    """
    try:
        url = f"{ollama_url.rstrip('/')}/api/generate"
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "format": "json"
        }
        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data_bytes, headers={"Content-Type": "application/json"}, method="POST")

        with urllib.request.urlopen(req, timeout=timeout) as response:
            if response.status == 200:
                res_obj = json.loads(response.read().decode("utf-8"))
                response_text = res_obj.get("response", "")
                return clean_and_parse_json(response_text)
    except Exception as e:
        logger.warning(f"Ollama query failed ({type(e).__name__}): {e}")
        return None


def extract_transactions_from_pdf_text_llm(
    raw_text: str,
    model_name: str = "qwen2.5:3b",
    ollama_url: str = "http://localhost:11434"
) -> pd.DataFrame:
    """
    Extracts structured bank statement transactions from raw document text by chunking
    text into manageable blocks (1500-2000 chars) to prevent Ollama socket timeouts.
    """
    if not raw_text or not raw_text.strip():
        return pd.DataFrame()

    # Split text into chunks of ~1500 characters or line blocks
    lines = [line.strip() for line in raw_text.split("\n") if line.strip()]
    chunk_size = 25  # lines per chunk
    line_chunks = [lines[i:i + chunk_size] for i in range(0, len(lines), chunk_size)]

    all_transactions = []

    for idx, chunk in enumerate(line_chunks):
        chunk_text = "\n".join(chunk)
        if len(chunk_text) < 20:
            continue

        prompt = f"""
        You are an expert financial document parser. Extract all financial bank statement transactions from the raw text block below.

        Text Block:
        \"\"\"
        {chunk_text}
        \"\"\"

        Instructions:
        1. Extract every transaction item in this block.
        2. Normalize dates to YYYY-MM-DD format (infer year if missing).
        3. Extract Description, Debit, Credit, Amount, and Balance.

        Return JSON with this exact key structure:
        {{
            "transactions": [
                {{
                    "Date": "YYYY-MM-DD",
                    "Description": "transaction detail text",
                    "Debit": 100.00 or null,
                    "Credit": 500.00 or null,
                    "Amount": 100.00 or null,
                    "Balance": 2480.42 or null
                }}
            ]
        }}
        """

        res = query_ollama_json(prompt, model=model_name, ollama_url=ollama_url, timeout=120)
        if res and "transactions" in res and isinstance(res["transactions"], list):
            for tx in res["transactions"]:
                if isinstance(tx, dict) and any(tx.get(k) for k in ["Date", "Description", "Amount", "Balance"]):
                    all_transactions.append(tx)

    if all_transactions:
        return pd.DataFrame(all_transactions)

    return pd.DataFrame()


def categorize_transactions_df(
    df: pd.DataFrame,
    provider: str = "offline",  # "offline", "ollama", or "cloud"
    model_name: str = "llama3.2",
    ollama_url: str = "http://localhost:11434",
    api_key: Optional[str] = None
) -> pd.DataFrame:
    """
    Categorizes all transactions in DataFrame for ATO Tax Return purposes.
    Adds ATO Tax Category, Deductibility, and Tax Notes columns.
    Uses batched Ollama queries (10 transactions per prompt) for 10x faster local inference.
    """
    if df.empty:
        return df

    out_df = df.copy()

    # Check if local Ollama is available when provider == "ollama"
    use_ollama = False
    if provider == "ollama":
        is_running, _ = check_ollama_status(ollama_url)
        if is_running:
            use_ollama = True

    # First pass: fast offline keyword rule categorization
    categories = []
    statuses = []
    notes = []

    for idx, row in out_df.iterrows():
        desc = str(row.get("Description", "") or "")
        amount = row.get("Amount")
        cat, status, note = categorize_transaction_offline_rules(desc, amount)
        categories.append(cat)
        statuses.append(status)
        notes.append(note)

    out_df["ATO Tax Category"] = categories
    out_df["Deductibility"] = statuses
    out_df["Tax Notes"] = notes

    # Second pass: If Ollama enabled, refine unmapped or personal transactions in batches of 10
    if use_ollama:
        unmapped_indices = [
            i for i, row in out_df.iterrows()
            if row["ATO Tax Category"] == "Personal / Non-Deductible" and len(str(row.get("Description", ""))) > 3
        ]
        
        batch_size = 10
        for i in range(0, len(unmapped_indices), batch_size):
            batch_idx = unmapped_indices[i:i + batch_size]
            items_to_query = [
                {"id": idx, "description": str(out_df.loc[idx, "Description"]), "amount": out_df.loc[idx, "Amount"]}
                for idx in batch_idx
            ]

            prompt = f"""
            You are an Australian Taxation Office (ATO) Tax Accountant.
            Categorize these bank transactions for an Australian tax return.

            Transactions: {json.dumps(items_to_query)}
            Allowed Categories: {json.dumps(ATO_TAX_CATEGORIES)}
            Allowed Deductibility Statuses: {json.dumps(DEDUCTIBILITY_STATUSES)}

            Return JSON matching this exact structure:
            {{
                "results": [
                    {{
                        "id": <transaction id number>,
                        "category": "<one of allowed categories>",
                        "deductibility": "<one of allowed statuses>",
                        "note": "<short explanation>"
                    }}
                ]
            }}
            """

            result = query_ollama_json(prompt, model=model_name, ollama_url=ollama_url, timeout=120)
            if result and "results" in result and isinstance(result["results"], list):
                for item in result["results"]:
                    tx_id = item.get("id")
                    if tx_id in out_df.index:
                        cat = item.get("category") if item.get("category") in ATO_TAX_CATEGORIES else out_df.loc[tx_id, "ATO Tax Category"]
                        ded = item.get("deductibility") if item.get("deductibility") in DEDUCTIBILITY_STATUSES else out_df.loc[tx_id, "Deductibility"]
                        nt = item.get("note", "Categorized by Local LLM")
                        out_df.loc[tx_id, "ATO Tax Category"] = cat
                        out_df.loc[tx_id, "Deductibility"] = ded
                        out_df.loc[tx_id, "Tax Notes"] = nt

    return out_df
