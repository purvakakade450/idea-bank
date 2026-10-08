"""Loads the starter ideas (and researched ideas with proof links). Safe to run on every start:
an idea is only added if no seed idea with the same title exists."""
import json
import os

from . import db, engine
from .domains import GATES, clean_idea

HERE = os.path.dirname(__file__)
FILES = ("seed_ideas.json", "seed_research.json")


def _link_evidence(problem, evidence):
    """Store the proof links as signals tied to one problem, so the idea page shows them."""
    pid = db.x("INSERT INTO problems(statement,who,why_now,sector,fields,evidence_count,has_idea,created_at,updated_at) "
               "VALUES(?,?,?,?,?,?,1,?,?)",
               (problem["problem"], "", "", problem["sector"], db.dumps(list(problem["roles"])), 0, db.now(), db.now()))
    n = 0
    for e in evidence:
        db.conn().execute(
            "INSERT OR IGNORE INTO signals(source,title,summary,url,published_at,fetched_at,processed,meta) VALUES(?,?,?,?,?,?,1,?)",
            (e.get("source", "research"), e["title"][:300], "", e["url"][:1000], None, db.now(), "{}"))
        row = db.q("SELECT id FROM signals WHERE url=?", (e["url"],), one=True)
        if row:
            n += db.conn().execute("INSERT OR IGNORE INTO problem_signals(problem_id,signal_id) VALUES(?,?)",
                                   (pid, row["id"])).rowcount
    db.conn().commit()
    db.x("UPDATE problems SET evidence_count=? WHERE id=?", (n, pid))
    return pid


def run():
    have = {r["title"] for r in db.q("SELECT title FROM ideas WHERE origin='seed'")}
    added = 0
    for name in FILES:
        path = os.path.join(HERE, name)
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as f:
            items = json.load(f)
        for it in items:
            evidence = it.get("evidence") or []
            it["gates"] = {k: {"pass": True, "why": "Starter example"} for k in GATES}
            idea = clean_idea(it)
            if not idea or idea["title"] in have:
                continue
            pid = _link_evidence(idea, evidence) if evidence else None
            engine.insert_idea(idea, pid, origin="seed", force_status="approved")
            have.add(idea["title"])
            added += 1
    return added
