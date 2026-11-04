# Backend hosting

The FastAPI backend runs on DigitalOcean App Platform, behind Cloudflare. Autodeploy
is on, so it redeploys from `main` after a push, which took about 2 minutes on
2026-11-04. The source directory is the repository root, the port is 8080, and no
run command is set. The `Dockerfile` defaults to that port and starts `uvicorn`.

The app's name, ID and URL are kept in the DigitalOcean dashboard, not in this
repository.

The website runs on Vercel and proxies `/api/*` to the backend through
`FPL_API_SERVER_URL`. That value is server-only and must never be exposed through a
`NEXT_PUBLIC_*` variable.

## What a push deploys

The serving bundle in `data/processed` and `models` is committed, so a push to
`main` is all a new bundle needs. The `Data refresh` workflow makes that push when
a newly finalized Gameweek is published (see
[`docs/operations.md`](../operations.md)).

Before pushing a bundle by hand:

1. Confirm `data/processed/current_artifact_manifest.json` exists.
2. Confirm the model metadata lists every officially finalized Gameweek.
3. Validate `/api/readiness` locally.

## Verify

```powershell
$site = "https://YOUR-SITE-ORIGIN"
Invoke-RestMethod "$site/api/health"
Invoke-RestMethod "$site/api/readiness"
```

`/api/health` shows the process is running. Recommendations also need
`/api/readiness` to return `ready: true` with no blockers.

## Cloud Run

SquadMetric does not run on Cloud Run, and the Cloud Run API is disabled on its
Google Cloud projects. The earlier `gcloud run deploy` instructions are in the git
history of `docs/deployment/cloud-run.md`.
