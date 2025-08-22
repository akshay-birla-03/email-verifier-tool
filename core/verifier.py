import re
import asyncio
import datetime
import smtplib # Potentially still needed for constants, but aiosmtplib replaces its core functionality
import socket # Used for socket.gethostname() in old smtp_check, but aiosmtplib handles this
import dns.resolver # Only for constants or old synchronous functions, will be replaced by aiodns
import whois
import aiodns
import aiosmtplib
from pathlib import Path 
import traceback 

from core import config 
from core.models import VerificationResult, SingleEmailRequest, BulkEmailRequest # Ensure these are imported from your models.py

# --- CONFIG ---
# For now, defining them here for clarity of conversion.
SMTP_TIMEOUT = 10 # seconds
MAX_DNS_RETRIES = 3 # Increased from 2 for robustness
DNS_SERVERS = ['8.8.8.8', '1.1.1.1'] # Explicitly setting them for aiodns

# Disposable domains from the text file are preferred over hardcoded ones
def get_disposable_domains_from_file() -> set:
    """Reads the disposable domains from the text file."""
    disposable_file = Path(__file__).parent / "disposable_domains.txt"
    try:
        with open(disposable_file, "r") as f:
            return {line.strip().lower() for line in f if line.strip()}
    except FileNotFoundError:
        print(f"WARNING: disposable_domains.txt not found at {disposable_file}. Using hardcoded default.")
        return {"mailinator.com", "10minutemail.com", "guerrillamail.com", "trashmail.com"} # Fallback
    except Exception as e:
        print(f"ERROR reading disposable_domains.txt: {e}. Using hardcoded default.")
        return {"mailinator.com", "10minutemail.com", "guerrillamail.com", "trashmail.com"} # Fallback


# Use the file-based disposable domains, with a fallback
DISPOSABLE_DOMAINS = get_disposable_domains_from_file()

# --- Helper Functions (Asynchronous) ---

async def is_valid_format_async(email: str) -> bool:
    """Asynchronously checks if the email format is valid."""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

async def is_disposable_email_async(email: str) -> bool:
    """Asynchronously checks if the email is from a disposable domain."""
    domain = email.split('@')[-1].lower()
    return domain in DISPOSABLE_DOMAINS

async def has_mx_record_async(domain: str) -> bool:
    """Asynchronously checks for MX records with retries, using aiodns."""
    resolver = aiodns.DNSResolver()
    resolver.nameservers = DNS_SERVERS # Set explicit DNS servers
    
    for attempt in range(MAX_DNS_RETRIES):
        try:
            mx_records = await resolver.query(domain, 'MX')
            if mx_records: # Ensure records are actually found
                return True
        except aiodns.error.DNSError as e:
            print(f"DEBUG: MX DNS query attempt {attempt+1}/{MAX_DNS_RETRIES} for {domain} failed: {e}")
            if attempt < MAX_DNS_RETRIES - 1:
                await asyncio.sleep(0.5) # Wait before retrying
            else:
                return False # All retries failed
        except asyncio.TimeoutError:
            print(f"DEBUG: MX DNS query attempt {attempt+1}/{MAX_DNS_RETRIES} for {domain} timed out.")
            if attempt < MAX_DNS_RETRIES - 1:
                await asyncio.sleep(0.5)
            else:
                return False
        except Exception as e: # Catch any other unexpected errors
            print(f"DEBUG: Unexpected error during MX DNS query attempt {attempt+1}/{MAX_DNS_RETRIES} for {domain}: {e}")
            traceback.print_exc()
            return False
    return False # Fallback if loop finishes without returning

async def check_domain_age_async(domain: str) -> tuple[bool, str]:
    """
    Asynchronously checks domain age by running the synchronous whois library
    in a separate thread to avoid blocking the event loop.
    """
    def sync_whois_lookup(d):
        """The original synchronous function to be run in a thread."""
        try:
            w = whois.whois(d)
            creation_date = w.creation_date
            
            if isinstance(creation_date, list):
                creation_date = creation_date[0] # Take the first date if it's a list

            if not isinstance(creation_date, datetime.datetime):
                return (True, "WHOIS returned no valid date, assuming valid")

            age_days = (datetime.datetime.now() - creation_date).days
            # Using 90 days as per your original code's implied threshold
            is_old_enough = age_days >= 90 
            reason = f"Domain is {age_days} days old."
            return (is_old_enough, reason)
        except Exception as e:
            # If WHOIS lookup fails, assume valid to not block verification unnecessarily
            return (True, f"WHOIS lookup failed: {str(e)}, assuming valid.")

    try:
        # Run the synchronous function in a non-blocking way
        loop = asyncio.get_running_loop()
        is_old_enough, reason = await loop.run_in_executor(
            None, sync_whois_lookup, domain
        )
        return is_old_enough, reason
    except Exception as e:
        # If executor execution fails, assume valid
        return True, f"WHOIS execution failed: {str(e)}, assuming valid."


