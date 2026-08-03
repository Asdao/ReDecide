"""Command line entrypoint for the standalone replay extractor."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .extractor import load_jsonl, parse_directory
from .normalize import normalize_record
from .repository import ReplayRepository
from .segmenter import segment_replay


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    parse = commands.add_parser("parse", help="parse native .dem files into JSONL")
    parse.add_argument("--input", type=Path, required=True)
    parse.add_argument("--output", type=Path, required=True)
    parse.add_argument("--tick-interval", type=int, default=32)
    parse.add_argument("--no-sidecar-fallback", action="store_true")

    ingest = commands.add_parser("ingest", help="normalize JSONL and write the segmented SQLite vault")
    ingest.add_argument("--input", type=Path, required=True)
    ingest.add_argument("--database", type=Path, required=True)
    ingest.add_argument("--heatmap-cell-size", type=int, default=256)

    stats = commands.add_parser("stats", help="show vault row counts")
    stats.add_argument("--database", type=Path, required=True)

    args = parser.parse_args()
    if args.command == "parse":
        count, fallback = parse_directory(
            args.input,
            args.output,
            tick_interval=args.tick_interval,
            sidecar_fallback=not args.no_sidecar_fallback,
        )
        print(json.dumps({"parsed": count, "sidecar_fallback": fallback, "output": str(args.output)}))
        return 0
    repository = ReplayRepository(args.database)
    try:
        if args.command == "ingest":
            count = 0
            for raw in load_jsonl(args.input):
                repository.write(segment_replay(normalize_record(raw), heatmap_cell_size=args.heatmap_cell_size))
                count += 1
            print(json.dumps({"ingested": count, "stats": repository.stats()}))
        else:
            print(json.dumps(repository.stats()))
    finally:
        repository.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
