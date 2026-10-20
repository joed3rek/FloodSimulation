"""The polite downloader (docs/KNOWLEDGE_BRIEF.md, A2).

- Only sources the registry marks open and checked reachable are fetched; user-supplied documents are
  added by the user (``add``), metadata-only ones never.
- It says who it is (the registry's user agent), follows robots.txt as RFC 9309 has it (2xx: its rules,
  including Crawl-delay, Request-rate and Visit-time; 4xx: no rules; 5xx or no answer: nothing allowed), waits
  between requests to one host, retries with backoff, and resumes a partial download.
- A login, bot-check or error page in place of a document is reported as blocked, never kept, and no other
  host is tried.
- Each source folder ``knowledge/raw/<id>/`` (git-ignored) has a ``fetch.json``: url, final url, file, date,
  HTTP status, sha256, size, content type, the registry's licence note, and the outcome with its reason.
"""

from __future__ import annotations

import hashlib
import json
import logging
import mimetypes
import re
import shutil
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from . import registry
from .registry import Source

log = logging.getLogger(__name__)

MIN_DELAY_S = 2.0            # between two requests to one host, when robots.txt asks for nothing longer
RETRIES = 3
TIMEOUT_S = 60
CHUNK = 1 << 16
SOCRATA_PAGE = 50000
DOC_SUFFIXES = (".pdf", ".xlsx", ".xls", ".zip", ".geojson", ".csv", ".docx")


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


# --------------------------------------------------------------------------- robots.txt (RFC 9309)
@dataclass
class Rules:
    parser: Optional[urllib.robotparser.RobotFileParser]   # None: no rules (allow all)
    allow_all: bool = False
    deny_all: bool = False
    note: str = ""
    visit: Optional[Tuple[int, int]] = None                # (from, to) in minutes of the UTC day

    def allowed(self, ua: str, url: str) -> bool:
        if self.deny_all:
            return False
        if self.allow_all or self.parser is None:
            return True
        return self.parser.can_fetch(ua, url)

    def delay(self, ua: str) -> float:
        d = MIN_DELAY_S
        if self.parser is not None:
            cd = self.parser.crawl_delay(ua)
            if cd:
                d = max(d, float(cd))
            rr = self.parser.request_rate(ua)
            if rr and rr.requests:
                d = max(d, rr.seconds / rr.requests)
        return d

    def visit_ok(self, now: Optional[datetime] = None) -> bool:
        if not self.visit:
            return True
        t = now or datetime.now(timezone.utc)
        m = t.hour * 60 + t.minute
        a, b = self.visit
        return a <= m <= b if a <= b else (m >= a or m <= b)


def _visit_time(text: str) -> Optional[Tuple[int, int]]:
    """``Visit-time: HHMM-HHMM`` (UTC), the first one in the file."""
    m = re.search(r"(?im)^\s*visit-time\s*:\s*(\d{4})\s*-\s*(\d{4})", text)
    if not m:
        return None
    a, b = m.group(1), m.group(2)
    return int(a[:2]) * 60 + int(a[2:]), int(b[:2]) * 60 + int(b[2:])


