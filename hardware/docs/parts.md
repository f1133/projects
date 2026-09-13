# Parts: what the design uses, against what is on the shelf

Both boards are designed around the stock actually in hand. Where the original
BOM called for a value that is not there, the design changed rather than the
order — every passive below is covered by existing stock except two items that
have no substitute.

Quantities are for **three actuator nodes plus one main brain**.

## Covered by stock

| Value | Needed | Have | Spare |
|---|---|---|---|
| 100 nF 1206 | 43 | 50 | 7 |
| 10 k 1206 | 19 | 30 | 11 |
| 120 R 1206 | 12 | 100 | 88 |
| 10 µF 1206 | 12 | 14 | 2 |
| XL-3216SURC red LED | 8 | 9 | 1 |
| 1 µF 1206 | 6 | 22 | 16 |
| 30 pF 1206 C0G | 6 | 12 | 6 |
| 4k7 1206 | 3 | 16 | 13 |
| INA240A1D | 6 | 8 | 2 |
| 100 k 1206 | 5 | 13 | 8 |
| 470 µF 50 V | 4 | 6 | 2 |
| SN65HVD230 | 4 | 4 | **0** |
| 8 MHz HC-49S SMD | 3 | 6 | 3 |
| AMS1117-3.3 | 3 | 5 | 2 |
| 2k2 1206 | 2 | 100 | 98 |
| AO3481 P-FET | 1 | 2 | 1 |
| 1 k 1206 | 1 | 16 | 15 |

**The transceiver has no margin.** Four parts, four sockets, none spare — and
the head board, which is out of scope here, needs a fifth. Worth adding a few
to the next order before one gets cooked.

## Must order — no substitute exists

