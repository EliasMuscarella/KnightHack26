import { listKnownTickers } from "@/lib/data";

export const dynamic = "force-dynamic";

/** Tickers with a cached or API-served comparison, so the search box can choose overview vs live analysis. */
export async function GET() {
  const tickers = await listKnownTickers();
  return Response.json({ tickers }, { headers: { "Cache-Control": "no-store" } });
}
