# RE:DECIDE QA Matrix

Last updated: 2026-08-05 (Asia/Singapore)

Owner: YJ (Person 5 - User Evidence, QA, Pitch Deck, and Demo)

Status: Test plan prepared; execution not started

## Purpose

This matrix records whether the final RE:DECIDE submission behaves safely,
reliably, and truthfully. It prioritizes failures that can break the recorded
demo, expose secrets, leak future information, or present unsupported coaching.

No row is evidence of working behavior until its status is `PASS` and it links
to a recorded environment, commit, actual result, and supporting evidence.

## Status values

Use only:

- `NOT_RUN` - test has not been attempted;
- `PASS` - observed behavior matches the expected result;
- `FAIL` - observed behavior does not match the expected result;
- `BLOCKED` - a documented dependency prevents execution; or
- `NOT_APPLICABLE` - the feature is explicitly outside the frozen submission
  scope, with the team decision recorded.

Do not use `PASS` for a test that was inferred from code, passed on another
branch, or reported verbally without reproducible evidence.

## Severity definitions

| Priority | Meaning | Release effect |
| --- | --- | --- |
| P0 | Submission cannot complete, secret/private data exposed, future outcome influences coaching, or false evidence is presented | Must be fixed or the affected path must be removed from the submission |
| P1 | Major user flow or common reliability failure; important result is wrong or unsafe | Fix or document an explicit demo-safe mitigation before freeze |
| P2 | Recoverable usability, accessibility, copy, or uncommon workflow problem | Fix after P0/P1 when time allows |
| P3 | Cosmetic issue with no meaningful effect on correctness or completion | Does not block freeze unless it harms the recorded demo |

## Test environment record

Complete this before executing rows.

| Field | Value |
| --- | --- |
| Final candidate branch | TBD |
| Final candidate commit | TBD |
| Test date/time | TBD |
| Tester | YJ |
| Operating system | TBD |
| Browser and version | TBD |
| Python version | TBD |
| Node version | TBD |
| pnpm version | TBD |
| Backend URL | TBD |
| Frontend URL | TBD |
| Provider/model | TBD |
| Parser/model release | TBD |
| Primary demo/sample ID | TBD |
| Secondary demo/sample ID | TBD |
| Network conditions | TBD |

## Frozen scope gates

These decisions determine which tests are applicable. Person 1 should confirm
them against the final demo commit.

| Feature | Submission scope | Evidence/decision |
| --- | --- | --- |
| Direct `.dem` upload | TBD | TBD |
| Bundled sample | TBD | TBD |
| Player selection | TBD | TBD |
| Live provider coaching | TBD | TBD |
| Player intent | TBD | Current API documentation says unsupported; recheck final commit |
| Full version `1.0` Decision Card | TBD | Documented separately from live replay-job result; recheck final commit |
| Expandable evidence references | TBD | TBD |
| Next-match quest | TBD | TBD |
| Later outcome reveal | TBD | Current frontend status says later outcome is not rendered; recheck final commit |
| Visualization/radar timeline | TBD | Retrieval exists; rendered scope is unconfirmed |
| Fixture fallback | TBD | Must be visibly labelled and never silently replace a real failure |

## Test data required

| Data item | Source/owner | Availability | Notes |
| --- | --- | --- | --- |
| Primary legal `.dem` or genuine sample | Persons 1 and 2 | TBD | Exact recording input |
| Secondary legal `.dem` or sample | Person 2 | TBD | Different match or map when possible |
| Player with an eligible decision | Person 2 | TBD | Stable `player_id` and `decision_id` |
| Player with no eligible decision | Person 2 | TBD | Must not be treated as parser failure |
| Unsupported/malformed demo | Person 2 | TBD | Non-private safe fixture |
| Low-data-quality packet | Persons 2 and 3 | TBD | Used to test abstention |
| Contradictory packet/output | Person 3 | TBD | Deterministic negative fixture |
| Unsupported evidence-reference output | Person 3 | TBD | Nonexistent evidence ID |
| Future-information injection | Persons 1 and 3 | TBD | Safe deterministic test only |
| Malformed provider output | Person 3 | TBD | Injected fixture; no paid call required |

