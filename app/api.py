"""REST API."""
import hashlib
import hmac
import re
import secrets
import threading
import time
from collections import defaultdict, deque
from functools import wraps

from flask import Blueprint, abort, current_app, g, jsonify, request
from itsdangerous import BadSignature, URLSafeTimedSerializer

from . import db, engine, ingest, llm, mailer
from .config import Config
from .domains import BUDGET, FIELDS, PRODUCT, SETTING, total
from .matching import fit, team_hours, team_months
from .sources import ALL

bp = Blueprint("api", __name__, url_prefix="/api")

# ------------------------------------------------------------------ helpers
_hits = defaultdict(deque)
_lock = threading.Lock()


def rate_limit(per_hour):
    def deco(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            ip = request.headers.get("X-Forwarded-For", request.remote_addr or "?").split(",")[0].strip()
            now = time.time()
            with _lock:
                q = _hits[(fn.__name__, ip)]
                while q and q[0] < now - 3600:
                    q.popleft()
                if len(q) >= per_hour:
                    return jsonify(error="Too many requests. Try again later."), 429
                q.append(now)
            return fn(*a, **kw)
        return wrapper
    return deco


def _sessions():
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt="idea-bank-admin")


def admin_required(fn):
    """Accepts a sign-in session (from /admin/login) or, for scripts, the raw ADMIN_TOKEN."""
    @wraps(fn)
    def wrapper(*a, **kw):
        token = request.headers.get("X-Admin-Token", "")
        ok = bool(Config.ADMIN_TOKEN) and hmac.compare_digest(token, Config.ADMIN_TOKEN)
        if not ok and token:
            try:
                ok = _sessions().loads(token, max_age=Config.ADMIN_SESSION_HOURS * 3600).get("admin") is True
            except BadSignature:
                ok = False
        if not ok:
            return jsonify(error="Please sign in as admin."), 401
        return fn(*a, **kw)
    return wrapper


@bp.post("/admin/login")
@rate_limit(20)
def admin_login():
    b = body()
    user, pw = str(b.get("username") or ""), str(b.get("password") or "")
    if not Config.ADMIN_PASSWORD:
        return jsonify(error="No admin password is set. Add ADMIN_PASSWORD to .env and restart."), 503
    good = hmac.compare_digest(user.strip().lower(), Config.ADMIN_USERNAME.strip().lower()) & \
        hmac.compare_digest(pw, Config.ADMIN_PASSWORD)
    if not good:
        return jsonify(error="Wrong username or password."), 401
    return jsonify(token=_sessions().dumps({"admin": True}), hours=Config.ADMIN_SESSION_HOURS)


def _hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def reviewer_required(fn):
    """A reviewer is a person the admin has given an access code to, so they can finalize ideas."""
    @wraps(fn)
    def wrapper(*a, **kw):
        token = request.headers.get("X-Reviewer-Token", "").strip()
        r = db.q("SELECT id,name FROM reviewers WHERE token_hash=? AND active=1", (_hash(token),), one=True) if token else None
        if not r:
            return jsonify(error="Reviewer code missing, wrong, or switched off."), 401
        g.reviewer = r
        return fn(*a, **kw)
    return wrapper


def body():
    return request.get_json(silent=True) or {}


def s(v, n):
    return str(v or "").strip()[:n]


def idea_out(r, full=False):
    d = {k: r[k] for k in ("id", "title", "sector", "problem", "solution", "product", "budget", "setting",
                           "roles", "hours", "months", "scores", "total", "status", "origin", "created_at")}
    d["model"] = r.get("model") or {}
    d["checks"] = r.get("checks") or {}
    if full:
        d["gates"] = r.get("gates") or {}
        d["domain_metrics"] = r.get("domain_metrics") or {}
        d["evidence"] = engine.evidence_for(r["problem_id"]) if r.get("problem_id") else []
        d["reviewed_by"] = r.get("reviewed_by") or ""
        d["reviewed_at"] = r.get("reviewed_at")
        d["review_note"] = r.get("review_note") or ""
    return d


def get_idea(idea_id, allow_any=False):
    r = db.q("SELECT * FROM ideas WHERE id=?", (idea_id,), one=True)
    if not r or (not allow_any and r["status"] != "approved"):
        abort(404)
    return r


