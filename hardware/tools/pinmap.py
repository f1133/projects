#!/usr/bin/env python3
"""Derive the MCU pin map from the netlist and audit it for firmware.

The point is to answer two questions with the board as evidence rather than a
hand-kept table: is any pin asked to do two things, and is any signal the
firmware needs missing from the board?

What this can prove: what is wired where, that nothing is double-booked, and
that every function the design intends has a pin. What it cannot prove is that
a peripheral is genuinely available on that pin in silicon - that comes from
the datasheet's alternate-function table, and the entries below carry the AF
number so CubeMX can confirm each one. Chunk A4 is still A4.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import spec                                                   # noqa: E402

# pin -> (function, peripheral, alternate function, note)
INTENT = {
    "PA8":  ("PWM phase A", "TIM1_CH1", "AF6", ""),
    "PA9":  ("PWM phase B", "TIM1_CH2", "AF6", ""),
    "PA10": ("PWM phase C", "TIM1_CH3", "AF6", ""),
    "PB12": ("driver enable", "GPIO out", "-", "also the shared kill line"),
    "PB4":  ("driver fault in", "GPIO in", "-",
             "PB4 is NJTRST after reset; set SYS Debug to Serial Wire only"),
    "PA1":  ("phase A current", "ADC1_IN2", "analog", "injected group with PA3"),
    "PA3":  ("phase B current", "ADC1_IN4", "analog", "injected group with PA1"),
    "PA0":  ("motor NTC", "ADC1_IN1", "analog", ""),
    "PB0":  ("bus voltage", "ADC1_IN15", "analog",
             "console calls this IN12; confirm the channel number in CubeMX"),
    "PB6":  ("encoder clock", "I2C1_SCL", "AF4", ""),
    "PB7":  ("encoder data", "I2C1_SDA", "AF4", ""),
    "PB8":  ("CAN receive", "FDCAN1_RX", "AF9",
             "shares the pin with BOOT0 - see CONFLICT-2"),
    "PB9":  ("CAN transmit", "FDCAN1_TX", "AF9", ""),
    "PA5":  ("spare SPI clock", "SPI1_SCK", "AF5", "encoder/driver upgrade path"),
    "PA6":  ("spare SPI in", "SPI1_MISO", "AF5", ""),
    "PA7":  ("spare SPI out", "SPI1_MOSI", "AF5", ""),
    "PA4":  ("spare SPI select", "SPI1_NSS", "AF5", "or drive as plain GPIO"),
    "PB13": ("node address 0", "GPIO in", "-", "internal pull-up, jumper to GND"),
    "PB14": ("node address 1", "GPIO in", "-", ""),
    "PB15": ("node address 2", "GPIO in", "-", ""),
    "PC13": ("status LED", "GPIO out", "-", "7.5 mA through 120 R"),
    "PA13": ("debug data", "SWDIO", "AF0", ""),
    "PA14": ("debug clock", "SWCLK", "AF0", ""),
    "PF0":  ("crystal in", "RCC_OSC_IN", "-", "8 MHz, needed for CAN bit timing"),
    "PF1":  ("crystal out", "RCC_OSC_OUT", "-", ""),
    "PG10": ("reset", "NRST", "-", "pin 7; KiCad names it PG10"),
}

POWER = {"VDD", "VSS", "VDDA", "VSSA", "VBAT", "VREF+"}


def audit():
    nets_of = {}
    for net, conns in spec.ACTUATOR_NETS.items():
        for ref, pin in conns:
            if ref == "U1":
                nets_of.setdefault(pin, []).append(net)

    problems, rows = [], []
    for pin, nets in sorted(nets_of.items()):
        if pin.rstrip("*") in POWER or pin in POWER:
            continue
        if len(nets) > 1:
            problems.append(f"{pin} is on {len(nets)} nets: {', '.join(nets)}")
        intent = INTENT.get(pin)
        if not intent:
            problems.append(f"{pin} is wired to {nets[0]} but has no declared "
                            f"firmware function")
            continue
        rows.append((pin, nets[0], *intent))

    for pin in sorted(INTENT):
        if pin not in nets_of:
            problems.append(f"{pin} has a declared function "
                            f"({INTENT[pin][0]}) but is not wired on the board")

    # peripherals must not be claimed twice
    periph = {}
    for pin, _net, _fn, per, _af, _n in rows:
        # GPIO is not an exclusive resource - any number of pins can be one.
        # Only a specific peripheral instance+channel can be double-claimed.
        if per.startswith("GPIO") or per in ("-",) or "_" not in per:
            continue
        periph.setdefault(per, []).append(pin)
    for per, pins in periph.items():
        if len(pins) > 1:
            problems.append(f"{per} is claimed by {', '.join(pins)}")
    return rows, problems, periph


if __name__ == "__main__":
    rows, problems, periph = audit()
    print(f"{len(rows)} signal pins wired on the MCU\n")
    print(f"{'pin':<6}{'net':<14}{'function':<22}{'peripheral':<14}{'AF':<8}note")
    print("-" * 104)
    for pin, net, fn, per, af, note in rows:
        print(f"{pin:<6}{net:<14}{fn:<22}{per:<14}{af:<8}{note}")
    used = sorted({p.split('_')[0] for p in periph})
    print(f"\nperipherals used: {', '.join(used)}")
    if problems:
        print(f"\n{len(problems)} PROBLEM(S):")
        for p in problems:
            print("  -", p)
        sys.exit(1)
    print("\nno pin serves two nets; no declared function is unwired")
