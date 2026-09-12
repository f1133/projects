#!/usr/bin/env python3
"""Perf-board layouts for the actuator-node prototypes (10 x 15 cm, 38 x 58 holes).

L1  single motor  - STM32F401 Black Pill + SimpleFOC Mini + 2x ACS712 + AS5600
L2  dual motor    - Black Pill + 2x SimpleFOC Mini + 2x AS5600 (+ ACS712 pairs)
L3  target        - bare STM32G431CBT6 on a LQFP48->DIP adapter + SN65HVD230 CAN

Run:  python3 layouts.py [outdir]
"""

import os
import sys

from perfboard import (Design, fp_acs712, fp_axial, fp_blackpill, fp_ceramic, fp_crystal,
                       fp_diode, fp_dip, fp_dip_switch4, fp_header, fp_led, fp_point,
                       fp_qfp48_adapter, fp_radial, fp_sfmini, fp_tactile, fp_terminal,
                       fp_to220, write_outputs)

COLS, ROWS = 38, 58          # 10 x 15 cm double-sided perf board


# --------------------------------------------------------------------------
# shared building blocks
# --------------------------------------------------------------------------

def power_section(d, gnd_bus, bp_diode=True, divider="right", vm_start=10, bus_5v=None):
    """12 V in -> PTC -> series Schottky -> VM bus; 7805 -> 5 V bus; VBUS divider.

    Rows 3-12.  VM bus = bare wire on row 7 (cols vm_start-23), 5 V bus = row 7
    (cols 25-36), GND bus = row 9 across the board (part of ``gnd_bus``).
    """
    d.add("J1", fp_terminal("terminal 2 pos 5.08 mm", 2, names=["+", "-"]), (3, 4),
          value="12 V IN", note="screw terminal, 5.08 mm pitch (sits on the 0.1 in grid)")
    d.add("F1", fp_radial("radial PTC, 5 mm lead spacing", 2, dia=7.5, cls="protection"), (8, 4),
          value="PTC 1.1 A", note="resettable fuse e.g. MF-R110 (or a 2 A fuse holder)")
    d.add("D1", fp_diode("axial DO-201, 12.7 mm span", 5), (17, 4), rot=180,
          value="1N5822", note="reverse-polarity protection, 3 A Schottky (SB540/SB560 ok)")
    d.add("C1", fp_radial("radial 10 mm, 5 mm lead spacing", 2, dia=10.0, polarized=True),
          (11, 7), rot=90, value="470u 25V", note="bulk cap for the motor driver (polymer or electrolytic)")
    d.add("D2", fp_diode("axial DO-201, 12.7 mm span", 5), (14, 8), value="1.5KE22CA",
          note="bidirectional TVS across VM (optional on a bench supply)")
    d.add("C2", fp_ceramic("ceramic, 5.08 mm span", 2), (21, 7), rot=90, value="100n",
          note="7805 input decoupling")
    d.add("U2", fp_to220("TO-220 upright + clip-on heatsink", names=("IN", "GND", "OUT")), (23, 7),
          value="L7805CV", note=("5 V for the ACS712s and the Black Pill; ~0.7 W -> small heatsink"
                                 if bp_diode else
                                 "5 V for the ACS712s and the 3.3 V regulator; ~0.7 W -> small heatsink"))
    d.add("C3", fp_radial("radial 8 mm, 3.5-5 mm lead spacing", 2, dia=8.0, polarized=True),
          (28, 7), rot=90, value="100u 16V", note="7805 output cap (polymer ok)")
    d.add("C4", fp_ceramic("ceramic, 5.08 mm span", 2), (31, 7), rot=90, value="100n",
          note="7805 output decoupling")
    if bp_diode:
        d.add("D3", fp_diode("axial DO-41, 10.16 mm span", 4), (36, 11), rot=270, value="1N5819",
              note="5 V bus -> Black Pill 5V pin; keeps the 7805 from back-feeding a USB host")
    if divider == "right":
        r4_at, r5_at = (10, 11), (14, 12)
    else:
        r4_at, r5_at = (3, 11), (7, 12)
    d.add("R4", fp_axial("axial 1/4 W, 10.16 mm span", 4), r4_at, value="100k",
          note="VBUS sense divider, top")
    d.add("R5", fp_axial("axial 1/4 W, 10.16 mm span", 4), r5_at, value="15k",
          note="VBUS sense divider, bottom (12 V -> 1.57 V, 24 V -> 3.13 V)")

    d.net("VIN_RAW", "VM", ("J1", "+"), ("F1", "1"))
    d.net("VIN_F", "VM", ("F1", "2"), ("D1", "A"))
    d.net("VM", "VM", ("D1", "K"), ("C1", "+"), ("D2", "K"), ("C2", "1"), ("U2", "IN"), ("R4", "1"),
          bus=[(vm_start, 7), (23, 7)])
    d.net("+5V", "5V", ("U2", "OUT"), ("C3", "+"), ("C4", "1"), bus=bus_5v or [(25, 7), (36, 7)])
    if bp_diode:
        d.net("+5V", "5V", ("D3", "A"))
    d.net("GND", "GND", ("J1", "-"), ("C1", "-"), ("D2", "A"), ("C2", "2"), ("U2", "GND"),
          ("C3", "-"), ("C4", "2"), ("R5", "2"), bus=gnd_bus)
    d.net("VBUS_SENSE", "SENSE", ("R4", "2"), ("R5", "1"))