def load_team(code):
    t = db.q("SELECT * FROM teams WHERE code=?", (s(code, 12).upper(),), one=True)
    if not t:
        abort(404)
    t["members"] = db.q("SELECT id,name,field,skills,hours,months FROM members WHERE team_id=? ORDER BY id", (t["id"],))
    return t


def team_out(t):
    return {"code": t["code"], "name": t["name"], "market": t["interest"], "product": t.get("product") or "mix",
            "budget": t.get("budget") or "unsure", "setting": t.get("setting") or "any", "city": t.get("city") or "",
            "members": [{k: m[k] for k in ("id", "name", "field", "skills", "hours", "months")} for m in t["members"]],
            "hours_per_week": team_hours(t) if t["members"] else 0,
            "months": team_months(t) if t["members"] else 0}


def clean_member(m):
    f = m.get("field")
    if f not in FIELDS:
        abort(400, description="field must be one of " + ", ".join(FIELDS))
    try:
        hours = max(1, min(60, int(m.get("hours", 10))))
        months = max(1, min(24, int(m.get("months", 6))))
    except (TypeError, ValueError):
        abort(400, description="hours and months must be numbers")
    return {"name": s(m.get("name"), 60), "field": f, "skills": s(m.get("skills"), 160), "hours": hours, "months": months}


@bp.errorhandler(400)
@bp.errorhandler(404)
def _err(e):
    return jsonify(error=getattr(e, "description", "Not found")), e.code


# ------------------------------------------------------------------ public
@bp.get("/health")
def health():
    return jsonify(ok=True, ai=llm.available(), sources={n: m.enabled() for n, m in ALL.items()})


@bp.get("/meta")
def meta():
    sectors = [r["sector"] for r in db.q("SELECT DISTINCT sector FROM ideas WHERE status='approved' ORDER BY sector")]
    return jsonify(fields=FIELDS, product=PRODUCT, budget=BUDGET, setting=SETTING, sectors=sectors, ai=llm.available())


@bp.get("/ideas")
def list_ideas():
    sql, args = "SELECT * FROM ideas WHERE status='approved'", []
    if request.args.get("sector"):
        sql += " AND sector=?"; args.append(request.args["sector"])
    if request.args.get("min_score"):
        sql += " AND total>=?"; args.append(int(request.args.get("min_score", 0) or 0))
    if request.args.get("q"):
        sql += " AND (title LIKE ? OR problem LIKE ? OR solution LIKE ?)"; args += [f"%{request.args['q'][:60]}%"] * 3
    sql += " ORDER BY total DESC, created_at DESC LIMIT ?"
    args.append(min(200, int(request.args.get("limit", 100) or 100)))
    rows = db.q(sql, args)
    f = request.args.get("field")
    if f:
        rows = [r for r in rows if f in (r["roles"] or {})]
    return jsonify(ideas=[idea_out(r) for r in rows])


@bp.get("/ideas/<int:idea_id>")
def one_idea(idea_id):
    return jsonify(idea=idea_out(get_idea(idea_id), full=True))


@bp.get("/signals")
def signals():
    rows = db.q("SELECT id,source,title,url,published_at,fetched_at FROM signals ORDER BY fetched_at DESC LIMIT ?",
                (min(100, int(request.args.get("limit", 30) or 30)),))
    return jsonify(signals=rows)


# ------------------------------------------------------------------ teams
def new_code():
    alphabet = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
    while True:
        code = "".join(secrets.choice(alphabet) for _ in range(6))
        if not db.q("SELECT 1 FROM teams WHERE code=?", (code,), one=True):
            return code


def apply_prefs(team_id, b):
    upd = {}
    if "market" in b: upd["interest"] = s(b["market"], 40) or "Any"
    if b.get("product") in PRODUCT: upd["product"] = b["product"]
    if b.get("budget") in list(BUDGET) + ["unsure"]: upd["budget"] = b["budget"]
    if b.get("setting") in SETTING: upd["setting"] = b["setting"]
    if "city" in b: upd["city"] = s(b["city"], 60)
    if "name" in b: upd["name"] = s(b["name"], 60)
    for k, v in upd.items():
        db.x(f"UPDATE teams SET {k}=? WHERE id=?", (v, team_id))  # k comes from the fixed list above


