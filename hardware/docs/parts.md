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
| 10 k 1206 | 16 | 30 | 14 |
| 120 R 1206 | 12 | 100 | 88 |
| 10 µF 1206 | 12 | 14 | 2 |
| XL-3216SURC red LED | 8 | 9 | 1 |
| 1 µF 1206 | 6 | 22 | 16 |
| 30 pF 1206 C0G | 6 | 12 | 6 |
| 4k7 1206 | 6 | 16 | 10 |
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
| **30 mΩ 1 % 1206 shunt** | 6 | The whole current-sense chain hangs off it. A 0 Ω jumper is a few milliohms of uncontrolled, badly tempco'd copper — it cannot stand in for a precision shunt. Keep the value at 30 mΩ: with the INA240A1's fixed 20 V/V it puts ±2 A at ±1.2 V around the 1.65 V mid-rail, which is the right span. |
| **N-channel MOSFET** (2N7002 SOT-23, or 2N7000 TO-92) | 1 | The kill line pulls the shared EN bus down to ground, which needs a low-side switch. The AO3481 on the shelf is P-channel — wrong polarity for the job, and the kill line is the one circuit that must not be improvised. |

## Changed to suit stock

| Was | Now | Reason |
|---|---|---|
| 220 R LED series (node) | **120 R** | Not in stock. At Vf 2.4 V on a 3.3 V rail, 120 R gives 7.5 mA — bright, inside the LED's 20 mA and inside what a G431 pin sources. This was the console's original choice too. |
| 470 R LED series (brain, 5 V) | **1 k** | 2.6 mA. 120 R here would draw 21.7 mA and exceed the LED's rating, because the 5 V rail leaves more headroom. |
| 220 R LED series (brain, 3V3) | **120 R** | Same as the node. |
| 100 R kill gate series | **120 R** | Not in stock, and the exact value is immaterial for a gate series resistor. |
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
- **SMT female header strip.** Every socket and header stayed through-hole, on
  the grounds that the driver module is plugged, unplugged and shaken on a
  moving joint. You will need through-hole female headers instead.
