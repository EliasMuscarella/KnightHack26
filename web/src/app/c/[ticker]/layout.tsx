import { notFound } from "next/navigation";

import { getComparison } from "@/lib/data";
import { normalizeTicker } from "@/lib/ticker";

export const dynamic = "force-dynamic";

/**
 * Existence check before any Suspense boundary. The `loading.tsx` files live below this
 * layout (in the `(overview)` group and under `[changeId]`), so an unknown ticker reaches
 * notFound() before streaming starts and the response is a real HTTP 404, not a soft 404.
 * getComparison is request-cached, so the page below reuses this load.
 */
export default async function ComparisonLayout({ children, params }: LayoutProps<"/c/[ticker]">) {
  const { ticker: raw } = await params;
  const ticker = normalizeTicker(raw);
  if (!ticker) notFound();
  const result = await getComparison(ticker);
  if (!result) notFound();
  return children;
}
