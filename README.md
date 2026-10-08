# Idea Bank

A website that finds today's real problems and turns them into business ideas to explore
for mixed student teams (computer, mechanical, electrical, civil, business).

```
Many sources ──► One idea engine ──► Reality check ──► Domain metrics ──► Team fit
(news, trends,    (collects and       (6 tough          (each field's      (chatbot learns
 posts, users)     finds problems)     questions)        own numbers)       skills and time)
                                                                                 │
              Problem statement ──► Business idea ──► Suggestions your team can adapt
```

## What's inside

| Part | Where | What it does |
|---|---|---|
| Website | `static/index.html` | Light/dark site: team chatbot (8 questions), idea bank, idea pages |
| Admin page | `static/admin.html` (open `/admin`) | Source health, "run now", add reviewers, approve or reject AI ideas |
| Reviewer page | `static/review.html` (open `/review`) | Reviewers read each new idea and approve or reject it. Only approved ideas show on the site |
| API | `app/api.py` | REST endpoints (list below) |
| Live data | `app/sources/` | NewsData.io, GDELT, Google Trends RSS, Google News RSS (30 sector searches), Reddit |
| Idea engine | `app/engine.py` | Signals → problems (merged, with evidence) → ideas (rules, reality check, metrics, score) |
| Team fit | `app/matching.py` | Ranks ideas for a team: roles for every member, skills, time, product, budget, market |
| Scheduler | `app/worker.py` | Runs collection and the engine every few hours |
| Storage | `app/db.py` | SQLite (WAL mode), file in `data/` |
| Tests | `tests/` | Run without network or keys (sources and AI are mocked) |

## Quick start (your laptop)

You need Python 3.10 or newer.

```bash
cd idea-bank
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # then open .env and fill in the keys
python run.py
```

Open http://localhost:8000 for the site and http://localhost:8000/admin for the admin page
(use the `ADMIN_TOKEN` from `.env`).

The site works straight away with 30+ researched starter ideas (each with proof links). To get **live** ideas:

1. Put your Claude API key in `ANTHROPIC_API_KEY` (from https://console.anthropic.com).
2. Optionally add a free NewsData.io key in `NEWSDATA_API_KEY`. GDELT and Google Trends need no key.
3. On the admin page, press **Collect data and find ideas now**.
4. Approve the ideas you like in "Ideas waiting for review" (or set `AUTO_APPROVE=true` for demos).

To collect data automatically while using `python run.py`, start it with `RUN_SCHEDULER=true python run.py`,
or run the worker in a second terminal: `python -m app.worker`.

## Reviewers (who finalizes ideas)

New AI ideas stay hidden until a person approves them (keep `AUTO_APPROVE=false`).

1. Open `/admin`, go to **Reviewers**, type a name and press **Add reviewer**.
2. Copy the access code shown once and send it privately. Only a hash is stored, so a lost code cannot be viewed again; add a new reviewer instead.
3. The reviewer opens `/review`, signs in with the code, reads each idea with its proof, and presses **Approve and publish** or **Reject**, with an optional note.
4. Approved ideas go live and show "Finalized by <name>". You can switch a reviewer off at any time.

## Run with Docker (recommended for a server)

```bash
cp .env.example .env     # fill in keys
docker compose up -d --build
```

This starts two services that share one database volume: `web` (the site and API on port 8000)
and `worker` (collects data and runs the engine every `INGEST_INTERVAL_HOURS`).

## API keys and settings (`.env`)

| Setting | Needed? | Notes |
|---|---|---|
| `ANTHROPIC_API_KEY` | For AI | Finds problems and creates ideas. Without it, the site uses starter ideas. |
| `ANTHROPIC_MODEL` | No | Default `claude-sonnet-5-5`. |
| `NEWSDATA_API_KEY` | Optional | Free tier works; adds Indian news by category. |
| `REDDIT_CLIENT_ID` / `SECRET` | Optional | Create a "script" app at reddit.com/prefs/apps. Without it, Reddit may block requests. |
| `ENABLE_*` | No | Turn each source on or off. |
| `INGEST_INTERVAL_HOURS` | No | How often the worker runs (default 4). |
| `MAX_SIGNALS_PER_RUN`, `MAX_IDEAS_PER_RUN` | No | Keep AI costs under control. |
| `MIN_EVIDENCE` | No | Signals a problem needs before it gets an idea. Use 2+ once you have lots of data. |
| `AUTO_APPROVE` | No | `true` publishes ideas that pass all 4 rules without admin review. |
| `ADMIN_TOKEN` | Yes | Long random string for the admin page and admin API. |

## How an idea is judged

1. **Four must-pass rules:** someone will pay, clear way to earn revenue, can start small (under 3 months), real proof.
   Fail any one and the idea is rejected.
2. **Reality check:** six questions: real demand, what people do today, who needs it most, smallest first version,
   real struggle seen, will it matter more later.
3. **Domain metrics:** each field's numbers (for example build time for computer, unit cost for mechanical,
   power saved for electrical, project cost for civil, margin for business).
4. **Score out of 100:** need 25, revenue 25, seed-ready 20, entrepreneurial 15, impact 15. 75+ is a strong score.
5. **Team fit** (per team): every member gets a role, skills covered, time, product type, budget, market, region.

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | Server, AI and source status |
| GET | `/api/meta` | Fields, budgets, markets |
| GET | `/api/ideas?field=&sector=&min_score=&q=` | Live ideas |
| GET | `/api/ideas/<id>` | One idea with evidence links and domain metrics |
| GET | `/api/signals` | Latest collected market signals |
| POST | `/api/teams` | Create a team with members and preferences → team code |
| GET/PATCH | `/api/teams/<code>` | Read or update team preferences |
| POST | `/api/teams/<code>/members` | A teammate adds themselves from their own device |
| GET | `/api/teams/<code>/matches` | Best ideas for the team, with fit details |
| POST | `/api/teams/<code>/generate` | New ideas for this team from live problems (AI) |
| GET | `/api/admin/overview` | Admin: counts and source runs (header `X-Admin-Token`) |
| POST | `/api/admin/run` | Admin: `{steps:["ingest","engine"]}` in the background |
| GET | `/api/admin/ideas?status=pending` | Admin: review queue |
| GET/POST | `/api/admin/reviewers` | Admin: list reviewers, add one (code shown once) |
| POST | `/api/admin/reviewers/<id>/active` | Admin: `{active:true\|false}` |
| GET | `/api/review/ideas?status=pending` | Reviewer (header `X-Reviewer-Token`): ideas to read |
| POST | `/api/review/ideas/<id>/decision` | Reviewer: `{status:"approved"\|"rejected", note?}` |
| POST | `/api/admin/ideas/<id>/status` | Admin: `{status:"approved"\|"rejected"}` |

## Tests

```bash
python -m unittest discover -s tests -v
```

## Good to know

- **Costs:** each engine run makes a few AI calls (about one per 20 signals, plus one per idea). The limits in `.env`
  keep it small. A cheap keyword filter drops obviously irrelevant news before any AI call.
- **Respect sources:** the app stores titles, short summaries and links, never full articles. Check each API's
  terms before going public, and keep request rates low.
- **Scaling up:** SQLite is fine for a college or pilot launch. For many users, move to PostgreSQL and run more
  web workers (the rate limiter is in-memory, so switch it to Redis at the same time).
- **AI ideas are suggestions:** always talk to real customers before building.
