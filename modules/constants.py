# modules/constants.py

# Limiti
MAX_TEXT_LENGTH = 1000
MAX_TITLE_LENGTH = 100

# Ocjene
MIN_SCORE = 1
MAX_SCORE = 5

# Tekstualni limiti za utils
MAX_TEXT_MEDIUM = 500
MAX_TEXT_LONG = 2000

# Statusi
STATUS_DRAFT = "Draft"
STATUS_SUBMITTED = "Submitted"
STATUS_APPROVED = "Approved"
STATUS_ARCHIVED = "Archived"

# Default Lozinka (override env varijablom: TALENT_DEFAULT_PASSWORD)
import os
DEFAULT_PASSWORD = os.environ.get("TALENT_DEFAULT_PASSWORD", "lozinka123")

# Kriptografski salt (override env varijablom: TALENT_SECRET_SALT)
SECRET_SALT = os.environ.get("TALENT_SECRET_SALT", "SaaS_Secure_Performance_2026")
