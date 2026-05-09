import { NextRequest, NextResponse } from "next/server";

import { readLogTailFast } from "@/lib/observability";

export async function GET(request: NextRequest): Promise<NextResponse> {
  const logPath = request.nextUrl.searchParams.get("logPath") ?? "";
  if (!logPath) {
    return NextResponse.json({ error: "Missing logPath" }, { status: 400 });
  }

  try {
    const { tail, isTruncated } = readLogTailFast(logPath);
    return NextResponse.json({ tail, isTruncated });
  } catch {
    return NextResponse.json({ error: `Run log is missing: ${logPath}` }, { status: 404 });
  }
}