def blackpill(d):
    d.add("U1", fp_blackpill("WeAct Black Pill V3.0 on 2x 1x20 female headers"), (3, 14),
          value="STM32F401CCU6", note="USB-C DFU + SWD programmable; 3.3 V LDO on board")
    d.net("GND", "GND", ("U1", "T_G"), ("U1", "B_G"))
    d.net("+5V_BP", "5V", ("D3", "K"), ("U1", "B_5V"))
    d.net("VBUS_SENSE", "SENSE", ("U1", "A3"))


def acs712_pair(d, refs, at, rrefs, top_row, mcu_pins, tps, sense_names):
    """Two ACS712 modules side by side (headers on ``top_row``), each with a
    10k/20k divider (rows top_row-3 / top_row-2) feeding an ADC pin, and the
    solder-point holes for the phase leads under their screw terminals."""
    for i, (ref, col, rref, mcu, tp, sname) in enumerate(zip(refs, at, rrefs, mcu_pins, tps,
                                                              sense_names)):
        d.add(ref, fp_acs712("ACS712 module on a 1x3 female socket"), (col, top_row),
              value="ACS712-05B", note="185 mV/A; needs 5 V; output centred at 2.5 V")
        rs, rg = rref
        d.add(rs, fp_axial("axial 1/4 W, 10.16 mm span", 4), (col - 1, top_row - 2), value="10k",
              note=f"{ref} OUT series resistor (divider top)")
        d.add(rg, fp_axial("axial 1/4 W, 10.16 mm span", 4), (col - 1, top_row - 3), value="20k",
              note=f"{ref} divider bottom: 0-5 V -> 0-3.3 V for the ADC")
        d.net(f"{ref}_OUT", "SENSE", (ref, "OUT"), (rs, "2"))
        d.net(sname, "SENSE", (rs, "1"), (rg, "1"), (mcu[0], mcu[1]))
        d.net("GND", "GND", (rg, "2"), (ref, "GND"))
        d.net("+5V", "5V", (ref, "VCC"))
        tpi, tpo = tp
        d.add(tpi, fp_point("solder point"), (col, top_row + 12), note="hole for the phase lead into IP+")
        d.add(tpo, fp_point("solder point"), (col + 2, top_row + 12), note="hole for the phase lead out of IP-")


