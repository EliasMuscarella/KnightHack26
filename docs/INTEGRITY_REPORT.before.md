# Integrity report

Generated 2026-10-10T21:11:29Z by `scripts/check_integrity.py`. Exit code 1.

## Sources

- local published: 2 files, 2 current (NVDA, SF) in /home/user/KnightHack26/data/published
- API: http://127.0.0.1:8001 (store health {'remote': 'disabled', 'warehouse_state': None})
- /trends: status disabled, source local, 2 companies
- Databricks: not configured (DATABRICKS_HOST / TOKEN / WAREHOUSE_ID unset)
- derived trend facts: 2 of 2 current reports have a current file in /home/user/KnightHack26/data/derived; all re-derived in memory with the current code

## Current code

- pipeline 0.1.0, rubric 1.1.0, code fingerprint `e94330fbe528`, stage 0 sec_fetch 0.1.0, stage 1 extract 0.2.1, stage 2 segment 0.2.1, stage 3 embed 0.1.0, stage 4 match 0.1.0, stage 5 diff 0.1.2, stage 6 signals 0.2.1
- display rule checked: `legacy`

## Summary

| Check | Violations | stale data | code | data | accepted |
|-------|-----------:|-----------:|-----:|-----:|---------:|
| SNIP-TOPIC | 1 | 0 | 1 | 0 | 0 |
| SNIP-CHANGE | 0 | 0 | 0 | 0 | 0 |
| TOPIC-NEW | 20 | 0 | 20 | 0 | 0 |
| TOPIC-MEANINGFUL | 25 | 0 | 25 | 0 | 0 |
| PAIR | 0 | 0 | 0 | 0 | 0 |
| CASE | 31 | 1 | 30 | 0 | 0 |
| YEARS | 0 | 0 | 0 | 0 | 0 |
| COUNTS | 0 | 0 | 0 | 0 | 0 |
| TITLES | 50 | 0 | 50 | 0 | 0 |
| PREAMBLE | 1 | 1 | 0 | 0 | 0 |
| ENTITY | 5 | 2 | 3 | 0 | 0 |
| STALE | 2 | 2 | 0 | 0 | 0 |
| HEATMAP | 0 | 0 | 0 | 0 | 0 |
| **Total** | **135** | 6 | 129 | 0 | 0 |

## Reports

| Ticker | analysis_id | pipeline | rubric | current code | earliest stage to re-run |
|--------|-------------|----------|--------|--------------|--------------------------|
| NVDA | `13acfdfe2afd` | 0.1.0 | 1.0.0 | no | 2 (segment) |
| SF | `c07038f75e99` | 0.1.0 | 1.0.0 | no | 5 (diff) |

## Violations

### SNIP-TOPIC (1)

- **SF** change `3b93c57e20a358e4`, sentences `0001193125-26-067130:14:34`: topic 'Gramm-Leach-Bliley Act': displayed 'In providing services to clients, we collect, use, store, and transmit sensitive client and associa…' lacks ['Gramm-Leach-Bliley Act']
  - *code*: display rule: legacy

### TOPIC-NEW (20)

- **NVDA** change `a4156a06454f6dfd`, sentences `0001045810-26-000021:21:7`: 'csp market' via 'CSP market' (phrase): term is outside the inserted spans (it was already in the sentence last year). 'For example, the French Competition Authority collected information from us regarding our business and competition in the graphics card and…'
  - *code*: derived with the current code
- **NVDA** change `a4156a06454f6dfd`, sentences `0001045810-26-000021:21:33`: 'non data center product' via 'non-data center products' (phrase): term is outside the inserted spans (it was already in the sentence last year). 'Export controls have and could in the future disrupt our supply chain and distribution channels, negatively impacting our ability to serve…'
  - *code*: derived with the current code
- **NVDA** change `a4156a06454f6dfd`, sentences `0001045810-26-000021:21:42`: 'networking business' via 'networking business' (phrase): term is outside the inserted spans (it was already in the sentence last year). 'If regulators conclude that we have failed to fulfill the terms of our Mellanox acquisition or we have violated any applicable law in China…'
  - *code*: derived with the current code
- **NVDA** change `a4156a06454f6dfd`, sentences `0001045810-26-000021:21:100`: 'connected vehicle restriction' via 'Connected Vehicle” restrictions' (phrase): term is outside the inserted spans (it was already in the sentence last year). 'For example, the USG adopted “Connected Vehicle” restrictions on the import and sale of certain automotive products in the United States, w…'
  - *code*: derived with the current code
- **NVDA** change `6ef9abded50fdc62`, sentences `0001045810-26-000021:18:1`: 'exceptional talent' via 'exceptional talent' (phrase): term is outside the inserted spans (it was already in the sentence last year). 'To remain competitive and successfully execute our business strategy, we must attract, retain, and motivate our executives and key employee…'
  - *code*: derived with the current code
- **NVDA** change `8789091d41a73853`, sentences `0001045810-26-000021:26:7`: 'fddei deduction' via 'FDDEI deduction' (phrase): term is outside the inserted spans (it was already in the sentence last year). 'If U.S. tax rates increase or the FDDEI deduction is reduced, our provision for income taxes, results of operations, net income, and cash f…'
  - *code*: derived with the current code
