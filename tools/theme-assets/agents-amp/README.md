# Agents Amp status icon source

The four `monitor*.xpm` files are the original 16×16 pixel sources for the
Agents Amp status icons. They were created for this project and are licensed
under the repository's MIT License. They do not copy a third-party logo or
skin asset. Each state has a distinct screen glyph as well as its own color.

The runtime PNGs are nearest-neighbour 128×128 renders. Their screen color is:

- `good`: `#69E31C`
- `worried`: `#F2D15C`
- `critical`: `#FF4D6D`
- `dead`: `#8992AA`

`chrome-shell.svg` is the deterministic first-generation shell source retained
for provenance. The selected second-generation raster source is
`imagegen/device-shell-master-v1.png`; its runtime copy is
`assets/ui/chrome-shell-v2.png`. It is a 1360×1040 HiDPI shell with empty live
data apertures and exact 2× geometry for the 680×520 popup.

`imagegen/action-buttons-*-atlas-v1.png` are the transparent source atlases for
the four action buttons. Runtime files are cropped and resampled to the exact
2× actor sizes documented in `IMAGEGEN.md`. Labels, icons, focus state, values,
equalizer segments, scrolling content, and actions remain live UI widgets.

The raster artwork was generated specifically for this project. A classic
late-1990s media-player screenshot was used only as a palette and material
reference; no logo, name, character, music data, layout, or third-party pixels
were copied. The final prompts and exclusions are recorded in `IMAGEGEN.md`.
The source artwork license is stored separately in `LICENSE`.
