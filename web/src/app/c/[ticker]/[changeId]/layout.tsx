import { notFound } from "next/navigation";

import { getComparison } from "@/lib/data";
import { CHANGE_ID_RE, normalizeTicker } from "@/lib/ticker";

export const dynamic = "force-dynamic";

/**
 * Checks the change id before the `[changeId]/loading.tsx` boundary renders, so an unknown
 * change id returns a real HTTP 404 (caught by `c/[ticker]/not-found.tsx`).
 */
export default async function ChangeLayout({ children, params }: LayoutProps<"/c/[ticker]/[changeId]">) {
  const { ticker: raw, changeId } = await params;
  const ticker = normalizeTicker(raw);
  if (!ticker || !CHANGE_ID_RE.test(changeId)) notFound();
  const result = await getComparison(ticker);
  if (!result || !result.comparison.changes.some((c) => c.id === changeId)) notFound();
  return children;
}