def motor_block(d, m, sf_at, acs_cols, acs_row, term_at, enc_at, pu_cols, mcu, sense_pins,
                enc_pins):
    """One SimpleFOC Mini + its AS5600 header (+ pull-ups) + ACS712 pair + motor terminal.

    m        - motor index (1 or 2) used for refs
    sf_at    - hole of the SimpleFOC Mini IN1 pin
    mcu      - dict IN1, IN2, IN3, EN, nFT -> Black Pill pin names
    """
    U = f"U{10 + m}"
    d.add(U, fp_sfmini("SimpleFOC Mini v1.1, male pins down"), sf_at, value=f"SimpleFOC Mini (M{m})",
          note="DRV8313; plug into 1x6 + 1x5 + 1x3 female sockets or solder the pins directly")
    J = f"J{10 + m}"
    d.add(J, fp_header("1x5 male header", 5, names=["3V3", "GND", "SCL", "SDA", "DIR"]), enc_at,
          value=f"AS5600 M{m}", note="to the encoder on the motor; DIR tied to GND on the board")
    Rs, Rd = f"R{20 + 2 * m}", f"R{21 + 2 * m}"
    d.add(Rs, fp_axial("axial 1/4 W, 10.16 mm span", 4), (pu_cols[0], enc_at[1] + 2), rot=90,
          value="4k7", note=f"I2C pull-up SCL (M{m})")
    d.add(Rd, fp_axial("axial 1/4 W, 10.16 mm span", 4), (pu_cols[1], enc_at[1] + 2), rot=90,
          value="4k7", note=f"I2C pull-up SDA (M{m})")
    JM = f"J{20 + m}"
    d.add(JM, fp_terminal("terminal 3 pos 5.08 mm", 3, names=["A", "B", "C"]), term_at, rot=90,
          value=f"MOTOR {m}", note="2804 gimbal motor phases")
    tpv, tpg = f"TP{m}V", f"TP{m}G"
    d.add(tpg, fp_point("solder point"), (sf_at[0] + 9, sf_at[1] + 1), note="hookup wire up to the module's VIN- terminal")
    d.add(tpv, fp_point("solder point"), (sf_at[0] + 9, sf_at[1] + 3), note="hookup wire up to the module's VIN+ terminal")

    A, B = f"U{12 + 2 * m}", f"U{13 + 2 * m}"          # ACS712 refs
    RA, RB = (f"R{30 + 4 * m}", f"R{31 + 4 * m}"), (f"R{32 + 4 * m}", f"R{33 + 4 * m}")
    TPA, TPB = (f"TP{m}A", f"TP{m}A2"), (f"TP{m}B", f"TP{m}B2")
    acs712_pair(d, (A, B), acs_cols, (RA, RB), acs_row, sense_pins, (TPA, TPB),
                (f"I_A{m}", f"I_B{m}"))

    # control
    d.net(f"PWM_A{m}", "PWM", (mcu["IN1"][0], mcu["IN1"][1]), (U, "IN1"))
    d.net(f"PWM_B{m}", "PWM", (mcu["IN2"][0], mcu["IN2"][1]), (U, "IN2"))
    d.net(f"PWM_C{m}", "PWM", (mcu["IN3"][0], mcu["IN3"][1]), (U, "IN3"))
    d.net(f"EN{m}", "CTRL", (mcu["EN"][0], mcu["EN"][1]), (U, "EN"))
    d.net(f"nFAULT{m}", "CTRL", (mcu["nFT"][0], mcu["nFT"][1]), (U, "nFT"))
    # encoder
    d.net(f"SCL{m}", "I2C", (enc_pins[0][0], enc_pins[0][1]), (J, "SCL"), (Rs, "1"))
    d.net(f"SDA{m}", "I2C", (enc_pins[1][0], enc_pins[1][1]), (J, "SDA"), (Rd, "1"))
    d.net("+3V3", "3V3", (J, "3V3"), (Rs, "2"), (Rd, "2"))
    d.net("GND", "GND", (J, "GND"), (J, "DIR"), (U, "GND"), (tpg, "1"))
    d.net("VM", "VM", (tpv, "1"))
    d.fly("GND", "GND", (tpg, "1"), (U, "VIN-"), "screw into the module's VIN- terminal")
    d.fly("VM", "VM", (tpv, "1"), (U, "VIN+"), "screw into the module's VIN+ terminal")
    # phases: M1 -> ACS712 A -> terminal A ; M2 -> ACS712 B -> terminal B ; M3 -> terminal C
    d.net(f"PH_A{m}_in", "PHASE", (U, "M1"), (TPA[0], "1"))
    d.fly(f"PH_A{m}_in", "PHASE", (TPA[0], "1"), (A, "IP+"), "screw into IP+")
    d.fly(f"PH_A{m}", "PHASE", (A, "IP-"), (TPA[1], "1"), "screw into IP-")
    d.net(f"PH_A{m}", "PHASE", (TPA[1], "1"), (JM, "A"))
    d.net(f"PH_B{m}_in", "PHASE", (U, "M2"), (TPB[0], "1"))
    d.fly(f"PH_B{m}_in", "PHASE", (TPB[0], "1"), (B, "IP+"), "screw into IP+")
    d.fly(f"PH_B{m}", "PHASE", (B, "IP-"), (TPB[1], "1"), "screw into IP-")
    d.net(f"PH_B{m}", "PHASE", (TPB[1], "1"), (JM, "B"))
    d.net(f"PH_C{m}", "PHASE", (U, "M3"), (JM, "C"))


# --------------------------------------------------------------------------
# L1: single motor, F401 Black Pill
# --------------------------------------------------------------------------

