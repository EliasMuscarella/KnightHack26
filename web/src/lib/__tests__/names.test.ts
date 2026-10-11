import assert from "node:assert/strict";
import { test } from "node:test";

import { displayName } from "../names.ts";

test("drops corporate suffixes and title-cases", () => {
  assert.equal(displayName("AMAZON COM INC"), "Amazon");
  assert.equal(displayName("FIRST SOLAR INC"), "First Solar");
  assert.equal(displayName("STIFEL FINANCIAL CORP"), "Stifel");
  assert.equal(displayName("WELLS FARGO & COMPANY/MN"), "Wells Fargo");
  assert.equal(displayName("ACME HOLDINGS LTD"), "Acme");
});

test("keeps acronyms and house styles", () => {
  assert.equal(displayName("NVIDIA CORP"), "NVIDIA");
  assert.equal(displayName("ADVANCED MICRO DEVICES INC"), "AMD");
  assert.equal(displayName("INTERNATIONAL BUSINESS MACHINES CORP"), "IBM");
  assert.equal(displayName("BANK OF NEW YORK MELLON CORP"), "BNY");
  assert.equal(displayName("AT&T INC."), "AT&T");
  assert.equal(displayName("MCDONALDS CORP"), "McDonald's");
  assert.equal(displayName("CrowdStrike Holdings, Inc."), "CrowdStrike");
  assert.equal(displayName("TAKE TWO INTERACTIVE SOFTWARE INC"), "Take-Two Interactive");
  assert.equal(displayName("ELI LILLY & Co"), "Eli Lilly");
  // A suffix drop never leaves a dangling ampersand behind.
  assert.equal(displayName("SMITH & CO"), "Smith");
});

test("never returns an empty name and handles odd input", () => {
  assert.equal(displayName("INC"), "Inc");
  assert.equal(displayName("  "), "");
  assert.equal(displayName(null), "");
  assert.equal(displayName("BANK OF AMERICA CORP /DE/"), "Bank of America");
});
