import { NextRequest } from "next/server";
import { afterEach, describe, expect, it } from "vitest";

import { middleware } from "./middleware";

const ORIGINAL_USERNAME = process.env.HISTORY_DASHBOARD_AUTH_USERNAME;
const ORIGINAL_PASSWORD = process.env.HISTORY_DASHBOARD_AUTH_PASSWORD;

function setAuthEnv(username?: string, password?: string): void {
  if (username === undefined) {
    delete process.env.HISTORY_DASHBOARD_AUTH_USERNAME;
  } else {
    process.env.HISTORY_DASHBOARD_AUTH_USERNAME = username;
  }

  if (password === undefined) {
    delete process.env.HISTORY_DASHBOARD_AUTH_PASSWORD;
  } else {
    process.env.HISTORY_DASHBOARD_AUTH_PASSWORD = password;
  }
}

function buildAuthHeader(username: string, password: string): string {
  const encoded = Buffer.from(`${username}:${password}`, "utf-8").toString("base64");
  return `Basic ${encoded}`;
}

afterEach(() => {
  if (ORIGINAL_USERNAME === undefined) {
    delete process.env.HISTORY_DASHBOARD_AUTH_USERNAME;
  } else {
    process.env.HISTORY_DASHBOARD_AUTH_USERNAME = ORIGINAL_USERNAME;
  }

  if (ORIGINAL_PASSWORD === undefined) {
    delete process.env.HISTORY_DASHBOARD_AUTH_PASSWORD;
  } else {
    process.env.HISTORY_DASHBOARD_AUTH_PASSWORD = ORIGINAL_PASSWORD;
  }
});

describe("history dashboard middleware auth", () => {
  it("allows request when credentials are unset (open access fallback)", () => {
    setAuthEnv(undefined, undefined);
    const request = new NextRequest("http://localhost:3000/api/history");

    const response = middleware(request);

    expect(response.status).toBe(200);
    expect(response.headers.get("x-middleware-next")).toBe("1");
  });

  it("rejects request with missing authorization header", () => {
    setAuthEnv("admin", "secret");
    const request = new NextRequest("http://localhost:3000/api/history");

    const response = middleware(request);

    expect(response.status).toBe(401);
    expect(response.headers.get("www-authenticate")).toBe('Basic realm="History Dashboard"');
  });

  it("rejects request with wrong credentials", () => {
    setAuthEnv("admin", "secret");
    const request = new NextRequest("http://localhost:3000/api/history", {
      headers: {
        authorization: buildAuthHeader("admin", "bad-password"),
      },
    });

    const response = middleware(request);

    expect(response.status).toBe(401);
    expect(response.headers.get("www-authenticate")).toBe('Basic realm="History Dashboard"');
  });

  it("allows request with valid credentials", () => {
    setAuthEnv("admin", "secret");
    const request = new NextRequest("http://localhost:3000/api/history", {
      headers: {
        authorization: buildAuthHeader("admin", "secret"),
      },
    });

    const response = middleware(request);

    expect(response.status).toBe(200);
    expect(response.headers.get("x-middleware-next")).toBe("1");
  });
});

