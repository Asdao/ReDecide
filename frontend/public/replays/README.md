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
