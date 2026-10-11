import type { NextRequest } from "next/server";

import { briefingFilename, printOrigin, printUrl, renderBriefingPdf } from "@/lib/briefing/pdf";
import { parseSelection } from "@/lib/briefing/selection";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const NO_STORE = { "Cache-Control": "no-store" };

function jsonError(status: number, error: string): Response {
  return Response.json({ error }, { status, headers: NO_STORE });
}

/** GET /api/briefing.pdf?tickers=NVDA,AAPL&title=…&for=… → the Disclosure Briefing as a Letter PDF. */
export async function GET(request: NextRequest) {
  const search = request.nextUrl.searchParams;
  const params: Record<string, string[]> = {};
  for (const key of ["tickers", "title", "for"]) {
    const values = search.getAll(key);
    if (values.length) params[key] = values;
  }
  const sel = parseSelection(params);
  if (sel.tickers.length === 0) return jsonError(400, "Choose at least one valid ticker, for example tickers=NVDA,AAPL");

  // Only validated values reach the URL Chromium opens.
  const url = printUrl(printOrigin(request.url, process.env.RISKDIFF_WEB_ORIGIN), sel);
  const result = await renderBriefingPdf(url);
  if (!result.ok) return jsonError(result.status, result.error);

  return new Response(new Uint8Array(result.pdf), {
    status: 200,
    headers: {
      ...NO_STORE,
      "Content-Type": "application/pdf",
      "Content-Disposition": `attachment; filename="${briefingFilename(sel.tickers)}"`,
      "Content-Length": String(result.pdf.length),
    },
  });
}
