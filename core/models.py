# core/models.py

from pydantic import BaseModel
from typing import Optional, Tuple

class VerificationResult(BaseModel):
    email: str
    is_valid: bool
    reason: str
    details: dict

class SingleEmailRequest(BaseModel):
    email: str

class BulkEmailRequest(BaseModel):
    emails: list[str]