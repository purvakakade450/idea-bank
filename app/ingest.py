"""Step 1-2 of the flow: pull signals from every enabled source into one store."""
import logging

from . import db
from .sources import ALL

log = logging.getLogger(__name__)


def run(only=None):
    report = {}
    for name, mod in ALL.items():
        if only and name not in only:
            continue
        if not mod.enabled():
            report[name] = {"ok": False, "skipped": True, "error": "disabled or missing API key"}
            continue
        started = db.now()
        try:
            items = mod.fetch()
            added = 0
            for it in items:
                cur = db.conn().execute(
                    "INSERT OR IGNORE INTO signals(source,title,summary,url,published_at,fetched_at,meta) VALUES(?,?,?,?,?,?,?)",
                    (it["source"], it["title"][:300], it.get("summary", "")[:800], it["url"][:1000],
                     it.get("published_at"), db.now(), db.dumps(it.get("meta") or {})),
                )
                added += cur.rowcount
            db.conn().commit()
            db.x("INSERT INTO source_runs(source,started_at,ok,fetched,added) VALUES(?,?,1,?,?)",
                 (name, started, len(items), added))
            report[name] = {"ok": True, "fetched": len(items), "added": added}
            log.info("ingest %s: fetched %d, new %d", name, len(items), added)
        except Exception as e:
            db.x("INSERT INTO source_runs(source,started_at,ok,error) VALUES(?,?,0,?)", (name, started, str(e)[:500]))
            report[name] = {"ok": False, "error": str(e)[:300]}
            log.warning("ingest %s failed: %s", name, e)
    return report