| Part | Qty | Why nothing in stock works |
|---|---|---|
| **30 mΩ 1 % 1206 shunt** | 6 | The whole current-sense chain hangs off it. A 0 Ω jumper is a few milliohms of uncontrolled, badly tempco'd copper — it cannot stand in for a precision shunt. Keep the value at 30 mΩ: with the INA240A1's fixed 20 V/V it puts ±2 A at ±1.2 V around the 1.65 V mid-rail, and saturates at ±2.75 A — just past the driver's own 2.5 A peak, which is where you want the measurement to give out. |
| **5 pin JST-XH male right angle** | 2 more | Seven are needed (CAN in and CAN ext on three nodes, plus the brain's outgoing port) and five are on the shelf. See the connector table below. |
| **JST-XH female crimp contacts** | ~40 more | Ten in stock against roughly fifty needed once the CAN, phase and NTC looms are counted. These are the cheapest part in the project and the one most likely to stop a build night. |

## Connectors, against the order

Board-side counts are for **three nodes plus one brain**; cable-side counts
assume a CAN chain of three segments (brain → node 1 → node 2 → node 3) and a
19 V loom that fans out from the brain.

| Board-side part | Where | Need | Have | |
|---|---|---|---|---|
| 3 pin JST-XH male RA | node J1 phases, J7 NTC | 6 | 10 | ✅ |
| 5 pin JST-XH male RA | node J2/J3 CAN, brain J2 | 7 | 5 | ❌ **short 2** |
| 2 pin JST-VH male RA | node J4 19 V, brain J3 | 4 | 10 | ✅ |
| 2.54 mm male header, pins | node J5 SWD (5), J6 encoder (4), J8 SPI (6), brain J4 (5) | 50 | strip stock | ✅ |
| 2.54 mm female header, pins | the A1 driver socket, 15 per node | 45 | strip stock | ✅ |
| Barrel jack PJ-102AH | brain J1 | 1 | — | order |

| Cable-side part | Need | Have | |
|---|---|---|---|
| 5 pin XH female housing | 6 (3 segments × 2 ends) | 5 loose + 1 ready-made double-ended lead | ✅ |
| 3 pin XH female housing | 6 (3 phase + 3 NTC) | 5 loose + 1 ready-made lead | ✅ exactly |
| 2 pin VH female housing | 4 (one brain end, three node ends) | 5 loose + 1 ready-made lead | ✅ |
| **XH female crimp contacts** | ~48 | 10 | ❌ **short ~38** |
| VH female crimp contacts | 8 | 10 | ✅ |

**About the pitch.** The order calls the XH parts "2.54 mm"; genuine JST XH is
2.50 mm, and "XH2.54" is simply what the part is sold as almost everywhere.
The projects use KiCad's real 2.50 mm XH footprints. Across five ways the
cumulative difference is 0.16 mm against 0.36 mm of slop between a 0.64 mm pin
and a 1.0 mm hole, so it seats either way. Nothing to change.

**The female strip in this order is SMT.** Use the through-hole female headers
you have separately for the A1 socket — the driver module gets plugged,
unplugged and shaken on a moving joint, and SMT sockets peel.

**The 19 V bus has no pass-through on the node.** J4 is an input only, so the
motor supply fans out from the brain's single J3 rather than daisy-chaining the
way CAN does. That is a star distribution, which is the better arrangement
anyway — no node carries another node's motor current — but it does mean the
19 V loom is a Y-splitter and not a chain.

**The NTC in the order is the right one.** MF52E103FL395 is 10 kΩ at 25 °C with
B ≈ 3950 in a 1 mm bead, which fits inside a stator winding. Against the 4k7
pull-up on R5 it reads 2.24 V at 25 °C, 0.70 V at 80 °C and 0.42 V at 100 °C —
about 170 ADC counts per 10 °C in the range where a motor is actually at risk.

## Changed to suit stock

| Was | Now | Reason |
|---|---|---|
| 220 R LED series (node) | **120 R** | Not in stock. At Vf 2.4 V on a 3.3 V rail, 120 R gives 7.5 mA — bright, inside the LED's 20 mA and inside what a G431 pin sources. This was the console's original choice too. |
| 470 R LED series (brain, 5 V) | **1 k** | 2.6 mA. 120 R here would draw 21.7 mA and exceed the LED's rating, because the 5 V rail leaves more headroom. |
| 220 R LED series (brain, 3V3) | **120 R** | Same as the node. |
| 4k7 Vbus divider bottom | **10 k** | Not a stock problem - a range problem. 100 k / 4k7 puts the 19 V bus at 0.85 V, a quarter of the ADC's span, and wastes the rest on voltages the rail never reaches. 100 k / 10 k reads 1.73 V at 19 V and clips at 36 V, so half the ADC range covers the rail that exists. 10 k is on the shelf either way. |
| 100 R kill gate series | **120 R** | Not in stock, and the exact value is immaterial for a gate series resistor. |
| 2N7002 N-FET (kill line) | **AO3400A** | The kill line needs a low-side switch and the AO3481 on the shelf is P-channel. AO3400A is the N-channel part in the same SOT-23 outline: 30 V, 5.8 A, Vgs(th) 0.7 V, so it is fully enhanced from a 3.3 V GPIO with nothing between. |
| SI2301-class P-FET | **AO3481** | The part actually on hand: 30 V, 4.2 A, SOT-23. KiCad has no AO3481 symbol, so the projects use `AO3401A` — same family, same G/S/D pinout. |
| 10 V zener + 100 k | **100 k / 100 k divider** | No zener in stock. A 19 V input with the gate pulled to ground sits at the FET's gate-source limit, so the gate is divided instead of clamped: R9 source-to-gate and R6 gate-to-ground give Vgs ≈ −9.5 V, which enhances the FET hard and stays far inside its rating. Two resistors that are on the shelf, replacing one part that is not. |

## In stock, now unused

- **0 Ω jumpers, 44.** Bought for single-layer crossovers. The boards are
  2-layer, so nothing needs them. Keep them if you might ever revert to
  hand-etching.
- **CD43 3.3 µH 1 A inductor, 4.** Nothing in either board needs an inductor —
  the only regulator on the node is an LDO, and the brain's buck is a module
  with its own. The one place it could go, an LC filter on the node's incoming
  5 V, resonates at about 28 kHz with the existing 10 µF and would sit right on
  top of the motor PWM, amplifying the noise it was added to remove. Damping it
  needs roughly 1 Ω in series, which is not in stock either. Leave it out.
- **SMT female header strip, 3 × 1×40.** Every socket and header in both
  projects is through-hole, for the reason above. These stay in the drawer.
- **Single-sided copper clad, 4 × 76 × 100 mm.** The node is 70 × 60 mm so it
  would fit the blank, but both boards are 2-layer with a ground pour on the
  back — there is no single-sided version of this design to etch.
