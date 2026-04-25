import { formatApiError, resolveApiBaseUrl } from "@/lib/api";

const originalApiBaseUrl = process.env.NEXT_PUBLIC_API_PROXY_BASE_URL;

afterEach(() => {
  if (originalApiBaseUrl === undefined) {
    delete process.env.NEXT_PUBLIC_API_PROXY_BASE_URL;
  } else {
    process.env.NEXT_PUBLIC_API_PROXY_BASE_URL = originalApiBaseUrl;
  }
});

test("resolveApiBaseUrl defaults to the internal Next.js API proxy", () => {
  delete process.env.NEXT_PUBLIC_API_PROXY_BASE_URL;

  expect(resolveApiBaseUrl()).toBe("/api/backend");
});

test("resolveApiBaseUrl trims a configured proxy base URL", () => {
  process.env.NEXT_PUBLIC_API_PROXY_BASE_URL = "/custom-api/";

  expect(resolveApiBaseUrl()).toBe("/custom-api");
});

test("formatApiError expands the browser network failure into an actionable message", () => {
  delete process.env.NEXT_PUBLIC_API_PROXY_BASE_URL;

  expect(formatApiError(new Error("Failed to fetch"))).toContain(
    "Unable to connect to the chat API through /api/backend.",
  );
});
