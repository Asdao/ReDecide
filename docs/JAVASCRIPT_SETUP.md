# JavaScript dependency setup

RE:DECIDE has two JavaScript projects:

- `agent-harness/` — the model-facing coaching process
- `frontend/` — the Next.js browser application

Both projects use pnpm lockfiles. The repository does not contain
`package-lock.json` files, so use pnpm rather than `npm install`.

## Requirements

- Node.js 24.x
- pnpm 11.x
- WSL Ubuntu when working with the WSL Python environment

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

## Install from the lockfiles

From a WSL terminal at the repository root:

```bash
bash scripts/install-js-deps.sh
```

The script runs the equivalent of:

```bash
cd agent-harness
pnpm install --frozen-lockfile

cd ../frontend
pnpm install --frozen-lockfile
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

Then open a WSL terminal and run the JavaScript installation script there.
The JavaScript projects can remain under `/mnt/c/Users/...`; only the Python
virtual environment needs to live in the native WSL filesystem for reliable
interpreter discovery and faster indexing.

## Common problems

### `pnpm` or `node` is not found

Install or enable Node 24 and pnpm 11 in the environment where the script is
running. Windows PowerShell and WSL can have different PATHs; check versions
from the same WSL terminal that will run the script.

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

### Reinstalling from scratch

It is safe to remove generated `node_modules` directories and rerun the script:

```bash
rm -rf agent-harness/node_modules frontend/node_modules
bash scripts/install-js-deps.sh
```

Do not remove `pnpm-lock.yaml` files; they are the reproducibility contract.
