import { formatApiError, resolveApiBaseUrl, resolveApiBearerToken } from "@/lib/api";

const originalApiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL;
const originalApiBearerToken = process.env.NEXT_PUBLIC_API_BEARER_TOKEN;

afterEach(() => {
  if (originalApiBaseUrl === undefined) {
    delete process.env.NEXT_PUBLIC_API_BASE_URL;
  } else {
    process.env.NEXT_PUBLIC_API_BASE_URL = originalApiBaseUrl;
  }

  if (originalApiBearerToken === undefined) {
    delete process.env.NEXT_PUBLIC_API_BEARER_TOKEN;
  } else {
    process.env.NEXT_PUBLIC_API_BEARER_TOKEN = originalApiBearerToken;
  }
});

test("resolveApiBaseUrl defaults to the documented local FastAPI address", () => {
  delete process.env.NEXT_PUBLIC_API_BASE_URL;

  expect(resolveApiBaseUrl()).toBe("http://127.0.0.1:8000");
});

test("resolveApiBaseUrl trims a configured API base URL", () => {
  process.env.NEXT_PUBLIC_API_BASE_URL = "http://localhost:9000/";

  expect(resolveApiBaseUrl()).toBe("http://localhost:9000");
});

test("resolveApiBearerToken returns a trimmed configured token", () => {
  process.env.NEXT_PUBLIC_API_BEARER_TOKEN = " test-token ";

  expect(resolveApiBearerToken()).toBe("test-token");
});

test("formatApiError expands the browser network failure into an actionable message", () => {
  delete process.env.NEXT_PUBLIC_API_BASE_URL;

  expect(formatApiError(new Error("Failed to fetch"))).toContain(
    "Unable to connect to the chat API at http://127.0.0.1:8000.",
  );
});
