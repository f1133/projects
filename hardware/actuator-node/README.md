# actuator-node

STM32G431CBT6 CAN-FD joint controller. One per joint; the boards daisy-chain on
a single CAN bus and are addressed by three solder jumpers. 70 x 60 mm.

Parts are placed by functional block - see `placement.svg` for the colour-coded
map. Each block keeps its own passives: the CAN transceiver with its
termination and decoupling, the crystal with its two load caps, each INA240
with its shunt, the LDO with its input and output caps. Parts with an
electrical reason to hug something else are placed against it rather than
merely in the same region, and `tools/check.py` enforces the distances - the
crystal is held within 12 mm of the MCU and its load caps within 9 mm of it.

Generated from the Juno build console. Schematic and PCB are complete through
placement, netclasses and design rules. **No copper is routed** — that is yours.

## Before you route: three things to check

**1. The driver module is measured, and it is A1, not M1.** Its footprint and
symbol are read at build time from the vendor's own EasyEDA exports in
`vendor/`: the PCB export gives pad positions, sizes and drills, and the
schematic export resolves that PCB's anonymous `U1_nn` nets to real signals.
19 pads — 15 pins plus 4 mounting holes — over 22.6 × 17.9 mm.

The reference is **A1** rather than M1, because the module's own silkscreen
calls its three motor pads M1/M2/M3 and `("M1", "M1")` in a netlist helps
nobody.

| Pin | Signal | Goes to | Pin | Signal | Goes to |
|---|---|---|---|---|---|
| 1 | EN | PB12, the kill line | 9 | GND | GND |
| 2 | IN3 | PA10, TIM1_CH3 | 10 | 3V3 | **nothing — see below** |
| 3 | IN2 | PA9, TIM1_CH2 | 11 | GND | GND |
| 4 | IN1 | PA8, TIM1_CH1 | 12 | VM | +19 V |
| 5 | GND | GND | 13 | M1 | phase A, through shunt R1 |
| 6 | nFlt | PB4 | 14 | M2 | phase B, through shunt R2 |
| 7 | nSlp | open | 15 | M3 | phase C |
| 8 | nRes | open | | | |

**2. Pin 10 is an output, and must stay unconnected.** The vendor schematic
shows it is DRV8313 pin 15, `V3P3OUT` — the driver's internal 3.3 V regulator.
An earlier revision of this project tied it to the carrier's 3.3 V rail on the
assumption it was a supply input, which would have connected the AMS1117's
output to the module's regulator. `tools/check.py` now fails the build if it
ever reappears on a net.

That same regulator feeds the module's own pull-ups on nSlp, nRes and nFlt,
which is why those three idle in the running state with nothing attached — the
driver comes out of sleep and reset by itself once VM is present.

**3. An earlier export was the wrong board.** The first EasyEDA file supplied
was a "step mini": a quad half-bridge with IN1–IN4 and four outputs. The board
on the bench is the SimpleFOC Mini v1.0 (DRV8313, three phases, dated 04/22),
and everything here is built from its export instead. The checker refuses any
net mentioning `IN4` or `OUT4` so the two cannot be confused again.

Still print the footprint at 1:1 and sit the real module on it before ordering.
Geometry is measured now rather than guessed, so this is a confirmation rather
than a discovery — but it is the one check that catches a mirrored footprint.

**2. The INA240 pinout.** The console and the KiCad symbol disagree: the console
says pin 1 IN+, pin 4 REF1, pin 7 NC; KiCad says pin 1 IN−, pin 4 GND, pin 7
REF1. This is resolved in KiCad's favour, because the console's pin numbers are
demonstrably unreliable (its MCU diagram gives both NRST and VSSA as pin 7) and
two independent sources corroborate pin 4 = GND and pin 7 = REF1. It matters:
taking the console's numbering would have driven the chip's ground pin to 3V3.
Worth one look at the datasheet, which you can open locally.

