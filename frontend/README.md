# SquadMetric frontend

Next.js 16 and React 19 website for the SquadMetric recommendation platform.
It proxies same-origin `/api/*` requests to the FastAPI service.

## Local development

```powershell
npm.cmd ci
npm.cmd run dev
```

Open <http://localhost:3000>. FastAPI must be running at
`http://localhost:8000` unless `FPL_API_SERVER_URL` is overridden.

Authentication requires the public Supabase variables described in
[`../supabase/README.md`](../supabase/README.md). Never expose the service-role
key through a `NEXT_PUBLIC_*` variable.

## Quality gates

```powershell
npm.cmd run test:unit
npm.cmd run lint
npx.cmd tsc --noEmit
npm.cmd run build
npm.cmd run test:e2e
```

See [`DEPLOYMENT.md`](DEPLOYMENT.md) for the production contract.
