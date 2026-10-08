"""Sends plain emails through any SMTP server (Gmail, Outlook, your college mail...). Settings are in .env."""
import logging
import smtplib
import threading
from email.message import EmailMessage

from . import db
from .config import Config

log = logging.getLogger(__name__)


KEYS = ("host", "port", "user", "password", "from", "tls")


def conf():
    """Email settings: saved on the admin page first, then .env."""
    saved = {r["key"][5:]: r["value"] for r in db.q("SELECT key,value FROM settings WHERE key LIKE 'smtp_%'")}
    if saved.get("host"):
        try:
            port = int(saved.get("port") or 587)
        except ValueError:
            port = 587
        return {"host": saved["host"], "port": port, "user": saved.get("user", ""), "password": saved.get("password", ""),
                "from": saved.get("from") or saved.get("user", ""), "tls": saved.get("tls", "1") == "1", "source": "admin page"}
    return {"host": Config.SMTP_HOST, "port": Config.SMTP_PORT, "user": Config.SMTP_USER, "password": Config.SMTP_PASSWORD,
            "from": Config.SMTP_FROM or Config.SMTP_USER, "tls": Config.SMTP_TLS, "source": ".env"}


def configured():
    c = conf()
    return bool(c["host"] and c["from"])


def send(to, subject, text):
    """Send one email. Raises RuntimeError with a plain message if it cannot be sent."""
    c = conf()
    if not (c["host"] and c["from"]):
        raise RuntimeError("Email is not set up yet. Fill in Email settings on this page.")
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = c["from"], to, subject
    msg.set_content(text)
    try:
        if c["port"] == 465:
            srv = smtplib.SMTP_SSL(c["host"], c["port"], timeout=15)
        else:
            srv = smtplib.SMTP(c["host"], c["port"], timeout=15)
            srv.ehlo()
            if c["tls"]:
                srv.starttls()
                srv.ehlo()
        with srv:
            if c["user"]:
                srv.login(c["user"], c["password"])
            srv.send_message(msg)
    except smtplib.SMTPAuthenticationError as e:
        raise RuntimeError("The email server refused the login. For Gmail, use a 16-letter app password, "
                           "not your normal password.") from e
    except (smtplib.SMTPException, OSError) as e:
        raise RuntimeError(f"Could not send the email: {e}") from e


def invite_text(name, code):
    link = Config.PUBLIC_URL.rstrip("/") + "/review"
    return (f"Hello {name},\n\n"
            "You have been added as a reviewer on Idea Bank. You read new business ideas and decide which ones go on the website. "
            "Only ideas you approve are shown.\n\n"
            f"1. Open: {link}\n"
            f"2. Sign in with this code: {code}\n\n"
            "Keep the code private. If you lose it, ask the admin for a new one.\n\n"
            "Idea Bank")


def send_invite(name, email, code):
    send(email, "You are a reviewer on Idea Bank", invite_text(name, code))


def notify_waiting():
    """Tell active reviewers that ideas are waiting. Runs in the background and never raises."""
    def job():
        try:
            if not configured():
                return
            n = db.q("SELECT COUNT(*) n FROM ideas WHERE status='pending'", one=True)["n"]
            if not n:
                return
            link = Config.PUBLIC_URL.rstrip("/") + "/review"
            for r in db.q("SELECT name,email FROM reviewers WHERE active=1 AND email!=''"):
                send(r["email"], f"{n} idea{'s' if n != 1 else ''} waiting for your review",
                     f"Hello {r['name']},\n\n{n} new idea{'s are' if n != 1 else ' is'} waiting for a decision.\n"
                     f"Open {link} to read and approve or reject.\n\nIdea Bank")
        except Exception:
            log.exception("could not notify reviewers")
        finally:
            db.close()
    threading.Thread(target=job, daemon=True, name="notify-reviewers").start()