@bp.post("/teams")
def create_team():
    b = body()
    members = [clean_member(m) for m in (b.get("members") or [])][:12]
    code = new_code()
    tid = db.x("INSERT INTO teams(code,created_at) VALUES(?,?)", (code, db.now()))
    apply_prefs(tid, b)
    for m in members:
        db.x("INSERT INTO members(team_id,name,field,skills,hours,months,created_at) VALUES(?,?,?,?,?,?,?)",
             (tid, m["name"], m["field"], m["skills"], m["hours"], m["months"], db.now()))
    return jsonify(team=team_out(load_team(code))), 201


@bp.get("/teams/<code>")
def get_team(code):
    return jsonify(team=team_out(load_team(code)))


@bp.patch("/teams/<code>")
def update_team(code):
    t = load_team(code)
    apply_prefs(t["id"], body())
    return jsonify(team=team_out(load_team(code)))


@bp.post("/teams/<code>/members")
def add_member(code):
    t = load_team(code)
    if len(t["members"]) >= 12:
        abort(400, description="A team can have at most 12 members.")
    m = clean_member(body())
    db.x("INSERT INTO members(team_id,name,field,skills,hours,months,created_at) VALUES(?,?,?,?,?,?,?)",
         (t["id"], m["name"], m["field"], m["skills"], m["hours"], m["months"], db.now()))
    return jsonify(team=team_out(load_team(code))), 201


@bp.get("/teams/<code>/matches")
def matches(code):
    t = load_team(code)
    if not t["members"]:
        return jsonify(matches=[])
    team = {**team_out(t), "members": t["members"]}
    ideas = [idea_out(r) for r in db.q("SELECT * FROM ideas WHERE status='approved'")]
    ranked = sorted(({"idea": i, "fit": fit(i, team)} for i in ideas), key=lambda x: -x["fit"]["match"])
    return jsonify(matches=ranked[:int(request.args.get("limit", 3) or 3)])


@bp.post("/teams/<code>/generate")
@rate_limit(6)
def generate_for_team(code):
    if not llm.available():
        return jsonify(error="AI is not configured on the server (ANTHROPIC_API_KEY)."), 503
    t = load_team(code)
    if not t["members"]:
        abort(400, description="Add team members first.")
    team = {**team_out(t), "members": t["members"]}
    fields = {m["field"] for m in t["members"]}
    probs = db.q("SELECT * FROM problems ORDER BY evidence_count DESC, updated_at DESC LIMIT 60")
    if team["market"] not in ("", "Any"):
        probs = [p for p in probs if p["sector"] == team["market"]] or probs
    probs.sort(key=lambda p: -len(fields & set(p["fields"] or [])))
    if not probs:
        return jsonify(error="No live problems yet. Run data collection first (admin page)."), 409
    created, sent = [], 0
    for p in probs[:3]:
        try:
            idea = engine.generate_idea(p, engine.evidence_for(p["id"]), team)
        except llm.LLMError as e:
            return jsonify(error=f"AI step failed: {e}", ideas=created), 502
        if not idea:
            continue
        ok = all(g.get("pass") for g in idea["gates"].values())
        live = ok and Config.AUTO_APPROVE
        iid = engine.insert_idea(idea, p["id"], origin="team", force_status="approved" if live else ("pending" if ok else "rejected"))
        if live:
            created.append({"idea": idea_out(get_idea(iid)), "fit": fit(idea, team)})
        elif ok:
            sent += 1
    if sent:
        mailer.notify_waiting()
    return jsonify(ideas=created, sent_for_review=sent)


# ------------------------------------------------------------------ admin
_job = {"running": False, "last": None}


def _run_job(app, steps):
    with app.app_context():
        try:
            rep = {}
            if "ingest" in steps:
                rep["ingest"] = ingest.run()
            if "engine" in steps:
                rep["engine"] = engine.run()
            _job["last"] = {"at": db.now(), "report": rep}
        except Exception as e:
            _job["last"] = {"at": db.now(), "error": str(e)}
        finally:
            _job["running"] = False
            db.close()


