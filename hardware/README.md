# juno hardware

Two greenfield KiCad projects. Both are generated from the Juno build console
(`vendor/build_console.html`) — its Schematic tab defines the connectivity and
its BOM tab defines the parts.

| Project | Board | Role |
|---|---|---|
| `actuator-node/` | CAN bus actuator node, 70 x 60 mm | One per joint. Drives its motor locally, daisy-chains on CAN. |
| `main-brain/` | ESP32-S3 board, 170 x 100 mm | Main brain. Two I2C devices, two microphones on a shared clock, kill line, power chain. |

The head board is deliberately out of scope for now.

## Relationship to the perf-board work

None. This is greenfield. The perf-board prototypes and the schematic-only
project on `claude/stm32g431-kicad-schematic-3e1o5o` (SimpleFOC Mini + ACS712 +
LD1117 on stripboard) are a separate lineage and are not a source for these
boards. Where the two disagree, the build console wins.

## Status

Both projects are complete through schematic, footprint placement, netclasses
and design rules, with no copper routed. `tools/check.py` verifies 296 pad nets
and 296 schematic stubs against the spec, that every part belongs to exactly one
functional group, that pinned parts and proximity constraints hold, and that no
courtyards collide.

Placement is by functional block: each block keeps its own passives, and parts
with an electrical reason to hug another are held against it and checked. See
`placement.svg` in each project for the colour-coded map.

ERC and DRC have **not** been run: KiCad was not available where these were
generated. Each project README lists what to check before ordering; the module
footprints are the highest-risk item in both.

## Board-level decisions

- **Everything is on-board except the FOC driver.** The SimpleFOC Mini mounts on
  female headers; the board carries its mating footprint, not its circuitry.
- **Encoders are motor-mounted.** Each board exposes a 4-pin header for the
  encoder cable rather than carrying an encoder.
- **No routing.** Both projects ship with symbols, footprints, netlist, board
  outline, placement, netclasses and design rules complete. Copper routing is
  done by hand in KiCad afterwards.

## Fabrication

The node board goes to **Lion Circuits, 2-layer, 1.6 mm, 1 oz copper**, and the
project is pre-set to emit the Protel-extension Gerber names their sample set
uses. JLCPCB remains the fallback and the rules clear both. See
[`docs/fabrication.md`](docs/fabrication.md) for the comparison, and for the
case where home etching still makes sense (it does not, for these boards).

Design rules are set for comfortable hand-routing and hand-soldering, and sit
well inside either fab's cheapest tier:

| Rule | Value |
|---|---|
| Track, signal | 0.25 mm |
| Clearance | 0.2 mm |
| Via | 0.6 mm pad / 0.3 mm drill |
| Edge clearance | 0.5 mm |
| Silkscreen | 0.15 mm min width, 1 mm min text |

Track widths by netclass are sized from IPC-2221 for 1 oz outer copper at a
10 °C rise: 0.25 mm ≈ 0.9 A, 1.0 mm ≈ 2.4 A, 1.5 mm ≈ 3.2 A (the motor
netclass), 2.0 mm ≈ 4.0 A (the 19 V netclass).
Motor and VIN widths are set from the current figures in the build console.

## What the node can do

[`docs/capabilities.md`](docs/capabilities.md) is the specification: bus range,
torque and current resolution, loop rates, CAN bandwidth against three joints,
thermals, and an explicit list of what the board cannot do.
[`docs/pinmap.md`](docs/pinmap.md) is the MCU pin map, generated from the
netlist, with the three traps that will bite firmware.

`actuator-node/views/` holds rendered assembly images — top, bottom, copper and
a zoom on the driver and MCU — with silkscreen, designators and dimensions.

## Verification

KiCad is not installed in the environment these projects were generated in, so
ERC and DRC have **not** been run. Every emitted file is round-trip parsed with
`kiutils` as a syntax gate, and the netlist is checked against the build console
by script — but open both projects in KiCad and run ERC and DRC before ordering.
