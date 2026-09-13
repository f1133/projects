# juno hardware

Two greenfield KiCad projects. Both are generated from the Juno build console
(`vendor/build_console.html`) — its Schematic tab defines the connectivity and
its BOM tab defines the parts.

| Project | Board | Role |
|---|---|---|
| `actuator-node/` | CAN bus actuator node | One per joint. Drives its motor locally, daisy-chains on CAN. |
| `main-brain/` | ESP32-S3 board | Main brain. Two I2C devices, two microphones on a shared clock, kill line, power chain. |

The head board is deliberately out of scope for now.

## Relationship to the perf-board work

None. This is greenfield. The perf-board prototypes and the schematic-only
project on `claude/stm32g431-kicad-schematic-3e1o5o` (SimpleFOC Mini + ACS712 +
LD1117 on stripboard) are a separate lineage and are not a source for these
boards. Where the two disagree, the build console wins.

## Status

Both projects are complete through schematic, footprint placement, netclasses
and design rules, with no copper routed. `tools/check.py` verifies 268 pad nets
and 268 schematic stubs against the spec and finds no courtyard collisions.

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

Both boards target **JLCPCB, 2-layer, 1.6 mm, 1 oz copper**. See
[`docs/fabrication.md`](docs/fabrication.md) for why, and for the case where
home etching still makes sense.

Design rules are set for comfortable hand-routing and hand-soldering, and sit
well inside JLCPCB's cheapest tier:

| Rule | Value |
|---|---|
| Track, signal | 0.25 mm |
| Clearance | 0.2 mm |
| Via | 0.6 mm pad / 0.3 mm drill |
| Edge clearance | 0.5 mm |
| Silkscreen | 0.15 mm min width, 1 mm min text |

Track widths by netclass are sized from IPC-2221 for 1 oz outer copper at a
10 °C rise: 0.25 mm ≈ 0.9 A, 0.5 mm ≈ 1.5 A, 1.0 mm ≈ 2.4 A, 2.0 mm ≈ 4.0 A.
Motor and VIN widths are set from the current figures in the build console.

## Verification

KiCad is not installed in the environment these projects were generated in, so
ERC and DRC have **not** been run. Every emitted file is round-trip parsed with
`kiutils` as a syntax gate, and the netlist is checked against the build console
by script — but open both projects in KiCad and run ERC and DRC before ordering.
