# rdr-item-filter-gimp
`rdr-item-filter-gimp` is a GIMP 3 plugin that applies a Red Dead-style item render look to a selected layer.

It gives you a quick, repeatable pipeline for stylized item images with adjustable controls.

## What It Does
When you run the filter, it opens a settings window with sliders for the core look controls (saturation, exposure, black point, cartoon intensity/radius, and shadow settings).

After you confirm, it applies the effect pipeline in order:
1. Tone and stylization filters (saturation, exposure, cartoon filter)
2. Grayscale-copy mask creation and mask apply (for clean alpha shaping)
3. Drop shadow as the final pass

This keeps the output clean while still allowing fast artistic tweaks.

## Installation (GIMP 3)
1. Close GIMP if it is running.
2. Copy this plugin folder into your GIMP user plug-ins path in `%appdata%`:
	`C:\Users\<YourUser>\AppData\Roaming\GIMP\3.0\plug-ins\`
3. Ensure the final structure looks like this:
	`...\plug-ins\rdr-item-style-once\rdr_item_img_once.py`
	`...\plug-ins\rdr-item-style-once\rdr-item-style-once.py`
4. Start GIMP.
5. Open an image and select a layer (must have a transparent and alpha channel).
6. Then navigate and apply filter through menu:
	`Filters > Artistic > RDR Item Style Once`

## Notes
- Designed for GIMP 3.0 and up.
- The filter runs on the currently selected drawable/layer.
- If the menu entry does not appear, restart GIMP after confirming files are in the correct plug-ins folder.
