"""T10/T11: trend facts derived from published reports (lexicon, entities, phrases, activity,
determinism) and the shared aggregation."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from pipeline.schema import Comparison
from pipeline.trends import derive
from pipeline.trends.derive import (
    added_spans,
    change_activity,
    compile_terms,
    derive_after_publish,
    derive_trend_facts,
    ensure_facts,
    facts_json,
    is_stop_entity,
    lexicon_topic_for,
    load_facts,
    load_lexicon,
    normalize_entity,
    own_name_tokens,
    write_facts,
)
from tests.test_store import real_doc

ROOT = Path(__file__).resolve().parents[1]
PUBLISHED = sorted((ROOT / "data" / "published").glob("*_*_*.json"))
EXPORT_CHANGE = "d434664e80f07fbb"  # fixture change whose added sentence names export restrictions


def doc_comp(mutate=None) -> Comparison:
    d = real_doc()
    if mutate:
        mutate(d)
    return Comparison.model_validate(d)


def change(d: dict, cid: str) -> dict:
    return next(c for c in d["changes"] if c["id"] == cid)


def topics_of(facts, cid: str | None = None) -> set[tuple[str, str]]:
    return {(m.source, m.topic) for m in facts.topic_mentions if cid is None or m.change_id == cid}


# ---------- lexicon ----------


def test_terms_match_whole_words_only():
    tariff = compile_terms(["tariff"])
    assert tariff.search("a new tariff on imports") and tariff.search("Tariff-related costs")
    assert not tariff.search("new tariffs on imports")  # plural only when listed
    china = compile_terms(["China"])
    assert china.search("sales to china fell") and china.search("China-based customers")
    assert not china.search("our Chinatown office") and not china.search("Indochina")
    trade_war = compile_terms(["trade war"])
    assert trade_war.search("an escalating trade\n  war") and trade_war.search("a trade-war")
    assert not trade_war.search("trade warrants")
    prc = compile_terms(["People's Republic of China"])
    assert prc.search("the People’s Republic of China")  # curly apostrophe in filings


def test_lexicon_contents():
    version, topics = load_lexicon()
    assert version == 1 and len(topics) >= 30
    by = {t.name: {s.casefold() for s in t.synonyms} for t in topics}
    required = {
        "Tariffs": {
            "tariff",
            "tariffs",
            "trade war",
            "reciprocal tariffs",
            "section 232",
            "section 301",
        },
        "Export controls": {
            "export controls",
            "entity list",
            "export license",
            "export restrictions",
        },
        "AI regulation": {"eu ai act", "ai regulation", "ai act", "state ai laws", "ai governance"},
        "Generative AI": {"generative ai", "large language models", "llm", "foundation models"},
        "Cybersecurity incidents": {
            "ransomware",
            "cyberattacks",
            "data breaches",
            "security incident",
        },
        "Middle East": {"israel", "gaza", "red sea", "houthi"},
        "Data privacy laws": {"gdpr", "ccpa", "privacy laws"},
        "Antitrust": {"antitrust", "competition authority", "samr", "doj investigation"},
        "Taxes": {"pillar two", "global minimum tax"},
    }
    for name, syns in required.items():
        assert syns <= by[name], (name, syns - by[name])
    for name in (
        "Interest rates",
        "Inflation",
        "China",
        "Taiwan",
        "Russia / Ukraine",
        "Supply chain disruption",
        "Climate",
        "Government shutdown",
        "Immigration policy",
        "Energy and power for data centers",
        "Semiconductor supply",
        "Pandemic",
        "Labor",
        "Litigation",
        "Sanctions",
        "Debt and credit markets",
        "Counterparty and credit risk",
        "Foreign exchange",
        "Government contracts",
        "Natural disasters",
    ):
        assert name in by
    every = set().union(*by.values())
    # generic single words that would match boilerplate are deliberately absent
    assert not every & {"duties", "visa", "visas", "supply chain", "risk", "regulation"}
    assert lexicon_topic_for("subject to fiduciary duties") is None
    assert lexicon_topic_for("Visa and Mastercard networks") is None


# ---------- "new this year" ----------


def test_topic_counts_only_when_absent_from_last_year_text():
    facts = derive_trend_facts(doc_comp())
    assert ("lexicon", "Export controls") in topics_of(facts, EXPORT_CHANGE)
    # "Natural disasters" is in a modified sentence but was already in last year's text
    assert ("lexicon", "Natural disasters") not in topics_of(facts, EXPORT_CHANGE)

    def old_mentions_it(d):
        c = change(d, EXPORT_CHANGE)
        c["old_text"] += "\nFIXTURE: Export controls could limit sales."

    facts = derive_trend_facts(doc_comp(old_mentions_it))
    assert ("lexicon", "Export controls") not in topics_of(facts, EXPORT_CHANGE)


def test_mentions_keep_verbatim_text_ids_and_spans():
    comp = doc_comp()
    facts = derive_trend_facts(comp)
    idx = comp.sentence_index
    for m in facts.topic_mentions:
        assert idx[m.sentence_id].text == m.text  # verbatim, never generated
        assert m.status in ("added", "modified") and m.matched_terms
        for a, b in m.added_spans:
            assert 0 <= a < b <= len(m.text)
    exp = next(m for m in facts.topic_mentions if m.topic == "Export controls")
    assert exp.status == "added" and exp.added_spans == [(0, len(exp.text))]
    assert exp.matched_terms == ["export restrictions"]
    # modified sentence: spans are exactly the inserted words
    s = next(s for s in comp.changes[0].sentences if s.status == "modified" and s.side == "new")
    assert [s.text[a:b] for a, b in added_spans(s)] == [", Eastland,", "Ruritania"]


# ---------- entities ----------


def test_entity_normalization_alias_and_stoplist():
    assert normalize_entity("the  U.S.") == ("united states", "United States")
    assert normalize_entity("USG") == ("u.s. government", "U.S. government")
    assert normalize_entity("PRC")[1] == "China"
    assert normalize_entity("Groq, Inc") == ("groq", "Groq")
    assert normalize_entity("The Entity List") == ("entity list", "Entity List")
    assert normalize_entity("D:4")[0] == ""  # the pipeline's NER post-filter drops codes
    ident, toks = own_name_tokens("NVIDIA CORP", "NVDA")
    for generic in (
        "sec",
        "united states",
        "nasdaq",
        "congress",
        "fasb",
        "irs",
        "board",
        "fiscal 2025",
        "fiscal year",
        "q3",
        "third quarter of fiscal 2026",
        "january 2025",
        "march",
        "2024",
    ):
        assert is_stop_entity(generic, ident, toks), generic
    assert is_stop_entity("nvidia corporation", ident, toks)  # the company itself
    assert is_stop_entity("nvda", ident, toks)
    assert not is_stop_entity("groq", ident, toks)
    sf_ident, sf_toks = own_name_tokens("STIFEL FINANCIAL CORP", "SF")
    assert is_stop_entity("stifel", sf_ident, sf_toks)
    # a generic word of the company name does not exclude other entities containing it
    assert not is_stop_entity("financial industry regulatory authority", sf_ident, sf_toks)


def test_new_entities_become_topics_or_reinforce_lexicon_topics():
    def add_entities(d):
        c = change(d, EXPORT_CHANGE)
        sid = "0000000000-25-000001:0:3"
        c["signals"]["new_entities"] = [
            {"value": v, "detail": None, "old_sentence_ids": [], "new_sentence_ids": [sid]}
            for v in ("SEC", "PRC", "Acme Rocket Works", "the Entity List", "Q3 fiscal 2025")
        ]

    facts = derive_trend_facts(doc_comp(add_entities))
    t = topics_of(facts, EXPORT_CHANGE)
    assert ("entity", "Acme Rocket Works") in t
    assert ("lexicon", "China") in t  # PRC -> China -> the lexicon topic
    assert not {x for x in t if x[1] in ("SEC", "Q3 fiscal 2025", "Entity List")}
    exp = next(
        m
        for m in facts.topic_mentions
        if m.topic == "Export controls" and m.change_id == EXPORT_CHANGE
    )
    assert exp.source == "lexicon" and exp.matched_terms == [
        "export restrictions",
        "the Entity List",
    ]


# ---------- phrases ----------


def test_phrases_are_lemmatized_noun_chunks_without_boilerplate():
    nlp = derive.get_phrase_nlp()
    got = derive.phrases_in(
        nlp(
            "Our business could suffer a material adverse effect on our "
            "financial condition and results of operations."
        )
    )
    assert got == []
    got = dict(
        derive.phrases_in(
            nlp(
                "New export license requirements delayed shipments of "
                "accelerated computing products to binding customers."
            )
        )
    )
    assert "export license requirement" in got  # nouns lemmatized, lowercased
    for phrase in got:
        assert 2 <= len(phrase.split()) <= 4 and phrase == phrase.lower()
    facts = derive_trend_facts(doc_comp())
    phrases = {m.topic for m in facts.topic_mentions if m.source == "phrase"}
    assert "shipment delay" in phrases
    assert not phrases & set(derive.PHRASE_STOPLIST)


# ---------- activity ----------


@pytest.mark.parametrize("path", PUBLISHED, ids=lambda p: p.stem)
def test_word_counts_partition_the_diff_stats(path):
    comp = Comparison.model_validate_json(path.read_text(encoding="utf-8"))
    for c in comp.changes:
        a = change_activity(c)
        assert (a.added_sentences, a.removed_sentences, a.modified_sentences) == (
            c.stats.added,
            c.stats.removed,
            c.stats.modified,
        )
        assert a.added_words + a.removed_words + a.modified_words == (
            c.stats.added_word_count + c.stats.removed_word_count
        )


# ---------- determinism + files ----------


@pytest.mark.parametrize("path", PUBLISHED, ids=lambda p: p.stem)
def test_derivation_is_deterministic_and_leaves_the_report_untouched(path, tmp_path):
    before = path.read_bytes()
    comp = Comparison.model_validate_json(before)
    a = facts_json(derive_trend_facts(comp))
    b = facts_json(derive_trend_facts(Comparison.model_validate_json(before)))
    assert a == b
    out = derive_after_publish(path, tmp_path)
    assert out["status"] == "ok" and Path(out["path"]).read_text(encoding="utf-8") == a
    assert path.read_bytes() == before  # the published JSON is byte-identical
    assert json.loads(a)["analysis_id"] == comp.analysis_id


def test_committed_derived_files_are_current():
    """data/derived/ holds the facts of the committed reports; they must match a fresh derivation."""
    for path in PUBLISHED:
        comp = Comparison.model_validate_json(path.read_text(encoding="utf-8"))
        committed = ROOT / "data" / "derived" / f"{comp.analysis_id}.trends.json"
        assert committed.read_text(encoding="utf-8") == facts_json(derive_trend_facts(comp))


def test_ensure_facts_writes_once_and_rederives_stale_files(tmp_path):
    comp = doc_comp()
    facts = ensure_facts(comp, tmp_path)
    path = tmp_path / f"{comp.analysis_id}.trends.json"
    mtime = path.stat().st_mtime_ns
    assert ensure_facts(comp, tmp_path) == facts and path.stat().st_mtime_ns == mtime
    assert write_facts(tmp_path, facts) == (path, False)
    stale = json.loads(path.read_text())
    stale["derivation"] = "0.0.0+topics0"
    path.write_text(json.dumps(stale))
    assert load_facts(tmp_path, comp.analysis_id) is None
    assert ensure_facts(comp, tmp_path) == facts
    assert load_facts(tmp_path, comp.analysis_id) == facts


def test_fixture_is_never_derived(tmp_path, monkeypatch):
    fx = json.loads((ROOT / "contract" / "fixtures" / "FIXTURE_comparison.json").read_text())
    with pytest.raises(ValueError):
        derive_trend_facts(Comparison.model_validate(fx))
    monkeypatch.setenv("RISKDIFF_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("RISKDIFF_ALLOW_FIXTURE", "1")
    from pipeline.run import run_pipeline

    ctx = run_pipeline("FIXTUR", until_stage=8)
    assert "remote_publish" not in ctx.outputs and not (tmp_path / "derived").exists()


def test_pipeline_post_publish_step_derives_facts(tmp_path, monkeypatch):
    """publish_remote_if_enabled (called by run.py after the local publish) writes the facts next
    to the published directory, even with Databricks disabled."""
    from pipeline.schema import canonical_json
    from pipeline.store.publisher import publish_remote_if_enabled

    for v in ("DATABRICKS_HOST", "DATABRICKS_TOKEN", "DATABRICKS_WAREHOUSE_ID"):
        monkeypatch.delenv(v, raising=False)
    comp = doc_comp()
    pub = tmp_path / "published"
    pub.mkdir()
    p = pub / "TEST_2024_2025.json"
    p.write_text(canonical_json(comp), encoding="utf-8")
    before = p.read_bytes()
    out = publish_remote_if_enabled(p)
    assert out["status"] == "disabled" and out["trend_facts"]["status"] == "ok"
    assert load_facts(tmp_path / "derived", comp.analysis_id) is not None
    assert p.read_bytes() == before


def test_pipeline_sources_are_unchanged_by_trends():
    """Top-level pipeline/*.py feed code_fingerprint (analysis_id); trends live in a sub-package."""
    from pipeline.score import _pipeline_source_hash

    names = sorted(x.name for x in (ROOT / "pipeline").glob("*.py"))
    assert "derive.py" not in names and _pipeline_source_hash()


def test_potential_to_actual_and_change_mix_come_from_the_report():
    comp = doc_comp()
    facts = derive_trend_facts(comp)
    assert facts.by_change_type == comp.summary.by_change_type
    p2a = [h for h in comp.highlights if h.kind == "potential_became_actual"]
    assert [
        (p.change_id, p.old_sentence_id, p.new_sentence_id) for p in facts.potential_to_actual
    ] == [(h.change_id, h.old_sentence_id, h.new_sentence_id) for h in p2a]
    for p in facts.potential_to_actual:
        assert p.old_text == comp.sentence_index[p.old_sentence_id].text
        assert p.new_text == comp.sentence_index[p.new_sentence_id].text


def test_derive_does_not_mutate_its_input():
    comp = doc_comp()
    snap = copy.deepcopy(comp.model_dump())
    derive_trend_facts(comp)
    assert comp.model_dump() == snap


# ---------- T11: aggregation ----------

from pipeline.trends import aggregate  # noqa: E402


def mention(
    ticker,
    topic,
    *,
    source="lexicon",
    sid="0000000000-25-000001:0:1",
    terms=("x",),
    text="FIXTURE: sentence.",
    cid="a" * 16,
):
    return {
        "ticker": ticker,
        "change_id": cid,
        "sentence_id": sid,
        "topic": topic,
        "source": source,
        "matched_terms": list(terms),
        "status": "added",
        "text": text,
        "added_spans": [(0, len(text))],
        "short_title": "FIXTURE: title",
    }


def test_phrases_need_two_companies_lexicon_and_entities_do_not():
    rows = [
        mention("AAA", "supply agreement", source="phrase"),
        mention("AAA", "chip design", source="phrase"),
        mention("BBB", "chip design", source="phrase"),
        mention("AAA", "Tariffs"),
        mention("BBB", "Groq", source="entity"),
    ]
    got = {(t["source"], t["topic"]): t for t in aggregate.topics(rows)}
    assert ("phrase", "supply agreement") not in got
    assert got[("phrase", "chip design")]["companies"] == ["AAA", "BBB"]
    assert ("lexicon", "Tariffs") in got and ("entity", "Groq") in got


def test_topic_ranking_and_example_selection():
    rows = [
        mention(
            "AAA",
            "Tariffs",
            sid="0000000000-25-000001:0:1",
            terms=("tariffs",),
            text="FIXTURE: short.",
        ),
        mention(
            "AAA",
            "Tariffs",
            sid="0000000000-25-000001:0:2",
            terms=("tariffs", "Section 232"),
            text="FIXTURE: a longer sentence with two terms.",
        ),
        mention("BBB", "Tariffs", sid="0000000000-25-000002:0:1", text="FIXTURE: b two."),
        mention("BBB", "Tariffs", sid="0000000000-25-000002:0:2", text="FIXTURE: b."),
        mention("AAA", "China", sid="0000000000-25-000001:0:3"),
        mention("BBB", "Antitrust", sid="0000000000-25-000002:0:3"),
        mention("BBB", "entity list", source="entity"),
        mention("CCC", "Entity List", source="entity", sid="0000000000-25-000003:0:1"),
    ]
    t = aggregate.topics(rows)
    # company_count desc, then sentence_count desc, then topic asc
    assert [(x["topic"], x["company_count"], x["sentence_count"]) for x in t] == [
        ("Tariffs", 2, 4),
        ("entity list", 2, 2),  # entity names merge case-insensitively
        ("Antitrust", 1, 1),
        ("China", 1, 1),
    ]
    ex = {e["ticker"]: e for e in t[0]["examples"]}
    assert list(ex) == ["AAA", "BBB"]  # one example per company
    assert ex["AAA"]["matched_terms"] == ["tariffs", "Section 232"]  # most matched terms first
    assert ex["BBB"]["text"] == "FIXTURE: b."  # then the shortest sentence
    assert set(ex["AAA"]) == {
        "ticker",
        "change_id",
        "sentence_id",
        "short_title",
        "status",
        "text",
        "added_spans",
        "matched_terms",
    }


def test_category_activity_sums_and_skips_unchanged():
    base = {
        "added_sentences": 1,
        "removed_sentences": 2,
        "modified_sentences": 3,
        "added_words": 10,
        "removed_words": 20,
        "modified_words": 30,
    }
    rows = [
        {
            "ticker": "AAA",
            "category": "credit",
            "change_id": "b" * 16,
            "change_type": "new",
            "score": 40,
            **base,
        },
        {
            "ticker": "AAA",
            "category": "credit",
            "change_id": "c" * 16,
            "change_type": "expanded",
            "score": 60,
            **base,
        },
        {
            "ticker": "AAA",
            "category": "credit",
            "change_id": "d" * 16,
            "change_type": "largely_unchanged",
            "score": 99,
            **base,
        },
    ]
    (row,) = aggregate.category_activity(rows)
    assert row["risk_factors"] == 2 and row["change_ids"] == ["c" * 16, "b" * 16]
    assert row["added_words"] == 20 and row["modified_sentences"] == 6 and row["max_score"] == 60


def local_body() -> dict:
    facts = [
        load_facts(
            ROOT / "data" / "derived",
            Comparison.model_validate_json(p.read_text(encoding="utf-8")).analysis_id,
        )
        for p in PUBLISHED
    ]
    assert all(facts)
    return aggregate.body_from_facts(facts)


def test_local_body_on_the_real_reports():
    body = local_body()
    assert [c["ticker"] for c in body["companies"]] == ["NVDA", "SF"]
    nvda = body["companies"][0]
    assert nvda["cik"] == "0001045810" and nvda["edgar_url_new"].startswith("https://www.sec.gov/")
    assert (
        nvda["meaningful_changes"]
        == nvda["total_changes"] - nvda["by_change_type"]["largely_unchanged"]
    )
    assert body["headline"]["companies"] == 2
    assert body["headline"]["top_topic"] == {
        "topic": body["topics"][0]["topic"],
        "company_count": body["topics"][0]["company_count"],
    }
    assert body["potential_to_actual"] and body["potential_to_actual"][0]["ticker"] == "NVDA"
    for t in body["topics"]:
        for e in t["examples"]:
            for a, b in e["added_spans"]:
                assert 0 <= a < b <= len(e["text"])
    # no banned wording anywhere in what /trends shows
    text = json.dumps(body).lower()
    for banned in ("riskier", "biggest risk", "probability"):
        assert banned not in text


# ---------- T11: the Databricks path against simulated tables ----------


class TrendsStore:
    """Duck-typed store for the API whose SQL is answered from TableSim rows (the publisher's
    real MERGEs filled them). Evaluates the three trends queries in Python with the semantics the
    SQL states (current ids, phrase rule, one example per topic+source+ticker)."""

    def __init__(self, sim):
        self.sim = sim
        self.settings = type(
            "S",
            (),
            {
                "table": lambda self, n: f"`riskdiff`.`main`.`{n}`",
                "host": "h",
                "catalog": "riskdiff",
                "schema": "main",
                "warehouse_id": "w",
            },
        )()
        self.statements: list[tuple[str, dict]] = []

    def list_reports(self):
        return [r for r in self.sim.rows["reports"].values() if r["is_current"]]

    def health(self):
        return {"remote": "ok", "warehouse_state": "RUNNING"}

    def execute(self, sql, params=None):
        params = params or {}
        self.statements.append((sql, params))
        ids = set(json.loads(params["ids"]))
        cur = {a for (a,), r in self.sim.rows["reports"].items() if r["is_current"]} & ids
        changes = self.sim.rows["changes"]
        if sql.startswith("WITH m AS"):
            assert params["phrase"] == "phrase" and params["current"] is True
            ms = [r for r in self.sim.rows["topic_mentions"].values() if r["analysis_id"] in cur]
            share: dict[str, set] = {}
            for r in ms:
                if r["topic_source"] == "phrase":
                    share.setdefault(r["topic"], set()).add(r["ticker"])
            ms = [
                r
                for r in ms
                if r["topic_source"] != "phrase"
                or len(share[r["topic"]]) >= params["min_companies"]
            ]
            groups: dict[tuple, list] = {}
            for r in ms:
                groups.setdefault((r["topic"], r["topic_source"], r["ticker"]), []).append(r)
            out = []
            for rs in groups.values():
                best = min(
                    rs,
                    key=lambda r: (
                        -len(r["matched_terms"]),
                        len(r["sentence_text"]),
                        r["change_id"],
                        r["sentence_id"],
                    ),
                )
                out.append(
                    {
                        **best,
                        "matched_terms": json.dumps(best["matched_terms"]),
                        "short_title": changes[(best["analysis_id"], best["change_id"])][
                            "short_title"
                        ],
                        "ticker_sentence_count": len(rs),
                    }
                )
            return out
        if sql.startswith("SELECT ca.ticker"):
            return [
                r
                for r in self.sim.rows["category_activity"].values()
                if r["analysis_id"] in cur and r["change_type"] != params["unchanged"]
            ]
        if sql.startswith("SELECT h.ticker"):
            reports = self.sim.rows["reports"]
            return [
                {
                    **h,
                    "company_name": reports[(h["analysis_id"],)]["company_name"],
                    "score": changes[(h["analysis_id"], h["change_id"])]["score"],
                }
                for h in self.sim.rows["highlights"].values()
                if h["analysis_id"] in cur and h["kind"] == params["kind"]
            ]
        raise AssertionError(sql[:60])


def test_databricks_trends_match_the_local_aggregate(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from api import main as api_main
    from pipeline.store import DatabricksStore
    from pipeline.store.publisher import publish_remote
    from tests.test_api_store import settings_for, wait_for_trends
    from tests.test_store import HOST, FakeClient, settings
    from tests.test_store_publish import TableSim

    monkeypatch.setenv("DATABRICKS_HOST", HOST)
    sim = TableSim()
    db = DatabricksStore(settings(), client=FakeClient(sim), sleep=lambda s: None)
    for p in PUBLISHED:  # the real reports through the real publish step (incl. the new MERGEs)
        publish_remote(p, db, published_by="tester", derived_dir=tmp_path / "derived")
    assert sim.rows["topic_mentions"] and sim.rows["category_activity"]
    for sql in (r for r in sim.statements if r.startswith("MERGE")):
        assert "'" not in sql.split("from_json(:rows, '")[0]  # values only as parameters

    store = TrendsStore(sim)
    s = settings_for(tmp_path)  # no local reports: everything comes from the store
    app = api_main.create_app(s, store_factory=lambda: store)
    with TestClient(app) as client:
        remote = wait_for_trends(client, lambda t: t["source"] == "databricks")
    assert remote["status"] == "ok" and remote["source"] == "databricks"
    assert len(store.statements) == 3  # at most three small queries
    for sql, params in store.statements:
        assert ":ids" in sql and ":current" in sql and "NVDA" not in sql
        assert sorted(json.loads(params["ids"])) == sorted(
            c["analysis_id"] for c in remote["companies"]
        )
    local = local_body()
    for key in ("headline", "topics", "category_activity", "potential_to_actual", "change_mix"):
        assert remote[key] == local[key], key
    for rc, lc in zip(remote["companies"], local["companies"], strict=True):
        assert rc["edgar_url_old"] is None and rc["edgar_url_new"] is None  # not in the table
        assert {k: v for k, v in rc.items() if not k.startswith("edgar")} == {
            k: v for k, v in lc.items() if not k.startswith("edgar")
        }


# ---------- T11: the backfill script ----------


def test_derive_trends_script_is_idempotent(tmp_path, monkeypatch, capsys):
    import importlib
    import shutil

    script = importlib.import_module("scripts.derive_trends")
    for v in ("DATABRICKS_HOST", "DATABRICKS_TOKEN", "DATABRICKS_WAREHOUSE_ID"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setenv("RISKDIFF_DATA_DIR", str(tmp_path))
    (tmp_path / "published").mkdir()
    for p in PUBLISHED:
        shutil.copy(p, tmp_path / "published" / p.name)
    assert script.main([]) == 0
    files = sorted((tmp_path / "derived").glob("*.trends.json"))
    assert len(files) == len(PUBLISHED)
    snap = {f.name: (f.read_bytes(), f.stat().st_mtime_ns) for f in files}
    assert script.main(["--local-only"]) == 0
    assert {f.name: (f.read_bytes(), f.stat().st_mtime_ns) for f in files} == snap  # no rewrite
    out = capsys.readouterr().out
    assert "unchanged" in out and "local only" in out
    for f in files:  # identical to the committed derived files
        assert f.read_bytes() == (ROOT / "data" / "derived" / f.name).read_bytes()
    # a bad file counts as a failure (exit 1), the others still derive
    (tmp_path / "published" / "BAD_2024_2025.json").write_text("{}")
    assert script.main(["--local-only"]) == 1


def test_derive_trends_script_backfills_the_store(tmp_path, monkeypatch):
    import importlib
    import shutil

    from pipeline.store import DatabricksStore
    from pipeline.store.publisher import publish_remote
    from tests.test_store import HOST, FakeClient, settings
    from tests.test_store_publish import TableSim

    script = importlib.import_module("scripts.derive_trends")
    monkeypatch.setenv("DATABRICKS_HOST", HOST)
    monkeypatch.setenv("DATABRICKS_TOKEN", "dapi-test")
    monkeypatch.setenv("DATABRICKS_WAREHOUSE_ID", "wh1")
    monkeypatch.setenv("RISKDIFF_DATA_DIR", str(tmp_path))
    sim = TableSim()
    fake = FakeClient(sim)
    db = DatabricksStore(settings(), client=fake, sleep=lambda s: None)
    for p in PUBLISHED:
        publish_remote(p, db, published_by="tester")
    # a workspace from before T11: the report rows exist but the trend tables are empty
    sim.rows["topic_mentions"].clear()
    sim.rows["category_activity"].clear()
    store = TrendsStore(sim)
    store.download_report = lambda aid, volume_path=None, content_sha256=None: db.download_report(
        aid, volume_path=volume_path, content_sha256=content_sha256
    )
    store.execute = db.execute
    monkeypatch.setattr(script, "DatabricksStore", lambda s: store)
    (tmp_path / "published").mkdir()
    shutil.copy(
        PUBLISHED[0], tmp_path / "published" / PUBLISHED[0].name
    )  # one local, one remote-only
    assert script.main([]) == 0
    n = len(sim.rows["topic_mentions"])
    assert n > 0 and sim.rows["category_activity"]
    assert len(list((tmp_path / "derived").glob("*.trends.json"))) == len(PUBLISHED)
    assert script.main([]) == 0 and len(sim.rows["topic_mentions"]) == n  # insert-if-absent
