"""
Bank Statement PDF Table Extractor, LLM Reshaper & ATO Tax Converter
100% Offline Local Streamlit Application
"""

import io
import warnings
import pandas as pd
import streamlit as st

# Suppress PyTorch and Streamlit UserWarnings
warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=FutureWarning)

from src.extractor import extract_bank_statement_tables
from src.parser import (
    auto_map_columns,
    normalize_statement_dataframe,
    STANDARD_HEADERS,
    clean_currency_str,
    clean_date_str,
    extract_statement_metadata
)
from src.llm_processor import (
    check_ollama_status,
    categorize_transactions_df,
    ATO_TAX_CATEGORIES,
    DEDUCTIBILITY_STATUSES
)
from src.excel_exporter import (
    dataframe_to_excel_bytes,
    export_multi_sheet_workbook,
    export_statements_zip
)

# Page layout & styling
st.set_page_config(
    page_title="Bank Statement PDF Extractor & ATO Tax Categorizer",
    page_icon="🇦🇺",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS styling
st.markdown("""
<style>
    .main-header {
        font-size: 2.2rem;
        font-weight: 700;
        color: #1E3A8A;
        margin-bottom: 0.2rem;
    }
    .sub-header {
        font-size: 1.05rem;
        color: #4B5563;
        margin-bottom: 1.5rem;
    }
    .badge-status {
        background-color: #D1FAE5;
        color: #065F46;
        padding: 4px 10px;
        border-radius: 6px;
        font-weight: 600;
        font-size: 0.85rem;
    }
</style>
""", unsafe_allow_html=True)


def main():
    st.markdown('<div class="main-header">🇦🇺 Bank Statement PDF Extractor & ATO Tax Categorizer</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="sub-header">Extract tables, standardize fields, and auto-label transactions for Australian ATO Tax Returns. 100% local & private.</div>',
        unsafe_allow_html=True
    )

    # Sidebar settings
    st.sidebar.header("⚙️ Configuration")

    # 1. Extraction Strategy
    st.sidebar.subheader("1. Extraction Engine Strategy")
    engine_choice = st.sidebar.radio(
        "PDF Engine Strategy:",
        options=["docling", "pdfplumber", "llm"],
        index=0,
        format_func=lambda x: {
            "docling": "🔍 IBM Docling (Recommended — Scanned & Complex PDFs)",
            "llm": "🤖 LLM Direct AI Extraction (Ollama / Local LLM)",
            "pdfplumber": "📄 pdfplumber (Fast Digital Vector PDFs)",
        }[x],
        help="IBM Docling is recommended for most bank statement PDFs. LLM Direct mode feeds raw text to a local Ollama model."
    )

    st.sidebar.markdown("---")
    
    # 2. LLM & ATO Tax Categorization Settings
    st.sidebar.subheader("2. ATO Tax Categorization Engine")
    tax_provider = st.sidebar.selectbox(
        "Categorization Engine:",
        options=["offline", "ollama"],
        format_func=lambda x: {
            "offline": "⚡ Offline Rule Engine (AU Merchant Dictionary)",
            "ollama": "🤖 Local Ollama LLM (http://localhost:11434)"
        }[x],
        help="Choose between lightning fast offline merchant matching or local Ollama LLM."
    )

    ollama_model = "llama3.2"
    if tax_provider == "ollama":
        ollama_running, available_models = check_ollama_status()
        if ollama_running:
            st.sidebar.success("🟢 Ollama Connected Locally")
            if available_models:
                ollama_model = st.sidebar.selectbox("Ollama Model:", options=available_models)
            else:
                ollama_model = st.sidebar.text_input("Ollama Model Name:", value="llama3.2")
        else:
            st.sidebar.warning("🔴 Ollama server not detected at http://localhost:11434. Will use Offline AU Rules.")

    st.sidebar.markdown("---")
    st.sidebar.info("🔒 **100% Local & Private**\nAll document processing runs on your local machine. Zero internet calls required.")

    # Main content - File Uploader
    uploaded_files = st.file_uploader(
        "Upload one or more Bank Statement PDFs:",
        type=["pdf"],
        accept_multiple_files=True,
        help="Select digital or scanned bank statement PDF files."
    )

    if not uploaded_files:
        st.info("👆 Upload bank statement PDF files above to begin table extraction.")
        return

    if "extracted_data" not in st.session_state or st.session_state.get("last_uploaded_names") != [f.name for f in uploaded_files]:
        st.session_state["extracted_data"] = {}
        st.session_state["last_uploaded_names"] = [f.name for f in uploaded_files]

    # Process files
    if st.button("🚀 Extract & Normalize Tables", type="primary"):
        with st.spinner("Processing PDF statements locally..."):
            extracted_results = {}
            for pdf_file in uploaded_files:
                file_bytes = pdf_file.read()
                pdf_file.seek(0)
                try:
                    dfs, engine_used = extract_bank_statement_tables(
                        pdf_path_or_bytes=file_bytes,
                        file_name=pdf_file.name,
                        engine=engine_choice,
                        model_name=ollama_model
                    )

                    # Invalidate stale editor session state cache if present
                    if f"editor_{pdf_file.name}" in st.session_state:
                        del st.session_state[f"editor_{pdf_file.name}"]

                    if dfs:
                        norm_sub_dfs = [normalize_statement_dataframe(df, file_name=pdf_file.name) for df in dfs]
                        norm_sub_dfs = [df for df in norm_sub_dfs if not df.empty]

                        if norm_sub_dfs:
                            norm_df = pd.concat(norm_sub_dfs, ignore_index=True)
                            raw_combined = pd.concat(dfs, ignore_index=True)

                            # Auto run ATO categorization
                            categorized_df = categorize_transactions_df(
                                norm_df,
                                provider=tax_provider,
                                model_name=ollama_model
                            )

                            meta = extract_statement_metadata(pdf_path_or_bytes=file_bytes)

                            extracted_results[pdf_file.name] = {
                                "raw_df": raw_combined,
                                "engine_used": engine_used,
                                "normalized_df": categorized_df,
                                "metadata": meta
                            }
                    else:
                        st.warning(f"No tables detected in {pdf_file.name}.")
                except Exception as e:
                    st.error(f"Error processing {pdf_file.name}: {e}")

            st.session_state["extracted_data"] = extracted_results

    results = st.session_state.get("extracted_data", {})
    if not results:
        return

    # Build processed_statements and metadata dicts from latest session state
    processed_statements = {}
    metadata_dict = {}
    for file_name, result in results.items():
        df = result.get("edited_df", result["normalized_df"])
        processed_statements[file_name] = df
        metadata_dict[file_name] = result.get("metadata", {})

    st.markdown("---")

    # Batch export options (placed above Extracted Statements section)
    if len(processed_statements) > 1:
        st.header("📦 Batch Export Options")
        b_col1, b_col2, b_col3 = st.columns(3)

        with b_col1:
            zip_bytes = export_statements_zip(processed_statements, metadata_dict=metadata_dict)
            st.download_button(
                label="🗂️ Download All as ZIP Archive (.zip)",
                data=zip_bytes,
                file_name="bank_statements_ato_tax.zip",
                mime="application/zip",
                width="stretch"
            )

        with b_col2:
            multi_sheet_bytes = export_multi_sheet_workbook(processed_statements, metadata_dict=metadata_dict)
            st.download_button(
                label="📊 Download Multi-Sheet Workbook (.xlsx)",
                data=multi_sheet_bytes,
                file_name="combined_bank_statements_ato_tax.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                width="stretch"
            )

        with b_col3:
            merged_list = []
            for fname, df_item in processed_statements.items():
                df_copy = df_item.copy()
                df_copy.insert(0, "Source_File", fname)
                merged_list.append(df_copy)
            master_df = pd.concat(merged_list, ignore_index=True)
            master_excel_bytes = dataframe_to_excel_bytes(master_df, sheet_name="Master Transactions")

            st.download_button(
                label="📑 Download Merged Master Tax Sheet (.xlsx)",
                data=master_excel_bytes,
                file_name="master_merged_ato_tax_transactions.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                width="stretch"
            )

        st.markdown("---")

    # Extracted Statements & ATO Tax Categorization section with tabs
    st.header("📋 Extracted Statements & ATO Tax Categorization")

    tabs = st.tabs([f"📑 {file_name}" for file_name in results.keys()])

    for tab, (file_name, result) in zip(tabs, results.items()):
        with tab:
            meta = result.get("metadata", {})

            # Display Statement Metadata Metrics
            st.markdown("#### 🏦 Statement Account Summary")
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Bank Name", meta.get("Bank Name", "Unknown Bank"))
            m2.metric("Client Name", meta.get("Client Name", "N/A"))
            m3.metric("BSB Number", meta.get("BSB Number", "N/A"))
            m4.metric("Account Number", meta.get("Account Number", "N/A"))

            st.caption(f"Extraction Engine: **{result['engine_used']}**")
            raw_df = result["raw_df"]
            current_df = result["normalized_df"]

            # Option to re-run categorization
            if st.button(f"🏷️ Re-Categorize for ATO Tax ({file_name})", key=f"re_cat_{file_name}"):
                current_df = categorize_transactions_df(current_df, provider=tax_provider, model_name=ollama_model)
                st.session_state["extracted_data"][file_name]["normalized_df"] = current_df
                if f"editor_{file_name}" in st.session_state:
                    del st.session_state[f"editor_{file_name}"]
                if "edited_df" in st.session_state["extracted_data"][file_name]:
                    del st.session_state["extracted_data"][file_name]["edited_df"]
                st.success("Re-categorization complete!")

            st.subheader("Interactive Statement & Tax Editor")
            st.caption("Directly edit transaction details, adjust ATO Tax Categories, or update deductibility statuses below.")

            edited_df = st.data_editor(
                current_df,
                num_rows="dynamic",
                width="stretch",
                key=f"editor_{file_name}",
                column_config={
                    "Date": st.column_config.TextColumn("Date (YYYY-MM-DD)"),
                    "Description": st.column_config.TextColumn("Description"),
                    "Debit": st.column_config.NumberColumn("Debit ($)", format="$%.2f"),
                    "Credit": st.column_config.NumberColumn("Credit ($)", format="$%.2f"),
                    "Amount": st.column_config.NumberColumn("Amount ($)", format="$%.2f"),
                    "Balance": st.column_config.NumberColumn("Balance ($)", format="$%.2f"),
                    "ATO Tax Category": st.column_config.SelectboxColumn(
                        "ATO Tax Category",
                        options=ATO_TAX_CATEGORIES,
                        required=True
                    ),
                    "Deductibility": st.column_config.SelectboxColumn(
                        "Deductibility Status",
                        options=DEDUCTIBILITY_STATUSES,
                        required=True
                    ),
                    "Tax Notes": st.column_config.TextColumn("Tax Notes"),
                }
            )

            # Keep track of latest edited df in session state for batch export
            st.session_state["extracted_data"][file_name]["edited_df"] = edited_df

            # Single Excel download
            single_excel_bytes = dataframe_to_excel_bytes(edited_df, sheet_name="Statement", metadata=meta)
            st.download_button(
                label=f"💾 Download {file_name.rsplit('.', 1)[0]}_ATO_Tax.xlsx",
                data=single_excel_bytes,
                file_name=f"{file_name.rsplit('.', 1)[0]}_ATO_Tax.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key=f"dl_single_{file_name}"
            )


if __name__ == "__main__":
    main()
