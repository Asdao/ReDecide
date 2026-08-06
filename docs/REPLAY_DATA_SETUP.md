# Replay maps and demo data

The replay engine already provides bounded, checksum-aware downloaders. Use
the wrapper below from WSL after activating the project Python environment:

```bash
cd /mnt/c/Users/n8469/PycharmProjects/GHackathon
source /home/<user>/.virtualenvs/GHackathon1/bin/activate
bash scripts/download-replay-assets.sh --help
```

The wrapper calls the canonical modules in
`backend/replay_engine/training/`; it does not maintain a second downloader or
rewrite their lock/manifest logic.

## Download map assets

The default map set is the current competitive map set:

```bash
bash scripts/download-replay-assets.sh maps
```

Download selected maps only:

```bash
bash scripts/download-replay-assets.sh maps --maps de_mirage de_nuke
```

Assets are written to `data/public/maps` by default. Set
`CS2_PUBLIC_DATA_ROOT` to place public assets elsewhere. The map downloader
records source URLs, patch, and SHA-256 checksums in `manifest.json`.

## Download dataset metadata

Metadata is small and is required before selecting quality-filtered sidecars:

```bash
bash scripts/download-replay-assets.sh metadata --max-gb 1
```

Metadata is written to `data/public/metadata` by default.

## Download processed replay sidecars

Sidecars are analysis JSON files selected by map and quality filters. They are
safer for deterministic development than downloading native demos:

```bash
bash scripts/download-replay-assets.sh sidecars --max-files 100 --max-gb 0.25
```

Sidecars are written to `data/private/sidecars` by default. Use
`CS2_PRIVATE_DATA_ROOT` to place private data on another disk.

## Download raw demo files

Raw `.dem` files are downloaded only when explicitly named. The downloader
enforces a cumulative byte budget and rejects unsafe repository paths:

```bash
bash scripts/download-replay-assets.sh demos \
  --file demos/shard-example/match/map.dem \
  --output data/private/raw_demos \
  --max-gb 1
```

You can provide multiple `--file` arguments. Do not attempt to download the
whole dataset by default: it may be large, and the dataset maintainer's source
and tournament terms must be checked before redistributing raw demos.

## Reproducible subsets

After downloading a known subset, create a checksum manifest:

```bash
python -m backend.replay_engine.training.download_dataset lock \
  --input data/private/sidecars \
  --output data/private/sidecars_manifest.json \
  --revision main
```

On another machine, reproduce and verify it:

```bash
python -m backend.replay_engine.training.download_dataset locked \
  --manifest data/private/sidecars_manifest.json \
  --output data/private/sidecars

python -m backend.replay_engine.training.download_dataset verify \
  --manifest data/private/sidecars_manifest.json \
  --input data/private/sidecars
```

The `data/private/` and runtime data roots are ignored by Git. Keep manifests
outside those roots, or add them deliberately when a reproducible benchmark
requires a checked-in manifest.
