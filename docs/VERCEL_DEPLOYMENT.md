# Vercel deployment

The repository is configured as a Vercel Services project. The root
`vercel.json` defines a Next.js `frontend` service, a FastAPI `backend` service,
ordered `/api` rewrites, and a private service binding used for durable Blob
artifacts. Deploy from the repository root so Vercel reads that configuration.
The Vercel project itself must also have its framework setting set to
**Services**.

## Current readiness

The frontend upload, sample, player-selection, coaching, result-recovery, and
replay-viewer flows are implemented. The bundled processed-replay catalog can
be demonstrated without a live provider. A hosted deployment still needs a
provider key, Blob configuration, and a real end-to-end smoke test before it
should be treated as production-ready.

## Build and verification

The frontend service uses Node 24 and pnpm 11:

| Setting | Value |
| --- | --- |
| Service root | `frontend/` (declared by root `vercel.json`) |
| Framework | Next.js |
| Install command | `pnpm install --frozen-lockfile` |
| Build command | `pnpm build` |
| Node.js version | `24.x` |
| Package manager | pnpm 11 |

The backend service applies `maxDuration: 300` to `**/*.py`. This gives replay
import/parsing and the documented coaching wait a bounded five-minute window
when the selected Vercel plan supports it. Vercel still enforces the plan's
maximum, so confirm the effective value in the deployed Function settings and
runtime logs.

Before deployment, run from `frontend/`:

```bash
pnpm install --frozen-lockfile
pnpm run typecheck
pnpm run lint
pnpm run build
```

The latest local `pnpm run verify` gate passes: 138 Vitest tests, TypeScript,
ESLint, and the Next.js 16.2.12 production build.

## Environment variables

### Frontend service

For Vercel Services, leave `NEXT_PUBLIC_API_BASE_URL` unset so browser requests
use same-origin `/api` rewrites. Set:

```text
NEXT_PUBLIC_REPLAY_UPLOAD_MODE=blob
```

The Blob upload, cleanup, and retention routes are server-side Next.js routes. Their Blob
credentials must remain server-only; never put a Blob token or provider key in
a `NEXT_PUBLIC_*` variable. The Blob upload path accepts `.dem` files up to
1 GB, stores temporary objects under a randomized `uploads/` prefix, and
deletes the raw object after a validated successful import.

Do not use direct multipart upload for a typical replay on Vercel. Vercel
Functions currently limit request and response bodies to 4.5 MB, so production
replays must upload directly to Blob and then use the disabled-by-default
import route. The 1 GB application limit does not override platform, plan,
execution-duration, storage, or bandwidth limits.

Set a long random `CRON_SECRET` for the server-side retention job. Vercel Cron
sends it as `Authorization: Bearer <secret>`; the route fails closed if the
secret is missing. The default daily policy is 1 day for failed analysis jobs,
14 days for other analysis jobs, and 30 days for non-sample replay artifacts.
Pinned hosted samples are retained. To inspect the job safely on its first
deployment, temporarily set `REDECIDE_RETENTION_DRY_RUN=true`, invoke the route
with the secret, inspect the returned counts, then restore it to `false`.

### Backend service

Configure the FastAPI service with:

```text
REDECIDE_BLOB_ACCESS=private
REDECIDE_API_ALLOWED_ORIGINS=https://<production-domain>,https://<preview-domain>
REDECIDE_BLOB_IMPORT_ENABLED=true
REDECIDE_BLOB_MAX_BYTES=1073741824
REDECIDE_SAMPLE_CACHE_VERSION=ancient-full-v2
HARNESS_MODEL_BASE_URL=https://api.deepseek.com
HARNESS_MODEL_API_KEY=<server-side-secret>
```

`DEEPSEEK_API_KEY` may be used instead of `HARNESS_MODEL_API_KEY`. The root
`vercel.json` injects `REDECIDE_BLOB_SERVICE_URL` through the backend-to-
frontend service binding, which automatically enables durable Blob storage;
do not copy that binding into local `.env` files. Set
`REDECIDE_STORAGE_BACKEND=filesystem` only when intentionally opting out.
The backend selects the Python HTTP coach when the provider base URL and key
are present. The legacy Pi subprocess is not needed for the normal deployment.

The public Blob import route accepts only HTTPS URLs on
`<store-id>.public.blob.vercel-storage.com`. It does not accept private Blob
URLs; private durable artifacts use the internal service binding instead.

## Routing

The root rewrites are ordered as follows:

```text
/api/blob/upload, /api/blob/cleanup,
/api/cron/blob-retention             -> Next.js frontend service
/api/*                               -> FastAPI backend service
/service-internal/*                  -> FastAPI backend service
/*                                   -> Next.js frontend service
```

The `/service-internal/blob-artifacts` route is not a browser API. FastAPI uses
it to request narrowly scoped, short-lived Blob URLs for durable artifacts.

## Deployment checklist

- [ ] Deploy from the repository root with the root `vercel.json`.
- [ ] Set the Vercel project framework to **Services**.
- [ ] Confirm Node 24 and pnpm 11 are selected for the frontend service.
- [ ] Confirm the backend Python functions show a 300-second maximum duration.
- [ ] Run the frontend typecheck, lint, and production build locally.
- [ ] Set `NEXT_PUBLIC_REPLAY_UPLOAD_MODE=blob` only when public Blob upload is
      intentionally enabled.
- [ ] Set backend storage to Blob and verify the service binding is present.
- [ ] Configure provider credentials only in backend/server-side variables.
- [ ] Set `CRON_SECRET`, run retention once in dry-run mode, and confirm the
      daily Cron appears in the Vercel deployment.
- [ ] Set `REDECIDE_API_ALLOWED_ORIGINS` to the exact deployed browser origins.
- [ ] Verify `GET /api/health` returns `{"status":"ok"}`.
- [ ] Exercise the sample flow, player selection, coaching, and replay viewer.
- [ ] Run one hosted Blob-backed analysis and confirm state restores after a
      second backend invocation.
- [ ] Add authentication or platform-level protection before exposing public
      upload routes to untrusted users.

The configuration was checked against Vercel's live `vercel.json` schema and
current Services documentation on 2026-08-07. This verifies the configuration
shape, not a deployment: environment bindings, Blob access, provider calls,
function duration, and the hosted end-to-end flow still require dashboard and
runtime smoke tests.

## References

- [Current product state](CURRENT_STATE.md)
- [Backend API](../backend/app/API.md)
- [Frontend status](../frontend/STATUS.md)
- [Vercel Services configuration](../vercel.json)
- [Vercel Services documentation](https://vercel.com/docs/services)
- [Vercel Functions limits](https://vercel.com/docs/functions/limitations)
- [Next.js deployment](https://nextjs.org/docs/app/getting-started/deploying)
- [Next.js environment variables](https://nextjs.org/docs/pages/guides/environment-variables)
