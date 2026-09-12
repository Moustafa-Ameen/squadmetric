# SquadMetric website deployment

The website is a Next.js Node server, not a static export. It relies on same-origin
`/api/*` rewrites to a separately running FastAPI service.

## Required production contract

1. Run the FastAPI service with the repository's Python environment and current,
   validated 2026/27 artifacts.
2. Set `FPL_API_SERVER_URL` to the server-side FastAPI origin. Never expose that
   value through `NEXT_PUBLIC_*`.
3. Create a Supabase project, apply the migration in `../supabase/migrations`, and
   configure email/password plus Google authentication. Set
   `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`, and the
   canonical `NEXT_PUBLIC_SITE_URL`. Set `SUPABASE_SERVICE_ROLE_KEY` only as a
   server-side secret; it is used by the authenticated account-deletion route and
   must never have a `NEXT_PUBLIC_` prefix.
4. Add the exact production `/auth/callback` URL to Supabase's redirect allow list,
   configure the Google provider's client credentials and callback, and configure
   production SMTP. Avoid broad production redirect wildcards.
5. Set a monitored `NEXT_PUBLIC_SUPPORT_EMAIL`, then verify the production
   contract, build, and start the website:

   ```powershell
   npm ci
   npm run verify:production
   npm run build
   npm run start:production -- --hostname 0.0.0.0 --port 3000
   ```

6. Put both services behind TLS and a reverse proxy. The browser should reach only
   the Next.js origin; Next.js proxies `/api/*` to FastAPI.
7. Use `/api/health` for liveness and `/api/readiness` for decision-serving
   readiness. A healthy process with stale or drifted artifacts is intentionally
   not recommendation-ready.
8. Run the 2026/27 refresh manually after an official gameweek is finalized and data-checked. The app deliberately does not update artifacts automatically and blocks recommendations when a finalized gameweek is missing.

## Vercel launch checklist

1. Import the GitHub repository into Vercel and set the Root Directory to `frontend`.
2. Add every variable from `.env.production.example` to the Production environment.
3. Deploy the separately hosted FastAPI service first, verify `/api/health` and
   `/api/readiness`, then use that origin as `FPL_API_SERVER_URL`.
4. Add the final Vercel or custom-domain origin to Supabase Auth URL configuration.
   Redeploy after any `NEXT_PUBLIC_*` change because those values are embedded at
   build time.
5. Test signup/confirmation, email and Google login, password reset, consent,
   onboarding, cross-device synchronization, export, and deletion in Production.

Do not deploy from a dirty working tree containing unrelated changes. Create a
reviewable release commit and apply the database migration first.

`next.config.ts` adds baseline security headers. The supported deployment path uses
the standard Next.js Node server (`next build` followed by `next start`), which
retains all framework features and the server-side API rewrite contract.

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
