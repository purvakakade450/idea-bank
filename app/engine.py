"""Steps 2-4 of the flow: the idea engine.
signals -> problems (deduplicated, with evidence) -> ideas (reality check, domain metrics, score)."""
import logging
import re

from . import db, llm, mailer
from .config import Config
from .domains import BUDGET, CHECKS, DOMAIN_METRICS, FIELDS, GATES, LENSES, PRODUCT, SETTING, clean_idea, total

log = logging.getLogger(__name__)

STOP = set("a an the of to in for on and or with by from at is are was were be been it its this that as into about over "
           "people their they them can cannot can't not no who what why how more less new".split())
PROBLEM_WORDS = re.compile(r"shortage|price|hike|rise|loss|delay|crisis|complain|struggle|lack|unable|problem|"
                           r"expensive|costly|unsafe|pollut|flood|heat|drought|jobless|unemploy|traffic|waste|outage|"
                           r"scam|fraud|queue|trending", re.I)


def tokens(text):
    return {w for w in re.findall(r"[a-z]{3,}", (text or "").lower()) if w not in STOP}


def similar(a, b):
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


# ---------------------------------------------------------------- problems
EXTRACT_PROMPT = """You read market signals from India (news, search trends, online posts) and find REAL PROBLEMS
that a small student startup team could solve with a product or service.

Signals (id: source | title | summary):
{signals}

Rules:
- Only include problems that hurt a clear group of people or businesses and that a startup could address.
- Skip celebrity, sports, politics-only, crime and entertainment items unless they reveal a real everyday problem.
- Merge signals that describe the same problem.
- Use simple English.

Return JSON: {{"problems":[{{"statement":str (one sentence: who struggles with what),
"who":str, "why_now":str, "sector":str (e.g. "Farming and food", "Mobility", "Water", "Education", "Health",
"Manufacturing", "Housing", "Clean air", "Finance", "Retail"),
"fields":[subset of {fields}], "signal_ids":[int]}}]}}
Return {{"problems":[]}} if nothing qualifies."""


def extract_problems(batch):
    lines = "\n".join(f"{s['id']}: {s['source']} | {s['title']} | {(s['summary'] or '')[:220]}" for s in batch)
    out = llm.complete_json(EXTRACT_PROMPT.format(signals=lines, fields=list(FIELDS)), max_tokens=3000)
    valid_ids = {s["id"] for s in batch}
    res = []
    for p in (out.get("problems") if isinstance(out, dict) else None) or []:
        if not isinstance(p, dict) or not p.get("statement"):
            continue
        ids = [i for i in (p.get("signal_ids") or []) if isinstance(i, int) and i in valid_ids]
        if not ids:
            continue
        res.append({
            "statement": str(p["statement"])[:300],
            "who": str(p.get("who") or "")[:160],
            "why_now": str(p.get("why_now") or "")[:220],
            "sector": str(p.get("sector") or "Other")[:40],
            "fields": [f for f in (p.get("fields") or []) if f in FIELDS][:5],
            "signal_ids": ids,
        })
    return res


def save_problem(p):
    existing = db.q("SELECT id, statement FROM problems ORDER BY updated_at DESC LIMIT 300")
    match = max(existing, key=lambda e: similar(e["statement"], p["statement"]), default=None)
    if match and similar(match["statement"], p["statement"]) >= 0.45:
        pid = match["id"]
    else:
        pid = db.x("INSERT INTO problems(statement,who,why_now,sector,fields,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
                   (p["statement"], p["who"], p["why_now"], p["sector"], db.dumps(p["fields"]), db.now(), db.now()))
    for sid in p["signal_ids"]:
        db.conn().execute("INSERT OR IGNORE INTO problem_signals(problem_id,signal_id) VALUES(?,?)", (pid, sid))
    db.conn().commit()
    n = db.q("SELECT COUNT(*) AS n FROM problem_signals WHERE problem_id=?", (pid,), one=True)["n"]
    db.x("UPDATE problems SET evidence_count=?, updated_at=? WHERE id=?", (n, db.now(), pid))
    return pid


# ---------------------------------------------------------------- ideas
IDEA_PROMPT = """You are the idea engine of Idea Bank, which turns real market problems in India into business ideas
for mixed student teams (computer, mechanical, electrical, civil, business).

PROBLEM: {statement}
WHO: {who}
WHY NOW: {why_now}
EVIDENCE (real signals):
{evidence}
{team}
Create ONE business idea. Then judge it honestly:
1. Four must-pass rules (gates): pay (a named customer will pay), earn (clear revenue model),
   small (first version in under 3 months), proof (the evidence shows real struggle).
2. Reality check: answer six questions: {checks}
3. Domain metrics: for each field with a role, give a short assessment of: {metrics}
4. Score: need 0-25, revenue 0-25, seed (can it grow, why now) 0-20, entre (can a small team start it) 0-15, impact 0-15.
Give a real role to as many fields as genuinely make sense. Do not invent statistics, prices or market sizes;
use "[₹__]" for prices.

Return JSON: {{"title":str,"sector":str,"product":one of {products},"budget":one of {budgets},"setting":one of {settings},
"problem":str,"solution":str,"roles":{{field_key:str}},
"model":{{"customer":str,"value":str,"revenue":str,"pricing":str,"costs":str,"channels":str}},
"hours":int (team hours per week needed),"months":int,
"gates":{{"pay":{{"pass":bool,"why":str}},"earn":{{...}},"small":{{...}},"proof":{{...}}}},
"checks":{{"demand":str,"today":str,"who":str,"wedge":str,"seen":str,"future":str}},
"domain_metrics":{{field_key:{{metric:str}}}},
"scores":{{"need":int,"revenue":int,"seed":int,"entre":int,"impact":int}}}}
Field keys: {fields}. Keep every string under 150 characters, simple English."""


