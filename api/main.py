# api/main.py

import asyncio
from fastapi import FastAPI, HTTPException, UploadFile, File, Response # Import Response for direct file downloads
from fastapi.responses import StreamingResponse # Import StreamingResponse
from io import StringIO, BytesIO # Import BytesIO for Excel creation
import pandas as pd
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[1]))

from core.verifier import verify_email_async, process_bulk_async
from core.models import VerificationResult, SingleEmailRequest, BulkEmailRequest
from core import config
import traceback # For detailed error logging

app = FastAPI(
    title="Email Verifier API",
    description="An API to verify single or bulk email addresses.",
    version="1.0.0"
)

# --- Helper function to generate Excel (can be moved to a separate utils.py if preferred) ---
def generate_excel_report(df_results: pd.DataFrame) -> BytesIO:
    excel_buffer = BytesIO()
    with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
        # Define Valid emails:
        # If MX Check is 'Passed'
        # OR if SMTP Check Info contains 'passed' (case-insensitive)
        
        # Ensure 'SMTP Check Info' column exists and handle potential NaN/None
        smtp_check_conditions = (df_results['SMTP Check Info'].fillna('').str.contains('passed', case=False, na=False))

        df_valid = df_results[
            (df_results['MX Check'] == 'Passed') | # MX check passes
            (smtp_check_conditions)                # OR SMTP check passes
        ].copy()

        # All other emails are considered Invalid
        df_invalid = df_results[
            ~((df_results['MX Check'] == 'Passed') | # NOT (MX check passes
              (smtp_check_conditions))               # OR SMTP check passes)
        ].copy()

        # Write DataFrames to two sheets
        df_valid.to_excel(writer, sheet_name='Valid Emails', index=False)
        df_invalid.to_excel(writer, sheet_name='Invalid Emails', index=False)
        
    excel_buffer.seek(0) # Rewind the buffer to the beginning
    return excel_buffer

# --- API Endpoints ---

@app.post("/verify-single", response_model=VerificationResult, tags=["Verification"])
async def verify_single(request: SingleEmailRequest):
    """
    Verifies a single email address.
    """
    semaphore = asyncio.Semaphore(1)
    try:
        result = await verify_email_async(request.email, semaphore)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# --- Modified /verify-bulk to return Excel ---
@app.post("/verify-bulk/excel", tags=["Verification"]) # New endpoint for Excel output
async def verify_bulk_excel(request: BulkEmailRequest):
    """
    Verifies a list of email addresses concurrently and returns results as an Excel file.
    """
    if not request.emails:
        raise HTTPException(status_code=400, detail="Email list cannot be empty.")
    
    try:
        results_list_of_pydantic_models = await process_bulk_async(request.emails)
        
        # Convert Pydantic models to dicts for DataFrame, if process_bulk_async doesn't do it
        results_data = [r.model_dump() for r in results_list_of_pydantic_models] 
        
        # Prepare DataFrame with detailed columns
        df_results = pd.DataFrame(results_data)
        
        # Ensure details are expanded if needed for the excel generation logic
        # This part depends on how process_bulk_async returns data.
        # If 'details' is a nested dict, you might need to flatten it.
        # Assuming process_bulk_async returns flattened dictionaries like in Streamlit UI:
        # Example for flattening if 'details' column is present:
        # if 'details' in df_results.columns:
        #     df_details_normalized = pd.json_normalize(df_results['details'])
        #     df_results = pd.concat([df_results.drop(columns=['details']), df_details_normalized], axis=1)

        # For the Excel report, let's ensure we have the necessary columns by explicitly preparing the df
        processed_for_excel = []
        for r_dict in results_data:
            processed_for_excel.append({
                'Email': r_dict.get('email', 'N/A'),
                'Overall Status': 'VALID' if r_dict.get('is_valid') else 'INVALID',
                'Reason': r_dict.get('reason', 'N/A'),
                'Format Check': r_dict.get('details', {}).get('format_check', 'N/A'),
                'Disposable Check': r_dict.get('details', {}).get('disposable_check', 'N/A'),
                'MX Check': r_dict.get('details', {}).get('mx_check', 'N/A'),
                'Domain Age Info': r_dict.get('details', {}).get('domain_age_check', 'N/A'),
                'SMTP Check Info': r_dict.get('details', {}).get('smtp_check', 'N/A')
            })
        df_final_for_excel = pd.DataFrame(processed_for_excel) 

        excel_buffer = generate_excel_report(df_final_for_excel)

        return StreamingResponse(
            excel_buffer,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=bulk_email_results.xlsx"}
        )
    except Exception as e:
        print(f"ERROR in /verify-bulk/excel endpoint: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to process bulk emails for Excel: {str(e)}")


