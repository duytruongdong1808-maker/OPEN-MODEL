import RedisMock from "ioredis-mock";

import {
  buildRateLimitKey,
  getRateLimiter,
  InMemoryRateLimiter,
  RedisRateLimiter,
  resetRateLimiterForTests,
  type RateLimitConfig,
} from "@/lib/rate-limit";

const originalEnv = {
  authRateLimitWindowMs: process.env.AUTH_RATE_LIMIT_WINDOW_MS,
  authRateLimitMaxRequests: process.env.AUTH_RATE_LIMIT_MAX_REQUESTS,
  internalHmacSecret: process.env.INTERNAL_HMAC_SECRET,
  redisUrl: process.env.REDIS_URL,
};

const testConfig: Required<RateLimitConfig> = {
  windowMs: 1_000,
  maxRequests: 2,
  keyPrefix: "test-rate-limit",
};

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date("2026-01-01T00:00:00.000Z"));
  process.env.INTERNAL_HMAC_SECRET = "test-secret-with-at-least-32-bytes";
  delete process.env.REDIS_URL;
  resetRateLimiterForTests();
});

afterEach(() => {
  vi.useRealTimers();
  restoreEnv();
  resetRateLimiterForTests();
});

function restoreEnv(): void {
  setEnv("AUTH_RATE_LIMIT_WINDOW_MS", originalEnv.authRateLimitWindowMs);
  setEnv("AUTH_RATE_LIMIT_MAX_REQUESTS", originalEnv.authRateLimitMaxRequests);
  setEnv("INTERNAL_HMAC_SECRET", originalEnv.internalHmacSecret);
  setEnv("REDIS_URL", originalEnv.redisUrl);
}

function setEnv(name: string, value: string | undefined): void {
  if (value === undefined) {
    delete process.env[name];
  } else {
    process.env[name] = value;
  }
}

test("in-memory limiter blocks after the configured request limit", async () => {
  const limiter = new InMemoryRateLimiter(testConfig);

  expect(await limiter.check("user-1")).toMatchObject({
    allowed: true,
    limit: 2,
    remaining: 1,
  });
  expect(await limiter.check("user-1")).toMatchObject({
    allowed: true,
    remaining: 0,
  });
  expect(await limiter.check("user-1")).toMatchObject({
    allowed: false,
    remaining: 0,
    retryAfter: 1,
  });
});

test("in-memory limiter resets after the configured window", async () => {
  const limiter = new InMemoryRateLimiter(testConfig);

  await limiter.check("user-1");
  await limiter.check("user-1");
  expect(await limiter.check("user-1")).toMatchObject({ allowed: false });

  vi.advanceTimersByTime(1_001);

  expect(await limiter.check("user-1")).toMatchObject({
    allowed: true,
    remaining: 1,
  });
});

test("Redis limiter increments a single expiring bucket with the Lua script", async () => {
  const redis = new RedisMock();
  const limiter = new RedisRateLimiter(
    redis as unknown as ConstructorParameters<typeof RedisRateLimiter>[0],
    testConfig,
  );

  expect(await limiter.check("user-1")).toMatchObject({
    allowed: true,
    remaining: 1,
  });
  expect(await limiter.check("user-1")).toMatchObject({
    allowed: true,
    remaining: 0,
  });
  expect(await limiter.check("user-1")).toMatchObject({
    allowed: false,
    remaining: 0,
    retryAfter: 1,
  });

  const key = buildRateLimitKey("user-1", testConfig.keyPrefix);
  expect(key).not.toContain("user-1");
  await expect(redis.get(key)).resolves.toBe("3");
  expect(await redis.pttl(key)).toBeGreaterThan(0);

  redis.disconnect();
});

test("factory falls back to in-memory limiter when REDIS_URL is unset", () => {
  delete process.env.REDIS_URL;

  expect(getRateLimiter()).toBeInstanceOf(InMemoryRateLimiter);
});