# --------------------------------------------------------------------------- the fetcher
class Fetcher:
    def __init__(self, ua: str, opener: Optional[Callable] = None, sleep: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.monotonic):
        self.ua = ua
        self._open = opener or urllib.request.urlopen
        self._sleep = sleep
        self._clock = clock
        self._robots: Dict[str, Rules] = {}
        self._last: Dict[str, float] = {}

    # ---------------------------------------------------------------- requests
    def _request(self, url: str, headers: Optional[Dict[str, str]] = None):
        req = urllib.request.Request(url, headers={"User-Agent": self.ua, **(headers or {})})
        return self._open(req, timeout=TIMEOUT_S)

    def _wait(self, host: str, delay: float) -> None:
        last = self._last.get(host)
        if last is not None:
            gap = self._clock() - last
            if gap < delay:
                self._sleep(delay - gap)
        self._last[host] = self._clock()

    def rules(self, url: str) -> Rules:
        u = urllib.parse.urlsplit(url)
        key = f"{u.scheme}://{u.netloc}"
        if key in self._robots:
            return self._robots[key]
        self._wait(u.netloc, MIN_DELAY_S)
        try:
            with self._request(key + "/robots.txt") as r:
                text = r.read(512 * 1024).decode("utf-8", "replace")
            p = urllib.robotparser.RobotFileParser()
            p.parse(text.splitlines())
            rules = Rules(p, note="robots.txt read", visit=_visit_time(text))
        except urllib.error.HTTPError as ex:
            if 400 <= ex.code < 500:   # RFC 9309 2.3.1.3: unavailable, no rules
                rules = Rules(None, allow_all=True, note=f"no robots.txt (HTTP {ex.code}): no rules")
            else:                      # 2.3.1.4: unreachable, nothing allowed
                rules = Rules(None, deny_all=True, note=f"robots.txt unreachable (HTTP {ex.code}): not fetched")
        except Exception as ex:   # network failure: unreachable
            rules = Rules(None, deny_all=True, note=f"robots.txt unreachable ({ex.__class__.__name__}): not fetched")
        self._robots[key] = rules
        return rules

    # ---------------------------------------------------------------- one file
    def fetch(self, url: str, folder: Path) -> Dict[str, Any]:
        """Download ``url`` into ``folder``; returns the fetch.json entry."""
        entry: Dict[str, Any] = {"url": url, "date": _now()}
        rules = self.rules(url)
        entry["robots"] = rules.note
        if not rules.allowed(self.ua, url):
            return {**entry, "outcome": "skipped", "reason": "robots.txt does not allow it"}
        if not rules.visit_ok():
            a, b = rules.visit
            return {**entry, "outcome": "deferred",
                    "reason": f"robots.txt asks for visits between {a // 60:02d}:{a % 60:02d} and {b // 60:02d}:{b % 60:02d} UTC"}
        host = urllib.parse.urlsplit(url).netloc
        delay = rules.delay(self.ua)
        if _socrata(url):
            return self._socrata(url, folder, entry, host, delay)
        folder.mkdir(parents=True, exist_ok=True)
        err = None
        for attempt in range(RETRIES):
            part = folder / (".partial-" + hashlib.sha1(url.encode()).hexdigest()[:12])
            have = part.stat().st_size if part.exists() else 0
            self._wait(host, delay)
            try:
                with self._request(url, {"Range": f"bytes={have}-"} if have else None) as r:
                    status = getattr(r, "status", 200)
                    ctype = r.headers.get("Content-Type", "")
                    final = r.geturl()
                    mode = "ab" if have and status == 206 else "wb"
                    with open(part, mode) as f:
                        shutil.copyfileobj(r, f, CHUNK)
                    name = _filename(final, r.headers, url)
                if _unexpected_page(url, final, ctype):
                    part.unlink(missing_ok=True)
                    return {**entry, "outcome": "blocked", "http_status": status, "final_url": final, "content_type": ctype,
                            "reason": "the server answered with a web page (login, bot check or error page) instead of the document"}
                dest = _unique(folder, name)
                part.replace(dest)
                return {**entry, "outcome": "ok", "http_status": status, "final_url": final, "file": dest.name,
                        "content_type": ctype, "size": dest.stat().st_size, "sha256": _sha256(dest)}
            except urllib.error.HTTPError as ex:
                err = f"HTTP {ex.code}"
                if ex.code == 416:   # the partial copy is already complete or stale: start again
                    part.unlink(missing_ok=True)
                    continue
                if ex.code not in (429, 500, 502, 503, 504):
                    return {**entry, "outcome": "failed", "http_status": ex.code, "reason": err}
            except Exception as ex:   # timeouts, resets: retried (the partial copy is resumed)
                err = f"{ex.__class__.__name__}: {ex}"
            self._sleep(2 ** (attempt + 1))
        return {**entry, "outcome": "failed", "reason": f"{err} after {RETRIES} tries"}

    def _socrata(self, url: str, folder: Path, entry: Dict[str, Any], host: str, delay: float) -> Dict[str, Any]:
        """An open-data (Socrata) GeoJSON resource, read page by page and saved as one FeatureCollection."""
        feats: List[Any] = []
        offset = 0
        sep = "&" if "?" in url else "?"
        while True:
            page = f"{url}{sep}$limit={SOCRATA_PAGE}&$offset={offset}&$order=:id"
            self._wait(host, delay)
            try:
                with self._request(page) as r:
                    doc = json.loads(r.read().decode("utf-8"))
            except urllib.error.HTTPError as ex:
                return {**entry, "outcome": "failed", "http_status": ex.code, "reason": f"HTTP {ex.code} at offset {offset}"}
            except Exception as ex:
                return {**entry, "outcome": "failed", "reason": f"{ex.__class__.__name__} at offset {offset}"}
            got = doc.get("features", [])
            feats += got
            if len(got) < SOCRATA_PAGE:
                break
            offset += SOCRATA_PAGE
        folder.mkdir(parents=True, exist_ok=True)
        dest = folder / Path(urllib.parse.urlsplit(url).path).name
        dest.write_text(json.dumps({"type": "FeatureCollection", "features": feats}), encoding="utf-8")
        return {**entry, "outcome": "ok", "http_status": 200, "final_url": url, "file": dest.name, "features": len(feats),
                "content_type": "application/geo+json", "size": dest.stat().st_size, "sha256": _sha256(dest)}


