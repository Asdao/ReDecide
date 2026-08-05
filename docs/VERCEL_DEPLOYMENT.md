# Vercel deployment

This guide deploys the Next.js frontend to Vercel. The FastAPI service is a
separate deployment; Vercel does not run `backend/app/main.py` for this
repository.

## Current readiness

The frontend is a deployable fixture-first slice. The landing route can be
built and served without a backend, but the upload, preparation, player
selection, and coaching screens are not connected to the API yet. Deploying
the frontend therefore publishes the current product shell; it does not make
the complete replay-to-coaching flow live.

## Vercel project settings

Create a Vercel project from this repository and use these settings:

| Setting | Value |
| --- | --- |
| Root Directory | `frontend` |
| Framework preset | Next.js |
| Install command | `pnpm install --frozen-lockfile` |
| Build command | `pnpm build` |
| Output directory | Leave blank (Vercel manages Next.js output) |
| Node.js version | `24.x` |
| Package manager | pnpm 11 (declared by `package.json`) |

**Deployment note:** Vercel must run the frontend package’s `build` script
(`pnpm build`, equivalent to `npm run build`). Keep this script in
`frontend/package.json` and verify it locally before deploying; do not replace
it with a hard-coded command that bypasses the project script.

The `frontend/pnpm-lock.yaml`, `frontend/package.json`, and `frontend/.nvmrc`
must remain in the selected root directory. Do not run `npm install` for this
project: it creates a second lockfile and can resolve a different dependency
tree.

Before creating a production deployment, run the same checks locally:

```bash
cd frontend
pnpm install --frozen-lockfile
pnpm run verify
```

`pnpm run verify` runs the frontend tests, TypeScript check, ESLint, and a
production Next.js build.

## Environment variables

### Frontend

`NEXT_PUBLIC_API_BASE_URL` is documented in the repository environment
template, but the current fixture-first frontend does not read it yet. Setting
it in Vercel is harmless, but it will not connect the browser to the backend
until the API adapter is implemented.

When that integration is ready, add this variable in Vercel for the relevant
environments:

```text
NEXT_PUBLIC_API_BASE_URL=https://api.example.com
```

Set it before the deployment build. `NEXT_PUBLIC_*` values are embedded into
the browser bundle during the Next.js build, so changing the value requires a
new deployment.

Never put `DEEPSEEK_API_KEY`, `HARNESS_MODEL_API_KEY`, or another provider
credential in a `NEXT_PUBLIC_*` variable.

### Backend

Deploy the FastAPI application separately using the platform and process
manager appropriate for the target host. Its production command is equivalent
to:

```bash
uv run uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT:-8000}
```

Configure the backend with the deployed frontend origin, including the scheme
and no trailing path:

```text
REDECIDE_API_ALLOWED_ORIGINS=https://redecide.example.com,https://redecide-<team>.vercel.app
```

If the standalone replay API is deployed independently, set its corresponding
`REPLAY_API_ALLOWED_ORIGINS` value as well. Restart the backend after changing
environment variables.

Check the deployed service before wiring it to the frontend:

```bash
curl https://api.example.com/api/health
```

Expected response:

```json
{"status":"ok"}
```

## Optional Vercel Blob import

The backend has a disabled-by-default `POST /api/replay/import-url` route for
public Vercel Blob URLs. Enable it only when the frontend upload flow and the
storage policy are ready:

```text
REDECIDE_BLOB_IMPORT_ENABLED=true
REDECIDE_BLOB_MAX_BYTES=1073741824
```

The route accepts only public `https://<store-id>.public.blob.vercel-storage.com/...`
URLs. It does not make private Blob objects or direct browser uploads work by
itself.

## Deployment checklist

- [ ] Vercel root directory is `frontend`.
- [ ] Vercel uses Node 24 and pnpm 11.
- [ ] `pnpm install --frozen-lockfile` succeeds.
- [ ] `pnpm run verify` passes locally.
- [ ] A separately deployed backend responds to `/api/health`.
- [ ] Backend CORS includes the exact Vercel production origin.
- [ ] `NEXT_PUBLIC_API_BASE_URL` is set only after the frontend API adapter is
      implemented.
- [ ] Provider credentials exist only in backend/server-side environment
      variables.
- [ ] Blob import remains disabled unless its security and upload flow have
      been reviewed.

## References

- [Next.js deployment](https://nextjs.org/docs/app/getting-started/deploying)
- [Next.js environment variables](https://nextjs.org/docs/pages/guides/environment-variables)
- [Repository API notes](../backend/app/API.md)
- [Current frontend status](FRONTEND_STATUS.md)
