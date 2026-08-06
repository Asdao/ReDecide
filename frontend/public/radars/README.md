# CS2 radar images

This directory contains top-down radar PNGs used to render replay positions.
The seven maps represented in the current replay database use concise names:

- `de_ancient.png`
- `de_anubis.png`
- `de_dust2.png`
- `de_inferno.png`
- `de_mirage.png`
- `de_nuke.png` and `de_nuke_lower.png`
- `de_overpass.png`

The remaining PNGs cover maps not currently represented by the replay
database. Filenames use the map name plus an explicit `_lower` or `_higher1`
suffix only when the image is a genuine vertical layer. Redundant PSD/TGA,
spectate, hashed, and version variants have been removed.

## Inventory summary

- 41 images across 36 map families;
- 31 images with fully transparent background pixels;
- 21 map families with matching overview metadata;
- 15 image-only map families that cannot yet place replay coordinates; and
- five retained secondary floor images: Baggage lower, Boulder higher, Nuke
  lower, Train lower, and Vertigo lower.

The image-only maps are `de_dogtown`, `de_edin`, `de_golden`, `de_grail`,
`de_jura`, `de_lake`, `de_memento`, `de_mills`, `de_palacio`, `de_palais`,
`de_rooftop`, `de_sugarcane`, `de_thera`, `de_transit`, and `de_whistle`.

Use `data/public/radar-info/catalog.json` instead of inferring transforms,
layers, or filenames in frontend code. Its image values are browser paths such
as `/radars/de_mirage.png`. Radar images are Valve game assets; confirm the
intended redistribution terms and preserve appropriate attribution before
publishing them.
