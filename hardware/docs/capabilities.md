# What the actuator node can actually do

Numbers below are derived from the design as built — the netlist in
`tools/spec.py`, the netclasses in `tools/kigen.py`, and the part values on the
board. Where a figure depends on the motor rather than the board, it says so.
Where I am estimating rather than computing, it says that too.

---

## 1. Power

| | |
|---|---|
| Bus voltage, designed | **19 V** (laptop brick, via J4) |
| Bus voltage, usable | **8 – 36 V** |
| What sets the ceiling | The Vbus divider. 100k / 10k puts 36.3 V at the ADC's 3.3 V full scale; above that the firmware is blind to its own bus. C19 is a 50 V part and the DRV8313 goes to 60 V, so 36 V is a firmware limit, not a smoke limit. |
| What sets the floor | DRV8313 UVLO at 8 V |
| Logic rail | 3.3 V from U6 (AMS1117), fed by the **5 V that arrives on the CAN harness** — not from the 19 V |
| Logic current | ~80 mA: STM32 at 170 MHz ≈ 40 mA, SN65HVD230 ≈ 10 mA, AS5600 ≈ 7 mA, two LEDs at 7.5 mA |
| LDO dissipation | (5 − 3.3) × 80 mA = **0.14 W**, ~8 °C rise in SOT-223. Cold. |

**Consequence worth knowing:** a node with 19 V but no 5 V has a dead MCU and a
live bridge input; a node with 5 V but no 19 V runs, talks on CAN, and reports
its own bus as zero. The second case is the useful one for bench work — you can
flash and talk to a joint with no motor supply connected at all.

**No reverse-polarity protection on this board.** The brain board has the
high-side FET; the actuator node does not. 19 V backwards kills C19 and the
driver module. Key the J4 cable or check it twice.

## 2. Torque, current and what you can measure

The current sense is the part of this board that earns its existence.

| | |
|---|---|
| Topology | **Inline phase sensing** — shunt in the wire between the module output and J1, not in the low-side leg |
| Shunt | 30 mΩ, 1206 (ERJ8CWFR030V), 0.5 W |
| Amplifier | INA240A1, gain 20 V/V, ±80 V common mode, biased to mid-rail so it reads both directions |
| Full scale | **±2.75 A** per phase |
| Resolution | 3.3 V / 4096 ÷ (20 × 0.030 Ω) = **1.34 mA per LSB** |
| Shunt dissipation | 0.09 W at 1.75 A RMS, 0.23 W at full scale — under half the rating |
| Phases sensed | A and B; C is inferred as −(A+B), which is exact for a wye motor with no neutral |

**Why inline matters.** Low-side sensing only sees current while the low-side
FET is on, so it goes blind as duty approaches 100 % — exactly where a joint
holding against gravity lives. Inline sensing across a shunt that swings the
full 19 V PWM waveform is valid at any duty, including 0 % and 100 %. That is
what the INA240's ±80 V common mode and its PWM-rejection front end are for,
and it is the difference between guessing torque from applied voltage and
measuring it.

**What that buys, in robot terms:** torque control, impedance/compliance
control, gravity compensation, collision detection by current, and
force-feedback teleoperation. All four need a current number you can trust.

### Translated to the joint

With the 2804 and the 15:1 cycloid at 75 % efficiency the console's own figure
is **0.7 N·m at the output**, from 0.06 N·m at the motor.

- 1.34 mA/LSB → roughly **0.9 mN·m of torque quantisation at the joint output**
- Expect a few LSB of PWM-synchronous noise in practice, so plan on
  **3 – 5 mN·m of usable torque resolution** — about 0.5 % of full output torque
- Sense full scale (±2.75 A) sits above the driver's own 2.5 A peak, so the
  measurement never saturates before the hardware does. That is deliberate.

## 3. Drive

The DRV8313 on the SimpleFOC Mini, not the carrier, sets these.

| | |
|---|---|
| Peak | 2.5 A per half bridge |
| RMS, datasheet | 1.75 A |
| RMS, honest | **~1 A continuous, still air.** Roughly 1.5 W of conduction loss at 1 A across three phases, on a module with no heatsink. More with airflow. |
| PWM | TIM1, three single-ended inputs, internal dead time |
| PWM frequency | 15 – 40 kHz sensible; DRV8313 is good past 100 kHz |
| Duty resolution | 11.7 bits at 25 kHz (170 MHz / 2 / 25 kHz = 3400 counts, centre-aligned) |
| Protection | Overcurrent, thermal shutdown, UVLO, `nFAULT` back to PB4 |
| Fail-safe | R7 holds `EN` low, so the bridge is off whenever the MCU is unpowered or in reset |

**Trace capacity is not the limit.** Phase traces are a 1.5 mm netclass —
about 3.2 A at a 10 °C rise on 1 oz outer copper (IPC-2221), 4.4 A at 20 °C.
The 19 V feed is 2.0 mm, about 4.0 A. Both are well clear of the module.

**The heat is all on the module.** Because the Mini plugs into sockets and
stands 8.5 mm off the board, the one part that gets hot is the one part you can
pull and replace without a soldering iron. The carrier's own losses are the LDO
(0.14 W) and two shunts (0.09 W each). Nothing else on this board warms up.

## 4. Sensing and control loops

| | |
|---|---|
| Encoder | AS5600, motor-mounted, I²C on J6 (3V3 / GND / SCL / SDA) |
| Resolution at the motor | 12 bit, 4096 counts/rev, 0.088° |
| Resolution at the joint | ×15 → 61 440 counts/rev = **0.0059° = 21 arcsec** |
| Accuracy at the joint | ~**2 arcmin**, limited by the AS5600's own ±0.5° INL, not by the gearing |
| I²C read cost | ~112 µs for a 2-byte angle at 400 kHz → **~5 kHz practical position loop** |
| Current loop | Runs at the PWM rate, 20 – 25 kHz on a 170 MHz G431 with injected ADC |
| Electrical pole | ~900 Hz (≈2 mH / 11 Ω), so a 1 – 2 kHz current loop is achievable |

