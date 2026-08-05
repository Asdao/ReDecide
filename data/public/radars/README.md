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

The remaining PNGs are an unfiltered source catalog for maps not currently
represented by the replay database. Their original suffixes are retained
because some maps have multiple PSD/TGA-derived variants at different sizes.

Use `../radar-info/catalog.json` instead of inferring transforms, layers, or
filenames in frontend code. Radar images are Valve game assets; confirm the
intended redistribution terms and preserve appropriate attribution before
publishing them.
