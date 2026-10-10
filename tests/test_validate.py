"""Citation validator tests: invalid citations and banned phrases are dropped, never displayed."""

from __future__ import annotations

from pipeline.validate import banned_language, validate_llm_output

ALLOWED = {"0000000000-24-000001:1:1", "0000000000-25-000001:1:1", "0000000000-25-000001:1:2"}


def raw(claims, rubric=None):
    return {
        "rubric": rubric
        or [
            {
                "question_id": "Q1",
                "answer": True,
                "cited_sentence_ids": ["0000000000-25-000001:1:2"],
                "rationale": "The new text reports the event.",
            },
            {
                "question_id": "Q2",
                "answer": True,
                "cited_sentence_ids": ["0000000000-99-000001:9:9"],
                "rationale": "x",
            },
            {"question_id": "Q3", "answer": False, "cited_sentence_ids": []},
        ],
        "claims": claims,
    }


def test_invalid_citations_are_dropped_and_yes_becomes_no():
    r = validate_llm_output(
        raw(
            [
                {
                    "text": "Valid claim about the new foundry.",
                    "cited_sentence_ids": ["0000000000-25-000001:1:1"],
                },
                {
                    "text": "Claim citing a sentence that does not exist.",
                    "cited_sentence_ids": ["0000000000-25-000001:7:7"],
                },
                {"text": "Claim with no citations at all.", "cited_sentence_ids": []},
                {"text": "Claim with a non-string citation.", "cited_sentence_ids": [42]},
            ]
        ),
        ALLOWED,
    )
    assert [c.text for c in r.claims] == ["Valid claim about the new foundry."]
    assert r.dropped_claim_count == 3
    by_q = {a.question_id: a for a in r.rubric}
    assert by_q["Q1"].answer is True and by_q["Q1"].cited_sentence_ids == [
        "0000000000-25-000001:1:2"
    ]
    assert (
        by_q["Q2"].answer is False and by_q["Q2"].raw_answer is True
    )  # yes without valid citation -> no
    assert by_q["Q3"].answer is False
    assert by_q["Q4"].answer is False and by_q["Q4"].raw_answer is None  # missing -> no
    assert any("Q2 'yes' downgraded" in x for x in r.dropped_reasons)
    assert any("Q4 missing" in x for x in r.dropped_reasons)


def test_banned_phrases_are_dropped():
    bad = [
        "The company is likely to face losses.",
        "There is a 30% probability of disruption.",
        "This makes the company riskier than before.",
        "Investors should buy the stock.",
        "We recommend caution.",
        "Risk increased by 20%.",
        "This is a 40% risk.",
        "Management will guarantee delivery.",
        "It is unlikely that this matters.",
        "Avoid Investing here.",
    ]
    r = validate_llm_output(
        raw([{"text": t, "cited_sentence_ids": ["0000000000-25-000001:1:1"]} for t in bad]), ALLOWED
    )
    assert r.claims == []
    assert r.dropped_claim_count == len(bad)
    assert all("banned language" in x for x in r.dropped_reasons if x.startswith("claim"))


def test_banned_matching_is_whole_word_and_case_insensitive():
    assert banned_language("The seller delivered.") is None  # 'sell' inside 'seller' is fine
    assert banned_language("LIKELY outcomes") == "likely"
    assert banned_language("The buyout closed.") is None
    assert (
        banned_language("A government investigation began.") is None
    )  # 'investigation' is allowed
    assert banned_language("The investment thesis.") == "investment"  # invest* stems are banned
    assert banned_language("Do not invest.") == "invest"


def test_claim_limits():
    claims = [
        {"text": f"Claim {i} text.", "cited_sentence_ids": ["0000000000-25-000001:1:1"]}
        for i in range(5)
    ]
    claims.append({"text": "x" * 500, "cited_sentence_ids": ["0000000000-25-000001:1:1"]})
    r = validate_llm_output(raw(claims), ALLOWED)
    assert len(r.claims) == 3
    assert r.dropped_claim_count == 3
    r2 = validate_llm_output(
        {"rubric": "garbage", "claims": "garbage"}
        if False
        else {"rubric": [], "claims": [1, "two", None]},
        ALLOWED,
    )
    assert r2.claims == [] and r2.dropped_claim_count == 3
    assert all(a.answer is False for a in r2.rubric)
