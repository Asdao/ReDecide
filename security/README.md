# Dependency security

This repository treats dependency installation as a security-sensitive operation.
The `frontend` and `agent-harness` projects each have a committed
`pnpm-lock.yaml`, explicit build-script approvals, and a shared dependency
policy enforced by `check-lockfiles.mjs`.

Each project must contain exactly one Node dependency lockfile: its
`pnpm-lock.yaml`. The checker rejects legacy `package-lock.json`,
`npm-shrinkwrap.json`, Yarn, and Bun lockfiles so a second package-manager
graph cannot drift from the reviewed pnpm graph.

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

Python lockfiles are checked with `uv lock --check`; CI exports the frozen root
and backend graphs (including root extras) to hashed requirements and audits
them with a pinned `pip-audit` release. The scheduled workflow repeats this
check independently of code changes.

Install only from the committed resolution and prefer the local pnpm store
when it is already warmed:

```powershell
pnpm -C frontend install --frozen-lockfile --offline
pnpm -C agent-harness install --frozen-lockfile --offline
```

`--offline` prevents missing package tarballs from being downloaded, but pnpm
11.9 may still attempt registry metadata queries while enforcing release-age
and trust policies. Use an OS/container network restriction when zero outbound
network access is a hard requirement.

Do not use `pnpm audit --fix`, `pnpm update`, or `pnpm add` as an automatic
security response. Dependency changes require review of the manifest diff,
lockfile diff, package provenance, install scripts, and audit results.

## Policy

- New releases must age for three days before resolution. This is longer than
  pnpm's one-day default while remaining compatible with the reviewed lockfile.
- Transitive git and direct-tarball sources are blocked.
- A package whose registry trust evidence decreases is rejected.
- `pnpm run`, including `pnpm dev`, fails on stale dependencies instead of
  automatically running an install.
- Dependency build scripts are denied unless explicitly approved in
  `pnpm-workspace.yaml`.
- CI must use `--frozen-lockfile` and must not expose application credentials
  while installing or auditing dependencies.

Policy exceptions must name an exact package version. The current frontend
lockfile has three reviewed exceptions: `get-tsconfig@4.14.1` was already
locked shortly before the three-day policy was introduced, while
`eslint-import-resolver-typescript@3.10.1` and `semver@6.3.1` trigger pnpm's
historical trust-downgrade check. The exceptions do not apply to later
versions. The agent harness similarly exempts only its already-locked
`undici-types@6.21.0` from the trust-history check.

The workspace policies also pin three audited transitive security fixes:
frontend forces `postcss@8.5.23` and `sharp@0.35.0`, and the agent harness
forces `undici@8.9.0`. Their exact versions are temporarily exempt from the
release-age delay because they remediate current advisories; replacement
versions require another reviewed lockfile change.

These controls reduce supply-chain risk; they cannot prove that a package was
benign when it was published. Keep provider tokens and production credentials
out of dependency-install and untrusted development environments.

## Incident response

If a package or version is reported as compromised, stop running the affected
project, preserve the lockfile and relevant logs, identify whether the version
was installed or executed, and rotate any credentials available to that
process. Remove the affected version through a reviewed lockfile change, then
perform a clean frozen install and rerun the audit and test gates.