- **NVDA** change `8910beb6333642bd`, sentences `0001045810-26-000021:3:2`: 'data protection incident' via 'data protection incidents' (phrase): term is outside the inserted spans (it was already in the sentence last year). 'Product, system security and data protection incidents or breaches, as well as cyber-attacks could disrupt our operations and adversely aff…'
  - *code*: derived with the current code
- **NVDA** change `ad4f3805e248f79e`, sentences `0001045810-26-000021:14:8`: 'sustainability related law' via 'sustainability-related laws' (phrase): term is outside the inserted spans (it was already in the sentence last year). 'Our business and those of our suppliers and customers is subject to sustainability-related laws, regulations and lawsuits.'
  - *code*: derived with the current code
- **SF** change `3b93c57e20a358e4`, sentences `0001193125-26-067130:14:21`: 'supply chain attack' via 'supply-chain attacks' (phrase): term is outside the inserted spans (it was already in the sentence last year). 'Despite our implementation of protective measures and our efforts to modify them as circumstances warrant, our computer systems, software,…'
  - *code*: derived with the current code
- **SF** change `3b93c57e20a358e4`, sentences `0001193125-26-067130:14:22`: 'cybersecurity insurance' via 'cybersecurity insurance' (phrase): term is outside the inserted spans (it was already in the sentence last year). 'In addition, although we maintain cybersecurity insurance as one component of our broader risk-mitigation strategy, coverage is subject to…'
  - *code*: derived with the current code
- **SF** change `3b93c57e20a358e4`, sentences `0001193125-26-067130:14:22`: 'policy term' via 'policy terms' (phrase): term is outside the inserted spans (it was already in the sentence last year). 'In addition, although we maintain cybersecurity insurance as one component of our broader risk-mitigation strategy, coverage is subject to…'
  - *code*: derived with the current code
- **SF** change `3b93c57e20a358e4`, sentences `0001193125-26-067130:14:28`: 'high transaction volume' via 'high transaction volumes' (phrase): term is outside the inserted spans (it was already in the sentence last year). 'Given our high transaction volumes, remote-work environment, and the large number of clients, partners, and counterparties we serve, a cybe…'
  - *code*: derived with the current code
- **SF** change `3b93c57e20a358e4`, sentences `0001193125-26-067130:14:30`: 'complete and reliable information' via 'complete and reliable information' (phrase): term is outside the inserted spans (it was already in the sentence last year). 'Investigations can require substantial time and resources, and there may be significant delays before we obtain complete and reliable infor…'
  - *code*: derived with the current code
- **SF** change `3b93c57e20a358e4`, sentences `0001193125-26-067130:14:31`: 'malicious action' via 'malicious actions' (phrase): term is outside the inserted spans (it was already in the sentence last year). 'During an extended investigation, we may not know the full extent of the harm or the optimal remediation path, and certain errors or malici…'
  - *code*: derived with the current code
- **SF** change `3b93c57e20a358e4`, sentences `0001193125-26-067130:14:36`: 'criminal penalty' via 'criminal penalties' (phrase): term is outside the inserted spans (it was already in the sentence last year). 'If any person, including an associate or a third-party service provider, negligently disregards or intentionally breaches our controls or o…'
  - *code*: derived with the current code
- **SF** change `61ffb76925cf3bc2`, sentences `0001193125-26-067130:20:1`: 'foreign regulatory authority' via 'foreign regulatory authorities' (phrase): term is outside the inserted spans (it was already in the sentence last year). 'We have multiple stakeholders, including our shareholders, clients, associates, federal, state, and foreign regulatory authorities, and the…'
  - *code*: derived with the current code
- **SF** change `faa01310d8a450a6`, sentences `0001193125-26-067130:5:5`: 'governmental policy change' via 'governmental policy changes' (phrase): term is outside the inserted spans (it was already in the sentence last year). 'In addition, our results of operations may be impacted by governmental policy changes and/or regulatory reform in multiple areas, including…'
  - *code*: derived with the current code
- **SF** change `db2dc1bfc373add1`, sentences `0001193125-26-067130:18:2`: 'non public confidential information' via 'non-public, confidential information' (phrase): term is outside the inserted spans (it was already in the sentence last year). 'For example, our investment banking business often requires that we appropriately manage the use of our institutional clients’ non-public,…'
  - *code*: derived with the current code
- **SF** change `db2dc1bfc373add1`, sentences `0001193125-26-067130:18:3`: 'client confidential information' via 'clients’ confidential information' (phrase): term is outside the inserted spans (it was already in the sentence last year). 'Similarly, many of our associates interact routinely with clients and counterparties and are expected to comply with our policies and proce…'
  - *code*: derived with the current code
- **SF** change `db2dc1bfc373add1`, sentences `0001193125-26-067130:18:4`: 'regulatory action' via 'regulatory action' (phrase): term is outside the inserted spans (it was already in the sentence last year). 'If confidential information, for example, is improperly used or disclosed by any associate, we could be subject to regulatory action and su…'
  - *code*: derived with the current code

### TOPIC-MEANINGFUL (25)

- **NVDA** change `b7c169267209801d`, sentences `0001045810-26-000021:16:2`: 'direct customer' counted on an essentially unchanged risk factor: 'For fiscal year 2026, sales to one direct customer represented 22% of total revenue and sales to another direct custome…'
  - *code*: derived with the current code
- **NVDA** change `472606c9d458f2e9`, sentences `0001045810-26-000021:15:15`: 'OpenAI' counted on an essentially unchanged risk factor: 'We are finalizing an investment and partnership agreement with OpenAI.'
  - *code*: derived with the current code