async def smtp_check_async(email: str, semaphore: asyncio.Semaphore) -> tuple[bool, str]:
    """
    Asynchronously performs SMTP verification using aiosmtplib.
    Includes retries for MX lookup and robust error handling.
    """
    domain = email.split('@')[-1]
    async with semaphore:
        try:
            resolver = aiodns.DNSResolver()
            resolver.nameservers = DNS_SERVERS # Set explicit DNS servers
            
            # --- MX Record Lookup with Retries (copied from has_mx_record_async logic) ---
            mx_records = None
            for attempt in range(MAX_DNS_RETRIES):
                try:
                    mx_records = await resolver.query(domain, 'MX')
                    if mx_records:
                        break # Success, break out of retry loop
                except aiodns.error.DNSError as e:
                    print(f"DEBUG: SMTP MX DNS query attempt {attempt+1}/{MAX_DNS_RETRIES} for {domain} failed: {e}")
                    if attempt < MAX_DNS_RETRIES - 1:
                        await asyncio.sleep(0.5) # Wait before retrying
                    else:
                        return False, f"DNS lookup for MX records failed after {MAX_DNS_RETRIES} attempts: {e}"
                except asyncio.TimeoutError:
                    print(f"DEBUG: SMTP MX DNS query attempt {attempt+1}/{MAX_DNS_RETRIES} for {domain} timed out.")
                    if attempt < MAX_DNS_RETRIES - 1:
                        await asyncio.sleep(0.5)
                    else:
                        return False, f"DNS lookup for MX records timed out after {MAX_DNS_RETRIES} attempts."

            if not mx_records:
                return False, "No MX records found for domain after retries."

            # Sort by preference (priority) and get the exchange host
            mx_record_host = str(sorted(mx_records, key=lambda r: r.priority)[0].host)

            smtp_client = aiosmtplib.SMTP(
                hostname=mx_record_host, port=25, timeout=SMTP_TIMEOUT
            )

            async with smtp_client:
                # Try to upgrade to a secure connection
                try:
                    await smtp_client.starttls()
                except aiosmtplib.errors.SMTPException as e_starttls:
                    print(f"DEBUG: STARTTLS failed for {email} on {mx_record_host}: {e_starttls}")
                    pass 
                
                # CORRECTED LINE: Remove socket.gethostname()
                await smtp_client.helo() # Call helo() without arguments
                # Or, even better for modern servers, use ehlo()
                #await smtp_client.ehlo()

                await smtp_client.mail('test@example.com')
                code, message = await smtp_client.rcpt(email)

                if code in (250, 251):
                    return True, "SMTP check passed."
                else:
                    return False, f"SMTP check failed: {code} {message.decode().strip()}"

        except aiosmtplib.errors.SMTPConnectError as e:
            print(f"DEBUG: SMTPConnectError for {email}: {e}")
            traceback.print_exc()
            return False, f"SMTP connection failed: {e}"
        except asyncio.TimeoutError:
            print(f"DEBUG: asyncio.TimeoutError for {email}")
            traceback.print_exc()
            return False, "SMTP connection timed out."
        except aiodns.error.DNSError as e: # This handles DNS errors if they occur during the smtp_client setup
            print(f"DEBUG: aiodns.error.DNSError (during SMTP setup) for {email}: {e}")
            traceback.print_exc()
            return False, f"DNS lookup for MX records failed: {e}"
        except Exception as e:
            print(f"DEBUG: UNEXPECTED EXCEPTION in SMTP check for {email}: {type(e).__name__}: {e}")
            traceback.print_exc()
            return False, f"An unexpected error occurred during SMTP check: {str(e)}"

# === FULL ASYNCHRONOUS CHECK FOR ONE EMAIL ===
async def verify_email_async(email: str, semaphore: asyncio.Semaphore) -> VerificationResult:
    """Main async orchestrator for verifying a single email."""
    details = {}
    is_valid = True
    reason = "Email appears to be valid"

    # 1. Format Check
    if not await is_valid_format_async(email):
        details['format_check'] = 'Failed'
        return VerificationResult(email=email, is_valid=False, reason="Invalid email format", details=details)
    details['format_check'] = 'Passed'

    # 2. Disposable Check
    if await is_disposable_email_async(email):
        details['disposable_check'] = 'Failed'
        return VerificationResult(email=email, is_valid=False, reason="Disposable email provider", details=details)
    details['disposable_check'] = 'Passed'

    domain = email.split('@')[-1]

    # 3. MX Record Check
    if not await has_mx_record_async(domain):
        details['mx_check'] = 'Failed'
        return VerificationResult(email=email, is_valid=False, reason="Domain does not accept mail (MX lookup failed)", details=details)
    details['mx_check'] = 'Passed'

    # 4. Domain Age Check
    age_ok, age_reason = await check_domain_age_async(domain)
    details['domain_age_check'] = age_reason
    if not age_ok:
        return VerificationResult(email=email, is_valid=False, reason="Domain is too new", details=details)

    # 5. SMTP Check
    smtp_ok, smtp_reason = await smtp_check_async(email, semaphore)
    details['smtp_check'] = smtp_reason
    if not smtp_ok:
        return VerificationResult(email=email, is_valid=False, reason="SMTP validation failed", details=details)

    return VerificationResult(email=email, is_valid=True, reason="Email appears to be valid", details=details)


# === ASYNCHRONOUS BULK PROCESSING ===
async def process_bulk_async(emails: list[str]) -> list:
    """Processes a list of emails concurrently."""
    # Use config.SMTP_CONCURRENCY_LIMIT for the semaphore, assuming it's defined
    # If not, you might want to set a default, e.g., asyncio.Semaphore(10)
    semaphore = asyncio.Semaphore(getattr(config, 'SMTP_CONCURRENCY_LIMIT', 10)) 
    tasks = [verify_email_async(email, semaphore) for email in emails]
    results = await asyncio.gather(*tasks)
    return [r.model_dump() for r in results] 

