"""GDELT DOC 2.0 API: free, no key. Searches the last day of Indian English news
for problem words (shortages, price rises, complaints…)."""
import requests

from ..config import Config

NAME = "gdelt"
URL = "https://api.gdeltproject.org/api/v2/doc/doc"
QUERY = ('(shortage OR "price rise" OR "price hike" OR complaints OR losses OR crisis OR delay OR unemployment) '
         "sourcecountry:IN sourcelang:english")


def enabled():
    return Config.ENABLE_GDELT


def fetch():
    params = {"query": QUERY, "mode": "ArtList", "format": "json", "maxrecords": 75, "timespan": "1d", "sort": "DateDesc"}
    r = requests.get(URL, params=params, timeout=Config.HTTP_TIMEOUT, headers={"User-Agent": Config.USER_AGENT})
    r.raise_for_status()
    try:
        data = r.json()
    except ValueError:
        # GDELT replies with plain text when the query is rejected or rate limited
        raise RuntimeError(f"GDELT: {r.text[:200]}")
    out = []
    for a in data.get("articles") or []:
        if not a.get("title") or not a.get("url"):
            continue
        out.append({
            "source": NAME,
            "title": a["title"].strip(),
            "summary": "",
            "url": a["url"],
            "published_at": a.get("seendate"),
            "meta": {"publisher": a.get("domain")},
        })
    return out
