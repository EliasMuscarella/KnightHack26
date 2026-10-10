# Integrity report

Generated 2026-10-10T22:00:38Z by `scripts/check_integrity.py`. Exit code 1.

## Sources

- local published: 2 files, 2 current (NVDA, SF) in /home/user/KnightHack26/data/published
- API: http://127.0.0.1:8000 (store health {'remote': 'disabled', 'warehouse_state': None})
- /trends: status disabled, source local, 2 companies
- Databricks: not configured (DATABRICKS_HOST / TOKEN / WAREHOUSE_ID unset)
- derived trend facts: 2 of 2 current reports have a current file in /home/user/KnightHack26/data/derived; all re-derived in memory with the current code

## Current code

- pipeline 0.2.0, rubric 1.1.0, code fingerprint `4797c77d2bda`, stage 0 sec_fetch 0.1.1, stage 1 extract 0.2.1, stage 2 segment 0.2.2, stage 3 embed 0.1.0, stage 4 match 0.1.0, stage 5 diff 0.1.3, stage 6 signals 0.2.2
- display rule checked: `window`

## Summary

| Check | Violations | stale data | code | data | accepted |
|-------|-----------:|-----------:|-----:|-----:|---------:|
| SNIP-TOPIC | 0 | 0 | 0 | 0 | 0 |
| SNIP-CHANGE | 0 | 0 | 0 | 0 | 0 |
| TOPIC-NEW | 0 | 0 | 0 | 0 | 0 |
| TOPIC-MEANINGFUL | 0 | 0 | 0 | 0 | 0 |
| PAIR | 0 | 0 | 0 | 0 | 0 |
| CASE | 21 | 21 | 0 | 0 | 0 |
| YEARS | 0 | 0 | 0 | 0 | 0 |
| COUNTS | 0 | 0 | 0 | 0 | 0 |
| TITLES | 0 | 0 | 0 | 0 | 0 |
| PREAMBLE | 1 | 1 | 0 | 0 | 0 |
| ENTITY | 6 | 6 | 0 | 0 | 0 |
| STALE | 2 | 2 | 0 | 0 | 0 |
| HEATMAP | 0 | 0 | 0 | 0 | 0 |
| **Total** | **30** | 30 | 0 | 0 | 0 |

## Reports

| Ticker | analysis_id | pipeline | rubric | current code | earliest stage to re-run |
|--------|-------------|----------|--------|--------------|--------------------------|
| NVDA | `13acfdfe2afd` | 0.1.0 | 1.0.0 | no | 2 (segment) |
| SF | `c07038f75e99` | 0.1.0 | 1.0.0 | no | 5 (diff) |

## Violations

### CASE (21)

- **NVDA** change `a4156a06454f6dfd`, sentences `0001045810-25-000023:19:95`, `0001045810-26-000021:21:91`: highlighted though only case/space/punctuation differ: export
  - *stale*, re-run from stage 5: current diff no longer marks these words
- **NVDA** change `a4156a06454f6dfd`, sentences `0001045810-25-000023:19:96`, `0001045810-26-000021:21:92`: highlighted though only case/space/punctuation differ: export
  - *stale*, re-run from stage 5: current diff no longer marks these words
- **NVDA** change `a4156a06454f6dfd`, sentences `0001045810-25-000023:19:98`, `0001045810-26-000021:21:94`: highlighted though only case/space/punctuation differ: export
  - *stale*, re-run from stage 5: current diff no longer marks these words
- **NVDA** change `a4156a06454f6dfd`, sentences `0001045810-25-000023:19:107`, `0001045810-26-000021:21:106`: highlighted though only case/space/punctuation differ: if
  - *stale*, re-run from stage 5: current diff no longer marks these words
- **NVDA** change `f7a8d95bf7b51298`, sentences `0001045810-25-000023:12:14`, `0001045810-26-000021:13:14`: highlighted though only case/space/punctuation differ: some
  - *stale*, re-run from stage 5: current diff no longer marks these words
- **NVDA** change `dfe9c44ef07b2d30`, sentences `0001045810-25-000023:6:14`, `0001045810-26-000021:7:14`: highlighted though only case/space/punctuation differ: these
  - *stale*, re-run from stage 5: current diff no longer marks these words
- **NVDA** change `dfe9c44ef07b2d30`, sentences `0001045810-25-000023:6:15`, `0001045810-26-000021:7:15`: highlighted though only case/space/punctuation differ: these
  - *stale*, re-run from stage 5: current diff no longer marks these words
- **NVDA** change `dfe9c44ef07b2d30`, sentences `0001045810-25-000023:6:36`, `0001045810-26-000021:7:40`: highlighted though only case/space/punctuation differ: geopolitical
  - *stale*, re-run from stage 5: current diff no longer marks these words
- **NVDA** change `76929d4c94edf687`, sentences `0001045810-25-000023:8:9`, `0001045810-26-000021:9:9`: highlighted though only case/space/punctuation differ: such
  - *stale*, re-run from stage 5: current diff no longer marks these words
- **NVDA** change `b7c169267209801d`, sentences `0001045810-25-000023:15:2`, `0001045810-26-000021:16:2`: highlighted though only case/space/punctuation differ: sales
  - *stale*, re-run from stage 5: current diff no longer marks these words
- **NVDA** change `5f11cecb0925b7ee`, sentences `0001045810-25-000023:3:1`, `0001045810-26-000021:4:1`: highlighted though only case/space/punctuation differ: scrutiny
  - *stale*, re-run from stage 5: current diff no longer marks these words
