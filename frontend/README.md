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

The launch experience is guest-first. Team links, drafts, watchlists, and
preferences are stored in the visitor's browser; no account provider is required.

## Quality gates

```powershell
npm.cmd run test:unit
npm.cmd run lint
npx.cmd tsc --noEmit
npm.cmd run build
npm.cmd run test:e2e
```

See [`DEPLOYMENT.md`](DEPLOYMENT.md) for the production contract.
