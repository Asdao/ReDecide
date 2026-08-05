# RE:DECIDE

Upload a Counter-Strike 2 `.dem` replay, choose a player, and receive coaching
for their post-contact decisions.

Maintenance documents:

- [Current product state](CURRENT_STATE.md)
- [Repository cleanup plan](CLEANUP_PLAN.md)
- [JavaScript dependency setup](JAVASCRIPT_SETUP.md)
- [Dependency security policy and checks](DEPENDENCY_SECURITY.md)
- [Replay maps and demo data](REPLAY_DATA_SETUP.md)
- [Vercel frontend deployment](VERCEL_DEPLOYMENT.md)

## First-time setup

You need Python 3.12+, `uv`, Node.js 24, and `pnpm` 11.

Run these commands from the repository root:

```powershell
uv sync --extra full

cd agent-harness
pnpm install --frozen-lockfile
cd ..

cd frontend
pnpm install --frozen-lockfile
cd ..

Copy-Item .env.example .env
Set-Content frontend/.env.local 'NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000'
```

From WSL, the same JavaScript setup can be run with the lockfile-preserving
helper:

```bash
bash scripts/install-js-deps.sh
```

Open `.env` and add your coaching API key:

```powershell
notepad .env
```

```text
DEEPSEEK_API_KEY=your-real-key-here
```

Never put the API key in `frontend/.env.local`.

## Start the product

Backend - run from the repository root:

```powershell
uv run uvicorn backend.app.main:app --reload --port 8000
```

Frontend - run in a second PowerShell window:

```powershell
cd frontend
pnpm dev
```

Open:

- Product: `http://localhost:3000`
- Backend API: `http://127.0.0.1:8000/docs`

Press `Ctrl+C` in both windows to stop.
