# RE:DECIDE

Upload a Counter-Strike 2 `.dem` replay, choose a player, and receive coaching
for their post-contact decisions.

Maintenance documents:

- [Current product state](CURRENT_STATE.md)
- [JavaScript dependency setup](JAVASCRIPT_SETUP.md)
- [Dependency security policy and checks](DEPENDENCY_SECURITY.md)
- [Replay maps and demo data](REPLAY_DATA_SETUP.md)
- [Vercel frontend deployment](VERCEL_DEPLOYMENT.md)
- [Backend API](../backend/app/API.md)
- [Frontend implementation status](../frontend/STATUS.md)
- [Legacy Pi/agent harness setup](../agent-harness/docs/GETTING_STARTED.md)

## First-time setup

You need Python 3.12+, `uv`, Node.js 24, and `pnpm` 11 for the frontend.
Installing the separate `agent-harness` dependencies is optional unless you
explicitly use the legacy Pi coach (`REDECIDE_COACH_MODE=pi`).

Run these commands from the repository root:

```powershell
uv sync --extra full

cd frontend
pnpm install --frozen-lockfile
cd ..

Copy-Item .env.example .env
Set-Content frontend/.env.local 'NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000'
# Optional: set NEXT_PUBLIC_REPLAY_UPLOAD_MODE=blob only when public Vercel
# Blob upload and the backend import route are configured.
```

For this Windows checkout, the lockfile-preserving setup helper is:

```powershell
.\scripts\install-js-deps.ps1
```

Do not run `pnpm install` or `pnpm dev` from WSL against this same `/mnt/c/...`
checkout. Windows and Linux native packages cannot safely share one
`node_modules` tree. Use PowerShell here; use WSL for Python, or create a
separate clone under the native WSL filesystem for Linux JavaScript work.

Open `.env` and add your coaching API key:

```powershell
notepad .env
```

```text
DEEPSEEK_API_KEY=your-real-key-here
```

Never put the API key in `frontend/.env.local`.

## Start the product

From the repository root, the Windows launcher installs missing locked
dependencies, creates local environment files when absent, reuses healthy
services already on ports 8000 and 3000, and starts whichever service is
missing:

```powershell
.\scripts\start-dev.ps1
```

Pass `-SkipSetup` when the locked Python and frontend dependencies are already
installed. The launcher refuses to replace an unrelated process occupying
either port.

Backend - run from the repository root:

```powershell
uv run uvicorn backend.app.main:app --env-file .env --reload --port 8000
```

Frontend - run in a second PowerShell window:

```powershell
cd frontend
pnpm dev
```

The frontend runs an environment check before install and development. It
requires Node 24, pnpm 11, the correct Windows native packages, and refuses the
unsafe WSL-on-`/mnt/c` combination with a recovery message. The default local
upload mode is direct multipart upload; Vercel uses the optional Blob mode.

Open:

- Product: `http://localhost:3000`
- Backend API: `http://127.0.0.1:8000/docs`

Press `Ctrl+C` in both windows to stop.

When the provider base URL and key are configured, the backend selects the
Python HTTP coach automatically. To use the legacy Pi/Node path instead, set
`REDECIDE_COACH_MODE=pi` in `.env` and install the optional `agent-harness`
dependencies with `pnpm install --frozen-lockfile` from that directory.

For a quick browser demo without uploading a native replay, use `Use a sample
match` or `Open processed replays` from the landing page. The sample path calls
the backend catalog and enters the same player-selection, coaching, and replay
viewer flow as a native upload.

For backend tests from WSL, use the Linux virtual environment so native replay
and HTTP dependencies match the runtime:

```bash
source .venv-wsl/bin/activate
pytest backend/tests/test_coach_mode.py -q
```