def _socrata(url: str) -> bool:
    u = urllib.parse.urlsplit(url)
    return u.path.startswith("/resource/") and u.path.endswith(".geojson") and "cityofnewyork.us" in u.netloc


def _unexpected_page(url: str, final: str, ctype: str) -> bool:
    """A document was asked for and a web page came back."""
    want_doc = any(urllib.parse.urlsplit(u).path.lower().endswith(DOC_SUFFIXES) for u in (url, final)) \
        or "/download" in url or "ZyPDF" in url or "serve-file" in url
    return want_doc and "text/html" in ctype.lower()


def _filename(final: str, headers, url: str) -> str:
    cd = headers.get("Content-Disposition", "") or ""
    m = re.search(r"filename\*\s*=\s*[^']*''([^;]+)", cd) or re.search(r'filename\s*=\s*"?([^";]+)"?', cd)
    if m:
        name = urllib.parse.unquote(m.group(1)).strip()
    else:
        q = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
        name = (q.get("Dockey") or [""])[0] or Path(urllib.parse.unquote(urllib.parse.urlsplit(final).path)).name or "index"
    name = re.sub(r"[^\w.\-() ]+", "_", name).strip(" .") or "file"
    if not Path(name).suffix:
        ext = mimetypes.guess_extension((headers.get("Content-Type", "") or "").split(";")[0].strip()) or ""
        name += ".html" if ext in (".htm", "") and "html" in (headers.get("Content-Type", "") or "") else ext
    return name


def _unique(folder: Path, name: str) -> Path:
    p = folder / name
    k = 2
    while p.exists():
        p = folder / f"{Path(name).stem}_{k}{Path(name).suffix}"
        k += 1
    return p


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


# --------------------------------------------------------------------------- per source
def _record(s: Source, base: Path) -> Dict[str, Any]:
    p = s.raw_dir(base) / "fetch.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {"source": s.id, "title": s.title, "licence_note": s.licence_note, "entries": []}


def _save(s: Source, base: Path, rec: Dict[str, Any]) -> None:
    d = s.raw_dir(base)
    d.mkdir(parents=True, exist_ok=True)
    rec["licence_note"] = s.licence_note
    (d / "fetch.json").write_text(json.dumps(rec, indent=2, ensure_ascii=False), encoding="utf-8")


