import { LIBRARY_STATUS_COPY } from "@/lib/copy";
import type { LibraryStatus } from "@/lib/types";

/** One quiet line about the shared report library; renders nothing when disabled or unknown. */
export function LibraryStatusLine({ status, size = "xs" }: { status: LibraryStatus; size?: "xs" | "sm" }) {
  const text = LIBRARY_STATUS_COPY[status];
  if (!text) return null;
  return (
    <p className={`${size === "sm" ? "text-sm" : "text-xs"} text-ink-secondary`} data-library-status={status}>
      {text}
    </p>
  );
}
