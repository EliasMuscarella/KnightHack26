"""Print block ids + headings for two filings so a labeler can write eval/golden_pairs.json.

uv run python -m eval.golden_tool NVDA > /tmp/nvda_blocks.txt
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.run import run_pipeline  # noqa: E402


def main() -> int:
    ticker = sys.argv[1]
    ctx = run_pipeline(ticker, until_stage=2)
    fetch = ctx.outputs["fetch"]
    segs = ctx.outputs["segments"]
    print(
        f"# {ticker}: old={fetch.old.accession_number} (FY{fetch.old.fiscal_year}) new={fetch.new.accession_number} (FY{fetch.new.fiscal_year})"
    )
    for side in ("old", "new"):
        print(f"\n## {side.upper()} blocks")
        for b in segs[side].blocks:
            print(f"{b.id}\t[{b.section_group or '-'}]\t{b.heading[:140]}")
            print(f"\t{b.body[:300].replace(chr(10), ' ')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