- **NVDA** change `6827ebf0162cb806`, sentences `0001045810-25-000023:20:0`, `0001045810-26-000021:22:0`: highlighted though only case/space/punctuation differ: scrutiny
  - *stale*, re-run from stage 5: current diff no longer marks these words
- **SF** change `3b93c57e20a358e4`, sentences `0000950170-25-027702:14:24`, `0001193125-26-067130:14:23`: highlighted though only case/space/punctuation differ: maintain
  - *stale*, re-run from stage 5: current diff no longer marks these words
- **SF** change `3b93c57e20a358e4`, sentences `0000950170-25-027702:14:29`, `0001193125-26-067130:14:29`: highlighted though only case/space/punctuation differ: such
  - *stale*, re-run from stage 5: current diff no longer marks these words
- **SF** change `3b93c57e20a358e4`, sentences `0000950170-25-027702:14:30`, `0001193125-26-067130:14:30`: highlighted though only case/space/punctuation differ: substantial, time
  - *stale*, re-run from stage 5: current diff no longer marks these words
- **SF** change `3b93c57e20a358e4`, sentences `0000950170-25-027702:14:37`, `0001193125-26-067130:14:37`: highlighted though only case/space/punctuation differ: unauthorized
  - *stale*, re-run from stage 5: current diff no longer marks these words
- **SF** change `3b93c57e20a358e4`, sentences `0000950170-25-027702:14:40`, `0001193125-26-067130:14:39`: highlighted though only case/space/punctuation differ: lapses
  - *stale*, re-run from stage 5: current diff no longer marks these words
- **SF** change `61ffb76925cf3bc2`, sentences `0000950170-25-027702:20:9`, `0001193125-26-067130:20:4`: highlighted though only case/space/punctuation differ: frameworks
  - *stale*, re-run from stage 5: current diff no longer marks these words
- **SF** change `faa01310d8a450a6`, sentences `0000950170-25-027702:5:7`, `0001193125-26-067130:5:6`: highlighted though only case/space/punctuation differ: changes
  - *stale*, re-run from stage 5: current diff no longer marks these words
- **SF** change `db2dc1bfc373add1`, sentences `0000950170-25-027702:18:4`, `0001193125-26-067130:18:3`: highlighted though only case/space/punctuation differ: own, policies
  - *stale*, re-run from stage 5: current diff no longer marks these words
- **SF** change `db2dc1bfc373add1`, sentences `0000950170-25-027702:18:9`, `0001193125-26-067130:18:5`: highlighted though only case/space/punctuation differ: associate
  - *stale*, re-run from stage 5: current diff no longer marks these words

### PREAMBLE (1)

- **NVDA** change `692187bd48c050c3`, sentences `0001045810-26-000021:0:0`: 'The following risk factors should be considered in addition to the other information in this Annual Report on Form 10-K.': heading is the Item 1A introduction
  - *stale*, re-run from stage 2: segment 0.2.2 skips intro and summary units; confirmed only by a re-run from stage 2

### ENTITY (6)

- **NVDA** change `a4156a06454f6dfd`, sentences `0001045810-26-000021:21:64`: 'AI Diffusion IFR in': post-filter changes it to 'AI Diffusion IFR' (trailing/leading stopword); trailing preposition
  - *stale*, re-run from stage 6: current entity code no longer emits it
- **NVDA** change `a4156a06454f6dfd`, sentences `0001045810-26-000021:21:71`: 'Biden Administration': bare government administration; generic body or regulator (signals stoplist); on the trends entity stoplist
  - *stale*, re-run from stage 6: current entity code no longer emits it
- **NVDA** change `a4156a06454f6dfd`, sentences `0001045810-26-000021:21:47`, `0001045810-26-000021:21:63`: 'D:4': dropped by the entity post-filter (code or too short); short code; on the trends entity stoplist
  - *stale*, re-run from stage 6: current entity code no longer emits it
- **NVDA** change `a4156a06454f6dfd`, sentences `0001045810-26-000021:21:70`: 'Senate': generic body or regulator (signals stoplist); on the trends entity stoplist
  - *stale*, re-run from stage 6: current entity code no longer emits it
- **NVDA** change `a4156a06454f6dfd`, sentences `0001045810-26-000021:21:71`: 'Trump Administration': bare government administration; generic body or regulator (signals stoplist); on the trends entity stoplist
  - *stale*, re-run from stage 6: current entity code no longer emits it
- **SF** change `61ffb76925cf3bc2`, sentences `0001193125-26-067130:20:2`, `0001193125-26-067130:20:11`: 'SEC': generic body or regulator (signals stoplist); on the trends entity stoplist
  - *stale*, re-run from stage 6: current entity code no longer emits it

### STALE (2)

- **NVDA** change —, sentences —: pipeline 0.1.0 != 0.2.0; rubric 1.0.0 != 1.1.0; code fingerprint f7ef0450bbe6 != current 4797c77d2bda
  - *stale*, re-run from stage 2: stage versions are not recorded in this report; the earliest stage is inferred from the other findings
- **SF** change —, sentences —: pipeline 0.1.0 != 0.2.0; rubric 1.0.0 != 1.1.0; code fingerprint f7ef0450bbe6 != current 4797c77d2bda
  - *stale*, re-run from stage 5: stage versions are not recorded in this report; the earliest stage is inferred from the other findings

