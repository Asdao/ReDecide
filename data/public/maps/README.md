# CS2 map assets

These assets are kept separate from replay data and model artifacts. They are
the seven maps present in the current replay database:

`de_ancient`, `de_anubis`, `de_dust2`, `de_inferno`, `de_mirage`, `de_nuke`,
and `de_overpass`.

Each map directory contains:

- an Awpy-parsed navigation mesh (`.json`), useful for coordinate-to-area
  lookup; and
- a radar overview (`.png`) for visualisation.

Nuke also includes `de_nuke_lower.png` for the lower level.

`manifest.json` records the Awpy patch, source URLs, and SHA-256 checksums.
Recreate or refresh the folder with:

```powershell
$env:PYTHONPATH = "src"
python -m training.download_maps --output data/maps
```

The current public location is `data/public/maps`:

```powershell
python -m training.download_maps --output data/public/maps
```
