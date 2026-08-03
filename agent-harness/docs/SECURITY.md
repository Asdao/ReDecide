# Security model

The harness is a policy boundary, not a general-purpose sandbox. Treat the Pi project, simulator, model provider, and host process as trusted only to the degree required by the deployment.

## Threats and controls

| Threat | Control |
| --- | --- |
| Model requests an unapproved tool | Default-deny registry and explicit allowlist; unknown names are rejected before dispatch. |
| Accidental shell or filesystem access | Pi built-in tools are disabled; the bridge uses an explicit executable and script path with `shell: false`. |
| Runaway simulator or hung child | Per-call timeout, abort propagation, process termination, and bounded stdout/stderr retention. |
| Oversized model or bridge result | TypeBox bounds, `max_events` 1–100, 64 KiB tool result cap, and 256 KiB bridge output cap. |
| Protocol confusion | Versioned JSON envelopes, fixed operation table, strict fields, and independent validation in TypeScript and Python. |
| Sensitive diagnostic leakage | Stderr is diagnostic only; bridge failures return stable, sanitized error codes and messages. |
| Duplicate or unreviewed instructions | Skills come only from explicit directories and fail closed on malformed or duplicate `SKILL.md` files. |
| Untracked activity | Audit events record request, allow/deny, finish, timeout, and cancellation decisions without storing secrets by default. |

## Credential and data handling

Keep provider credentials in the host environment or secret manager, never in this package, skills, prompts, or tool arguments. Do not commit sessions, audit logs, generated output, or copied simulator state. Review prompts and returned state before sending them to an external model provider.

## Production checklist

- Run the bridge under a dedicated low-privilege account or container for untrusted workloads.
- Use an absolute Python executable and bridge path; do not accept model-supplied paths.
- Keep the allowlist minimal and require explicit approval for any future write-effect tool.
- Set deployment-specific timeouts, output limits, and resource quotas.
- Rotate and protect provider credentials; redact correlation IDs or inputs if audit sinks become externally visible.
- Pin dependencies and review Pi SDK, Python, and simulator updates before rollout.
- Test malformed JSON, unknown operations, cancellation, timeout, oversized output, and duplicate skills as part of release checks.
