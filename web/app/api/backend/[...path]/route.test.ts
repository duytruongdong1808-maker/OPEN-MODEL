import { NextRequest } from "next/server";

import { auth } from "@/auth";
import { getRateLimiter } from "@/lib/rate-limit";

vi.mock("@/auth", () => ({
  auth: vi.fn(),
}));

vi.mock("@/lib/rate-limit", async () => {
  const actual = await vi.importActual<typeof import("@/lib/rate-limit")>("@/lib/rate-limit");
  return {
    ...actual,
    getRateLimiter: vi.fn(),
  };
});

const originalEnv = {
  agentOpsToken: process.env.AGENT_OPS_TOKEN,
  internalHmacSecret: process.env.INTERNAL_HMAC_SECRET,
  openModelApiBaseUrl: process.env.OPEN_MODEL_API_BASE_URL,
};

beforeEach(() => {
  process.env.AGENT_OPS_TOKEN = "ops-token";
  process.env.INTERNAL_HMAC_SECRET = "test-secret-with-at-least-32-bytes";
  process.env.OPEN_MODEL_API_BASE_URL = "http://backend.test";
  vi.mocked(auth).mockResolvedValue({
    user: {
      id: "user-id",
      email: "user@example.com",
    },
  });
  vi.mocked(getRateLimiter).mockReturnValue({
    check: vi.fn().mockResolvedValue({
      allowed: true,
      limit: 120,
      remaining: 119,
      reset: 1_767_225_660,
    }),
  });
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => Response.json({ ok: true })),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  restoreEnv();
});

function restoreEnv(): void {
  setEnv("AGENT_OPS_TOKEN", originalEnv.agentOpsToken);
  setEnv("INTERNAL_HMAC_SECRET", originalEnv.internalHmacSecret);
  setEnv("OPEN_MODEL_API_BASE_URL", originalEnv.openModelApiBaseUrl);
}

function setEnv(name: string, value: string | undefined): void {
  if (value === undefined) {
    delete process.env[name];
  } else {
    process.env[name] = value;
  }
}

function request(): NextRequest {
  return new NextRequest("http://localhost/api/backend/chat");
}

function context() {
  return {
    params: Promise.resolve({ path: ["chat"] }),
  };
}

test("forwards allowed requests with rate limit headers", async () => {
  const { GET } = await import("@/app/api/backend/[...path]/route");

  const response = await GET(request(), context());

  expect(response.status).toBe(200);
  expect(response.headers.get("X-RateLimit-Limit")).toBe("120");
  expect(response.headers.get("X-RateLimit-Remaining")).toBe("119");
  expect(response.headers.get("X-RateLimit-Reset")).toBe("1767225660");
  expect(fetch).toHaveBeenCalledWith(
    "http://backend.test/chat",
    expect.objectContaining({
      method: "GET",
      cache: "no-store",
    }),
  );
});

test("returns 429 with Retry-After and rate limit headers when blocked", async () => {
  vi.mocked(getRateLimiter).mockReturnValue({
    check: vi.fn().mockResolvedValue({
      allowed: false,
      limit: 2,
      remaining: 0,
      reset: 1_767_225_660,
      retryAfter: 30,
    }),
  });
  const { GET } = await import("@/app/api/backend/[...path]/route");

  const response = await GET(request(), context());

  expect(response.status).toBe(429);
  expect(response.headers.get("Retry-After")).toBe("30");
  expect(response.headers.get("X-RateLimit-Limit")).toBe("2");
  expect(response.headers.get("X-RateLimit-Remaining")).toBe("0");
  expect(fetch).not.toHaveBeenCalled();
});

test("fails open when the limiter throws", async () => {
  vi.spyOn(console, "error").mockImplementation(() => undefined);
  vi.mocked(getRateLimiter).mockReturnValue({
    check: vi.fn().mockRejectedValue(new Error("redis unavailable")),
  });
  const { GET } = await import("@/app/api/backend/[...path]/route");

  const response = await GET(request(), context());

  expect(response.status).toBe(200);
  expect(response.headers.get("X-RateLimit-Limit")).toBe("120");
  expect(fetch).toHaveBeenCalledTimes(1);
  expect(console.error).toHaveBeenCalledWith("Rate limiter failed open:", "redis unavailable");
});
