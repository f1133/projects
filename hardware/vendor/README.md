# vendor

Source files that the KiCad projects are generated from. These are inputs, not
outputs — nothing here is edited by the generators.

| File | Purpose | Present |
|---|---|---|
| `build_console.html` | Source of truth. Schematic tab defines connectivity; BOM tab defines parts. | yes |
| `06_electrical.md` | Pin assignment, ports, power tree, wiring rules. | yes |
| `simplefoc_mini_v1.json` | EasyEDA PCB export of the SimpleFOC Mini v1.0. Pad positions, sizes and drills are read from it at build time. | yes |
| `simplefoc_mini_v1_sch.json` | The matching schematic export. It is what resolves the PCB's anonymous `U1_nn` nets to real signals, and what proves the 3V3 pin is `V3P3OUT`, a regulator output. | yes |

## Still needed

The ESP32-S3 Super Mini pin order. No reachable source could confirm the
physical order of its 2 x 11 header, so `ESP32_S3_LEFT` / `ESP32_S3_RIGHT` in
`tools/modules.py` hold the conventional arrangement and nothing stronger.
A photo of the board, or its vendor pinout, closes this the same way the
EasyEDA export closed the driver module.

The schematic is correct regardless - nets are written by pin name - so a wrong
order is a footprint fix and a rebuild, not a rewire.

## A note on the step-mini exports

Two earlier exports named `simplefoc_stepmini` were supplied first and used to
build the original footprint. They are a different product — a quad
half-bridge with IN1–IN4 and four outputs — and have been removed. The giveaway
was the pin count: the real v1.0 has a 2 × 5 control header and three motor
pads, the step mini has six and five in its two rows and four outputs.
