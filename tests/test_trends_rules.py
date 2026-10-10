"""Trend-derivation rules (TRENDS_VERSION 1.2.x) and the Trends/companies serving path, proved on
the real published reports (sentences are loaded from data/published/, never copied by hand).

TOPIC-NEW         a topic counts only when its matched term lies wholly inside inserted text and
                  appears nowhere in last year's text of the risk factor
TOPIC-MEANINGFUL  an essentially unchanged risk factor never contributes a topic
COUNTS            /trends lists exactly the /companies set, in the local and the Databricks paths
"""

from __future__ import annotations

import json
import re
import shutil
from functools import lru_cache
from pathlib import Path

import pytest

from pipeline.schema import Comparison
from pipeline.trends import aggregate, derive
from pipeline.trends.derive import (
    added_spans,
    derive_trend_facts,
    last_year_text,
    term_in,
    term_inserted,
    term_regex,
    topic_mentions,
)
from tests.test_trends import doc_comp, set_sentence_text

ROOT = Path(__file__).resolve().parents[1]
PUBLISHED_DIR = ROOT / "data" / "published"
NVDA = "NVDA_2025_2026.json"
SF = "SF_2024_2025.json"
UNCHANGED = "largely_unchanged"


@lru_cache(maxsize=4)
def report(name: str) -> Comparison:
    return Comparison.model_validate_json((PUBLISHED_DIR / name).read_text(encoding="utf-8"))


@lru_cache(maxsize=4)
def facts_of(name: str):
    return derive_trend_facts(report(name))


def change_of(comp: Comparison, cid: str):
    return next(c for c in comp.changes if c.id == cid)


def sentence_of(comp: Comparison, cid: str, sid: str):
    return next(s for s in change_of(comp, cid).sentences if s.id == sid)


def only_change(comp: Comparison, cid: str, **update) -> Comparison:
    """The report narrowed to one change (optionally with fields replaced), to isolate one rule.
    The sentences stay the verbatim filing text."""
    c = change_of(comp, cid)
    return comp.model_copy(update={"changes": [c.model_copy(update=update)]})


def mentions_in(facts, sid: str) -> list:
    return [m for m in facts.topic_mentions if m.sentence_id == sid]


def occurrences(term: str, text: str) -> list[tuple[int, int]]:
    return [(m.start(), m.end()) for m in re.finditer(term_regex(term), text, re.IGNORECASE)]


# ---------- TOPIC-NEW: only words that were actually inserted ----------


def test_partly_inserted_phrase_is_not_new_nvda_csp_market():
    """NVDA: only "CSP" was inserted ("cloud service provider" was deleted); the noun chunk
    "CSP market" reaches into words that were already there and must not count."""
    comp = report(NVDA)
    cid, sid = "a4156a06454f6dfd", "0001045810-26-000021:21:7"
    c, s = change_of(comp, cid), sentence_of(comp, cid, sid)
    assert c.change_type != UNCHANGED and s.status == "modified"
    spans = added_spans(s)
    assert [s.text[a:b] for a, b in spans] == ["CSP"]
    assert occurrences("CSP market", s.text)  # the phrase is in the sentence...
    assert not term_inserted("CSP market", s.text, spans)  # ...but not inside the insertion
    assert term_inserted("CSP", s.text, spans)
    for m in mentions_in(facts_of(NVDA), sid):
        assert m.topic != "csp market"
        assert "csp market" not in {t.casefold() for t in m.matched_terms}


def test_sentence_without_inserted_words_contributes_nothing_nvda_exceptional_talent():
    """NVDA: a rewritten sentence with deletions only; "exceptional talent" has no inserted word.
    Even with the risk factor treated as meaningfully changed, the containment rule alone drops it."""
    comp = report(NVDA)
    cid, sid = "6ef9abded50fdc62", "0001045810-26-000021:18:1"
    s = sentence_of(comp, cid, sid)
    assert s.status == "modified" and added_spans(s) == []
    assert occurrences("exceptional talent", s.text)
    assert mentions_in(facts_of(NVDA), sid) == []
    forced = only_change(comp, cid, change_type="expanded")
    assert [m for m in topic_mentions(forced) if m.sentence_id == sid] == []


