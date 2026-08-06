# Public CS2 data

This directory contains data that is approved for redistribution or can be
downloaded from its recorded public source.  Check `source_manifest.json` and
the source license before publishing raw files.

The private data root is `../private/` and is intentionally ignored by Git.
It contains raw demos, parsed replay rows, SQLite databases, feature exports,
benchmark caches, and user uploads.

Public benchmark metadata is stored in `benchmark_manifest.json`; the actual
demo is referenced by a `private:` cache path and is downloaded locally by the
benchmark command.
