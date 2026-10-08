"""Team fit: how well an idea suits a team (every member gets a role, skills, time, product, budget, market)."""
from .domains import FIELDS, total

BUDGET_ORDER = {"low": 0, "mid": 1, "high": 2}


def team_hours(team):
    return sum(int(m.get("hours") or 0) for m in team["members"])


def team_months(team):
    return min((int(m.get("months") or 0) for m in team["members"]), default=0)


def fit(idea, team):
    tf = sorted({m["field"] for m in team["members"]})
    need = list((idea.get("roles") or {}).keys())
    used = [f for f in tf if f in idea["roles"] or f == "other"]
    missing = [f for f in need if f not in tf]
    unused = [f for f in tf if f not in idea["roles"] and f != "other"]
    usage = len(used) / len(tf) if tf else 0
    cover = (len(need) - len(missing)) / len(need) if need else 0
    need_hours = (idea.get("hours") or 30) * (idea.get("months") or 6)
    time = min(1.0, team_hours(team) * team_months(team) / (need_hours or 1))

    p = team.get("product") or "mix"
    product = 1 if p == "mix" else (1 if idea.get("product") == p else (0.75 if idea.get("product") == "mix" else 0.35))
    b = team.get("budget") or "unsure"
    if b == "unsure":
        budget = 0.75
    else:
        gap = max(0, BUDGET_ORDER.get(idea.get("budget"), 1) - BUDGET_ORDER.get(b, 1))
        budget = [1, 0.5, 0.15][gap]
    market = 1 if (team.get("market") in (None, "", "Any") or idea.get("sector") == team.get("market")) else 0.7
    st = team.get("setting") or "any"
    setting = 1 if (st == "any" or idea.get("setting") in ("any", st)) else 0.9

    score = round(100 * (0.35 * usage + 0.20 * cover + 0.15 * time + 0.10 * product + 0.10 * budget
                         + 0.10 * total(idea.get("scores")) / 100) * market * setting)
    return {
        "match": score,
        "fields_used": len(used),
        "fields_total": len(tf),
        "missing": [FIELDS[f] for f in missing],
        "unused": [FIELDS[f] for f in unused],
        "fits_time": time >= 1,
        "fits_budget": budget >= 1,
    }
