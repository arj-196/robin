import { NextResponse } from "next/server";

import { getAllRunHistory } from "@/lib/observability";

const DEFAULT_HISTORY_LIMIT = 500;

export async function GET(): Promise<NextResponse> {
  const rawLimit = (process.env.HISTORY_DASHBOARD_HISTORY_LIMIT ?? String(DEFAULT_HISTORY_LIMIT)).trim();
  const limit = Number.parseInt(rawLimit, 10);
  const safeLimit = Number.isFinite(limit) && limit > 0 ? limit : DEFAULT_HISTORY_LIMIT;
  const records = getAllRunHistory(safeLimit);
  return NextResponse.json({ records, total: records.length });
}
