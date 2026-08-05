# Dependency security

The repository's JavaScript projects use pnpm lockfiles and share the
dependency-security policy documented in [`../security/README.md`](../security/README.md).
There is no scheduled dependency bot; updates are manual and are verified by
CI in [`.github/workflows/dependency-security.yml`](../.github/workflows/dependency-security.yml).

## Before installing

From the repository root, run the dependency-free policy and lockfile check:

```powershell
node security/check-lockfiles.mjs
```

This checks the pinned pnpm version, release-age and trust settings, explicit
build approvals, lockfile format, SHA-512 integrity values, and forbidden
exotic sources.

## Safe install and audit

Use the checked-in lockfiles:

```powershell
pnpm -C agent-harness install --frozen-lockfile
pnpm -C frontend install --frozen-lockfile
pnpm -C agent-harness run security
pnpm -C frontend run security
```

The audit commands query the registry advisory database; they do not update
dependencies. `pnpm dev` does not install packages or perform an audit.

When the pnpm store is already populated, use `--offline` to prevent registry
access entirely:

```powershell
pnpm -C agent-harness install --frozen-lockfile --offline
pnpm -C frontend install --frozen-lockfile --offline
```

Never use `pnpm audit --fix`, `pnpm update`, or `pnpm add` as an unattended
security action. Review manifest and lockfile changes, audit results, package
provenance, and build-script approvals together.

## CI gate

Pull requests that change either JavaScript manifest, lockfile, workspace
policy, or the security checker run the dependency-security workflow. It uses
frozen installs, runs the checker and high-severity audit, then runs each
project's tests, typecheck, and build gates. The workflow has read-only content
permissions and does not receive application credentials.
