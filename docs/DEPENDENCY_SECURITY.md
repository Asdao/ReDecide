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
build approvals, the no-auto-install script policy, lockfile format, SHA-512
integrity values, and forbidden exotic sources.

## Safe install and audit

Use the checked-in lockfiles:

```powershell
pnpm -C agent-harness install --frozen-lockfile
pnpm -C frontend install --frozen-lockfile
pnpm -C agent-harness run security
pnpm -C frontend run security
```

The audit commands query the registry advisory database; they do not update
dependencies. `pnpm dev` does not install packages or perform an audit; it
fails with a stale-dependency error when `node_modules` needs an install.

When the pnpm store is already populated, `--offline` prevents missing package
tarballs from being downloaded:

```powershell
pnpm -C agent-harness install --frozen-lockfile --offline
pnpm -C frontend install --frozen-lockfile --offline
```

The release-age and trust-policy checks in pnpm 11.9 may still attempt registry
metadata queries. If zero outbound access is required, enforce it at the
operating-system or container boundary as well.

Never use `pnpm audit --fix`, `pnpm update`, or `pnpm add` as an unattended
security action. Review manifest and lockfile changes, audit results, package
provenance, and build-script approvals together.

Release-age or trust exceptions must be exact-version selectors and include a
review rationale in [`../security/README.md`](../security/README.md). Broad
package or scope exclusions are rejected by the repository checker.

Security overrides are likewise exact and enforced by the checker. They exist
only for current audited transitive fixes (`postcss`, `sharp`, and `undici`),
not as permission for unattended upgrades.

## CI gate

Every pull request and push to `main` runs the dependency-security workflow; it
can also be started manually. It uses frozen installs, runs the checker and
high-severity audit, then runs each project's tests, typecheck, and build
gates. The workflow has read-only content permissions, does not persist GitHub
credentials after checkout, and does not receive application credentials.
Concurrent runs for the same branch are cancelled to avoid wasting CI minutes.
