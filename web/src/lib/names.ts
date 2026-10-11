/**
 * Display names for companies. SEC "conformed names" are shouted and suffixed
 * ("AMAZON COM INC", "NVIDIA CORP"); the interface shows "Amazon" and "NVIDIA". The official
 * name stays in the audit trail. Deterministic, no network, no special cases per ticker beyond
 * the documented exceptions map (acronyms and house styles).
 */

/** Uppercase words kept as written (acronyms, brands written in capitals). */
const KEEP_UPPER = new Set([
  "NVIDIA",
  "AMD",
  "IBM",
  "BNY",
  "AT&T",
  "HP",
  "HSBC",
  "UBS",
  "ING",
  "KKR",
  "PNC",
  "CVS",
  "UPS",
  "GE",
  "3M",
  "AIG",
  "ADP",
  "ASML",
  "SAP",
  "TSMC",
  "BP",
  "EQT",
  "DTE",
  "PPG",
  "NRG",
  "KLA",
  "ON",
  "LLC",
]);

/** Exact official names whose house style is not title case. */
const EXCEPTIONS: Record<string, string> = {
  "AMAZON COM INC": "Amazon",
  "NVIDIA CORP": "NVIDIA",
  "ADVANCED MICRO DEVICES INC": "AMD",
  "INTERNATIONAL BUSINESS MACHINES CORP": "IBM",
  "BANK OF NEW YORK MELLON CORP": "BNY",
  "BANK OF NEW YORK MELLON CORP /NY/": "BNY",
  "ALPHABET INC.": "Alphabet",
  "META PLATFORMS, INC.": "Meta",
  "MICROSOFT CORP": "Microsoft",
  "APPLE INC.": "Apple",
  "JPMORGAN CHASE & CO": "JPMorgan Chase",
  "GOLDMAN SACHS GROUP INC": "Goldman Sachs",
  "MORGAN STANLEY": "Morgan Stanley",
  "WELLS FARGO & COMPANY/MN": "Wells Fargo",
  "CITIGROUP INC": "Citigroup",
  "BLACKROCK, INC.": "BlackRock",
  "PAYPAL HOLDINGS, INC.": "PayPal",
  "SALESFORCE, INC.": "Salesforce",
  "ADOBE INC.": "Adobe",
  "NETFLIX INC": "Netflix",
  "TESLA, INC.": "Tesla",
  "EXXON MOBIL CORP": "ExxonMobil",
  "UNITEDHEALTH GROUP INC": "UnitedHealth",
  "JOHNSON & JOHNSON": "Johnson & Johnson",
  "PROCTER & GAMBLE CO": "Procter & Gamble",
  "COCA COLA CO": "Coca-Cola",
  "PEPSICO INC": "PepsiCo",
  "MCDONALDS CORP": "McDonald's",
  "WALMART INC.": "Walmart",
  "HOME DEPOT, INC.": "Home Depot",
  "STIFEL FINANCIAL CORP": "Stifel",
  "CROWDSTRIKE HOLDINGS, INC.": "CrowdStrike",
  "TAKE TWO INTERACTIVE SOFTWARE INC": "Take-Two Interactive",
  "ELI LILLY & CO": "Eli Lilly",
};

/** Corporate suffixes dropped from the END of a display name, repeatedly. */
const SUFFIXES = new Set([
  "CORP",
  "CORPORATION",
  "INC",
  "INCORPORATED",
  "CO",
  "COMPANY",
  "COM",
  "LTD",
  "LIMITED",
  "PLC",
  "LLC",
  "LP",
  "L.P.",
  "SA",
  "NV",
  "N.V.",
  "AG",
  "HOLDINGS",
  "HOLDING",
  "GROUP",
  "TRUST",
  "DE",
  "/DE/",
  "/DE",
  "/NY/",
  "/MN/",
  "/PA/",
  "/OH/",
  "/MD/",
  "/TX/",
  "/NEW/",
]);

/** Words kept lowercase inside a title-cased name. */
const SMALL = new Set(["of", "and", "the", "for", "in", "on", "at", "de", "la", "du", "von", "van"]);

function titleWord(raw: string, first: boolean): string {
  const w = raw.replace(/[,.]+$/g, "");
  if (!w) return "";
  if (KEEP_UPPER.has(w.toUpperCase())) return w.toUpperCase();
  if (/^[A-Z]&[A-Z]$/.test(w)) return w.toUpperCase();
  if (/\d/.test(w) && w.length <= 4) return w.toUpperCase();
  const lower = w.toLowerCase();
  if (!first && SMALL.has(lower)) return lower;
  // Mc/Mac prefixes and hyphenated parts: capitalize each part.
  return lower
    .split("-")
    .map((part) => {
      if (part.startsWith("mc") && part.length > 2) return "Mc" + part[2].toUpperCase() + part.slice(3);
      return part.charAt(0).toUpperCase() + part.slice(1);
    })
    .join("-");
}

/**
 * "AMAZON COM INC" -> "Amazon"; "NVIDIA CORP" -> "NVIDIA"; "STIFEL FINANCIAL CORP" -> "Stifel";
 * "FIRST SOLAR INC" -> "First Solar". Falls back to the trimmed input when nothing is left.
 */
export function displayName(official: string | null | undefined): string {
  const raw = (official ?? "").replace(/\s+/g, " ").trim();
  if (!raw) return "";
  const exact = EXCEPTIONS[raw.toUpperCase()];
  if (exact) return exact;
  const words = raw.split(" ");
  // Drop trailing suffixes ("INC", "CORP", "COM", "/DE/") but never the whole name.
  // A dropped suffix can leave a dangling "&" ("ELI LILLY & Co" -> "Eli Lilly"), which goes too.
  while (
    words.length > 1 &&
    (SUFFIXES.has(words[words.length - 1].toUpperCase().replace(/[,.]+$/g, "")) || words[words.length - 1] === "&")
  ) {
    words.pop();
  }
  // "NEW" in "AMAZON COM INC /NEW/"-style tails is covered above; plain "NEW" alone is kept.
  const out = words.map((w, i) => titleWord(w, i === 0)).filter(Boolean).join(" ");
  return out || raw;
}
