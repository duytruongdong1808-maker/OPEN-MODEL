import { createHmac } from "crypto";
import Redis, { type RedisOptions } from "ioredis";

const DEFAULT_RATE_LIMIT_WINDOW_MS = 60_000;
const DEFAULT_RATE_LIMIT_MAX_REQUESTS = 120;
const DEFAULT_RATE_LIMIT_KEY_PREFIX = "open-model:auth-rate-limit";

const RATE_LIMIT_SCRIPT = `
local count = redis.call("INCR", KEYS[1])
if count == 1 then
  redis.call("PEXPIRE", KEYS[1], ARGV[1])
  return {count, tonumber(ARGV[1])}
end

local ttl = redis.call("PTTL", KEYS[1])
if ttl < 0 then
  redis.call("PEXPIRE", KEYS[1], ARGV[1])
  ttl = tonumber(ARGV[1])
end
return {count, ttl}
`;

export type RateLimitConfig = {
  windowMs: number;
  maxRequests: number;
  keyPrefix?: string;
};

export type RateLimitResult = {
  allowed: boolean;
  limit: number;
  remaining: number;
  reset: number;
  retryAfter?: number;
};

export interface RateLimiter {
  check(userKey: string): Promise<RateLimitResult>;
}

type RateBucket = {
  windowStart: number;
  count: number;
};

type RedisLike = {
  eval(script: string, numberOfKeys: number, ...args: Array<string | number>): Promise<unknown>;
};

let rateLimiter: RateLimiter | null = null;

function resolvePositiveInteger(name: string, fallback: number): number {
  const rawValue = process.env[name]?.trim();
  if (!rawValue) return fallback;
  const value = Number.parseInt(rawValue, 10);
  return Number.isFinite(value) && value > 0 ? value : fallback;
}

function resolveInternalHmacSecret(): string {
  const secret = process.env.INTERNAL_HMAC_SECRET?.trim();
  if (!secret || Buffer.byteLength(secret, "utf8") < 32) {
    throw new Error("INTERNAL_HMAC_SECRET must be configured with at least 32 bytes.");
  }
  return secret;
}

export function resolveRateLimitConfig(): RateLimitConfig {
  return {
    windowMs: resolvePositiveInteger("AUTH_RATE_LIMIT_WINDOW_MS", DEFAULT_RATE_LIMIT_WINDOW_MS),
    maxRequests: resolvePositiveInteger(
      "AUTH_RATE_LIMIT_MAX_REQUESTS",
      DEFAULT_RATE_LIMIT_MAX_REQUESTS,
    ),
    keyPrefix: DEFAULT_RATE_LIMIT_KEY_PREFIX,
  };
}

export function buildRateLimitKey(userKey: string, keyPrefix = DEFAULT_RATE_LIMIT_KEY_PREFIX): string {
  const digest = createHmac("sha256", resolveInternalHmacSecret()).update(userKey).digest("hex");
  return `${keyPrefix}:${digest}`;
}

function buildResult(count: number, ttlMs: number, config: RateLimitConfig): RateLimitResult {
  const allowed = count <= config.maxRequests;
  const retryAfter = Math.max(1, Math.ceil(ttlMs / 1000));
  return {
    allowed,
    limit: config.maxRequests,
    remaining: Math.max(0, config.maxRequests - count),
    reset: Math.ceil((Date.now() + ttlMs) / 1000),
    retryAfter: allowed ? undefined : retryAfter,
  };
}

export function createPassThroughRateLimitResult(config = resolveRateLimitConfig()): RateLimitResult {
  return {
    allowed: true,
    limit: config.maxRequests,
    remaining: config.maxRequests,
    reset: Math.ceil((Date.now() + config.windowMs) / 1000),
  };
}

export function rateLimitHeaders(result: RateLimitResult): HeadersInit {
  const headers: Record<string, string> = {
    "X-RateLimit-Limit": String(result.limit),
    "X-RateLimit-Remaining": String(result.remaining),
    "X-RateLimit-Reset": String(result.reset),
  };
  if (result.retryAfter !== undefined) {
    headers["Retry-After"] = String(result.retryAfter);
  }
  return headers;
}

export class InMemoryRateLimiter implements RateLimiter {
  private readonly buckets = new Map<string, RateBucket>();
  private lastCleanup = 0;

  constructor(private readonly config = resolveRateLimitConfig()) {}

  async check(userKey: string): Promise<RateLimitResult> {
    const now = Date.now();
    this.cleanupExpiredBuckets(now);

    const key = buildRateLimitKey(userKey, this.config.keyPrefix);
    const current = this.buckets.get(key);
    const bucket =
      current && now - current.windowStart < this.config.windowMs
        ? current
        : { windowStart: now, count: 0 };

    bucket.count += 1;
    this.buckets.set(key, bucket);

    const ttlMs = Math.max(1, bucket.windowStart + this.config.windowMs - now);
    return buildResult(bucket.count, ttlMs, this.config);
  }

  private cleanupExpiredBuckets(now: number): void {
    if (now - this.lastCleanup < this.config.windowMs) return;
    this.lastCleanup = now;
    for (const [key, bucket] of this.buckets.entries()) {
      if (now - bucket.windowStart >= this.config.windowMs) {
        this.buckets.delete(key);
      }
    }
  }
}

export class RedisRateLimiter implements RateLimiter {
  private readonly client: RedisLike;
  private readonly config: RateLimitConfig;

  constructor(redisUrlOrClient: string | RedisLike, config = resolveRateLimitConfig()) {
    this.config = config;
    this.client =
      typeof redisUrlOrClient === "string"
        ? new Redis(redisUrlOrClient, redisOptions())
        : redisUrlOrClient;
  }

  async check(userKey: string): Promise<RateLimitResult> {
    const result = await this.client.eval(
      RATE_LIMIT_SCRIPT,
      1,
      buildRateLimitKey(userKey, this.config.keyPrefix),
      this.config.windowMs,
    );

    if (!Array.isArray(result) || result.length < 2) {
      throw new Error("Redis rate limiter returned an unexpected response.");
    }

    const count = Number(result[0]);
    const ttlMs = Number(result[1]);
    if (!Number.isFinite(count) || !Number.isFinite(ttlMs)) {
      throw new Error("Redis rate limiter returned non-numeric values.");
    }

    return buildResult(count, ttlMs, this.config);
  }
}

function redisOptions(): RedisOptions {
  return {
    connectTimeout: 5_000,
    commandTimeout: 5_000,
    enableOfflineQueue: false,
    maxRetriesPerRequest: 1,
    retryStrategy: (attempt) => Math.min(attempt * 100, 1_000),
  };
}

export function getRateLimiter(): RateLimiter {
  if (rateLimiter) return rateLimiter;

  const redisUrl = process.env.REDIS_URL?.trim();
  rateLimiter = redisUrl
    ? new RedisRateLimiter(redisUrl, resolveRateLimitConfig())
    : new InMemoryRateLimiter(resolveRateLimitConfig());
  return rateLimiter;
}

export function resetRateLimiterForTests(): void {
  rateLimiter = null;
}
