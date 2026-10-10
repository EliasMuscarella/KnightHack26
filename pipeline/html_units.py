"""Linearize filing HTML into ordered "units" (paragraph-like leaf blocks).

A unit keeps: normalized text, emphasis runs (bold/italic/underline/heading), the source tag,
whether it sits in a table cell, and a serialized HTML snippet. Later stages work on units,
which sidesteps the many ways filers nest <div>/<span>/<font> and inline XBRL tags.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from lxml import etree
from lxml import html as lxml_html

BLOCK_TAGS = frozenset(
    {
        "p",
        "div",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "li",
        "td",
        "th",
        "blockquote",
        "pre",
        "center",
        "section",
        "article",
        "body",
        "dd",
        "dt",
        "caption",
        "tr",
        "table",
        "ul",
        "ol",
        "address",
        "fieldset",
        "form",
        "header",
        "footer",
        "main",
        "nav",
    }
)
SKIP_TAGS = frozenset({"script", "style", "head", "title", "meta", "link", "noscript"})
EMPH_TAGS = frozenset({"b", "strong", "i", "em", "u", "h1", "h2", "h3", "h4", "h5", "h6"})
_STYLE_BOLD = re.compile(r"font-weight\s*:\s*(bold|bolder|[6-9]00)", re.I)
_STYLE_ITALIC = re.compile(r"font-style\s*:\s*italic", re.I)
_STYLE_UNDERLINE = re.compile(r"text-decoration[^;]*underline", re.I)
_STYLE_HIDDEN = re.compile(r"display\s*:\s*none", re.I)
_WS = re.compile(r"[\s  -​ 　﻿]+")


def normalize_ws(s: str) -> str:
    return _WS.sub(" ", s).strip()


@dataclass
class Run:
    text: str
    emph: bool


@dataclass
class Unit:
    text: str
    runs: list[Run]
    tag: str
    in_table: bool
    html: str = ""
    emph_ratio: float = 0.0
    index: int = 0

    @property
    def word_count(self) -> int:
        return len(self.text.split())

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "runs": [[r.text, r.emph] for r in self.runs],
            "tag": self.tag,
            "in_table": self.in_table,
            "emph_ratio": round(self.emph_ratio, 4),
            "html": self.html,
        }

    @staticmethod
    def from_dict(d: dict, index: int = 0) -> Unit:
        return Unit(
            text=d["text"],
            runs=[Run(t, bool(e)) for t, e in d["runs"]],
            tag=d["tag"],
            in_table=bool(d["in_table"]),
            html=d.get("html", ""),
            emph_ratio=float(d.get("emph_ratio", 0.0)),
            index=index,
        )


def _tag(el) -> str:
    t = el.tag
    if not isinstance(t, str):
        return ""
    if "}" in t:
        t = t.split("}", 1)[1]
    return t.lower()


def _is_hidden(el) -> bool:
    style = el.get("style") or ""
    return bool(_STYLE_HIDDEN.search(style))


def _is_emph(el) -> bool:
    t = _tag(el)
    if t in EMPH_TAGS:
        return True
    style = el.get("style") or ""
    return bool(
        _STYLE_BOLD.search(style) or _STYLE_ITALIC.search(style) or _STYLE_UNDERLINE.search(style)
    )


@dataclass
class _Collector:
    chars: list[str] = field(default_factory=list)
    flags: list[bool] = field(default_factory=list)

    def add(self, text: str, emph: bool) -> None:
        if not text:
            return
        self.chars.extend(text)
        self.flags.extend([emph] * len(text))

    def finish(self) -> tuple[str, list[Run], float]:
        out_chars: list[str] = []
        out_flags: list[bool] = []
        pending_ws = False
        ws_flag = False
        for ch, fl in zip(self.chars, self.flags, strict=True):
            if _WS.match(ch):
                if out_chars and not pending_ws:
                    pending_ws, ws_flag = True, fl
                continue
            if pending_ws:
                out_chars.append(" ")
                out_flags.append(ws_flag)
                pending_ws = False
            out_chars.append(ch)
            out_flags.append(fl)
        text = "".join(out_chars)
        runs: list[Run] = []
        for ch, fl in zip(out_chars, out_flags, strict=True):
            if runs and runs[-1].emph == fl:
                runs[-1].text += ch
            else:
                runs.append(Run(ch, fl))
        # whitespace-only runs inherit the neighbor's flag to avoid spurious splits
        merged: list[Run] = []
        for r in runs:
            if merged and (
                r.text.strip() == "" or merged[-1].text.strip() == "" and len(merged) == 1
            ):
                if r.text.strip() == "":
                    merged[-1].text += r.text
                    continue
                if merged[-1].text.strip() == "":
                    r.text = merged[-1].text + r.text
                    merged[-1] = r
                    continue
            if merged and merged[-1].emph == r.emph:
                merged[-1].text += r.text
            else:
                merged.append(r)
        non_ws = [f for c, f in zip(out_chars, out_flags, strict=True) if c != " "]
        ratio = (sum(non_ws) / len(non_ws)) if non_ws else 0.0
        return text, merged, ratio


def _collect_inline(el, emph: bool, col: _Collector) -> None:
    """Collect text of an element subtree treating everything as inline."""
    t = _tag(el)
    if t in SKIP_TAGS or _is_hidden(el) or not isinstance(el.tag, str):
        return
    e = emph or _is_emph(el)
    if t == "br":
        col.add(" ", e)
    col.add(el.text or "", e)
    for child in el:
        if not isinstance(child.tag, str):
            # comments / processing instructions: still honor the tail text
            col.add(child.tail or "", e)
            continue
        _collect_inline(child, e, col)
        if _tag(child) in BLOCK_TAGS:
            col.add(" ", e)
        col.add(child.tail or "", e)


def linearize(doc_html: str | bytes) -> list[Unit]:
    """Parse HTML and return leaf-block units in document order."""
    if isinstance(doc_html, str):
        doc_html = doc_html.encode("utf-8", errors="replace")
    parser = lxml_html.HTMLParser(encoding="utf-8", remove_comments=True, huge_tree=True)
    root = lxml_html.document_fromstring(doc_html, parser=parser)

    # has_block[el] = element has a descendant block element with text (so el is not a leaf block)
    has_block: dict = {}
    for el in reversed(list(root.iter())):
        if not isinstance(el.tag, str):
            continue
        flag = False
        for child in el:
            if not isinstance(child.tag, str):
                continue
            ct = _tag(child)
            if has_block.get(child):
                flag = True
                break
            if ct in BLOCK_TAGS and normalize_ws(child.text_content()):
                flag = True
                break
        has_block[el] = flag

    units: list[Unit] = []

    def emit(col: _Collector, tag: str, in_table: bool, el=None) -> None:
        text, runs, ratio = col.finish()
        if not text:
            return
        snippet = ""
        if el is not None:
            try:
                snippet = etree.tostring(el, encoding="unicode", method="html", with_tail=False)
            except Exception:
                snippet = ""
            if len(snippet) > 20000:
                snippet = ""
        units.append(
            Unit(text=text, runs=runs, tag=tag, in_table=in_table, html=snippet, emph_ratio=ratio)
        )

    def walk(el, emph: bool, in_table: bool) -> None:
        if not isinstance(el.tag, str):
            return
        t = _tag(el)
        if t in SKIP_TAGS or _is_hidden(el):
            return
        e = emph or _is_emph(el)
        it = in_table or t in ("td", "th")
        if not has_block.get(el):
            if t in BLOCK_TAGS:
                col = _Collector()
                _collect_inline(el, e, col)
                emit(col, t, it, el)
                return
            # inline element with no block descendants but reached at block level: treat as a block
            col = _Collector()
            _collect_inline(el, e, col)
            emit(col, t, it, el)
            return
        # element containing block descendants: direct text becomes its own unit, recurse into children
        col = _Collector()
        col.add(el.text or "", e)
        for child in el:
            if not isinstance(child.tag, str):
                col.add(child.tail or "", e)
                continue
            ct = _tag(child)
            if ct in SKIP_TAGS or _is_hidden(child):
                continue
            if ct in BLOCK_TAGS or has_block.get(child):
                emit(col, t, it)
                col = _Collector()
                walk(child, e, it)
            else:
                _collect_inline(child, e, col)
            col.add(child.tail or "", e)
        emit(col, t, it)

    body = root.find("body")
    walk(body if body is not None else root, False, False)
    for i, u in enumerate(units):
        u.index = i
    return units
