# Cloud Run backend deployment

SquadMetric's launch backend runs as one request-billed Cloud Run service. The
local source upload deliberately includes the ignored `data/processed` and
`models` artifacts in the container image, while `.gcloudignore` excludes raw
history, snapshots, the frontend, tests, and development environments.

## Before deploying

1. Run the manual season refresh and validate `/api/readiness` locally.
2. Confirm `data/processed/current_artifact_manifest.json` exists.
3. Confirm the model metadata lists every officially finalized gameweek.
4. Authenticate the Google Cloud CLI and select the intended project.

## Deploy

From the repository root:

```powershell
gcloud run deploy squadmetric-api `
  --source . `
  --region europe-west1 `
  --allow-unauthenticated `
  --memory 1Gi `
  --cpu 1 `
  --min 0 `
  --max 1 `
  --concurrency 20 `
  --timeout 300 `
  --set-env-vars FPL_ACTIVE_SEASON=2026-27
```

Keep request-based billing and zero minimum instances. Set a Google Cloud budget
alert before sharing the public URL. The single-instance cap limits accidental
scale-out, but a budget alert is still required because it is not a hard cap.

## Verify

```powershell
$api = "https://YOUR-CLOUD-RUN-URL"
Invoke-RestMethod "$api/api/health"
Invoke-RestMethod "$api/api/readiness"
```

`/api/health` proves the process is running. Do not connect the frontend until
`/api/readiness` returns `ready: true` and contains no blockers.

Use the Cloud Run URL as Vercel's server-only `FPL_API_SERVER_URL`; it must never
be exposed through a `NEXT_PUBLIC_*` variable.