def test_phrase_with_unchanged_words_is_not_new_sf_cybersecurity_insurance():
    """SF: "cybersecurity" was inserted before "insurance", which was already there."""
    comp = report(SF)
    cid, sid = "3b93c57e20a358e4", "0001193125-26-067130:14:22"
    c, s = change_of(comp, cid), sentence_of(comp, cid, sid)
    assert c.change_type != UNCHANGED and s.status == "modified"
    spans = added_spans(s)
    assert "cybersecurity" in [s.text[a:b] for a, b in spans]
    assert occurrences("cybersecurity insurance", s.text)
    assert not term_inserted("cybersecurity insurance", s.text, spans)
    topics = {m.topic for m in mentions_in(facts_of(SF), sid)}
    assert "cybersecurity insurance" not in topics
    assert "policy term" not in topics  # "policy" inserted, "terms" unchanged


@pytest.mark.parametrize("name", [NVDA, SF])
def test_every_mention_is_inserted_new_language_on_a_meaningful_change(name):
    """The integrity checker's TOPIC-NEW and TOPIC-MEANINGFUL rules over every mention."""
    comp, facts = report(name), facts_of(name)
    changes = {c.id: c for c in comp.changes}
    idx = comp.sentence_index
    assert facts.topic_mentions  # the rules still leave real new language
    for m in facts.topic_mentions:
        c = changes[m.change_id]
        assert c.change_type != UNCHANGED
        assert idx[m.sentence_id].text == m.text  # verbatim
        s = next(s for s in c.sentences if s.id == m.sentence_id)
        assert m.added_spans == added_spans(s) and m.added_spans
        old = " ".join(x.text for x in c.sentences if x.side == "old") or (c.old_text or "")
        for term in m.matched_terms:
            assert term_inserted(term, m.text, m.added_spans), (m.sentence_id, term)
            assert not occurrences(term, old), (m.sentence_id, term)
            assert not term_in(term, last_year_text(c))


def test_last_year_text_comes_from_old_sentences_when_old_text_is_absent():
    cid, old_sid = "d434664e80f07fbb", "0000000000-24-000001:0:4"  # an unchanged old sentence

    def no_old_text(d):
        next(c for c in d["changes"] if c["id"] == cid)["old_text"] = None

    facts = derive_trend_facts(doc_comp(no_old_text))
    assert ("lexicon", "Export controls") in {
        (m.source, m.topic) for m in facts.topic_mentions if m.change_id == cid
    }

    def old_sentence_mentions_it(d):
        no_old_text(d)
        set_sentence_text(
            d, old_sid, d["sentence_index"][old_sid]["text"] + " Export restrictions apply."
        )

    comp = doc_comp(old_sentence_mentions_it)
    assert change_of(comp, cid).old_text is None
    assert "Export restrictions" in last_year_text(change_of(comp, cid))
    facts = derive_trend_facts(comp)
    assert "Export controls" not in {m.topic for m in facts.topic_mentions if m.change_id == cid}


def test_entity_counts_only_inside_the_inserted_words():
    """Fixture data: "Ruritania" is inserted into a rewritten sentence; "Westland" is in its
    unchanged words (and last year's text)."""
    cid, sid = "d434664e80f07fbb", "0000000000-25-000001:0:1"

    def entities(d):
        c = next(c for c in d["changes"] if c["id"] == cid)
        c["signals"]["new_entities"] = [
            {"value": v, "detail": None, "old_sentence_ids": [], "new_sentence_ids": [sid]}
            for v in ("Ruritania", "Westland")
        ]

    got = {(m.source, m.topic) for m in derive_trend_facts(doc_comp(entities)).topic_mentions}
    assert ("entity", "Ruritania") in got and ("entity", "Westland") not in got


# ---------- TOPIC-MEANINGFUL: essentially unchanged risk factors never count ----------


def test_essentially_unchanged_risk_factor_contributes_no_topic_nvda_openai():
    """NVDA: a wholly added sentence in an essentially unchanged risk factor. It is new text, but
    the risk factor did not change meaningfully, so it never becomes a trend."""
    comp = report(NVDA)
    cid, sid = "472606c9d458f2e9", "0001045810-26-000021:15:15"
    c, s = change_of(comp, cid), sentence_of(comp, cid, sid)
    assert c.change_type == UNCHANGED and s.status == "added"
    assert "OpenAI" in s.text and "investment and partnership agreement" in s.text
    assert [m for m in facts_of(NVDA).topic_mentions if m.change_id == cid] == []
    # the change type is what excludes it: the same risk factor marked as changed would count
    forced = {m.topic for m in topic_mentions(only_change(comp, cid, change_type="expanded"))}
    assert {"OpenAI", "investment and partnership agreement"} & forced


