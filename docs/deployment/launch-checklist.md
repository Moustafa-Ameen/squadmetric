# SquadMetric public-launch checklist

Use this list for the first guest-first release. Do not announce the site until the production smoke checks pass against the public URL.

## Release candidate verified locally

- Guest onboarding accepts a Team ID, official FPL URL, or squad screenshot.
- No login, OAuth provider, email service, database, or FPL password is required.
- Team link, preferences, drafts, watchlist, and decision history stay in browser storage and can be exported.
- The current model bundle covers finalized Gameweeks 1–5 and reports recommendation readiness as ready.
- The Linux backend image starts within a 1 GB memory limit and serves a real manager recommendation.
- Security headers, privacy terms, robots policy, sitemap, and a 1200×630 social preview are included.
- Python, unit, TypeScript, lint, production-build, desktop, mobile, and dependency-audit gates pass.

## Deployment day

1. Enable billing for the Google Cloud project, then deploy the FastAPI image with the commands in [cloud-run.md](cloud-run.md).
2. Confirm the public backend returns HTTP 200 from `/api/health` and `ready: true` from `/api/readiness`.
3. Import `frontend` into Vercel and configure:
   - `FPL_API_SERVER_URL` as the private server-side Cloud Run origin.
   - `NEXT_PUBLIC_SITE_URL` as the final HTTPS website origin.
   - `NEXT_PUBLIC_SUPPORT_EMAIL` as an inbox that is monitored.
4. Deploy the frontend and confirm the page source uses the public URL—not localhost—for `og:url`, `og:image`, and the sitemap.
5. Test the full flow in a private browser window and on a phone:
   - Team ID and an official URL containing `/en/` both connect.
   - Screenshot import can be reviewed before use.
   - Team grade, transfer explanation, Best XI, captaincy, player drawer, fixtures, and chips render.
   - Refreshing preserves browser data; disconnecting removes the linked team; export downloads valid JSON.
   - The stale-data state blocks recommendations clearly instead of serving old advice.
6. Open the public URL in LinkedIn Post Inspector so LinkedIn fetches the current title, description, and preview card.
7. Publish only after the final production smoke check has no console errors, broken requests, overflow, or inaccessible controls.

## Weekly operation

- After an official Gameweek is finalized and data-checked, run the manual season refresh.
- Verify `/api/readiness` before sharing or relying on new recommendations.
- Do not add an automatic refresh schedule unless the operating policy is deliberately changed.
- Capture deadline evidence before the deadline and settle it only after official finalization.

## Rollback rule

If the public frontend cannot reach a ready backend, or a new bundle fails readiness, do not leave recommendations partially available. Roll back to the last verified release or show the fail-closed freshness message until the issue is corrected.
