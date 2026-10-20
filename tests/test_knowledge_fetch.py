"""The knowledge downloader is polite and honest (docs/KNOWLEDGE_BRIEF.md, A2): it follows robots.txt, waits
between requests, retries, resumes, never keeps a login page as a document, records every fetch with its
sha256 and licence note, and only fetches open sources."""

import hashlib
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from spongepark.engine.knowledge import fetch, registry

DOC = b"%PDF-1.4 " + bytes(range(256)) * 400   # ~100 kB


class Handler(BaseHTTPRequestHandler):
    hits = {}
    robots = "User-agent: *\nDisallow: /private/\nCrawl-delay: 3\n"

    def log_message(self, *a):
        pass

    def do_GET(self):
        Handler.hits[self.path] = Handler.hits.get(self.path, 0) + 1
        if self.path == "/robots.txt":
            return self._send(200, Handler.robots.encode(), "text/plain")
        if self.path in ("/doc.pdf", "/private/doc.pdf"):
            rng = self.headers.get("Range")
            if rng:
                start = int(rng.split("=")[1].split("-")[0])
                self.send_response(206)
                self.send_header("Content-Type", "application/pdf")
                self.send_header("Content-Length", str(len(DOC) - start))
                self.end_headers()
                self.wfile.write(DOC[start:])
                return
            return self._send(200, DOC, "application/pdf")
        if self.path == "/login.pdf":
            return self._send(200, b"<html>please sign in</html>", "text/html")
        if self.path == "/flaky.pdf":
            if Handler.hits[self.path] == 1:
                return self._send(503, b"busy", "text/plain")
            return self._send(200, DOC, "application/pdf")
        return self._send(404, b"no", "text/plain")

    def _send(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture
def server():
    Handler.hits = {}
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


@pytest.fixture
def kb(tmp_path, server):
    (tmp_path / "sources.yaml").write_text(f"""
user_agent: "spongepark-test/1"
sources:
  - id: open_doc
    title: A manual
    publisher: Owner
    access: open
    status: reachable
    licence_note: "free to download"
    files: ["{server}/doc.pdf", "{server}/private/doc.pdf", "{server}/login.pdf", "{server}/flaky.pdf"]
  - id: paid
    title: A paid manual
    publisher: Seller
    access: user-supplied
    status: sold
  - id: paper
    title: A paper
    publisher: Authors
    access: metadata-only
    status: reachable
""", encoding="utf-8")
    return tmp_path


def _fetcher(slept):
    return fetch.Fetcher("spongepark-test/1", sleep=slept.append)


def test_fetches_politely_and_records_everything(kb):
    slept = []
    src = {s.id: s for s in registry.sources(kb / "sources.yaml")}
    rec = fetch.fetch_source(src["open_doc"], _fetcher(slept), base=kb)
    out = {e["url"].rsplit("/", 2)[-2] + "/" + e["url"].rsplit("/", 1)[-1]: e for e in rec["entries"]}
    ok = next(e for k, e in out.items() if k.endswith("/doc.pdf") and "private" not in k)
    assert ok["outcome"] == "ok" and ok["sha256"] == hashlib.sha256(DOC).hexdigest() and ok["size"] == len(DOC)
    assert out["private/doc.pdf"]["outcome"] == "skipped"                     # robots.txt
    assert Handler.hits.get("/private/doc.pdf") is None                        # never requested
    assert out[next(k for k in out if k.endswith("login.pdf"))]["outcome"] == "blocked"   # a sign-in page, not kept
    assert not list((kb / "raw" / "open_doc").glob("login*"))
    assert out[next(k for k in out if k.endswith("flaky.pdf"))]["outcome"] == "ok"        # retried after a 503
    assert any(s >= 3 for s in slept)                                         # Crawl-delay: 3 respected
    saved = json.loads((kb / "raw" / "open_doc" / "fetch.json").read_text(encoding="utf-8"))
    assert saved["licence_note"] == "free to download" and len(saved["entries"]) == 4
    # a second run fetches nothing already fetched
    before = dict(Handler.hits)
    fetch.fetch_source(src["open_doc"], _fetcher([]), base=kb)
    assert Handler.hits["/doc.pdf"] == before["/doc.pdf"]


def test_resumes_a_partial_download(kb, server):
    folder = kb / "raw" / "open_doc"
    folder.mkdir(parents=True)
    url = f"{server}/doc.pdf"
    part = folder / (".partial-" + hashlib.sha1(url.encode()).hexdigest()[:12])
    part.write_bytes(DOC[:30000])
    e = fetch.Fetcher("spongepark-test/1", sleep=lambda s: None).fetch(url, folder)
    assert e["outcome"] == "ok" and e["http_status"] == 206 and e["sha256"] == hashlib.sha256(DOC).hexdigest()


def test_robots_rules_rfc9309():
    assert fetch.Rules(None, allow_all=True).allowed("ua", "http://x/private/a")   # 4xx: no rules
    assert not fetch.Rules(None, deny_all=True).allowed("ua", "http://x/a")        # unreachable: nothing
    assert fetch._visit_time("User-agent: *\nVisit-time: 0100-1045\n") == (60, 645)
    from datetime import datetime, timezone

    night = fetch.Rules(None, visit=(60, 645))
    assert night.visit_ok(datetime(2026, 10, 20, 9, 0, tzinfo=timezone.utc))
    assert not night.visit_ok(datetime(2026, 10, 20, 15, 0, tzinfo=timezone.utc))


def test_only_open_sources_are_fetched_and_user_copies_are_added(kb, tmp_path):
    src = {s.id: s for s in registry.sources(kb / "sources.yaml")}
    with pytest.raises(ValueError, match="user-supplied"):
        fetch.fetch_source(src["paid"], _fetcher([]), base=kb)
    with pytest.raises(ValueError):
        fetch.fetch_source(src["paper"], _fetcher([]), base=kb)
    copy = tmp_path / "bought.pdf"
    copy.write_bytes(DOC)
    fetch.add("paid", copy, base=kb)
    with pytest.raises(ValueError, match="metadata-only"):
        fetch.add("paper", copy, base=kb)
    st = {r["id"]: r for r in fetch.status(base=kb)}
    assert st["paid"]["state"] == "user copy added" and st["paper"]["state"] == "metadata-only"
    assert st["open_doc"]["state"] == "not fetched"
