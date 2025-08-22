import streamlit as st
import pandas as pd
import asyncio
from io import StringIO, BytesIO # Import BytesIO for Excel export
import sys
from pathlib import Path
import traceback

# Adjust the path to import from the core directory
sys.path.append(str(Path(__file__).resolve().parents[1]))

from core.verifier import process_bulk_async, verify_email_async
from core.models import VerificationResult

st.set_page_config(layout="wide")

st.title("Email Verifier Panel")

# --- Robust helper function to run async code in Streamlit ---
def run_async(async_func):
    """
    Runs an async function in a way that's compatible with Streamlit's
    event loop management.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    if loop.is_closed():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    return loop.run_until_complete(async_func)

# --- UI Tabs ---
tab1, tab2 = st.tabs(["Single Verification", "Bulk Verification"])

# --- Single Verification Tab ---
with tab1:
    st.header("Verify a Single Email Address")
    
    with st.form(key="single_email_form"):
        email_input = st.text_input(label="Enter email address to verify")
        submit_button = st.form_submit_button(label="Verify Email")

    if submit_button and email_input:
        with st.spinner("Verifying..."):
            semaphore = asyncio.Semaphore(1)
            
            # DEBUG PRINT FOR SINGLE EMAIL
            print(f"DEBUG (Single): Email passed to verify_email_async: '{email_input}'")
            
            result = run_async(verify_email_async(email_input, semaphore))
            
            if result.is_valid:
                st.success(f"**Email:** {result.email} is **VALID**")
            else:
                st.error(f"**Email:** {result.email} is **INVALID**")
            
            st.write(f"**Reason:** {result.reason}")
            st.json(result.details)

# --- Bulk Verification Tab ---
with tab2:
    st.header("Verify a List of Emails from a File")
    
    uploaded_file = st.file_uploader(
        "Upload a .txt or .csv file with one email per line.",
        type=["txt", "csv"]
    )

    if uploaded_file is not None:
        stringio = StringIO(uploaded_file.getvalue().decode("utf-8"))
        
        try:
            df_uploaded = pd.read_csv(stringio) # Renamed to df_uploaded to avoid confusion
            
            if 'emails' not in df_uploaded.columns and 'email' not in df_uploaded.columns:
                st.error("Error: CSV file must contain a column named 'emails' or 'email'.")
                emails_to_verify = []
            else:
                # Prioritize 'emails' then 'email' column, or pick the first column if neither
                if 'emails' in df_uploaded.columns:
                    email_column_name = 'emails'
                elif 'email' in df_uploaded.columns:
                    email_column_name = 'email'
                else: # Fallback to first column if neither specific name is found
                    email_column_name = df_uploaded.columns[0]
                    st.warning(f"No 'emails' or 'email' column found. Using the first column: '{email_column_name}'")


                raw_emails_from_csv = df_uploaded[email_column_name].astype(str).tolist()
                
                emails_to_verify = []
                for email_val in raw_emails_from_csv:
                    cleaned_email = email_val.strip()
                    # Filter out the header if it was read as a value (based on found column name)
                    if cleaned_email.lower() == email_column_name.lower() or not cleaned_email:
                        continue
                    emails_to_verify.append(cleaned_email)

        except pd.errors.EmptyDataError:
            st.error("The uploaded CSV file is empty.")
            emails_to_verify = []
        except Exception as e:
            st.error(f"An error occurred while reading the CSV: {e}")
            emails_to_verify = []
        
        st.write(f"Found {len(emails_to_verify)} emails to verify.")

        if st.button("Start Bulk Verification"):
            with st.spinner(f"Verifying {len(emails_to_verify)} emails... This may take a while."):
                
                # DEBUG PRINTS FOR BULK EMAILS
                print("\nDEBUG (Bulk): Emails passed to process_bulk_async:")
                for i, email in enumerate(emails_to_verify):
                    print(f"  [{i}]: '{email}'")
                print("--- End Bulk Debug ---")

                results_raw = run_async(process_bulk_async(emails_to_verify))
                
                # --- Prepare DataFrame for display and Excel export ---
                results_data = []
                for r in results_raw:
                    # Extract details for the DataFrame
                    format_check_status = r['details'].get('format_check', 'N/A')
                    disposable_check_status = r['details'].get('disposable_check', 'N/A')
                    mx_check_status = r['details'].get('mx_check', 'N/A')
                    domain_age_info = r['details'].get('domain_age_check', 'N/A')
                    smtp_check_info = r['details'].get('smtp_check', 'N/A')

                    # --- Apply the custom 'Valid' logic for displayed 'Overall Status' ---
                    is_valid_for_display = False
                    if mx_check_status == 'Passed':
                        is_valid_for_display = True
                    elif isinstance(smtp_check_info, str) and 'passed' in smtp_check_info.lower():
                        is_valid_for_display = True
                    # If neither MX nor SMTP passed, it remains False (Invalid)

                    results_data.append({
                        'Email': r['email'],
                        'Overall Status': 'VALID' if is_valid_for_display else 'INVALID',
                        'Reason': r['reason'], 
                        'Format Check': format_check_status,
                        'Disposable Check': disposable_check_status,
                        'MX Check': mx_check_status,
                        'Domain Age Info': domain_age_info,
                        'SMTP Check Info': smtp_check_info
                    })
                
                df_results = pd.DataFrame(results_data)
                st.session_state['bulk_results'] = df_results

    if 'bulk_results' in st.session_state:
        st.subheader("Verification Results")
        df_results = st.session_state['bulk_results']

        def style_status(val):
            color = 'green' if val == 'VALID' else 'red'
            return f'color: {color}; font-weight: bold;'

        st.dataframe(
            df_results.style.applymap(style_status, subset=['Overall Status']),
            use_container_width=True
        )

        # --- Download All Results as CSV (Existing) ---
        csv_all = df_results.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="Download All Results as CSV",
            data=csv_all,
            file_name="email_verification_results.csv",
            mime="text/csv",
        )

        # --- NEW: Download Results as Excel with Categories ---
        st.subheader("Download Categorized Results (Excel)")
        if st.button("Generate & Download Excel"):
            # Create a BytesIO buffer to store the Excel file in memory
            excel_buffer = BytesIO()

            with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                # Define Valid and Invalid based on MX Check and SMTP Check
                # Prioritize 'MX Check' for categorization
                df_valid = df_results[
                    (df_results['MX Check'] == 'Passed') &
                    (df_results['Overall Status'] == 'VALID') # Ensure overall is also valid
                ].copy() # Use .copy() to avoid SettingWithCopyWarning

                df_invalid = df_results[
                    (df_results['MX Check'] != 'Passed') |
                    (df_results['Overall Status'] == 'INVALID') # Capture all invalid cases
                ].copy()

                # Optional: Refine "Invalid" further based on SMTP status if desired
                # For example, if MX is passed but SMTP failed.
                df_invalid_mx_fail = df_results[df_results['MX Check'] != 'Passed'].copy()
                df_invalid_smtp_fail = df_results[
                    (df_results['MX Check'] == 'Passed') & 
                    (df_results['SMTP Check Info'].str.contains('failed', case=False, na=False))
                ].copy()

                # Write DataFrames to different sheets
                # Sheet 1: All Valid (based on MX + Overall)
                df_valid.to_excel(writer, sheet_name='Valid Emails', index=False)
                
                # Sheet 2: All Invalid (catch-all)
                df_invalid.to_excel(writer, sheet_name='Invalid Emails (All Reasons)', index=False)
                
                # Optional additional sheets for specific invalid reasons:
                if not df_invalid_mx_fail.empty:
                    df_invalid_mx_fail.to_excel(writer, sheet_name='Invalid - MX Failed', index=False)
                if not df_invalid_smtp_fail.empty:
                     df_invalid_smtp_fail.to_excel(writer, sheet_name='Invalid - SMTP Failed', index=False)


            # Get the value from the buffer
            excel_data = excel_buffer.getvalue()

            st.download_button(
                label="Download Categorized Excel",
                data=excel_data,
                file_name="categorized_email_results.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )