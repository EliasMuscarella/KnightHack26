"""Stage 5: sentence-level diff inside each matched block pair, and change_type rules.

Sentence alignment: order-preserving dynamic programming (weighted longest common subsequence)
over a similarity matrix sim(a, b) = 0.5 * word-level SequenceMatcher ratio + 0.5 * embedding
cosine. Pairs below `sentence_match_threshold` cannot align. Aligned pairs whose normalized text
is identical are `unchanged`; otherwise `modified`, with word-level spans from difflib
(deterministic, autojunk disabled). Unaligned old sentences are `removed`, new ones `added`.

Word spans (`word_spans`): only word tokens are aligned, compared by a normalized key
(`token_key`: casefold, curly quotes/dashes folded to ASCII), so "Export" vs "export", a line
break vs a space, or an added comma is never a change; the original text is always emitted.
Content words anchor the alignment (`_word_opcodes`: the anchored alignment is used when it marks
fewer content words than the plain one). Whitespace right after a changed word joins the change;
other whitespace/punctuation at a change border stays equal; changed spans with no alphanumeric
character fold into `equal` (`_fold_ws`). Each side's spans still concatenate to its exact text.

`classify_change_type` is the ONLY place change types are decided; its rules are in its docstring.
"""

from __future__ import annotations

import difflib
import logging
import re
from dataclasses import dataclass

import numpy as np

from pipeline.schema import DiffSpan, DiffStats, Sentence
from pipeline.types import RiskBlock

log = logging.getLogger(__name__)

STAGE_VERSION = "0.1.3"

TOKEN_RE = re.compile(r"\s+|\w+(?:[’'\-]\w+)*|[^\w\s]")
_NORM_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class DiffParams:
    sentence_match_threshold: float = 0.45
    sentence_unchanged_threshold: float = (
        1.0  # unchanged == exact after whitespace/quote normalization
    )
    expanded_ratio: float = 0.15
    reworded_similarity: float = 0.80
    minor_ratio: float = 0.05
    reworded_total_ratio: float = 0.30
    both_sides_ratio: float = 0.25

    def to_dict(self) -> dict:
        return dict(self.__dict__)


DEFAULT_DIFF_PARAMS = DiffParams()
# TF-IDF cosine lives on a lower scale than dense cosine, so rule 8's similarity floor differs.
DIFF_PARAMS_BY_BACKEND = {
    "sentence-transformers": DEFAULT_DIFF_PARAMS,
    "lexical-fallback": DiffParams(reworded_similarity=0.45),
}


def diff_params_for(backend: str) -> DiffParams:
    return DIFF_PARAMS_BY_BACKEND.get(backend, DEFAULT_DIFF_PARAMS)


def normalize_sentence(s: str) -> str:
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    s = s.replace("–", "-").replace("—", "-")
    return _NORM_RE.sub(" ", s).strip().lower()


def words(s: str) -> list[str]:
    return [t for t in TOKEN_RE.findall(s) if t.strip() and (t[0].isalnum())]


def lexical_ratio(a: str, b: str) -> float:
    wa, wb = [w.lower() for w in words(a)], [w.lower() for w in words(b)]
    if not wa and not wb:
        return 1.0
    return difflib.SequenceMatcher(a=wa, b=wb, autojunk=False).ratio()


_JUNK_WORDS = frozenset("and or the a an of to in on for with by as at".split())


def _is_junk_token(t: str) -> bool:
    """Whitespace, punctuation and function words never anchor an alignment."""
    return not t.strip() or not t[0].isalnum() or t.lower() in _JUNK_WORDS


_KEY_TRANS = str.maketrans(
    {"\u2019": "'", "\u2018": "'", "\u201c": '"', "\u201d": '"', "\u2013": "-", "\u2014": "-"}
)


def token_key(t: str) -> str:
    """Comparison key of one token: case, curly quotes/dashes and the kind of whitespace are
    not changes."""
    if not t.strip():
        return " "
    return t.translate(_KEY_TRANS).casefold()


def _is_word(t: str) -> bool:
    return bool(t.strip()) and t[0].isalnum()


def _changed_marks(ops: list[tuple], ka: list[str], kb: list[str]) -> tuple[int, int]:
    """(content words marked, all words marked) by a list of word-level opcodes."""
    content = total = 0
    for tag, i1, i2, j1, j2 in ops:
        if tag == "equal":
            continue
        for w in ka[i1:i2] + kb[j1:j2]:
            total += 1
            content += w not in _JUNK_WORDS
    return content, total


def _word_opcodes(ka: list[str], kb: list[str]) -> list[tuple]:
    """Word-level opcodes over normalized word keys (whitespace and punctuation excluded).

    Two deterministic alignments are computed: a plain one (difflib, autojunk off) and one where
    content words anchor the alignment (function words in _JUNK_WORDS are difflib "junk": they
    still match next to anchors but never anchor). The alignment that marks fewer content words
    wins, then the one marking fewer words overall; a tie keeps the plain alignment. So
    "Westland and Eastland." vs "Westland, Eastland, and Ruritania." keeps "Eastland" equal
    (marking "and" twice instead of "Eastland" twice), while two equivalent alignments never
    move a mark from a word the plain diff leaves alone."""
    plain = difflib.SequenceMatcher(a=ka, b=kb, autojunk=False).get_opcodes()
    anchored = difflib.SequenceMatcher(
        isjunk=_is_junk_token, a=ka, b=kb, autojunk=False
    ).get_opcodes()
    if _changed_marks(anchored, ka, kb) < _changed_marks(plain, ka, kb):
        return anchored
    return plain


def _side_spans(tokens: list[str], word_op: list[str]) -> list[DiffSpan]:
    """Spans of one side from the per-word ops (`word_op[k]` = op of the k-th word token).

    A gap of non-word tokens (whitespace, punctuation) between two words of the same op takes
    that op. A whitespace-only gap right after a changed run joins it (so "Excessive or
    shifting " is deleted with its trailing space); any other gap at the border of a changed run
    stays equal (punctuation alone is never a change). Text is emitted verbatim."""
    word_pos = [i for i, t in enumerate(tokens) if _is_word(t)]
    ops = ["equal"] * len(tokens)
    for k, i in enumerate(word_pos):
        ops[i] = word_op[k]
    bounds = [-1] + word_pos + [len(tokens)]
    for g in range(len(bounds) - 1):
        lo, hi = bounds[g] + 1, bounds[g + 1]
        if lo >= hi:
            continue
        left = ops[bounds[g]] if bounds[g] >= 0 else None
        right = ops[bounds[g + 1]] if bounds[g + 1] < len(tokens) else None
        gap = "".join(tokens[lo:hi])
        if left is not None and left == right:
            op = left
        elif not gap.strip() and left not in (None, "equal"):
            op = left
        else:
            op = "equal"
        for i in range(lo, hi):
            ops[i] = op
    spans: list[DiffSpan] = []
    for t, op in zip(tokens, ops, strict=True):
        if spans and spans[-1].op == op:
            spans[-1] = DiffSpan(op=op, text=spans[-1].text + t)
        else:
            spans.append(DiffSpan(op=op, text=t))
    return spans


def word_spans(old: str, new: str) -> tuple[list[DiffSpan], list[DiffSpan]]:
    """Word-level diff. Old side gets equal/delete spans, new side equal/insert spans; each
    side's spans concatenate back to its exact text.

    Only word tokens are aligned, by their normalized key (`token_key`), so case, curly quotes,
    whitespace and punctuation never count as a change; see _word_opcodes for the alignment and
    _side_spans for how whitespace/punctuation between words is attributed."""
    a, b = TOKEN_RE.findall(old), TOKEN_RE.findall(new)
    assert "".join(a) == old and "".join(b) == new
    ka = [token_key(t) for t in a if _is_word(t)]
    kb = [token_key(t) for t in b if _is_word(t)]
    a_op = ["equal"] * len(ka)
    b_op = ["equal"] * len(kb)
    for tag, i1, i2, j1, j2 in _word_opcodes(ka, kb):
        if tag in ("delete", "replace"):
            a_op[i1:i2] = ["delete"] * (i2 - i1)
        if tag in ("insert", "replace"):
            b_op[j1:j2] = ["insert"] * (j2 - j1)
    # whitespace- or punctuation-only changed spans are noise: fold them into neighbors as equal
    old_spans = _fold_ws(_side_spans(a, a_op))
    new_spans = _fold_ws(_side_spans(b, b_op))
    return old_spans, new_spans


def _has_alnum(text: str) -> bool:
    return any(c.isalnum() for c in text)


def _fold_ws(spans: list[DiffSpan]) -> list[DiffSpan]:
    """Fold changed spans that carry no alphanumeric character (whitespace or punctuation only)
    into `equal`, merging adjacent spans of the same op."""
    out: list[DiffSpan] = []
    for sp in spans:
        op = "equal" if (sp.op != "equal" and not _has_alnum(sp.text)) else sp.op
        if out and out[-1].op == op:
            out[-1] = DiffSpan(op=op, text=out[-1].text + sp.text)
        else:
            out.append(DiffSpan(op=op, text=sp.text))
    return out


def align_sentences(sim: np.ndarray, threshold: float) -> list[tuple[int, int]]:
    """Monotonic alignment maximizing total similarity of aligned pairs (weighted LCS)."""
    n, m = sim.shape
    score = np.zeros((n + 1, m + 1))
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            best = max(score[i - 1, j], score[i, j - 1])
            s = sim[i - 1, j - 1]
            if s >= threshold:
                best = max(best, score[i - 1, j - 1] + s)
            score[i, j] = best
    pairs: list[tuple[int, int]] = []
    i, j = n, m
    while i > 0 and j > 0:
        s = sim[i - 1, j - 1]
        if s >= threshold and abs(score[i, j] - (score[i - 1, j - 1] + s)) < 1e-12:
            pairs.append((i - 1, j - 1))
            i, j = i - 1, j - 1
        elif score[i - 1, j] >= score[i, j - 1]:
            i -= 1
        else:
            j -= 1
    return pairs[::-1]


def sentence_similarity(
    old: RiskBlock, new: RiskBlock, old_vecs: np.ndarray | None, new_vecs: np.ndarray | None
) -> np.ndarray:
    n, m = len(old.sentences), len(new.sentences)
    sim = np.zeros((n, m))
    emb = None
    if old_vecs is not None and new_vecs is not None and len(old_vecs) == n and len(new_vecs) == m:
        emb = np.clip(np.asarray(old_vecs) @ np.asarray(new_vecs).T, 0.0, 1.0)
    for i, a in enumerate(old.sentences):
        for j, b in enumerate(new.sentences):
            if normalize_sentence(a.text) == normalize_sentence(b.text):
                sim[i, j] = 1.0
                continue
            lex = lexical_ratio(a.text, b.text)
            sim[i, j] = 0.5 * lex + 0.5 * float(emb[i, j]) if emb is not None else lex
    return sim


@dataclass
class PairDiff:
    sentences: list[Sentence]
    stats: DiffStats
    change_type: str


def _wc(s: str) -> int:
    return len(words(s))


def diff_pair(
    old: RiskBlock | None,
    new: RiskBlock | None,
    *,
    similarity: float | None,
    old_vecs: np.ndarray | None = None,
    new_vecs: np.ndarray | None = None,
    params: DiffParams = DEFAULT_DIFF_PARAMS,
) -> PairDiff:
    sentences: list[Sentence] = []
    added = removed = modified = unchanged = 0
    added_wc = removed_wc = 0
    pair_index = 0

    if old is None or new is None:
        side = "new" if old is None else "old"
        blk = new if old is None else old
        status = "added" if old is None else "removed"
        for s in blk.sentences:
            sentences.append(
                Sentence(id=s.id, side=side, status=status, text=s.text, pair_index=pair_index)
            )
            pair_index += 1
        if old is None:
            added, added_wc = len(blk.sentences), sum(_wc(s.text) for s in blk.sentences)
        else:
            removed, removed_wc = len(blk.sentences), sum(_wc(s.text) for s in blk.sentences)
    else:
        sim = sentence_similarity(old, new, old_vecs, new_vecs)
        aligned = align_sentences(sim, params.sentence_match_threshold)
        ai = {i: j for i, j in aligned}
        aj = {j: i for i, j in aligned}
        i = j = 0
        n, m = len(old.sentences), len(new.sentences)
        while i < n or j < m:
            if i < n and i not in ai:
                s = old.sentences[i]
                sentences.append(
                    Sentence(
                        id=s.id, side="old", status="removed", text=s.text, pair_index=pair_index
                    )
                )
                removed += 1
                removed_wc += _wc(s.text)
                pair_index += 1
                i += 1
                continue
            if j < m and j not in aj:
                s = new.sentences[j]
                sentences.append(
                    Sentence(
                        id=s.id, side="new", status="added", text=s.text, pair_index=pair_index
                    )
                )
                added += 1
                added_wc += _wc(s.text)
                pair_index += 1
                j += 1
                continue
            # both aligned: they must be aligned to each other (monotonic alignment)
            a, b = old.sentences[i], new.sentences[j]
            assert ai[i] == j, (i, j, ai)
            score = round(float(sim[i, j]), 4)
            if normalize_sentence(a.text) == normalize_sentence(b.text):
                sentences.append(
                    Sentence(
                        id=a.id,
                        side="old",
                        status="unchanged",
                        text=a.text,
                        pair_index=pair_index,
                        counterpart_id=b.id,
                        alignment_similarity=score,
                    )
                )
                sentences.append(
                    Sentence(
                        id=b.id,
                        side="new",
                        status="unchanged",
                        text=b.text,
                        pair_index=pair_index,
                        counterpart_id=a.id,
                        alignment_similarity=score,
                    )
                )
                unchanged += 1
            else:
                os_, ns_ = word_spans(a.text, b.text)
                sentences.append(
                    Sentence(
                        id=a.id,
                        side="old",
                        status="modified",
                        text=a.text,
                        pair_index=pair_index,
                        counterpart_id=b.id,
                        alignment_similarity=score,
                        diff_spans=os_,
                    )
                )
                sentences.append(
                    Sentence(
                        id=b.id,
                        side="new",
                        status="modified",
                        text=b.text,
                        pair_index=pair_index,
                        counterpart_id=a.id,
                        alignment_similarity=score,
                        diff_spans=ns_,
                    )
                )
                modified += 1
                removed_wc += sum(_wc(sp.text) for sp in os_ if sp.op == "delete")
                added_wc += sum(_wc(sp.text) for sp in ns_ if sp.op == "insert")
            pair_index += 1
            i += 1
            j += 1

    stats = DiffStats(
        old_sentence_count=len(old.sentences) if old else 0,
        new_sentence_count=len(new.sentences) if new else 0,
        added=added,
        removed=removed,
        modified=modified,
        unchanged=unchanged,
        old_word_count=_wc(old.full_text) if old else 0,
        new_word_count=_wc(new.full_text) if new else 0,
        added_word_count=added_wc,
        removed_word_count=removed_wc,
    )
    return PairDiff(
        sentences=sentences,
        stats=stats,
        change_type=classify_change_type(stats, similarity, params),
    )


def classify_change_type(
    stats: DiffStats, similarity: float | None, params: DiffParams = DEFAULT_DIFF_PARAMS
) -> str:
    """Deterministic change_type rules (the only place these are decided).

    Let added = added_word_count / new_word_count and removed = removed_word_count / old_word_count
    (words in added/removed sentences plus inserted/deleted spans of modified sentences).

    1. No old block                                      -> "new"
    2. No new block                                      -> "removed"
    3. added < minor_ratio and removed < minor_ratio     -> "largely_unchanged"   (minor_ratio = 0.05)
    4. added >= both_sides_ratio and removed >= both_sides_ratio
       (substantial change in both directions, 0.25)    -> "materially_reworded"
    5. added - removed >= 0.10 and added >= expanded_ratio (0.15)    -> "expanded"
    6. removed - added >= 0.10 and removed >= expanded_ratio (0.15)  -> "reduced"
    7. added + removed >= reworded_total_ratio (0.30)    -> "materially_reworded"
    8. similarity known and similarity < reworded_similarity (0.80)
       and added + removed >= expanded_ratio             -> "materially_reworded"
    9. otherwise (small edits)                           -> "largely_unchanged"
    """

    if stats.old_word_count == 0 and stats.new_word_count > 0:
        return "new"
    if stats.new_word_count == 0 and stats.old_word_count > 0:
        return "removed"
    added = stats.added_word_count / max(1, stats.new_word_count)
    removed = stats.removed_word_count / max(1, stats.old_word_count)
    total = added + removed
    net = added - removed
    if added < params.minor_ratio and removed < params.minor_ratio:
        return "largely_unchanged"
    if added >= params.both_sides_ratio and removed >= params.both_sides_ratio:
        return "materially_reworded"
    if net >= 0.10 and added >= params.expanded_ratio:
        return "expanded"
    if -net >= 0.10 and removed >= params.expanded_ratio:
        return "reduced"
    if total >= params.reworded_total_ratio:
        return "materially_reworded"
    if (
        similarity is not None
        and similarity < params.reworded_similarity
        and total >= params.expanded_ratio
    ):
        return "materially_reworded"
    return "largely_unchanged"