def test_a_report_with_only_unchanged_risk_factors_yields_no_mentions():
    comp = report(NVDA)
    unchanged = [c for c in comp.changes if c.change_type == UNCHANGED]
    assert unchanged and any(
        s.status in ("added", "modified") for c in unchanged for s in c.sentences
    )
    by = {k: 0 for k in comp.summary.by_change_type} | {UNCHANGED: len(unchanged)}
    only = comp.model_copy(
        update={
            "changes": unchanged,
            "summary": comp.summary.model_copy(
                update={"total_changes": len(unchanged), "by_change_type": by}
            ),
        }
    )
    facts = derive_trend_facts(only)
    assert facts.topic_mentions == []
    body = aggregate.body_from_facts([facts])
    assert body["topics"] == [] and body["companies"][0]["meaningful_changes"] == 0


# ---------- potential -> actual: aligned pairs only ----------


def test_potential_to_actual_keeps_only_aligned_pairs():
    def unaligned(d):
        d["highlights"][3] = (  # replaces the new_named_party one (at most 5 highlights)
            {
                "change_id": "d434664e80f07fbb",
                "kind": "potential_became_actual",
                "old_sentence_id": "0000000000-24-000001:0:3",  # aligned with 25-...:0:4, not 0:1
                "new_sentence_id": "0000000000-25-000001:0:1",
                "short_title": d["changes"][0]["short_title"],
                "detail": None,
            }
        )

    comp = doc_comp(unaligned)
    pairs = {
        (p.old_sentence_id, p.new_sentence_id) for p in derive_trend_facts(comp).potential_to_actual
    }
    assert ("0000000000-24-000001:0:3", "0000000000-25-000001:0:1") not in pairs
    assert ("0000000000-24-000001:0:3", "0000000000-25-000001:0:4") in pairs
    for name in (NVDA, SF):  # the real reports: every kept pair is a rewritten pair of the diff
        sentences = {s.id: s for c in report(name).changes for s in c.sentences}
        for p in facts_of(name).potential_to_actual:
            new = sentences[p.new_sentence_id]
            assert new.status == "modified" and new.counterpart_id == p.old_sentence_id


# ---------- Databricks rows carry the derivation ----------


def test_trend_rows_are_keyed_by_derivation_and_queries_read_only_the_current_one():
    from pipeline.store import tables
    from tests.test_store import settings

    facts = derive_trend_facts(doc_comp())
    assert facts.derivation == derive.derivation_id()
    assert facts.derivation.startswith(f"{derive.TRENDS_VERSION}+")
    for rows, table in (
        (tables.topic_mention_rows(facts), tables.TOPIC_MENTIONS),
        (tables.category_activity_rows(facts), tables.CATEGORY_ACTIVITY),
    ):
        assert rows and all(r["derivation"] == facts.derivation for r in rows)
        assert set(rows[0]) == {n for n, _ in tables.COLUMNS[table]}
        assert "derivation" in tables.KEYS[table]
        assert (table, "derivation", "STRING") in tables.ADDED_COLUMNS
    s = settings()
    for sql in (tables.trends_topics_sql(s), tables.trends_activity_sql(s)):
        assert ".derivation = :derivation" in sql and facts.derivation not in sql
    ddl = dict(tables.ddl(s))
    assert "`derivation` STRING NOT NULL" in ddl[tables.TOPIC_MENTIONS]


# ---------- COUNTS: /trends lists exactly the /companies set ----------


def _app_client(settings, store_factory):
    from fastapi.testclient import TestClient

    from api import main as api_main

    return api_main.create_app(settings, store_factory=store_factory), TestClient


def _ids(cards: list[dict]) -> dict[str, str]:
    return {c["ticker"]: c["analysis_id"] for c in cards}


def _disabled():
    from pipeline.store import StoreDisabled

    raise StoreDisabled("not configured")


