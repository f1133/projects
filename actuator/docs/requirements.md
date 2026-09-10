# Requirements

What the gearbox has to do, and where each number came from. Anything still
marked open is a placeholder in `config/gearbox.toml`, not a decision.

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
| Architecture | single-stage cycloidal | 24:1 in one stage inside Ø48; tolerant of shock loads |
| Reduction | 24:1 | 25 ring pins, 24 lobes |
| Discs | 2, at 180° | cancels the orbiting imbalance, which a desk robot will otherwise transmit to the table |
| Axial length | ≤ 30 mm | provisional, pending the joint stack-up |

## Open

These block a final design, not a first one. Each has a placeholder in the
config so the tooling runs; none of the placeholders should be trusted.

1. **The motor.** Not on the electronics BOM — it is owned but unrecorded. Its
   torque constant sets every load in the gearbox, and the current placeholder
   (`Kt = 0.05 N·m/A`) is a guess. Needed: part number, Kv, outside diameter,
   shaft diameter and length.
2. **Disc material.** Contact stress rules out every common filament at the
   placeholder torque — see the design log. Whether the disc is printed or cut
   depends on the real Kt.
3. **Clear bore.** `required_bore_radius_mm = 3.5` is an estimate for the
   wiring. The eccentric cam wall eats into the bearing bore, so the true clear
   hole is smaller than the 9 mm bore radius the disc is drawn with.
4. **Output bearing.** Not yet sized; waits on the output flange.
5. **Duty cycle.** Continuous current is set by the stator thermistor, which is
   in the winding but has no calibration yet.

## Not requirements

Backlash is not specified. A pin-and-hole cycloidal drive has backlash from
the pin and hole fits, and `profile_offset_mm` exists to tune it, but no target
has been set because nothing in the arm yet needs one.
