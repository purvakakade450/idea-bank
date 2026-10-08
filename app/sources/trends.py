"""Google Trends 'trending now' RSS feed: free, no key."""
import datetime as dt
import urllib.parse
import xml.etree.ElementTree as ET

import requests

from ..config import Config

NAME = "trends"
URL = "https://trends.google.com/trending/rss"
NS = {"ht": "https://trends.google.com/trending/rss"}


def enabled():
    return Config.ENABLE_TRENDS


def parse(xml_text, geo, day):
    root = ET.fromstring(xml_text)
    out = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        if not title:
            continue
        traffic = item.findtext("ht:approx_traffic", default="", namespaces=NS)
        news = [
            {"title": (n.findtext("ht:news_item_title", default="", namespaces=NS) or "").strip(),
             "url": n.findtext("ht:news_item_url", default="", namespaces=NS)}
            for n in item.findall("ht:news_item", NS)
        ]
        summary = "; ".join(n["title"] for n in news if n["title"])[:600]
        q = urllib.parse.quote(title)
        out.append({
            "source": NAME,
            "title": f"Trending search: {title}",
            "summary": summary,
            # one row per search term per day, so a term trending again tomorrow is a new signal
            "url": f"https://trends.google.com/trends/explore?geo={geo}&q={q}#{day}",
            "published_at": item.findtext("pubDate"),
            "meta": {"traffic": traffic, "news": news[:3]},
        })
    return out


def fetch():
    geo = Config.TRENDS_GEO
    r = requests.get(URL, params={"geo": geo}, timeout=Config.HTTP_TIMEOUT, headers={"User-Agent": Config.USER_AGENT})
    r.raise_for_status()
    return parse(r.text, geo, dt.date.today().isoformat())