def test_a_company_whose_facts_cannot_be_derived_stays_listed_with_a_warning(tmp_path, monkeypatch):
    """Mechanism (a): the local compute used to `continue` past a failed derivation, so the company
    vanished from /trends while /companies listed it."""
    from tests.test_api_store import settings_for

    s = settings_for(tmp_path)
    s.published_dir.mkdir(parents=True)
    for name in (NVDA, SF):
        shutil.copy(PUBLISHED_DIR / name, s.published_dir / name)
    ddir = s.data_dir / "derived"
    ddir.mkdir(parents=True)
    nvda_file = f"{report(NVDA).analysis_id}.trends.json"
    shutil.copy(ROOT / "data" / "derived" / nvda_file, ddir / nvda_file)  # SF must be derived

    def broken(comp, derived_dir, nlp=None):
        raise RuntimeError("simulated derivation failure")

    monkeypatch.setattr(derive, "ensure_facts", broken)
    app, TestClient = _app_client(s, _disabled)
    with TestClient(app) as client:
        companies = client.get("/companies").json()["companies"]
        t = client.get("/trends").json()
    assert (
        _ids(t["companies"])
        == _ids(companies)
        == {
            "NVDA": report(NVDA).analysis_id,
            "SF": report(SF).analysis_id,
        }
    )
    assert t["headline"]["companies"] == 2
    assert len(t["warnings"]) == 1 and t["warnings"][0].startswith("SF:")
    assert "RuntimeError" in t["warnings"][0]
    sf = next(c for c in t["companies"] if c["ticker"] == "SF")
    assert sf["total_changes"] == report(SF).summary.total_changes  # listed, with its change mix
    assert not any("SF" in topic["companies"] for topic in t["topics"])
    assert not any(row["ticker"] == "SF" for row in t["category_activity"])


def _store_world(tmp_path, publish: list[str]):
    """A simulated shared store (the publisher's real MERGEs into TableSim) holding `publish`."""
    from pipeline.store import DatabricksStore
    from pipeline.store.publisher import publish_remote
    from tests.test_store import FakeClient, settings
    from tests.test_store_publish import TableSim
    from tests.test_trends import TrendsStore

    sim = TableSim()
    db = DatabricksStore(settings(), client=FakeClient(sim), sleep=lambda s: None)
    for name in publish:
        publish_remote(
            PUBLISHED_DIR / name, db, published_by="tester", derived_dir=tmp_path / "store-derived"
        )
    return sim, TrendsStore(sim)


def test_local_only_and_remote_only_reports_are_on_both_pages(tmp_path, monkeypatch):
    """Mechanism (b): the Databricks body used to list only the store's rows, while /companies
    merged local files in. NVDA exists only locally (never synced), SF only in the store."""
    from tests.test_api_store import settings_for, wait_for_trends
    from tests.test_store import HOST
    from tests.test_trends import local_body

    monkeypatch.setenv("DATABRICKS_HOST", HOST)
    sim, store = _store_world(tmp_path, [SF])
    s = settings_for(tmp_path)
    s.published_dir.mkdir(parents=True)
    shutil.copy(PUBLISHED_DIR / NVDA, s.published_dir / NVDA)
    shutil.copytree(ROOT / "data" / "derived", s.data_dir / "derived")
    app, TestClient = _app_client(s, lambda: store)
    with TestClient(app) as client:
        t = wait_for_trends(client, lambda t: t["source"] == "databricks")
        companies = client.get("/companies").json()["companies"]
    assert t["source"] == "databricks"
    assert (
        _ids(t["companies"])
        == _ids(companies)
        == {
            "NVDA": report(NVDA).analysis_id,
            "SF": report(SF).analysis_id,
        }
    )
    assert {c["ticker"]: c["source"] for c in companies} == {"NVDA": "local", "SF": "remote"}
    assert t["warnings"] == []
    # SF from the store's rows, NVDA from its local facts: the same body as the local aggregate
    local = local_body()
    for key in ("headline", "topics", "category_activity", "potential_to_actual", "change_mix"):
        assert t[key] == local[key], key
    # only the store's analysis is queried; NVDA's local facts complete phrase counts
    topic_q = next(p for sql, p in store.statements if sql.startswith("WITH m AS"))
    assert json.loads(topic_q["ids"]) == [report(SF).analysis_id]
    assert topic_q["min_companies"] == 1