@bp.get("/admin/overview")
@admin_required
def overview():
    runs = db.q("""SELECT r.* FROM source_runs r JOIN (SELECT source, MAX(id) AS mid FROM source_runs GROUP BY source) m
                   ON r.id=m.mid ORDER BY r.source""")
    counts = {
        "signals": db.q("SELECT COUNT(*) n FROM signals", one=True)["n"],
        "unprocessed": db.q("SELECT COUNT(*) n FROM signals WHERE processed=0", one=True)["n"],
        "problems": db.q("SELECT COUNT(*) n FROM problems", one=True)["n"],
        "ideas": {r["status"]: r["n"] for r in db.q("SELECT status, COUNT(*) n FROM ideas GROUP BY status")},
        "teams": db.q("SELECT COUNT(*) n FROM teams", one=True)["n"],
    }
    return jsonify(sources={n: m.enabled() for n, m in ALL.items()}, last_runs=runs, counts=counts,
                   ai=llm.available(), job=_job, interval_hours=Config.INGEST_INTERVAL_HOURS)


@bp.post("/admin/run")
@admin_required
def run_now():
    from flask import current_app
    steps = body().get("steps") or ["ingest", "engine"]
    if _job["running"]:
        return jsonify(error="A run is already in progress."), 409
    _job["running"] = True
    threading.Thread(target=_run_job, args=(current_app._get_current_object(), steps), daemon=True).start()
    return jsonify(started=steps), 202


@bp.get("/admin/ideas")
@admin_required
def admin_ideas():
    st = request.args.get("status", "pending")
    rows = db.q("SELECT * FROM ideas WHERE status=? ORDER BY created_at DESC LIMIT 100", (st,))
    return jsonify(ideas=[idea_out(r, full=True) for r in rows])


@bp.post("/admin/ideas/<int:idea_id>/status")
@admin_required
def set_status(idea_id):
    st = body().get("status")
    if st not in ("approved", "rejected", "pending"):
        abort(400, description="status must be approved, rejected or pending")
    get_idea(idea_id, allow_any=True)
    db.x("UPDATE ideas SET status=?, reviewed_by='Admin', reviewed_at=? WHERE id=?", (st, db.now(), idea_id))
    return jsonify(ok=True, id=idea_id, status=st)


# ------------------------------------------------------------------ reviewers (managed by the admin)
@bp.get("/admin/reviewers")
@admin_required
def list_reviewers():
    rows = db.q("""SELECT r.id, r.name, r.email, r.active, r.created_at,
                   (SELECT COUNT(*) FROM ideas i WHERE i.reviewed_by=r.name AND i.status='approved') AS approved,
                   (SELECT COUNT(*) FROM ideas i WHERE i.reviewed_by=r.name AND i.status='rejected') AS rejected
                   FROM reviewers r ORDER BY r.id""")
    return jsonify(reviewers=rows)


def _valid_email(e):
    return bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", e)) and len(e) <= 120


def _invite(rid, name, email):
    """Make a fresh code for a reviewer and email it. The code is shown to the admin only if the email fails."""
    token = "rv-" + secrets.token_urlsafe(18)
    db.x("UPDATE reviewers SET token_hash=? WHERE id=?", (_hash(token), rid))
    try:
        mailer.send_invite(name, email, token)
        return {"id": rid, "name": name, "email": email, "emailed": True}
    except RuntimeError as e:
        return {"id": rid, "name": name, "email": email, "emailed": False, "email_error": str(e), "code": token,
                "subject": "You are a reviewer on Idea Bank", "message": mailer.invite_text(name, token)}


@bp.post("/admin/reviewers")
@admin_required
def add_reviewer():
    b = body()
    name, email = s(b.get("name"), 60), s(b.get("email"), 120).lower()
    if not name:
        abort(400, description="Give the reviewer a name.")
    if not _valid_email(email):
        abort(400, description="Enter the reviewer's email address.")
    if db.q("SELECT 1 FROM reviewers WHERE lower(name)=lower(?) OR email=?", (name, email), one=True):
        abort(400, description="A reviewer with this name or email already exists.")
    rid = db.x("INSERT INTO reviewers(name,email,token_hash,active,created_at) VALUES(?,?,?,1,?)",
               (name, email, _hash(secrets.token_hex(16)), db.now()))
    return jsonify(_invite(rid, name, email)), 201


