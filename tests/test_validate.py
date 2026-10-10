"""Citation validator tests: invalid citations and banned phrases are dropped, never displayed."""

from __future__ import annotations

from pipeline.validate import banned_language, validate_llm_output

ALLOWED = {
    "0000000000-24-000001:1:1": "Tariffs could increase our costs.",
    "0000000000-25-000001:1:1": "We are qualifying a new foundry in Northland over 18 months.",
    "0000000000-25-000001:1:2": "Export restrictions resulted in a shipment delay that reduced revenue by $1.2 billion in fiscal 2025.",
}


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
    assert banned_language("LIKELY outcomes") == "predictive wording"
    assert banned_language("The buyout closed.") is None
    assert (
        banned_language("A government investigation began.") is None
    )  # 'investigation' is allowed
    assert banned_language("The investment thesis.") == "advice wording"  # invest* stems are banned
    assert banned_language("Do not invest.") == "advice wording"


def test_claim_limits():
    claims = [
        {"text": f"Claim {c} text.", "cited_sentence_ids": ["0000000000-25-000001:1:1"]}
        for c in "ABCDE"
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


def test_partially_invalid_citations_drop_the_whole_claim():
    r = validate_llm_output(
        raw(
            [
                {
                    "text": "The company was fined by the EU.",
                    "cited_sentence_ids": [
                        "0000000000-25-000001:1:1",
                        "0000000001-25-000001:99:99",
                    ],
                }
            ]
        ),
        ALLOWED,
    )
    assert r.claims == [] and r.dropped_claim_count == 1
    assert "invalid citation" in r.dropped_reasons[-1]


def test_rubric_yes_with_one_fabricated_id_becomes_no():
    r = validate_llm_output(
        raw(
            [],
            rubric=[
                {
                    "question_id": "Q3",
                    "answer": True,
                    "cited_sentence_ids": ["0000000000-25-000001:1:2", "0000000000-25-000001:7:7"],
                    "rationale": "Revenue fell $1.2 billion.",
                }
            ],
        ),
        ALLOWED,
    )
    q3 = next(a for a in r.rubric if a.question_id == "Q3")
    assert q3.answer is False and q3.raw_answer is True and q3.rationale is None


def test_numbers_not_in_cited_sentences_are_dropped():
    ok = {
        "text": "Revenue was reduced by $1.2 billion in fiscal 2025 after export restrictions.",
        "cited_sentence_ids": ["0000000000-25-000001:1:2"],
    }
    bad = {
        "text": "The company was fined $2 billion.",
        "cited_sentence_ids": ["0000000000-25-000001:1:2"],
    }
    bad2 = {
        "text": "Qualifying the foundry takes 24 months.",
        "cited_sentence_ids": ["0000000000-25-000001:1:1"],
    }
    r = validate_llm_output(raw([ok, bad, bad2]), ALLOWED)
    assert [c.text for c in r.claims] == [ok["text"]]
    assert r.dropped_claim_count == 2
    assert all("number" in x for x in r.dropped_reasons if x.startswith("claim"))


def test_extra_banned_language():
    for t in [
        "The company is now more risky.",
        "The company is safer now.",
        "There is a chance of loss.",
        "The odds improved.",
        "30 percent higher in risk terms.",
    ]:
        assert banned_language(t) is not None, t
    assert banned_language("Revenue grew 3 percent.") is None


def test_hf_payload_shape(monkeypatch):
    """The Hugging Face client must send a valid json_schema response_format and temperature 0."""
    import pipeline.llm as llm
    from pipeline.config import Settings

    captured = {}

    class FakeClient:
        def __init__(self, token=None, timeout=None):
            pass

        def chat_completion(self, **kw):
            captured.update(kw)

            class R:
                choices = [
                    type(
                        "C",
                        (),
                        {"message": type("M", (), {"content": '{"rubric": [], "claims": []}'})()},
                    )()
                ]

            return R()

    monkeypatch.setattr("huggingface_hub.InferenceClient", FakeClient)
    settings = Settings(
        sec_user_agent=None,
        hf_token="x",
        gemini_api_key=None,
        data_dir=__import__("pathlib").Path("/tmp"),
        embed_model="m",
        llm_model="org/model",
        gemini_model="g",
        api_origin="o",
    )
    client = llm.make_hf_client(settings)
    assert client.model_id == "hf:org/model"
    assert llm.probe(client) is True
    rf = captured["response_format"]
    assert (
        rf["type"] == "json_schema"
        and set(rf["json_schema"]) >= {"name", "schema"}
        and "value" not in rf
    )
    assert captured["temperature"] == 0.0 and captured["model"] == "org/model"
    from huggingface_hub.inference._generated.types.chat_completion import (
        ChatCompletionInputResponseFormatJSONSchema,
    )

    ChatCompletionInputResponseFormatJSONSchema(type="json_schema", json_schema=rf["json_schema"])


def test_dropped_reasons_never_contain_the_banned_word():
    r = validate_llm_output(
        raw(
            [
                {
                    "text": "This is likely to recur and investors should sell.",
                    "cited_sentence_ids": ["0000000000-25-000001:1:1"],
                }
            ]
        ),
        ALLOWED,
    )
    joined = " ".join(r.dropped_reasons).lower()
    for w in ("likely", "sell", "invest"):
        assert w not in joined
    assert "banned language" in joined


def test_comparative_risk_paraphrases_are_banned():
    for t in [
        "The company now faces higher risk from export controls.",
        "There is greater risk from Taiwan.",
        "The company is more vulnerable to supply shocks.",
        "Holders should consider exiting.",
        "Investors should avoid the shares.",
        "This represents an increased level of risk.",
    ]:
        assert banned_language(t) is not None, t
    assert banned_language("The filing names Taiwan as a manufacturing location.") is None