def team_text(team):
    if not team:
        return ""
    m = "; ".join(f"{FIELDS.get(x['field'], x['field'])} ({x.get('skills') or 'skills not given'}, {x['hours']} h/week)"
                  for x in team["members"])
    return (f"TEAM: {m}. Market: {team.get('market') or 'Any'}. Product wanted: {team.get('product') or 'mix'}. "
            f"Budget: {team.get('budget') or 'unsure'}. Where: {team.get('setting') or 'any'} {team.get('city') or ''}.\n"
            "Every team field must get a real role.\n")


def generate_idea(problem, evidence, team=None):
    ev = "\n".join(f"- [{e['source']}] {e['title']}" for e in evidence[:8]) or "- (user submitted)"
    prompt = IDEA_PROMPT.format(
        statement=problem["statement"], who=problem.get("who", ""), why_now=problem.get("why_now", ""),
        evidence=ev, team=team_text(team), checks="; ".join(CHECKS.values()),
        metrics="; ".join(f"{k}: {', '.join(v)}" for k, v in DOMAIN_METRICS.items()),
        products=list(PRODUCT), budgets=list(BUDGET), settings=list(SETTING), fields=list(FIELDS))
    return clean_idea(llm.complete_json(prompt, max_tokens=3000))


def insert_idea(idea, problem_id=None, origin="engine", force_status=None):
    gates_ok = all(idea["gates"].get(k, {}).get("pass") for k in GATES)
    t = total(idea["scores"])
    if force_status:
        status = force_status
    elif not gates_ok:
        status = "rejected"
    elif Config.AUTO_APPROVE and t >= 50:
        status = "approved"
    else:
        status = "pending"
    return db.x(
        """INSERT INTO ideas(problem_id,title,sector,problem,solution,product,budget,setting,model,roles,hours,months,
           scores,total,checks,gates,domain_metrics,status,origin,created_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (problem_id, idea["title"], idea["sector"], idea["problem"], idea["solution"], idea["product"],
         idea["budget"], idea["setting"], db.dumps(idea["model"]), db.dumps(idea["roles"]), idea["hours"],
         idea["months"], db.dumps(idea["scores"]), t, db.dumps(idea["checks"]), db.dumps(idea["gates"]),
         db.dumps(idea["domain_metrics"]), status, origin, db.now()))


def evidence_for(problem_id):
    return db.q("""SELECT s.id, s.source, s.title, s.url, s.published_at FROM signals s
                   JOIN problem_signals ps ON ps.signal_id=s.id WHERE ps.problem_id=? ORDER BY s.fetched_at DESC""",
                (problem_id,))


def run():
    if not llm.available():
        return {"skipped": "ANTHROPIC_API_KEY is not set, so the engine cannot find problems or create ideas"}
    report = {"signals": 0, "problems": 0, "ideas": 0, "errors": []}
    pending = db.q("SELECT id, source, title, summary FROM signals WHERE processed=0 ORDER BY fetched_at DESC LIMIT ?",
                   (Config.MAX_SIGNALS_PER_RUN,))
    # cheap pre-filter: keep likely problem signals (always keep trends), drop the rest without an AI call
    keep = [s for s in pending if s["source"] == "trends" or PROBLEM_WORDS.search(s["title"] + " " + (s["summary"] or ""))]
    drop = [s["id"] for s in pending if s not in keep]
    if drop:
        db.conn().executemany("UPDATE signals SET processed=1 WHERE id=?", [(i,) for i in drop])
        db.conn().commit()
    for i in range(0, len(keep), 20):
        batch = keep[i:i + 20]
        try:
            for p in extract_problems(batch):
                save_problem(p)
                report["problems"] += 1
        except llm.LLMError as e:
            report["errors"].append(f"extract: {e}")
            continue
        db.conn().executemany("UPDATE signals SET processed=1 WHERE id=?", [(s["id"],) for s in batch])
        db.conn().commit()
        report["signals"] += len(batch)

    todo = db.q("SELECT * FROM problems WHERE has_idea=0 AND evidence_count>=? ORDER BY evidence_count DESC, updated_at DESC LIMIT ?",
                (Config.MIN_EVIDENCE, Config.MAX_IDEAS_PER_RUN))
    for p in todo:
        try:
            idea = generate_idea(p, evidence_for(p["id"]))
            if idea:
                insert_idea(idea, p["id"])
                report["ideas"] += 1
            db.x("UPDATE problems SET has_idea=1 WHERE id=?", (p["id"],))
        except llm.LLMError as e:
            report["errors"].append(f"idea for problem {p['id']}: {e}")
    if report["ideas"] and not Config.AUTO_APPROVE:
        mailer.notify_waiting()
    log.info("engine run: %s", report)
    return report
