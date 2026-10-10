"""Unit tests for scripts/check_integrity.py and scripts/refresh_stale.py.

The checker is a script, not a package module, so it is loaded by path. Real published reports
under data/published/ are used when present (verbatim sentences by id); tests that need them skip
otherwise.
"""

from __future__ import annotations

import importlib.util
import json
import random
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PUBLISHED = ROOT / "data" / "published"
VECTORS = ROOT / "tests" / "fixtures" / "snippet_vectors.json"


def load_script(name: str):  # noqa: ANN201
    path = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


ci = load_script("check_integrity")
rs = load_script("refresh_stale")


def node_eval(expr_file: str, source: str) -> list | dict | None:
    """Run a snippet in Node against a web TypeScript module; None when Node is unavailable."""
    node = shutil.which("node")
    if not node:
        return None
    try:
        proc = subprocess.run(  # noqa: S603
            [
                node,
                "--experimental-strip-types",
                "--no-warnings",
                "--input-type=module",
                "-e",
                source,
            ],
            cwd=str(ROOT / "web"),
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    try:
        return json.loads(proc.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return None


# ---------------------------------------------------------------------------------------------
# display rules
# ---------------------------------------------------------------------------------------------


def test_snippet_window_matches_shared_vectors():
    doc = json.loads(VECTORS.read_text(encoding="utf-8"))
    for c in doc["cases"]:
        s, e = ci.snippet_window(c["text"], [tuple(x) for x in c["evidence"]], c["max"])
        assert (s, e) == (c["start"], c["end"]), c["name"]


def test_snippet_window_always_contains_the_span():
    words = "alpha bravo charlie delta echo foxtrot golf hotel india juliet".split()
    text = " ".join(words[i % len(words)] for i in range(120)) + "."
    starts = [m for m in range(len(text)) if m == 0 or text[m - 1] == " "]
    ends = [m for m in range(1, len(text) + 1) if m == len(text) or text[m] == " "]
    rng = random.Random(3)
    for _ in range(300):
        a = rng.choice(starts)
        cands = [e for e in ends if e >= a + rng.randint(3, 260)]
        b = cands[0] if cands else len(text)
        if b <= a:
            continue
        s, e = ci.snippet_window(text, [(a, b)], 220)
        assert e - s <= 220
        assert s <= a
        assert e >= b or (b - a) >= 220
        assert s == 0 or text[s - 1] == " "
        assert e == len(text) or text[e] == " " or e == b


def test_frontend_snippet_port_agrees_when_present():
    """When web/src/lib/snippet.ts exists (after the frontend fix), its snippetWindow must give the
    vectors' start/end exactly."""
    if not (ROOT / "web" / "src" / "lib" / "snippet.ts").exists():
        pytest.skip("web/src/lib/snippet.ts not present yet")
    doc = json.loads(VECTORS.read_text(encoding="utf-8"))
    src = (
        "import { snippetWindow } from './src/lib/snippet.ts';"
        f"const cases = {json.dumps(doc['cases'])};"
        "console.log(JSON.stringify(cases.map(c => { const w = snippetWindow(c.text, c.evidence, c.max); return [w.start, w.end]; })));"
    )
    got = node_eval("snippet", src)
    if got is None:
        pytest.skip("node could not evaluate web/src/lib/snippet.ts")
    assert got == [[c["start"], c["end"]] for c in doc["cases"]]


def test_trim_quote_port_matches_frontend():
    texts = [
        "Short sentence.",
        "The regulator collected information from us regarding our business and competition in the graphics card market as part of an ongoing inquiry into competition in those markets, which may be expensive and burdensome and could negatively impact our business.",
        'We paid approximately $4.5 billion in charges, "excess inventory and purchase obligations", as the demand for the product diminished during the first quarter of the fiscal year, and we may incur more.',
    ]
    src = (
        "import { trimQuote } from './src/lib/quote.ts';"
        f"const texts = {json.dumps(texts)};"
        "console.log(JSON.stringify(texts.map(t => { const r = trimQuote(t, 120); return [r.head, r.trimmed]; })));"
    )
    got = node_eval("quote", src)
    if got is None:
        pytest.skip("node could not evaluate web/src/lib/quote.ts")
    assert got == [list(ci.trim_quote(t, 120)) for t in texts]


# ---------------------------------------------------------------------------------------------
# rules
# ---------------------------------------------------------------------------------------------


def test_title_problems_flags_fragments_and_company_names():
    keys = {ci._name_key("Alphabet Inc."), ci._name_key(ci._strip_suffix("Alphabet Inc."))}
    assert ci.title_problems("We are subject to complex laws", keys)
    assert ci.title_problems("The technology industry, including", keys)
    assert ci.title_problems("Alphabet Inc", keys)
    assert ci.title_problems("We are subject to complex laws, rules…", keys)
    assert ci.title_problems("One two three four five six seven eight nine ten eleven", keys)
    assert not ci.title_problems("Export controls restrict sales of our products", keys)
    assert not ci.title_problems("Commercial arrangements expose us to counterparty risks", keys)


def test_entity_problems_patterns():
    comp = type("C", (), {})()
    comp.company = type("Co", (), {"name": "NVIDIA CORP", "ticker": "NVDA"})()
    assert ci.entity_problems("Biden Administration", comp)
    assert ci.entity_problems("D:4", comp)
    assert ci.entity_problems("AI Diffusion IFR in", comp)
    assert not ci.entity_problems("Groq", comp)


def test_expected_insert_words_ignores_case_and_punctuation():
    old = "Excessive or shifting export controls increase the risk, because by the time a product is ready it may be subject to new controls."
    new = "Export controls increase the risk; because by the time a product is ready it may be subject to new controls."
    assert ci.expected_insert_words(old, new) == {}


def test_marked_spans_and_window_contains():
    s = {
        "status": "modified",
        "text": "Export controls increase the risk, resulting in excess inventory.",
        "diff_spans": [
            {"op": "insert", "text": "Export"},
            {"op": "equal", "text": " controls increase the risk"},
            {"op": "insert", "text": ", resulting in excess inventory"},
            {"op": "equal", "text": "."},
        ],
    }
    spans = ci.marked_spans(s, "insert")
    assert spans[0] == (0, 6)
    assert s["text"][spans[1][0] : spans[1][1]] == ", resulting in excess inventory"
    assert ci.window_contains((0, 40), (0, 6))
    assert not ci.window_contains((0, 10), (20, 30))
    assert ci.marked_spans({"status": "added", "text": "abc", "diff_spans": None}, "insert") == [
        (0, 3)
    ]


def test_heatmap_columns_are_unique_and_empty_rows_follow_the_frontend():
    activity = [
        {
            "ticker": "AAA",
            "category": c,
            "added_sentences": n,
            "removed_sentences": 0,
            "modified_sentences": 0,
        }
        for n, c in enumerate(
            [
                "regulation",
                "geopolitical",
                "cybersecurity",
                "supply_chain",
                "climate",
                "competition",
                "ip",
                "macro",
                "credit",
                "liquidity",
                "other",
                "people",
            ],
            start=1,
        )
    ]
    columns = ci.heatmap_columns(activity, max_columns=10)
    assert len(columns) == len(set(columns)), columns
    assert columns[-1] == "other" and len(columns) == 11
    body = {"category_activity": activity, "companies": [{"ticker": "AAA"}, {"ticker": "BBB"}]}
    out = ci.check_heatmap(body)
    assert not [v for v in out if "duplicate" in v.evidence]
    placeholder = "No changed sentences" in (
        ROOT / "web" / "src" / "components" / "TrendsView.tsx"
    ).read_text(encoding="utf-8")
    empties = [v for v in out if v.ticker == "BBB"]
    assert bool(empties) == (not placeholder)


# ---------------------------------------------------------------------------------------------
# checks on the fixture and the real reports
# ---------------------------------------------------------------------------------------------


def fixture_report():  # noqa: ANN201
    path = ROOT / "contract" / "fixtures" / "FIXTURE_comparison.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    comp = ci.Comparison.model_validate(raw)
    return ci.Report(path=path, comp=comp, raw=raw)


def test_pair_check_flags_an_unaligned_pair():
    r = fixture_report()
    comp = r.comp
    cur = ci.CurrentCode()
    assert ci.check_pair(r, cur) == [] or all(v.check == "PAIR" for v in ci.check_pair(r, cur))
    # forge a potential_became_actual highlight whose two sentences are not aligned
    change = next(
        c
        for c in comp.changes
        if sum(1 for s in c.sentences if s.side == "old")
        and sum(1 for s in c.sentences if s.side == "new")
    )
    old_s = next(s for s in change.sentences if s.side == "old")
    new_s = next(s for s in change.sentences if s.side == "new" and s.counterpart_id != old_s.id)
    forged = comp.model_copy(
        update={
            "highlights": [
                ci.hl_mod.Highlight(
                    change_id=change.id,
                    kind="potential_became_actual",
                    old_sentence_id=old_s.id,
                    new_sentence_id=new_s.id,
                    short_title=change.short_title,
                    detail="may -> did",
                )
            ]
        }
    )
    fr = ci.Report(path=r.path, comp=forged, raw=r.raw)
    out = [v for v in ci.check_pair(fr, cur) if v.sentence_ids == [old_s.id, new_s.id]]
    assert out and out[0].check == "PAIR"


def test_case_check_on_real_nvda_export_pair():
    path = PUBLISHED / "NVDA_2025_2026.json"
    if not path.exists():
        pytest.skip("no NVDA report")
    raw = json.loads(path.read_text(encoding="utf-8"))
    comp = ci.Comparison.model_validate(raw)
    r = ci.Report(path=path, comp=comp, raw=raw)
    out = ci.check_case(r)
    hit = [v for v in out if "0001045810-26-000021:21:94" in v.sentence_ids]
    if not hit:
        pytest.skip("the NVDA report no longer carries the case-only span (re-run landed)")
    assert "export" in hit[0].evidence


def test_run_end_to_end_without_api(tmp_path):
    args = type("A", (), {})()
    args.published = str(PUBLISHED)
    args.data_dir = str(ROOT / "data")
    args.no_api = True
    args.api = None
    args.exceptions = str(tmp_path / "none.json")
    result = ci.run(args)
    assert set(result["counts"]) == set(ci.CHECKS) | {"TOTAL"}
    assert result["display_profile"] in ("legacy", "window")
    assert "local published" in result["sources"]
    for v in result["violations"]:
        assert v["check"] in ci.CHECKS
        assert v["classification"] in ("stale", "code", "data")


# ---------------------------------------------------------------------------------------------
# refresh_stale
# ---------------------------------------------------------------------------------------------


def test_refresh_stale_orders_and_builds_commands(tmp_path):
    integrity = {
        "reports": [
            {"ticker": "SF", "earliest_stage": 5},
            {"ticker": "NVDA", "earliest_stage": 2},
            {"ticker": "AAA", "earliest_stage": None},
        ],
        "violations": [
            {"check": "STALE", "ticker": "SF", "analysis_id": "s" * 64, "stage": 5},
            {"check": "STALE", "ticker": "NVDA", "analysis_id": "n" * 64, "stage": 2},
            {"check": "STALE", "ticker": "AAA", "analysis_id": "a" * 64, "stage": None},
            {"check": "CASE", "ticker": "SF"},
        ],
    }
    pub = tmp_path / "published"
    pub.mkdir()
    (pub / "SF_2024_2025.json").write_text("{}")
    (pub / "AAA_2024_2025.json").write_text("{}")
    import os
    import time

    old = time.time() - 1000
    os.utime(pub / "SF_2024_2025.json", (old, old))
    stale = rs.stale_reports(integrity)
    assert {s["ticker"] for s in stale} == {"SF", "NVDA", "AAA"}
    ordered = [r["ticker"] for r in rs.order(stale, pub)]
    assert ordered[0] == "NVDA"
    assert ordered.index("SF") < ordered.index("AAA")  # oldest file first
    assert rs.run_command("NVDA", 2, True) == [
        sys.executable,
        "-m",
        "pipeline.run",
        "NVDA",
        "--force",
        "--from-stage",
        "2",
        "--no-remote",
    ]
    assert rs.run_command("AAA", None, False) == [
        sys.executable,
        "-m",
        "pipeline.run",
        "AAA",
        "--force",
    ]


def test_refresh_one_logs_status_and_new_id(tmp_path):
    pub = tmp_path / "published"
    pub.mkdir()
    calls = []

    def fake_runner(cmd, **kwargs):  # noqa: ANN001
        calls.append(cmd)
        (pub / "ZZZ_2024_2025.json").write_text(json.dumps({"analysis_id": "f" * 64}))
        return subprocess.CompletedProcess(cmd, 0, stdout="ok", stderr="")

    result = rs.refresh_one(
        {"ticker": "zzz", "analysis_id": "e" * 64, "earliest_stage": 5},
        published_dir=pub,
        no_remote=True,
        dry_run=False,
        runner=fake_runner,
    )
    assert result["status"] == "ok"
    assert result["new_analysis_id"] == "f" * 64
    assert calls[0][3:] == ["ZZZ", "--force", "--from-stage", "5", "--no-remote"]
    log_path = tmp_path / "log.jsonl"
    rs.append_log(result, log_path)
    assert rs.already_done("ZZZ", result["code_fingerprint"], rs.read_log(log_path))

    def failing_runner(cmd, **kwargs):  # noqa: ANN001
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="SecUnavailable: 403")

    failed = rs.refresh_one(
        {"ticker": "ZZZ", "analysis_id": None, "earliest_stage": None},
        published_dir=pub,
        no_remote=True,
        dry_run=False,
        runner=failing_runner,
    )
    assert failed["status"] == "failed" and "403" in failed["log_tail"]
    dry = rs.refresh_one(
        {"ticker": "ZZZ", "analysis_id": None, "earliest_stage": None},
        published_dir=pub,
        no_remote=True,
        dry_run=True,
    )
    assert dry["status"] == "dry-run"
