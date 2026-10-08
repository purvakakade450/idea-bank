"""Fields (team backgrounds), scoring lenses and per-field metrics."""

FIELDS = {
    "cs": "Computer science",
    "mech": "Mechanical",
    "elec": "Electrical",
    "civil": "Civil",
    "biz": "Business",
    "other": "Other",
}

# Score out of 100
LENSES = [("need", 25), ("revenue", 25), ("seed", 20), ("entre", 15), ("impact", 15)]

# The six reality-check questions every idea must answer
CHECKS = {
    "demand": "Do people really need this?",
    "today": "What do they do today instead?",
    "who": "Who needs it most, exactly?",
    "wedge": "What is the smallest version we can sell first?",
    "seen": "Have we seen real people struggle with it?",
    "future": "Will this matter more in the future?",
}

# Domain metrics: what each field is judged on
DOMAIN_METRICS = {
    "cs": ["active users", "monthly revenue", "build time"],
    "mech": ["unit cost", "prototype time", "manufacturing scale"],
    "elec": ["power saved", "hardware cost", "certifications needed"],
    "civil": ["project cost", "government tenders", "lifespan"],
    "biz": ["margin", "cost to win a customer", "repeat buyers"],
    "other": ["cost to start", "time to first sale"],
}

PRODUCT = {"app": "App", "device": "Device", "service": "Service", "mix": "Mix"}
BUDGET = {"low": "Under ₹50,000", "mid": "₹50,000 – ₹5 lakh", "high": "Above ₹5 lakh"}
SETTING = {"city": "Big city", "town": "Small town", "rural": "Rural area", "any": "Anywhere in India"}
MODEL_KEYS = ["customer", "value", "revenue", "pricing", "costs", "channels"]
GATES = {"pay": "Someone will pay", "earn": "Clear way to earn revenue", "small": "Can start small", "proof": "Real proof"}


def total(scores):
    return sum(int((scores or {}).get(k, 0) or 0) for k, _ in LENSES)


def clean_idea(o):
    """Validate an idea dict coming from the AI or a user. Returns a clean dict or None."""
    if not isinstance(o, dict) or not o.get("title") or not o.get("problem"):
        return None

    def s(v, n):
        return str(v or "").strip()[:n]

    roles = {}
    for k, v in (o.get("roles") or {}).items():
        if k in FIELDS and v:
            roles[k] = s(v, 160)
    scores = {}
    for k, mx in LENSES:
        try:
            scores[k] = max(0, min(mx, int(round(float((o.get("scores") or {}).get(k, 0))))))
        except (TypeError, ValueError):
            scores[k] = 0
    checks = {k: s((o.get("checks") or {}).get(k), 220) for k in CHECKS}
    model = {k: s((o.get("model") or {}).get(k), 140) for k in MODEL_KEYS}
    gates = {}
    for k in GATES:
        g = (o.get("gates") or {}).get(k) or {}
        gates[k] = {"pass": g.get("pass") is True, "why": s(g.get("why"), 200)}
    metrics = {}
    for k, v in (o.get("domain_metrics") or {}).items():
        if k in FIELDS and isinstance(v, dict):
            metrics[k] = {s(mk, 40): s(mv, 120) for mk, mv in list(v.items())[:4]}

    def clamp(v, lo, hi, d):
        try:
            return max(lo, min(hi, int(v)))
        except (TypeError, ValueError):
            return d

    return {
        "title": s(o["title"], 120),
        "sector": s(o.get("sector") or "Other", 40),
        "product": o.get("product") if o.get("product") in PRODUCT else "mix",
        "budget": o.get("budget") if o.get("budget") in BUDGET else "mid",
        "setting": o.get("setting") if o.get("setting") in SETTING else "any",
        "problem": s(o["problem"], 300),
        "solution": s(o.get("solution"), 300),
        "roles": roles,
        "model": model,
        "hours": clamp(o.get("hours"), 5, 200, 30),
        "months": clamp(o.get("months"), 1, 24, 6),
        "scores": scores,
        "checks": checks,
        "gates": gates,
        "domain_metrics": metrics,
    }
