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
