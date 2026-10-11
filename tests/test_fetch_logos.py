"""scripts/fetch_logos.py: sanitizer, allowlist, ticker/CIK handling, shapes, manifest rewrite.

No network: HTTP goes through respx mocks and the client sleeps through a no-op.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import httpx
import pytest
import respx

ROOT = Path(__file__).resolve().parents[1]


def _load():
    spec = importlib.util.spec_from_file_location("fetch_logos", ROOT / "scripts" / "fetch_logos.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["fetch_logos"] = mod
    spec.loader.exec_module(mod)
    return mod


fl = _load()

SVG_HEAD = '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="0 0 100 50">'


def _sanitize(body: str) -> str:
    return fl.sanitize_svg(f"{SVG_HEAD}{body}</svg>".encode()).svg


def _assert_clean(svg: str) -> None:
    lowered = svg.lower()
    for bad in ("<script", "javascript:", "foreignobject", "<image", "http://evil", "<!", "<a ", "<a>"):
        assert bad not in lowered, bad
    assert not re.search(r"\son[a-z]+\s*=", lowered)
    assert not re.search(r'href="(?!#)', svg)


# ---------------------------------------------------------------------------------------------
# Sanitizer: malicious inputs
# ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "body",
    [
        '<script>alert(1)</script><path d="M0 0h10v10z"/>',
        '<script xlink:href="http://evil.example/x.js"/><path d="M0 0h10v10z"/>',
        '<path d="M0 0h10v10z" onload="alert(1)" onclick="alert(2)"/>',
        '<image href="http://evil.example/x.png" width="10" height="10"/><path d="M0 0h1z"/>',
        '<image xlink:href="data:image/png;base64,AAAA"/><path d="M0 0h1z"/>',
        '<foreignObject><div xmlns="http://www.w3.org/1999/xhtml">hi</div></foreignObject><path d="M0 0h1z"/>',
        '<a href="javascript:alert(1)"><path d="M0 0h1z"/></a><path d="M0 0h1z"/>',
        '<a xlink:href="http://evil.example"><path d="M0 0h1z"/></a><path d="M0 0h1z"/>',
        '<use xlink:href="http://evil.example/sprite.svg#a"/><path d="M0 0h1z"/>',
        '<use href="javascript:alert(1)"/><path d="M0 0h1z"/>',
        '<path d="M0 0h1z" style="fill:url(http://evil.example/p.svg#g)"/>',
        '<path d="M0 0h1z" style="fill:red;background:url(https://evil.example/t.png)"/>',
        '<path d="M0 0h1z" fill="url(http://evil.example/#g)"/>',
        '<path d="M0 0h1z" style="fill:\\75 rl(http://evil.example)"/>',
        '<animate attributeName="href" to="javascript:alert(1)"/><set attributeName="onload" to="x"/><path d="M0 0h1z"/>',
        '<g onmouseover="alert(1)"><path d="M0 0h1z" fill="javascript:alert(1)"/></g>',
    ],
)
def test_sanitizer_strips_active_and_external_content(body):
    svg = _sanitize(body)
    _assert_clean(svg)
    assert "<path" in svg  # the harmless artwork survives


@pytest.mark.parametrize(
    "raw",
    [
        '<?xml version="1.0"?><!DOCTYPE svg [<!ENTITY x "boom">]><svg xmlns="http://www.w3.org/2000/svg">&x;</svg>',
        '<!doctype svg><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1 1"/>',
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1 1"><!ENTITY a "b"></svg>',
    ],
)
def test_sanitizer_rejects_doctype_and_entities(raw):
    with pytest.raises(fl.SanitizeError, match="DOCTYPE or ENTITY"):
        fl.sanitize_svg(raw.encode())


@pytest.mark.parametrize(
    "body, reason",
    [
        ('<style>@import url(http://evil.example/x.css);</style>', "at-rules"),
        ('<style>g > path{fill:red}</style>', "selector"),
        ('<filter id="f"><feGaussianBlur stdDeviation="2"/></filter>', "unsupported element"),
        ('<pattern id="p"/>', "unsupported element"),
    ],
)
def test_sanitizer_fails_closed(body, reason):
    with pytest.raises(fl.SanitizeError, match=reason):
        fl.sanitize_svg(f"{SVG_HEAD}{body}</svg>".encode())


def test_stylesheet_external_url_is_dropped():
    svg = _sanitize('<style>.a{fill:url(http://evil.example/g);stroke:#000}</style><path class="a" d="M0 0h1z"/>')
    _assert_clean(svg)
    assert "url(" not in svg and 'style="stroke:#000"' in svg


def test_style_element_is_inlined_and_removed():
    svg = _sanitize('<style>.a{fill:#123456}#b{stroke:#000}</style><path class="a" id="b" d="M0 0h1z"/>')
    assert "<style" not in svg and "class=" not in svg
    assert 'style="fill:#123456;stroke:#000"' in svg


def test_unsafe_style_declarations_dropped_but_safe_ones_kept():
    svg = _sanitize('<path d="M0 0h1z" style="fill:red;behavior:url(x.htc);stroke:url(#g)"/>')
    assert 'style="fill:red;stroke:url(#g)"' in svg


def test_editor_namespaces_metadata_and_comments_removed():
    raw = (
        '<?xml version="1.0"?><!-- made in a tool -->'
        '<svg xmlns="http://www.w3.org/2000/svg" xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" '
        'xmlns:sodipodi="http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd" width="20" height="10" '
        'inkscape:version="1.0"><sodipodi:namedview id="nv"/><metadata><x/></metadata><title>t</title>'
        '<path d="M0 0h1z" inkscape:label="layer"/></svg>'
    )
    svg = fl.sanitize_svg(raw.encode()).svg
    assert svg == '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 10"><path d="M0 0h1z"/></svg>\n'


def test_clean_logo_survives_intact():
    raw = (
        '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="0 0 120 40" width="240" height="80">'
        '<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#f00"/>'
        '<stop offset="1" stop-color="#00f"/></linearGradient><clipPath id="c"><rect width="120" height="40"/></clipPath></defs>'
        '<g clip-path="url(#c)" transform="translate(1 2)"><path d="M0 0L10 10Z" fill="url(#g)" fill-rule="evenodd"/>'
        '<circle cx="5" cy="5" r="4" stroke="#000" stroke-width="2" opacity="0.5"/>'
        '<use xlink:href="#c"/><text x="1" y="30" font-family="Arial" font-size="12">Acme <tspan>Co</tspan></text></g></svg>'
    )
    result = fl.sanitize_svg(raw.encode())
    root = ET.fromstring(result.svg)
    tags = [e.tag.split("}")[1] for e in root.iter()]
    assert tags == [
        "svg", "defs", "linearGradient", "stop", "stop", "clipPath", "rect", "g", "path", "circle", "use", "text", "tspan",
    ]
    assert root.get("viewBox") == "0 0 120 40" and root.get("width") is None and root.get("height") is None
    path = root.find(".//{http://www.w3.org/2000/svg}path")
    assert path.attrib == {"d": "M0 0L10 10Z", "fill": "url(#g)", "fill-rule": "evenodd"}
    assert root.find(".//{http://www.w3.org/2000/svg}use").get("href") == "#c"
    assert "Acme <tspan>Co</tspan></text>" in result.svg
    assert result.notes == []
    # Sanitizing the sanitized output is a fixed point.
    assert fl.sanitize_svg(result.svg.encode()).svg == result.svg


def test_viewbox_derived_from_width_and_height():
    result = fl.sanitize_svg(b'<svg xmlns="http://www.w3.org/2000/svg" width="300px" height="100"><path d="M0 0h1z"/></svg>')
    assert 'viewBox="0 0 300 100"' in result.svg and "width=" not in result.svg
    assert (result.width, result.height) == (300.0, 100.0)
    with pytest.raises(fl.SanitizeError, match="viewBox"):
        fl.sanitize_svg(b'<svg xmlns="http://www.w3.org/2000/svg" width="100%"><path d="M0 0h1z"/></svg>')


def test_rejects_non_svg_root_and_oversize():
    with pytest.raises(fl.SanitizeError, match="root"):
        fl.sanitize_svg(b'<html xmlns="http://www.w3.org/1999/xhtml"/>')
    with pytest.raises(fl.SanitizeError, match="larger"):
        fl.sanitize_svg(SVG_HEAD.encode() + b" " * (400 * 1024) + b"</svg>")


# ---------------------------------------------------------------------------------------------
# Shape, ticker, CIK
# ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "w, h, shape",
    [(100, 100, "mark"), (160, 100, "mark"), (161, 100, "wordmark"), (1000, 618, "wordmark"), (50, 100, "mark")],
)
def test_classify_shape(w, h, shape):
    assert fl.classify_shape(w, h) == shape


def test_classify_shape_rejects_empty_box():
    with pytest.raises(ValueError):
        fl.classify_shape(0, 10)


@pytest.mark.parametrize("raw, expected", [("nvda", "NVDA"), (" brk.b ", "BRK.B"), ("BF-B", "BF-B"), ("V", "V")])
def test_ticker_validation_accepts(raw, expected):
    assert fl.normalize_ticker(raw) == expected


@pytest.mark.parametrize("raw", ["", "TOOLONG", "NV DA", "../x", "A1", "NVDA;rm", "é", "<b>"])
def test_ticker_validation_rejects(raw):
    with pytest.raises(ValueError):
        fl.normalize_ticker(raw)


def test_tickers_argument():
    assert fl.parse_tickers_arg("msft, nvda,MSFT") == ["MSFT", "NVDA"]
    assert fl.parse_tickers_arg(None) is None
    with pytest.raises(ValueError):
        fl.parse_tickers_arg("NVDA,http://x")
    assert fl.main(["--tickers", "../../etc"]) == 1


@pytest.mark.parametrize(
    "cik, forms",
    [
        ("0000789019", ["0000789019", "789019"]),
        ("789019", ["0000789019", "789019"]),
        ("2488", ["0000002488", "2488"]),
        ("1234567890", ["1234567890"]),
    ],
)
def test_cik_forms(cik, forms):
    assert fl.cik_forms(cik) == forms


@pytest.mark.parametrize("cik", ["", "0", "12345678901", "12a4", "-5"])
def test_cik_forms_rejects(cik):
    with pytest.raises(ValueError):
        fl.cik_forms(cik)


# ---------------------------------------------------------------------------------------------
# Network allowlist
# ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "https://www.wikidata.org/w/api.php",
        "https://commons.wikimedia.org/w/api.php",
        "https://upload.wikimedia.org/wikipedia/commons/2/25/Microsoft_icon.svg",
        "http://localhost:8000/companies",
    ],
)
def test_allowlist_accepts(url):
    assert fl.check_url(url) == url


@pytest.mark.parametrize(
    "url",
    [
        "https://evil.example/x.svg",
        "http://www.wikidata.org/w/api.php",  # Wikimedia only over https
        "https://upload.wikimedia.org.evil.example/x.svg",
        "https://user@www.wikidata.org/w/api.php",
        "http://localhost:9000/companies",
        "https://localhost:8000/companies",
        "file:///etc/passwd",
        "http://169.254.169.254/latest/meta-data",
    ],
)
def test_allowlist_refuses(url):
    with pytest.raises(fl.DisallowedURLError):
        fl.check_url(url)


def _client(**kw):
    return fl.PoliteClient(cache_dir=None, min_interval=0, sleep=lambda _s: None, **kw)


@respx.mock
def test_client_refuses_other_hosts_without_a_request():
    client = _client()
    with pytest.raises(fl.DisallowedURLError):
        client.get_bytes("https://evil.example/logo.svg", kind="files")
    assert client.network_calls == 0


@respx.mock
def test_client_refuses_redirect_off_the_allowlist():
    route = respx.get("https://upload.wikimedia.org/a.svg").mock(
        return_value=httpx.Response(302, headers={"location": "https://evil.example/b.svg"})
    )
    client = _client()
    with pytest.raises(fl.DisallowedURLError):
        client.get_bytes("https://upload.wikimedia.org/a.svg", kind="files")
    assert route.call_count == 1


@respx.mock
def test_client_follows_redirect_within_the_allowlist_and_sends_generic_ua():
    respx.get("https://upload.wikimedia.org/a.svg").mock(
        return_value=httpx.Response(301, headers={"location": "/b.svg"})
    )
    target = respx.get("https://upload.wikimedia.org/b.svg").mock(return_value=httpx.Response(200, content=b"<svg/>"))
    assert _client().get_bytes("https://upload.wikimedia.org/a.svg", kind="files") == b"<svg/>"
    ua = target.calls.last.request.headers["user-agent"]
    assert ua == fl.USER_AGENT and "@" not in ua


@respx.mock
def test_client_backs_off_on_maxlag_and_429():
    url_re = re.compile(r"https://www\.wikidata\.org/w/api\.php.*")
    respx.get(url__regex=url_re.pattern).mock(
        side_effect=[
            httpx.Response(200, json={"error": {"code": "maxlag"}}, headers={"retry-after": "5"}),
            httpx.Response(429),
            httpx.Response(200, json={"query": {"search": [{"title": "Q2283"}]}}),
        ]
    )
    sleeps: list[float] = []
    client = fl.PoliteClient(cache_dir=None, min_interval=0, sleep=sleeps.append)
    payload = client.get_api(fl.WIKIDATA_API, {"action": "query"})
    assert payload["query"]["search"][0]["title"] == "Q2283"
    assert sleeps == [5.0, 5.0 * 2]
    request = respx.calls.last.request
    assert "maxlag=5" in str(request.url)


@respx.mock
def test_cache_means_no_second_request(tmp_path):
    route = respx.get("https://upload.wikimedia.org/a.svg").mock(return_value=httpx.Response(200, content=b"x"))
    first = fl.PoliteClient(cache_dir=tmp_path, min_interval=0, sleep=lambda _s: None)
    first.get_bytes("https://upload.wikimedia.org/a.svg", kind="files")
    second = fl.PoliteClient(cache_dir=tmp_path, min_interval=0, sleep=lambda _s: None)
    assert second.get_bytes("https://upload.wikimedia.org/a.svg", kind="files") == b"x"
    assert route.call_count == 1 and second.network_calls == 0


@respx.mock
def test_company_list_falls_back_to_published(tmp_path):
    respx.get(fl.COMPANIES_URL).mock(side_effect=httpx.ConnectError("down"))
    (tmp_path / "MSFT_2025_2026.json").write_text(
        json.dumps({"company": {"ticker": "MSFT", "name": "MICROSOFT CORP", "cik": "0000789019"}})
    )
    (tmp_path / "BAD.json").write_text(json.dumps({"company": {"ticker": "../x", "name": "x", "cik": "1"}}))
    companies, source = fl.load_companies(_client(), published_dir=tmp_path)
    assert source == "published"
    assert [c.ticker for c in companies] == ["MSFT"]


# ---------------------------------------------------------------------------------------------
# Wikidata claim selection
# ---------------------------------------------------------------------------------------------


def _claim(value, rank="normal", end=None, start=None):
    quals = {}
    if end:
        quals["P582"] = [{"snaktype": "value", "datavalue": {"value": {"time": end}}}]
    if start:
        quals["P580"] = [{"snaktype": "value", "datavalue": {"value": {"time": start}}}]
    return {"rank": rank, "mainsnak": {"snaktype": "value", "datavalue": {"value": value}}, "qualifiers": quals}


def test_logo_candidates_prefer_icon_current_and_preferred():
    entity = {
        "claims": {
            "P154": [
                _claim("Old.svg", end="+2012-00-00T00:00:00Z"),
                _claim("Current.svg", rank="preferred", start="+2012-08-24T00:00:00Z"),
                _claim("Other.svg"),
                _claim("Bad.svg", rank="deprecated"),
            ],
            "P8972": [_claim("Icon.svg")],
        }
    }
    names = [(c.prop, c.file_name) for c in fl.logo_candidates(entity)]
    assert names == [("P8972", "Icon.svg"), ("P154", "Current.svg"), ("P154", "Other.svg")]


def test_entity_cik_confirmation():
    entity = {"claims": {"P5531": [_claim("0000789019")]}}
    assert fl.entity_has_cik(entity, "789019")
    assert not fl.entity_has_cik(entity, "789018")


# ---------------------------------------------------------------------------------------------
# Manifest and SOURCES.md rewrites
# ---------------------------------------------------------------------------------------------

MANIFEST = """const LOGO_MANIFEST = {
  // BEGIN GENERATED by scripts/fetch_logos.py
  NVDA: "wordmark",
  AAPL: "mark",
  // END GENERATED
} as const satisfies Record<string, LogoShape>;
"""


def test_manifest_rewrite_sorted_and_idempotent():
    once = fl.rewrite_manifest(MANIFEST, {"MSFT": "mark", "BRK.B": "wordmark", "NVDA": "mark"})
    assert once == (
        "const LOGO_MANIFEST = {\n"
        "  // BEGIN GENERATED by scripts/fetch_logos.py\n"
        '  AAPL: "mark",\n'
        '  "BRK.B": "wordmark",\n'
        '  MSFT: "mark",\n'
        '  NVDA: "mark",\n'
        "  // END GENERATED\n"
        "} as const satisfies Record<string, LogoShape>;\n"
    )
    assert fl.rewrite_manifest(once, {"MSFT": "mark"}) == once
    assert fl.read_manifest(once) == {"AAPL": "mark", "BRK.B": "wordmark", "MSFT": "mark", "NVDA": "mark"}


def test_manifest_rewrite_rejects_bad_input():
    with pytest.raises(ValueError):
        fl.rewrite_manifest(MANIFEST, {"../X": "mark"})
    with pytest.raises(ValueError):
        fl.rewrite_manifest(MANIFEST, {"MSFT": "banner"})
    with pytest.raises(fl.ScriptError):
        fl.rewrite_manifest("const X = {};", {"MSFT": "mark"})


def test_real_manifest_block_parses():
    text = (ROOT / "web" / "src" / "lib" / "logos.ts").read_text(encoding="utf-8")
    entries = fl.read_manifest(text)
    assert list(entries) == sorted(entries)
    assert fl.rewrite_manifest(text, {}) == text


def test_sources_rewrite_sorted_and_idempotent():
    text = f"# Logos\n\n{fl.SOURCES_BEGIN}\n{fl.SOURCES_HEADER}\n| SF | Stifel | none | x | PD | manual |\n{fl.SOURCES_END}\ntail\n"
    row = fl.SourceRow("MSFT", "Microsoft", "Q2283", "Microsoft icon.svg", "https://commons.wikimedia.org/wiki/File:Microsoft_icon.svg", "Public domain | x", "P8972")
    once = fl.rewrite_sources(text, {"MSFT": row})
    assert fl.rewrite_sources(once, {"MSFT": row}) == once
    lines = once.splitlines()
    assert lines[3].startswith("| Ticker |") and lines[4].startswith("|---")
    assert lines[5].startswith("| MSFT |") and lines[6].startswith("| SF |")
    assert sum(line.startswith("|---") for line in lines) == 1
    assert "Public domain / x" in once and once.endswith("tail\n")


@respx.mock
def test_file_info_leaves_out_wiki_markup_in_attribution():
    """Commons metadata is user-edited: template markup in Artist/Credit is never published."""
    respx.get(url__regex=r"https://commons\.wikimedia\.org/w/api\.php.*").mock(
        return_value=httpx.Response(
            200,
            json={
                "query": {
                    "pages": [
                        {
                            "imageinfo": [
                                {
                                    "url": "https://upload.wikimedia.org/x/Logo.svg",
                                    "mime": "image/svg+xml",
                                    "size": 1000,
                                    "extmetadata": {
                                        "LicenseShortName": {"value": "Public domain"},
                                        "Artist": {"value": "{{Vandal text}}"},
                                        "Credit": {"value": "company.example"},
                                    },
                                }
                            ]
                        }
                    ]
                }
            },
        )
    )
    client = fl.PoliteClient(cache_dir=None, min_interval=0, sleep=lambda _s: None)
    info = fl.get_file_info(client, "Logo.svg")
    assert info.license == "Public domain (Credit: company.example)"
    assert "{{" not in info.license
