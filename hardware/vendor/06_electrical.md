# Electrical

## STM32G431CBT6 node — collision-free, 18 pins

| Pin | Function |
|---|---|
| PA8 / PA9 / PA10 | TIM1 CH1/2/3, phase PWM |
| PB12 | driver EN |
| PA1 / PA3 | ADC1, INA240 outputs |
| PB6 / PB7 | I2C1 SCL / SDA, AS5600 |
| PB8 / PB9 | FDCAN1 RX / TX |
| PB0 | Vbus divider, ADC1_IN12 |
| PA0 | motor NTC, ADC1_IN1 |
| PB13 / PB14 / PB15 | node ID solder jumpers |
| PA13 / PA14 | SWDIO / SWCLK |
| PC13 | status LED |

## ESP32-S3 Super Mini — brain

| GPIO | Function |
|---|---|
| 1 | spare |
| 2 | I2S DIN, both mics |
| 3 | **leave free**, strapping pin |
| 4 | I2S DOUT, speaker amp |
| 5 / 6 | UART or CAN to the nodes |
| 7 | kill line → 2N7000 |
| 8 / 9 | I2C SDA / SCL |
| 10 / 11 / 12 | spare (SD card if wanted) |
| 13 | ToF INT |
| 43 / 44 | I2S BCLK / WS |
| 48 | onboard LED |

## ESP32-C3 Super Mini — head, CAN node 4

| GPIO | Function |
|---|---|
| 0 / 1 | pan / tilt servo |
| 4 / 5 / 6 | TFT SCK / MOSI / DC |
| 7 | WS2812 ear LEDs |
| 3 | CAN TX |
| 10 | CAN RX |
| 20 / 21 | I2C to the depth imager |
| 2, 8, 9 | **leave free — boot straps** |

The C3 has a TWAI controller, so it joins the CAN bus directly with nothing but
a transceiver. Keep CAN off GPIO 2, 8 and 9: GPIO 9 low at reset means download
mode, and a transceiver RX pin reads a dominant bus bit as a low. That failure
only appears when you hot-plug the head onto a busy bus, which is the normal way
to plug it in.

Two pins freed by: **TFT CS tied to ground** (only device on that SPI bus) and
**RST on a 10 k + 100 nF RC** instead of a driven pin.

## Node board — 50 × 45 mm, one copper layer

**Copper side, faces air:** G431, two INA240, two shunts, CAN transceiver,
AMS1117, all 1206 passives, the 470 µF SMD can, and the Mini on sockets.

**Plain side, faces the motor:** AS5600 soldered through at the exact board
centre, and all four connectors — but only in the corners, outside the Ø48
gearbox circle, where there is unlimited height. Under the circle there is
5.5 mm and nothing but the encoder fits.

### Ports

| Port | Pins | Signals |
|---|---|---|
| SWD | 5 pads | 3V3, SWDIO, SWCLK, **NRST**, GND |
| CAN in | XH 5 | CANH, CANL, EN, 5 V, GND |
| CAN ext | XH 5 | identical, wired in parallel |
| Phases | XH 3 | A, B, C |
| Power | VH 2 | 19 V, GND |

NRST is the pin people skip and regret. Without it the ST-Link cannot do
connect-under-reset, and firmware that disables SWD early bricks the chip.

## Power tree

```
19 V 65 W laptop brick
  └─ barrel jack + P-mosfet reverse protection
       ├─ 19 V bus ──┬─ node 1  (470 µF local)
       │             ├─ node 2  (470 µF local)
       │             └─ node 3  (470 µF local)
       └─ MP1584 ──── 5 V ──┬─ ESP32-S3, speaker amp
                             ├─ harness to each node → AMS1117 → 3.3 V
                             └─ head flange → C3 + servos (470 µF local)
```

**Star ground at the barrel jack.** Every motor return goes back there
independently. Daisy-chaining puts one motor's current across another's shunt.

## Wiring rules

- Twist SDA with its own ground return, SCL with its own. Two pairs, not one bundle
- Same for CANH / CANL
- 2.2 kΩ I2C pull-ups at the master end only
- 120 Ω termination at the two physical ends of the CAN bus only. Every node has
  a jumper; close it on the last one
- Kelvin taps soldered to the shunt's own end caps, not to the trace. At 30 mΩ,
  20 mm of copper is a 5% error
- Motor phases are the aggressor, not the victim. They can be loose

## Design rules for toner transfer

| Setting | Value |
|---|---|
| Trace / clearance | 0.5 mm, 0.4 mm in the LQFP fanout |
| Power trace | 3.0 mm for 19 V, 2.0 mm for 5 V |
| Hole | 0.9 mm headers, 1.2 mm JST |
| Annular ring | 0.4 mm |
| Jumpers | 8 planned, expect 12, stop at 15 |

**No jumper may cross under the LQFP.** If you need one there, the CubeMX pin
assignment is wrong.
