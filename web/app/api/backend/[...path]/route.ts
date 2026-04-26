import { createHmac } from "crypto";
import { type NextRequest } from "next/server";

import { auth } from "@/auth";
import {
  createPassThroughRateLimitResult,
  getRateLimiter,
  rateLimitHeaders,
  type RateLimitResult,
} from "@/lib/rate-limit";

export const runtime = "nodejs";

const DEFAULT_BACKEND_URL = "http://127.0.0.1:8000";

type RouteContext = {
  params: Promise<{ path?: string[] }>;
};

type SessionWithGoogle = {
  googleUserId?: string;
  googleEmail?: string;
  user?: {
    id?: string | null;
    email?: string | null;
    name?: string | null;
  };
};

function resolveBackendUrl(): string {
  return (process.env.OPEN_MODEL_API_BASE_URL?.trim() || DEFAULT_BACKEND_URL).replace(/\/$/, "");
}

function resolveOpsToken(): string | null {
  return process.env.AGENT_OPS_TOKEN?.trim() || null;
}

function resolveInternalHmacSecret(): string {
  const secret = process.env.INTERNAL_HMAC_SECRET?.trim();
  if (!secret || Buffer.byteLength(secret, "utf8") < 32) {
    throw new Error("INTERNAL_HMAC_SECRET must be configured with at least 32 bytes.");
  }
  return secret;
}

function signUserId(userId: string): string {
  return createHmac("sha256", resolveInternalHmacSecret()).update(userId).digest("hex");
}

function rateLimitResponse(rateLimit: RateLimitResult): Response {
  return Response.json(
    { detail: "Rate limit exceeded." },
    {
      status: 429,
      headers: rateLimitHeaders(rateLimit),
    },
  );
}

function withRateLimitHeaders(response: Response, rateLimit: RateLimitResult): Response {
  const headers = new Headers(response.headers);
  for (const [name, value] of Object.entries(rateLimitHeaders(rateLimit))) {
    headers.set(name, value);
  }

  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
}

function buildBackendUrl(request: NextRequest, pathParts: string[] = []): string {
  const path = pathParts.map(encodeURIComponent).join("/");
  const url = new URL(`${resolveBackendUrl()}/${path}`);
  url.search = request.nextUrl.search;
  return url.toString();
}

function buildProxyHeaders(request: NextRequest, session: SessionWithGoogle, userId: string): Headers {
  const headers = new Headers();
  const contentType = request.headers.get("content-type");
  const accept = request.headers.get("accept");
  const token = resolveOpsToken();

  if (contentType) headers.set("content-type", contentType);
  if (accept) headers.set("accept", accept);
  if (token) headers.set("authorization", `Bearer ${token}`);
  headers.set("x-user-id", userId);
  headers.set("x-user-id-sig", signUserId(userId));
  if (session.googleUserId) headers.set("x-open-model-google-user-id", session.googleUserId);
  if (session.googleEmail) headers.set("x-open-model-google-email", session.googleEmail);

  return headers;
}

function buildPublicProxyHeaders(request: NextRequest): Headers {
  const headers = new Headers();
  const accept = request.headers.get("accept");
  if (accept) headers.set("accept", accept);
  return headers;
}

async function getPathParts(context: RouteContext): Promise<string[]> {
  const params = await context.params;
  return params.path ?? [];
}

function isPublicBackendPath(pathParts: string[]): boolean {
  return pathParts.join("/") === "health/live";
}

async function forwardRequest(
  request: NextRequest,
  pathParts: string[],
  headers: Headers,
): Promise<Response> {
  const method = request.method.toUpperCase();
  const hasBody = method !== "GET" && method !== "HEAD";
  let response: globalThis.Response;
  try {
    response = await fetch(buildBackendUrl(request, pathParts), {
      method,
      headers,
      body: hasBody ? request.body : undefined,
      duplex: hasBody ? "half" : undefined,
      redirect: "manual",
      cache: "no-store",
    } as RequestInit & { duplex?: "half" });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown backend proxy error.";
    return Response.json(
      { detail: "Backend service is unavailable.", error: message },
      {
        status: 503,
        headers: {
          "cache-control": "no-cache",
        },
      },
    );
  }

  const responseHeaders = new Headers();
  const contentType = response.headers.get("content-type");
  const location = response.headers.get("location");
  if (contentType) responseHeaders.set("content-type", contentType);
  if (location) responseHeaders.set("location", location);
  responseHeaders.set("cache-control", "no-cache");

  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers: responseHeaders,
  });
}

async function proxyRequest(request: NextRequest, context: RouteContext): Promise<Response> {
  const pathParts = await getPathParts(context);
  if (isPublicBackendPath(pathParts)) {
    return forwardRequest(request, pathParts, buildPublicProxyHeaders(request));
  }

  const passThroughRateLimit = createPassThroughRateLimitResult();
  const session = await auth();
  if (!session?.user) {
    return Response.json(
      { detail: "Authentication required." },
      { status: 401, headers: rateLimitHeaders(passThroughRateLimit) },
    );
  }
  const sessionWithGoogle = session as typeof session & SessionWithGoogle;
  const userId = sessionWithGoogle.user?.id?.trim();
  if (!userId) {
    return Response.json(
      { detail: "Authenticated session is missing a user id." },
      { status: 401, headers: rateLimitHeaders(passThroughRateLimit) },
    );
  }
  const userKey = sessionWithGoogle.googleUserId ?? session.user.email ?? session.user.name ?? "local-user";
  let rateLimit: RateLimitResult;
  try {
    rateLimit = await getRateLimiter().check(userKey);
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown Redis rate limiter error.";
    console.error("Rate limiter failed open:", message);
    rateLimit = passThroughRateLimit;
  }
  if (!rateLimit.allowed) return rateLimitResponse(rateLimit);

  const response = await forwardRequest(request, pathParts, buildProxyHeaders(request, sessionWithGoogle, userId));
  return withRateLimitHeaders(response, rateLimit);
}

export async function GET(request: NextRequest, context: RouteContext): Promise<Response> {
  return proxyRequest(request, context);
}

export async function POST(request: NextRequest, context: RouteContext): Promise<Response> {
  return proxyRequest(request, context);
}

export async function DELETE(request: NextRequest, context: RouteContext): Promise<Response> {
  return proxyRequest(request, context);
}