**The encoder is the bottleneck, and J8 is the exit.** The I²C read is what
caps the position loop at a few kHz. The SPI header breaks out SPI1 (SCK, MISO,
MOSI, CS on PA5/6/7/4) so an AS5047P or MA732 can replace the AS5600 — a 3 µs
read at 10 MHz instead of 112 µs, which lets the position loop run at the PWM
rate. Same header also takes an SPI-configured driver if the Mini is ever
outgrown.

**ADC note for firmware:** both phase currents currently sit on ADC1 (IN2 and
IN4), so they are converted ~320 ns apart — 0.8 % of a 25 kHz period, which is
negligible. If you want them sampled at the same instant, PA1 also reaches
ADC2, so one phase per ADC in dual simultaneous mode works; confirm the channel
in CubeMX before committing.

## 5. The bus

| | |
|---|---|
| Controller | FDCAN1 on the STM32G431 |
| Transceiver | SN65HVD230, 3.3 V, rated to **1 Mbit/s** |
| Timing reference | 8 MHz crystal — the internal HSI16's ±1 % blows CAN's ±0.5 % budget, which is the whole reason Y1 exists |
| Termination | JP1, solder jumper — close it on the two physical ends of the chain only |
| Addressing | JP2/JP3/JP4 = 3 bits = **8 node addresses**, read on PB13/14/15 |
| Topology | J2 and J3 are wired straight through, so the chain enters one edge and leaves the other |

**Classical CAN at 1 Mbit/s is the honest spec.** The G431's FDCAN core will do
a 5 Mbit/s data phase, but the SN65HVD230 is a classical transceiver spec'd to
1 Mbit/s; CAN-FD data rates above that are out of spec for it. If you want real
FD later, swap U2 for a TCAN332 or MCP2562FD — same SOIC-8, same pinout.

**What that means for update rate.** An 11-bit ID frame with 8 data bytes is
about 135 µs at 1 Mbit/s including stuffing and the interframe gap. For three
joints:

- one broadcast command frame + three feedback frames = 540 µs
- at **1 kHz** that is **54 % bus load** — workable, with headroom for faults
- at **500 Hz**, 27 % — comfortable, and the sane place to start

So: **1 kHz joint-level command and feedback across three nodes**, with the
20 kHz current loop and ~5 kHz position loop running locally on each node. That
is the right division of labour — the bus carries setpoints, not PWM.

## 6. Mechanical and fabrication

| | |
|---|---|
| Board | 70 × 60 mm, 2 layers, 1.6 mm FR4, 1 oz copper |
| Mounting | 4 × M3 on 63 × 53 mm centres |
| Rear clearance | Ø48 mm circle centred on the board is the gearbox; rear protrusion must stay under 5.5 mm |
| Rear protrusion, actual | Everything is front-mounted; through-hole legs and fillets protrude ~1.5 mm. Comfortably inside. |
| Ports | All eight on the perimeter |
| Minimum feature | 0.25 mm track, 0.2 mm clearance — well inside Lion Circuits' capability |

**Port layout follows the cable runs.** The two CAN connectors sit on opposite
edges so a harness enters left and leaves right. Everything that goes to the
motor — phases, stator NTC, encoder, and the SPI upgrade header — clusters on
the bottom edge so one loom leaves in one direction. Power and SWD take the top.

## 7. What it cannot do

Stated plainly, because knowing the edges is most of the value:

- **No regen path.** Decelerating a geared load pumps the bus; C19's 85 mJ
  absorbs a little and nothing else does. Hard stops from speed under load will
  raise the rail. Watch `VBUS_SENSE` for it.
- **No hall inputs.** FOC is encoder-based. If the encoder cable falls off mid
  move, the node has no fallback commutation.
- **No independent high/low-side PWM.** The DRV8313 takes IN1/2/3 with internal
  dead time, so exotic modulation schemes and active freewheeling are off the
  table. Standard SVPWM is fine.
- **No isolation on CAN**, no common-mode choke, no bus fault protection beyond
  the transceiver's own. A shared ground fault propagates.
- **No fuse and no reverse-polarity FET** on the 19 V input.
- **No driver temperature sense.** The NTC is in the stator; the module's own
  thermal state reaches you only as `nFAULT` after it has already shut down.
- **Not safety-rated.** There is no redundant disable path, no watchdog output,
  no STO. The kill line lives on the brain board.

## 8. Where this sits as an actuator driver

It is a **quasi-direct-drive joint controller for a small arm**: 0.7 N·m at the
output, 21 arcsec of position resolution, true phase-current measurement, and
one CAN cable daisy-chaining the joints.

That combination — geared-but-backdrivable mechanics plus real current sense —
is what puts it in the same family as the ODrive/moteus/MIT-Cheetah style of
actuator rather than the hobby-servo family. You can command torque directly,
so you get:

- impedance and admittance control, and therefore a joint that is safe to bump
  into
- collision detection from current alone, with no extra sensor
- gravity compensation from a model plus measured current
- kinesthetic teaching: back-drive the arm by hand and record the trajectory
- force-feedback teleoperation, one node per joint

What it is not: a high-speed spindle drive, a >36 V drive, a >2 A drive, or
anything that needs a safety rating. For a three-joint desk arm at 19 V, it is
sized correctly — the sense chain reaches past the driver's limits, the traces
reach past the sense chain, and the only hot part unplugs.
