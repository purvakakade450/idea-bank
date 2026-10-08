"""Background worker: collects live data and runs the idea engine on a schedule.

    python -m app.worker          # loop forever (every INGEST_INTERVAL_HOURS)
    python -m app.worker --once   # one run, e.g. from cron
"""
import logging
import sys
import time

from . import db, engine, ingest, seed
from .config import Config


def once():
    rep = {"ingest": ingest.run(), "engine": engine.run()}
    logging.info("run finished: %s", rep)
    return rep


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    db.init(Config.DATABASE_PATH)
    seed.run()
    if "--once" in sys.argv:
        once()
        return
    while True:
        try:
            once()
        except Exception:
            logging.exception("run failed")
        time.sleep(Config.INGEST_INTERVAL_HOURS * 3600)


if __name__ == "__main__":
    main()
