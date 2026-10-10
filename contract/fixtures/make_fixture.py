"""Build the hand-made development fixture `FIXTURE_comparison.json`.

Every free-text string is prefixed with "FIXTURE:" so it can never be mistaken for real
filing text. The fixture is for frontend development only and MUST NOT appear in
`data/published/` (the publisher refuses `is_fixture == True`).

Usage: uv run python contract/fixtures/make_fixture.py
"""

from __future__ import annotations

import difflib
import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipeline.schema import (  # noqa: E402
    CATEGORIES,
    CHANGE_TYPES,
    SCHEMA_VERSION,
    Comparison,
    canonical_json,
)

F = "FIXTURE: "
OLD_ACC = "0000000000-24-000001"
NEW_ACC = "0000000000-25-000001"
TOKEN_RE = re.compile(r"\s+|\w+|[^\w\s]")


def word_spans(old: str, new: str) -> tuple[list[dict], list[dict]]:
    a, b = TOKEN_RE.findall(old), TOKEN_RE.findall(new)
    sm = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    old_spans: list[dict] = []
    new_spans: list[dict] = []

    def push(spans: list[dict], op: str, text: str) -> None:
        if not text:
            return
        if spans and spans[-1]["op"] == op:
            spans[-1]["text"] += text
        else:
            spans.append({"op": op, "text": text})

    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            push(old_spans, "equal", "".join(a[i1:i2]))
            push(new_spans, "equal", "".join(b[j1:j2]))
        if tag in ("delete", "replace"):
            push(old_spans, "delete", "".join(a[i1:i2]))
        if tag in ("insert", "replace"):
            push(new_spans, "insert", "".join(b[j1:j2]))
    return old_spans, new_spans


class Filing:
    def __init__(self, acc: str, side: str):
        self.acc = acc
        self.side = side
        self.blocks: list[dict] = []
        self.cursor = 0
        self.index: dict[str, dict] = {}

    def block(self, heading: str, sentences: list[str], group: str) -> dict:
        bi = len(self.blocks)
        bid = f"{self.acc}:{bi}"
        ids: list[str] = []
        texts = [heading] + sentences
        for si, text in enumerate(texts):
            sid = f"{bid}:{si}"
            start = self.cursor
            end = start + len(text)
            self.cursor = end + 1
            self.index[sid] = {
                "id": sid,
                "accession_number": self.acc,
                "side": self.side,
                "block_id": bid,
                "text": text,
                "char_start": start,
                "char_end": end,
                "is_heading": si == 0,
            }
            ids.append(sid)
        b = {"id": bid, "heading": heading, "sentences": texts, "ids": ids, "group": group}
        self.blocks.append(b)
        return b


def wc(s: str) -> int:
    return len(s.split())


