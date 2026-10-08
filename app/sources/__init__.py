"""Live market-signal sources. Each source returns a list of signal dicts:
{"source", "title", "summary", "url", "published_at", "meta"}"""
from . import gdelt, gnews, newsdata, reddit, trends

ALL = {
    "newsdata": newsdata,
    "gdelt": gdelt,
    "gnews": gnews,
    "trends": trends,
    "reddit": reddit,
}
