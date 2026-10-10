"""Stage 6 tests: hedge->actual, new entities, new quantities, categories. All cited."""

from __future__ import annotations

from pipeline.diff import diff_pair
from pipeline.signals import (
    SignalContext,
    categorize,
    compute_signals,
    hypothetical_to_actual,
    new_entities,
    new_quantities,
)
from tests.test_diff import NEW, OLD, block


def ctx_for(old, new):
    d = diff_pair(old, new, similarity=0.85)
    return SignalContext(
        old=old,
        new=new,
        sentences=d.sentences,
        similarity=0.85,
        added_word_count=d.stats.added_word_count,
        removed_word_count=d.stats.removed_word_count,
        old_word_count=d.stats.old_word_count,
        new_word_count=d.stats.new_word_count,
    )


def test_hedge_to_actual_in_modified_sentence():
    old = block(
        OLD,
        1,
        "Supply risk.",
        [
            "Natural disasters or trade restrictions may affect our suppliers.",
            "We keep safety stock.",
        ],
    )
    new = block(
        NEW,
        1,
        "Supply risk.",
        [
            "Natural disasters or trade restrictions have affected our suppliers.",
            "We keep safety stock.",
        ],
    )
    hits = hypothetical_to_actual(ctx_for(old, new))
    assert len(hits) == 1
    assert hits[0].value == "may -> have affected"
    assert hits[0].old_sentence_ids == [f"{OLD}:1:1"] and hits[0].new_sentence_ids == [f"{NEW}:1:1"]


def test_hedge_to_actual_in_added_sentence_with_year():
    old = block(
        OLD,
        1,
        "Supply risk.",
        [
            "Export restrictions could delay shipments from our foundries and reduce our revenue.",
            "We keep safety stock.",
        ],
    )
    new = block(
        NEW,
        1,
        "Supply risk.",
        [
            "Export restrictions could delay shipments from our foundries and reduce our revenue.",
            "In fiscal 2025, export restrictions resulted in a shipment delay from our foundries that reduced our revenue.",
            "We keep safety stock.",
        ],
    )
    hits = hypothetical_to_actual(ctx_for(old, new))
    assert len(hits) == 1
    assert hits[0].old_sentence_ids == [f"{OLD}:1:1"] and hits[0].new_sentence_ids == [f"{NEW}:1:2"]
    assert hits[0].value.startswith("could ->")


def test_hedge_kept_but_actual_inserted():
    old = block(
        OLD,
        1,
        "Changes in trade policy could increase our costs.",
        ["Tariffs on imported components could increase our cost of goods sold."],
    )
    new = block(
        NEW,
        1,
        "Changes in trade policy, including tariffs, have increased and could further increase our costs.",
        [
            "Tariffs on imported components increased our cost of goods sold by approximately 3% in fiscal 2025."
        ],
    )
    hits = hypothetical_to_actual(ctx_for(old, new))
    values = {h.value for h in hits}
    assert "could -> have increased" in values
    assert "could -> increased" in values
    assert len(hits) == 2


def test_added_sentence_still_hedged_is_not_a_hit():
    old = block(
        OLD,
        1,
        "Trade.",
        ["Changes in export control regulations could limit the markets in which we sell."],
    )
    new = block(
        NEW,
        1,
        "Trade.",
        [
            "Changes in export control regulations could limit the markets in which we sell.",
            "Additional export control regulations announced in March 2025 could limit the markets in which we sell.",
        ],
    )
    assert hypothetical_to_actual(ctx_for(old, new)) == []


def test_no_false_hedge_hit_when_nothing_changed():
    old = block(OLD, 1, "Risk.", ["We may face losses.", "We have faced losses before."])
    new = block(NEW, 1, "Risk.", ["We may face losses.", "We have faced losses before."])
    assert hypothetical_to_actual(ctx_for(old, new)) == []


def test_new_entities_detected_and_cited():
    old = block(
        OLD,
        1,
        "Foundries.",
        ["We rely on foundries in Taiwan and South Korea.", "Regulations may change."],
    )
    new = block(
        NEW,
        1,
        "Foundries.",
        [
            "We rely on foundries in Taiwan, South Korea, and Japan.",
            "Regulations such as the European Union AI Act may change.",
            "The U.S. Department of Commerce imposed new rules.",
        ],
    )
    hits = new_entities(ctx_for(old, new))
    values = {h.value.lower() for h in hits}
    assert "japan" in values
    assert not any("taiwan" in v for v in values)
    assert any("department of commerce" in v or "commerce" in v for v in values) or any(
        "european union" in v or "ai act" in v for v in values
    )
    for h in hits:
        assert h.new_sentence_ids and all(s.startswith(NEW) for s in h.new_sentence_ids)


