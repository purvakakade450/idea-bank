"""Google News RSS search: free, no key. One query per sector, each looking for problem words
(shortage, losses, complaints…) in Indian English news from the last 3 days."""
import urllib.parse
import xml.etree.ElementTree as ET

import requests

from ..config import Config

NAME = "gnews"
URL = "https://news.google.com/rss/search"
PROBLEM = "(shortage OR losses OR crisis OR complaints OR struggle OR delay OR unsafe OR expensive OR fraud)"
TOPICS = [
    "farmers", "crop storage", "dairy", "fisheries", "water scarcity", "flooding drainage", "heatwave workers",
    "air pollution", "solid waste", "e-waste", "electric vehicle charging", "rooftop solar", "power cuts",
    "rural healthcare", "elderly care", "mental health students", "college graduates jobs", "school learning",
    "small business MSME", "kirana stores", "gig workers", "housing rent", "construction cost", "road safety",
    "cyber fraud UPI", "handloom artisans", "disability assistive", "public transport", "food prices", "textile workers",
]


def enabled():
    return Config.ENABLE_GNEWS


def parse(xml_text, topic):
    out = []
    for item in ET.fromstring(xml_text).iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        if not title or not link:
            continue
        out.append({
            "source": NAME,
            "title": title,
            "summary": f"Topic: {topic}",
            "url": link,
            "published_at": item.findtext("pubDate"),
            "meta": {"topic": topic, "publisher": item.findtext("source")},
        })
    return out


def fetch():
    out, errors = [], 0
    for topic in TOPICS[:Config.GNEWS_TOPICS]:
        q = f'{topic} India {PROBLEM} when:3d'
        try:
            r = requests.get(URL, params={"q": q, "hl": "en-IN", "gl": "IN", "ceid": "IN:en"},
                             timeout=Config.HTTP_TIMEOUT, headers={"User-Agent": Config.USER_AGENT})
            r.raise_for_status()
            out += parse(r.text, topic)[:8]
        except Exception:
            errors += 1
    if not out and errors:
        raise RuntimeError("Google News RSS: every topic request failed")
    return out