Do not commit private `.dem` files or real player identifiers to this branch.

## P0 test register

| ID | Area | Test | Expected result | Owner | Status | Evidence |
| --- | --- | --- | --- | --- | --- | --- |
| QA-P0-001 | End to end | Complete the exact recorded-demo path from landing to final result | Flow completes on the frozen commit without terminal intervention or hidden manual data replacement | Persons 1-4 | NOT_RUN | TBD |
| QA-P0-002 | End to end | Repeat the primary path after a fresh restart | Same input reaches a valid result or a documented deterministic limitation without stale state | Persons 1-4 | NOT_RUN | TBD |
| QA-P0-003 | Secrets | Inspect Git status/history, `.env.example`, logs, screenshots, network responses, and production frontend output | No provider key, private replay path/content, personal identifier, or server-only configuration is exposed | Persons 1, 3, and 4 | NOT_RUN | TBD |
| QA-P0-004 | Evidence | Inject or load a coaching output referencing a nonexistent evidence ID | Missing reference is rejected or omitted from verified evidence; no invented evidence detail is displayed | Persons 1, 3, and 4 | NOT_RUN | TBD |
| QA-P0-005 | Knowledge boundary | Inject a later kill/death/win/outcome fact into a negative test case | Future-information check blocks or invalidates the coaching output; unsafe prose is not shown as verified | Persons 1-4 | NOT_RUN | TBD |
| QA-P0-006 | Knowledge boundary | Inspect the actual provider input for the primary demo case | No event after `action_close_tick`, later outcome, winner, or future label is supplied to the coach | Persons 2 and 3 | NOT_RUN | TBD |
| QA-P0-007 | Truthfulness | Force the real sample/upload path to fail while fixture fallback is available | Product never silently substitutes fixture output; fallback requires an explicit action and persistent provenance label | Persons 1 and 4 | NOT_RUN | TBD |
| QA-P0-008 | Submission setup | Follow final setup instructions on a clean machine or clean environment | Product installs and the recorded path runs using documented commands; any unavailable dependency is explicitly disclosed | Person 1 with YJ verification | NOT_RUN | TBD |

## P1 test register - replay and API

| ID | Area | Test | Expected result | Owner | Status | Evidence |
| --- | --- | --- | --- | --- | --- | --- |
| QA-P1-001 | Health | Request `GET /api/health` | Returns the documented healthy response without secrets | Person 1 | NOT_RUN | TBD |
| QA-P1-002 | Upload | Upload the primary legal `.dem` through `POST /api/replay/upload` | File is accepted once and a validated replay manifest with stable `replay_id` is returned | Persons 1 and 2 | NOT_RUN | TBD |
| QA-P1-003 | Upload | Submit a wrong file type or malformed demo | Typed, non-sensitive invalid/unsupported-demo response; no stack trace in UI | Persons 1, 2, and 4 | NOT_RUN | TBD |
| QA-P1-004 | Upload | Submit a file above the configured size limit | Request is rejected safely with usable guidance and no partial success | Persons 1, 2, and 4 | NOT_RUN | TBD |
| QA-P1-005 | Preparation | Send the returned `replay_id` to `POST /api/analysis/prepare` | Asynchronous job is created with stable `analysis_id` and progress locations | Persons 1 and 2 | NOT_RUN | TBD |
| QA-P1-006 | Preparation | Poll analysis and player endpoints until ready | Status progresses truthfully and selectable players have stable IDs | Persons 1, 2, and 4 | NOT_RUN | TBD |
| QA-P1-007 | Player selection | Select an eligible stable `player_id` | The selected player owns the displayed decision and coaching result | Persons 1, 2, and 4 | NOT_RUN | TBD |
| QA-P1-008 | Player selection | Select a missing, ambiguous, or ineligible player | Typed error; no coaching call and no result for the wrong player | Persons 1, 2, and 4 | NOT_RUN | TBD |
| QA-P1-009 | No decision | Analyze a player/match with no eligible post-contact decision | Clear no-eligible-decision state; not misreported as parser or provider failure | Persons 1, 2, and 4 | NOT_RUN | TBD |
| QA-P1-010 | Coaching | Run coaching once for the selected player | One provider request produces a validated player-scoped result or typed failure | Persons 1, 3, and 4 | NOT_RUN | TBD |
| QA-P1-011 | Recovery | Simulate a lost/timeout response after coaching may have completed | Frontend checks result recovery without automatically starting a duplicate paid call | Persons 1, 3, and 4 | NOT_RUN | TBD |
| QA-P1-012 | Result | Retrieve `GET /api/analysis/{analysis_id}/result` after completion | Same completed result is returned without rerunning coaching | Persons 1 and 3 | NOT_RUN | TBD |
| QA-P1-013 | Restart | Restart backend after creating an in-memory analysis job | User receives an honest job-not-found/restart limitation and recovery path | Persons 1 and 4 | NOT_RUN | TBD |
| QA-P1-014 | Visualization | Request replay JSON before and after coaching unlock | Locked/processing state is enforced before coaching; validated visualization becomes available only after success | Persons 1, 2, and 4 | NOT_RUN | TBD |

