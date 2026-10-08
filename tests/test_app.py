"""Run with:  python -m unittest discover -s tests -v
No network or API key needed: sources and the AI are mocked."""
import json
import os
import tempfile
import unittest
from unittest import mock

os.environ["DATABASE_PATH"] = os.path.join(tempfile.mkdtemp(), "test.db")
os.environ["ADMIN_TOKEN"] = "test-token"
os.environ["ANTHROPIC_API_KEY"] = ""

from app import create_app, db, engine, ingest  # noqa: E402
from app.config import Config  # noqa: E402
from app.domains import clean_idea  # noqa: E402
from app.sources import gdelt, newsdata, trends  # noqa: E402


class FakeResp:
    def __init__(self, data=None, text="", status=200):
        self._data, self.text, self.status_code = data, text, status

    def json(self):
        if self._data is None:
            raise ValueError("no json")
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


TRENDS_XML = """<?xml version="1.0"?><rss xmlns:ht="https://trends.google.com/trending/rss"><channel>
<item><title>onion prices</title><ht:approx_traffic>50000+</ht:approx_traffic>
<ht:news_item><ht:news_item_title>Onion prices jump 40% in Mumbai</ht:news_item_title><ht:news_item_url>https://example.com/onion</ht:news_item_url></ht:news_item>
</item></channel></rss>"""

IDEA_JSON = {
    "title": "Onion price alert app", "sector": "Farming and food", "product": "app", "budget": "low", "setting": "city",
    "problem": "Small restaurants can't plan onion costs.", "solution": "Price alerts and group buying.",
    "roles": {"cs": "Build the app", "biz": "Sign up restaurants"},
    "model": {"customer": "Restaurants", "value": "Steady costs", "revenue": "Subscription", "pricing": "[₹__]/month",
              "costs": "Servers", "channels": "WhatsApp groups"},
    "hours": 20, "months": 3,
    "gates": {k: {"pass": True, "why": "ok"} for k in ("pay", "earn", "small", "proof")},
    "checks": {"demand": "yes", "today": "phone calls", "who": "restaurants", "wedge": "one area", "seen": "news", "future": "rising"},
    "domain_metrics": {"cs": {"build time": "6 weeks"}},
    "scores": {"need": 22, "revenue": 20, "seed": 16, "entre": 14, "impact": 9},
}


class SourceTests(unittest.TestCase):
    def test_trends_parse(self):
        items = trends.parse(TRENDS_XML, "IN", "2026-10-05")
        self.assertEqual(len(items), 1)
        self.assertIn("onion prices", items[0]["title"])
        self.assertIn("Onion prices jump", items[0]["summary"])

    def test_gdelt_fetch(self):
        data = {"articles": [{"title": "Water shortage hits Pune", "url": "https://e.com/w", "seendate": "20261005", "domain": "e.com"}]}
        with mock.patch("app.sources.gdelt.requests.get", return_value=FakeResp(data)):
            items = gdelt.fetch()
        self.assertEqual(items[0]["source"], "gdelt")

    def test_newsdata_fetch(self):
        data = {"status": "success", "results": [{"title": "EV chargers scarce in small towns", "link": "https://e.com/ev", "description": "d"}]}
        with mock.patch.object(Config, "NEWSDATA_API_KEY", "k"), \
             mock.patch("app.sources.newsdata.requests.get", return_value=FakeResp(data)):
            self.assertEqual(newsdata.fetch()[0]["url"], "https://e.com/ev")