- **NVDA** change `472606c9d458f2e9`, sentences `0001045810-26-000021:15:15`: 'investment and partnership agreement' counted on an essentially unchanged risk factor: 'We are finalizing an investment and partnership agreement with OpenAI.'
  - *code*: derived with the current code
- **NVDA** change `472606c9d458f2e9`, sentences `0001045810-26-000021:15:16`: 'investment and partnership agreement' counted on an essentially unchanged risk factor: 'There is no assurance that we will enter into an investment and partnership agreement with OpenAI or that a transaction…'
  - *code*: derived with the current code
- **NVDA** change `3efe394c13cfbc9c`, sentences `0001045810-26-000021:27:1`: 'intellectual property' counted on an essentially unchanged risk factor: 'We currently and will likely continue to face legal, administrative and regulatory proceedings, claims, demands and/or…'
  - *code*: derived with the current code
- **NVDA** change `514830a330b756d7`, sentences `0001045810-26-000021:10:11`: 'cash management purpose' counted on an essentially unchanged risk factor: 'Additionally, we maintain a portfolio of liquid investments for cash management purposes, including various holdings, t…'
  - *code*: derived with the current code
- **NVDA** change `514830a330b756d7`, sentences `0001045810-26-000021:10:11`: 'liquid investment' counted on an essentially unchanged risk factor: 'Additionally, we maintain a portfolio of liquid investments for cash management purposes, including various holdings, t…'
  - *code*: derived with the current code
- **NVDA** change `6ef9abded50fdc62`, sentences `0001045810-26-000021:18:1`: 'exceptional talent' counted on an essentially unchanged risk factor: 'To remain competitive and successfully execute our business strategy, we must attract, retain, and motivate our executi…'
  - *code*: derived with the current code
- **NVDA** change `8789091d41a73853`, sentences `0001045810-26-000021:26:7`: 'fddei deduction' counted on an essentially unchanged risk factor: 'If U.S. tax rates increase or the FDDEI deduction is reduced, our provision for income taxes, results of operations, ne…'
  - *code*: derived with the current code
- **NVDA** change `8789091d41a73853`, sentences `0001045810-26-000021:26:9`: 'coordination mechanism' counted on an essentially unchanged risk factor: 'A number of countries in which we conduct business have enacted, or are in the process of enacting, elements of the Pil…'
  - *code*: derived with the current code
- **NVDA** change `8789091d41a73853`, sentences `0001045810-26-000021:26:9`: 'safe harbor' counted on an essentially unchanged risk factor: 'A number of countries in which we conduct business have enacted, or are in the process of enacting, elements of the Pil…'
  - *code*: derived with the current code
- **NVDA** change `8910beb6333642bd`, sentences `0001045810-26-000021:3:2`: 'data protection incident' counted on an essentially unchanged risk factor: 'Product, system security and data protection incidents or breaches, as well as cyber-attacks could disrupt our operatio…'
  - *code*: derived with the current code
- **NVDA** change `8910beb6333642bd`, sentences `0001045810-26-000021:3:7`: 'Counterparty and credit risk' counted on an essentially unchanged risk factor: 'Commercial arrangements expose us to counterparty risks, which may negatively impact our business, financial condition,…'
  - *code*: derived with the current code
- **NVDA** change `8910beb6333642bd`, sentences `0001045810-26-000021:3:7`: 'commercial arrangement' counted on an essentially unchanged risk factor: 'Commercial arrangements expose us to counterparty risks, which may negatively impact our business, financial condition,…'
  - *code*: derived with the current code
- **NVDA** change `ad4f3805e248f79e`, sentences `0001045810-26-000021:14:8`: 'sustainability related law' counted on an essentially unchanged risk factor: 'Our business and those of our suppliers and customers is subject to sustainability-related laws, regulations and lawsui…'
  - *code*: derived with the current code
- **SF** change `cdde20b394f48139`, sentences `0001193125-26-067130:21:3`: 'DOL' counted on an essentially unchanged risk factor: 'The financial services industry has experienced an extended period of significant change in laws and regulations, as we…'
  - *code*: derived with the current code
- **SF** change `cdde20b394f48139`, sentences `0001193125-26-067130:21:18`: 'banking regulator' counted on an essentially unchanged risk factor: 'In particular, the banking regulators have broad enforcement power over bank holding companies and banks, including wit…'
  - *code*: derived with the current code
- **SF** change `cdde20b394f48139`, sentences `0001193125-26-067130:21:18`: 'enforcement power' counted on an essentially unchanged risk factor: 'In particular, the banking regulators have broad enforcement power over bank holding companies and banks, including wit…'
  - *code*: derived with the current code
- **SF** change `cdde20b394f48139`, sentences `0001193125-26-067130:21:18`: 'unsafe or unsound practice' counted on an essentially unchanged risk factor: 'In particular, the banking regulators have broad enforcement power over bank holding companies and banks, including wit…'
  - *code*: derived with the current code
- **SF** change `004fde9f3c9e2280`, sentences `0001193125-26-067130:22:6`: 'firm policy' counted on an essentially unchanged risk factor: 'Unauthorized or illegal acts or noncompliance with firm policies by our associates could also result in substantial lia…'
  - *code*: derived with the current code
