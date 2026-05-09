import { NextRequest, NextResponse } from "next/server";

const REALM = 'Basic realm="History Dashboard"';

function unauthorizedResponse(): NextResponse {
  return new NextResponse("Authentication required", {
    status: 401,
    headers: {
      "WWW-Authenticate": REALM,
    },
  });
}

function decodeBasicAuthHeader(value: string): { username: string; password: string } | null {
  if (!value.startsWith("Basic ")) {
    return null;
  }

  const encoded = value.slice("Basic ".length).trim();
  if (!encoded) {
    return null;
  }

  try {
    const decoded = atob(encoded);
    const separatorIndex = decoded.indexOf(":");
    if (separatorIndex < 0) {
      return null;
    }

    return {
      username: decoded.slice(0, separatorIndex),
      password: decoded.slice(separatorIndex + 1),
    };
  } catch {
    return null;
  }
}

function getConfiguredCredentials(): { username: string; password: string } | null {
  const username = (process.env.HISTORY_DASHBOARD_AUTH_USERNAME ?? "").trim();
  const password = (process.env.HISTORY_DASHBOARD_AUTH_PASSWORD ?? "").trim();

  if (!username || !password) {
    return null;
  }

  return { username, password };
}

export function middleware(request: NextRequest): NextResponse {
  const credentials = getConfiguredCredentials();
  if (!credentials) {
    return NextResponse.next();
  }

  const authorization = request.headers.get("authorization") ?? "";
  const parsed = decodeBasicAuthHeader(authorization);
  if (!parsed) {
    return unauthorizedResponse();
  }

  if (
    parsed.username !== credentials.username ||
    parsed.password !== credentials.password
  ) {
    return unauthorizedResponse();
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/", "/api/:path*"],
};

