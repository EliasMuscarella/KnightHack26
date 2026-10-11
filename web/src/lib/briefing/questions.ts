/**
 * Follow-up questions for management (page 4). Each question is a fixed template chosen by the
 * basis of the item it is anchored to; the only inserted values are a figure string from the
 * deterministic signal. Templates ask; they never assert a cause, an impact or a risk level.
 */
import type { BeforeAfterQuote, ManagementQuestion, RiskListItem } from "./types";

export const MAX_QUESTIONS = 5;
/** First pass: at most this many questions per basis, so one template does not fill the page. */
export const MAX_PER_BASIS_FIRST_PASS = 2;

export const QUESTION_TEMPLATES = {
  potential_became_actual:
    "The filing now describes this as having happened. What is the expected ongoing impact, and what would change the disclosure next year?",
  new_risk: "What prompted a standalone risk factor on this subject this year, and what changed in the business behind it?",
  dropped_risk: "Was this risk judged no longer material, or was it merged into another risk factor?",
} as const;

/** "$1.4 billion -> $2.6 billion" -> ["$1.4 billion", "$2.6 billion"]; null when not a pair. */
function figurePair(detail: string | null): [string, string] | null {
  if (!detail || !detail.includes("->")) return null;
  const parts = detail.split("->").map((s) => s.trim());
  return parts.length === 2 && parts[0] && parts[1] ? [parts[0], parts[1]] : null;
}

export function figureQuestion(detail: string | null, figureChanged: boolean): string {
  const pair = figureChanged ? figurePair(detail) : null;
  if (pair) return `What explains the change in this figure from ${pair[0]} to ${pair[1]}, and is a further change expected under the same conditions?`;
  const figure = (detail ?? "").trim();
  return figure
    ? `How was the ${figure} figure determined, and is further exposure expected under the same conditions?`
    : "How was this figure determined, and is further exposure expected under the same conditions?";
}

/**
 * Up to MAX_QUESTIONS, drawn in order from potential-became-actual items, figure items, new risks
 * and dropped risks (each list already ranked), at most one question per risk factor. A first
 * pass takes at most MAX_PER_BASIS_FIRST_PASS per group, a second pass fills the rest in the
 * same order; the result keeps the group order.
 */
export function buildQuestions(actuals: BeforeAfterQuote[], figures: BeforeAfterQuote[], newRisks: RiskListItem[], droppedRisks: RiskListItem[]): ManagementQuestion[] {
  const groups: ManagementQuestion[][] = [
    actuals.map((a) => ({ ticker: a.ticker, name: a.name, changeId: a.changeId, riskFactorTitle: a.shortTitle, basis: "potential became actual", question: QUESTION_TEMPLATES.potential_became_actual })),
    figures.map((f) => ({
      ticker: f.ticker,
      name: f.name,
      changeId: f.changeId,
      riskFactorTitle: f.shortTitle,
      basis: f.figureChanged ? "changed figure" : "new figure",
      question: figureQuestion(f.detail, f.figureChanged),
    })),
    newRisks.map((r) => ({ ticker: r.ticker, name: r.name, changeId: r.changeId, riskFactorTitle: r.shortTitle, basis: "new", question: QUESTION_TEMPLATES.new_risk })),
    droppedRisks.map((r) => ({ ticker: r.ticker, name: r.name, changeId: r.changeId, riskFactorTitle: r.shortTitle, basis: "dropped", question: QUESTION_TEMPLATES.dropped_risk })),
  ];
  const used = new Set<string>();
  const picked: ManagementQuestion[][] = groups.map(() => []);
  let count = 0;
  for (const cap of [MAX_PER_BASIS_FIRST_PASS, Infinity]) {
    groups.forEach((g, i) => {
      for (const q of g) {
        if (count >= MAX_QUESTIONS || picked[i].length >= cap) return;
        const key = `${q.ticker}:${q.changeId}`;
        if (used.has(key)) continue;
        used.add(key);
        picked[i].push(q);
        count++;
      }
    });
  }
  return picked.flat();
}
