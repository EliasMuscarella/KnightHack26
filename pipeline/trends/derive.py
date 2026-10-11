"""Derive trend facts from one published report. Pure and deterministic (same report + same
TRENDS_VERSION/TOPICS_VERSION + same spaCy model -> byte-identical file); no LLM, no network.

A topic counts for a company only when it is NEWLY ADDED LANGUAGE (TRENDS_VERSION 1.2.0):
* the risk factor changed meaningfully (`change_type != "largely_unchanged"`): a small insertion in
  an essentially unchanged risk factor is never counted as a trend;
* at least one occurrence of the matched term (whole word, case-insensitive, `term_regex`) lies
  WHOLLY inside the inserted text of this year's sentence (the whole sentence for an added one, an
  insert span for a modified one), so words that were already there last year never count; and
* the term (and, for lexicon topics, every synonym of the topic) appears nowhere in that risk
  factor's last-year text (`last_year_text`: `change.old_text` plus the change's old-side
  sentences; the old-side sentences alone when `old_text` is absent).
Three sources:

1. lexicon  curated topics in topics.yml (whole-word, case-insensitive, multi-word synonyms).
2. entity   `change.signals.new_entities` (already "new this year" by construction), normalized
            (casefold, leading "the" and corporate suffixes stripped, whitespace collapsed, ALIASES),
            minus the company's own name and ENTITY_STOPLIST / ENTITY_STOP_PATTERNS. An entity that
            matches a lexicon topic reinforces that topic instead of becoming its own.
3. phrase   spaCy noun chunks of the added/modified sentences, lemmatized, lowercased, 2-4 tokens,
            minus PHRASE_STOPLIST / GENERIC_TOKENS / BANNED_TOKENS and anything a lexicon topic
            already covers. All are stored; the API shows a phrase only when 2+ companies share it.

Every mention keeps the verbatim sentence, its id, and the character spans of the inserted text.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from pipeline.config import NER_MODEL_ID
from pipeline.diff import words
from pipeline.schema import Change, Comparison, Sentence, canonical_json
from pipeline.signals import clean_entity, is_generic_entity
from pipeline.trends.schema import (
    TRENDS_VERSION,
    ChangeActivity,
    PotentialToActual,
    TopicMention,
    TrendFacts,
)

log = logging.getLogger(__name__)

LEXICON_PATH = Path(__file__).with_name("topics.yml")
SOURCE_PRIORITY = {"lexicon": 0, "entity": 1, "phrase": 2}
PHRASE_MIN_TOKENS, PHRASE_MAX_TOKENS = 2, 4

# ---------- lexicon ----------


@dataclass(frozen=True)
class Topic:
    name: str
    synonyms: tuple[str, ...]
    pattern: re.Pattern[str]


def term_regex(term: str) -> str:
    """Whole-word, case-insensitive (flag set by the caller) regex for a term: words joined by any
    whitespace or a hyphen ("data protection laws" also matches "data-protection laws"), straight
    or curly apostrophes, never a match inside a longer word ("tariff" does not match "tariffs")."""
    parts = [re.escape(w).replace("'", "['’]") for w in term.split()]
    return r"(?<!\w)" + r"(?:\s*-\s*|\s+)".join(parts) + r"(?!\w)"


def compile_terms(terms: Iterable[str]) -> re.Pattern[str]:
    ordered = sorted({t.strip() for t in terms if t.strip()}, key=lambda t: (-len(t), t))
    return re.compile("|".join(term_regex(t) for t in ordered), re.IGNORECASE)


@lru_cache(maxsize=4)
def load_lexicon(path: Path = LEXICON_PATH) -> tuple[int, tuple[Topic, ...]]:
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    version = int(doc["TOPICS_VERSION"])
    topics = []
    for entry in doc["topics"]:
        syns = tuple(str(s) for s in entry["synonyms"])
        topics.append(Topic(name=str(entry["topic"]), synonyms=syns, pattern=compile_terms(syns)))
    names = [t.name for t in topics]
    if len(set(names)) != len(names):
        raise ValueError("duplicate topic names in topics.yml")
    return version, tuple(topics)


def derivation_id() -> str:
    version, _ = load_lexicon()
    return f"{TRENDS_VERSION}+topics{version}"


@lru_cache(maxsize=4096)
def _term_pattern(term: str) -> re.Pattern[str]:
    return re.compile(term_regex(term), re.IGNORECASE)


def _inside(a: int, b: int, spans: list[tuple[int, int]]) -> bool:
    return any(x <= a and b <= y for x, y in spans)


def term_inserted(term: str, text: str, spans: list[tuple[int, int]]) -> bool:
    """True when at least one whole-word occurrence of `term` lies wholly inside one span."""
    try:
        rx = _term_pattern(term)
    except re.error:
        return False
    return any(_inside(m.start(), m.end(), spans) for m in rx.finditer(text))


def term_in(term: str, text: str) -> bool:
    """Whole-word, case-insensitive occurrence of `term` anywhere in `text`."""
    if not text:
        return False
    try:
        return _term_pattern(term).search(text) is not None
    except re.error:
        return False


def inserted_terms(topic: Topic, text: str, spans: list[tuple[int, int]]) -> list[str]:
    """Verbatim matches (whitespace collapsed) of a topic's synonyms that lie wholly inside one of
    `spans`, in text order, deduplicated case-insensitively. Each synonym is searched on its own
    (an inserted "tariffs" is found even where a longer synonym also matches across the boundary
    of the insertion); a match inside a longer kept match is dropped."""
    if not spans:
        return []
    hits: list[tuple[int, int, str]] = []
    for syn in topic.synonyms:
        for m in _term_pattern(syn).finditer(text):
            if _inside(m.start(), m.end(), spans):
                hits.append((m.start(), m.end(), m.group(0)))
    hits.sort(key=lambda h: (h[0], -(h[1] - h[0])))
    kept: list[tuple[int, int, str]] = []
    for a, b, t in hits:
        if any(x <= a and b <= y for x, y, _ in kept):
            continue
        kept.append((a, b, t))
    out: list[str] = []
    seen: set[str] = set()
    for _, _, t in kept:
        t = re.sub(r"\s+", " ", t)
        if t.casefold() not in seen:
            seen.add(t.casefold())
            out.append(t)
    return out


def lexicon_topic_for(text: str) -> Topic | None:
    """The first lexicon topic (file order) any of whose synonyms occurs in `text`."""
    _, topics = load_lexicon()
    return next((t for t in topics if t.pattern.search(text)), None)


# ---------- entities ----------

# casefolded alias -> canonical display
ALIASES: dict[str, str] = {
    "u.s.": "United States",
    "u.s": "United States",
    "us": "United States",
    "usa": "United States",
    "u.s.a.": "United States",
    "united states of america": "United States",
    "usg": "U.S. government",
    "u.s. government": "U.S. government",
    "us government": "U.S. government",
    "united states government": "U.S. government",
    "prc": "China",
    "people's republic of china": "China",
    "eu": "European Union",
    "e.u.": "European Union",
    "uk": "United Kingdom",
    "u.k.": "United Kingdom",
}
# Generic entities that appear in every 10-K and say nothing about a trend (casefolded, after
# normalization and aliasing).
ENTITY_STOPLIST: frozenset[str] = frozenset(
    {
        "sec",
        "securities and exchange commission",
        "u.s. securities and exchange commission",
        "company",
        "board",
        "board of directors",
        "gaap",
        "u.s. gaap",
        "fasb",
        "financial accounting standards board",
        "irs",
        "internal revenue service",
        "united states",
        "nasdaq",
        "nasdaq global select market",
        "nyse",
        "new york stock exchange",
        "congress",
        "u.s. congress",
        "exchange act",
        "securities act",
        "form 10-k",
        "annual report on form 10-k",
        "item 1a",
        "risk factors",
    }
)
_MONTHS = "january|february|march|april|may|june|july|august|september|october|november|december"
ENTITY_STOP_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^(?:the )?(?:first|second|third|fourth|q[1-4])(?: fiscal)? quarter\b.*$"),
    re.compile(r"^q[1-4](?: (?:fiscal )?(?:19|20)?\d{2})?$"),
    re.compile(r"^(?:fiscal|calendar)(?: year)?(?: (?:19|20)\d{2})?$"),
    re.compile(r"^fy ?(?:19|20)?\d{2}$"),
    re.compile(r"^(?:19|20)\d{2}$"),
    re.compile(rf"^(?:{_MONTHS})(?: \d{{1,2}})?,?(?: (?:19|20)\d{{2}})?$"),
    re.compile(r"^(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)$"),
    # a government administration named by one name ("Trump Administration", "Biden-Harris
    # Administration") is not a newly named party; agencies ("Federal Aviation Administration") are
    re.compile(r"^(?:the )?[a-z]+(?:-[a-z]+)? administration$"),
)
_CORP_SUFFIX_RE = re.compile(
    r"(?:,?\s+(?:inc|incorporated|corp|corporation|co|company|llc|l\.l\.c|ltd|limited|plc|"
    r"n\.v|s\.a|ag|gmbh|holdings))\.?$",
    re.IGNORECASE,
)
# words of a company name that do not identify it (so "Stifel Financial" excludes "Stifel" but
# not every entity containing "Financial")
GENERIC_NAME_TOKENS = frozenset(
    "inc incorporated corp corporation co company companies llc ltd limited plc holdings holding "
    "group the and of financial technologies technology international global industries "
    "systems services bancorp trust".split()
)


def normalize_entity(value: str) -> tuple[str, str]:
    """(key, display) for an entity: whitespace collapsed, quotes and a leading "the" stripped,
    the alias map ("U.S." -> "United States"), then the pipeline's own NER post-filter
    (`signals.clean_entity`: codes such as "D:4" are dropped) and a trailing corporate suffix
    removed ("Groq, Inc" -> "Groq"). key is the casefolded display ("" = drop)."""
    t = re.sub(r"\s+", " ", value).strip(" ,;:\"'()[]\u201c\u201d\u2018\u2019")
    t = re.sub(r"^the\s+", "", t, flags=re.IGNORECASE).replace("\u2019", "'")
    alias = ALIASES.get(t.casefold()) or ALIASES.get(t.casefold().rstrip("."))
    if alias:
        return alias.casefold(), alias
    t = clean_entity(t) or ""
    prev = None
    while prev != t:
        prev = t
        t = _CORP_SUFFIX_RE.sub("", t).strip(" ,.")
    display = ALIASES.get(t.casefold(), t)
    return display.casefold(), display


def own_name_tokens(name: str, ticker: str) -> tuple[frozenset[str], frozenset[str]]:
    """(identifying tokens, all tokens) of the company name, plus the ticker."""
    toks = [w for w in re.findall(r"[a-z0-9]+", name.casefold())]
    ident = {w for w in toks if w not in GENERIC_NAME_TOKENS and len(w) > 1}
    ident.add(ticker.casefold())
    return frozenset(ident), frozenset(toks) | {ticker.casefold()}


def is_stop_entity(key: str, ident: frozenset[str], all_tokens: frozenset[str]) -> bool:
    if key in ENTITY_STOPLIST or any(p.match(key) for p in ENTITY_STOP_PATTERNS):
        return True
    if is_generic_entity(key):  # the company page's own stoplist (regulators, legislatures, courts)
        return True
    toks = set(re.findall(r"[a-z0-9]+", key))
    if not toks:
        return True
    # the company's own name: any identifying token ("nvidia"), or only words of its name
    return bool(toks & ident) or toks <= (all_tokens | GENERIC_NAME_TOKENS)


# ---------- key phrases ----------

# lemmatized, lowercased phrases that are 10-K boilerplate
PHRASE_STOPLIST: frozenset[str] = frozenset(
    {
        "our business",
        "financial condition",
        "results of operation",
        "result of operation",
        "adverse effect",
        "material adverse effect",
        "adverse impact",
        "material adverse impact",
        "negative impact",
        "significant risk",
        "future result",
        "operating result",
        "financial result",
        "financial performance",
        "stock price",
        "common stock",
        "annual report",
        "risk factor",
        "fiscal year",
        "forward-looking statement",
        "cash flow",
        "business operation",
    }
)
# a phrase made only of these lemmas is generic
GENERIC_TOKENS: frozenset[str] = frozenset(
    "business operation result financial condition adverse material effect impact risk factor "
    "future significant certain other additional new various product service customer company "
    "ability manner way extent time period year number level part term case matter event "
    "change increase decrease reputation cost expense revenue growth following applicable "
    "potential current near multiple numerous particular ongoing desired expected anticipated "
    "necessary adequate limited appropriate legitimate related relevant key broad".split()
)
# phrases containing any of these tokens are dropped (determiners, pronouns, vague quantifiers)
BANNED_TOKENS: frozenset[str] = frozenset(
    "such these those this that other certain various many some any each all our we us it its "
    "they their them he she his her you your which who whose what".split()
)
_LEADING_POS = frozenset({"DET", "PRON", "NUM", "PART", "CCONJ", "ADP", "PUNCT", "SYM"})
_PHRASE_TOKEN_RE = re.compile(r"^[a-z][a-z\-]*[a-z]$|^[a-z]$")

_phrase_nlp = None


def phrase_model_id() -> str:
    import spacy

    return f"{NER_MODEL_ID}+spacy@{spacy.__version__}:noun_chunks"


def get_phrase_nlp():
    """en_core_web_sm with the parser (noun chunks) and lemmatizer; NER is not needed here."""
    global _phrase_nlp
    if _phrase_nlp is None:
        import spacy

        _phrase_nlp = spacy.load("en_core_web_sm", disable=["ner"])
    return _phrase_nlp


def _lemma(tok) -> str:
    """Nouns are lemmatized ("restrictions" -> "restriction"); every other word keeps its
    lowercased surface form (participles such as "binding" or "related" must not become verbs),
    and "data" stays "data" (the model's lemma is "datum")."""
    low = tok.lower_
    if tok.pos_ in ("NOUN", "PROPN") and low != "data":
        return tok.lemma_.lower()
    return low


def phrases_in(doc) -> list[tuple[str, str]]:
    """(lemma phrase, verbatim surface) for each acceptable noun chunk of a parsed sentence."""
    out: list[tuple[str, str]] = []
    for chunk in doc.noun_chunks:
        toks = [t for t in chunk if not (t.is_punct or t.is_space)]
        while toks and (
            toks[0].pos_ in _LEADING_POS
            or toks[0].is_stop
            or (toks[0].pos_ == "ADJ" and toks[0].lower_ in GENERIC_TOKENS)  # "new", "additional"
        ):
            toks.pop(0)
        while toks and toks[-1].pos_ not in ("NOUN", "PROPN"):
            toks.pop()
        if toks and toks[0].i > 0 and doc[toks[0].i - 1].text == "-":
            continue  # the first word lost its hyphenated prefix ("third-party" -> "party")
        if not PHRASE_MIN_TOKENS <= len(toks) <= PHRASE_MAX_TOKENS:
            continue
        lemmas = [_lemma(t) for t in toks]
        if any(not _PHRASE_TOKEN_RE.match(lm) for lm in lemmas):
            continue  # numbers, codes, symbols
        if any(t.pos_ == "PRON" or t.lower_ in BANNED_TOKENS for t in toks):
            continue
        if any(lm in BANNED_TOKENS for lm in lemmas):
            continue
        phrase = " ".join(lemmas)
        if phrase in PHRASE_STOPLIST or all(lm in GENERIC_TOKENS for lm in lemmas):
            continue
        surface = doc.text[toks[0].idx : toks[-1].idx + len(toks[-1].text)]
        out.append((phrase, re.sub(r"\s+", " ", surface)))
    return out


# ---------- spans + counts ----------


def added_spans(s: Sentence) -> list[tuple[int, int]]:
    """Offsets of inserted text inside s.text (whitespace-trimmed, adjacent runs merged)."""
    return _marked_spans(s, "insert", "added")


def removed_spans(s: Sentence) -> list[tuple[int, int]]:
    """Offsets of deleted text inside s.text (the old side's own spans)."""
    return _marked_spans(s, "delete", "removed")


def _marked_spans(s: Sentence, op: str, whole_status: str) -> list[tuple[int, int]]:
    if s.status == whole_status:
        return [(0, len(s.text))]
    spans: list[tuple[int, int]] = []
    pos = 0
    for sp in s.diff_spans or []:
        end = pos + len(sp.text)
        if sp.op == op:
            seg = s.text[pos:end]
            a = pos + (len(seg) - len(seg.lstrip()))
            b = end - (len(seg) - len(seg.rstrip()))
            if b > a:
                if spans and not s.text[spans[-1][1] : a].strip():
                    spans[-1] = (spans[-1][0], b)
                else:
                    spans.append((a, b))
        pos = end
    return spans


def change_activity(c: Change) -> ChangeActivity:
    added = removed = modified = 0
    added_w = removed_w = modified_w = 0
    for s in c.sentences:
        if s.status == "added":
            added += 1
            added_w += len(words(s.text))
        elif s.status == "removed":
            removed += 1
            removed_w += len(words(s.text))
        elif s.status == "modified":
            if s.side == "new":
                modified += 1
                modified_w += sum(
                    len(words(sp.text)) for sp in s.diff_spans or [] if sp.op == "insert"
                )
            else:
                modified_w += sum(
                    len(words(sp.text)) for sp in s.diff_spans or [] if sp.op == "delete"
                )
    return ChangeActivity(
        change_id=c.id,
        short_title=c.short_title,
        categories=list(c.categories),
        change_type=c.change_type,
        score=c.score,
        added_sentences=added,
        removed_sentences=removed,
        modified_sentences=modified,
        added_words=added_w,
        removed_words=removed_w,
        modified_words=modified_w,
    )


# ---------- mentions ----------


class _Mentions:
    """Collects mentions keyed by (change_id, sentence_id, topic); a second source for the same key
    adds its matched terms, and the higher-priority source (lexicon > entity > phrase) is kept."""

    def __init__(self) -> None:
        self.items: dict[tuple[str, str, str], TopicMention] = {}

    def add(self, m: TopicMention) -> None:
        key = (m.change_id, m.sentence_id, m.topic)
        cur = self.items.get(key)
        if cur is None:
            self.items[key] = m
            return
        terms = list(cur.matched_terms)
        for t in m.matched_terms:
            if t.casefold() not in {x.casefold() for x in terms}:
                terms.append(t)
        src = min(cur.source, m.source, key=SOURCE_PRIORITY.__getitem__)
        self.items[key] = cur.model_copy(update={"matched_terms": terms, "source": src})


def _mention(
    ticker: str, c: Change, pos: int, s: Sentence, topic: str, source: str, terms: list[str]
) -> TopicMention:
    return TopicMention(
        ticker=ticker,
        change_id=c.id,
        sentence_id=s.id,
        position=pos,
        topic=topic,
        source=source,  # type: ignore[arg-type]
        matched_terms=terms,
        status=s.status,  # type: ignore[arg-type]
        text=s.text,
        added_spans=added_spans(s),
    )


UNCHANGED = "largely_unchanged"


def last_year_text(c: Change) -> str:
    """Last year's text of a risk factor: `old_text` (heading + body) plus the change's old-side
    sentences, or the old-side sentences alone when `old_text` is absent (it is optional in the
    contract). Empty for a new risk factor."""
    parts = [c.old_text] if c.old_text else []
    parts.extend(s.text for s in c.sentences if s.side == "old")
    return "\n".join(parts)


def topic_mentions(comp: Comparison, nlp=None) -> list[TopicMention]:
    """Newly added language per risk factor (see the module docstring for the three rules)."""
    _, topics = load_lexicon()
    ticker = comp.company.ticker
    ident, all_tokens = own_name_tokens(comp.company.name, ticker)
    out = _Mentions()
    # sentences to parse for phrases, in a fixed order (deterministic batches)
    phrase_jobs: list[tuple[Change, int, Sentence, str, frozenset[str], list]] = []
    for c in comp.changes:
        if c.change_type == UNCHANGED:
            continue  # an essentially unchanged risk factor never contributes a trend
        old = last_year_text(c)
        new_sents = [
            (pos, s, added_spans(s))
            for pos, s in enumerate(c.sentences)
            if s.side == "new" and s.status in ("added", "modified")
        ]
        new_sents = [(pos, s, sp) for pos, s, sp in new_sents if sp]
        if not new_sents:
            continue
        fresh = [t for t in topics if not (old and t.pattern.search(old))]
        # 1. lexicon: a synonym inside the inserted text
        for pos, s, spans in new_sents:
            for t in fresh:
                terms = inserted_terms(t, s.text, spans)
                if terms:
                    out.add(_mention(ticker, c, pos, s, t.name, "lexicon", terms))
        # 2. new named entities: the entity's own words inside the inserted text
        by_id = {s.id: (pos, s, spans) for pos, s, spans in new_sents}
        fresh_names = {t.name for t in fresh}
        entity_keys: set[str] = set()
        for hit in c.signals.new_entities:
            key, display = normalize_entity(hit.value)
            entity_keys.update({key, hit.value.casefold()})
            if not key or is_stop_entity(key, ident, all_tokens):
                continue
            if term_in(hit.value, old):
                continue  # the entity's words were already in last year's text
            lex = lexicon_topic_for(display) or lexicon_topic_for(hit.value)
            if lex is not None:
                if lex.name not in fresh_names:
                    continue  # the topic was already in last year's text
                topic, source = lex.name, "lexicon"
            else:
                if term_in(display, old):
                    continue
                topic, source = display, "entity"
            for sid in hit.new_sentence_ids:
                if sid in by_id:
                    pos, s, spans = by_id[sid]
                    if term_inserted(hit.value, s.text, spans):
                        out.add(_mention(ticker, c, pos, s, topic, source, [hit.value]))
        for pos, s, spans in new_sents:
            phrase_jobs.append((c, pos, s, old, frozenset(entity_keys), spans))
    # 3. key phrases: the noun chunk's words inside the inserted text
    if phrase_jobs:
        nlp = nlp or get_phrase_nlp()
        docs = nlp.pipe([j[2].text for j in phrase_jobs], batch_size=64)
        for (c, pos, s, old, entity_keys, spans), doc in zip(phrase_jobs, docs, strict=True):
            for phrase, surface in phrases_in(doc):
                if not term_inserted(surface, s.text, spans):
                    continue  # (partly) words that were already in the sentence last year
                if lexicon_topic_for(surface) is not None:
                    continue  # a curated topic already covers it
                if set(phrase.split()) & ident:
                    continue  # the company's own name
                if phrase in entity_keys or surface.casefold() in entity_keys:
                    continue  # the same words are already an entity of this risk factor
                if term_in(surface, old) or term_in(phrase, old):
                    continue
                out.add(_mention(ticker, c, pos, s, phrase, "phrase", [surface]))
    order = {c.id: i for i, c in enumerate(comp.changes)}
    return sorted(
        out.items.values(),
        key=lambda m: (order[m.change_id], m.position, SOURCE_PRIORITY[m.source], m.topic),
    )


def aligned_pair(old_s: Sentence | None, new_s: Sentence | None) -> bool:
    """The two sentences are a rewritten pair of the diff: the new one is `modified` and its
    counterpart is the old one."""
    return (
        old_s is not None
        and new_s is not None
        and new_s.side == "new"
        and new_s.status == "modified"
        and new_s.counterpart_id == old_s.id
    )


def potential_to_actual(comp: Comparison) -> list[PotentialToActual]:
    """`potential_became_actual` highlights whose two sentences are an aligned pair of the diff
    (a hedge and an unrelated sentence elsewhere in the risk factor are never shown as one)."""
    idx = comp.sentence_index
    scores = {c.id: c.score for c in comp.changes}
    sentences = {s.id: s for c in comp.changes for s in c.sentences}
    out = []
    for h in comp.highlights:
        if h.kind != "potential_became_actual":
            continue
        if h.old_sentence_id not in idx or h.new_sentence_id not in idx:
            continue
        old_s, new_s = sentences.get(h.old_sentence_id), sentences.get(h.new_sentence_id)
        if not aligned_pair(old_s, new_s):
            continue
        out.append(
            PotentialToActual(
                ticker=comp.company.ticker,
                company_name=comp.company.name,
                change_id=h.change_id,
                short_title=h.short_title,
                old_sentence_id=h.old_sentence_id,
                new_sentence_id=h.new_sentence_id,
                old_text=idx[h.old_sentence_id].text,
                new_text=idx[h.new_sentence_id].text,
                score=scores.get(h.change_id, 0),
                old_spans=removed_spans(old_s),
                new_spans=added_spans(new_s),
            )
        )
    return out


# ---------- entry points ----------


def derive_trend_facts(report: Comparison, nlp=None) -> TrendFacts:
    if report.is_fixture:
        raise ValueError("trend facts are never derived from FIXTURE data")
    return TrendFacts(
        derivation=derivation_id(),
        phrase_model=phrase_model_id(),
        analysis_id=report.analysis_id,
        ticker=report.company.ticker,
        company_name=report.company.name,
        cik=report.company.cik,
        old_fiscal_year=report.old_filing.fiscal_year,
        new_fiscal_year=report.new_filing.fiscal_year,
        old_accession=report.old_filing.accession_number,
        new_accession=report.new_filing.accession_number,
        old_edgar_url=report.old_filing.edgar_url,
        new_edgar_url=report.new_filing.edgar_url,
        total_changes=report.summary.total_changes,
        by_change_type=dict(report.summary.by_change_type),
        category_activity=[change_activity(c) for c in report.changes],
        topic_mentions=topic_mentions(report, nlp),
        potential_to_actual=potential_to_actual(report),
    )


def facts_json(facts: TrendFacts) -> str:
    return canonical_json(facts)


def derived_path(derived_dir: Path, analysis_id: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{64}", analysis_id):
        raise ValueError("not an analysis_id")
    return derived_dir / f"{analysis_id}.trends.json"


def load_facts(derived_dir: Path, analysis_id: str) -> TrendFacts | None:
    """The derived file for an analysis if it exists, validates and is current; else None."""
    path = derived_path(derived_dir, analysis_id)
    try:
        facts = TrendFacts.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if (
        facts.analysis_id != analysis_id
        or facts.derivation != derivation_id()
        or facts.phrase_model != phrase_model_id()
    ):
        return None
    return facts


def write_facts(derived_dir: Path, facts: TrendFacts) -> tuple[Path, bool]:
    """Write atomically; returns (path, changed). An identical file is left untouched."""
    path = derived_path(derived_dir, facts.analysis_id)
    text = facts_json(facts)
    try:
        if path.read_text(encoding="utf-8") == text:
            return path, False
    except OSError:
        pass
    derived_dir.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)
    return path, True


def ensure_facts(report: Comparison, derived_dir: Path, nlp=None) -> TrendFacts:
    """The current derived facts for a report: loaded when the file is current, else derived and
    written (idempotent)."""
    facts = load_facts(derived_dir, report.analysis_id)
    if facts is None:
        facts = derive_trend_facts(report, nlp)
        write_facts(derived_dir, facts)
    return facts


def derived_dir_for(data_dir: Path) -> Path:
    return data_dir / "derived"


def derive_after_publish(published_path: Path, derived_dir: Path) -> dict:
    """The pipeline's post-publish step. Never raises: returns {"status": "ok", "path", "changed"}
    or {"status": "failed", "code"} so a derivation problem never undoes the local publish."""
    from pipeline.publish import load_published

    try:
        report = load_published(Path(published_path))
        facts = derive_trend_facts(report)
        path, changed = write_facts(derived_dir, facts)
        return {"status": "ok", "path": str(path), "changed": changed}
    except Exception as e:  # noqa: BLE001
        log.warning(
            "trend facts not derived for %s: %s", Path(published_path).name, type(e).__name__
        )
        return {"status": "failed", "code": type(e).__name__}
