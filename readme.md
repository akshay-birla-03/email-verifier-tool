Email Verifier API and Streamlit App
This project is a robust, asynchronous email verification tool built with FastAPI and a user-friendly front-end using Streamlit. It's designed to perform various checks on a single email or a list of emails to determine their validity and catch potential issues like disposable domains or invalid syntax.

Features ✨
FastAPI API: Provides endpoints for single and bulk email verification, including a new endpoint that returns results as a categorized Excel file.

Asynchronous Operations: Uses aiosmtplib and aiodns to perform non-blocking checks, allowing for high-performance concurrent processing of multiple emails.

Streamlit UI: A simple, interactive web interface for both single and bulk verification, with the ability to upload CSV/TXT files and download results.

Comprehensive Checks:

Format Check: Validates the email address syntax.

Disposable Domain Check: Identifies emails from known temporary providers using a local disposable_domains.txt file.

MX Record Check: Confirms the domain has a Mail Exchange record, which is necessary for receiving emails.

Domain Age Check: Uses the whois library to check if the domain is older than a specified threshold (90 days).

SMTP Connection Check: Attempts to connect to the email server to confirm the address exists and accepts mail.

API Endpoints 🚀
The FastAPI application provides the following endpoints:

Single Email Verification
Endpoint: POST /verify-single

Description: Verifies a single email address.

Request Body:

JSON

{
  "email": "test@example.com"
}
Response: Returns a VerificationResult object with the email's validity status and details.

Bulk Email Verification (JSON Output)
Endpoint: POST /verify-bulk

Description: Processes a list of emails concurrently and returns a JSON list of results.

Request Body:

JSON

{
  "emails": ["user1@example.com", "user2@example.com"]
}
Response: A JSON array of VerificationResult objects for each email provided.

Bulk Email Verification (Excel Output)
Endpoint: POST /verify-bulk/excel

Description: Verifies a list of emails from a JSON body and returns the results as a downloadable Excel file. The Excel file contains two sheets: "Valid Emails" and "Invalid Emails".

Request Body:

JSON

{
  "emails": ["user1@example.com", "user2@example.com"]
}
Response: A StreamingResponse with an application/vnd.openxmlformats-officedocument.spreadsheetml.sheet media type.

CSV File Upload and Verification
Endpoint: POST /verify-csv/excel

Description: Accepts an uploaded CSV or TXT file, verifies all emails within it, and returns the results as a downloadable Excel file. The file should have a column named emails or email.

Request Body: A multipart/form-data request with the file.

Response: A StreamingResponse with the Excel file.

Core Logic & Dependencies 🛠️
The core verification logic resides in verifier.py. It uses a combination of standard libraries and asynchronous third-party packages to maximize efficiency.


aiosmtplib: An asynchronous SMTP client for checking email existence without blocking the event loop.


aiodns: An asynchronous DNS library for quick MX record lookups.


whois: A synchronous library for domain information lookups, executed in a thread pool to prevent event loop blocking.


pandas: Used for processing CSV/TXT files and structuring data into DataFrames for display and Excel export.


fastapi: The web framework for building the API endpoints.


streamlit: The framework for creating the user interface.


openpyxl: A library for creating and modifying Excel files (.xlsx), used by pandas for the Excel export functionality.

The project's dependencies are listed in requirements.txt. Some notable ones are: 

aiodns, aiosmtplib, fastapi, pandas, streamlit, and whois. Disposable domains are sourced from a 

disposable_domains.txt file and include entries like mailinator.com, 10minutemail.com, and others.

Author 
Akshay Birla 
s