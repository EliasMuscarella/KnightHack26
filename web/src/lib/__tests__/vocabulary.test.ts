import assert from "node:assert/strict";
import { test } from "node:test";

import { changeLevel, countedLabel, directionOf, displayTitle, levelSegments, shortTitleFromHeading } from "../vocabulary.ts";

const BANNED_FRAGMENTS = ["We are subject to complex laws", "Alphabet Inc", "The technology industry, including"];

test("short titles follow the clause rule: longest clean clause of 4 to 10 words, no ellipsis", () => {
  assert.equal(
    shortTitleFromHeading("Failure to meet the evolving needs of our industry and markets may adversely impact our financial results."),
    "Failure to meet the evolving needs of our industry",
  );
  assert.equal(shortTitleFromHeading("Commercial arrangements expose us to counterparty risks."), "Commercial arrangements expose us to counterparty risks");
  assert.equal(shortTitleFromHeading("The following risk factors should be considered in addition to the other information in this Annual Report on Form 10-K."), "The following risk factors");
  assert.equal(shortTitleFromHeading("  “Adverse economic conditions   may harm our business.”  "), "Adverse economic conditions may harm our business");
  // No qualifying clause: the first ten words, trailing dangling words removed.
  assert.equal(
    shortTitleFromHeading("Significant disruptions affecting manufacturing sites located across several regions of the world could occur."),
    "Significant disruptions affecting manufacturing sites located across several regions",
  );
  for (const t of [
    shortTitleFromHeading("Failure to meet the evolving needs of our industry and markets may adversely impact our financial results."),
    shortTitleFromHeading("The following risk factors should be considered in addition to the other information in this Annual Report on Form 10-K."),
  ]) {
    assert.ok(!t.endsWith("…") && t.split(" ").length <= 10);
  }
});

test("the brief's fragment examples do not come back", () => {
  // Synthetic headings shaped like the examples in the brief.
  const laws = shortTitleFromHeading(
    "We are subject to complex laws, rules, regulations and other actions, including restrictions on the export of our products, which may adversely impact our business.",
  );
  const tech = shortTitleFromHeading(
    "The technology industry, including the Internet and mobile platforms, is subject to rapid change, which could harm our business.",
  );
  const company = displayTitle(
    "Alphabet Inc",
    "Alphabet Inc. faces intense competition in every market where its products are sold today.",
    "Alphabet Inc.",
  );
  assert.equal(laws, "We are subject to complex laws, rules, regulations");
  assert.equal(tech, "The technology industry, including the Internet and mobile platforms");
  assert.equal(company, "Alphabet Inc. faces intense competition in every market");
  for (const t of [laws, tech, company]) assert.ok(!BANNED_FRAGMENTS.includes(t), t);
  // A short title that is only the company name, with no heading to fall back on: no title.
  assert.equal(displayTitle("Alphabet Inc…", null, "Alphabet Inc."), "");
  // A company-name result is replaced by the first-words rule.
  assert.equal(
    shortTitleFromHeading("Acme Widget Supply Holdings, together with its subsidiaries across many different countries around the world, faces competition.", "Acme Widget Supply Holdings Inc"),
    "Acme Widget Supply Holdings, together with its subsidiaries across many",
  );
});