@bp.post("/admin/reviewers/<int:rid>/new-code")
@admin_required
def new_reviewer_code(rid):
    r = db.q("SELECT id,name,email FROM reviewers WHERE id=?", (rid,), one=True)
    if not r:
        abort(404)
    return jsonify(_invite(r["id"], r["name"], r["email"]))


@bp.get("/admin/email-settings")
@admin_required
def get_email_settings():
    c = mailer.conf()
    return jsonify(host=c["host"], port=c["port"], user=c["user"], sender=c["from"], tls=c["tls"],
                   has_password=bool(c["password"]), configured=mailer.configured(), source=c["source"])


@bp.post("/admin/email-settings")
@admin_required
def save_email_settings():
    b = body()
    host = s(b.get("host"), 120)
    if not host:
        abort(400, description="Enter the mail server, for example smtp.gmail.com.")
    try:
        port = int(b.get("port") or 587)
    except (TypeError, ValueError):
        abort(400, description="Port must be a number such as 587.")
    vals = {"smtp_host": host, "smtp_port": str(port), "smtp_user": s(b.get("user"), 120),
            "smtp_from": s(b.get("sender"), 160), "smtp_tls": "1" if b.get("tls", True) else "0"}
    pw = str(b.get("password") or "").replace(" ", "")  # Google shows app passwords with spaces
    if pw:
        vals["smtp_password"] = pw[:200]
    for k, v in vals.items():
        db.x("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (k, v))
    return jsonify(ok=True)


@bp.post("/admin/email-test")
@admin_required
def email_test():
    to = s(body().get("to"), 120).lower()
    if not _valid_email(to):
        abort(400, description="Enter an email address to send the test to.")
    try:
        mailer.send(to, "Idea Bank test email", "This is a test from Idea Bank. Email sending works.")
    except RuntimeError as e:
        return jsonify(ok=False, error=str(e))
    return jsonify(ok=True)


@bp.post("/admin/reviewers/<int:rid>/active")
@admin_required
def set_reviewer_active(rid):
    on = 1 if body().get("active") else 0
    if not db.q("SELECT 1 FROM reviewers WHERE id=?", (rid,), one=True):
        abort(404)
    db.x("UPDATE reviewers SET active=? WHERE id=?", (on, rid))
    return jsonify(ok=True, id=rid, active=bool(on))


# ------------------------------------------------------------------ reviewers (finalize ideas)
@bp.get("/review/me")
@reviewer_required
def review_me():
    n = db.q("SELECT COUNT(*) n FROM ideas WHERE status='pending'", one=True)["n"]
    return jsonify(name=g.reviewer["name"], waiting=n)


@bp.get("/review/ideas")
@reviewer_required
def review_ideas():
    st = request.args.get("status", "pending")
    if st not in ("pending", "approved", "rejected"):
        abort(400, description="status must be pending, approved or rejected")
    if st == "pending":
        rows = db.q("SELECT * FROM ideas WHERE status='pending' ORDER BY total DESC, created_at DESC LIMIT 100")
    else:
        rows = db.q("SELECT * FROM ideas WHERE status=? AND reviewed_by=? ORDER BY reviewed_at DESC LIMIT 100",
                    (st, g.reviewer["name"]))
    return jsonify(ideas=[idea_out(r, full=True) for r in rows])


@bp.post("/review/ideas/<int:idea_id>/decision")
@reviewer_required
def review_decision(idea_id):
    b = body()
    st = b.get("status")
    if st not in ("approved", "rejected"):
        abort(400, description="status must be approved or rejected")
    r = get_idea(idea_id, allow_any=True)
    if r["status"] != "pending":
        return jsonify(error="This idea was already finalized."), 409
    note = s(b.get("note"), 300)
    db.x("UPDATE ideas SET status=?, reviewed_by=?, reviewed_at=?, review_note=? WHERE id=? AND status='pending'",
         (st, g.reviewer["name"], db.now(), note, idea_id))
    return jsonify(ok=True, id=idea_id, status=st, reviewed_by=g.reviewer["name"])
