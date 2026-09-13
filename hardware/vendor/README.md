# vendor

Source files that the KiCad projects are generated from. These are inputs, not
outputs — nothing here is edited by the generators.

| File | Purpose | Present |
|---|---|---|
| `build_console.html` | Source of truth. Schematic tab defines connectivity; BOM tab defines parts. | yes |
| `06_electrical.md` | Pin assignment, ports, power tree, wiring rules. | yes |
| `simplefoc_stepmini.json` | EasyEDA export of the driver module. Footprint geometry and pinout are read straight from it at build time. | yes |

## Still needed

The ESP32-S3 Super Mini pin order. No reachable source could confirm the
physical order of its 2 x 11 header, so `ESP32_S3_LEFT` / `ESP32_S3_RIGHT` in
`tools/modules.py` hold the conventional arrangement and nothing stronger.
A photo of the board, or its vendor pinout, closes this the same way the
EasyEDA export closed the driver module.

The schematic is correct regardless - nets are written by pin name - so a wrong
order is a footprint fix and a rebuild, not a rewire.
