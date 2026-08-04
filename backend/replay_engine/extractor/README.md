# Replay extractor

Standalone ingestion and segmentation package for CS2 demo data. It is deliberately separate from `model/src/cs2_sim/core/model` so the analyzer can consume normalized replay data without owning parsing or storage.

## Pipeline

```text
CS2 .dem / sidecar JSON
        |
        v
  parse or load JSONL
        |
        v
  normalize canonical schema
        |
        v
  segment rounds/events/ticks/heatmap cells
        |
        v
  SQLite replay vault
```

The extractor keeps raw input immutable. The SQLite database is a queryable projection and can later be replaced with Parquet, DuckDB, or a hosted analytics store without changing the canonical record shape.

## Install

```powershell
python -m pip install -e extractor
```

The core package has no runtime dependencies. Native `.dem` parsing uses the optional Awpy extra:

```powershell
python -m pip install -e "extractor[full]"
```

## Usage

For application code, use the package-root facade. It keeps parser, schema, and
storage details behind one stable object:

```python
from replay_extractor import ExtractorConfig, ReplayExtractor

extractor = ReplayExtractor(ExtractorConfig(tick_interval=32))
replay = extractor.parse("match.dem")
segments = extractor.segment(replay)
```

Use `parse_batch()` and `ingest()` for directory and JSONL workflows. Their
typed results contain output paths, counts, and vault statistics. Catch
`ExtractorError` at application boundaries. See
[`docs/MODULE_API.md`](../docs/MODULE_API.md) for the complete contract.

Parse native demos into JSONL (Awpy required):

```powershell
python -m replay_extractor.cli parse `
  --input data\full\demos `
  --output extractor\vault\parsed.jsonl `
  --tick-interval 32
```

Materialize parsed JSONL into a segmented SQLite vault:

```powershell
python -m replay_extractor.cli ingest `
  --input extractor\vault\parsed.jsonl `
  --database extractor\vault\replays.sqlite
```

Inspect counts:

```powershell
python -m replay_extractor.cli stats `
  --database extractor\vault\replays.sqlite
```

## Data boundaries

- `extractor.py` reads `.dem` files or sidecar records and emits JSONL.
- `api.py` exposes the stable `ReplayExtractor` facade.
- `normalize.py` converts parser-specific fields into stable records.
- `segmenter.py` creates round, event, player-tick, and heatmap projections.
- `repository.py` owns SQLite persistence and bounded lookup queries.
- The analyzer/model layer should consume repository queries, not raw parser payloads.

The `vault/` directory is ignored by git. Keep original demos and credentials outside source control.