def test_trends_follow_a_new_local_report_before_the_cache_expires(tmp_path, monkeypatch):
    """A remote body computed for another company set is stale at once (not after 60 s)."""
    from tests.test_api_store import settings_for, wait_for_trends
    from tests.test_store import HOST

    monkeypatch.setenv("DATABRICKS_HOST", HOST)
    _, store = _store_world(tmp_path, [SF])
    s = settings_for(tmp_path)
    s.published_dir.mkdir(parents=True)
    shutil.copytree(ROOT / "data" / "derived", s.data_dir / "derived")
    app, TestClient = _app_client(s, lambda: store)
    with TestClient(app) as client:
        t = wait_for_trends(client, lambda t: t["source"] == "databricks")
        assert [c["ticker"] for c in t["companies"]] == ["SF"]
        shutil.copy(PUBLISHED_DIR / NVDA, s.published_dir / NVDA)  # e.g. a fresh local publish
        companies = client.get("/companies").json()["companies"]
        t = wait_for_trends(client, lambda t: len(t["companies"]) == 2)
    assert _ids(t["companies"]) == _ids(companies) and len(companies) == 2


def test_store_rows_of_another_derivation_are_never_served(tmp_path, monkeypatch):
    """Insert-if-absent MERGEs keep rows written by older code. They sit next to the current
    rows and are ignored; a report that has ONLY old rows is listed with a warning."""
    from tests.test_api_store import settings_for, wait_for_trends
    from tests.test_store import HOST
    from tests.test_trends import local_body

    monkeypatch.setenv("DATABRICKS_HOST", HOST)
    sim, store = _store_world(tmp_path, [NVDA, SF])
    old = "1.1.0+topics1"
    for table in ("topic_mentions", "category_activity"):
        for key, row in list(sim.rows[table].items()):
            stale = {**row, "derivation": old}
            if table == "topic_mentions":
                stale["topic"] = "stale topic from older code"
            sim.rows[table][(*key[:-1], old)] = stale
    s = settings_for(tmp_path)  # nothing local: everything comes from the store
    app, TestClient = _app_client(s, lambda: store)
    with TestClient(app) as client:
        t = wait_for_trends(client, lambda t: t["source"] == "databricks")
    local = local_body()
    for key in ("headline", "topics", "category_activity", "potential_to_actual", "change_mix"):
        assert t[key] == local[key], key
    assert t["warnings"] == []

    # SF's facts exist only under the old derivation (published before the upgrade)
    sf_id = report(SF).analysis_id
    for table in ("topic_mentions", "category_activity"):
        for key in [k for k, r in sim.rows[table].items() if r["analysis_id"] == sf_id]:
            if sim.rows[table][key]["derivation"] != old:
                del sim.rows[table][key]
    s2 = settings_for(tmp_path / "second")
    app2, _ = _app_client(s2, lambda: store)
    with TestClient(app2) as client:
        t = wait_for_trends(client, lambda t: t["source"] == "databricks")
        companies = client.get("/companies").json()["companies"]
    assert (
        _ids(t["companies"])
        == _ids(companies)
        == {
            "NVDA": report(NVDA).analysis_id,
            "SF": sf_id,
        }
    )
    assert len(t["warnings"]) == 1 and t["warnings"][0].startswith("SF:")
    assert derive.derivation_id() in t["warnings"][0]
    assert not any("SF" in topic["companies"] for topic in t["topics"])
    assert not any(row["ticker"] == "SF" for row in t["category_activity"])
    assert "stale topic from older code" not in json.dumps(t)


# ---------- the backfill script ----------


def test_derive_trends_script_continues_past_failures_and_names_them(tmp_path, monkeypatch, capsys):
    import importlib

    script = importlib.import_module("scripts.derive_trends")
    for v in ("DATABRICKS_HOST", "DATABRICKS_TOKEN", "DATABRICKS_WAREHOUSE_ID"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setenv("RISKDIFF_DATA_DIR", str(tmp_path))
    (tmp_path / "published").mkdir()
    for name in (NVDA, SF):
        shutil.copy(PUBLISHED_DIR / name, tmp_path / "published" / name)
    (tmp_path / "published" / "BAD_2024_2025.json").write_text("{}")
    real = script.derive_trend_facts

    def flaky(comp, nlp=None):
        if comp.company.ticker == "NVDA":
            raise RuntimeError("simulated")
        return real(comp, nlp)

    monkeypatch.setattr(script, "derive_trend_facts", flaky)
    assert script.main(["--local-only"]) == 1
    out = capsys.readouterr()
    assert "1 ok, 2 failed" in out.out
    assert "Failed reports:" in out.err
    assert "BAD_2024_2025.json" in out.err and f"{NVDA} [RuntimeError]" in out.err
    derived = {p.name for p in (tmp_path / "derived").glob("*.trends.json")}
    assert derived == {f"{report(SF).analysis_id}.trends.json"}  # SF still derived
