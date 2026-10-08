"""NewsData.io latest news (free key: https://newsdata.io)."""
import requests

from ..config import Config

NAME = "newsdata"
URL = "https://newsdata.io/api/1/latest"


def enabled():
    return Config.ENABLE_NEWSDATA and bool(Config.NEWSDATA_API_KEY)


def fetch():
    params = {
        "apikey": Config.NEWSDATA_API_KEY,
        "country": Config.NEWSDATA_COUNTRY,
        "language": "en",
        "category": Config.NEWSDATA_CATEGORIES,
    }
    r = requests.get(URL, params=params, timeout=Config.HTTP_TIMEOUT, headers={"User-Agent": Config.USER_AGENT})
    r.raise_for_status()
    data = r.json()
    if data.get("status") != "success":
        raise RuntimeError(f"NewsData error: {str(data)[:200]}")
    out = []
    for a in data.get("results") or []:
        if not a.get("title") or not a.get("link"):
            continue
        out.append({
            "source": NAME,
            "title": a["title"].strip(),
            "summary": (a.get("description") or "").strip()[:600],
            "url": a["link"],
            "published_at": a.get("pubDate"),
            "meta": {"publisher": a.get("source_name") or a.get("source_id"), "category": a.get("category")},
        })
    return out
