# Public and private data layout

The analyser separates redistributable inputs from local or user-provided
replay data.

```text
data/
├── public/
│   ├── metadata/             # public Parquet metadata, subject to license
│   ├── processed/            # sanitized derived snapshots
│   ├── maps/                 # map layouts and overview assets
│   ├── benchmark_manifest.json
│   └── benchmark_evaluation.json
└── private/
    ├── raw_demos/            # .dem files and user uploads
    ├── processed/            # parsed JSONL and audits
    ├── databases/            # SQLite training stores
    ├── features/             # Parquet training exports
    ├── sidecars/
    └── benchmark_cache/
```

The roots default to `data/public` and `data/private`. They can be relocated
with `CS2_PUBLIC_DATA_ROOT` and `CS2_PRIVATE_DATA_ROOT`.

Run the migration from the repository root:

```powershell
$env:PYTHONPATH = "Noah/model/src;Noah/extractor/src;."
python -m Noah.training.migrate_data_layout
python -m Noah.training.migrate_data_layout --apply
```

The migration refuses to overwrite an existing destination and writes
`data/public/layout_manifest.json`. Private files are never included in a
public manifest by absolute machine path; benchmark references use the
portable `private:` prefix.

Public data should only be uploaded after checking its source license. A
public manifest and downloader are preferred when raw demo redistribution is
not permitted.
