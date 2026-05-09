import { NextRequest, NextResponse } from "next/server";

import { readFullLog } from "@/lib/observability";

export async function GET(request: NextRequest): Promise<NextResponse> {
  const logPath = request.nextUrl.searchParams.get("logPath") ?? "";
  if (!logPath) {
    return NextResponse.json({ error: "Missing logPath" }, { status: 400 });
  }

  try {
    const text = readFullLog(logPath);
    return new NextResponse(text, {
      status: 200,
      headers: {
        "Content-Type": "text/plain; charset=utf-8",
      },
    });
  } catch {
    return NextResponse.json({ error: `Run log is missing: ${logPath}` }, { status: 404 });
  }
}