**3. BOOT0 does not exist as its own pin here.** On the LQFP-48 G431 it is
multiplexed onto PB8, which the pin assignment gives to FDCAN1_RX. The console's
MCU diagram draws a standalone BOOT0 pin with a pull-down; that pin is not on
the package. R6 is therefore a pull-down on PB8 itself.

By factory default `nBOOT_SEL = 1` and the pin is ignored, so this is latent
rather than broken. But if it is ever cleared, an idle (recessive) bus holds the
transceiver's R output high at reset and the part boots the ROM bootloader
instead of your firmware — the same hot-plug trap your own notes call out for
the C3's straps. FDCAN1 can move to PA11/PA12, which are otherwise unused, if
you want PB8 free. Settle it in CubeMX (chunk A4) before etching.

## Deviations from the console

| | |
|---|---|
| **Encoder** | Motor-mounted, so a 4-pin header (3V3 GND SCL SDA) at J6 replaces the AS5600 soldered through the board centre. |
| **Two layers, not one** | See `../docs/fabrication.md`. The 0 R crossover jumpers JP1–JP8 in the console BOM are not needed and are gone. |
| **470 µF moved** | The console puts it where the CAN-ext connector is; there they are on opposite faces, here both are front-side. |
| **LEDs** | Two, both XL-3216SURC red 1206 (the part you have). D1 is the status LED on PC13; D2 is new and reports the 3.3 V rail directly, so a dead board tells you whether the LDO is up before firmware is involved. Series resistors are 220 R: at Vf 2.4 V there is only 0.9 V of headroom on a 3.3 V rail, so the value sets the current sharply - 220 R gives about 4 mA, plenty for a 225 mcd part. |
| **Shunt sense polarity** | The console's drawing and its caption contradict each other. Taken as drawn: IN+ driver side, IN− motor side, so output rises above mid-rail for current flowing driver → motor. A firmware sign constant, not a wiring hazard. |

## Known tight spot

The gearbox leaves 5.5 mm of height over everything inside its circle, so the
four corners are the only places a connector fits — and the console already uses
all four. The encoder header (J6) and the NTC connector (J7) are new, and they
sit on the left and right edges at mid-height, the only other strip that clears
the circle. It is tight. If it fouls the gearbox in the flesh, the fixes are a
right-angle header, a JST-SH, or 2 mm more board.

Note also that the console labels the gearbox circle Ø48 but draws it at Ø43.6.
The keepout marked on `Cmts.User` follows the drawing, because that is what
makes the corner connectors clear it. Measure the real gearbox.

## Ports

| Ref | Port | Pins |
|---|---|---|
| J1 | Motor phases | A, B, C |
| J2 / J3 | CAN in / ext, in parallel | CANH, CANL, EN, 5 V, GND |
| J4 | 19 V in | +19 V, GND |
| J5 | SWD | 3V3, SWDIO, SWCLK, NRST, GND |
| J6 | Encoder | 3V3, GND, SCL, SDA |
| J7 | Motor NTC | two wires from inside the stator |

NRST is on the header deliberately. Without it the ST-Link cannot do
connect-under-reset, and firmware that disables SWD early bricks the chip.

## Verification status

ERC and DRC have **not** been run — KiCad was not available in the environment
this was generated in. What has been checked, by `tools/check.py`:

- every pad's net matches the spec, 172 of them;
- every schematic stub actually touches its pin's connection point and carries
  the right label, so nothing looks connected while being open;
- no two courtyards overlap and everything is inside the outline;
- every file round-trips through `kiutils`.

Open it, run ERC and DRC, and expect one intentional courtyard note: the Mini
sits 8.5 mm above the MCU on headers, so its footprint deliberately has two
separate courtyards with the MCU in the gap.

## Regenerating

```sh
cd ../tools && KICAD_LIBS=<dir with kicad-symbols and kicad-footprints at 8.0.9> \
  python3 build.py && python3 check.py
```

Once you start editing in KiCad the `.kicad_*` files become the source of truth
and the generator is history. Until then, change `spec.py` rather than the
schematic — the checker verifies the board against it.