## P1 test register - coach, evidence, and contracts

| ID | Area | Test | Expected result | Owner | Status | Evidence |
| --- | --- | --- | --- | --- | --- | --- |
| QA-P1-015 | Provider config | Start coaching without a provider API key | Typed missing-key/model-unavailable error with no secret or stack trace | Persons 1, 3, and 4 | NOT_RUN | TBD |
| QA-P1-016 | Timeout | Force provider or request timeout | Truthful timeout state, no duplicate submission, and safe retry/recovery behavior | Persons 1, 3, and 4 | NOT_RUN | TBD |
| QA-P1-017 | Provider output | Return malformed JSON or an invalid provider shape | Output is rejected and never rendered as a successful coaching result | Persons 1, 3, and 4 | NOT_RUN | TBD |
| QA-P1-018 | Contract | Pair a packet and card/result with different `decision_id` values | Mismatch is rejected before display | Persons 1, 3, and 4 | NOT_RUN | TBD |
| QA-P1-019 | Evidence | Provide duplicate, blank, missing, or unsupported evidence IDs | Invalid references are rejected or filtered according to the frozen contract; no empty verified-evidence popover | Persons 1, 3, and 4 | NOT_RUN | TBD |
| QA-P1-020 | Contradiction | Set contradiction detection or provide conflicting facts | Unsafe directional coaching is suppressed or converted to the agreed invalid/abstention state | Persons 1, 3, and 4 | NOT_RUN | TBD |
| QA-P1-021 | Data quality | Provide low-quality or materially incomplete evidence | System communicates uncertainty and uses `INSUFFICIENT_EVIDENCE` when a responsible directional verdict is unsupported | Persons 2, 3, and 4 | NOT_RUN | TBD |
| QA-P1-022 | Confidence | Evaluate a low-quality or warning-heavy case | Confidence respects the implemented cap/rules and does not imply unsupported certainty | Person 3 | NOT_RUN | TBD |
| QA-P1-023 | Outcome language | Search the primary coaching output for later death, survival, kill, win, and round-result claims | Coaching contains no future/outcome claim unless the final UI reveals outcome in a clearly separate post-coaching region | Persons 3 and 4 | NOT_RUN | TBD |
| QA-P1-024 | Intent scope | Verify intent behavior against the frozen submission scope | If unsupported, UI does not collect or claim intent; if supported, intent is collected before judgement and length/validation rules apply | Persons 1, 3, and 4 | NOT_RUN | TBD |
| QA-P1-025 | Full card scope | Verify Decision Card, evidence, options, limitations, and quest against the frozen submission scope | Only implemented and validated fields are shown; absent features are not claimed in deck/demo | Persons 1, 3, and 4 | NOT_RUN | TBD |

