import logging
import os
import threading
import time

from flask import Flask, send_from_directory

from . import db, seed
from .config import Config

STATIC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")


def create_app(config=Config):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    app = Flask(__name__, static_folder=STATIC, static_url_path="/static")
    app.config.from_object(config)
    app.config["JSON_SORT_KEYS"] = False

    db.init(config.DATABASE_PATH)
    seed.run()

    from .api import bp
    app.register_blueprint(bp)

    @app.teardown_appcontext
    def _close(_exc):
        db.close()

    @app.get("/")
    def home():
        return send_from_directory(STATIC, "index.html")

    for page in ("why", "how", "team", "ideas"):
        app.add_url_rule(f"/{page}", endpoint=f"page_{page}",
                         view_func=lambda page=page: send_from_directory(STATIC, f"{page}.html"))

    @app.get("/favicon.ico")
    def favicon():
        return "", 204

    @app.get("/review")
    def review():
        return send_from_directory(STATIC, "review.html")

    @app.get("/admin")
    def admin():
        return send_from_directory(STATIC, "admin.html")

    @app.after_request
    def headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        return resp

    if os.getenv("RUN_SCHEDULER", "").lower() in ("1", "true", "yes"):
        start_scheduler()
    return app


def start_scheduler():
    """In-process scheduler for single-process setups (python run.py). In production use the worker service."""
    from . import engine, ingest

    def loop():
        while True:
            try:
                ingest.run()
                engine.run()
            except Exception:
                logging.exception("scheduled run failed")
            finally:
                db.close()
            time.sleep(Config.INGEST_INTERVAL_HOURS * 3600)

    threading.Thread(target=loop, daemon=True, name="ideabank-scheduler").start()
