"""Stage 6: deterministic, cited signals per change.

- hypothetical_to_actual: hedged wording in the old text ("may", "could", "might", "potential")
  that became actual/past-tense wording in the corresponding new text ("has/have + participle",
  "resulted in", "experienced", "incurred"); a modal right before the marker ("could have
  disrupted") does not count. Detected (a) inside aligned modified sentence pairs via the word-level
  diff (deleted hedge + inserted actual marker) and (b) for added sentences that report an event
  with a year/past-tense marker and overlap lexically with a hedged old sentence.
- new_entities: spaCy NER (en_core_web_sm) entities of type GPE/NORP/ORG/LAW/LOC/EVENT/FAC in the
  new block that do not appear in the old block.
- new_quantities: dollar amounts, percentages, and counted units present in the new block but
  not the old; changed numbers inside aligned sentences are reported as "old -> new".
- added_text_ratio / removed_text_ratio / semantic_shift (= 1 - pair similarity).
- category: hybrid of a keyword lexicon (always) and embedding similarity to category prototype
  descriptions (when a dense embedder is available). The method used is recorded in model_ids.

Every hit cites the sentence ids that triggered it.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from pipeline.diff import lexical_ratio
from pipeline.schema import CATEGORIES, Sentence, SignalHit, Signals
from pipeline.types import RiskBlock

log = logging.getLogger(__name__)

STAGE_VERSION = "0.1.2"
LEXICON_METHOD_ID = "keyword-lexicon-v1"

HEDGE_RE = re.compile(
    r"\b(may|could|might|would|potential|potentially|possible|possibly|possibility)\b", re.I
)
ACTUAL_RE = re.compile(
    r"\b(has|have|had)\s+(?:\w+\s+){0,2}?(been|resulted|experienced|incurred|caused|led|affected|impacted|"
    r"increased|decreased|reduced|disrupted|delayed|suspended|terminated|recorded|recognized|imposed|"
    r"announced|filed|adopted|enacted|occurred|materially)\b|"
    r"\b(resulted in|experienced|incurred|has occurred|have occurred)\b",
    re.I,
)
PAST_EVENT_RE = re.compile(
    r"\b(resulted in|experienced|incurred|imposed|announced|filed|adopted|enacted|occurred|caused|led to|"
    r"reduced|increased|decreased|disrupted|delayed|suspended|terminated|recorded|recognized)\b",
    re.I,
)
YEAR_RE = re.compile(
    r"\b(?:fiscal|calendar|in|during|since)\s+(?:year\s+)?(?:19|20)\d{2}\b|\b(?:19|20)\d{2}\b"
)

MONEY_RE = re.compile(
    r"\$\s?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?:\s*(?:thousand|million|billion|trillion))?", re.I
)
PERCENT_RE = re.compile(r"\b\d+(?:\.\d+)?\s?(?:%|percent)", re.I)
UNIT_RE = re.compile(
    r"\b\d[\d,]*(?:\.\d+)?\s+(?:employees|customers|countries|days|months|years|patents|facilities|"
    r"square feet|basis points|units|suppliers|foundries|lawsuits|incidents|locations|stores|vehicles)\b",
    re.I,
)
BIGNUM_RE = re.compile(r"\b\d{1,3}(?:,\d{3})+\b")
NUMBER_TOKEN_RE = re.compile(r"\$?\d[\d,]*(?:\.\d+)?%?")

ENTITY_LABELS = frozenset({"GPE", "NORP", "ORG", "LAW", "LOC", "EVENT", "FAC"})

# (pattern, weight). Multi-word phrases weigh more than single words.
LEXICON: dict[str, list[tuple[str, int]]] = {
    "geopolitical": [
        (r"geopolitic\w*", 2),
        (r"\bwar\b|\bwars\b|armed conflict|military", 2),
        (r"sanction\w*", 2),
        (r"taiwan|china|chinese|russia|ukraine|israel|middle east|hong kong", 2),
        (r"export control\w*|export restriction\w*|trade restriction\w*", 2),
        (r"political instability|political (?:unrest|tension\w*)|terroris\w+", 2),
        (r"\btariff\w*", 1),
    ],
    "supply_chain": [
        (r"supply chain\w*", 3),
        (r"supplier\w*", 2),
        (r"foundr(?:y|ies)|contract manufacturer\w*|manufactur\w+", 1),
        (r"component\w*|raw material\w*", 1),
        (r"shortage\w*|allocation|lead time\w*", 2),
        (r"logistics|shipping|freight|inventory", 1),
        (r"sole[- ]source|single[- ]source|limited number of (?:suppliers|foundries|sources)", 3),
    ],
    "regulation": [
        (r"regulat\w+", 2),
        (r"\blaws?\b|legislation|legislative", 1),
        (r"compliance|comply", 1),
        (r"government\w*|regulator\w*|agenc(?:y|ies)|authorit(?:y|ies)", 1),
        (r"antitrust|competition law|privacy law\w*|gdpr|data protection", 2),
        (r"licen[sc]\w+|permit\w*", 1),
        (r"\bact\b|\brule\b|directive", 1),
    ],
    "cybersecurity": [
        (r"cyber\w*", 3),
        (r"security (?:breach|incident)\w*|data breach\w*", 3),
        (r"ransomware|malware|phishing|hacker\w*|denial[- ]of[- ]service", 3),
        (r"unauthorized access|information technology|it systems|networks?", 1),
        (r"vulnerabilit\w+|intrusion\w*|exploit\w*", 1),
    ],
    "customer_concentration": [
        (r"(?:small|limited) number of (?:our )?customers", 4),
        (r"largest customers?|significant customers?|key customers?|major customers?", 3),
        (r"concentrat\w+ of (?:our )?(?:customers|revenue|sales)", 3),
        (r"accounted for (?:approximately )?\d+%", 2),
        (r"loss of (?:any|one|a) (?:of these |significant |major |key )?customers?", 3),
        (r"\bcustomers?\b", 0),
    ],
    "competition": [
        (r"compet\w+", 3),
        (r"market share", 2),
        (r"pricing pressure\w*|price (?:reduction|erosion|competition)", 2),
        (r"new entrants?|substitute\w*", 2),
    ],
    "liquidity": [
        (r"liquidity", 3),
        (r"indebtedness|\bdebt\b|borrowing\w*|notes outstanding|senior notes", 2),
        (r"credit facilit\w+|covenant\w*|revolving", 2),
        (r"cash flows?|financing|capital markets|capital resources", 1),
        (r"dividend\w*|repurchase\w*|buyback\w*", 1),
    ],
    "credit": [
        (r"credit risk\w*|credit loss\w*|credit quality", 3),
        (r"counterpart\w+", 2),
        (r"default\w*|delinquen\w+|nonperforming|non-performing|charge-offs?", 2),
        (r"receivable\w*|collateral|creditworth\w+|borrower\w*|loan portfolio|loans?\b", 2),
        (r"allowance for (?:credit|loan) losses", 3),
    ],
    "interest_rates": [
        (r"interest rates?", 4),
        (r"federal reserve|monetary policy|central bank\w*", 2),
        (r"net interest (?:income|margin)", 3),
        (r"\byield\w*", 1),
        (r"rate (?:increase|decrease|hike|cut)\w*", 2),
    ],
    "foreign_exchange": [
        (r"foreign (?:currency|exchange)", 4),
        (r"exchange rates?", 3),
        (r"currenc(?:y|ies)", 2),
        (r"u\.s\. dollar|dollar strength\w*|strengthening (?:of the )?(?:u\.s\. )?dollar", 2),
        (r"hedg\w+|forward contracts?", 1),
        (r"translation", 1),
    ],
    "artificial_intelligence": [
        (r"artificial intelligence", 4),
        (r"\bai\b|\bgenai\b|generative", 3),
        (r"machine learning|large language model\w*|\bllm\w*|neural network\w*|deep learning", 3),
        (r"algorithm\w*|training data|\bmodels?\b", 1),
        (r"ai act|ai regulation\w*", 2),
    ],
    "intellectual_property": [
        (r"intellectual property", 4),
        (r"patent\w*", 3),
        (r"trademark\w*|copyright\w*|trade secret\w*", 2),
        (r"infring\w+", 3),
        (r"licens\w+", 1),
    ],
    "labor": [
        (r"employee\w*|personnel|workforce|talent|labor|labour", 2),
        (r"attract(?:ing)? and retain\w*|retention|hiring|recruit\w*", 3),
        (r"key (?:personnel|employees|executives|management)|senior management", 2),
        (r"union\w*|strike\w*|work stoppage\w*|collective bargaining", 3),
        (r"compensation|equity awards?|stock-based", 1),
    ],
    "climate": [
        (r"climate", 4),
        (r"greenhouse gas\w*|emission\w*|carbon", 3),
        (
            r"natural disaster\w*|extreme weather|flood\w*|wildfire\w*|hurricane\w*|earthquake\w*|drought\w*",
            2,
        ),
        (r"sustainab\w+|\besg\b|environmental", 2),
        (r"water (?:supply|scarcity|usage)", 2),
    ],
    "litigation": [
        (r"litigation|lawsuits?", 4),
        (r"legal proceeding\w*|class action\w*", 3),
        (r"\bclaims?\b|judgment\w*|settlement\w*|damages", 1),
        (r"court\w*|arbitration|indemnif\w+", 2),
        (r"investigation\w*|subpoena\w*|enforcement action\w*", 2),
    ],
    "macroeconomic": [
        (
            r"macroeconomic|economic conditions|economic (?:uncertainty|downturn|slowdown|environment)",
            4,
        ),
        (r"recession\w*|inflation\w*|downturn\w*", 3),
        (r"consumer (?:spending|demand|confidence)|demand for our products", 2),
        (r"unemployment|gdp|economy", 2),
        (r"\binterest rates?\b", 0),
    ],
}
_LEXICON_COMPILED = {c: [(re.compile(p, re.I), w) for p, w in pats] for c, pats in LEXICON.items()}

CATEGORY_PROTOTYPES: dict[str, str] = {
    "geopolitical": "Geopolitical risk: wars, armed conflicts, sanctions, export controls, trade restrictions, and political instability in countries where we operate or sell.",
    "supply_chain": "Supply chain risk: dependence on a limited number of suppliers or foundries, component shortages, manufacturing capacity, logistics and shipping disruptions.",
    "regulation": "Regulatory risk: changes in laws, regulations, government policy, licensing, and compliance obligations that could restrict our business or increase costs.",
    "cybersecurity": "Cybersecurity risk: security breaches, ransomware, phishing, unauthorized access to information technology systems, and loss of confidential data.",
    "customer_concentration": "Customer concentration risk: a small number of customers account for a significant portion of revenue, and the loss of a major customer would reduce sales.",
    "competition": "Competition risk: intense competition, loss of market share, pricing pressure, and competitors introducing superior or cheaper products.",
    "liquidity": "Liquidity and indebtedness risk: debt levels, covenants, access to capital markets, cash flow, and the ability to fund operations and dividends.",
    "credit": "Credit risk: counterparty defaults, loan losses, receivables collection, collateral values, and the creditworthiness of borrowers and customers.",
    "interest_rates": "Interest rate risk: changes in interest rates, central bank monetary policy, net interest margin, and the cost of borrowing.",
    "foreign_exchange": "Foreign exchange risk: fluctuations in currency exchange rates, a strengthening U.S. dollar, hedging effectiveness, and translation of international revenue.",
    "artificial_intelligence": "Artificial intelligence risk: developing and deploying AI and machine learning features, inaccurate or biased model outputs, and evolving AI laws.",
    "intellectual_property": "Intellectual property risk: patents, trademarks, trade secrets, infringement claims, licensing, and the inability to protect proprietary technology.",
    "labor": "Labor and human capital risk: attracting and retaining qualified employees and key personnel, compensation, unions, and workforce disruptions.",
    "climate": "Climate and environmental risk: extreme weather, natural disasters, greenhouse gas emissions regulation, sustainability requirements, and physical damage to facilities.",
    "litigation": "Litigation and legal risk: lawsuits, legal proceedings, class actions, government investigations, judgments, settlements, and indemnification obligations.",
    "macroeconomic": "Macroeconomic risk: recessions, inflation, economic downturns, weak consumer demand, and general economic uncertainty affecting demand for our products.",
    "other": "General business risk not covered by a specific category.",
}


@dataclass
class SignalContext:
    old: RiskBlock | None
    new: RiskBlock | None
    sentences: list[Sentence]
    similarity: float | None
    added_word_count: int
    removed_word_count: int
    old_word_count: int
    new_word_count: int


# ---------- hedge -> actual ----------


def _hedges(text: str) -> list[str]:
    return [m.group(0).lower() for m in HEDGE_RE.finditer(text)]


def _actuals(text: str) -> list[str]:
    return [m.group(0).lower() for m in ACTUAL_RE.finditer(text)]


def hypothetical_to_actual(ctx: SignalContext) -> list[SignalHit]:
    hits: list[SignalHit] = []
    if ctx.old is None or ctx.new is None:
        return hits
    by_id = {s.id: s for s in ctx.sentences}
    seen: set[tuple[str, str]] = set()
    # (a) modified pairs: the old sentence is hedged and the inserted text carries an actual
    #     marker ("have increased", "resulted in", ...), or a hedge was deleted and a past-event
    #     verb inserted while the new sentence is less hedged than the old one.
    for s in ctx.sentences:
        if s.side != "new" or s.status != "modified" or not s.counterpart_id:
            continue
        old_s = by_id.get(s.counterpart_id)
        if old_s is None or not old_s.diff_spans or not s.diff_spans:
            continue
        deleted = " ".join(sp.text for sp in old_s.diff_spans if sp.op == "delete")
        inserted = " ".join(sp.text for sp in s.diff_spans if sp.op == "insert")
        old_h = _hedges(old_s.text)
        if not old_h:
            continue
        a = _actuals(inserted)
        if a and _modal_before(s.text, a[0]):
            a = []  # "could have disrupted" / "may have been subject": still hypothetical
        if not a:
            del_h = _hedges(deleted)
            past = PAST_EVENT_RE.search(inserted)
            if del_h and past and len(_hedges(s.text)) < len(old_h):
                a = [past.group(0).lower()]
                old_h = del_h
        if a:
            key = (old_s.id, s.id)
            if key not in seen:
                seen.add(key)
                hits.append(
                    SignalHit(
                        value=f"{old_h[0]} -> {a[0]}",
                        detail="Hedged wording in the prior filing was replaced by actual/past-tense wording in the new filing.",
                        old_sentence_ids=[old_s.id],
                        new_sentence_ids=[s.id],
                    )
                )
    # (b) added sentence reporting a past event, overlapping a hedged old sentence
    old_hedged = [s for s in ctx.old.sentences if HEDGE_RE.search(s.text)]
    for s in ctx.sentences:
        if s.side != "new" or s.status != "added":
            continue
        if not (PAST_EVENT_RE.search(s.text) and YEAR_RE.search(s.text)) or HEDGE_RE.search(s.text):
            continue
        best, best_r = None, 0.0
        for o in old_hedged:
            r = lexical_ratio(o.text, s.text)
            if r > best_r:
                best, best_r = o, r
        if best is not None and best_r >= 0.25:
            key = (best.id, s.id)
            if key not in seen:
                seen.add(key)
                ev = PAST_EVENT_RE.search(s.text).group(0).lower()
                hits.append(
                    SignalHit(
                        value=f"{_hedges(best.text)[0]} -> {ev}",
                        detail="A possibility in the prior filing is reported as an event that occurred, in a newly added sentence.",
                        old_sentence_ids=[best.id],
                        new_sentence_ids=[s.id],
                    )
                )
    return hits


_MODAL_RE = re.compile(r"\b(may|might|could|would|should|can)\b", re.I)


def _modal_before(sentence: str, marker: str, window: int = 3) -> bool:
    """True when a modal verb sits within `window` tokens before `marker` in `sentence`."""
    low = sentence.lower()
    idx = low.find(marker.lower())
    if idx < 0:
        return False
    before = low[:idx].split()[-window:]
    return any(_MODAL_RE.fullmatch(t.strip(",;:()")) for t in before)


# ---------- entities ----------

_nlp = None


def get_nlp():
    global _nlp
    if _nlp is None:
        import spacy

        _nlp = spacy.load("en_core_web_sm", disable=["lemmatizer", "textcat"])
    return _nlp


def _norm_entity(text: str) -> str:
    t = re.sub(r"^(the|a|an)\s+", "", text.strip(), flags=re.I)
    t = re.sub(r"['’]s$", "", t)
    t = re.sub(r"\s+", " ", t).strip(" .,;:")
    return t.lower()


def entities_by_sentence(block: RiskBlock, nlp=None) -> dict[str, list[tuple[str, str]]]:
    """sentence id -> [(normalized entity, label)]"""
    nlp = nlp or get_nlp()
    out: dict[str, list[tuple[str, str]]] = {}
    texts = [s.text for s in block.sentences]
    for s, doc in zip(block.sentences, nlp.pipe(texts, batch_size=32), strict=True):
        ents = []
        for e in doc.ents:
            if e.label_ in ENTITY_LABELS:
                n = _norm_entity(e.text)
                if len(n) >= 3 and any(c.isalpha() for c in n) and not n.isdigit():
                    ents.append((n, e.label_))
        if ents:
            out[s.id] = ents
    return out


def new_entities(ctx: SignalContext, nlp=None) -> list[SignalHit]:
    if ctx.new is None:
        return []
    new_ents = entities_by_sentence(ctx.new, nlp)
    old_text = ctx.old.full_text.lower() if ctx.old else ""
    old_norm = set()
    if ctx.old:
        for ents in entities_by_sentence(ctx.old, nlp).values():
            old_norm.update(n for n, _ in ents)
    first_seen: dict[str, tuple[str, list[str]]] = {}
    for sid, ents in new_ents.items():
        for n, label in ents:
            if n in old_norm or (old_text and n in old_text):
                continue
            if n not in first_seen:
                first_seen[n] = (label, [sid])
            elif sid not in first_seen[n][1]:
                first_seen[n][1].append(sid)
    label_names = {
        "GPE": "Geography",
        "NORP": "Nationality/group",
        "ORG": "Organization",
        "LAW": "Law/regulation",
        "LOC": "Location",
        "EVENT": "Event",
        "FAC": "Facility",
    }
    hits = []
    for n, (label, sids) in sorted(first_seen.items()):
        display = _display_entity(ctx.new, sids[0], n)
        hits.append(
            SignalHit(
                value=display,
                detail=f"{label_names.get(label, label)} named in the new filing but not in the prior filing (spaCy {label}).",
                new_sentence_ids=sids,
            )
        )
    return hits


def _display_entity(block: RiskBlock, sid: str, norm: str) -> str:
    text = next((s.text for s in block.sentences if s.id == sid), "")
    m = re.search(re.escape(norm), text, flags=re.I)
    return m.group(0) if m else norm


# ---------- quantities ----------


def _quantities(text: str) -> list[str]:
    found: list[str] = []
    for rx in (MONEY_RE, PERCENT_RE, UNIT_RE, BIGNUM_RE):
        for m in rx.finditer(text):
            found.append(re.sub(r"\s+", " ", m.group(0)).strip())
    # drop bare big numbers that are part of money/percent matches
    out: list[str] = []
    for q in found:
        if BIGNUM_RE.fullmatch(q) and any(q in other and other != q for other in found):
            continue
        out.append(q)
    return out


def _norm_q(q: str) -> str:
    return q.lower().replace(" ", "").replace("percent", "%")


def new_quantities(ctx: SignalContext) -> list[SignalHit]:
    if ctx.new is None:
        return []
    old_qs = {
        _norm_q(q) for s in (ctx.old.sentences if ctx.old else []) for q in _quantities(s.text)
    }
    hits: list[SignalHit] = []
    seen: set[str] = set()
    by_id = {s.id: s for s in ctx.sentences}
    for s in ctx.sentences:
        if s.side != "new" or s.status not in ("added", "modified"):
            continue
        qs = _quantities(s.text)
        if not qs:
            continue
        old_s = by_id.get(s.counterpart_id) if s.counterpart_id else None
        new_norm = {_norm_q(x) for x in qs}
        # old numbers of the aligned sentence that disappeared; each may explain one new number
        unexplained_old = [
            oq for oq in (_quantities(old_s.text) if old_s else []) if _norm_q(oq) not in new_norm
        ]
        for q in qs:
            nq = _norm_q(q)
            if nq in old_qs or nq in seen:
                continue
            seen.add(nq)
            changed_from = None
            for k, oq in enumerate(unexplained_old):
                if _same_kind(oq, q):
                    changed_from = unexplained_old.pop(k)
                    break
            if changed_from:
                hits.append(
                    SignalHit(
                        value=f"{changed_from} -> {q}",
                        detail="A quantity in the aligned sentence changed.",
                        old_sentence_ids=[old_s.id],
                        new_sentence_ids=[s.id],
                    )
                )
            else:
                hits.append(
                    SignalHit(
                        value=q,
                        detail="Quantity present in the new filing but not in the prior filing.",
                        new_sentence_ids=[s.id],
                    )
                )
    return hits


def _same_kind(a: str, b: str) -> bool:
    return (a.startswith("$") == b.startswith("$")) and (
        ("%" in a or "percent" in a.lower()) == ("%" in b or "percent" in b.lower())
    )


# ---------- categories ----------


def lexicon_scores(text: str) -> dict[str, float]:
    raw: dict[str, float] = {}
    for cat, pats in _LEXICON_COMPILED.items():
        score = 0.0
        for rx, w in pats:
            if w <= 0:
                continue
            score += w * len(rx.findall(text))
        raw[cat] = score
    total = sum(raw.values())
    if total <= 0:
        return {c: 0.0 for c in CATEGORIES}
    out = {c: raw.get(c, 0.0) / total for c in CATEGORIES}
    return out


def categorize(
    text: str, dense_scores: dict[str, float] | None = None
) -> tuple[list[str], dict[str, float]]:
    """Return (categories[1..2], scores). Hybrid of lexicon distribution and dense similarity."""
    lex = lexicon_scores(text)
    if dense_scores:
        vals = np.array([dense_scores.get(c, 0.0) for c in CATEGORIES if c != "other"])
        shifted = np.clip(vals - vals.min(), 0, None)
        dist = shifted / shifted.sum() if shifted.sum() > 0 else np.zeros_like(shifted)
        dense = dict(zip([c for c in CATEGORIES if c != "other"], dist.tolist(), strict=True))
        dense["other"] = 0.0
        scores = {c: 0.5 * lex[c] + 0.5 * dense[c] for c in CATEGORIES}
    else:
        scores = dict(lex)
    ranked = sorted(
        ((c, s) for c, s in scores.items() if c != "other"), key=lambda x: (-x[1], x[0])
    )
    top, top_s = ranked[0]
    cats: list[str] = []
    if top_s >= 0.12:
        cats.append(top)
        second, second_s = ranked[1]
        if second_s >= 0.18 and second_s >= 0.6 * top_s:
            cats.append(second)
    if not cats:
        cats = ["other"]
    return cats, {c: round(s, 4) for c, s in scores.items() if s > 0}


# ---------- assemble ----------


def compute_signals(
    ctx: SignalContext, dense_category_scores: dict[str, float] | None = None, nlp=None
) -> tuple[Signals, list[str]]:
    text = (ctx.new or ctx.old).full_text
    cats, cat_scores = categorize(text, dense_category_scores)
    sig = Signals(
        hypothetical_to_actual=hypothetical_to_actual(ctx),
        new_entities=new_entities(ctx, nlp),
        new_quantities=new_quantities(ctx),
        added_text_ratio=round(
            min(1.0, ctx.added_word_count / max(1, ctx.new_word_count))
            if ctx.new_word_count
            else 0.0,
            4,
        ),
        removed_text_ratio=round(
            min(1.0, ctx.removed_word_count / max(1, ctx.old_word_count))
            if ctx.old_word_count
            else 0.0,
            4,
        ),
        semantic_shift=round(max(0.0, 1.0 - ctx.similarity), 4)
        if ctx.similarity is not None
        else 0.0,
        category_scores=cat_scores,
    )
    return sig, cats


def dense_category_scorer(embedder) -> Callable[[str], dict[str, float]] | None:
    """Build a function text -> {category: cosine} using a dense embedder (None for lexical)."""
    if getattr(embedder, "backend", "") != "sentence-transformers":
        return None
    names = [c for c in CATEGORIES if c != "other"]
    protos = embedder.embed([CATEGORY_PROTOTYPES[c] for c in names])

    def score(text: str) -> dict[str, float]:
        v = embedder.embed([text])[0]
        sims = protos @ v
        return {c: float(s) for c, s in zip(names, sims, strict=True)}

    return score
