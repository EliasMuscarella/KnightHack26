import { NextResponse } from "next/server";

import { getTrendsFromApi } from "@/lib/api";

export const dynamic = "force-dynamic";

/** Same-origin proxy for the Trends page's client-side retries while the shared store connects. */
export async function GET() {
  const trends = await getTrendsFromApi(4000);
  return NextResponse.json(trends ?? { status: "offline" }, { headers: { "Cache-Control": "no-store" } });
}
