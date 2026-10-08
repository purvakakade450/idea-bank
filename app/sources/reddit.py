"""Reddit top posts of the day from chosen subreddits.
Uses an app-only OAuth token when REDDIT_CLIENT_ID/SECRET are set (recommended);
otherwise tries the public JSON endpoints, which Reddit may block."""
import time

import requests

from ..config import Config

NAME = "reddit"
_token = {"value": None, "exp": 0}


def enabled():
    return Config.ENABLE_REDDIT and bool(Config.REDDIT_SUBREDDITS)


def _get_token():
    if _token["value"] and _token["exp"] > time.time() + 60:
        return _token["value"]
    r = requests.post(
        "https://www.reddit.com/api/v1/access_token",
        auth=(Config.REDDIT_CLIENT_ID, Config.REDDIT_CLIENT_SECRET),
        data={"grant_type": "client_credentials"},
        headers={"User-Agent": Config.USER_AGENT},
        timeout=Config.HTTP_TIMEOUT,
    )
    r.raise_for_status()
    d = r.json()
    _token["value"] = d["access_token"]
    _token["exp"] = time.time() + int(d.get("expires_in", 3600))
    return _token["value"]


def fetch():
    use_oauth = bool(Config.REDDIT_CLIENT_ID and Config.REDDIT_CLIENT_SECRET)
    headers = {"User-Agent": Config.USER_AGENT}
    base = "https://www.reddit.com"
    if use_oauth:
        headers["Authorization"] = f"bearer {_get_token()}"
        base = "https://oauth.reddit.com"
    out, errors = [], []
    for sub in Config.REDDIT_SUBREDDITS:
        try:
            r = requests.get(f"{base}/r/{sub}/top.json", params={"t": "day", "limit": 25},
                             headers=headers, timeout=Config.HTTP_TIMEOUT)
            r.raise_for_status()
            for c in r.json().get("data", {}).get("children", []):
                p = c.get("data", {})
                if not p.get("title") or p.get("stickied") or p.get("over_18"):
                    continue
                out.append({
                    "source": NAME,
                    "title": p["title"].strip(),
                    "summary": (p.get("selftext") or "").strip()[:600],
                    "url": "https://www.reddit.com" + p.get("permalink", ""),
                    "published_at": str(int(p.get("created_utc", 0))),
                    "meta": {"subreddit": sub, "score": p.get("score"), "comments": p.get("num_comments")},
                })
        except Exception as e:  # keep going with other subreddits
            errors.append(f"r/{sub}: {e}")
        time.sleep(1)  # be polite
    if errors and not out:
        raise RuntimeError("; ".join(errors)[:300])
    return out
