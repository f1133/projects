# g431-can-actuator

KiCad schematic for a CAN-FD actuator node built around the **STM32G431CBT6**
(Cortex-M4F, 170 MHz, 128 KB flash, LQFP-48). One board sits on each actuator
and drives its motor locally; the boards daisy-chain on a single CAN bus and
are addressed by a 4-bit DIP switch, so a chain of up to 16 actuators needs one
bus cable rather than one motor harness per joint.

Schematic only — there is no PCB layout yet. Before the PCB is ordered the node
is being built on perf board with modules; the plan, the three layouts (single
motor on a Black Pill, dual motor, bare G431 + SN65HVD230 CAN) and their
placement / wiring pictures live in [`proto/`](proto/README.md).

## Specification

| | |
|---|---|
| MCU | STM32G431CBT6, 170 MHz, 128 KB flash, 32 KB RAM, LQFP-48 |
| Supply | 9–18 V DC (12 V nominal), reverse-polarity and transient protected |
| Motor stage | DRV8311S — integrated three-phase bridge, 3–20 V, 5 A peak |
| Motor types | 3-phase BLDC/PMSM (FOC or six-step); a brushed DC actuator can use two of the three half-bridges |
| Current sensing | three driver-integrated sense amplifiers into ADC1 |
| Position feedback | Hall sensors (TIM3 Hall mode) or a quadrature encoder with index |
| Bus | FDCAN1 through a TJA1042T/3, split termination fitted only on end nodes |
| Node address | 4-bit DIP switch, 16 nodes per bus |
| Rails | 12 V → 5 V buck (TPS54233) → 3.3 V LDO (AP2112K) → ferrite-filtered 3.3 V analog |
| Debug | SWD + SWO header, 3.3 V debug UART, nine test points |

## Sheets

| Page | File | Contents |
|---|---|---|
| 1 | `g431-can-actuator.kicad_sch` | top level, four hierarchical sheets |
| 2 | `power.kicad_sch` | fuse, TVS, reverse-polarity FET, 5 V buck, 3.3 V LDO, analog rail, bus/board sensing |
| 3 | `mcu.kicad_sch` | STM32G431CBT6, decoupling, 8 MHz HSE, reset/boot, SWD, UART, node-address DIP, LEDs |
| 4 | `can.kicad_sch` | TJA1042T/3, NUP2105L clamp, split termination, daisy-chain connectors |
| 5 | `motor.kicad_sch` | DRV8311S, charge pump, bulk decoupling, phase outputs, feedback conditioning |

Cross-sheet nets use hierarchical labels; the top sheet joins matching sheet
pins by name instead of routing bundles across the page.

## Connectors

| Ref | Function | Pinout |
|---|---|---|
| J1 | Power in | 1 = VIN (9–18 V), 2 = GND |
| J2 / J3 | CAN daisy-chain (wired in parallel) | 1 = CANH, 2 = CANL, 3 = GND |
| J4 | SWD | 1 = 3V3, 2 = SWCLK, 3 = GND, 4 = SWDIO, 5 = NRST, 6 = SWO |
| J5 | Debug UART (3.3 V) | 1 = GND, 2 = TX, 3 = RX, 4 = 3V3 |
| J6 | Motor phases | 1 = A, 2 = B, 3 = C |
| J7 | Feedback | 1 = VCC (JP3-selected), 2 = GND, 3 = Hall A / ENC A, 4 = Hall B / ENC B, 5 = Hall C, 6 = index, 7 = NTC, 8 = GND |
| JP1 | Fit to force the ROM bootloader | |
| JP2 | Fit on the two end nodes for 120 Ω termination | |
| JP3 | Feedback supply: 1–2 = 5 V, 2–3 = 3.3 V | |

## Opening the project

Open `g431-can-actuator.kicad_pro` in KiCad 7 or later. Newer versions upgrade
the file format on first save. The three symbols the stock libraries do not
carry (`DRV8311S`, and the `VM` / `+3V3A` power symbols) live in
`lib/g431-can-actuator.kicad_sym`, registered through the project
`sym-lib-table`; every other symbol is a stock KiCad symbol embedded in the
sheets, so the project opens standalone.

