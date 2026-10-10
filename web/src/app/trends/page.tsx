import type { Metadata } from "next";

import { TrendsView } from "@/components/TrendsView";
import { getTrends } from "@/lib/data";

export const dynamic = "force-dynamic";

export const metadata: Metadata = { title: "Trends" };

export default async function TrendsPage() {
  return <TrendsView trends={await getTrends()} />;
}
