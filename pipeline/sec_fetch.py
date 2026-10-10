"""Stage 0: ticker -> CIK -> filing history -> two latest original 10-Ks -> primary HTML.

All SEC traffic goes through `AllowlistClient` (User-Agent, rate limit, host allowlist).
Raw artifacts are cached under data/cache/sec/ and never re-downloaded:
  company_tickers.json          (TTL 7 days)
  submissions/CIK##########.json (TTL 24 hours; new filings appear over time)
  filings/<accession>/<primary document>  (forever: a filed document never changes)
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from pathlib import Path

from pipeline.config import Settings, normalize_ticker
from pipeline.errors import ConfigError, NoTenKFound, SecUnavailable, TickerNotFound
from pipeline.http import AllowlistClient
from pipeline.schema import Company
from pipeline.types import FetchResult, FilingRecord

log = logging.getLogger(__name__)

STAGE_VERSION = "0.1.0"
TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/{name}"
ARCHIVE_URL = "https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_nodash}/{doc}"

TICKERS_TTL = 7 * 24 * 3600
SUBMISSIONS_TTL = 24 * 3600

ACCESSION_RE = re.compile(r"^\d{10}-\d{2}-\d{6}$")
PAGE_NAME_RE = re.compile(r"^CIK\d{10}-submissions-\d{3}\.json$")
DOC_NAME_RE = re.compile(r"^[A-Za-z0-9._\-]{1,128}$")
ORIGINAL_FORMS = ("10-K", "10-K405")
AMENDMENT_FORMS = ("10-K/A", "10-K405/A")
FY_FOCUS_RE = re.compile(
    r'name="dei:DocumentFiscalYearFocus"[^>]*>\s*(?:<[^>]+>\s*)*(\d{4})\s*<', re.IGNORECASE
)


def _fresh(path: Path, ttl: float) -> bool:
    return path.exists() and (time.time() - path.stat().st_mtime) < ttl


def _write_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)


def _get_json(
    client: AllowlistClient, url: str, *, not_found: type[Exception] = TickerNotFound
) -> dict:
    resp = client.get(url)
    if resp.status_code == 404:
        raise not_found(f"SEC returned 404 for {url}")
    if resp.status_code >= 400:
        raise SecUnavailable(f"SEC returned HTTP {resp.status_code} for {url}")
    try:
        return resp.json()
    except ValueError as e:
        raise SecUnavailable(f"SEC returned non-JSON for {url}") from e


def load_company_tickers(client: AllowlistClient, cache_dir: Path) -> dict[str, tuple[str, str]]:
    """ticker -> (10-digit CIK, company title)."""
    path = cache_dir / "sec" / "company_tickers.json"
    if _fresh(path, TICKERS_TTL):
        raw = json.loads(path.read_text(encoding="utf-8"))
    else:
        raw = _get_json(client, TICKERS_URL)
        _write_atomic(path, json.dumps(raw).encode("utf-8"))
    out: dict[str, tuple[str, str]] = {}
    rows = raw.values() if isinstance(raw, dict) else raw
    for row in rows:
        t = str(row.get("ticker", "")).upper()
        if t:
            out[t] = (f"{int(row['cik_str']):010d}", str(row.get("title", "")).strip())
    return out


def resolve_ticker(ticker: str, client: AllowlistClient, cache_dir: Path) -> Company:
    t = normalize_ticker(ticker)
    table = load_company_tickers(client, cache_dir)
    hit = table.get(t)
    if hit is None:
        # SEC lists share classes with '-' (e.g. BRK-B); users often type '.'
        alt = t.replace(".", "-")
        hit = table.get(alt)
    if hit is None:
        raise TickerNotFound(f"Ticker {t} was not found in the SEC company list.")
    cik, title = hit
    return Company(ticker=t, name=title, cik=cik)


def fetch_submissions(client: AllowlistClient, cik: str, cache_dir: Path) -> dict:
    name = f"CIK{cik}.json"
    path = cache_dir / "sec" / "submissions" / name
    if _fresh(path, SUBMISSIONS_TTL):
        return json.loads(path.read_text(encoding="utf-8"))
    data = _get_json(client, SUBMISSIONS_URL.format(name=name))
    _write_atomic(path, json.dumps(data).encode("utf-8"))
    return data


def _iter_filings(client: AllowlistClient, cik: str, cache_dir: Path, subs: dict):
    """Yield filing dicts newest-first across `recent` and the paginated `files`."""

    def rows(block: dict):
        keys = ["accessionNumber", "filingDate", "reportDate", "form", "primaryDocument"]
        n = len(block.get("accessionNumber", []))
        for i in range(n):
            yield {k: (block.get(k) or [None] * n)[i] for k in keys}

    yield from rows(subs.get("filings", {}).get("recent", {}))
    for extra in subs.get("filings", {}).get("files", []):
        name = extra.get("name")
        if not name or not PAGE_NAME_RE.match(name):
            continue
        path = cache_dir / "sec" / "submissions" / name
        if path.exists():
            block = json.loads(path.read_text(encoding="utf-8"))
        else:
            block = _get_json(client, SUBMISSIONS_URL.format(name=name), not_found=SecUnavailable)
            _write_atomic(path, json.dumps(block).encode("utf-8"))
        yield from rows(block)


def _collect_filings(client: AllowlistClient, cik: str, cache_dir: Path, subs: dict) -> list[dict]:
    """Walk the history newest-first and stop as soon as two original 10-Ks with distinct periods
    are in hand (big filers have many paginated history files)."""
    out: list[dict] = []
    periods: set[str] = set()
    for f in _iter_filings(client, cik, cache_dir, subs):
        out.append(f)
        if f.get("form") in ORIGINAL_FORMS and f.get("primaryDocument"):
            periods.add(f.get("reportDate") or f.get("filingDate") or "")
            if len(periods) >= 2:
                break
    return out


def select_two_latest(filings: list[dict]) -> tuple[dict, dict, str, list[str]]:
    """Pick the two most recent original 10-K filings (distinct report periods).

    Amendments (10-K/A) are excluded unless fewer than two originals exist; the choice is
    recorded in the returned note.
    """
    usable = [f for f in filings if f.get("primaryDocument") and f.get("accessionNumber")]
    originals = [f for f in usable if f.get("form") in ORIGINAL_FORMS]
    amendments = [f for f in usable if f.get("form") in AMENDMENT_FORMS]

    def dedupe_by_period(rows: list[dict]) -> list[dict]:
        # newest period first; within a period prefer an original 10-K over a 10-K/A, then the latest filing
        rows = sorted(
            rows,
            key=lambda f: (
                f.get("reportDate") or f["filingDate"],
                f.get("form") in ORIGINAL_FORMS,
                f["filingDate"],
                f["accessionNumber"],
            ),
            reverse=True,
        )
        seen: set[str] = set()
        out = []
        for f in rows:
            period = f.get("reportDate") or f["filingDate"]
            if period in seen:
                continue
            seen.add(period)
            out.append(f)
        return out

    considered = [
        f"{f['form']} {f['accessionNumber']} filed {f['filingDate']}"
        for f in originals + amendments
    ]
    picks = dedupe_by_period(originals)
    note = (
        "two most recent original 10-K filings (one per fiscal period); 10-K/A amendments excluded"
    )
    if len(picks) < 2:
        picks = dedupe_by_period(originals + amendments)
        note = (
            "fewer than two original 10-K filings were available, so 10-K/A amendments were "
            "included in the selection"
        )
    if len(picks) < 2:
        raise NoTenKFound(
            "Fewer than two 10-K filings with a primary document were found for this company."
        )
    new, old = picks[0], picks[1]
    return old, new, note, considered


def download_primary(client: AllowlistClient, cik: str, filing: dict, cache_dir: Path) -> Path:
    acc = filing["accessionNumber"]
    doc = filing["primaryDocument"]
    if not ACCESSION_RE.match(acc):
        raise SecUnavailable(f"Unexpected accession number format from SEC: {acc!r}")
    safe_doc = Path(doc).name  # primary docs are plain file names; never trust path segments
    if not DOC_NAME_RE.match(safe_doc):
        raise SecUnavailable(f"Unexpected primary document name from SEC: {doc!r}")
    path = cache_dir / "sec" / "filings" / acc / safe_doc
    if path.exists():
        return path
    url = ARCHIVE_URL.format(cik_int=int(cik), acc_nodash=acc.replace("-", ""), doc=doc)
    resp = client.get(url)
    if resp.status_code >= 400:
        raise SecUnavailable(f"SEC returned HTTP {resp.status_code} for {url}")
    _write_atomic(path, resp.content)
    return path


def fiscal_year_from_html(html: str, report_date: str) -> tuple[int, str]:
    m = FY_FOCUS_RE.search(html)
    if m:
        return int(m.group(1)), "dei:DocumentFiscalYearFocus"
    return int(report_date[:4]), "period_of_report"


def _record(cik: str, filing: dict, html_path: Path) -> FilingRecord:
    acc = filing["accessionNumber"]
    acc_nodash = acc.replace("-", "")
    data = html_path.read_bytes()
    text = data.decode("utf-8", errors="replace")
    fy, fy_src = fiscal_year_from_html(
        text[:400_000], filing.get("reportDate") or filing["filingDate"]
    )
    return FilingRecord(
        cik=cik,
        accession_number=acc,
        form=filing["form"],
        filing_date=filing["filingDate"],
        report_date=filing.get("reportDate") or filing["filingDate"],
        primary_document=filing["primaryDocument"],
        edgar_url=ARCHIVE_URL.format(
            cik_int=int(cik), acc_nodash=acc_nodash, doc=filing["primaryDocument"]
        ),
        edgar_index_url=ARCHIVE_URL.format(
            cik_int=int(cik), acc_nodash=acc_nodash, doc=f"{acc}-index.htm"
        ),
        is_amendment=filing["form"] in AMENDMENT_FORMS,
        html_path=str(html_path),
        html_sha256=hashlib.sha256(data).hexdigest(),
        fiscal_year=fy,
        fiscal_year_source=fy_src,
    )


def run_stage0(
    ticker: str, settings: Settings, client: AllowlistClient | None = None
) -> FetchResult:
    if not settings.sec_user_agent:
        raise ConfigError(
            "SEC_USER_AGENT is not set. Add it to .env (e.g. 'RiskDiff Jane Doe jane@example.com'). "
            "RiskDiff will not contact sec.gov without a real contact User-Agent."
        )
    own = client is None
    client = client or AllowlistClient(settings.sec_user_agent)
    try:
        cache_dir = settings.cache_dir
        company = resolve_ticker(ticker, client, cache_dir)
        subs = fetch_submissions(client, company.cik, cache_dir)
        name = (subs.get("name") or company.name).strip()
        company = Company(ticker=company.ticker, name=name or company.name, cik=company.cik)
        filings = _collect_filings(client, company.cik, cache_dir, subs)
        old, new, note, considered = select_two_latest(filings)
        old_path = download_primary(client, company.cik, old, cache_dir)
        new_path = download_primary(client, company.cik, new, cache_dir)
        result = FetchResult(
            company=company,
            old=_record(company.cik, old, old_path),
            new=_record(company.cik, new, new_path),
            selection_note=note,
            candidates_considered=considered[:20],
        )
        log.info(
            "stage0 %s: old=%s (%s FY%s) new=%s (%s FY%s) requests=%d",
            company.ticker,
            result.old.accession_number,
            result.old.filing_date,
            result.old.fiscal_year,
            result.new.accession_number,
            result.new.filing_date,
            result.new.fiscal_year,
            client.request_count,
        )
        return result
    finally:
        if own:
            client.__exit__(None, None, None)