def test_new_quantities_and_changed_quantity():
    old = block(
        OLD, 1, "FX.", ["Approximately 40% of our revenue is in foreign currencies.", "We hedge."]
    )
    new = block(
        NEW,
        1,
        "FX.",
        [
            "Approximately 30% of our revenue is in foreign currencies.",
            "We hedge.",
            "A 10% move would change revenue by $1.2 billion and affect 3,000 employees.",
        ],
    )
    hits = new_quantities(ctx_for(old, new))
    values = [h.value for h in hits]
    assert "40% -> 30%" in values
    assert "$1.2 billion" in values and "10%" in values and "3,000 employees" in values
    changed = next(h for h in hits if h.value == "40% -> 30%")
    assert changed.old_sentence_ids == [f"{OLD}:1:1"] and changed.new_sentence_ids == [f"{NEW}:1:1"]


def test_each_old_quantity_explains_at_most_one_new_quantity():
    old = block(
        OLD,
        1,
        "Customers.",
        ["Our ten largest customers accounted for approximately 55% of revenue."],
    )
    new = block(
        NEW,
        1,
        "Customers.",
        [
            "Our ten largest customers accounted for approximately 61% of revenue, and one customer accounted for 14%."
        ],
    )
    values = [h.value for h in new_quantities(ctx_for(old, new))]
    assert values == ["55% -> 61%", "14%"]


def test_categorize_lexicon():
    cats, scores = categorize(
        "Our information technology systems are vulnerable to ransomware and phishing. A security breach could expose confidential data."
    )
    assert cats[0] == "cybersecurity"
    cats, _ = categorize(
        "Approximately 40% of our revenue is denominated in foreign currencies. Exchange rate fluctuations and a strengthening U.S. dollar could reduce revenue."
    )
    assert cats[0] == "foreign_exchange"
    cats, _ = categorize("Blue skies and green fields.")
    assert cats == ["other"]


def test_categorize_hybrid_with_dense_scores():
    dense = {
        c: 0.1
        for c in [
            "geopolitical",
            "supply_chain",
            "regulation",
            "cybersecurity",
            "customer_concentration",
            "competition",
            "liquidity",
            "credit",
            "interest_rates",
            "foreign_exchange",
            "artificial_intelligence",
            "intellectual_property",
            "labor",
            "climate",
            "litigation",
            "macroeconomic",
        ]
    }
    dense["artificial_intelligence"] = 0.6
    cats, scores = categorize(
        "We integrate machine learning features into our software; model outputs may be inaccurate.",
        dense,
    )
    assert cats[0] == "artificial_intelligence"
    assert all(0 <= v <= 1 for v in scores.values())


def test_compute_signals_is_complete_and_cited():
    old = block(
        OLD,
        1,
        "Trade policy could increase our costs.",
        ["Tariffs on imported components could increase our cost of goods sold."],
    )
    new = block(
        NEW,
        1,
        "Trade policy has increased our costs.",
        [
            "Tariffs on imported components increased our cost of goods sold by approximately 3% in fiscal 2025.",
            "Additional tariffs announced by the Westland Trade Commission in March 2025 could apply to our products.",
        ],
    )
    sig, cats = compute_signals(ctx_for(old, new))
    assert sig.hypothetical_to_actual and sig.hypothetical_to_actual[0].old_sentence_ids
    assert any(h.value == "3%" for h in sig.new_quantities)
    assert 0 <= sig.added_text_ratio <= 1 and 0 <= sig.semantic_shift <= 1
    assert cats and cats[0] in ("regulation", "macroeconomic", "geopolitical")
    for hits in (sig.hypothetical_to_actual, sig.new_entities, sig.new_quantities):
        for h in hits:
            assert h.old_sentence_ids or h.new_sentence_ids


def test_bare_past_tense_insertions_are_not_hedge_to_actual_hits():
    old = block(
        OLD,
        1,
        "Demand.",
        [
            "Our business could be harmed if customers delay orders.",
            "We may be unable to obtain components.",
        ],
    )
    new = block(
        NEW,
        1,
        "Demand.",
        [
            "Our business could be harmed if customers, which were affected by tariffs, delay orders.",
            "We may be unable to obtain components that are currently sourced from Asia.",
        ],
    )
    assert hypothetical_to_actual(ctx_for(old, new)) == []


def test_money_regex_has_no_trailing_comma():
    from pipeline.signals import _quantities

    assert _quantities("We paid $5, and later $1,250.50 million, plus $3 billion.") == [
        "$5",
        "$1,250.50 million",
        "$3 billion",
    ]


def test_modal_before_actual_marker_is_not_a_hit():
    old = block(
        OLD,
        1,
        "Ops.",
        ["A disruption could disrupt our operations.", "We may be subject to penalties."],
    )
    new = block(
        NEW,
        1,
        "Ops.",
        [
            "A disruption could have disrupted our operations.",
            "We may have been subject to penalties.",
        ],
    )
    assert hypothetical_to_actual(ctx_for(old, new)) == []
    # but the genuine case still fires
    old2 = block(OLD, 1, "Ops.", ["Trade restrictions may affect our suppliers."])
    new2 = block(
        NEW,
        1,
        "Ops.",
        ["Trade restrictions have affected and may continue to affect our suppliers."],
    )
    assert len(hypothetical_to_actual(ctx_for(old2, new2))) == 1