- **SF** change `004fde9f3c9e2280`, sentences `0001193125-26-067130:22:6`: 'substantial liability' counted on an essentially unchanged risk factor: 'Unauthorized or illegal acts or noncompliance with firm policies by our associates could also result in substantial lia…'
  - *code*: derived with the current code
- **SF** change `004fde9f3c9e2280`, sentences `0001193125-26-067130:22:6`: 'unauthorized or illegal act' counted on an essentially unchanged risk factor: 'Unauthorized or illegal acts or noncompliance with firm policies by our associates could also result in substantial lia…'
  - *code*: derived with the current code
- **SF** change `1860d97fe1f9183e`, sentences `0001193125-26-067130:13:1`: 'technology solution' counted on an essentially unchanged risk factor: 'Our businesses rely extensively on data processing and communications systems, including both third-party and internall…'
  - *code*: derived with the current code
- **SF** change `fa831ff1fb46062f`, sentences `0001193125-26-067130:1:13`: 'fund banking client' counted on an essentially unchanged risk factor: 'During 2025, we have seen an increase in deposits from our commercial, venture banking, and fund banking clients.'
  - *code*: derived with the current code
- **SF** change `fa831ff1fb46062f`, sentences `0001193125-26-067130:1:13`: 'venture banking' counted on an essentially unchanged risk factor: 'During 2025, we have seen an increase in deposits from our commercial, venture banking, and fund banking clients.'
  - *code*: derived with the current code

### CASE (31)

- **NVDA** change `a4156a06454f6dfd`, sentences `0001045810-25-000023:19:55`, `0001045810-26-000021:21:65`: highlighted though only case/space/punctuation differ: the
  - *code*: current diff reproduces it
- **NVDA** change `a4156a06454f6dfd`, sentences `0001045810-25-000023:19:95`, `0001045810-26-000021:21:91`: highlighted though only case/space/punctuation differ: export
  - *code*: current diff reproduces it
- **NVDA** change `a4156a06454f6dfd`, sentences `0001045810-25-000023:19:96`, `0001045810-26-000021:21:92`: highlighted though only case/space/punctuation differ: export
  - *code*: current diff reproduces it
- **NVDA** change `a4156a06454f6dfd`, sentences `0001045810-25-000023:19:98`, `0001045810-26-000021:21:94`: highlighted though only case/space/punctuation differ: export
  - *code*: current diff reproduces it
- **NVDA** change `a4156a06454f6dfd`, sentences `0001045810-25-000023:19:104`, `0001045810-26-000021:21:104`: highlighted though only case/space/punctuation differ: to
  - *code*: current diff reproduces it
- **NVDA** change `a4156a06454f6dfd`, sentences `0001045810-25-000023:19:107`, `0001045810-26-000021:21:106`: highlighted though only case/space/punctuation differ: if
  - *code*: current diff reproduces it
- **NVDA** change `f7a8d95bf7b51298`, sentences `0001045810-25-000023:12:14`, `0001045810-26-000021:13:14`: highlighted though only case/space/punctuation differ: some
  - *code*: current diff reproduces it
- **NVDA** change `dfe9c44ef07b2d30`, sentences `0001045810-25-000023:6:14`, `0001045810-26-000021:7:14`: highlighted though only case/space/punctuation differ: these
  - *code*: current diff reproduces it
- **NVDA** change `dfe9c44ef07b2d30`, sentences `0001045810-25-000023:6:15`, `0001045810-26-000021:7:15`: highlighted though only case/space/punctuation differ: these
  - *code*: current diff reproduces it
- **NVDA** change `dfe9c44ef07b2d30`, sentences `0001045810-25-000023:6:36`, `0001045810-26-000021:7:40`: highlighted though only case/space/punctuation differ: geopolitical
  - *code*: current diff reproduces it
- **NVDA** change `dfe9c44ef07b2d30`, sentences `0001045810-25-000023:6:38`, `0001045810-26-000021:7:44`: highlighted though only case/space/punctuation differ: we
  - *code*: current diff reproduces it
- **NVDA** change `76929d4c94edf687`, sentences `0001045810-25-000023:8:9`, `0001045810-26-000021:9:9`: highlighted though only case/space/punctuation differ: such
  - *code*: current diff reproduces it
- **NVDA** change `b7c169267209801d`, sentences `0001045810-25-000023:15:2`, `0001045810-26-000021:16:2`: highlighted though only case/space/punctuation differ: sales
  - *code*: current diff reproduces it
- **NVDA** change `472606c9d458f2e9`, sentences `0001045810-25-000023:14:7`, `0001045810-26-000021:15:7`: highlighted though only case/space/punctuation differ: our
  - *code*: current diff reproduces it
- **NVDA** change `472606c9d458f2e9`, sentences `0001045810-25-000023:14:8`, `0001045810-26-000021:15:11`: highlighted though only case/space/punctuation differ: we
  - *code*: current diff reproduces it
- **NVDA** change `5f11cecb0925b7ee`, sentences `0001045810-25-000023:3:1`, `0001045810-26-000021:4:1`: highlighted though only case/space/punctuation differ: scrutiny
  - *code*: current diff reproduces it
- **NVDA** change `6827ebf0162cb806`, sentences `0001045810-25-000023:20:0`, `0001045810-26-000021:22:0`: highlighted though only case/space/punctuation differ: scrutiny
  - *code*: current diff reproduces it
- **SF** change `3b93c57e20a358e4`, sentences `0000950170-25-027702:14:17`, `0001193125-26-067130:14:19`: highlighted though only case/space/punctuation differ: we
  - *code*: current diff reproduces it