def build_change(
    old_b: dict | None,
    new_b: dict | None,
    alignment: list[tuple[int | None, int | None]],
    change_type: str,
    categories: list[str],
    similarity: float | None,
    heading_sim: float | None,
    body_sim: float | None,
    signals: dict,
    score_lines: list[dict],
    interpretation: dict,
) -> dict:
    sentences: list[dict] = []
    stats = dict(
        added=0, removed=0, modified=0, unchanged=0, added_word_count=0, removed_word_count=0
    )
    for pair_index, (oi, ni) in enumerate(alignment):
        o = old_b["sentences"][oi] if (old_b and oi is not None) else None
        n = new_b["sentences"][ni] if (new_b and ni is not None) else None
        oid = old_b["ids"][oi] if (old_b and oi is not None) else None
        nid = new_b["ids"][ni] if (new_b and ni is not None) else None
        if o is not None and n is not None:
            if o == n:
                status = "unchanged"
                stats["unchanged"] += 1
                sentences.append(
                    dict(
                        id=oid,
                        side="old",
                        status=status,
                        text=o,
                        pair_index=pair_index,
                        counterpart_id=nid,
                        alignment_similarity=1.0,
                    )
                )
                sentences.append(
                    dict(
                        id=nid,
                        side="new",
                        status=status,
                        text=n,
                        pair_index=pair_index,
                        counterpart_id=oid,
                        alignment_similarity=1.0,
                    )
                )
            else:
                status = "modified"
                stats["modified"] += 1
                os_, ns_ = word_spans(o, n)
                stats["removed_word_count"] += sum(
                    wc(s["text"]) for s in os_ if s["op"] == "delete"
                )
                stats["added_word_count"] += sum(wc(s["text"]) for s in ns_ if s["op"] == "insert")
                sentences.append(
                    dict(
                        id=oid,
                        side="old",
                        status=status,
                        text=o,
                        pair_index=pair_index,
                        counterpart_id=nid,
                        alignment_similarity=0.82,
                        diff_spans=os_,
                    )
                )
                sentences.append(
                    dict(
                        id=nid,
                        side="new",
                        status=status,
                        text=n,
                        pair_index=pair_index,
                        counterpart_id=oid,
                        alignment_similarity=0.82,
                        diff_spans=ns_,
                    )
                )
        elif o is not None:
            stats["removed"] += 1
            stats["removed_word_count"] += wc(o)
            sentences.append(
                dict(id=oid, side="old", status="removed", text=o, pair_index=pair_index)
            )
        else:
            stats["added"] += 1
            stats["added_word_count"] += wc(n)
            sentences.append(
                dict(id=nid, side="new", status="added", text=n, pair_index=pair_index)
            )

    old_text = "\n".join(old_b["sentences"]) if old_b else None
    new_text = "\n".join(new_b["sentences"]) if new_b else None
    old_wc = wc(old_text) if old_text else 0
    new_wc = wc(new_text) if new_text else 0
    key = f"{old_b['id'] if old_b else ''}|{new_b['id'] if new_b else ''}"
    cid = hashlib.sha256(key.encode()).hexdigest()[:16]
    title = (new_b or old_b)["heading"]
    score = min(100, sum(line["points"] for line in score_lines))
    return dict(
        id=cid,
        rank=0,
        title=title,
        old_title=old_b["heading"] if old_b else None,
        new_title=new_b["heading"] if new_b else None,
        section_group=(new_b or old_b)["group"],
        change_type=change_type,
        categories=categories,
        score=score,
        score_breakdown=score_lines,
        similarity=similarity,
        heading_similarity=heading_sim,
        body_similarity=body_sim,
        old_block_id=old_b["id"] if old_b else None,
        new_block_id=new_b["id"] if new_b else None,
        old_text=old_text,
        new_text=new_text,
        sentences=sentences,
        stats=dict(
            old_sentence_count=len(old_b["sentences"]) if old_b else 0,
            new_sentence_count=len(new_b["sentences"]) if new_b else 0,
            added=stats["added"],
            removed=stats["removed"],
            modified=stats["modified"],
            unchanged=stats["unchanged"],
            old_word_count=old_wc,
            new_word_count=new_wc,
            added_word_count=stats["added_word_count"],
            removed_word_count=stats["removed_word_count"],
        ),
        signals=dict(
            hypothetical_to_actual=signals.get("h2a", []),
            new_entities=signals.get("ent", []),
            new_quantities=signals.get("qty", []),
            added_text_ratio=round(stats["added_word_count"] / max(1, new_wc), 4)
            if new_wc
            else 0.0,
            removed_text_ratio=round(stats["removed_word_count"] / max(1, old_wc), 4)
            if old_wc
            else 0.0,
            semantic_shift=round(1 - similarity, 4) if similarity is not None else 0.0,
            category_scores=signals.get("cat", {}),
        ),
        interpretation=interpretation,
    )


