# Public replay visualization fixtures

`mirage-showcase.replay.json` is a sanitized `replay_visualization_v1`
fixture extracted from the private `fut-vs-the-mongolz-m2-mirage.dem` record.
It was selected from the available replay database for its combination of:

- 30 rounds and 10 players;
- broad Mirage radar coverage;
- 211 kills, 756 damage events, and 24 bomb events; and
- complete, in-bounds `X`, `Y`, and `Z` player snapshots.

The fixture replaces Steam IDs and player names with stable anonymous IDs and
display names. It also removes inventory and parser-only fields while retaining
the round boundaries, positions, health, armor, side, alive state, named map
areas, and normalized events needed by the replay UI.

Render it with the browser asset at `frontend/public/radars/de_mirage.png` and
the matching normalized transform in `data/public/radar-info/catalog.json`.

The original full-resolution replay database remains private at
`data/private/processed/full_replays.jsonl` and is intentionally ignored by
Git.

`inferno-processed.replay.json` is the unmodified public
`replay_visualization_v1` shape emitted by the backend for a 29-round Inferno
replay. Unlike the sanitized Mirage fixture, its snapshots retain the backend's
`name` and `player_name` fields and omit `alive` when the parser does not return
it. The browser adapter associates snapshots with the stable top-level player
records by their unique display names and derives alive state from health only
when the field is absent.

`inferno-processed.analysis.json` is the matching validated
`replay_pipeline_v1` result for the Inferno save. It contains saved coaching for
flameZ at the round-one damage event on tick 2579. The Mirage save has no
matching analysis artifact. The selector reports analysis availability
independently from visualization availability because they remain separate
backend contracts.