- **SF** change `3b93c57e20a358e4`, sentences `0000950170-25-027702:14:24`, `0001193125-26-067130:14:23`: highlighted though only case/space/punctuation differ: maintain
  - *stale*, re-run from stage 5: current diff no longer marks these words
- **SF** change `3b93c57e20a358e4`, sentences `0000950170-25-027702:14:29`, `0001193125-26-067130:14:29`: highlighted though only case/space/punctuation differ: such
  - *code*: current diff reproduces it
- **SF** change `3b93c57e20a358e4`, sentences `0000950170-25-027702:14:30`, `0001193125-26-067130:14:30`: highlighted though only case/space/punctuation differ: substantial, time
  - *code*: current diff reproduces it
- **SF** change `3b93c57e20a358e4`, sentences `0000950170-25-027702:14:37`, `0001193125-26-067130:14:37`: highlighted though only case/space/punctuation differ: unauthorized
  - *code*: current diff reproduces it
- **SF** change `3b93c57e20a358e4`, sentences `0000950170-25-027702:14:40`, `0001193125-26-067130:14:39`: highlighted though only case/space/punctuation differ: lapses
  - *code*: current diff reproduces it
- **SF** change `61ffb76925cf3bc2`, sentences `0000950170-25-027702:20:2`, `0001193125-26-067130:20:1`: highlighted though only case/space/punctuation differ: we
  - *code*: current diff reproduces it
- **SF** change `61ffb76925cf3bc2`, sentences `0000950170-25-027702:20:9`, `0001193125-26-067130:20:4`: highlighted though only case/space/punctuation differ: frameworks
  - *code*: current diff reproduces it
- **SF** change `6a8ab8f8ba0b3e6e`, sentences `0000950170-25-027702:11:17`, `0001193125-26-067130:11:21`: highlighted though only case/space/punctuation differ: we
  - *code*: current diff reproduces it
- **SF** change `faa01310d8a450a6`, sentences `0000950170-25-027702:5:5`, `0001193125-26-067130:5:5`: highlighted though only case/space/punctuation differ: in
  - *code*: current diff reproduces it
- **SF** change `faa01310d8a450a6`, sentences `0000950170-25-027702:5:7`, `0001193125-26-067130:5:6`: highlighted though only case/space/punctuation differ: changes
  - *code*: current diff reproduces it
- **SF** change `db2dc1bfc373add1`, sentences `0000950170-25-027702:18:4`, `0001193125-26-067130:18:3`: highlighted though only case/space/punctuation differ: own, policies
  - *code*: current diff reproduces it
- **SF** change `db2dc1bfc373add1`, sentences `0000950170-25-027702:18:9`, `0001193125-26-067130:18:5`: highlighted though only case/space/punctuation differ: associate
  - *code*: current diff reproduces it
- **SF** change `a3f929046016c860`, sentences `0000950170-25-027702:17:7`, `0001193125-26-067130:17:7`: highlighted though only case/space/punctuation differ: our
  - *code*: current diff reproduces it

### TITLES (50)

- **NVDA** change `a4156a06454f6dfd`, sentences —: 'We are subject to complex laws, rules…': ends with an ellipsis (truncated heading) (heading: 'We are subject to complex laws, rules, regulations, and political and other actions, including rest…')
  - *code*: the current fallback still gives 'We are subject to complex laws, rules…'
- **NVDA** change `32866661d1b11115`, sentences —: 'Failure to meet the evolving needs of…': ends with an ellipsis (truncated heading); ends mid-clause on 'of' (heading: 'Failure to meet the evolving needs of our industry and markets may adversely impact our financial r…')
  - *code*: the current fallback still gives 'Failure to meet the evolving needs of…'
- **NVDA** change `692187bd48c050c3`, sentences —: 'The following risk factors should be considered…': ends with an ellipsis (truncated heading) (heading: 'The following risk factors should be considered in addition to the other information in this Annual…')
  - *code*: the current fallback still gives 'The following risk factors should be considered…'
- **NVDA** change `f7a8d95bf7b51298`, sentences —: 'Business disruptions could harm our operations, lead…': ends with an ellipsis (truncated heading) (heading: 'Business disruptions could harm our operations, lead to a decline in revenue and increase our costs.')
  - *code*: the current fallback still gives 'Business disruptions could harm our operations, lead…'
- **NVDA** change `dfe9c44ef07b2d30`, sentences —: 'Long manufacturing lead times and uncertain supply…': ends with an ellipsis (truncated heading) (heading: 'Long manufacturing lead times and uncertain supply and capacity availability, combined with a failu…')
  - *code*: the current fallback still gives 'Long manufacturing lead times and uncertain supply…'
- **NVDA** change `76929d4c94edf687`, sentences —: 'Defects in our products have caused and…': ends with an ellipsis (truncated heading); ends mid-clause on 'and' (heading: 'Defects in our products have caused and could cause us to incur significant expenses to remediate,…')
  - *code*: the current fallback still gives 'Defects in our products have caused and…'
- **NVDA** change `b7c169267209801d`, sentences —: 'We receive a significant amount of our…': ends with an ellipsis (truncated heading); ends mid-clause on 'our' (heading: 'We receive a significant amount of our revenue from a limited number of partners and distributors a…')
  - *code*: the current fallback still gives 'We receive a significant amount of our…'
