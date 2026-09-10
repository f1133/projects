# Requirements

What the gearbox has to do, and where each number came from. Anything still
marked open is a placeholder in `config/gearbox.toml`, not a decision.

> The upstream spec is Juno's `03_mechanical/V2_SPEC.md`. This document records
> what that spec has to satisfy; where the two disagree, the spec wins.

## Context

Three CAN joint nodes drive a desk robot arm. Each node is a self-contained
board — STM32G431, SimpleFOC Mini, AS5600 — bolted to one actuator, and each
actuator needs one gearbox. The electronics are specified in the project's
BOM spreadsheet (CAN joint node, rev 14); this document covers only what that
BOM implies for the mechanics, plus the gaps it leaves.

## Fixed by the electronics

| Requirement | Value | Source |
|---|---|---|
| Outside diameter | Ø48 mm | The 50 × 45 mm node board overhangs the gearbox by ~9.6 mm |
| Motor torque | 0.06 N·m | 2804 gimbal at the driver's ceiling |
| Peak phase current | 2.5 A | DRV8313 on the SimpleFOC Mini |
| Current sense range | ±2.75 A | INA240A1 with a 30 mΩ shunt — saturates before the driver does |
| Bus voltage | 19 V | 65 W laptop brick, fixed output |
| Wiring path | through the joint | 22 AWG power and 28 AWG signal run down the hollow shafts |
| Quantity | 3 | one per node |

The current ceiling matters more than the motor: whatever the motor is rated
for, the gearbox never sees more than 2.5 A of phase current, so peak torque is
`Kt × 2.5 × ratio × efficiency` and nothing else.

## Chosen

| Requirement | Value | Why |
|---|---|---|
| Architecture | single-stage cycloidal | 15:1 in one stage inside Ø48; tolerant of shock loads |
| Reduction | 15:1 | 16 ring pins, 15 lobes; 0.06 → 0.68 N·m |
| Eccentricity | 0.80 mm | K = 0.674, matching two builds known to print and work |
| Discs | 1 | half the moving parts, no indexing step, 51 → 44 mm |
| Axial length | ≤ 44 mm | the spec's Z stack |

## Open

These block a final design, not a first one. Each has a placeholder in the
config so the tooling runs; none of the placeholders should be trusted.

1. **The output holes break out of the disc** and this blocks printing. Three
   of six holes cut through the rim by 0.75 mm at the drawn phase, and rotating
   the pattern cannot fix it. See the design log for the 688ZZ remedy.
2. **Kt is inferred, not measured.** Juno's `CLAUDE.md` gives 0.06 N·m for a
   2804, which at the 2.5 A driver ceiling is `Kt = 0.024 N·m/A`. Every load
   here scales with it. Confirm against the real motor.
3. **Does the shaft protrude below the stator?** Juno's own first question, and
   it decides whether the 17 mm board stack works at all. Not a gearbox
   question, but it gates the whole actuator.
4. **Cam screw pattern, M2 or M2.5.** Gates the cam and the housing.
5. **Does the split ring flex 0.5 mm without cracking?** Untested. The tuning
   procedure that replaces the reprint loop depends on it.
6. **Duty cycle.** Continuous current is set by the stator thermistor, which is
   in the winding but has no calibration yet.

## Not requirements

Backlash is not specified. A pin-and-hole cycloidal drive has backlash from
the pin and hole fits, and `profile_offset_mm` exists to tune it, but no target
has been set because nothing in the arm yet needs one.
