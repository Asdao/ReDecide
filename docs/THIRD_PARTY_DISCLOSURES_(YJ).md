# Third-Party Disclosures and Submission Audit

Last audited: 2026-08-06 (Asia/Singapore)

Owner: YJ (Person 5 - evidence and submission coordination)

Repository snapshot: branch `05/evidence_I_think`, commit `405b6a0`

Status: **WORKING INVENTORY - NOT YET APPROVED FOR SUBMISSION**

## Purpose and limits

This file records third-party software, services, models, data, fonts, and game
assets found in the repository so the team can prepare accurate submission and
README disclosures. It is an audit aid, not legal advice or a declaration that
every item is cleared for use.

The licence names below are the licences reported by the linked upstream
projects or package metadata. The team must still preserve required notices,
check the exact locked versions and distribution method, and obtain organiser
or rights-holder guidance where the terms are unclear.

## When this file must be updated

This is a living inventory, but it does not update automatically. YJ or the
relevant component owner must recheck it when any of the following changes:

- a dependency manifest or lockfile;
- the deployed AI provider, model ID, endpoint, or data-handling setting;
- a replay, dataset revision, trained artifact, font, image, map, or other asset;
- the hosting/storage service or deployment configuration;
- the final demo branch, commit, URL, screenshots, deck, or video; or
- an upstream licence, terms page, or rights-holder instruction.

Run a final comparison against the exact submission commit even if no teammate
reports a change. Record the new audit date and commit at the top, update each
affected row, and do not silently replace unresolved items with assumptions.

## Status labels

| Label | Meaning |
| --- | --- |
| `PRIMARY_SOURCE_CHECKED` | Licence or terms were found on the upstream project, package, or provider page |
| `REPO_DECLARED` | Use is visible in this repository, but the final deployed configuration still needs confirmation |
| `OWNER_CONFIRMATION_REQUIRED` | A component owner must confirm use, provenance, version, or permission before submission |
| `NOT_IN_FINAL_BUILD` | The team has confirmed that the item is not shipped, demonstrated, or used to create submitted artifacts |

These labels describe evidence status, not legal approval.

## Submission blockers requiring a team decision

| Blocker | Why it matters | Required owner | Resolution evidence |
| --- | --- | --- | --- |
| No repository-level `LICENSE` or `COPYING` file was found | Third-party licences do not determine the licence for the team's own code | Person 1 / repository owner | Chosen project licence or an explicit all-rights-reserved/submission-only decision recorded in the README |
| Final hosted AI model is inconsistent and unconfirmed | `.env.example` uses `deepseek-v3-flash`, while the harness default and tests also use `deepseek-v4-pro`; neither alias should be disclosed as final without deployment evidence | Persons 1 and 3 | Screenshot or deployment variable record showing provider, exact model ID, endpoint, and date |
| CS2 map imagery has no reusable software licence in the source repository | The source states that the icons, radars, thumbnails, and overview data are Valve property; attribution alone is not permission | Persons 1 and 4 | Remove/replace the asset, or record organiser/rights-holder approval and required attribution |
| Replay dataset licence does not settle upstream tournament rights | The Hugging Face card labels the dataset CC BY 4.0 but says users remain responsible for original tournament terms | Persons 1 and 2 | Final demo/training sample list with source, tournament, permitted use, attribution, and redistribution decision |
| Checked-in model release lacks linked dataset provenance | `releases/v5/release_manifest.json` has `dataset_manifest: null` and `metrics: null`, while the current pointer selects `v5` | Persons 2 and 3 | Model card or release record linking training data revision, licence review, code/version, metrics, and artifact hashes |
| Final dependency versions and notices are not frozen | Manifests mostly use version ranges and direct-dependency tables do not cover transitive packages | Component owners | Lockfile-based licence report/SBOM generated from the final demo commit and bundled notices where required |

## External services and hosted models