- **NVDA** change `1c8be25adeb58b98`, sentences —: 'International sales and operations are a significant…': ends with an ellipsis (truncated heading) (heading: 'International sales and operations are a significant part of our business, which exposes us to risk…')
  - *code*: the current fallback still gives 'International sales and operations are a significant…'
- **NVDA** change `472606c9d458f2e9`, sentences —: 'We may not be able to realize…': ends with an ellipsis (truncated heading) (heading: 'We may not be able to realize the potential benefits of business investments or acquisitions, and w…')
  - *code*: the current fallback still gives 'We may not be able to realize…'
- **NVDA** change `10122333e29876b3`, sentences —: 'Actions to adequately protect our IP rights…': ends with an ellipsis (truncated heading) (heading: 'Actions to adequately protect our IP rights could result in substantial costs to us and our ability…')
  - *code*: the current fallback still gives 'Actions to adequately protect our IP rights…'
- **NVDA** change `35fd73210c2228c8`, sentences —: 'Our operating results have in the past…': ends with an ellipsis (truncated heading) (heading: 'Our operating results have in the past fluctuated and may in the future fluctuate, and if our opera…')
  - *code*: the current fallback still gives 'Our operating results have in the past…'
- **NVDA** change `39ad1b38b2b34469`, sentences —: 'Our business is dependent upon the proper…': ends with an ellipsis (truncated heading) (heading: 'Our business is dependent upon the proper functioning of our business processes and information sys…')
  - *code*: the current fallback still gives 'Our business is dependent upon the proper…'
- **NVDA** change `3efe394c13cfbc9c`, sentences —: 'Our business is exposed to the burden…': ends with an ellipsis (truncated heading) (heading: 'Our business is exposed to the burden and risks associated with litigation, investigations and regu…')
  - *code*: the current fallback still gives 'Our business is exposed to the burden…'
- **NVDA** change `56b14b486f546efd`, sentences —: 'Long manufacturing lead times and uncertain supply…': ends with an ellipsis (truncated heading) (heading: 'Long manufacturing lead times and uncertain supply and capacity availability, combined with a failu…')
  - *code*: the current fallback still gives 'Long manufacturing lead times and uncertain supply…'
- **NVDA** change `5f11cecb0925b7ee`, sentences —: 'We are subject to complex laws, rules…': ends with an ellipsis (truncated heading) (heading: 'We are subject to complex laws, rules, regulations, and political and other actions, including rest…')
  - *code*: the current fallback still gives 'We are subject to complex laws, rules…'
- **NVDA** change `6827ebf0162cb806`, sentences —: 'Scrutiny from shareholders, regulators and others regarding…': ends with an ellipsis (truncated heading) (heading: 'Scrutiny from shareholders, regulators and others regarding our corporate sustainability practices…')
  - *code*: the current fallback still gives 'Scrutiny from shareholders, regulators and others regarding…'
- **NVDA** change `6d0df517b10be912`, sentences —: 'Delaware law and our certificate of incorporation…': ends with an ellipsis (truncated heading) (heading: 'Delaware law and our certificate of incorporation, bylaws and agreement with Microsoft could delay…')
  - *code*: the current fallback still gives 'Delaware law and our certificate of incorporation…'
- **NVDA** change `6ef9abded50fdc62`, sentences —: 'If we are unable to attract, retain…': ends with an ellipsis (truncated heading) (heading: 'If we are unable to attract, retain and motivate our executives and key employees, our business may…')
  - *code*: the current fallback still gives 'If we are unable to attract, retain…'
- **NVDA** change `8789091d41a73853`, sentences —: 'We may have exposure to additional tax…': ends with an ellipsis (truncated heading) (heading: 'We may have exposure to additional tax liabilities and our operating results may be adversely impac…')
  - *code*: the current fallback still gives 'We may have exposure to additional tax…'
- **NVDA** change `96dc984e6bfa0fbe`, sentences —: 'We are subject to stringent and changing…': ends with an ellipsis (truncated heading) (heading: 'We are subject to stringent and changing data privacy and security laws, rules, regulations and oth…')
  - *code*: the current fallback still gives 'We are subject to stringent and changing…'
- **NVDA** change `ad4f3805e248f79e`, sentences —: 'Climate change may have a long-term impact…': ends with an ellipsis (truncated heading) (heading: 'Climate change may have a long-term impact on our business.')
  - *code*: the current fallback still gives 'Climate change may have a long-term impact…'
- **NVDA** change `c19cbbb3b2e9dc2c`, sentences —: 'Dependency on third-party suppliers and their technology…': ends with an ellipsis (truncated heading) (heading: 'Dependency on third-party suppliers and their technology to manufacture, assemble, test, or package…')
  - *code*: the current fallback still gives 'Dependency on third-party suppliers and their technology…'
- **NVDA** change `cce082e1f3b27e76`, sentences —: 'Product, system security, and data protection incidents…': ends with an ellipsis (truncated heading) (heading: 'Product, system security, and data protection incidents or breaches, as well as cyber-attacks, coul…')
  - *code*: the current fallback still gives 'Product, system security, and data protection incidents…'
- **NVDA** change `df98eb8f5ae3787c`, sentences —: 'Competition could adversely impact our market share…': ends with an ellipsis (truncated heading) (heading: 'Competition could adversely impact our market share and financial results.')
  - *code*: the current fallback still gives 'Competition could adversely impact our market share…'