def main() -> int:
    old = Filing(OLD_ACC, "old")
    new = Filing(NEW_ACC, "new")
    G_BUS = F + "Risks Related to Our Business and Industry"
    G_REG = F + "Risks Related to Regulation and Legal Matters"
    G_FIN = F + "Risks Related to Financial Matters"

    # --- Block pair 1: expanded supply chain risk (old 0 <-> new 0) ---
    o1 = old.block(
        F + "We depend on a limited number of third-party foundries to manufacture our widgets.",
        [
            F
            + "We do not own manufacturing facilities and rely on a small number of foundries located in Westland and Eastland.",
            F
            + "A disruption at any of these foundries could delay shipments and increase our costs.",
            F
            + "Natural disasters, political instability, or trade restrictions may affect our suppliers.",
            F
            + "We attempt to mitigate these risks by maintaining safety stock, but our efforts may not be sufficient.",
        ],
        G_BUS,
    )
    n1 = new.block(
        F + "We depend on a limited number of third-party foundries to manufacture our widgets.",
        [
            F
            + "We do not own manufacturing facilities and rely on a small number of foundries located in Westland, Eastland, and Ruritania.",
            F
            + "A disruption at any of these foundries could delay shipments and increase our costs.",
            F
            + "In fiscal 2025, export restrictions imposed by the Ruritanian government resulted in a shipment delay that reduced our revenue by approximately $1.2 billion.",
            F
            + "Natural disasters, political instability, or trade restrictions have affected and may continue to affect our suppliers.",
            F
            + "We attempt to mitigate these risks by maintaining safety stock, but our efforts may not be sufficient.",
            F
            + "We are qualifying an additional foundry in Northland, which we expect to take at least 18 months.",
        ],
        G_BUS,
    )
    # --- Block pair 2: cybersecurity reworded (old 1 <-> new 1) ---
    o2 = old.block(
        F + "Security breaches could harm our business.",
        [
            F
            + "Our systems may be vulnerable to computer viruses, break-ins, and similar disruptions.",
            F
            + "A breach could result in the loss of confidential information and damage to our reputation.",
            F + "We may incur significant costs to remediate security incidents.",
        ],
        G_BUS,
    )
    n2 = new.block(
        F
        + "Cybersecurity incidents, including ransomware, could materially disrupt our operations.",
        [
            F
            + "Our information technology systems and those of our vendors are vulnerable to ransomware, phishing, and state-sponsored attacks.",
            F
            + "An incident could result in the loss or exposure of confidential information, regulatory penalties, and damage to our reputation.",
            F
            + "We may incur significant costs to remediate security incidents, and our insurance may not cover all losses.",
        ],
        G_BUS,
    )
    # --- Old-only block 3: removed acquisition risk ---
    o3 = old.block(
        F
        + "The pending acquisition of Gadgetron Inc. may not be completed on the expected timeline.",
        [
            F
            + "Completion of the acquisition is subject to regulatory approvals in the U.S. and the E.U., which may be delayed or denied.",
            F
            + "If the acquisition is not completed, we may be required to pay a termination fee of $450 million.",
        ],
        G_REG,
    )
    # --- New-only block 2: AI risk ---
    n3 = new.block(
        F
        + "Our use of artificial intelligence may create legal, regulatory, and reputational exposure.",
        [
            F
            + "We have begun to integrate machine learning features into our widget planning software.",
            F
            + "Laws governing artificial intelligence, such as the Westland AI Act, are evolving and may impose new obligations on us.",
            F
            + "If our models produce inaccurate or biased outputs, our customers may lose confidence in our products.",
        ],
        G_REG,
    )
    # --- Pair 4: reduced FX risk (old 3 <-> new 3) ---
    o4 = old.block(
        F + "Fluctuations in foreign currency exchange rates could adversely affect our results.",
        [
            F
            + "Approximately 40% of our revenue is denominated in currencies other than the U.S. dollar.",
            F
            + "We use forward contracts to hedge a portion of this exposure, but hedging may not be effective.",
            F
            + "A strengthening U.S. dollar would reduce the reported value of our international revenue.",
            F + "We do not hedge translation exposure for our subsidiaries in Southland.",
        ],
        G_FIN,
    )
    n4 = new.block(
        F + "Fluctuations in foreign currency exchange rates could adversely affect our results.",
        [
            F
            + "Approximately 30% of our revenue is denominated in currencies other than the U.S. dollar.",
            F
            + "We use forward contracts to hedge a portion of this exposure, but hedging may not be effective.",
        ],
        G_FIN,
    )
    # --- Pair 5: largely unchanged competition (old 4 <-> new 4) ---
    o5 = old.block(
        F + "The widget market is intensely competitive.",
        [
            F
            + "We compete with larger companies that have greater resources, e.g. Megacorp and Omnicorp.",
            F + "If we fail to compete effectively, our market share and margins could decline.",
        ],
        G_BUS,
    )
    n5 = new.block(
        F + "The widget market is intensely competitive.",
        [
            F
            + "We compete with larger companies that have greater resources, e.g. Megacorp and Omnicorp.",
            F + "If we fail to compete effectively, our market share and margins could decline.",
        ],
        G_BUS,
    )
    # --- Pair 6: tariffs expanded, interpretation unavailable (old 5 <-> new 5) ---
    o6 = old.block(
        F + "Changes in trade policy could increase our costs.",
        [
            F + "Tariffs on imported components could increase our cost of goods sold.",
            F + "We may be unable to pass these costs on to customers.",
        ],
        G_REG,
    )
    n6 = new.block(
        F
        + "Changes in trade policy, including tariffs, have increased and could further increase our costs.",
        [
            F
            + "Tariffs on imported components increased our cost of goods sold by approximately 3% in fiscal 2025.",
            F + "We may be unable to pass these costs on to customers.",
            F
            + "Additional tariffs announced by the Westland Trade Commission in March 2025 could apply to our products.",
        ],
        G_REG,
    )

    def sids(b: dict, *idx: int) -> list[str]:
        return [b["ids"][i] for i in idx]

    Q = {
        "Q1": F
        + "Does the new text describe an event or condition that has already occurred, where the old text described it as a possibility?",
        "Q2": F
        + "Does the new text name a specific geography, government, regulation, or counterparty not named in the old text?",
        "Q3": F
        + "Does the new text state or quantify a financial or operational impact not stated in the old text?",
        "Q4": F + "Does the change narrow or remove a previously disclosed exposure?",
    }

    def rubric(answers: dict[str, tuple[bool, list[str]]]) -> list[dict]:
        return [
            dict(
                question_id=q,
                question=Q[q],
                answer=a,
                cited_sentence_ids=c,
                rationale=F + "short rationale",
                raw_answer=a,
            )
            for q, (a, c) in answers.items()
        ]

    changes = []
    changes.append(
        build_change(
            o1,
            n1,
            [(0, 0), (1, 1), (2, 2), (None, 3), (3, 4), (4, 5), (None, 6)],
            "expanded",
            ["supply_chain", "geopolitical"],
            0.91,
            1.0,
            0.87,
            dict(
                h2a=[
                    dict(
                        value=F + "may affect -> have affected",
                        detail=F + "Hedged verb became an actual past-tense statement.",
                        old_sentence_ids=sids(o1, 3),
                        new_sentence_ids=sids(n1, 4),
                    )
                ],
                ent=[
                    dict(
                        value=F + "Ruritania",
                        detail=F + "Geography (GPE) not present in the old text.",
                        new_sentence_ids=sids(n1, 1, 3),
                    ),
                    dict(
                        value=F + "Northland",
                        detail=F + "Geography (GPE) not present in the old text.",
                        new_sentence_ids=sids(n1, 6),
                    ),
                ],
                qty=[
                    dict(
                        value=F + "$1.2 billion",
                        detail=F + "Dollar amount not present in the old text.",
                        new_sentence_ids=sids(n1, 3),
                    ),
                    dict(
                        value=F + "18 months",
                        detail=F + "Duration not present in the old text.",
                        new_sentence_ids=sids(n1, 6),
                    ),
                ],
                cat={"supply_chain": 0.71, "geopolitical": 0.58, "macroeconomic": 0.31},
            ),
            [
                dict(
                    signal="change_type",
                    label=F + "Risk was expanded",
                    points=15,
                    detail=F + "2 sentences added, 1 modified",
                    cited_sentence_ids=sids(n1, 3, 6),
                ),
                dict(
                    signal="hypothetical_to_actual",
                    label=F + "Hedged language became actual language",
                    points=20,
                    detail=F + "'may affect' -> 'have affected'",
                    cited_sentence_ids=sids(o1, 3) + sids(n1, 4),
                ),
                dict(
                    signal="new_entities",
                    label=F + "New named entities",
                    points=10,
                    detail=F + "Ruritania, Northland",
                    cited_sentence_ids=sids(n1, 1, 6),
                ),
                dict(
                    signal="new_quantities",
                    label=F + "New quantified impact",
                    points=15,
                    detail=F + "$1.2 billion",
                    cited_sentence_ids=sids(n1, 3),
                ),
                dict(
                    signal="rubric_q1",
                    label=F + "AI rubric: possibility became an occurred event",
                    points=10,
                    cited_sentence_ids=sids(n1, 3),
                ),
                dict(
                    signal="rubric_q3",
                    label=F + "AI rubric: newly quantified impact",
                    points=10,
                    cited_sentence_ids=sids(n1, 3),
                ),
            ],
            dict(
                status="ok",
                model_id="FIXTURE: fake/model-id",
                reason=None,
                rubric=rubric(
                    {
                        "Q1": (True, sids(n1, 3)),
                        "Q2": (True, sids(n1, 1)),
                        "Q3": (True, sids(n1, 3)),
                        "Q4": (False, []),
                    }
                ),
                claims=[
                    dict(
                        text=F
                        + "The new filing reports that Ruritanian export restrictions caused a shipment delay with a stated revenue effect, which the prior filing framed only as a possibility.",
                        cited_sentence_ids=sids(o1, 3) + sids(n1, 3),
                    ),
                    dict(
                        text=F
                        + "The company now names a third manufacturing country and discloses an 18-month timeline to qualify an additional foundry.",
                        cited_sentence_ids=sids(n1, 1, 6),
                    ),
                ],
                dropped_claim_count=1,
                dropped_reasons=[F + "claim 3 dropped: cited sentence id not in sentence_index"],
            ),
        )
    )
    changes.append(
        build_change(
            o2,
            n2,
            [(0, 0), (1, 1), (2, 2), (3, 3)],
            "materially_reworded",
            ["cybersecurity"],
            0.74,
            0.69,
            0.76,
            dict(
                ent=[
                    dict(
                        value=F + "state-sponsored attacks",
                        detail=F + "Threat actor category not present in the old text.",
                        new_sentence_ids=sids(n2, 1),
                    )
                ],
                cat={"cybersecurity": 0.83, "regulation": 0.22},
            ),
            [
                dict(
                    signal="change_type",
                    label=F + "Risk was materially reworded",
                    points=20,
                    detail=F + "4 of 4 sentences modified",
                    cited_sentence_ids=sids(n2, 0, 1, 2, 3),
                ),
                dict(
                    signal="semantic_shift",
                    label=F + "Meaning shifted noticeably",
                    points=8,
                    detail=F + "similarity 0.74",
                    cited_sentence_ids=sids(n2, 0),
                ),
                dict(
                    signal="rubric_q2",
                    label=F + "AI rubric: new specific counterparty or regulation",
                    points=10,
                    cited_sentence_ids=sids(n2, 1),
                ),
            ],
            dict(
                status="ok",
                model_id="FIXTURE: fake/model-id",
                reason=None,
                rubric=rubric(
                    {
                        "Q1": (False, []),
                        "Q2": (True, sids(n2, 1)),
                        "Q3": (False, []),
                        "Q4": (False, []),
                    }
                ),
                claims=[
                    dict(
                        text=F
                        + "The heading and body now name specific attack types (ransomware, phishing, state-sponsored) and extend the scope to vendors' systems.",
                        cited_sentence_ids=sids(n2, 0, 1),
                    )
                ],
                dropped_claim_count=0,
                dropped_reasons=[],
            ),
        )
    )
    changes.append(
        build_change(
            None,
            n3,
            [(None, 0), (None, 1), (None, 2), (None, 3)],
            "new",
            ["artificial_intelligence", "regulation"],
            None,
            None,
            None,
            dict(
                ent=[
                    dict(
                        value=F + "Westland AI Act",
                        detail=F + "Law/regulation named only in the new filing.",
                        new_sentence_ids=sids(n3, 2),
                    )
                ],
                cat={"artificial_intelligence": 0.88, "regulation": 0.52},
            ),
            [
                dict(
                    signal="change_type",
                    label=F + "New risk factor",
                    points=30,
                    detail=F + "No counterpart in the prior filing",
                    cited_sentence_ids=sids(n3, 0),
                ),
                dict(
                    signal="new_entities",
                    label=F + "New named entities",
                    points=10,
                    detail=F + "Westland AI Act",
                    cited_sentence_ids=sids(n3, 2),
                ),
                dict(
                    signal="rubric_q2",
                    label=F + "AI rubric: new specific regulation",
                    points=10,
                    cited_sentence_ids=sids(n3, 2),
                ),
            ],
            dict(
                status="ok",
                model_id="FIXTURE: fake/model-id",
                reason=None,
                rubric=rubric(
                    {
                        "Q1": (False, []),
                        "Q2": (True, sids(n3, 2)),
                        "Q3": (False, []),
                        "Q4": (False, []),
                    }
                ),
                claims=[
                    dict(
                        text=F
                        + "This is an entirely new risk factor; it cites a named AI law and ties the exposure to machine learning features in the company's software.",
                        cited_sentence_ids=sids(n3, 1, 2),
                    )
                ],
                dropped_claim_count=0,
                dropped_reasons=[],
            ),
        )
    )
    changes.append(
        build_change(
            o3,
            None,
            [(0, None), (1, None), (2, None)],
            "removed",
            ["litigation", "regulation"],
            None,
            None,
            None,
            dict(cat={"regulation": 0.61, "litigation": 0.44}),
            [
                dict(
                    signal="change_type",
                    label=F + "Risk factor removed",
                    points=20,
                    detail=F + "No counterpart in the new filing",
                    cited_sentence_ids=sids(o3, 0),
                )
            ],
            dict(
                status="ok",
                model_id="FIXTURE: fake/model-id",
                reason=None,
                rubric=rubric(
                    {
                        "Q1": (False, []),
                        "Q2": (False, []),
                        "Q3": (False, []),
                        "Q4": (True, sids(o3, 0)),
                    }
                ),
                claims=[
                    dict(
                        text=F
                        + "The prior filing's acquisition-related risk, including a stated termination fee, no longer appears.",
                        cited_sentence_ids=sids(o3, 0, 2),
                    )
                ],
                dropped_claim_count=0,
                dropped_reasons=[],
            ),
        )
    )
    changes.append(
        build_change(
            o4,
            n4,
            [(0, 0), (1, 1), (2, 2), (3, None), (4, None)],
            "reduced",
            ["foreign_exchange"],
            0.86,
            1.0,
            0.80,
            dict(
                qty=[
                    dict(
                        value=F + "30%",
                        detail=F + "Percentage changed from 40% to 30%.",
                        old_sentence_ids=sids(o4, 1),
                        new_sentence_ids=sids(n4, 1),
                    )
                ],
                cat={"foreign_exchange": 0.9},
            ),
            [
                dict(
                    signal="change_type",
                    label=F + "Risk was reduced",
                    points=10,
                    detail=F + "2 sentences removed",
                    cited_sentence_ids=sids(o4, 3, 4),
                ),
                dict(
                    signal="new_quantities",
                    label=F + "Changed quantity",
                    points=5,
                    detail=F + "40% -> 30%",
                    cited_sentence_ids=sids(n4, 1),
                ),
            ],
            dict(
                status="empty",
                model_id="FIXTURE: fake/model-id",
                reason=F + "all 2 claims dropped by the citation validator",
                rubric=rubric(
                    {"Q1": (False, []), "Q2": (False, []), "Q3": (False, []), "Q4": (False, [])}
                ),
                claims=[],
                dropped_claim_count=2,
                dropped_reasons=[
                    F + "claim 1 dropped: banned language ('likely')",
                    F + "claim 2 dropped: no citations",
                ],
            ),
        )
    )
    changes.append(
        build_change(
            o6,
            n6,
            [(0, 0), (1, 1), (2, 2), (None, 3)],
            "expanded",
            ["regulation", "macroeconomic"],
            0.84,
            0.78,
            0.86,
            dict(
                h2a=[
                    dict(
                        value=F + "could increase -> have increased",
                        detail=F + "Heading moved from hedged to actual.",
                        old_sentence_ids=sids(o6, 0),
                        new_sentence_ids=sids(n6, 0),
                    )
                ],
                ent=[
                    dict(
                        value=F + "Westland Trade Commission",
                        detail=F + "Government body named only in the new filing.",
                        new_sentence_ids=sids(n6, 3),
                    )
                ],
                qty=[
                    dict(
                        value=F + "3%",
                        detail=F + "Percentage not present in the old text.",
                        new_sentence_ids=sids(n6, 1),
                    )
                ],
                cat={"regulation": 0.66, "macroeconomic": 0.49},
            ),
            [
                dict(
                    signal="change_type",
                    label=F + "Risk was expanded",
                    points=15,
                    detail=F + "1 sentence added, 2 modified",
                    cited_sentence_ids=sids(n6, 3),
                ),
                dict(
                    signal="hypothetical_to_actual",
                    label=F + "Hedged language became actual language",
                    points=20,
                    detail=F + "'could increase' -> 'have increased'",
                    cited_sentence_ids=sids(o6, 0) + sids(n6, 0),
                ),
                dict(
                    signal="new_quantities",
                    label=F + "New quantified impact",
                    points=15,
                    detail=F + "3%",
                    cited_sentence_ids=sids(n6, 1),
                ),
            ],
            dict(
                status="unavailable",
                model_id=None,
                reason=F + "LLM stage unavailable: no provider configured",
                rubric=[],
                claims=[],
                dropped_claim_count=0,
                dropped_reasons=[],
            ),
        )
    )
    changes.append(
        build_change(
            o5,
            n5,
            [(0, 0), (1, 1), (2, 2)],
            "largely_unchanged",
            ["competition"],
            1.0,
            1.0,
            1.0,
            dict(cat={"competition": 0.93}),
            [],
            dict(
                status="skipped",
                model_id=None,
                reason=F + "not run for largely_unchanged risks",
                rubric=[],
                claims=[],
                dropped_claim_count=0,
                dropped_reasons=[],
            ),
        )
    )

    changes.sort(key=lambda c: (-c["score"], c["id"]))
    for i, c in enumerate(changes, start=1):
        c["rank"] = i

    by_type = {t: 0 for t in CHANGE_TYPES}
    by_cat = {c: 0 for c in CATEGORIES}
    for c in changes:
        by_type[c["change_type"]] += 1
        for cat in c["categories"]:
            by_cat[cat] += 1

    sentence_index = {**old.index, **new.index}
    doc = dict(
        schema_version=SCHEMA_VERSION,
        analysis_id=hashlib.sha256(b"FIXTURE").hexdigest(),
        pipeline_version="FIXTURE",
        rubric_version="FIXTURE",
        model_ids=dict(
            embedding_model=F + "fake/embedding-model",
            embedding_backend="lexical-fallback",
            ner_model=F + "fake/ner-model",
            category_method=F + "fake-method",
            sentence_splitter=F + "fake-splitter",
            llm_provider=None,
            llm_model=None,
            prompt_sha256=None,
        ),
        is_fixture=True,
        company=dict(
            ticker="FIXTUR",
            name=F + "Example Widgets Corp (synthetic, not a real company)",
            cik="0000000000",
        ),
        old_filing=dict(
            accession_number=OLD_ACC,
            form="10-K",
            fiscal_year=2024,
            period_of_report="2024-01-28",
            filing_date="2024-02-21",
            primary_document="FIXTURE-fixtur-20240128.htm",
            edgar_url="https://www.sec.gov/FIXTURE/not-a-real-filing-2024",
            edgar_index_url="https://www.sec.gov/FIXTURE/not-a-real-index-2024",
            is_amendment=False,
            item_1a_word_count=sum(wc(s) for b in old.blocks for s in b["sentences"]),
            item_1a_char_count=old.cursor,
            block_count=len(old.blocks),
            section_groups=[G_BUS, G_REG, G_FIN],
        ),
        new_filing=dict(
            accession_number=NEW_ACC,
            form="10-K",
            fiscal_year=2025,
            period_of_report="2025-01-26",
            filing_date="2025-02-26",
            primary_document="FIXTURE-fixtur-20250126.htm",
            edgar_url="https://www.sec.gov/FIXTURE/not-a-real-filing-2025",
            edgar_index_url="https://www.sec.gov/FIXTURE/not-a-real-index-2025",
            is_amendment=False,
            item_1a_word_count=sum(wc(s) for b in new.blocks for s in b["sentences"]),
            item_1a_char_count=new.cursor,
            block_count=len(new.blocks),
            section_groups=[G_BUS, G_REG, G_FIN],
        ),
        filing_selection_note=F
        + "two most recent original 10-K filings; amendments (10-K/A) excluded",
        summary=dict(
            total_changes=len(changes),
            by_change_type=by_type,
            by_category=by_cat,
            old_block_count=len(old.blocks),
            new_block_count=len(new.blocks),
            matched_pairs=sum(1 for c in changes if c["old_block_id"] and c["new_block_id"]),
            interpretation_status="ok",
            max_score=max(c["score"] for c in changes),
        ),
        thresholds=dict(
            match_threshold=0.55,
            heading_weight=0.4,
            body_weight=0.6,
            sentence_match_threshold=0.6,
            sentence_unchanged_threshold=0.98,
            expanded_ratio=0.25,
            reworded_similarity=0.8,
        ),
        changes=changes,
        sentence_index=sentence_index,
        notes=[
            F + "This is synthetic development data. It is not derived from any SEC filing.",
            F
            + "Not investment advice. RiskDiff shows changes in disclosed risk language, not changes in actual risk.",
        ],
    )
    comp = Comparison.model_validate(doc)
    out = ROOT / "contract" / "fixtures" / "FIXTURE_comparison.json"
    out.write_text(canonical_json(comp))
    print(
        f"wrote {out.relative_to(ROOT)} ({len(comp.changes)} changes, {len(comp.sentence_index)} sentences)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
