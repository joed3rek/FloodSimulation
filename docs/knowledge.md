# NbS knowledge base

The brief is [KNOWLEDGE_BRIEF.md](KNOWLEDGE_BRIEF.md). This page says how the parts built so far work.

## Folders

| Path | In git | What |
|---|---|---|
| `knowledge/sources.yaml` | yes | The source registry: owner, edition, URLs, access (open / user-supplied / metadata-only), the status found when checked, the licence or terms note, climate, elements, priority. |
| `knowledge/raw/<source>/` | **no** | Downloaded or user-supplied copies, `fetch.json` (url, final url, date, HTTP status, sha256, size, licence note, outcome and reason) and `index/` (the page-indexed text store). Never committed or redistributed. |
| `knowledge/staging/<source>.jsonl` | yes | Extracted values waiting for review: the fact, its units (SI with the original kept), when it applies, and where it is (file, page, section, a verbatim snippet under 15 words). |
| `knowledge/staging/authoring/<source>.py` | yes | How each source's staged rules were written (rerun to regenerate the `.jsonl`). |

## Commands

```
spongepark knowledge status                      # each source: fetched, failed (why), user copy needed ...
spongepark knowledge fetch --all                 # open sources checked reachable; --source <id>; --force
spongepark knowledge add --source <id> --file <path>   # a copy you supply (paid, login-only, blocked)
spongepark knowledge index [--source <id>]       # build the text store (PDF pages, web sections, sheets)
spongepark knowledge search <source> "<regex>"   # find passages
spongepark knowledge check [--source <id>]       # staged rules valid, and every snippet found on its page
```

Extraction needs the optional dependencies: `pip install -e .[knowledge]` (PyMuPDF, pdfplumber,
BeautifulSoup, openpyxl).

## How fetching behaves

- It names itself (the registry's `user_agent`), follows robots.txt as RFC 9309 has it (rules incl. Crawl-delay,
  Request-rate and Visit-time; 4xx = no rules; 5xx or no answer = nothing allowed), waits at least 2 s between
  requests to one host, retries 429/5xx with backoff and resumes partial files.
- A web page served where a document was asked for (login, bot check) is reported as blocked and not kept.
  No other host is tried and the client never disguises itself.
- Only `access: open` sources with `status: reachable` are fetched.

## Extraction

Values are read from the text store by a person or by Claude, written with their page and a verbatim
snippet, and `knowledge check` confirms each snippet is on the cited page (whitespace, dashes, quotes and
line-end hyphens are normalised). Every staged rule starts `unreviewed`; review (K3) approves, edits or
rejects it, and only approved rules will drive the design checks.

## State (2026-10-20)

- K1: 10 sources fetched (about 530 MB). Blocked to automated clients: Minnesota manual (bot check),
  NACTO, Townsville, Urban Nature Atlas, BMP Database summary (WRF answers 403); unreachable: CGWB (TLS),
  NRCS TR-55 (time-out), MOHURD. Paid: CIRIA C753/C768, Melbourne WSUD, MS 2526.
- K2: 219 staged rules from three sources (STEP LID wiki, PUB ABC Waters engineering procedures 2024,
  MSMA 2nd edition) for rain gardens / bioretention, bioswales and swales, detention basins, retention
  (wet) ponds, recharge wells (soakaways, infiltration sumps), infiltration trenches, filter strips, check
  dams and wetlands. Philadelphia's manuals and SWMM Vol. III (LID parameters) are next.
