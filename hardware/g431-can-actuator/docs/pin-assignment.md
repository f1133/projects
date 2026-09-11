# STM32G431CBT6 pin assignment

LQFP-48. Peripheral choices are driven by the motor-control requirement: one
advanced-control timer for the six PWM outputs, its break input wired to the
driver's fault pin, and the three phase currents on ADC channels that can be
sampled in sync with the PWM.

| Pin | Port | Net | Peripheral | Purpose |
|----:|------|-----|------------|---------|
| 1 | VBAT | `+3V3` | — | tied to VDD, no backup cell |
| 2 | PC13 | `ADDR0` | GPIO in | node address bit 0 |
| 3 | PC14 | `ADDR1` | GPIO in | node address bit 1 |
| 4 | PC15 | `ADDR2` | GPIO in | node address bit 2 |
| 5 | PF0 | `OSC_IN` | HSE | 8 MHz crystal |
| 6 | PF1 | `OSC_OUT` | HSE | 8 MHz crystal |
| 7 | PG10 | `NRST` | NRST | reset, 100 nF to GND |
| 8 | PA0 | `I_SENSE_A` | ADC1_IN1 | phase A current |
| 9 | PA1 | `I_SENSE_B` | ADC1_IN2 | phase B current |
| 10 | PA2 | `I_SENSE_C` | ADC1_IN3 | phase C current |
| 11 | PA3 | `VBUS_SENSE` | ADC1_IN4 | bus voltage, 100k/18k divider |
| 12 | PA4 | `TEMP_MOTOR` | ADC2_IN17 | motor NTC |
| 13 | PA5 | `DRV_SCLK` | SPI1_SCK | driver configuration |
| 14 | PA6 | `DRV_SDO` | SPI1_MISO | driver configuration |
| 15 | PA7 | `DRV_SDI` | SPI1_MOSI | driver configuration |
| 16 | PB0 | `HALL_C` | TIM3_CH3 | Hall C |
| 17 | PB1 | `TEMP_BOARD` | ADC1_IN12 | board NTC |
| 18 | PB2 | `ADDR3` | GPIO in | node address bit 3 |
| 19 | VSSA | `GNDA` | — | analog ground |
| 20 | VREF+ | `+3V3A` | — | ADC reference |
| 21 | VDDA | `+3V3A` | — | analog supply |
| 22 | PB10 | `UART_TX` | USART3_TX | debug console |
| 23 | VSS | `GND` | — | |
| 24 | VDD | `+3V3` | — | |
| 25 | PB11 | `UART_RX` | USART3_RX | debug console |
| 26 | PB12 | `DRV_nFAULT` | TIM1_BKIN | driver fault trips PWM in hardware |
| 27 | PB13 | `PWM_AL` | TIM1_CH1N | phase A low side |
| 28 | PB14 | `PWM_BL` | TIM1_CH2N | phase B low side |
| 29 | PB15 | `PWM_CL` | TIM1_CH3N | phase C low side |
| 30 | PA8 | `PWM_AH` | TIM1_CH1 | phase A high side |
| 31 | PA9 | `PWM_BH` | TIM1_CH2 | phase B high side |
| 32 | PA10 | `PWM_CH` | TIM1_CH3 | phase C high side |
| 33 | PA11 | `CAN_RX` | FDCAN1_RX | AF9 |
| 34 | PA12 | `CAN_TX` | FDCAN1_TX | AF9 |
| 35 | VSS | `GND` | — | |
| 36 | VDD | `+3V3` | — | |
| 37 | PA13 | `SWDIO` | SWD | |
| 38 | PA14 | `SWCLK` | SWD | |
| 39 | PA15 | `DRV_nSCS` | GPIO out | SPI chip select |
| 40 | PB3 | `SWO` | TRACESWO | |
| 41 | PB4 | `HALL_A` | TIM3_CH1 | Hall A / encoder A |
| 42 | PB5 | `HALL_B` | TIM3_CH2 | Hall B / encoder B |
| 43 | PB6 | `ENC_Z` | GPIO / EXTI6 | encoder index |
| 44 | PB7 | `LED_RUN` | GPIO out | green status LED |
| 45 | PB8 | `BOOT0` | BOOT0 | 10k pull-down, JP1 forces bootloader |
| 46 | PB9 | `LED_FAULT` | GPIO out | red fault LED |
| 47 | VSS | `GND` | — | |
| 48 | VDD | `+3V3` | — | |

## Why these peripherals

**TIM1** is the only advanced-control timer with three complementary outputs
plus a break input, so the six gate signals and the hardware fault trip all
come from one timer. `DRV_nFAULT` lands on `PB12`/`TIM1_BKIN` rather than a
plain GPIO so a driver fault shuts the bridge down without waiting for
firmware.

**TIM3** carries the three Hall inputs on `CH1..CH3`, which is the
configuration the XOR/Hall-interface mode needs. The same `CH1`/`CH2` pins work
as a quadrature encoder pair, with the index on `PB6` as an external interrupt.

**ADC1** takes the three phase currents and the bus voltage on `IN1..IN4`, so
an injected sequence triggered from TIM1 can sample all of them in the same
PWM window. The two thermistors sit on slower channels (`ADC1_IN12`,
`ADC2_IN17`).

**FDCAN1** uses `PA11`/`PA12`. These double as USB D-/D+; USB is not fitted, so
the pins are free.

## Free pins

None. All 38 I/O are assigned. If a function has to be dropped to free pins,
the debug UART (`PB10`/`PB11`) and the fault LED (`PB9`) are the least
load-bearing, followed by `SWO` (`PB3`).