# --- Modified /verify-csv to return Excel ---
@app.post("/verify-csv/excel", tags=["Verification"]) # New endpoint for Excel output  
async def verify_from_csv_upload_excel(file: UploadFile = File(...)):
    """
    Verifies a list of emails from an uploaded .csv or .txt file and returns results as an Excel file.
    The file should contain one email address per line, typically in a column named 'emails' or 'email'.
    """
    if not (file.filename.endswith('.csv') or file.filename.endswith('.txt')):
        raise HTTPException(status_code=400, detail="Invalid file type. Please upload a .csv or .txt file.")

    try:
        contents = await file.read()
        buffer = StringIO(contents.decode('utf-8'))
        
        df_uploaded = pd.read_csv(buffer)

        email_column_name = None
        if 'emails' in df_uploaded.columns:
            email_column_name = 'emails'
        elif 'email' in df_uploaded.columns:
            email_column_name = 'email'
        else:
            raise HTTPException(status_code=400, detail="CSV file must contain a column named 'emails' or 'email'.")
        
        emails_to_verify = [
            str(email_val).strip() 
            for email_val in df_uploaded[email_column_name].tolist()
            if str(email_val).strip() != '' and str(email_val).strip().lower() != email_column_name.lower()
        ]

        if not emails_to_verify:
            raise HTTPException(status_code=400, detail="The uploaded file is empty or contains no valid emails after parsing.")

        results_list_of_pydantic_models = await process_bulk_async(emails_to_verify)

        # Prepare DataFrame with detailed columns
        processed_for_excel = []
        for r_dict in results_list_of_pydantic_models: # process_bulk_async returns dicts
            processed_for_excel.append({
                'Email': r_dict.get('email', 'N/A'),
                'Overall Status': 'VALID' if r_dict.get('is_valid') else 'INVALID',
                'Reason': r_dict.get('reason', 'N/A'),
                'Format Check': r_dict.get('details', {}).get('format_check', 'N/A'),
                'Disposable Check': r_dict.get('details', {}).get('disposable_check', 'N/A'),
                'MX Check': r_dict.get('details', {}).get('mx_check', 'N/A'),
                'Domain Age Info': r_dict.get('details', {}).get('domain_age_check', 'N/A'),
                'SMTP Check Info': r_dict.get('details', {}).get('smtp_check', 'N/A')
            })
        df_final_for_excel = pd.DataFrame(processed_for_excel)

        excel_buffer = generate_excel_report(df_final_for_excel)

        return StreamingResponse(
            excel_buffer,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=uploaded_email_results.xlsx"}
        )
    except pd.errors.EmptyDataError:
        raise HTTPException(status_code=400, detail="The uploaded CSV file is empty.")
    except KeyError:
        raise HTTPException(status_code=400, detail="CSV file must contain a column named 'emails' or 'email'.")
    except Exception as e:
        print(f"ERROR in /verify-csv/excel endpoint: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to process file for Excel: {str(e)}")


@app.get("/", tags=["Root"])
async def read_root():
    return {"message": "Welcome to the Email Verifier API. Go to /docs for documentation."}