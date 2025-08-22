# core/config.py

SMTP_TIMEOUT = 10
DNS_SERVERS = ['8.8.8.8', '1.1.1.1']
DOMAIN_AGE_THRESHOLD_DAYS = 90
# Concurrency limit for bulk SMTP checks to avoid getting blocked
SMTP_CONCURRENCY_LIMIT = 50