- **NVDA** change `e0d772dcef65caf2`, sentences —: 'Issues relating to the responsible use of…': ends with an ellipsis (truncated heading); ends mid-clause on 'of' (heading: 'Issues relating to the responsible use of our technologies, including AI in our offerings, may resu…')
  - *code*: the current fallback still gives 'Issues relating to the responsible use of…'
- **SF** change `3b93c57e20a358e4`, sentences —: 'Cyber attack or other security breach of…': ends with an ellipsis (truncated heading); ends mid-clause on 'of' (heading: 'Cyber attack or other security breach of our technology systems, or those of other third parties we…')
  - *code*: the current fallback still gives 'Cyber attack or other security breach of…'
- **SF** change `61ffb76925cf3bc2`, sentences —: 'We are subject to risks relating to…': ends with an ellipsis (truncated heading); ends mid-clause on 'to' (heading: 'We are subject to risks relating to environmental, social, and governance matters that could advers…')
  - *code*: the current fallback still gives 'We are subject to risks relating to…'
- **SF** change `6a8ab8f8ba0b3e6e`, sentences —: 'We face intense competition and pricing pressures…': ends with an ellipsis (truncated heading) (heading: 'We face intense competition and pricing pressures and may not be able to keep pace with technologic…')
  - *code*: the current fallback still gives 'We face intense competition and pricing pressures…'
- **SF** change `faa01310d8a450a6`, sentences —: 'Our business is sensitive to domestic and…': ends with an ellipsis (truncated heading); ends mid-clause on 'and' (heading: 'Our business is sensitive to domestic and international macroeconomic conditions caused by politica…')
  - *code*: the current fallback still gives 'Our business is sensitive to domestic and…'
- **SF** change `db2dc1bfc373add1`, sentences —: 'Associate misconduct, which is difficult to detect…': ends with an ellipsis (truncated heading) (heading: 'Associate misconduct, which is difficult to detect and deter, could harm us by impairing our abilit…')
  - *code*: the current fallback still gives 'Associate misconduct, which is difficult to detect…'
- **SF** change `c9c637a7b6f09af9`, sentences —: 'A downgrade in our credit ratings could…': ends with an ellipsis (truncated heading); ends mid-clause on 'could' (heading: 'A downgrade in our credit ratings could have a material adverse effect on our operations, earnings,…')
  - *code*: the current fallback still gives 'A downgrade in our credit ratings could…'
- **SF** change `cdde20b394f48139`, sentences —: 'Financial services firms are highly regulated and…': ends with an ellipsis (truncated heading); ends mid-clause on 'and' (heading: 'Financial services firms are highly regulated and are subject to new and proposed regulations, all…')
  - *code*: the current fallback still gives 'Financial services firms are highly regulated and…'
- **SF** change `004fde9f3c9e2280`, sentences —: 'We are exposed to litigation and regulatory…': ends with an ellipsis (truncated heading) (heading: 'We are exposed to litigation and regulatory investigations and proceedings, which could materially…')
  - *code*: the current fallback still gives 'We are exposed to litigation and regulatory…'
- **SF** change `01c4bf9a6fdd34a1`, sentences —: 'Numerous regulatory changes and enhanced regulatory and…': ends with an ellipsis (truncated heading); ends mid-clause on 'and' (heading: 'Numerous regulatory changes and enhanced regulatory and enforcement activity relating to our asset…')
  - *code*: the current fallback still gives 'Numerous regulatory changes and enhanced regulatory and…'
- **SF** change `110fd3809db62155`, sentences —: 'As a financial holding company, our company’s…': ends with an ellipsis (truncated heading) (heading: 'As a financial holding company, our company’s liquidity depends on payments from its subsidiaries,…')
  - *code*: the current fallback still gives 'As a financial holding company, our company’s…'
- **SF** change `1860d97fe1f9183e`, sentences —: 'A continued interruption to our telecommunications or…': ends with an ellipsis (truncated heading); ends mid-clause on 'or' (heading: 'A continued interruption to our telecommunications or data processing systems, or the failure to ef…')
  - *code*: the current fallback still gives 'A continued interruption to our telecommunications or…'
- **SF** change `1d17926540b996ca`, sentences —: 'The soundness of other financial institutions and…': ends with an ellipsis (truncated heading); ends mid-clause on 'and' (heading: 'The soundness of other financial institutions and intermediaries affects us.')
  - *code*: the current fallback still gives 'The soundness of other financial institutions and…'
- **SF** change `5b166d3768038548`, sentences —: 'The development and use of artificial intelligence…': ends with an ellipsis (truncated heading) (heading: 'The development and use of artificial intelligence presents risks and challenges that could adverse…')
  - *code*: the current fallback still gives 'The development and use of artificial intelligence…'
- **SF** change `6273be7b6d05488d`, sentences —: 'Failure to comply with regulatory capital requirements…': ends with an ellipsis (truncated heading) (heading: 'Failure to comply with regulatory capital requirements primarily applicable to our company, our ban…')
  - *code*: the current fallback still gives 'Failure to comply with regulatory capital requirements…'
- **SF** change `688d9a8f3df31b31`, sentences —: 'Business growth, including through acquisitions, could increase…': ends with an ellipsis (truncated heading) (heading: 'Business growth, including through acquisitions, could increase costs and regulatory and integratio…')
  - *code*: the current fallback still gives 'Business growth, including through acquisitions, could increase…'
