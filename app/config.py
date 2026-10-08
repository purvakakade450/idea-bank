import os
from dotenv import load_dotenv

load_dotenv()


def _bool(name, default=False):
    v = os.getenv(name)
    if v is None or v == "":
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


def _int(name, default):
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _list(name, default=""):
    return [x.strip() for x in os.getenv(name, default).split(",") if x.strip()]


class Config:
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
    ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5-5")

    NEWSDATA_API_KEY = os.getenv("NEWSDATA_API_KEY", "")
    NEWSDATA_COUNTRY = os.getenv("NEWSDATA_COUNTRY", "in")
    NEWSDATA_CATEGORIES = os.getenv("NEWSDATA_CATEGORIES", "business,technology,environment,health,science")

    REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID", "")
    REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET", "")
    REDDIT_SUBREDDITS = _list("REDDIT_SUBREDDITS", "india,indianstartups,developersIndia,IndianFarmers")

    ENABLE_NEWSDATA = _bool("ENABLE_NEWSDATA", True)
    ENABLE_GDELT = _bool("ENABLE_GDELT", True)
    ENABLE_TRENDS = _bool("ENABLE_TRENDS", True)
    ENABLE_GNEWS = _bool("ENABLE_GNEWS", True)
    GNEWS_TOPICS = _int("GNEWS_TOPICS", 30)
    ENABLE_REDDIT = _bool("ENABLE_REDDIT", True)
    TRENDS_GEO = os.getenv("TRENDS_GEO", "IN")

    INGEST_INTERVAL_HOURS = max(1, _int("INGEST_INTERVAL_HOURS", 4))
    MAX_SIGNALS_PER_RUN = _int("MAX_SIGNALS_PER_RUN", 60)
    MAX_IDEAS_PER_RUN = _int("MAX_IDEAS_PER_RUN", 6)
    MIN_EVIDENCE = max(1, _int("MIN_EVIDENCE", 1))
    AUTO_APPROVE = _bool("AUTO_APPROVE", False)

    PUBLIC_URL = os.getenv("PUBLIC_URL", "http://localhost:8000")
    SMTP_HOST = os.getenv("SMTP_HOST", "")
    SMTP_PORT = _int("SMTP_PORT", 587)
    SMTP_USER = os.getenv("SMTP_USER", "")
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
    SMTP_FROM = os.getenv("SMTP_FROM", "")
    SMTP_TLS = _bool("SMTP_TLS", True)

    ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
    ADMIN_SESSION_HOURS = _int("ADMIN_SESSION_HOURS", 8)
    ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")
    DATABASE_PATH = os.getenv("DATABASE_PATH", "data/ideabank.db")
    SECRET_KEY = os.getenv("SECRET_KEY", "dev")
    USER_AGENT = "IdeaBank/1.0 (student project)"
    HTTP_TIMEOUT = _int("HTTP_TIMEOUT", 20)