class MiniSMTP:
    """A small local mail server for tests (plain text, AUTH PLAIN). Keeps every message it receives."""
    def __init__(self, password="app-pass"):
        import socket, threading
        self.password, self.messages, self.logins = password, [], []
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(5)
        self.port = self.sock.getsockname()[1]
        threading.Thread(target=self._serve, daemon=True).start()

    def _serve(self):
        while True:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return
            self._session(conn)

    def _session(self, conn):
        import base64
        f = conn.makefile("rwb")
        def say(t): f.write((t + "\r\n").encode()); f.flush()
        say("220 mini ready")
        data, rcpt, authed = None, [], False
        while True:
            line = f.readline()
            if not line:
                break
            cmd = line.decode().strip()
            up = cmd.upper()
            if up.startswith("EHLO"):
                f.write(b"250-mini\r\n250 AUTH PLAIN\r\n"); f.flush()
            elif up.startswith("AUTH PLAIN"):
                _, user, pw = base64.b64decode(cmd.split()[2]).decode().split("\x00")
                self.logins.append((user, pw))
                if pw == self.password:
                    authed = True; say("235 ok")
                else:
                    say("535 5.7.8 bad credentials")
            elif up.startswith("MAIL FROM"):
                say("250 ok")
            elif up.startswith("RCPT TO"):
                rcpt.append(cmd.split(":", 1)[1].strip(" <>")); say("250 ok")
            elif up == "DATA":
                say("354 go")
                lines = []
                while True:
                    ln = f.readline().decode()
                    if ln in (".\r\n", ".\n"):
                        break
                    lines.append(ln)
                self.messages.append({"to": list(rcpt), "text": "".join(lines), "authed": authed})
                say("250 queued")
            elif up == "QUIT":
                say("221 bye"); break
            else:
                say("250 ok")
        conn.close()

    def close(self):
        self.sock.close()


class AppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.c = cls.app.test_client()

    def test_01_seed_and_ideas(self):
        d = self.c.get("/api/ideas").get_json()
        self.assertGreaterEqual(len(d["ideas"]), 30)
        one = self.c.get(f"/api/ideas/{d['ideas'][0]['id']}").get_json()["idea"]
        self.assertIn("model", one)
        self.assertIn("checks", one)

    def test_02_team_flow(self):
        r = self.c.post("/api/teams", json={"market": "Any", "product": "mix", "budget": "mid", "setting": "rural",
                                            "members": [{"field": "cs", "hours": 10, "months": 6},
                                                        {"field": "mech", "hours": 15, "months": 6}]})
        self.assertEqual(r.status_code, 201)
        code = r.get_json()["team"]["code"]
        r = self.c.post(f"/api/teams/{code}/members", json={"field": "elec", "skills": "circuits", "hours": 10, "months": 9})
        self.assertEqual(len(r.get_json()["team"]["members"]), 3)
        m = self.c.get(f"/api/teams/{code}/matches").get_json()["matches"]
        self.assertEqual(len(m), 3)
        self.assertGreaterEqual(m[0]["fit"]["match"], m[-1]["fit"]["match"])
        self.assertEqual(self.c.post(f"/api/ideas/{m[0]['idea']['id']}/pitch").status_code, 404)

    def test_03_validation(self):
        self.assertEqual(self.c.post("/api/teams", json={"members": [{"field": "nope"}]}).status_code, 400)
        self.assertEqual(self.c.get("/api/teams/ZZZZZZ").status_code, 404)
        self.assertEqual(self.c.get("/api/admin/overview").status_code, 401)
        ok = self.c.get("/api/admin/overview", headers={"X-Admin-Token": "test-token"})
        self.assertEqual(ok.status_code, 200)

    def test_04_ingest_and_engine(self):
        def fake_get(url, *a, **kw):
            if "trends.google" in url:
                return FakeResp(text=TRENDS_XML)
            if "gdeltproject" in url:
                return FakeResp({"articles": [{"title": "Onion price hike hurts small eateries", "url": "https://e.com/o2"}]})
            return FakeResp(status=500)

        with self.app.app_context(), \
             mock.patch("app.sources.trends.requests.get", side_effect=fake_get), \
             mock.patch("app.sources.gdelt.requests.get", side_effect=fake_get), \
             mock.patch.object(Config, "ENABLE_REDDIT", False), \
             mock.patch.object(Config, "ENABLE_GNEWS", False):
            rep = ingest.run()
            self.assertTrue(rep["trends"]["ok"])
            self.assertTrue(rep["gdelt"]["ok"])
            # second run adds nothing new (dedupe on URL)
            self.assertEqual(ingest.run()["gdelt"]["added"], 0)

            sigs = db.q("SELECT id FROM signals WHERE processed=0")
            problems = {"problems": [{"statement": "Small restaurants can't plan onion costs", "who": "restaurants",
                                      "why_now": "price hike", "sector": "Farming and food", "fields": ["cs", "biz"],
                                      "signal_ids": [s["id"] for s in sigs]}]}
            replies = [json.dumps(problems), json.dumps(IDEA_JSON)]
            with mock.patch.object(Config, "ANTHROPIC_API_KEY", "x"), \
                 mock.patch.object(Config, "AUTO_APPROVE", True), \
                 mock.patch("app.llm.complete", side_effect=lambda *a, **k: replies.pop(0)):
                rep = engine.run()
            self.assertEqual(rep["ideas"], 1, rep)
            row = db.q("SELECT * FROM ideas WHERE origin='engine'", one=True)
            self.assertEqual(row["status"], "approved")
            self.assertEqual(len(engine.evidence_for(row["problem_id"])), len(sigs))

        d = self.c.get(f"/api/ideas/{row['id']}").get_json()["idea"]
        self.assertTrue(d["evidence"])

    def test_06_reviewers_finalize_ideas(self):
        adm = {"X-Admin-Token": "test-token"}
        self.assertEqual(self.c.post("/api/admin/reviewers", json={"name": "Asha"}).status_code, 401)
        self.assertEqual(self.c.post("/api/admin/reviewers", json={"name": "Asha"}, headers=adm).status_code, 400)  # email needed
        sent = []
        with mock.patch("app.mailer.send", side_effect=lambda to, subj, text: sent.append((to, text))), \
             mock.patch.object(Config, "SMTP_HOST", "smtp.test"), mock.patch.object(Config, "SMTP_FROM", "x@test"):
            r = self.c.post("/api/admin/reviewers", json={"name": "Asha", "email": "asha@example.com"}, headers=adm)
            self.assertEqual(r.status_code, 201)
            self.assertTrue(r.get_json()["emailed"])
            self.assertNotIn("code", r.get_json())  # the code goes only to the reviewer's inbox
            code = sent[0][1].split("with this code: ")[1].split("\n")[0]
            dup = self.c.post("/api/admin/reviewers", json={"name": "Other", "email": "ASHA@example.com"}, headers=adm)
            self.assertEqual(dup.status_code, 400)
        # when email is not set up, the admin gets the code on screen instead
        with mock.patch.object(Config, "SMTP_HOST", ""):
            r2 = self.c.post("/api/admin/reviewers", json={"name": "Ravi", "email": "ravi@example.com"}, headers=adm).get_json()
        self.assertFalse(r2["emailed"])
        self.assertTrue(r2["code"].startswith("rv-"))
        rv = {"X-Reviewer-Token": code}
        self.assertEqual(self.c.get("/api/review/me").status_code, 401)
        self.assertEqual(self.c.get("/api/review/me", headers={"X-Reviewer-Token": "nope"}).status_code, 401)
        self.assertEqual(self.c.get("/api/review/me", headers=rv).get_json()["name"], "Asha")

        # a new engine idea is pending, so it is hidden from the public site
        with self.app.app_context():
            iid = engine.insert_idea(clean_idea(dict(IDEA_JSON, title="Reviewer test idea")), None)
        self.assertEqual(self.c.get(f"/api/ideas/{iid}").status_code, 404)
        pend = self.c.get("/api/review/ideas", headers=rv).get_json()["ideas"]
        self.assertIn(iid, [i["id"] for i in pend])
        bad = self.c.post(f"/api/review/ideas/{iid}/decision", json={"status": "pending"}, headers=rv)
        self.assertEqual(bad.status_code, 400)
        ok = self.c.post(f"/api/review/ideas/{iid}/decision", json={"status": "approved", "note": "Good proof"}, headers=rv)
        self.assertEqual(ok.status_code, 200)
        pub = self.c.get(f"/api/ideas/{iid}").get_json()["idea"]
        self.assertEqual(pub["reviewed_by"], "Asha")
        self.assertEqual(self.c.post(f"/api/review/ideas/{iid}/decision", json={"status": "rejected"}, headers=rv).status_code, 409)

        # switching a reviewer off removes access
        rid = [x for x in self.c.get("/api/admin/reviewers", headers=adm).get_json()["reviewers"] if x["name"] == "Asha"][0]["id"]
        self.c.post(f"/api/admin/reviewers/{rid}/active", json={"active": False}, headers=adm)
        self.assertEqual(self.c.get("/api/review/me", headers=rv).status_code, 401)

    def test_07_admin_login(self):
        with mock.patch.object(Config, "ADMIN_USERNAME", "boss"), mock.patch.object(Config, "ADMIN_PASSWORD", "s3cret-pass"):
            self.assertEqual(self.c.post("/api/admin/login", json={"username": "boss", "password": "wrong"}).status_code, 401)
            self.assertEqual(self.c.post("/api/admin/login", json={"username": "x", "password": "s3cret-pass"}).status_code, 401)
            r = self.c.post("/api/admin/login", json={"username": "Boss", "password": "s3cret-pass"})
            self.assertEqual(r.status_code, 200)
            tok = r.get_json()["token"]
            self.assertEqual(self.c.get("/api/admin/reviewers", headers={"X-Admin-Token": tok}).status_code, 200)
            self.assertEqual(self.c.get("/api/admin/reviewers", headers={"X-Admin-Token": tok + "x"}).status_code, 401)
        with mock.patch.object(Config, "ADMIN_PASSWORD", ""):
            self.assertEqual(self.c.post("/api/admin/login", json={"username": "a", "password": "b"}).status_code, 503)

    def test_08_email_settings_saved_on_admin_page(self):
        adm = {"X-Admin-Token": "test-token"}
        self.assertEqual(self.c.post("/api/admin/email-settings", json={"host": ""}, headers=adm).status_code, 400)
        r = self.c.post("/api/admin/email-settings", headers=adm,
                        json={"host": "smtp.test", "port": "587", "user": "me@test", "password": "abcd efgh", "sender": "Idea Bank <me@test>"})
        self.assertEqual(r.status_code, 200)
        got = self.c.get("/api/admin/email-settings", headers=adm).get_json()
        self.assertTrue(got["configured"])
        self.assertTrue(got["has_password"])
        self.assertNotIn("password", got)
        with self.app.app_context():
            from app import mailer
            self.assertEqual(mailer.conf()["password"], "abcdefgh")
            db.x("DELETE FROM settings")

    def test_09_email_really_sends_through_smtp(self):
        adm = {"X-Admin-Token": "test-token"}
        srv = MiniSMTP(password="app-pass")
        try:
            def save(pw):
                return self.c.post("/api/admin/email-settings", headers=adm, json={
                    "host": "127.0.0.1", "port": srv.port, "user": "me@test.com", "password": pw,
                    "sender": "Idea Bank <me@test.com>", "tls": False})
            # wrong password: the admin sees a plain reason
            self.assertEqual(save("wrong").status_code, 200)
            bad = self.c.post("/api/admin/email-test", json={"to": "x@example.com"}, headers=adm).get_json()
            self.assertFalse(bad["ok"])
            self.assertIn("app password", bad["error"])
            # right password: the test email arrives
            self.assertEqual(save("app-pass").status_code, 200)
            good = self.c.post("/api/admin/email-test", json={"to": "x@example.com"}, headers=adm).get_json()
            self.assertTrue(good["ok"], good)
            self.assertEqual(srv.messages[-1]["to"], ["x@example.com"])
            self.assertTrue(srv.messages[-1]["authed"])
            # adding a reviewer emails the sign-in code, and the code really signs them in
            r = self.c.post("/api/admin/reviewers", json={"name": "Mina", "email": "mina@example.com"}, headers=adm).get_json()
            self.assertTrue(r["emailed"], r)
            self.assertNotIn("code", r)
            mail = srv.messages[-1]
            self.assertEqual(mail["to"], ["mina@example.com"])
            body = mail["text"].replace("=\r\n", "")
            code = body.split("with this code: ")[1].split()[0]
            self.assertEqual(self.c.get("/api/review/me", headers={"X-Reviewer-Token": code}).get_json()["name"], "Mina")
            # new-code emails again and the old code stops working
            self.c.post(f"/api/admin/reviewers/{r['id']}/new-code", headers=adm)
            self.assertEqual(self.c.get("/api/review/me", headers={"X-Reviewer-Token": code}).status_code, 401)
        finally:
            srv.close()
            with self.app.app_context():
                db.x("DELETE FROM settings")

    def test_05_similarity(self):
        self.assertGreater(engine.similar("Small restaurants can't plan onion costs",
                                          "Restaurants cannot plan onion costs"), 0.45)
        self.assertLess(engine.similar("Water shortage in Pune", "EV chargers in small towns"), 0.2)


if __name__ == "__main__":
    unittest.main()
