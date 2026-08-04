# RE:DECIDE

> Don't replay the match. Replay the decision.

RE:DECIDE is an outcome-blind Counter-Strike 2 decision coach. The MVP covers
one decision family: reset versus re-engage after first damage contact.

## Current state

The backend currently provides a Day 1 walking skeleton backed by checked-in
fixtures. It proves the frontend transport and validation boundaries; it does
not yet parse an uploaded `.dem` or call a live coaching model.

```text
fixture/sample -> neutral DecisionPacket -> player IntentInput
               -> fixture coach -> validated DecisionCard
```

The three version `1.0` product contracts live in
`backend/app/contracts.py`. Their field names, enums, knowledge cutoffs, and
evidence semantics must not change without Person 1 coordinating a migration.

## Backend setup

Python 3.12 or newer is required. With `uv` installed:

```powershell
uv sync --frozen --no-install-project
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload
```

The API is then available at `http://127.0.0.1:8000`, with interactive OpenAPI
documentation at `http://127.0.0.1:8000/docs`.

Run the focused backend tests with:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s backend/tests -p "test_*.py" -v
```

`--no-install-project` is temporarily required because the root setuptools
configuration still references legacy source paths that moved under `Noah/`.
Coordinate that shared packaging cleanup with Noah rather than deleting the
paths silently.

## Fixture API

| Endpoint | Day 1 behavior |
|---|---|
| `GET /api/health` | Reports service, schema, and fixture mode |
| `GET /api/samples` | Lists the canonical sample and aliased players |
| `POST /api/analyze` | Prepares a neutral packet or requests player selection |
| `POST /api/analyze-json` | Requires packet plus intent; returns packet plus card |

Bundled-sample preparation:

```json
{
  "sample_id": "fixture-mirage-01",
  "player": "PlayerA"
}
```

Post-intent analysis uses the checked-in
`backend/tests/fixtures/analyze_json_request.valid.json` request.

The API returns errors in one envelope:

```json
{
  "error": {
    "code": "CONTRACT_VALIDATION_FAILED",
    "message": "Request body does not match the RE:DECIDE API contract",
    "retryable": false,
    "decision_id": null
  }
}
```

## Deliberate limitations

- Uploaded-demo parsing and player discovery are not integrated.
- The fixture coach supports only the exact canonical packet.
- No live model provider or API key is used yet.
- `observed_action.evidence_ids` are traceability references represented in the
  UI through the neutral observed-action block in version `1.0`.
- Existing round-win models and simulator winner/final-state output are not
  decision-quality evidence and are not connected to this API.

See `Project_Context.md`, `INTEGRATION_STATUS.md`, and the applicable numbered
role brief before changing a component.
