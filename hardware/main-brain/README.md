# main-brain

ESP32-S3 controller for the base. Two I2C devices, two microphones on a shared
clock, the hardware kill line and the power chain — everything that does not
move. 140 x 70 mm.

Generated from the Juno build console's base wiring. Schematic and PCB are
complete through placement, netclasses and design rules. **No copper is
routed.**

## Why the board is this wide

The microphones set it. A6 and A7 sit at x = 5 mm and x = 135 mm, exactly
130 mm apart, because that spacing is what turns two microphones into a
bearing. Both share BCLK and WS and both drive the same data pin; A6 has L/R
tied low and A7 tied high, and that is what makes them stereo.

## Before you route

**The ESP32-S3 Super Mini footprint is unverified.** External sources for this
board were unreachable from the environment this was generated in, so
`ESP32_S3_LEFT` / `ESP32_S3_RIGHT` in `tools/modules.py` hold the conventional
2 x 11 Super Mini arrangement and nothing stronger. Check it against your actual
board before ordering. The schematic is correct regardless — nets are by pin
name — so if the order is wrong, correcting those two lists and re-running
`build.py` is the whole fix. Same applies to the MP1584EN, the mic breakouts and
the I2C modules, though those are more standard.

## One part added beyond the console BOM

**D1, a 10 V zener, plus R6.** The console specifies an SI2301-class P-MOSFET
for reverse-polarity protection straight off a 19 V input. That part is rated
around ±8 V gate-source, so an unclamped gate destroys it on first power-up.
R6 pulls the gate down and D1 clamps Vgs. Without these the protection circuit
is the thing that fails.

## One thing worth changing, not changed

The kill line works by pulling the shared EN wire low with Q2, while each node's
PB12 drives that same wire high push-pull. Killing therefore shorts three MCU
outputs to ground through Q2 — within ratings (about 60 mA total, Q2 handles
200 mA) but poor practice, and the node cannot tell it has been killed.

Two clean fixes: a series resistor between PB12 and the EN net on each node
board, or drive PB12 open-drain in firmware. It is left as the console
specifies because changing it is a design decision, not a transcription.

## Pin assignment

Follows `06_electrical.md`. GPIO 3 is left free as a strapping pin. CAN is on
GPIO 5/6 — the docs say "UART or CAN" without saying which is TX, so TX is 5 and
RX is 6; the TWAI controller maps to any GPIO, so swap in firmware if needed.

| GPIO | Use |
|---|---|
| 2 | I2S DIN, both mics |
| 4 | I2S DOUT, to the speaker amp on J4 |
| 5 / 6 | CAN TX / RX |
| 7 | kill line to Q2 |
| 8 / 9 | I2C SDA / SCL |
| 13 | ToF INT |
| 43 / 44 | I2S BCLK / WS |

I2C pull-ups (R1, R2, 2k2) are here and only here — the master end, as the
wiring rules require.

## Ports

| Ref | Port | Pins |
|---|---|---|
| J1 | 19 V barrel jack | star ground lands here |
| J2 | CAN + power to the arm | CANH, CANL, EN, 5 V, GND |
| J3 | 19 V to the arm | +19 V, GND |
| J4 | I2S to the speaker amp | 5 V, GND, DOUT, BCLK, WS |

J4 exists because GPIO 4 is assigned to a speaker amp that the BOM places in the
head while also saying it shares the mic I2S bus — and I2S does not travel over
CAN. The header puts the signal somewhere real; where the amp physically lives
is your call.

## Verification status

ERC and DRC have **not** been run. `tools/check.py` verifies 96 pad nets, 96
schematic stubs against their pin endpoints, courtyard collisions and the board
outline, and every file round-trips through `kiutils`. Run ERC and DRC locally
before ordering.
