# 📧 Email Verifier — Async API + Streamlit App

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/akshay-birla-03/email-verifier-tool/blob/main/notebooks/Run_in_Colab.ipynb)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)](#)
[![Streamlit](https://img.shields.io/badge/Streamlit-FF4B4B?logo=streamlit&logoColor=white)](#)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue?logo=python&logoColor=white)](#)

A robust, **asynchronous** email-verification tool: a **FastAPI** API plus a **Streamlit**
UI that validate single emails or bulk lists across five independent checks — and can return
categorised results as an Excel file.

▶️ **Try it now, no setup:** click the **Open in Colab** badge — it clones, installs and runs
the verifier on a sample batch of emails.

## The five checks

| Check | What it confirms |
|-------|------------------|
| **Format** | valid email syntax |
| **Disposable domain** | not a known throwaway provider (local \`disposable_domains.txt\`) |
| **MX record** | the domain can actually receive mail |
| **Domain age** | domain older than a threshold (via WHOIS) — flags fresh, risky domains |
| **SMTP** | the mailbox exists and accepts mail (non-blocking \`aiosmtplib\`) |

Async throughout (\`aiosmtplib\`, \`aiodns\`) so bulk lists are verified concurrently.

## API endpoints

| Method & path | Purpose |
|---------------|---------|
| \`POST /verify-single\` | verify one email → JSON result |
| \`POST /verify-bulk/excel\` | verify a list → downloadable Excel (Valid / Invalid sheets) |
| \`POST /verify-csv/excel\` | upload a CSV/TXT of emails → Excel results |

## Quickstart (local)

\`\`\`bash
git clone https://github.com/akshay-birla-03/email-verifier-tool.git
cd email-verifier-tool
pip install -r requirements.txt

uvicorn api.main:app --reload      # API + docs at http://localhost:8000/docs
streamlit run ui/app.py            # interactive UI
\`\`\`

## Project layout

\`\`\`
api/main.py        # FastAPI endpoints
core/verifier.py   # async verification engine (the 5 checks)
core/models.py     # Pydantic request/response models
core/config.py     # settings
core/disposable_domains.txt
ui/app.py          # Streamlit interface
notebooks/Run_in_Colab.ipynb
requirements.txt
\`\`\`

## Tech

Python · FastAPI · Streamlit · aiosmtplib · aiodns · python-whois · pandas · openpyxl

---
Author: **Akshay Birla** · [GitHub](https://github.com/akshay-birla-03)