## P1 test register - frontend reliability

| ID | Area | Test | Expected result | Owner | Status | Evidence |
| --- | --- | --- | --- | --- | --- | --- |
| QA-P1-026 | Network | Disconnect or block backend during each major request stage | Safe network error with preserved retry context; no fabricated result | Person 4 | NOT_RUN | TBD |
| QA-P1-027 | Response parsing | Return non-JSON error content or malformed successful JSON | Safe invalid-response state; unvalidated content is not rendered | Persons 1 and 4 | NOT_RUN | TBD |
| QA-P1-028 | Duplicate request | Double-click upload, player selection, or coaching action | Only one request/model call is accepted for the active operation | Person 4 | NOT_RUN | TBD |
| QA-P1-029 | Stale response | Reset or begin a new request before an older request completes | Late response cannot replace the current state | Person 4 | NOT_RUN | TBD |
| QA-P1-030 | Reset/privacy | Reset during upload/preparation/coaching and after result | Pending requests abort where possible and sensitive client state is cleared | Person 4 | NOT_RUN | TBD |
| QA-P1-031 | Refresh/back | Refresh or navigate back at major flow stages | Behavior is understandable and does not expose stale or mismatched coaching | Person 4 | NOT_RUN | TBD |
| QA-P1-032 | Sample list | Load zero, one, many, and unavailable samples | Each state is truthful, validated, and recoverable | Persons 1 and 4 | NOT_RUN | TBD |

## P2 accessibility and usability register

| ID | Area | Test | Expected result | Owner | Status | Evidence |
| --- | --- | --- | --- | --- | --- | --- |
| QA-P2-001 | Keyboard | Complete the recorded path without a mouse | All controls are reachable, focus is visible, and focus order follows the flow | Person 4 | NOT_RUN | TBD |
| QA-P2-002 | Focus | Trigger screen transitions and blocking errors | Focus moves to the new heading or error summary without trapping the user | Person 4 | NOT_RUN | TBD |
| QA-P2-003 | Semantics | Inspect upload, player selection, progress, result, and disclosure controls | Labels, headings, live regions, alerts, and expanded-state semantics are meaningful | Person 4 | NOT_RUN | TBD |
| QA-P2-004 | Viewports | Check `1440x900`, `1366x768`, `1280x720`, and the supported narrow viewport | No body-level horizontal overflow, clipped controls, or obscured focus | Person 4 | NOT_RUN | TBD |
| QA-P2-005 | Zoom | Inspect key screens at 200% browser zoom where feasible | Content remains readable and operable without hidden limitations | Person 4 | NOT_RUN | TBD |
| QA-P2-006 | Motion | Enable reduced-motion preference | Non-essential motion is removed and progress remains understandable | Person 4 | NOT_RUN | TBD |
| QA-P2-007 | Copy | Ask a first-time viewer to explain the decision, known facts, hidden future, observed action, and next lesson | Misunderstandings are recorded; no comprehension percentage without real participants and denominator | YJ and Person 4 | NOT_RUN | TBD |
| QA-P2-008 | Limitations | Inspect uncertainty, unknowns, failure, and abstention copy | Limitations are visible, readable, and not hidden in low-contrast fine print | Person 4 | NOT_RUN | TBD |

## P3 visual-polish register

| ID | Area | Test | Expected result | Owner | Status | Evidence |
| --- | --- | --- | --- | --- | --- | --- |
| QA-P3-001 | Visual consistency | Compare landing, progress, selection, and result screens | Typography, color, spacing, and control states are consistent | Person 4 | NOT_RUN | TBD |
| QA-P3-002 | Assets | Load map thumbnails, fonts, and icons with normal and blocked external network | Reviewed local assets load where required; fallback is intentional and attributed | Person 4 | NOT_RUN | TBD |
| QA-P3-003 | Recording | Capture the final route at recording resolution | Text and evidence remain readable in the exported video | YJ and Person 4 | NOT_RUN | TBD |