## Regenerating and checking

The sheets were bootstrapped by a generator that is kept in the repository so
the design intent stays in one readable place:

```sh
./tools/build.sh          # regenerate, export netlist + PDF, rebuild the BOM, verify
```

`tools/check_netlist.py` compares the KiCad-exported netlist against a
hand-written table of the intended connectivity (`EXACT` / `CONTAINS`) rather
than against the generator, so a change that silently rewires the board fails
the check. It currently verifies 54 nets and asserts that no pin is left
floating except the LDO's `NC`.

Once you start editing in KiCad, the `.kicad_sch` files become the source of
truth — rerunning the generator would discard your edits.

## Design notes

**Reverse-polarity protection.** Q1 is a P-channel FET with its drain on the
supply and source on the load, gate pulled to ground through R1 and clamped by
a 15 V zener. Correct polarity enhances the FET and bypasses its body diode;
reversed polarity keeps Vgs at or above zero and reverse-biases the body diode,
so nothing conducts. D1 is a **bidirectional** TVS (SMBJ18CA) for the same
reason — a unidirectional part would conduct on a reversed input and dump the
fault current into the polyfuse.

**Supply headroom.** The DRV8311 is rated 20 V on VM. The SMBJ18CA clamps at
roughly 29 V at its full 600 W surge rating, so a long inductive supply lead
could briefly exceed the driver's rating. For installations with long supply
runs, fit a lower-clamping TVS or add series input inductance.

**Fault handling.** `DRV_nFAULT` drives `TIM1_BKIN`, so a driver fault forces
the PWM outputs to their inactive state in hardware before firmware runs.

**Feedback levels.** The Hall/encoder inputs are pulled up to 3.3 V through
2k2, so open-collector Hall sensors running from the 5 V on J7 pin 1 still
present a 3.3 V logic high. JP3 drops that supply to 3.3 V for push-pull
encoders that would otherwise over-drive the inputs. The 100 Ω / 1 nF networks
give roughly a 100 ns time constant; for a high line-count encoder at speed,
reduce the capacitors.

**Current-sense conditioning.** The 100 Ω / 1 nF networks on `SOA`–`SOC` are a
charge reservoir for the SAR sampling capacitor (≈1.6 MHz corner), not an
anti-alias filter — FOC samples synchronously with the PWM, so heavy filtering
would add phase lag to the current loop.

**Analog reference.** VDDA and VREF+ share a ferrite-filtered rail, tied back
to digital ground at a single point through R7. The driver's `CSAREF` is on the
digital 3.3 V rail instead, to keep the motor-side reference off the MCU's
analog rail; the resulting gain error is the ferrite's DC drop, under 0.1 %.

## Before committing to a PCB

- Recheck the TPS54233 compensation (R4/C7) and the 10 µH inductor against TI's
  design tool for the final output capacitance — the values here are a
  reasonable starting point, not a closed-loop-verified result.
- Confirm DRV8311S thermals at the intended continuous current; the WQFN-24
  needs a solid thermal pad and vias to carry anything near 5 A.
- Run ERC in the KiCad GUI. The netlist check here is thorough about
  connectivity, but KiCad 7's CLI has no ERC command, so the electrical-type
  rules have not been machine-checked.
- Confirm footprint choices against the parts actually being bought,
  particularly the DIP switch, terminal blocks and the electrolytics.

## Layout notes for whoever does the PCB

- Keep the DRV8311S power loop (VM bulk → bridge → PGND) tight; place C36/C37
  against the VM and PGND pins.
- Star the analog ground at R7 only; do not stitch GNDA to GND elsewhere.
- Route CANH/CANL as a differential pair from the transceiver to J2/J3, with
  the termination network and clamp close to the connectors.
- Keep the crystal loop small and guard it from the switch node of the buck.
