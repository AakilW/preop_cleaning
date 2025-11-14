import streamlit as st
import pandas as pd
import re
from io import BytesIO

st.set_page_config(page_title="Tebra Encounter Report Cleaner", layout="wide")
st.title("Tebra Encounter Report Cleaner")

file = st.file_uploader("Upload exported Tebra report", type=["xlsx", "xls", "csv"])

if file:
    ext = file.name.split('.')[-1].lower()
    
    # --- Read Excel/CSV robustly
    if ext in ["xlsx", "xls"]:
        engine = "openpyxl" if ext == "xlsx" else "xlrd"
        df = pd.read_excel(file, header=None, engine=engine)
    else:
        df = pd.read_csv(file, header=None)
    
    # --- Clean all text
    df = df.fillna("").astype(str).apply(lambda x: x.str.strip())
    
    # --- Detect status rows
    status_pattern = r"(?i)\b(Draft|Approved|Review|WorkInProgress)\b"
    current_status = None
    cleaned = []

    for i, row in df.iterrows():
        first = row[0].strip()
        if re.match(status_pattern, first):
            current_status = first
            continue
        if not current_status or all(v == "" for v in row):
            continue

        # --- Encounter ID strictly from column B
        id_candidate = row[1].strip()
        encounter_id = id_candidate if id_candidate.isdigit() and len(id_candidate) > 2 else ""

        # --- Other fields
        provider_match = next((v for v in row if re.search(r",\s*(PA|MD|NP|DO)$", v)), "")
        svc_date_match = next((v for v in row if re.match(r"\d{4}-\d{2}-\d{2}", v)), "")
        diag_codes = [v for v in row if re.fullmatch(r"[A-Z]\d{2}\.?[A-Z0-9]*", v)]
        charge_match = next((v.replace(",", "") for v in row if re.match(r"^\d{1,6}\.\d{2}$", v.replace(",", ""))), "")

        diag1 = diag_codes[0] if len(diag_codes) > 0 else ""
        diag2 = diag_codes[1] if len(diag_codes) > 1 else ""

        cleaned.append([
            current_status, encounter_id, provider_match,
            svc_date_match, diag1, diag2, charge_match
        ])

    # --- Create DataFrame
    df_out = pd.DataFrame(cleaned, columns=[
        "Status", "Encounter ID", "Rendering Provider",
        "Svc Date", "Diag 1", "Diag 2", "Charges"
    ])

    # --- Forward-fill Encounter ID and Provider before filtering
    df_out[["Encounter ID", "Rendering Provider"]] = df_out[["Encounter ID", "Rendering Provider"]].replace("", pd.NA).ffill()

    # --- Convert Charges and Svc Date
    df_out["Charges"] = pd.to_numeric(df_out["Charges"], errors="coerce").fillna(0)
    df_out["Svc Date"] = pd.to_datetime(df_out["Svc Date"], errors="coerce")

    # --- Filter rows without Svc Date
    df_out = df_out[df_out["Svc Date"].notna()]

    # --- Tabs for Streamlit
    tabs = st.tabs(["Structured Encounter Data", "Monthly Summary"])

    # --- Tab 1: Cleaned Encounter Data
    with tabs[0]:
        st.subheader("Structured Encounter Data (Cleaned)")
        st.dataframe(df_out.head(50))

        output = BytesIO()
        df_out.to_excel(output, index=False)
        st.download_button(
            "📥 Download Cleaned Data",
            data=output.getvalue(),
            file_name="Tebra_Cleaned_Encounters.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    # --- Tab 2: Monthly Summary
    with tabs[1]:
        st.subheader("Monthly Claims Summary (by Encounter ID)")

        # Extract month
        df_out["Month"] = df_out["Svc Date"].dt.to_period("M")
        df_out["Month_str"] = df_out["Month"].astype(str)

        # Sum charges per Encounter ID per month
        agg_df = df_out.groupby(["Month_str", "Encounter ID"]).agg(
            Total_Charge=("Charges", "sum")
        ).reset_index()

        # Summary counts
        summary = agg_df.groupby("Month_str").agg(
            Total_Claims=("Encounter ID", "count"),
            Claims_GT_800=("Total_Charge", lambda x: (x > 800).sum()),
            Claims_LE_800=("Total_Charge", lambda x: (x <= 800).sum())
        ).reset_index()

        st.dataframe(summary)

        # Visualization
        st.bar_chart(summary.set_index("Month_str")[["Total_Claims", "Claims_GT_800", "Claims_LE_800"]])
