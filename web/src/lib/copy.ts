/** Shared UI copy. Neutral wording only: a disclosure change is not a measure of risk. */
export const DISCLAIMER =
  "Not investment advice. RiskDiff shows changes in disclosed risk language, not changes in actual risk.";

export const FIXTURE_BANNER = "FIXTURE DATA — synthetic, not from any SEC filing";

/** Shared-library status lines (footer and audit trail). "disabled"/unknown show nothing. */
export const LIBRARY_STATUS_COPY: Partial<Record<string, string>> = {
  ok: "Shared library: connected",
  connecting: "Shared library: connecting",
  offline: "Shared library: offline, showing reports on this computer",
};
