# Dependency security

This repository treats dependency installation as a security-sensitive operation.
The `frontend` and `agent-harness` projects each have a committed
`pnpm-lock.yaml`, explicit build-script approvals, and a shared dependency
policy enforced by `check-lockfiles.mjs`.

## Local checks

Run the static policy and lockfile checks without installing anything:

```powershell
node security/check-lockfiles.mjs
```

Run the registry vulnerability audits separately for each project:

```powershell
pnpm -C frontend audit --audit-level=high
pnpm -C agent-harness audit --audit-level=high
```

Install only from the committed resolution and, when the pnpm store is already
warmed, without contacting a registry:

```powershell
pnpm -C frontend install --frozen-lockfile --offline
pnpm -C agent-harness install --frozen-lockfile --offline
```

Do not use `pnpm audit --fix`, `pnpm update`, or `pnpm add` as an automatic
security response. Dependency changes require review of the manifest diff,
lockfile diff, package provenance, install scripts, and audit results.

## Policy

- New releases must age for seven days before resolution.
- Transitive git and direct-tarball sources are blocked.
- A package whose registry trust evidence decreases is rejected.
- Dependency build scripts are denied unless explicitly approved in
  `pnpm-workspace.yaml`.
- CI must use `--frozen-lockfile` and must not expose application credentials
  while installing or auditing dependencies.

These controls reduce supply-chain risk; they cannot prove that a package was
benign when it was published. Keep provider tokens and production credentials
out of dependency-install and untrusted development environments.

## Incident response

If a package or version is reported as compromised, stop running the affected
project, preserve the lockfile and relevant logs, identify whether the version
was installed or executed, and rotate any credentials available to that
process. Remove the affected version through a reviewed lockfile change, then
perform a clean frozen install and rerun the audit and test gates.
