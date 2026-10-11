/**
 * Deterministic ordering helpers for the briefing model. No locale-dependent comparison
 * (`localeCompare` can differ between runtimes): strings compare by code unit, names compare
 * case-folded first and then raw, so every sort has a total, stable tie-break.
 */

/** Plain code-unit comparison. */
export function cmpStr(a: string, b: string): number {
  return a < b ? -1 : a > b ? 1 : 0;
}

/** Case-insensitive name order with a raw tie-break (like the pipeline's `(s.casefold(), s)`). */
export function cmpName(a: string, b: string): number {
  return cmpStr(a.toLowerCase(), b.toLowerCase()) || cmpStr(a, b);
}

/** Descending numeric order. */
export function cmpDesc(a: number, b: number): number {
  return b - a;
}

const MAGNITUDE_RE = /(\d[\d,]*(?:\.\d+)?)\s*(trillion|billion|million|thousand)?/i;
const MULT: Record<string, number> = { trillion: 1e12, billion: 1e9, million: 1e6, thousand: 1e3 };

/**
 * Numeric size of a figure ("$4.5 billion" -> 4.5e9; "12% -> 22%" uses the new value).
 * Port of `_magnitude` in pipeline/highlights.py.
 */
export function figureMagnitude(value: string | null | undefined): number {
  const parts = (value ?? "").split("->");
  const v = parts[parts.length - 1];
  const m = MAGNITUDE_RE.exec(v);
  if (!m) return 0;
  const n = Number(m[1].replace(/,/g, ""));
  if (!Number.isFinite(n)) return 0;
  return n * (MULT[(m[2] ?? "").toLowerCase()] ?? 1);
}

/**
 * Dollar amounts before percentages before other quantities, larger figures first (a finance
 * reader's order). Port of `_figure_order` in pipeline/highlights.py; a missing figure sorts last.
 */
export function figureOrder(value: string | null | undefined): [number, number] {
  const v = value ?? "";
  if (!v.trim()) return [3, 0];
  const kind = v.includes("$") ? 0 : v.includes("%") || v.toLowerCase().includes("percent") ? 1 : 2;
  return [kind, -figureMagnitude(v)];
}

export function cmpFigure(a: string | null | undefined, b: string | null | undefined): number {
  const [ka, ma] = figureOrder(a);
  const [kb, mb] = figureOrder(b);
  return ka - kb || ma - mb;
}