test("NVDA headings (data/published/NVDA_2025_2026.json) give the spec's titles", () => {
  const expected: [string, string][] = [
    ["We are subject to complex laws, rules, regulations and other actions, including restrictions on the export of our products, which may adversely impact our business.", "We are subject to complex laws, rules, regulations"],
    ["Commercial arrangements expose us to counterparty risks.", "Commercial arrangements expose us to counterparty risks"],
    ["Failure to meet the evolving needs of our industry and markets may adversely impact our financial results.", "Failure to meet the evolving needs of our industry"],
    ["The following risk factors should be considered in addition to the other information in this Annual Report on Form 10-K.", "The following risk factors"],
    ["Business disruptions could harm our operations, lead to a decline in revenue and increase our costs.", "Business disruptions could harm our operations"],
    ["Long manufacturing lead times and uncertain supply and capacity availability, combined with a failure to estimate customer demand accurately, has led and could lead to mismatches between supply and demand.", "Long manufacturing lead times and uncertain supply and capacity availability"],
    ["Defects in our products have caused and could cause us to incur significant expenses to remediate, which can damage our reputation and cause us to lose market share.", "Defects in our products have caused"],
    ["We receive a significant amount of our revenue from a limited number of partners and distributors and we have a concentration of sales to customers who purchase directly or indirectly from us, and our revenue could be adversely affected if we lose or are prevented from selling to any of these customers.", "We receive a significant amount of our revenue"],
    ["International sales and operations are a significant part of our business, which exposes us to risks that could harm our business.", "International sales and operations are a significant part"],
    ["We may not be able to realize the potential benefits of business investments or acquisitions, and we may not be able to successfully integrate acquired companies, which could hurt our ability to grow our business, develop new products or sell our products.", "We may not be able to realize the potential benefits"],
    ["Actions to adequately protect our IP rights could result in substantial costs to us and our ability to compete could be harmed if we are unsuccessful or if we are prohibited from making or selling our products.", "Actions to adequately protect our IP rights"],
    ["Risks Related to Our Industry and Markets", "Risks Related to Our Industry and Markets"],
    ["Our operating results have in the past fluctuated and may in the future fluctuate, and if our operating results are below the expectations of securities analysts or investors, our stock price could decline.", "Our operating results have in the past fluctuated"],
    ["Our business is dependent upon the proper functioning of our business processes and information systems and modification or interruption of such systems may disrupt our business and internal controls.", "Our business is dependent upon the proper functioning"],
    ["Our business is exposed to the burden and risks associated with litigation, investigations and regulatory proceedings.", "Our business is exposed to the burden"],
    ["Adverse economic conditions may harm our business.", "Adverse economic conditions may harm our business"],
    ["Long manufacturing lead times and uncertain supply and capacity availability, combined with a failure to estimate customer demand accurately has led and could lead to mismatches between supply and demand.", "Long manufacturing lead times and uncertain supply and capacity availability"],
    ["Scrutiny from shareholders, regulators and others regarding our corporate sustainability practices could result in additional costs or risks and adversely impact our reputation and willingness of customers and suppliers to do business with us.", "Scrutiny from shareholders, regulators"],
    ["Delaware law and our certificate of incorporation, bylaws and agreement with Microsoft could delay or prevent a change in control.", "Delaware law and our certificate of incorporation, bylaws"],
    ["If we are unable to attract, retain and motivate our executives and key employees, our business may be harmed.", "If we are unable to attract, retain"],
    ["We may have exposure to additional tax liabilities and our operating results may be adversely impacted by changes in tax laws, higher than expected tax rates and other tax-related factors.", "We may have exposure to additional tax liabilities"],
    ["We are subject to stringent and changing data privacy and security laws, rules, regulations and other obligations. These areas could damage our reputation, deter current and potential customers, affect our product design, or result in legal or regulatory proceedings and liability.", "We are subject to stringent and changing data privacy"],
    ["Climate change may have a long-term impact on our business.", "Climate change may have a long-term impact on our business"],
    ["Dependency on third-party suppliers and their technology to manufacture, assemble, test, or package our products reduces our control over product quantity and quality, manufacturing yields, and product delivery schedules and could harm our business.", "Dependency on third-party suppliers and their technology to manufacture, assemble"],
    ["Product, system security, and data protection incidents or breaches, as well as cyber-attacks, could disrupt our operations, reduce our expected revenue, increase our expenses, and significantly harm our business and reputation.", "Product, system security, and data protection incidents or breaches"],
    ["Competition could adversely impact our market share and financial results.", "Competition could adversely impact our market share and financial results"],
    ["Issues relating to the responsible use of our technologies, including AI in our offerings, may result in reputational or financial harm and liability.", "Issues relating to the responsible use of our technologies"],
  ];
  for (const [heading, title] of expected) {
    assert.equal(shortTitleFromHeading(heading, "NVIDIA CORP"), title, heading);
    assert.ok(!title.endsWith("…"));
  }
});

test("displayTitle uses a real short title and falls back from truncations and company names", () => {
  assert.equal(displayTitle("Export controls on China sales", "We are subject to complex laws…"), "Export controls on China sales");
  assert.equal(
    displayTitle("We are subject to complex laws, rules…", "We are subject to complex laws, rules, regulations actions."),
    "We are subject to complex laws, rules, regulations actions",
  );
  // Without the full heading (Trends rows) the truncation itself is cleaned; no ellipsis.
  assert.equal(displayTitle("We are subject to complex laws, rules…", null), "We are subject to complex laws, rules");
  assert.equal(displayTitle("Cyber attack or other security breach of…", null), "Cyber attack or other security breach");
  assert.equal(displayTitle("NVIDIA", "Competition could adversely impact our market share and financial results.", "NVIDIA CORP"), "Competition could adversely impact our market share and financial results");
});

test("counted labels pluralize nouns only", () => {
  assert.equal(countedLabel(2, "new"), "2 new risks");
  assert.equal(countedLabel(1, "materially_reworded"), "1 major update");
  assert.equal(countedLabel(5, "materially_reworded"), "5 major updates");
  assert.equal(countedLabel(3, "expanded"), "3 expanded");
});

test("direction and level mapping", () => {
  assert.equal(directionOf("new"), "more");
  assert.equal(directionOf("reduced"), "less");
  assert.equal(directionOf("materially_reworded"), "rewrite");
  assert.equal(directionOf("largely_unchanged"), "none");
  assert.deepEqual([changeLevel(60), changeLevel(25), changeLevel(24)], ["High", "Medium", "Low"]);
  assert.deepEqual([levelSegments(100), levelSegments(40), levelSegments(0)], [3, 2, 1]);
});
