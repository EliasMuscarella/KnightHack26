/** The nine pipeline stages, in order. Labels match the API's StageEvent names. */
export type StageKind = "deterministic" | "ai";

export interface StageInfo {
  stage: number;
  label: string;
  kind: StageKind;
  /** Short explanation for the analyze explainer and the methodology diagram. */
  description: string;
}

export const STAGES: StageInfo[] = [
  {
    stage: 0,
    label: "Fetch filings from EDGAR",
    kind: "deterministic",
    description:
      "Looks up the company on SEC EDGAR and downloads its two most recent original 10-K filings (amendments excluded). Every request identifies itself and stays within SEC fair-access limits.",
  },
  {
    stage: 1,
    label: "Extract Item 1A",
    kind: "deterministic",
    description:
      "Finds the Risk Factors section (Item 1A) in each filing, skipping the table of contents and stopping at Item 1B, 1C or 2.",
  },
  {
    stage: 2,
    label: "Segment risk factors",
    kind: "deterministic",
    description:
      "Splits Item 1A into risk blocks (a heading plus its body), then into sentences with stable ids and character offsets back into the filing text.",
  },
  {
    stage: 3,
    label: "Embed risk blocks",
    kind: "ai",
    description:
      "A local embedding model turns each risk block into a vector so that equivalent risks can be recognized even when the wording moved.",
  },
  {
    stage: 4,
    label: "Match risks across years",
    kind: "deterministic",
    description:
      "Pairs old and new risk blocks with an optimal assignment over heading and body similarity. Pairs below the published threshold become new or removed risks.",
  },
  {
    stage: 5,
    label: "Sentence-level diff",
    kind: "deterministic",
    description:
      "Aligns sentences inside each matched pair, computes word-level insertions and deletions, and classifies the change (new, removed, expanded, reduced, reworded, largely unchanged).",
  },
  {
    stage: 6,
    label: "Deterministic signals",
    kind: "deterministic",
    description:
      "Rule-based detectors with citations: hedged wording that became actual wording, newly named entities, new quantities, and the share of added or removed text.",
  },
  {
    stage: 7,
    label: "AI rubric + interpretation",
    kind: "ai",
    description:
      "A language model answers narrow yes/no rubric questions and writes short interpretations. A citation validator drops every claim that does not cite valid filing sentences.",
  },
  {
    stage: 8,
    label: "Score + publish",
    kind: "deterministic",
    description:
      "Adds up published rubric weights into a 0 to 100 change score with an itemized breakdown, then writes the comparison file with a reproducible analysis id.",
  },
];
