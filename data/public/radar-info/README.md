# CS2 radar overview metadata

The `.txt` files are the original Valve overview descriptions. They contain
world-coordinate origins, scale, rotation, zoom, landmark positions, insets,
and—where applicable—vertical radar sections.

`catalog.json` normalizes the seven maps represented in the current replay
database into a frontend-friendly contract. Each entry contains:

- the world-to-radar transform;
- matching radar image paths and dimensions;
- optional spawn, bomb-site, zoom, rotation, and inset metadata;
- layer altitude ranges, including Nuke's default and lower floors; and
- SHA-256 hashes for the source overview and radar images.

For a world position `(X, Y)`, maps without an additional rotation convention
use the following pixel transform:

```text
radar_x = (X - pos_x) / scale
radar_y = (pos_y - Y) / scale
```

Use a player's `Z` value and the catalog altitude ranges to choose the active
floor. At a shared boundary, prefer the default layer; for Nuke this means
`Z >= -495` uses `default` and `Z < -495` uses `lower`. Keep the raw `.txt`
files alongside the normalized catalog so future metadata fields can be
recovered without redownloading the game assets.
