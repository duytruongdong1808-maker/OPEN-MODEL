# Playwright E2E

Run locally with the backend stack in one terminal:

```sh
docker compose up -d backend redis postgres
cd web
npm run dev
```

Then run the browser tests from `web/` in another terminal:

```sh
npm run e2e:ui
```

Required environment includes `AUTH_USERNAME`, `AUTH_PASSWORD`, `AUTH_SECRET`, `INTERNAL_HMAC_SECRET`, `AGENT_OPS_TOKEN`, `REDIS_URL`, and the backend settings needed by your local compose stack.

The chat tests mock only `/api/backend/conversations/*/messages/stream`. Playwright `route.fulfill()` returns one completed response, not a progressive stream, so tests assert the submitted request body and final rendered state instead of intermediate token timing.

When adding tests, prefer role-based selectors such as `getByRole` and `getByLabel`. Use `data-testid` for ambiguous chat surfaces only, and never couple tests to CSS classes.

Debug failures with:

```sh
npm run e2e:report
npx playwright show-trace test-results/path-to-trace.zip
```

Known limitation: auth is single-user today, so multi-user isolation tests are deferred to P3.
