# vendor

Source files that the KiCad projects are generated from. These are inputs, not
outputs — nothing here is edited by the generators.

| File | Purpose | Present |
|---|---|---|
| `build_console.html` | Source of truth. Schematic tab defines connectivity; BOM tab defines parts. | yes |
| `06_electrical.md` | Pin assignment, ports, power tree, wiring rules. | yes |
| `SimpleFOC_Mini.kicad_sym` | Symbol for the SimpleFOC Mini, which mounts on female headers. | **no** |

## Still needed

`SimpleFOC_Mini.kicad_sym`, and a `.kicad_mod` for it if one exists. Neither
arrived, so `tools/modules.py` builds both from the pin list in the build
console. That gives correct pin names but guessed geometry - the header row
spacing in particular. Drop the real files here and re-run `tools/build.py`.

Until then, print `actuator-node/lib/juno.pretty/SimpleFOC_Mini_Socket.kicad_mod`
at 1:1 and check it against the module before ordering. The same applies to the
ESP32-S3 Super Mini footprint, whose pin order could not be verified from any
reachable source.