def build_l1():
    d = Design("L1", COLS, ROWS,
               title="L1 - single BLDC actuator on perf board: STM32F401 Black Pill + SimpleFOC Mini",
               subtitle="10 x 15 cm double-sided perf board, 38 x 58 holes, 2.54 mm pitch. "
                        "Wire-wrap wire for signals, 22 AWG solid hookup wire for power, bare bus bars for GND / VM / 5 V.")
    gnd_bus = [(36, 9), (2, 9), (2, 36), (36, 36)]
    power_section(d, gnd_bus)
    blackpill(d)
    motor_block(d, 1, sf_at=(7, 26), acs_cols=(26, 32), acs_row=13, term_at=(36, 27),
                enc_at=(17, 25), pu_cols=(19, 20),
                mcu={"IN1": ("U1", "A8"), "IN2": ("U1", "A9"), "IN3": ("U1", "A10"),
                     "EN": ("U1", "B13"), "nFT": ("U1", "B12")},
                sense_pins=(("U1", "A1"), ("U1", "A2")),
                enc_pins=(("U1", "B6"), ("U1", "B7")))
    d.net("+3V3", "3V3", ("U1", "B_3V3"))
    d.note("Black Pill pins used: A8/A9/A10 = TIM1 PWM, B13 = EN, B12 = nFAULT,")
    d.note("B6/B7 = I2C1 (AS5600), A1/A2 = ADC phase currents, A3 = VBUS sense.")
    d.note("SimpleFOC Mini 3V3 / nSP / nRT pins stay unconnected (module pull-ups).")
    d.note("Program over USB-C (DFU: hold BOOT0, tap NRST) or the SWD pads.")
    return d


# --------------------------------------------------------------------------
# L2: two motors, F401 Black Pill
# --------------------------------------------------------------------------

def build_l2():
    d = Design("L2", COLS, ROWS,
               title="L2 - two BLDC actuators on one perf board: STM32F401 Black Pill + 2x SimpleFOC Mini",
               subtitle="10 x 15 cm double-sided perf board, 38 x 58 holes, 2.54 mm pitch. "
                        "Wire-wrap wire for signals, 22 AWG solid hookup wire for power, bare bus bars for GND / VM / 5 V.")
    gnd_bus = [(36, 9), (2, 9), (2, 36), (36, 36)]
    power_section(d, gnd_bus, bus_5v=[(25, 7), (37, 7), (37, 41)])
    blackpill(d)
    motor_block(d, 1, sf_at=(7, 26), acs_cols=(26, 32), acs_row=13, term_at=(36, 27),
                enc_at=(17, 25), pu_cols=(19, 20),
                mcu={"IN1": ("U1", "A8"), "IN2": ("U1", "A9"), "IN3": ("U1", "A10"),
                     "EN": ("U1", "B13"), "nFT": ("U1", "B12")},
                sense_pins=(("U1", "A1"), ("U1", "A2")),
                enc_pins=(("U1", "B6"), ("U1", "B7")))
    motor_block(d, 2, sf_at=(7, 42), acs_cols=(24, 30), acs_row=40, term_at=(36, 44),
                enc_at=(17, 41), pu_cols=(19, 20),
                mcu={"IN1": ("U1", "A6"), "IN2": ("U1", "A7"), "IN3": ("U1", "B0"),
                     "EN": ("U1", "B14"), "nFT": ("U1", "B15")},
                sense_pins=(("U1", "A4"), ("U1", "A5")),
                enc_pins=(("U1", "B10"), ("U1", "B3")))
    d.net("+3V3", "3V3", ("U1", "B_3V3"))
    d.note("Motor 1: A8/A9/A10 = TIM1 PWM, B13 = EN, B12 = nFAULT, B6/B7 = I2C1, A1/A2 = currents.")
    d.note("Motor 2: A6/A7/B0 = TIM3 PWM, B14 = EN, B15 = nFAULT, B10/B3 = I2C2, A4/A5 = currents.")
    d.note("A3 = VBUS sense.  ACS712 pairs are optional: without them run SimpleFOC in voltage mode.")
    d.note("SimpleFOC Mini 3V3 / nSP / nRT pins stay unconnected (module pull-ups).")
    d.note("Program over USB-C (DFU: hold BOOT0, tap NRST) or the SWD pads.")
    return d


# --------------------------------------------------------------------------
# L3: bare STM32G431CBT6 on a LQFP48 -> DIP adapter, SN65HVD230 CAN
# --------------------------------------------------------------------------

