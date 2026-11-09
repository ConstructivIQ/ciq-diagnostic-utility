"""
config.py — centralised configuration loader.
All settings are read from environment variables (or a .env file).
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from the project root if present
_env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=_env_path, override=False)


def _optional(key: str, default: str = "") -> str:
    return os.getenv(key, default)


# ── Jira ─────────────────────────────────────────────────────────────────────
JIRA_BASE_URL: str = _optional("JIRA_BASE_URL")
JIRA_EMAIL: str = _optional("JIRA_EMAIL")
JIRA_API_TOKEN: str = _optional("JIRA_API_TOKEN")

# ── Anthropic ─────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY: str = _optional("ANTHROPIC_API_KEY")
ANTHROPIC_MODEL: str = _optional("ANTHROPIC_MODEL", "claude-opus-4-5")

# ── Email ─────────────────────────────────────────────────────────────────────
EMAIL_HOST: str = _optional("EMAIL_HOST", "imap.gmail.com")
EMAIL_PORT: int = int(_optional("EMAIL_PORT", "993"))
EMAIL_USER: str = _optional("EMAIL_USER")
EMAIL_PASSWORD: str = _optional("EMAIL_PASSWORD")
EMAIL_FOLDER: str = _optional("EMAIL_FOLDER", "INBOX")

# ── Logs ──────────────────────────────────────────────────────────────────────
LOG_PATHS: list[str] = [
    p.strip()
    for p in _optional("LOG_PATHS", "").split(",")
    if p.strip()
]

# ── API ───────────────────────────────────────────────────────────────────────
API_BASE_URL: str = _optional("API_BASE_URL")
API_AUTH_TOKEN: str = _optional("API_AUTH_TOKEN")

# ── AWS — Non-Prod account (dev / qa / perf / demo) ──────────────────────────
AWS_ACCESS_KEY_ID_NONPROD: str = _optional("AWS_ACCESS_KEY_ID_NONPROD")
AWS_SECRET_ACCESS_KEY_NONPROD: str = _optional("AWS_SECRET_ACCESS_KEY_NONPROD")
AWS_REGION_NONPROD: str = _optional("AWS_REGION_NONPROD", "us-east-2")

# ── AWS — Prod account ────────────────────────────────────────────────────────
AWS_ACCESS_KEY_ID_PROD: str = _optional("AWS_ACCESS_KEY_ID_PROD")
AWS_SECRET_ACCESS_KEY_PROD: str = _optional("AWS_SECRET_ACCESS_KEY_PROD")
AWS_REGION_PROD: str = _optional("AWS_REGION_PROD", "us-east-1")

# Convenience: backwards-compatible single-account keys (used when only one set is configured)
AWS_ACCESS_KEY_ID: str = _optional("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY: str = _optional("AWS_SECRET_ACCESS_KEY")
AWS_REGION: str = _optional("AWS_REGION", "us-east-2")

# ── PostgreSQL / RDS ──────────────────────────────────────────────────────────
PG_HOST: str = _optional("PG_HOST")
PG_PORT: int = int(_optional("PG_PORT", "5432"))
PG_DATABASE: str = _optional("PG_DATABASE")
PG_USER: str = _optional("PG_USER")
PG_PASSWORD: str = _optional("PG_PASSWORD")