def fetch_source(s: Source, fetcher: Fetcher, base: Optional[Path] = None, force: bool = False) -> Dict[str, Any]:
    """Fetch a source's files (those not fetched yet, or all with ``force``); returns its fetch.json."""
    base = base or registry.root()
    if not s.fetchable:
        raise ValueError(f"{s.id} is {s.access} ({s.status}): the downloader does not fetch it"
                         + (" (add a copy with `spongepark knowledge add`)" if s.access == "user-supplied" else "") + ".")
    rec = _record(s, base)
    others = [e for e in rec["entries"] if e.get("url") not in s.files]   # user-supplied copies are kept
    old = {e["url"]: e for e in rec["entries"] if e.get("url") in s.files}
    new: Dict[str, Dict[str, Any]] = {}
    for url in s.files:
        e = old.get(url)
        if e and e.get("outcome") == "ok" and (s.raw_dir(base) / e.get("file", "")).is_file() and not force:
            new[url] = e
            continue
        new[url] = fetcher.fetch(url, s.raw_dir(base))
        log.info("%s: %s %s%s", s.id, new[url]["outcome"], url, f" ({new[url].get('reason')})" if new[url].get("reason") else "")
        rec["entries"] = others + [new.get(u) or old[u] for u in s.files if u in new or u in old]
        _save(s, base, rec)   # after every file, so an interrupted run keeps what it has
    rec["entries"] = others + [new[u] for u in s.files]
    _save(s, base, rec)
    return rec


def add(source_id: str, file: Path, base: Optional[Path] = None) -> Dict[str, Any]:
    """Register a copy the user supplies (a paid or blocked document) for a source."""
    base = base or registry.root()
    s = next((x for x in registry.sources(base / "sources.yaml") if x.id == source_id), None)
    if s is None:
        raise ValueError(f"no source '{source_id}' in sources.yaml.")
    if s.access == "metadata-only":
        raise ValueError(f"{s.id} is metadata-only: no copy is kept.")
    file = Path(file)
    if not file.is_file():
        raise ValueError(f"{file} is not a file.")
    d = s.raw_dir(base)
    d.mkdir(parents=True, exist_ok=True)
    dest = _unique(d, file.name)
    shutil.copy2(file, dest)
    rec = _record(s, base)
    rec["entries"].append({"url": None, "date": _now(), "outcome": "ok", "method": "user-supplied", "file": dest.name,
                           "original_path": str(file), "size": dest.stat().st_size, "sha256": _sha256(dest)})
    _save(s, base, rec)
    return rec


def status(base: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Each source: fetched, partly fetched, failed (with reasons), not fetched, user copy needed or added."""
    base = base or registry.root()
    rows = []
    for s in registry.sources(base / "sources.yaml"):
        rec = _record(s, base) if (s.raw_dir(base) / "fetch.json").exists() else {"entries": []}
        ok = [e for e in rec["entries"] if e.get("outcome") == "ok" and (s.raw_dir(base) / e.get("file", "")).is_file()]
        bad = [e for e in rec["entries"] if e.get("outcome") != "ok" and e.get("url") in s.files]
        if s.access == "metadata-only":
            state = "metadata-only"
        elif s.access == "user-supplied":
            state = "user copy added" if ok else "user copy needed"
        elif not s.fetchable:
            state = "copy added" if ok else f"not fetchable ({s.status})"
        elif len({e['url'] for e in ok if e.get('url')}) >= len(s.files):
            state = "fetched"
        elif ok:
            state = "partly fetched"
        elif bad:
            state = "failed"
        else:
            state = "not fetched"
        rows.append({"id": s.id, "access": s.access, "registry_status": s.status, "state": state,
                     "files": len(ok), "of": len(s.files),
                     "size_mb": round(sum(e.get("size", 0) for e in ok) / 1e6, 1),
                     "problems": [f"{e['url']}: {e.get('outcome')}: {e.get('reason')}" for e in bad]})
    return rows
