# JavaScript dependency setup

RE:DECIDE has two JavaScript projects:

- `agent-harness/` — the model-facing coaching process
- `frontend/` — the Next.js browser application

Both projects use pnpm lockfiles as their authoritative dependency graph. Use
pnpm rather than `npm install`; legacy npm lockfiles are not the supported local
installation path.

## Requirements

- Node.js 24.x
- pnpm 11.x
- Windows PowerShell for the checkout under `C:\Users\...`

The frontend declares these requirements in `frontend/package.json`. The
agent harness accepts Node 20+, but the combined setup uses Node 24 because the
frontend is part of the same development workflow.

Check the active tools:

```bash
node --version
pnpm --version
```

If the versions are wrong, fix the Node/pnpm installation before installing
dependencies. On systems using Volta, make sure the Volta directory is
writable and that the WSL terminal is using the intended Node installation.

## Install from the lockfiles on Windows

From Windows PowerShell at the repository root:

```powershell
.\scripts\install-js-deps.ps1
```

The script validates Node, pnpm, and lockfile policy, then runs:

```powershell
cd frontend
pnpm install --frozen-lockfile
```

The legacy Pi coach is optional. Install its dependencies only when needed:

```powershell
.\scripts\install-js-deps.ps1 -IncludeAgentHarness
```

`--frozen-lockfile` ensures that dependency installation follows the checked-in
lockfile and fails instead of silently rewriting it.

## Verify each project

Agent harness:

```bash
cd agent-harness
pnpm test
pnpm typecheck
pnpm build
```

Frontend:

```bash
cd frontend
pnpm test
pnpm typecheck
pnpm lint
pnpm build
```

The frontend also provides a combined command:

```bash
pnpm verify
```

## Security checks

Before a local install, run the repository-level policy and lockfile check:

```bash
node security/check-lockfiles.mjs
```

After installing, run the advisory audit in each project:

```bash
cd agent-harness
pnpm run security

cd ../frontend
pnpm run security
```

The security command does not update dependencies. It validates the checked-in
policy and lockfile, then queries the registry for high-severity advisories.
See [`DEPENDENCY_SECURITY.md`](DEPENDENCY_SECURITY.md) for the offline-install
and CI workflow.

## PyCharm and WSL

PyCharm’s WSL Python interpreter and the JavaScript package manager are
separate settings. Selecting the WSL Python interpreter does not install Node
dependencies automatically.

Use a WSL interpreter such as:

```text
/home/numnum/.virtualenvs/GHackathon1/bin/python
```

Keep the WSL interpreter for Python, but run the frontend's Node and pnpm
commands from Windows PowerShell. Do not share the Windows checkout's
`node_modules` with WSL through `/mnt/c/Users/...`; that mixes Windows and Linux
native binaries and pnpm metadata.

If Linux JavaScript execution is required, create a separate clone under a
native path such as `~/src/GHackathon`, then run `bash scripts/install-js-deps.sh`
inside that clone. The Bash helper refuses Windows-mounted `/mnt/<drive>` paths.

## Common problems

### `pnpm` or `node` is not found

Install or enable Node 24 and pnpm 11 in Windows PowerShell. Windows and WSL
have separate PATHs and separate native dependency trees.

### Volta cannot create its directory

This is a permissions or PATH problem in the Volta installation. Fix Volta or
use a Node installation available inside WSL. The setup script intentionally
stops when it cannot verify Node 24 rather than installing packages with an
unknown runtime.

### Lockfile mismatch

Do not switch to `npm install` to work around this. First confirm that the
correct project directory and pnpm major version are being used. Only update a
lockfile deliberately, review the diff, and commit the updated lockfile with
the corresponding `package.json` change.

### Reinstalling the Windows frontend from scratch

If the environment doctor reports Linux packages in the Windows tree, move the
generated directory aside and reinstall from PowerShell. Keep backups outside
`frontend/` so Tailwind never scans diagnostic artifacts:

```powershell
cd C:\Users\n8469\PycharmProjects\GHackathon
Move-Item frontend\node_modules "$env:TEMP\GHackathon-frontend-node_modules-backup"
.\scripts\install-js-deps.ps1
```

Do not remove `pnpm-lock.yaml` files; they are the reproducibility contract.

Before starting the frontend, you can run the same checks directly:

```powershell
cd frontend
pnpm doctor
pnpm dev
```