G431 = {  # LQFP48 pin numbers (from the KiCad MCU_ST_STM32G4 symbol)
    "VBAT": "1", "PC13": "2", "PC14": "3", "PC15": "4", "PF0": "5", "PF1": "6", "NRST": "7",
    "PA0": "8", "PA1": "9", "PA2": "10", "PA3": "11", "PA4": "12", "PA5": "13", "PA6": "14",
    "PA7": "15", "PB0": "16", "PB1": "17", "PB2": "18", "VSSA": "19", "VREF+": "20", "VDDA": "21",
    "PB10": "22", "VSS1": "23", "VDD1": "24", "PB11": "25", "PB12": "26", "PB13": "27",
    "PB14": "28", "PB15": "29", "PA8": "30", "PA9": "31", "PA10": "32", "PA11": "33",
    "PA12": "34", "VSS2": "35", "VDD2": "36", "PA13": "37", "PA14": "38", "PA15": "39",
    "PB3": "40", "PB4": "41", "PB5": "42", "PB6": "43", "PB7": "44", "PB8": "45", "PB9": "46",
    "VSS3": "47", "VDD3": "48",
}


def build_l3():
    d = Design("L3", COLS, ROWS,
               title="L3 - target node on perf board: bare STM32G431CBT6 (LQFP48 adapter) + SN65HVD230 CAN + SimpleFOC Mini",
               subtitle="10 x 15 cm double-sided perf board, 38 x 58 holes, 2.54 mm pitch. "
                        "Wire-wrap wire for signals, 22 AWG solid hookup wire for power, bare bus bars for GND / VM / 5 V / 3.3 V.")
    gnd_bus = [(36, 9), (2, 9), (2, 40), (36, 40)]
    power_section(d, gnd_bus, bp_diode=False, divider="left", vm_start=3)
    # 3.3 V regulator on the 5 V bus, feeding a U-shaped 3.3 V bus around the MCU
    d.add("U3", fp_to220("TO-220 upright", names=("GND", "OUT", "IN"), heatsink=False), (21, 10),
          value="LD1117V33", note="3.3 V for MCU, encoder, CAN transceiver (~100 mA); AMS1117-3.3 module also fine")
    d.add("C5", fp_radial("radial 6.3 mm, 2.5 mm lead spacing", 1, dia=6.3, polarized=True), (26, 12),
          rot=270, value="10u 16V", note="LD1117 output cap (tantalum/polymer, ESR >= 0.3 ohm preferred)")
    d.net("+5V", "5V", ("U3", "IN"))
    d.net("GND", "GND", ("U3", "GND"), ("C5", "-"))
    BUS_3V3 = [(14, 12), (26, 12), (26, 33), (4, 33)]

    # MCU on the adapter, rotated so ADC pins face up, PWM/CAN pins face down
    U = "U1"
    pins = {k: (U, v) for k, v in G431.items()}
    names = {v: k.rstrip("123") if k.startswith(("VSS", "VDD")) and k[-1].isdigit() else k
             for k, v in G431.items()}
    d.add(U, fp_qfp48_adapter("LQFP48 -> DIP48 adapter, 12 pins/side, 13 holes between rows",
                              names=names),
          (17, 17), rot=90, value="STM32G431CBT6", label_at=(-16.5, 4.2),
          note="0.5 mm pitch adapter board with 4x 1x12 male pin strips; check the pin-row spacing of yours")
    # top row (row 17): VBAT PC13 PC14 PC15 PF0 PF1 NRST PA0 PA1 PA2 PA3 PA4 at cols 16..5
    # left column (col 4): PA5 PA6 PA7 PB0 PB1 PB2 VSSA VREF+ VDDA PB10 VSS VDD rows 18..29
    # bottom row (row 30): PB11 PB12 PB13 PB14 PB15 PA8 PA9 PA10 PA11 PA12 VSS VDD cols 5..16
    # right column (col 17): PA13 PA14 PA15 PB3 PB4 PB5 PB6 PB7 PB8 PB9 VSS VDD rows 29..18
    d.add("C7", fp_ceramic("ceramic, 2.54 mm span", 1), (3, 25), rot=90, value="100n", note="VDD/VSS pins 23-24")
    d.add("C8", fp_ceramic("ceramic, 2.54 mm span", 1), (15, 31), value="100n", note="VDD/VSS pins 35-36")
    d.add("C9", fp_ceramic("ceramic, 2.54 mm span", 1), (18, 17), rot=90, value="100n", note="VDD/VSS pins 47-48")
    d.add("C11", fp_ceramic("ceramic, 5.08 mm span", 2), (3, 21), rot=90, value="1u", note="VDDA/VSSA (VREF+ tied to VDDA)")
    d.add("Y1", fp_crystal("HC-49S crystal, 2 holes"), (11, 16), value="8 MHz", note="HSE for FDCAN bit timing")
    d.add("C12", fp_ceramic("ceramic, 2.54 mm span", 1), (12, 14), value="20p", note="crystal load (PF0)")
    d.add("C13", fp_ceramic("ceramic, 2.54 mm span", 1), (10, 14), value="20p", note="crystal load (PF1)",
          label_at=(1.27, 3.0))
    d.add("C14", fp_ceramic("ceramic, 2.54 mm span", 1), (7, 16), value="100n", note="NRST filter")
    d.add("SW1", fp_tactile("6x6 mm tactile switch"), (5, 13), value="RESET", note="momentary to GND",
          label_at=(-2.0, -2.6))
    d.add("SW2", fp_dip_switch4("DIP switch 4 pos"), (16, 16), rot=270, value="ADDR",
          note="node address bits to GND; use the MCU internal pull-ups")
    d.add("D4", fp_led("5 mm / 3 mm LED", cls="passive"), (18, 20), value="LED FAULT", note="active-low LED from 3.3 V (PB9)")
    d.add("R7", fp_axial("axial 1/4 W, 10.16 mm span", 4), (20, 20), value="1k", note="LED FAULT series")
    d.add("JP1", fp_header("1x2 pin header + jumper", 2), (21, 21), value="BOOT0",
          note="fit the jumper to enter the system bootloader", label_at=(2 * 2.54 + 5.2, 0))
    d.add("R6", fp_axial("axial 1/4 W, 10.16 mm span", 4), (18, 22), value="10k", note="BOOT0 pull-down")
    d.add("D5", fp_led("5 mm / 3 mm LED", cls="passive"), (18, 25), value="LED RUN", note="active-low LED from 3.3 V (PB4)")
    d.add("R8", fp_axial("axial 1/4 W, 10.16 mm span", 4), (20, 25), value="1k", note="LED RUN series")
    d.add("J4", fp_header("1x5 male header", 5, names=["3V3", "SWDIO", "SWCLK", "NRST", "GND"], vertical=True),
          (19, 27), value="SWD", note="ST-Link V2 programming / debug")
    d.add("R9", fp_axial("axial 1/4 W, 10.16 mm span", 4), (21, 27), rot=90, value="4k7", note="I2C pull-up SCL")
    d.add("R10", fp_axial("axial 1/4 W, 10.16 mm span", 4), (22, 27), rot=90, value="4k7", note="I2C pull-up SDA")
    d.add("J5", fp_header("1x5 male header", 5, names=["3V3", "GND", "SCL", "SDA", "DIR"]), (19, 32),
          value="AS5600", note="encoder on the motor; DIR tied to GND on the board")
    d.add("J8", fp_header("1x3 male header", 3, names=["TX", "RX", "GND"]), (6, 32), value="UART3",
          note="PB10/PB11 debug console (3.3 V levels)")
    # CAN
    d.add("U4", fp_dip("SOIC-8 -> DIP-8 adapter", 8, rows_apart=3,
                       names=["D", "GND", "VCC", "R", "Vref", "CANL", "CANH", "Rs"], cls="module"),
          (22, 35), value="SN65HVD230", note="3.3 V CAN transceiver on a SOIC8->DIP8 adapter")
    d.add("R11", fp_axial("axial 1/4 W, 10.16 mm span", 4), (26, 35), value="0R (wire)",
          note="Rs: 0 R = high-speed mode; 10k = slope control for <= 500 kbit/s")
    d.add("JP2", fp_header("1x2 pin header + jumper", 2, vertical=True), (28, 36), value="TERM",
          note="fit the jumper on the two end nodes of the bus")
    d.add("R12", fp_axial("axial 1/4 W, 10.16 mm span", 4), (29, 37), value="120R", note="CAN termination")
    d.add("JC1", fp_header("1x3 male header", 3, names=["CANH", "CANL", "GND"], vertical=True), (36, 32),
          value="CAN A", note="bus in")
    d.add("JC2", fp_header("1x3 male header", 3, names=["CANH", "CANL", "GND"], vertical=True), (36, 36),
          value="CAN B", note="bus out (daisy chain)")
    # driver, encoder header, current sensors, motor terminal
    d.add("U11", fp_sfmini("SimpleFOC Mini v1.1, male pins down"), (10, 35), value="SimpleFOC Mini",
          note="DRV8313; plug into 1x6 + 1x5 + 1x3 female sockets or solder the pins directly")
    d.add("TP1G", fp_point("solder point"), (19, 36), note="hookup wire up to the module's VIN- terminal")
    d.add("TP1V", fp_point("solder point"), (19, 38), note="hookup wire up to the module's VIN+ terminal")
    d.add("J21", fp_terminal("terminal 3 pos 5.08 mm", 3, names=["A", "B", "C"]), (36, 42), rot=90,
          value="MOTOR", note="2804 gimbal motor phases")
    acs712_pair(d, ("U14", "U15"), (28, 34), (("R34", "R35"), ("R36", "R37")), 14,
                (pins["PA0"], pins["PA1"]), (("TP1A", "TP1A2"), ("TP1B", "TP1B2")), ("I_A", "I_B"))

    # ---- nets ------------------------------------------------------------
    d.net("+3V3", "3V3", ("U3", "OUT"), ("C5", "+"),
          pins["VDD1"], pins["VDD2"], pins["VDD3"], pins["VDDA"], pins["VREF+"], pins["VBAT"],
          ("C7", "2"), ("C8", "2"), ("C9", "2"), ("C11", "2"),
          ("J4", "3V3"), ("JP1", "2"), ("R7", "2"), ("R8", "2"), ("R9", "1"), ("R10", "1"),
          ("J5", "3V3"), ("U4", "VCC"),
          bus=BUS_3V3,
          taps={("U3", "OUT"): (22, 12), ("C7", "2"): pins["VDD1"], ("C8", "2"): pins["VDD2"],
                ("C9", "2"): pins["VDD3"], ("C11", "2"): pins["VDDA"], pins["VREF+"]: pins["VDDA"]})
    d.net("GND", "GND", pins["VSS1"], pins["VSS2"], pins["VSS3"], pins["VSSA"], ("C7", "1"), ("C8", "1"),
          ("C9", "1"), ("C11", "1"), ("C12", "2"), ("C13", "1"), ("C14", "1"),
          ("SW1", "B1"), ("SW2", "1b"), ("SW2", "2b"), ("SW2", "3b"), ("SW2", "4b"), ("R6", "2"),
          ("J4", "GND"), ("J5", "GND"), ("J5", "DIR"), ("J8", "GND"), ("U4", "GND"), ("R11", "2"),
          ("JC1", "GND"), ("JC2", "GND"), ("U11", "GND"), ("TP1G", "1"))
    d.net("VM", "VM", ("TP1V", "1"))
    d.fly("GND", "GND", ("TP1G", "1"), ("U11", "VIN-"), "screw into the module's VIN- terminal")
    d.fly("VM", "VM", ("TP1V", "1"), ("U11", "VIN+"), "screw into the module's VIN+ terminal")
    # clock, reset, boot, address
    d.net("XIN", "DBG", pins["PF0"], ("Y1", "2"), ("C12", "1"),
          chain=[pins["PF0"], ("Y1", "2"), ("C12", "1")])
    d.net("XOUT", "DBG", pins["PF1"], ("Y1", "1"), ("C13", "2"),
          chain=[pins["PF1"], ("Y1", "1"), ("C13", "2")])
    d.net("NRST", "CTRL", ("J4", "NRST"), pins["NRST"], ("C14", "2"), ("SW1", "A2"),
          chain=[("J4", "NRST"), pins["NRST"], ("C14", "2"), ("SW1", "A2")])
    d.net("BOOT0", "DBG", pins["PB8"], ("R6", "1"), ("JP1", "1"))
    d.net("ADDR0", "DBG", pins["PC13"], ("SW2", "1"))
    d.net("ADDR1", "DBG", pins["PC14"], ("SW2", "2"))
    d.net("ADDR2", "DBG", pins["PC15"], ("SW2", "3"))
    d.net("ADDR3", "DBG", pins["PB2"], ("SW2", "4"))
    # LEDs (active low: 3.3 V -> R -> LED -> GPIO)
    d.net("LED_FAULT", "DBG", pins["PB9"], ("D4", "K"))
    d.net("LED_FAULT_A", "DBG", ("D4", "A"), ("R7", "1"))
    d.net("LED_RUN", "DBG", pins["PB4"], ("D5", "K"))
    d.net("LED_RUN_A", "DBG", ("D5", "A"), ("R8", "1"))
    # debug
    d.net("SWDIO", "DBG", pins["PA13"], ("J4", "SWDIO"))
    d.net("SWCLK", "DBG", pins["PA14"], ("J4", "SWCLK"))
    d.net("UART3_TX", "DBG", pins["PB10"], ("J8", "TX"))
    d.net("UART3_RX", "DBG", pins["PB11"], ("J8", "RX"))
    # encoder
    d.net("SCL", "I2C", pins["PA15"], ("R9", "2"), ("J5", "SCL"))
    d.net("SDA", "I2C", pins["PB7"], ("R10", "2"), ("J5", "SDA"))
    # CAN
    d.net("CAN_TX", "CAN", pins["PA12"], ("U4", "D"))
    d.net("CAN_RX", "CAN", pins["PA11"], ("U4", "R"))
    d.net("CAN_RS", "CAN", ("U4", "Rs"), ("R11", "1"))
    d.net("CANH", "CAN", ("U4", "CANH"), ("JP2", "1"), ("JC1", "CANH"), ("JC2", "CANH"),
          chain=[("U4", "CANH"), ("JP2", "1"), ("JC1", "CANH"), ("JC2", "CANH")])
    d.net("CAN_TERM", "CAN", ("JP2", "2"), ("R12", "1"))
    d.net("CANL", "CAN", ("U4", "CANL"), ("R12", "2"), ("JC1", "CANL"), ("JC2", "CANL"),
          chain=[("U4", "CANL"), ("R12", "2"), ("JC1", "CANL"), ("JC2", "CANL")])
    # driver
    d.net("PWM_A", "PWM", pins["PA8"], ("U11", "IN1"))
    d.net("PWM_B", "PWM", pins["PA9"], ("U11", "IN2"))
    d.net("PWM_C", "PWM", pins["PA10"], ("U11", "IN3"))
    d.net("DRV_EN", "CTRL", pins["PA5"], ("U11", "EN"))
    d.net("nFAULT", "CTRL", pins["PB12"], ("U11", "nFT"))
    d.net("PH_A_in", "PHASE", ("U11", "M1"), ("TP1A", "1"))
    d.fly("PH_A_in", "PHASE", ("TP1A", "1"), ("U14", "IP+"), "screw into IP+")
    d.fly("PH_A", "PHASE", ("U14", "IP-"), ("TP1A2", "1"), "screw into IP-")
    d.net("PH_A", "PHASE", ("TP1A2", "1"), ("J21", "A"))
    d.net("PH_B_in", "PHASE", ("U11", "M2"), ("TP1B", "1"))
    d.fly("PH_B_in", "PHASE", ("TP1B", "1"), ("U15", "IP+"), "screw into IP+")
    d.fly("PH_B", "PHASE", ("U15", "IP-"), ("TP1B2", "1"), "screw into IP-")
    d.net("PH_B", "PHASE", ("TP1B2", "1"), ("J21", "B"))
    d.net("PH_C", "PHASE", ("U11", "M3"), ("J21", "C"))
    # VBUS divider node -> PA3
    d.net("VBUS_SENSE", "SENSE", pins["PA3"])
    d.note("Same pin map as the PCB except: EN = PA5 (3-PWM module), I2C1 = PA15/PB7 for the")
    d.note("AS5600, LED RUN = PB4, phase currents from ACS712 on PA0/PA1, no SPI / hall / NTC.")
    d.note("Address DIP switch uses the MCU internal pull-ups (no resistors).")
    d.note("Program with an ST-Link on J4 (or UART bootloader: jumper BOOT0, USART1 on PA9/PA10).")
    return d


BUILDERS = {"L1": build_l1, "L2": build_l2, "L3": build_l3}


def main():
    outdir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "..")
    only = sys.argv[2:] or list(BUILDERS)
    ok = True
    for name in only:
        d = BUILDERS[name]()
        sub = {"L1": "L1-single-f401", "L2": "L2-dual-f401", "L3": "L3-g431-can"}[name]
        problems, rows = write_outputs(d, os.path.join(outdir, sub), name)
        print(f"{name}: {len(d.parts)} parts, {len(d.nets)} nets, {len(rows)} wiring steps")
        for p in problems:
            ok = False
            print("  PROBLEM:", p)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
