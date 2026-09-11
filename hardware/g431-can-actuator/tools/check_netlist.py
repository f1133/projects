#!/usr/bin/env python3
"""Verify a KiCad-exported netlist against the intended connectivity.

The expectations below are written from the design intent (see
``docs/pin-assignment.md``), not derived from the generator, so this catches
a generator change that silently rewires the board.

    kicad-cli sch export netlist --output build/net.net g431-can-actuator.kicad_sch
    python3 tools/check_netlist.py build/net.net
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kisch import parse_sexp  # noqa: E402

# U3 = STM32G431CBT6, U5 = DRV8311S, U4 = TJA1042T/3, U1 = TPS54233,
# U2 = AP2112K-3.3.  Every net here must contain exactly these pins.
EXACT = {
    # TIM1 complementary PWM -> driver half-bridge inputs
    "PWM_AH": [("U3", "30"), ("U5", "15")],     # PA8  / TIM1_CH1  -> INHA
    "PWM_AL": [("U3", "27"), ("U5", "18")],     # PB13 / TIM1_CH1N -> INLA
    "PWM_BH": [("U3", "31"), ("U5", "14")],     # PA9  / TIM1_CH2  -> INHB
    "PWM_BL": [("U3", "28"), ("U5", "19")],     # PB14 / TIM1_CH2N -> INLB
    "PWM_CH": [("U3", "32"), ("U5", "13")],     # PA10 / TIM1_CH3  -> INHC
    "PWM_CL": [("U3", "29"), ("U5", "20")],     # PB15 / TIM1_CH3N -> INLC
    # SPI1 to the driver
    "DRV_SCLK": [("U3", "13"), ("U5", "23")],   # PA5  / SPI1_SCK
    "DRV_SDI":  [("U3", "15"), ("U5", "22")],   # PA7  / SPI1_MOSI
    "DRV_SDO":  [("U3", "14"), ("U5", "21")],   # PA6  / SPI1_MISO
    "DRV_nSCS": [("U3", "39"), ("U5", "24")],   # PA15 / GPIO
    # Fault trips TIM1 break input in hardware
    "DRV_nFAULT": [("U3", "26"), ("U5", "1"), ("R22", "2")],   # PB12 / TIM1_BKIN
    # FDCAN1
    "CAN_TX": [("U3", "34"), ("U4", "1")],      # PA12 -> TXD
    "CAN_RX": [("U3", "33"), ("U4", "4")],      # PA11 <- RXD
    "CAN_STB": [("U4", "8"), ("R19", "1")],
    # Analog inputs
    "I_SENSE_A": [("U3", "8"), ("R23", "2"), ("C38", "1")],    # PA0 / ADC1_IN1
    "I_SENSE_B": [("U3", "9"), ("R24", "2"), ("C39", "1")],    # PA1 / ADC1_IN2
    "I_SENSE_C": [("U3", "10"), ("R25", "2"), ("C40", "1")],   # PA2 / ADC1_IN3
    "VBUS_SENSE": [("U3", "11"), ("R8", "2"), ("R9", "1"), ("C17", "1")],
    "TEMP_MOTOR": [("U3", "12"), ("R35", "2"), ("C45", "1")],  # PA4 / ADC2_IN17
    "TEMP_BOARD": [("U3", "17"), ("R10", "2"), ("TH1", "1"), ("C18", "1")],
    # TIM3 Hall / encoder inputs
    "HALL_A": [("U3", "41"), ("R30", "2"), ("C41", "1")],      # PB4 / TIM3_CH1
    "HALL_B": [("U3", "42"), ("R31", "2"), ("C42", "1")],      # PB5 / TIM3_CH2
    "HALL_C": [("U3", "16"), ("R32", "2"), ("C43", "1")],      # PB0 / TIM3_CH3
    "ENC_Z":  [("U3", "43"), ("R33", "2"), ("C44", "1")],      # PB6 / EXTI6
    # Debug and boot
    "SWDIO": [("U3", "37"), ("J4", "4")],
    "SWCLK": [("U3", "38"), ("J4", "2")],
    "SWO":   [("U3", "40"), ("J4", "6")],
    "NRST":  [("U3", "7"), ("J4", "5"), ("C28", "1")],
    "BOOT0": [("U3", "45"), ("R12", "1"), ("JP1", "2")],
    "UART_TX": [("U3", "22"), ("J5", "2")],
    "UART_RX": [("U3", "25"), ("J5", "3")],
    "OSC_IN":  [("U3", "5"), ("Y1", "1"), ("C26", "1")],
    "OSC_OUT": [("U3", "6"), ("Y1", "3"), ("C27", "1")],
    # Driver support
    "CP":   [("U5", "6"), ("C32", "1")],
    "AVDD": [("U5", "17"), ("C33", "1")],
    # Buck converter
    "SW_5V": [("U1", "8"), ("L1", "1"), ("D3", "1"), ("C8", "2")],
    "BOOT":  [("U1", "1"), ("C8", "1")],
    "FB_5V": [("U1", "5"), ("R5", "2"), ("R6", "1")],
    "EN_5V": [("U1", "3"), ("R2", "2"), ("R3", "1")],
    # Input protection
    "VIN_F": [("F1", "2"), ("D1", "1"), ("Q1", "3")],
    "VGATE": [("Q1", "1"), ("R1", "1"), ("D2", "2")],
    # CAN split termination
    "TERM_H":   [("JP2", "2"), ("R20", "1")],
    "TERM_MID": [("R20", "2"), ("R21", "1"), ("C31", "1")],
}

# Rails carry many members; only the pins that must be on them are listed.
CONTAINS = {
    "+3V3":  [("U3", "1"), ("U3", "24"), ("U3", "36"), ("U3", "48"),
              ("U2", "5"), ("U4", "5"), ("U5", "2")],
    "+3V3A": [("U3", "20"), ("U3", "21"), ("FB1", "2")],
    "+5V":   [("U2", "1"), ("U2", "3"), ("U4", "3"), ("L1", "2")],
    "VM":    [("U1", "2"), ("U5", "7"), ("U5", "8"), ("Q1", "2"), ("C32", "2")],
    "GND":   [("U3", "23"), ("U3", "35"), ("U3", "47"), ("U1", "7"),
              ("U2", "2"), ("U4", "2"), ("U5", "9"), ("U5", "16"), ("U5", "25")],
    "GNDA":  [("U3", "19"), ("R7", "1")],
    "CANH":  [("U4", "7"), ("J2", "1"), ("J3", "1"), ("JP2", "1"), ("D7", "1")],
    "CANL":  [("U4", "6"), ("J2", "2"), ("J3", "2"), ("R21", "2"), ("D7", "2")],
    "PHASE_A": [("U5", "10"), ("J6", "1")],
    "PHASE_B": [("U5", "11"), ("J6", "2")],
    "PHASE_C": [("U5", "12"), ("J6", "3")],
}

# Pins that are deliberately left open.
ALLOWED_UNCONNECTED = {("U2", "4")}


def load(path):
    tree = parse_sexp(open(path, encoding="utf-8").read())
    nets, comps = {}, {}
    for top in tree:
        if not isinstance(top, list):
            continue
        if top[0] == "components":
            for c in top[1:]:
                ref = val = fp = None
                for f in c[1:]:
                    if isinstance(f, list) and f[0] == "ref":
                        ref = f[1]
                    elif isinstance(f, list) and f[0] == "value":
                        val = f[1]
                    elif isinstance(f, list) and f[0] == "footprint":
                        fp = f[1]
                comps[ref] = (val, fp)
        if top[0] == "nets":
            for n in top[1:]:
                name, members = None, []
                for f in n[1:]:
                    if isinstance(f, list) and f[0] == "name":
                        name = f[1]
                    elif isinstance(f, list) and f[0] == "node":
                        ref = pin = None
                        for g in f[1:]:
                            if g[0] == "ref":
                                ref = g[1]
                            elif g[0] == "pin":
                                pin = g[1]
                        members.append((ref, pin))
                nets[name] = sorted(members)
    return nets, comps


def short(name):
    return name.rsplit("/", 1)[-1]


def main(path):
    nets, comps = load(path)
    by_short = {}
    for name, members in nets.items():
        by_short.setdefault(short(name), []).extend(members)

    problems = []
    for net, want in EXACT.items():
        got = by_short.get(net)
        if got is None:
            problems.append(f"{net}: net does not exist")
            continue
        have, want = set(got), set(want)
        if have != want:
            if want - have:
                problems.append(f"{net}: missing {sorted(want - have)}")
            if have - want:
                problems.append(f"{net}: unexpected {sorted(have - want)}")
    for net, want in CONTAINS.items():
        got = by_short.get(net)
        if got is None:
            problems.append(f"{net}: net does not exist")
            continue
        missing = set(want) - set(got)
        if missing:
            problems.append(f"{net}: missing {sorted(missing)}")

    for name, members in nets.items():
        if len(members) < 2 and set(members) - ALLOWED_UNCONNECTED:
            problems.append(f"{name}: single-pin net {members}")

    checked = len(EXACT) + len(CONTAINS)
    print(f"{len(nets)} nets, {len(comps)} components, {checked} nets checked")
    if problems:
        print(f"\nFAILED ({len(problems)}):")
        for p in problems:
            print("   ", p)
        return 1
    print("netlist matches the intended connectivity")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "build/net.net"))
