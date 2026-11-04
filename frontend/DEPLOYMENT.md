# SquadMetric website deployment

For the end-to-end first-release sequence, use the [public-launch checklist](../docs/deployment/launch-checklist.md).

The website is a Next.js server app, not a static export, and runs on Vercel. It
relies on same-origin `/api/*` rewrites to a separately hosted FastAPI service. For
how that service is hosted, see
[`../docs/deployment/backend.md`](../docs/deployment/backend.md).

## Required production contract

1. Run the FastAPI service with the repository's Python environment and current,
   validated 2026/27 artifacts.
2. Set `FPL_API_SERVER_URL` to the server-side FastAPI origin. Never expose that
   value through `NEXT_PUBLIC_*`.
3. Set the canonical `NEXT_PUBLIC_SITE_URL`. The launch experience is guest-first:
   team links, preferences, drafts, watchlists, and history are stored in the
   visitor's browser. No identity provider or OAuth credentials are required.
4. Set a monitored `NEXT_PUBLIC_SUPPORT_EMAIL`. Vercel builds and runs the website.
   To verify the production contract, build, and start it outside Vercel:

   ```powershell
   npm ci
   npm run verify:production
   npm run build
   npm run start:production -- --hostname 0.0.0.0 --port 3000
   ```

5. Serve both services over TLS. The browser should reach only the Next.js origin;
   Next.js proxies `/api/*` to FastAPI.
6. Use `/api/health` for liveness and `/api/readiness` for decision-serving
   readiness. A healthy process with stale or drifted artifacts is intentionally
   not recommendation-ready.
7. The `Data refresh` GitHub workflow refreshes the 2026/27 artifacts on GitHub's servers twice a day and pushes them only after an official gameweek is finalized, data-checked, and the full test suite passes (see `docs/operations.md`). It keeps serving with a "projections use results through GWx" label while the model trails by at most two finalized gameweeks, and blocks recommendations beyond that.

## Vercel launch checklist

1. Import the GitHub repository into Vercel and set the Root Directory to `frontend`.
2. Add every variable from `.env.production.example` to the Production environment.
3. Deploy the separately hosted FastAPI service first, verify `/api/health` and
   `/api/readiness`, then use that origin as `FPL_API_SERVER_URL`.
4. Redeploy after any `NEXT_PUBLIC_*` change because those values are embedded at
   build time.
5. Test Team ID and URL linking, guest-demo entry, local persistence, browser-data
   export, team disconnection, and the complete recommendation flow in Production.

Do not deploy from a dirty working tree containing unrelated changes. Create a
reviewable release commit first.

`next.config.ts` adds baseline security headers and the server-side API rewrite.
Outside Vercel, the website runs with `next build` followed by `next start`.

## Release gate

Run before deployment:

```powershell
npm run test:unit
npm run lint
npm run build
npm run test:e2e
```

The E2E suite runs desktop and mobile Chromium, mocks only official/API boundaries,
checks critical draft/deadline/review flows, verifies security headers, and fails on
serious WCAG A/AA violations.