# ---- Task 2: entity post-filters ----


def test_clean_entity_rules():
    from pipeline.signals import clean_entity

    assert clean_entity("D:4") is None
    assert clean_entity("Q3") is None
    assert clean_entity("AI Diffusion IFR in") == "AI Diffusion IFR"
    assert clean_entity("the GAIN AI Act") == "GAIN AI Act"
    assert clean_entity("Japan") == "Japan"
    assert clean_entity("§ 232") is None
    assert clean_entity("12,000") is None
    assert clean_entity("of the") is None
    assert clean_entity("U.S. Department of Commerce,") == "U.S. Department of Commerce"


def test_near_duplicate_entities_are_merged():
    from pipeline.schema import SignalHit
    from pipeline.signals import merge_near_duplicates

    hits = [
        SignalHit(value="Ruritania", new_sentence_ids=[f"{NEW}:1:1"]),
        SignalHit(value="Ruritanian", new_sentence_ids=[f"{NEW}:1:3"]),
        SignalHit(value="GAIN AI Act", new_sentence_ids=[f"{NEW}:1:2"]),
        SignalHit(value="GAIN AI Act's", new_sentence_ids=[f"{NEW}:1:4"]),
        SignalHit(value="Japan", new_sentence_ids=[f"{NEW}:1:5"]),
    ]
    out = merge_near_duplicates(hits)
    assert [h.value for h in out] == ["Ruritania", "GAIN AI Act", "Japan"]
    assert out[0].new_sentence_ids == [f"{NEW}:1:1", f"{NEW}:1:3"]
    assert out[1].new_sentence_ids == [f"{NEW}:1:2", f"{NEW}:1:4"]


def test_new_entities_drop_codes_and_trailing_prepositions():
    old = block(OLD, 1, "Export controls.", ["New export controls may affect our business."])
    new = block(
        NEW,
        1,
        "Export controls.",
        [
            "The AI Diffusion IFR in January added licensing requirements, and the GAIN AI Act was proposed in Japan; product D:4 is covered."
        ],
    )
    values = [h.value for h in new_entities(ctx_for(old, new))]
    assert not any(v.endswith(" in") for v in values)
    assert "D:4" not in values
    assert any("Japan" in v for v in values)


# ---- Task 3: in progress -> concluded ----

OLD_ANTITRUST = (
    "Regulators in China are investigating whether our business practices violate antitrust law."
)
NEW_ANTITRUST = "China's antitrust regulators published their preliminary finding that our business practices violated antitrust law."


def test_status_change_detected_on_aligned_pair():
    old = block(OLD, 1, "Regulation.", [OLD_ANTITRUST])
    new = block(NEW, 1, "Regulation.", [NEW_ANTITRUST])
    hits = hypothetical_to_actual(ctx_for(old, new))
    assert len(hits) == 1
    assert hits[0].value == "investigating -> published their preliminary finding"
    assert hits[0].old_sentence_ids == [f"{OLD}:1:1"] and hits[0].new_sentence_ids == [f"{NEW}:1:1"]


def test_status_change_detected_on_removed_added_pair():
    old = block(OLD, 1, "Regulation.", ["We sell products worldwide.", OLD_ANTITRUST])
    new = block(
        NEW,
        1,
        "Regulation.",
        [
            "We sell products worldwide.",
            "Additional language about unrelated topics appears here for context.",
            NEW_ANTITRUST,
        ],
    )
    hits = hypothetical_to_actual(ctx_for(old, new))
    assert any(
        h.value.startswith("investigating ->") and h.old_sentence_ids == [f"{OLD}:1:2"]
        for h in hits
    ), hits


def test_status_change_requires_concluded_and_less_tentative_wording():
    from pipeline.signals import status_change

    assert (
        status_change(
            "Regulators are investigating our practices.",
            "Regulators are still investigating our practices and may impose remedies.",
        )
        is None
    )
    assert (
        status_change(
            "Regulators are investigating our practices.", "Regulators could have fined us."
        )
        is None
    )
    assert status_change("We may incur costs.", "We incurred costs of $4.5 billion.") == (
        "may",
        "incurred",
    )
    assert (
        status_change(
            "The proposed rule may apply to us.", "The final rule was adopted and applies to us."
        )
        is not None
    )
    assert (
        status_change("Our products were widely available.", "We found new customers.") is None
    )  # no in-progress marker in old


def test_modal_pattern_still_detected():
    old = block(OLD, 1, "Costs.", ["Tariffs may increase our costs."])
    new = block(NEW, 1, "Costs.", ["Tariffs have increased our costs."])
    hits = hypothetical_to_actual(ctx_for(old, new))
    assert hits and hits[0].value == "may -> have increased"
