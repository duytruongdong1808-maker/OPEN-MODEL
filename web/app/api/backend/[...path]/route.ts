import { type NextRequest } from "next/server";

import { auth } from "@/auth";

const DEFAULT_BACKEND_URL = "http://127.0.0.1:8000";
const DEFAULT_RATE_LIMIT_WINDOW_MS = 60_000;
const DEFAULT_RATE_LIMIT_MAX_REQUESTS = 120;

type RateBucket = {
  windowStart: number;
  count: number;
};

const rateBuckets = new Map<string, RateBucket>();

type RouteContext = {
  params: Promise<{ path?: string[] }>;
};

function resolveBackendUrl(): string {
  return (process.env.OPEN_MODEL_API_BASE_URL?.trim() || DEFAULT_BACKEND_URL).replace(/\/$/, "");
}

function resolveOpsToken(): string | null {
  return process.env.AGENT_OPS_TOKEN?.trim() || null;
}

function resolvePositiveInteger(name: string, fallback: number): number {
  const rawValue = process.env[name]?.trim();
  if (!rawValue) return fallback;
  const value = Number.parseInt(rawValue, 10);
  return Number.isFinite(value) && value > 0 ? value : fallback;
}

function rateLimitResponse(userKey: string): Response | null {
  const windowMs = resolvePositiveInteger("AUTH_RATE_LIMIT_WINDOW_MS", DEFAULT_RATE_LIMIT_WINDOW_MS);
  const maxRequests = resolvePositiveInteger(
    "AUTH_RATE_LIMIT_MAX_REQUESTS",
    DEFAULT_RATE_LIMIT_MAX_REQUESTS,
  );
  const now = Date.now();
  const current = rateBuckets.get(userKey);
  const bucket =
    current && now - current.windowStart < windowMs
      ? current
      : { windowStart: now, count: 0 };

  bucket.count += 1;
  rateBuckets.set(userKey, bucket);

  if (bucket.count <= maxRequests) return null;

  const retryAfterSeconds = Math.max(1, Math.ceil((bucket.windowStart + windowMs - now) / 1000));
  return Response.json(
    { detail: "Rate limit exceeded." },
    {
      status: 429,
      headers: {
        "Retry-After": String(retryAfterSeconds),
      },
    },
  );
}

function buildBackendUrl(request: NextRequest, pathParts: string[] = []): string {
  const path = pathParts.map(encodeURIComponent).join("/");
  const url = new URL(`${resolveBackendUrl()}/${path}`);
  url.search = request.nextUrl.search;
  return url.toString();
}

function buildProxyHeaders(request: NextRequest): Headers {
  const headers = new Headers();
  const contentType = request.headers.get("content-type");
  const accept = request.headers.get("accept");
  const token = resolveOpsToken();

  if (contentType) headers.set("content-type", contentType);
  if (accept) headers.set("accept", accept);
  if (token) headers.set("authorization", `Bearer ${token}`);

  return headers;
}

async function getPathParts(context: RouteContext): Promise<string[]> {
  const params = await context.params;
  return params.path ?? [];
}

async function proxyRequest(request: NextRequest, context: RouteContext): Promise<Response> {
  const session = await auth();
  if (!session?.user) {
    return Response.json({ detail: "Authentication required." }, { status: 401 });
  }
  const userKey = session.user.email ?? session.user.name ?? "local-user";
  const limited = rateLimitResponse(userKey);
  if (limited) return limited;

  const method = request.method.toUpperCase();
  const hasBody = method !== "GET" && method !== "HEAD";
  const response = await fetch(buildBackendUrl(request, await getPathParts(context)), {
    method,
    headers: buildProxyHeaders(request),
    body: hasBody ? request.body : undefined,
    duplex: hasBody ? "half" : undefined,
    redirect: "manual",
    cache: "no-store",
  } as RequestInit & { duplex?: "half" });

  const headers = new Headers();
  const contentType = response.headers.get("content-type");
  const location = response.headers.get("location");
  if (contentType) headers.set("content-type", contentType);
  if (location) headers.set("location", location);
  headers.set("cache-control", "no-cache");

  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
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
