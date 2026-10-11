import { NextResponse } from "next/server";

import { getTickerTapeFromApi } from "@/lib/api";
import { UNAVAILABLE_TAPE } from "@/lib/tickerTape";

export const dynamic = "force-dynamic";

/** Same-origin proxy for the home page ticker tape's once-a-minute refresh. */
export async function GET() {
  const tape = await getTickerTapeFromApi(4000);
  return NextResponse.json(tape ?? UNAVAILABLE_TAPE, { headers: { "Cache-Control": "no-store" } });
}