| Service or model | Repository evidence and role | Governing material | Status and required action |
| --- | --- | --- | --- |
| DeepSeek API | `agent-harness/.env.example` configures the OpenAI-compatible endpoint `https://api.deepseek.com`; prompts may contain derived replay evidence and coaching context | [DeepSeek Terms of Use](https://cdn.deepseek.com/policies/en-US/deepseek-terms-of-use.html), [Open Platform Terms](https://cdn.deepseek.com/policies/en-US/deepseek-open-platform-terms-of-service.html), and [API documentation](https://platform.deepseek.com/api-docs) | `REPO_DECLARED`; Person 3 must confirm the exact deployed model ID, account/region, data handling, and whether any personal or confidential replay data is transmitted |
| DeepSeek model weights | No DeepSeek weights were found in the repository; current code appears to call a hosted API | Exact model page and model licence, only if weights are downloaded or redistributed | Treat as hosted-service use unless Person 3 confirms local/open-weight use; never infer a weights licence from API access |
| Vercel hosting | `docs/VERCEL_DEPLOYMENT.md` documents deployment; service configuration and environment secrets may be held by Vercel | [Vercel Terms](https://vercel.com/legal/terms) and applicable privacy/data-processing terms | `REPO_DECLARED`; Person 1 must confirm whether the submitted build is actually hosted on Vercel and identify the final URL |
| Vercel Blob | Documented as optional and disabled by default | [Vercel Blob documentation](https://vercel.com/docs/vercel-blob) and applicable Vercel terms | `OWNER_CONFIRMATION_REQUIRED`; disclose only if enabled, and document retention/deletion for uploaded replays |
| Hugging Face Hub | Training downloader references a public dataset on the Hub; not shown as a production runtime dependency | [Dataset page](https://huggingface.co/datasets/blanchon/cs2_dataset_demo) and Hub terms | `REPO_DECLARED` for training; Persons 2 and 3 must record the exact dataset revision used |
| GitHub raw-content hosting | The unmerged frontend work references map imagery using `raw.githubusercontent.com` | GitHub terms plus the underlying asset rights | Hosting availability does not grant asset rights; do not rely on attribution alone |

API keys and provider credentials must remain server-side secrets. They must
not appear in the repository, browser bundle, screenshots, deck, or demo video.

## Python direct dependencies

Source: root `pyproject.toml`. Ranges are repository declarations, not proof of
the exact installed or submitted versions.

| Dependency | Declared range/group | Role | Reported licence | Evidence status |
| --- | --- | --- | --- | --- |
| [FastAPI](https://github.com/fastapi/fastapi) | `>=0.115,<1` | Backend web API | MIT | `PRIMARY_SOURCE_CHECKED` |
| [HTTPX](https://github.com/encode/httpx) | `>=0.28,<1` | HTTP client and API testing | BSD-3-Clause | `PRIMARY_SOURCE_CHECKED` |
| [Pydantic](https://github.com/pydantic/pydantic) | `>=2.7,<3` | Validation and schemas | MIT | `PRIMARY_SOURCE_CHECKED` |
| [python-multipart](https://github.com/Kludex/python-multipart) | `>=0.0.9,<1` | Multipart replay uploads | Apache-2.0 | Verify the exact locked release and retain its notice |
| [Uvicorn](https://github.com/Kludex/uvicorn) | `>=0.34,<1` | ASGI server | BSD-3-Clause | Verify the exact locked release and retain its notice |
| [Awpy](https://github.com/pnxenopoulos/awpy) | `>=2.0.2`, optional `full` | CS2 demo parsing and map data tooling | MIT | `PRIMARY_SOURCE_CHECKED`; asset/data rights remain separate |
| [LightGBM](https://github.com/lightgbm-org/LightGBM) | `>=4.0`, optional `full` | Trains/loads predictive artifacts | MIT | `PRIMARY_SOURCE_CHECKED` |
| [PyArrow](https://github.com/apache/arrow) | `>=15.0`, optional `full` | Arrow/Parquet data processing | Apache-2.0 | `PRIMARY_SOURCE_CHECKED` |
| [fastparquet](https://github.com/dask/fastparquet) | `>=2024.0`, optional `data` | Parquet data processing | Apache-2.0 | `PRIMARY_SOURCE_CHECKED` |
| [pandas](https://github.com/pandas-dev/pandas) | `>=2.0`, optional `data` | Tabular data processing | BSD-3-Clause | `PRIMARY_SOURCE_CHECKED` |
| [pytest](https://github.com/pytest-dev/pytest) | `>=8,<9`, optional `test` | Test runner; development only | MIT | `PRIMARY_SOURCE_CHECKED` |
| [setuptools](https://github.com/pypa/setuptools) | `>=68`, build system | Python packaging/build | MIT | Confirm final build environment and exact version |

## Frontend direct dependencies

Source: `frontend/package.json`. `pnpm-lock.yaml` must be used to generate the
final exact-version and transitive-dependency report.

| Dependency group | Declared packages | Role | Reported licence | Evidence status |
| --- | --- | --- | --- | --- |
| Web framework | `next ^16.2.12` | Frontend framework | MIT | Upstream project checked; exact lockfile version required |
| UI runtime | `react ^19.2.8`, `react-dom ^19.2.8` | User interface | MIT | Upstream project checked; exact lockfile versions required |
| Validation | `zod ^4.4.3` | Runtime schema validation | MIT | Confirm from final installed package metadata |
| Fontsource packages | `@fontsource-variable/noto-sans ^5.3.0`, `@fontsource-variable/saira ^5.3.0`, `@fontsource/saira-condensed ^5.3.0` | Self-hosted webfont packaging | Package code: MIT; included fonts retain their own licences | See the separate font inventory below |
| Styling/build | `tailwindcss ^4.3.3`, `@tailwindcss/postcss ^4.3.3` | CSS generation | MIT | Upstream project checked; exact lockfile versions required |
| Lint/config | `eslint ^9.39.5`, `eslint-config-next ^16.2.12` | Development checks | MIT | Development-only unless bundled unexpectedly |
| Type declarations | `@types/node ^26.1.2`, `@types/react ^19.2.18`, `@types/react-dom ^19.2.4` | Development typing | MIT | Development-only |
| TypeScript | `typescript ^6.0.3` | Compiler; development/build | Apache-2.0 | Confirm exact lockfile version |
| Vitest | `vitest ^4.1.10` | Test runner; development only | MIT | Confirm exact lockfile version |

## Agent harness direct dependencies

Source: `agent-harness/package.json`.

| Dependency | Declared range | Role | Reported licence | Evidence status |
| --- | --- | --- | --- | --- |
| [`@earendil-works/pi-coding-agent`](https://www.npmjs.com/package/@earendil-works/pi-coding-agent) | `^0.83.0` | Agent/model harness SDK | MIT | `PRIMARY_SOURCE_CHECKED`; record exact locked version and transitive notices |
| [`@sinclair/typebox`](https://github.com/sinclairzx81/typebox) | `^0.34.41` | JSON-schema types | MIT | Confirm from final locked package metadata |
| `@types/node`, `tsx`, `typescript`, `vitest` | Development ranges in manifest | Types, TS execution/compiler, tests | MIT except TypeScript (Apache-2.0) | Development-only; exact versions remain lockfile-controlled |

## Fonts and visual/game assets

| Item | Source and current use | Reported terms | Submission action |
| --- | --- | --- | --- |
| Noto Sans | Bundled through `@fontsource-variable/noto-sans` | SIL Open Font License 1.1 for the current Fontsource font package; package code has separate MIT terms | Preserve the font licence/notice and verify the exact installed package |
| Saira and Saira Condensed | Bundled through Fontsource packages | SIL Open Font License 1.1 for the font files; package code has separate MIT terms | Preserve the font licence/notice and verify the exact installed packages |
| MurkyYT CS2 map icons/thumbnails/radars | Referenced by frontend work from [`MurkyYT/cs2-map-icons`](https://github.com/MurkyYT/cs2-map-icons) | Repository states the assets are Valve Corporation property and does not provide a reusable asset licence | `OWNER_CONFIRMATION_REQUIRED`; remove/replace unless the team can document permitted hackathon use; attribution by itself is insufficient |
| Awpy nav/map archives | Downloader fetches `navs.zip` and `maps.zip` from `awpycs.com` | Awpy software is MIT, but that does not automatically license separately distributed game-derived data/assets | Person 2 must identify what is included in the final build and verify its source terms |
| Counter-Strike names, maps, and imagery | Product necessarily refers to CS2 and may show game-derived information | Valve trademarks/copyrights are separate from open-source dependency licences | Add a factual non-affiliation notice if applicable and follow organiser/Valve guidance; avoid implying endorsement |
| Team-created UI, diagrams, screenshots, and video | Produced by the team | Team-owned only to the extent all embedded inputs and assets are cleared | Keep source/project files and record creator, date, and embedded third-party materials |

## Data and trained artifacts

| Item | Repository evidence | Stated licence/provenance | Status and action |
| --- | --- | --- | --- |
| `blanchon/cs2_dataset_demo` | `backend/replay_engine/training/download_dataset.py` and `sidecars_manifest.json` name this dataset; the manifest currently tracks `main` rather than an immutable revision | Dataset card displays CC BY 4.0 and says demos are mirrored from HLTV's public endpoint, with downstream users responsible for original tournament terms | `OWNER_CONFIRMATION_REQUIRED`; pin a commit/revision, preserve attribution, and verify the rights for every replay used in training, screenshots, or demo |
| Raw `.dem` files | Download workflow can retrieve tournament demos; no raw `.dem` was found in the tracked file list during this audit | Rights may belong to game publisher, tournament organiser, platform, teams, or players depending on the source | Keep raw demos private unless redistribution is clearly permitted; record the exact final demo sample and source |
| Analysis sidecars | `sidecars_manifest.json` lists derived analysis files and hashes from the dataset | Derivative status does not erase upstream restrictions | Record whether any sidecar is shipped and include its dataset/tournament provenance |
| Checked-in replay/model releases | `backend/replay_engine/model/artifacts/releases/` contains statistical and LightGBM-derived artifacts; `current.json` points to `v5` | Training-code dependency licences are listed above, but artifact provenance is incomplete in the release manifest | Persons 2 and 3 must create a model card or release note before making training-data, accuracy, or reproducibility claims |
| Human-review CSV | `data/eval/human/review_cases_(YJ).csv` is currently a team-created, header-only schema | No third-party rows or personal data have been added | If populated, anonymise reviewer/case identifiers, obtain consent where needed, and document the source of each case |

## Model and AI disclosure record to complete

The final submission should disclose the actual deployed configuration, not a
planned alias. Persons 1 and 3 should complete this record from the final demo
environment:

| Field | Final value |
| --- | --- |
| Provider | `TBD` |
| Exact model ID/version | `TBD` |
| Hosted API or local weights | `TBD` |
| Endpoint/region, excluding secrets | `TBD` |
| Date configuration was verified | `TBD` |
| What data is sent to the model | `TBD` |
| Data retention/privacy setting checked | `TBD` |
| Fallback model/provider | `TBD` |
| Evidence: deployment/commit reference | `TBD` |

Until this table is completed, use wording such as “the prototype is designed
to use an LLM-backed coaching layer.” Do not name a final model in the deck or
README as a confirmed fact.

## Proposed README handoff

Person 1 owns the root README. Once the blockers above are resolved, the README
should contain a concise disclosure resembling the following, edited to match
the final build:

> RE:DECIDE uses open-source web, data, replay-analysis, and agent libraries.
> The submitted build uses **[provider and exact model]** through a hosted API;
> secrets remain server-side. Training/evaluation data comes from **[pinned
> source and revision]** under **[licence]**, subject to **[upstream tournament
> terms]**. Visual assets are **[team-created or cleared source]** with required
> attribution. Counter-Strike and related game assets are the property of their
> respective owners; this project is not affiliated with or endorsed by Valve.
> Full dependency and third-party notices are available at **[path/link]**.

Do not paste this paragraph unchanged while bracketed fields or asset rights are
unresolved.

## Final verification checklist

- [ ] Person 1 records the final branch, commit, deployment URL, deadline, and repository-licence decision.
- [ ] Person 3 records the exact provider/model and verifies service/privacy terms for the submitted configuration.
- [ ] Persons 2 and 3 link model release `v5` (or its replacement) to an immutable dataset revision and model card.
- [ ] Person 2 records the source and permission basis for every replay used in the demo, evaluation, screenshots, or model training.
- [ ] Person 4 removes or clears Valve-derived map imagery and confirms the final font/asset inventory.
- [ ] Component owners generate lockfile-based exact dependency/licence reports for Python and both pnpm projects.
- [ ] Required copyright, licence, and attribution notices are bundled with the submission.
- [ ] YJ compares the final build against this inventory and marks unused entries `NOT_IN_FINAL_BUILD`.
- [ ] Person 1 incorporates the approved short disclosure into the README and submission form.
- [ ] The team checks deck screenshots and demo footage for secrets, personal data, unapproved logos, and uncleared assets.

## Repository evidence inspected

- `pyproject.toml`
- `frontend/package.json` and `frontend/pnpm-lock.yaml`
- `agent-harness/package.json`, `agent-harness/pnpm-lock.yaml`, and `agent-harness/.env.example`
- `agent-harness/src/model-config.ts`
- `docs/VERCEL_DEPLOYMENT.md`
- `backend/replay_engine/training/download_dataset.py`
- `backend/replay_engine/training/download_maps.py`
- `backend/replay_engine/training/sidecars_manifest.json`
- `backend/replay_engine/model/artifacts/releases/current.json`
- `backend/replay_engine/model/artifacts/releases/v5/release_manifest.json`
- Frontend status/docs and `origin/04/frontend` references to `MurkyYT/cs2-map-icons`

This inventory must be rerun against the final submission commit because
dependencies, services, assets, and deployment configuration may change.
