"""A page-indexed text store per downloaded document (docs/KNOWLEDGE_BRIEF.md, A3), for search and for
checking that every extracted value's snippet is really on the page it cites.

PDFs are read page by page (PyMuPDF), web pages section by section (BeautifulSoup: the headings), and
spreadsheets sheet by sheet (openpyxl, the cells' text and formulas). The store is derived from copyrighted
documents, so it lives beside them in ``knowledge/raw/<id>/index/`` (git-ignored) and is never committed.
"""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from . import registry


def norm(text: str) -> str:
    """Text as compared: unicode-folded, dashes and quotes plain, whitespace collapsed, lower case."""
    t = unicodedata.normalize("NFKC", text or "")
    t = t.replace("–", "-").replace("—", "-").replace("−", "-").replace("­", "")
    t = t.replace("‘", "'").replace("’", "'").replace("“", '"').replace("”", '"')
    t = re.sub(r"-\s*\n\s*", "", t)   # words broken across lines
    return re.sub(r"\s+", " ", t).strip().lower()


def _pdf_pages(path: Path) -> Iterator[Dict[str, Any]]:
    import pymupdf

    with pymupdf.open(path) as doc:
        for i, page in enumerate(doc, start=1):
            yield {"page": i, "label": page.get_label() or str(i), "text": page.get_text("text")}


def _html_sections(path: Path) -> Iterator[Dict[str, Any]]:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(path.read_bytes(), "html.parser")
    for t in soup(["script", "style", "nav", "header", "footer"]):
        t.decompose()
    main = soup.find(id="mw-content-text") or soup.find("main") or soup.body or soup
    section, buf, k = "(top)", [], 0
    for el in main.find_all(["h1", "h2", "h3", "h4", "p", "li", "td", "th", "caption", "dt", "dd"]):
        if el.name in ("h1", "h2", "h3", "h4"):
            if buf:
                k += 1
                yield {"page": k, "label": section, "text": "\n".join(buf)}
            section, buf = el.get_text(" ", strip=True), []
        elif not el.find(["p", "li", "td"]):   # leaves only, so nested text is not counted twice
            buf.append(el.get_text(" ", strip=True))
    if buf:
        yield {"page": k + 1, "label": section, "text": "\n".join(buf)}


def _xlsx_sheets(path: Path) -> Iterator[Dict[str, Any]]:
    import openpyxl

    wb = openpyxl.load_workbook(path, data_only=False, read_only=True)
    for i, ws in enumerate(wb.worksheets, start=1):
        rows = []
        for row in ws.iter_rows():
            cells = [f"{c.coordinate}: {c.value}" for c in row if c.value not in (None, "")]
            if cells:
                rows.append(" | ".join(cells))
        yield {"page": i, "label": ws.title, "text": "\n".join(rows)}


def pages_of(path: Path) -> List[Dict[str, Any]]:
    suf = path.suffix.lower()
    if suf == ".pdf":
        return list(_pdf_pages(path))
    if suf in (".html", ".htm"):
        return list(_html_sections(path))
    if suf in (".xlsx", ".xlsm"):
        return list(_xlsx_sheets(path))
    return []


def build(source_id: str, base: Optional[Path] = None, force: bool = False) -> List[Dict[str, Any]]:
    """Index every fetched or added file of a source; returns [{file, pages}]."""
    base = base or registry.root()
    raw = base / "raw" / source_id
    rec = json.loads((raw / "fetch.json").read_text(encoding="utf-8")) if (raw / "fetch.json").exists() else {"entries": []}
    out = []
    (raw / "index").mkdir(parents=True, exist_ok=True)
    for e in rec["entries"]:
        if e.get("outcome") != "ok" or not e.get("file"):
            continue
        f = raw / e["file"]
        idx = raw / "index" / (f.name + ".jsonl")
        if idx.exists() and not force and idx.stat().st_mtime >= f.stat().st_mtime:
            out.append({"file": f.name, "pages": sum(1 for _ in open(idx, encoding="utf-8"))})
            continue
        try:
            pages = pages_of(f)
        except Exception as ex:   # a damaged or unusual file is reported, not fatal
            out.append({"file": f.name, "pages": 0, "error": f"{ex.__class__.__name__}: {ex}"})
            continue
        with open(idx, "w", encoding="utf-8") as w:
            for p in pages:
                w.write(json.dumps({"file": f.name, **p}, ensure_ascii=False) + "\n")
        out.append({"file": f.name, "pages": len(pages)})
    return out


def pages(source_id: str, base: Optional[Path] = None) -> Iterator[Dict[str, Any]]:
    base = base or registry.root()
    for idx in sorted((base / "raw" / source_id / "index").glob("*.jsonl")):
        with open(idx, encoding="utf-8") as r:
            for line in r:
                yield json.loads(line)


def page(source_id: str, file: str, number: int, base: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    return next((p for p in pages(source_id, base) if p["file"] == file and p["page"] == number), None)


def search(source_id: str, pattern: str, base: Optional[Path] = None, width: int = 160, limit: int = 50) -> List[Dict[str, Any]]:
    """Places matching a regular expression (case-insensitive), with some text around each."""
    rx = re.compile(pattern, re.I)
    hits = []
    for p in pages(source_id, base):
        t = re.sub(r"\s+", " ", p["text"])
        for m in rx.finditer(t):
            hits.append({"file": p["file"], "page": p["page"], "label": p["label"],
                         "text": t[max(0, m.start() - width): m.end() + width]})
            if len(hits) >= limit:
                return hits
    return hits


def contains(source_id: str, file: str, number: int, snippet: str, base: Optional[Path] = None) -> bool:
    """Whether the snippet is on that page (compared after norm(); a snippet may run onto the next page)."""
    p = page(source_id, file, number, base)
    if p is None:
        return False
    nxt = page(source_id, file, number + 1, base)
    hay = norm(p["text"] + " " + (nxt["text"] if nxt else ""))
    if norm(snippet) in hay:
        return True
    # a hyphen at a line end is either a broken word or a real hyphen ("non-\npotable"): compare without hyphens
    unhyphen = lambda s: re.sub(r"\s*-\s*", "", s)   # noqa: E731
    return unhyphen(norm(snippet)) in unhyphen(hay)
