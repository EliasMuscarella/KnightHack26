# Prompt for the golden-set labeler (fresh subagent; must NOT read pipeline/match.py or embed.py)

You are labeling how risk factors correspond between a company's two consecutive 10-K filings.
You receive, for each company, a list of OLD blocks and NEW blocks (id, section group, heading, and
the first ~300 characters of the body). For each company, produce correspondences:

- `{"old_block_id": X, "new_block_id": Y}` when X and Y are the same risk factor (even if reworded,
  moved, merged with another, or substantially expanded);
- `{"old_block_id": X, "new_block_id": null}` when the old risk has no counterpart (removed);
- `{"old_block_id": null, "new_block_id": Y}` when the new risk has no counterpart (new).

Label 40–60 correspondences in total across the companies, including at least 5 removed and
5 new. Prefer the hard cases (reworded headings, split/merged risks). Do not guess: skip pairs you
are unsure about. Output `eval/golden_pairs.json` exactly in the format documented at the top of
`eval/eval.py`, with `"labeled_by": "AI subagent — needs human spot check"`.
