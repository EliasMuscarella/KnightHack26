"""Regenerate the JSON Schema and TypeScript types from pipeline/schema.py.

Usage: uv run python scripts/regen_contract.py [--check]
--check exits non-zero if the committed files are out of date (CI-style guard).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.schema import (  # noqa: E402
    CATEGORIES,
    CHANGE_TYPES,
    SCHEMA_VERSION,
    CompanyCard,
    Comparison,
    StageEvent,
)

SCHEMA_PATH = ROOT / "contract" / "comparison.schema.json"
TS_PATH = ROOT / "web" / "src" / "types" / "comparison.ts"


NAMED_ENUMS = {
    "Category": CATEGORIES,
    "ChangeType": CHANGE_TYPES,
    "SentenceStatus": ("added", "removed", "modified", "unchanged"),
    "FilingSide": ("old", "new"),
    "DiffOp": ("equal", "insert", "delete"),
    "InterpretationStatus": ("ok", "unavailable", "skipped", "empty"),
    "EmbeddingBackend": ("sentence-transformers", "lexical-fallback"),
    "StageStatus": ("started", "done", "cached", "error"),
}


def hoist_enums(node, defs: dict):
    """Replace inline string enums that match a known named enum with a $ref so that
    json2ts emits one named TypeScript union per enum instead of repeating it."""
    if isinstance(node, dict):
        if node.get("type") == "string" and isinstance(node.get("enum"), list):
            for name, values in NAMED_ENUMS.items():
                if tuple(node["enum"]) == tuple(values):
                    defs.setdefault(name, {"title": name, "type": "string", "enum": list(values)})
                    keep = {k: v for k, v in node.items() if k in ("description", "default")}
                    node.clear()
                    node.update({"$ref": f"#/$defs/{name}", **keep})
                    return
        for v in list(node.values()):
            hoist_enums(v, defs)
    elif isinstance(node, list):
        for v in node:
            hoist_enums(v, defs)


def strip_array_bounds(node, in_properties: bool = False):
    """TS-only: json2ts turns minItems/maxItems into tuple unions, which are unreadable,
    and turns every per-field `title` into a one-line alias (`export type Rank = number`)."""
    if isinstance(node, dict):
        if node.get("type") == "array":
            node.pop("minItems", None)
            node.pop("maxItems", None)
        if in_properties:
            node.pop("title", None)
        for k, v in node.items():
            if k == "properties" and isinstance(v, dict):
                for prop in v.values():
                    strip_array_bounds(prop, in_properties=True)
            else:
                strip_array_bounds(v, in_properties=False)
    elif isinstance(node, list):
        for v in node:
            strip_array_bounds(v)


def build_schema() -> dict:
    schema = Comparison.model_json_schema()
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"https://riskdiff.local/contract/comparison.schema.json#v{SCHEMA_VERSION}"
    schema["title"] = "Comparison"
    # Side payloads used by the API, exposed under $defs so one TS file covers them.
    for extra in (StageEvent, CompanyCard):
        sub = extra.model_json_schema()
        defs = sub.pop("$defs", {})
        schema.setdefault("$defs", {}).update(defs)
        schema["$defs"][extra.__name__] = sub
    defs = schema.setdefault("$defs", {})
    hoist_enums(schema, defs)
    return schema


def main() -> int:
    check = "--check" in sys.argv
    schema = build_schema()
    text = json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if check:
        if not SCHEMA_PATH.exists() or SCHEMA_PATH.read_text() != text:
            print(f"OUT OF DATE: {SCHEMA_PATH}")
            return 1
    else:
        SCHEMA_PATH.parent.mkdir(parents=True, exist_ok=True)
        SCHEMA_PATH.write_text(text)
        print(f"wrote {SCHEMA_PATH.relative_to(ROOT)}")

    web = ROOT / "web"
    if not (web / "node_modules" / ".bin" / "json2ts").exists():
        print("json2ts not installed: run `npm install` in web/ first", file=sys.stderr)
        return 2
    before = TS_PATH.read_text() if TS_PATH.exists() else None
    TS_PATH.parent.mkdir(parents=True, exist_ok=True)
    ts_schema = json.loads(text)
    strip_array_bounds(ts_schema)
    tmp = ROOT / "contract" / ".comparison.ts-input.schema.json"
    tmp.write_text(json.dumps(ts_schema, indent=2, sort_keys=True, ensure_ascii=False))
    try:
        subprocess.run(["npm", "run", "--silent", "gen:types"], cwd=web, check=True)
    finally:
        tmp.unlink(missing_ok=True)
    after = TS_PATH.read_text()
    if check and before != after:
        if before is not None:
            TS_PATH.write_text(before)
        print(f"OUT OF DATE: {TS_PATH}")
        return 1
    print(f"wrote {TS_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
