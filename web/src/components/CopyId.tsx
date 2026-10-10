"use client";

import { useState } from "react";

/** Monospace id, truncated by default; click to expand, copy button copies the full value. */
export function CopyId({ value, label = "analysis id", visibleChars = 16 }: { value: string; label?: string; visibleChars?: number }) {
  const [expanded, setExpanded] = useState(false);
  const [copied, setCopied] = useState<"ok" | "fail" | null>(null);
  const truncated = value.length > visibleChars ? `${value.slice(0, visibleChars)}…` : value;

  async function copy() {
    try {
      await navigator.clipboard.writeText(value);
      setCopied("ok");
    } catch {
      setCopied("fail");
      setExpanded(true);
    }
    setTimeout(() => setCopied(null), 2000);
  }

  return (
    <span className="inline-flex min-w-0 max-w-full items-center gap-2">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        title={value}
        aria-expanded={expanded}
        aria-label={`${label}: ${value}. ${expanded ? "Collapse" : "Show full value"}`}
        className={`min-w-0 rounded bg-sunken px-1.5 py-0.5 text-left font-mono text-xs text-ink hover:bg-line ${
          expanded ? "break-all" : "truncate"
        }`}
      >
        {expanded ? value : truncated}
      </button>
      <button
        type="button"
        onClick={copy}
        className="shrink-0 rounded border border-line-strong bg-surface px-2 py-0.5 text-xs font-medium text-ink-muted hover:border-accent hover:text-ink"
      >
        {copied === "ok" ? "✓ Copied" : copied === "fail" ? "Select to copy" : "Copy"}
      </button>
    </span>
  );
}
