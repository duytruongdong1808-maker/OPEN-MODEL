import { type NextRequest } from "next/server";

const DEFAULT_BACKEND_URL = "http://127.0.0.1:8000";

type RouteContext = {
  params: Promise<{ path?: string[] }>;
};

function resolveBackendUrl(): string {
  return (process.env.OPEN_MODEL_API_BASE_URL?.trim() || DEFAULT_BACKEND_URL).replace(/\/$/, "");
}

function resolveOpsToken(): string | null {
  return process.env.AGENT_OPS_TOKEN?.trim() || null;
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
  const method = request.method.toUpperCase();
  const hasBody = method !== "GET" && method !== "HEAD";
  const response = await fetch(buildBackendUrl(request, await getPathParts(context)), {
    method,
    headers: buildProxyHeaders(request),
    body: hasBody ? request.body : undefined,
    duplex: hasBody ? "half" : undefined,
    cache: "no-store",
  } as RequestInit & { duplex?: "half" });

  const headers = new Headers();
  const contentType = response.headers.get("content-type");
  if (contentType) headers.set("content-type", contentType);
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
