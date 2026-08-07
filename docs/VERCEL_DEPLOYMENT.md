# Vercel deployment

The repository is configured as a Vercel Services project. The root
`vercel.json` defines a Next.js `frontend` service, a FastAPI `backend` service,
ordered `/api` rewrites, and a private service binding used for durable Blob
artifacts. Deploy from the repository root so Vercel reads that configuration.

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

Before deployment, run from `frontend/`:

```bash
pnpm install --frozen-lockfile
pnpm run typecheck
pnpm run lint
pnpm run build
```

The current frontend status records one known Vitest mismatch: the SSE adapter
test still expects the old absolute backend URL, while the implementation now
uses same-origin `/api` in a Vercel Services deployment. TypeScript, ESLint,
and the production build pass; update that test expectation before requiring a
fully green `pnpm run verify` gate.

## Environment variables

### Frontend service

For Vercel Services, leave `NEXT_PUBLIC_API_BASE_URL` unset so browser requests
use same-origin `/api` rewrites. Set:

```text
NEXT_PUBLIC_REPLAY_UPLOAD_MODE=blob
```

The Blob upload and cleanup routes are server-side Next.js routes. Their Blob
credentials must remain server-only; never put a Blob token or provider key in
a `NEXT_PUBLIC_*` variable. The Blob upload path accepts `.dem` files up to
1 GB, stores temporary objects under a randomized `uploads/` prefix, and
deletes the raw object after a validated successful import.

### Backend service

Configure the FastAPI service with:

```text
REDECIDE_STORAGE_BACKEND=blob
REDECIDE_BLOB_ACCESS=private
REDECIDE_API_ALLOWED_ORIGINS=https://<production-domain>,https://<preview-domain>
REDECIDE_BLOB_IMPORT_ENABLED=true
REDECIDE_BLOB_MAX_BYTES=1073741824
HARNESS_MODEL_BASE_URL=https://api.deepseek.com
HARNESS_MODEL_API_KEY=<server-side-secret>
```

`DEEPSEEK_API_KEY` may be used instead of `HARNESS_MODEL_API_KEY`. The root
`vercel.json` injects `REDECIDE_BLOB_SERVICE_URL` through the backend-to-
frontend service binding; do not copy that binding into local `.env` files.
The backend selects the Python HTTP coach when the provider base URL and key
are present. The legacy Pi subprocess is not needed for the normal deployment.

The public Blob import route accepts only HTTPS URLs on
`<store-id>.public.blob.vercel-storage.com`. It does not accept private Blob
URLs; private durable artifacts use the internal service binding instead.

## Routing

The root rewrites are ordered as follows:

```text
/api/blob/upload, /api/blob/cleanup -> Next.js frontend service
/api/*                              -> FastAPI backend service
/service-internal/*                 -> FastAPI backend service
/*                                  -> Next.js frontend service
```

The `/service-internal/blob-artifacts` route is not a browser API. FastAPI uses
it to request narrowly scoped, short-lived Blob URLs for durable artifacts.

## Deployment checklist

- [ ] Deploy from the repository root with the root `vercel.json`.
- [ ] Confirm Node 24 and pnpm 11 are selected for the frontend service.
- [ ] Run the frontend typecheck, lint, and production build locally.
- [ ] Set `NEXT_PUBLIC_REPLAY_UPLOAD_MODE=blob` only when public Blob upload is
      intentionally enabled.
- [ ] Set backend storage to Blob and verify the service binding is present.
- [ ] Configure provider credentials only in backend/server-side variables.
- [ ] Set `REDECIDE_API_ALLOWED_ORIGINS` to the exact deployed browser origins.
- [ ] Verify `GET /api/health` returns `{"status":"ok"}`.
- [ ] Exercise the sample flow, player selection, coaching, and replay viewer.
- [ ] Run one hosted Blob-backed analysis and confirm state restores after a
      second backend invocation.
- [ ] Add authentication or platform-level protection before exposing public
      upload routes to untrusted users.

## References

- [Current product state](CURRENT_STATE.md)
- [Backend API](../backend/app/API.md)
- [Frontend status](../frontend/STATUS.md)
- [Vercel Services configuration](../vercel.json)
- [Next.js deployment](https://nextjs.org/docs/app/getting-started/deploying)
- [Next.js environment variables](https://nextjs.org/docs/pages/guides/environment-variables)