## Submission QA register

| ID | Test | Expected result | Owner | Status | Evidence |
| --- | --- | --- | --- | --- | --- |
| QA-SUB-001 | Verify final deck page count | PDF contains 15 slides or fewer | YJ | NOT_RUN | TBD |
| QA-SUB-002 | Verify final video duration | Video is 5:00 or shorter; target script remains near 4:20 | YJ | NOT_RUN | TBD |
| QA-SUB-003 | Inspect every exported PDF page | No clipping, missing fonts, placeholder metrics, unreadable citations, or accidental notes | YJ | NOT_RUN | TBD |
| QA-SUB-004 | Watch final video from start to finish | Audio is clear, UI is readable, timing is correct, and every claim matches the shown build | YJ and team | NOT_RUN | TBD |
| QA-SUB-005 | Verify repository access | Required Garena collaborator/access setting is confirmed | Person 1 | NOT_RUN | TBD |
| QA-SUB-006 | Verify README completeness | Setup, architecture, prompts/agent configuration, models, APIs, libraries, datasets, licences, privacy, limitations, and exceptions are documented | Person 1 with YJ handoff | NOT_RUN | TBD |
| QA-SUB-007 | Verify Drive/submission links in logged-out/incognito session | All required files open with correct names and permissions | YJ and Person 1 | NOT_RUN | TBD |
| QA-SUB-008 | Record immutable final identifiers | Final repository commit, deck filename, video filename, and submission time are recorded | YJ and Person 1 | NOT_RUN | TBD |
| QA-SUB-009 | Enforce post-submission freeze | No file or link is modified after the submission cutoff | Team | NOT_RUN | TBD |

## Detailed execution record template

Create one record for every executed test. Do not overwrite the original
failure when recording a retest.

```text
Test ID:
Priority:
Area:
Tester:
Date/time and timezone:
Branch and commit:
Environment:
Input/sample/decision ID:
Preconditions:
Steps:
Expected result:
Actual result:
Status: PASS / FAIL / BLOCKED / NOT_APPLICABLE
Screenshot, log, or artifact link:
Sensitive information removed: yes / no
Assigned owner:
Issue link:
Retest required: yes / no
Notes:
```

## Bug-report template

```text
Issue ID:
Related QA test ID:
Decision ID, when applicable:
Severity: P0 / P1 / P2 / P3
Environment and commit:
Reproduction steps:
Expected result:
Actual result:
Screenshot or evidence:
Privacy/secret impact:
Assigned owner:
Mitigation:
Status:
Retest evidence:
```

Do not include provider keys, private replay paths, personal information, or
unredacted raw model/provider logs in a bug report.

## Feature-freeze gate

The demo candidate is ready for feature freeze only when:

- every applicable P0 test passes;
- every applicable P1 test passes or has an explicit truthful mitigation;
- the exact primary demo path has completed on the frozen commit;
- secret and future-information inspections have passed;
- final implemented features match the deck and script;
- open P2/P3 issues do not obstruct or misrepresent the demo; and
- the final commit and test evidence are recorded.

If any P0 remains failed or untested, the team must not claim the affected path
is validated.

## Current totals

| Priority group | Total planned | Passed | Failed | Blocked | Not run |
| --- | ---: | ---: | ---: | ---: | ---: |
| P0 | 8 | 0 | 0 | 0 | 8 |
| P1 | 32 | 0 | 0 | 0 | 32 |
| P2 | 8 | 0 | 0 | 0 | 8 |
| P3 | 3 | 0 | 0 | 0 | 3 |
| Submission | 9 | 0 | 0 | 0 | 9 |

Totals must be updated whenever a row status changes.
