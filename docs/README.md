# RE:DECIDE documentation

Use this page as the documentation index. For the fastest local start, begin
with the root [README](../README.md). For implemented behavior and known
limits, read [Current state](CURRENT_STATE.md).

## Run and understand the product

- [Project overview and quick start](../README.md) - product purpose,
  components, environment variables, and the one-command Windows launcher.
- [Current product state](CURRENT_STATE.md) - implemented flow, known limits,
  timeline semantics, and latest verification.
- [Unified FastAPI API](../backend/app/API.md) - active replay, analysis,
  coaching, intent, sample, and compatibility endpoints.
- [Vercel deployment](VERCEL_DEPLOYMENT.md) - service routing, Blob bindings,
  environment configuration, retention, and deployment checks.

## Development setup

- [JavaScript setup](JAVASCRIPT_SETUP.md) - Node.js and pnpm requirements,
  lockfile installation, WSL guidance, and frontend/harness verification.
- [Replay data setup](REPLAY_DATA_SETUP.md) - map assets, sidecars, native
  demos, download limits, and reproducible manifests.
- [Dependency security](DEPENDENCY_SECURITY.md) - lockfile policy, local
  security commands, CI checks, and update workflow.
- [Security tooling](../security/README.md) - repository lockfile and source
  policy enforced by `security/check-lockfiles.mjs`.

## Backend references

- [Replay API component](../backend/replay_api/API.md) - standalone replay
  ingestion/artifact service and its handoff to the unified gateway.
- [Replay engine overview](../backend/replay_engine/README.md) - parser,
  replay-value model, simulator, training, and inference entry points.
- [Replay extractor](../backend/replay_engine/extractor/README.md) - canonical
  replay parsing, normalization, segmentation, and storage.
- [Replay data layout](../backend/replay_engine/docs/DATA_LAYOUT.md) - public,
  private, runtime, and model-artifact locations.
- [Replay module API](../backend/replay_engine/docs/MODULE_API.md) - supported
  Python package boundaries.
- [Model profiles](../backend/replay_engine/docs/MODEL_PROFILES.md) - model
  variants and intended usage.
- [Model training](../backend/replay_engine/docs/TRAINING.md) - reproducible
  training and evaluation commands.

## Frontend and replay assets

- [Processed replay assets](../frontend/public/replays/README.md) - bundled
  replay/analysis pairs consumed by the viewer.
- [Radar assets](../frontend/public/radars/README.md) - supported map radar
  files and metadata.
- [Public data assets](../data/public/README.md) - checked-in sanitized data
  and source metadata.

## Optional legacy agent harness

The normal local backend uses the Python HTTP coach when provider configuration
is present. These guides cover the optional Pi/Node harness:

- [Agent harness overview](../agent-harness/README.md)
- [Getting started](../agent-harness/docs/GETTING_STARTED.md)
- [Architecture](../agent-harness/docs/ARCHITECTURE.md)
- [Analysis pipeline](../agent-harness/docs/ANALYSIS_PIPELINE.md)
- [Tools](../agent-harness/docs/TOOLS.md)
- [Skills](../agent-harness/docs/SKILLS.md)
- [Security](../agent-harness/docs/SECURITY.md)

## Historical documents

Implementation diaries and superseded planning documents are stored under
[docs/archive](archive/README.md). They preserve project history but are not
current setup, API, architecture, or product requirements.

When documents disagree, use the root README for startup, the unified API guide
for transport, Current State for implemented behavior, and executable code and
tests as the final authority.