- **SF** change `6e2490b399eb9eb4`, sentences —: 'Changes in requirements relating to the standard…': ends with an ellipsis (truncated heading) (heading: 'Changes in requirements relating to the standard of care for broker-dealers have increased, and may…')
  - *code*: the current fallback still gives 'Changes in requirements relating to the standard…'
- **SF** change `9544e9cba9256740`, sentences —: 'Our operations and financial results are subject…': ends with an ellipsis (truncated heading) (heading: 'Our operations and financial results are subject to various risks and uncertainties, including thos…')
  - *code*: the current fallback still gives 'Our operations and financial results are subject…'
- **SF** change `9fa16d1123110dd3`, sentences —: 'Our business depends on fees earned from…': ends with an ellipsis (truncated heading); ends mid-clause on 'from' (heading: 'Our business depends on fees earned from the management of client accounts and asset management fee…')
  - *code*: the current fallback still gives 'Our business depends on fees earned from…'
- **SF** change `a3f929046016c860`, sentences —: 'Our risk management and conflicts of interest…': ends with an ellipsis (truncated heading) (heading: 'Our risk management and conflicts of interest policies and procedures may leave us exposed to unide…')
  - *code*: the current fallback still gives 'Our risk management and conflicts of interest…'
- **SF** change `b5a154b2ec7f44e6`, sentences —: 'We are exposed to market risk, including…': ends with an ellipsis (truncated heading); ends mid-clause on 'including' (heading: 'We are exposed to market risk, including interest rate risk.')
  - *code*: the current fallback still gives 'We are exposed to market risk, including…'
- **SF** change `c092b5083dee157f`, sentences —: 'The preparation of the consolidated financial statements…': ends with an ellipsis (truncated heading) (heading: 'The preparation of the consolidated financial statements requires the use of estimates that may var…')
  - *code*: the current fallback still gives 'The preparation of the consolidated financial statements…'
- **SF** change `da70c265a7c8e9a9`, sentences —: 'The Basel III regulatory capital standards impose…': ends with an ellipsis (truncated heading) (heading: 'The Basel III regulatory capital standards impose capital and other requirements on us that could n…')
  - *code*: the current fallback still gives 'The Basel III regulatory capital standards impose…'
- **SF** change `e05b4ea6d5ef463f`, sentences —: 'Our underwriting, market-making, trading, and other business…': ends with an ellipsis (truncated heading) (heading: 'Our underwriting, market-making, trading, and other business activities place our capital at risk.')
  - *code*: the current fallback still gives 'Our underwriting, market-making, trading, and other business…'
- **SF** change `fa831ff1fb46062f`, sentences —: 'Lack of funding, liquidity, or access to…': ends with an ellipsis (truncated heading); ends mid-clause on 'to' (heading: 'Lack of funding, liquidity, or access to capital could impair our business and financial condition.')
  - *code*: the current fallback still gives 'Lack of funding, liquidity, or access to…'
- **SF** change `fee898b2afc93812`, sentences —: 'Our ability to attract and retain senior…': ends with an ellipsis (truncated heading) (heading: 'Our ability to attract and retain senior professionals, qualified financial advisors, and other ass…')
  - *code*: the current fallback still gives 'Our ability to attract and retain senior…'

### PREAMBLE (1)

- **NVDA** change `692187bd48c050c3`, sentences `0001045810-26-000021:0:0`: 'The following risk factors should be considered in addition to the other information in this Annual Report on Form 10-K.': heading is the Item 1A introduction
  - *stale*, re-run from stage 2: segment 0.2.1 skips intro and summary units; confirmed only by a re-run from stage 2

### ENTITY (5)

- **NVDA** change `a4156a06454f6dfd`, sentences `0001045810-26-000021:21:64`: 'AI Diffusion IFR in': post-filter changes it to 'AI Diffusion IFR' (trailing/leading stopword); trailing preposition
  - *stale*, re-run from stage 6: current entity code no longer emits it
- **NVDA** change `a4156a06454f6dfd`, sentences `0001045810-26-000021:21:71`: 'Biden Administration': bare government administration
  - *code*: current entity code still emits it
- **NVDA** change `a4156a06454f6dfd`, sentences `0001045810-26-000021:21:47`, `0001045810-26-000021:21:63`: 'D:4': dropped by the entity post-filter (code or too short); short code; on the trends entity stoplist
  - *stale*, re-run from stage 6: current entity code no longer emits it
- **NVDA** change `a4156a06454f6dfd`, sentences `0001045810-26-000021:21:71`: 'Trump Administration': bare government administration
  - *code*: current entity code still emits it
- **SF** change `61ffb76925cf3bc2`, sentences `0001193125-26-067130:20:2`, `0001193125-26-067130:20:11`: 'SEC': on the trends entity stoplist
  - *code*: current entity code still emits it

### STALE (2)

- **NVDA** change —, sentences —: rubric 1.0.0 != 1.1.0; code fingerprint f7ef0450bbe6 != current e94330fbe528
  - *stale*, re-run from stage 2: stage versions are not recorded in this report; the earliest stage is inferred from the other findings
- **SF** change —, sentences —: rubric 1.0.0 != 1.1.0; code fingerprint f7ef0450bbe6 != current e94330fbe528
  - *stale*, re-run from stage 5: stage versions are not recorded in this report; the earliest stage is inferred from the other findings

