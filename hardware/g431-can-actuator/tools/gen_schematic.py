#!/usr/bin/env python3
"""Generate the ``g431-can-actuator`` KiCad schematic project.

A CAN-FD BLDC/PMSM actuator node: one STM32G431CBT6 and one integrated
three-phase driver per actuator, daisy-chained on a single CAN bus.

Requires KiCad's stock symbol libraries (``/usr/share/kicad/symbols`` or
``$KICAD_SYMBOL_DIR``)::

    python3 tools/gen_schematic.py

This script bootstraps the project and keeps the intended connectivity
readable in one place.  Once the project is opened in KiCad the generated
``.kicad_sch`` files become the source of truth.
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from kisch import (  # noqa: E402
    Sheet, SymbolLib, add_sheet_ref, make_ic_symbol, num, quote,
    render_sheet, uuid_for, write_symbol_lib,
)

PROJECT = "g431-can-actuator"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIBNAME = "g431-can-actuator"
REV = "A"

FP = {
    "R":        "Resistor_SMD:R_0603_1608Metric",
    "R_1206":   "Resistor_SMD:R_1206_3216Metric",
    "C":        "Capacitor_SMD:C_0603_1608Metric",
    "C_0805":   "Capacitor_SMD:C_0805_2012Metric",
    "C_1206":   "Capacitor_SMD:C_1206_3216Metric",
    "CP":       "Capacitor_SMD:CP_Elec_8x10.5",
    "L_BUCK":   "Inductor_SMD:L_Bourns-SRN6028",
    "FB":       "Inductor_SMD:L_0805_2012Metric",
    "LED":      "LED_SMD:LED_0603_1608Metric",
    "D_SOD123": "Diode_SMD:D_SOD-123",
    "D_SMA":    "Diode_SMD:D_SMA",
    "D_SMB":    "Diode_SMD:D_SMB",
    "SOT23":    "Package_TO_SOT_SMD:SOT-23",
    "SOT23_5":  "Package_TO_SOT_SMD:SOT-23-5",
    "SOIC8":    "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
    "LQFP48":   "Package_QFP:LQFP-48_7x7mm_P0.5mm",
    "QFN24":    "Package_DFN_QFN:QFN-24-1EP_3x3mm_P0.4mm_EP1.75x1.6mm",
    "XTAL":     "Crystal:Crystal_SMD_3225-4Pin_3.2x2.5mm",
    "FUSE":     "Fuse:Fuse_1812_4532Metric",
    "TP":       "TestPoint:TestPoint_Pad_D1.5mm",
    "DIP4":     "Button_Switch_SMD:SW_DIP_SPSTx04_Slide_9.78x12.34mm_W8.61mm_P2.54mm",
    "TERM2":    "TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-1,5-2-5.08_1x02_P5.08mm_Horizontal",
    "TERM3":    "TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-1,5-3-5.08_1x03_P5.08mm_Horizontal",
    "GH3":      "Connector_JST:JST_GH_BM03B-GHS-TBT_1x03-1MP_P1.25mm_Vertical",
    "GH8":      "Connector_JST:JST_GH_BM08B-GHS-TBT_1x08-1MP_P1.25mm_Vertical",
    "HDR2":     "Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical",
    "HDR3":     "Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical",
    "HDR4":     "Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical",
    "SWD6":     "Connector_PinHeader_1.27mm:PinHeader_1x06_P1.27mm_Vertical",
}

# --------------------------------------------------------------------------
# Terminating pins
#
#   "@RAIL"          -> power symbol
#   ">shape:NAME"    -> hierarchical label (cross-sheet)
#   "NAME"           -> local net label
# --------------------------------------------------------------------------


def term(sh, comp, pin, spec, length=2.54):
    if spec.startswith("@"):
        return sh.to_power(comp, pin, spec[1:], length)
    if spec.startswith(">"):
        shape, name = spec[1:].split(":", 1)
        return sh.net(comp, pin, name, length, kind="hier", shape=shape)
    return sh.net(comp, pin, spec, length)


def two(sh, comp, a, b, la=2.54, lb=2.54):
    term(sh, comp, "1", a, la)
    term(sh, comp, "2", b, lb)
    return comp


def res(sh, ref, value, at, a, b, rot=0, fp="R", **kw):
    return two(sh, sh.place(ref, "Device:R", value, at=at, rot=rot,
                            footprint=FP[fp], **kw), a, b)


def cap(sh, ref, value, at, a, b, rot=0, fp="C", **kw):
    return two(sh, sh.place(ref, "Device:C", value, at=at, rot=rot,
                            footprint=FP[fp], **kw), a, b)


def cap_pol(sh, ref, value, at, a, b, rot=0, fp="CP", **kw):
    return two(sh, sh.place(ref, "Device:C_Polarized", value, at=at, rot=rot,
                            footprint=FP[fp], **kw), a, b)


CUSTOM_POWER = {"VM": f"{LIBNAME}:VM", "+3V3A": f"{LIBNAME}:+3V3A"}


def new_sheet(lib, name, title, page):
    sh = Sheet(name, lib, PROJECT, title=title, page=page)
    sh.custom_power = dict(CUSTOM_POWER)
    return sh


def title_block(sheet):
    return "\n".join([
        "  (title_block",
        f"    (title {quote('STM32G431 CAN-FD actuator node')})",
        f"    (rev {quote(REV)})",
        f"    (comment 1 {quote(sheet.title)})",
        f"    (comment 2 {quote('12 V nominal (9-18 V) - 3-phase BLDC/PMSM - FDCAN')})",
        f"    (comment 3 {quote('One node per actuator, 4-bit DIP node address')})",
    ]) + "\n  )"


# --------------------------------------------------------------------------
# Symbols the stock libraries do not carry
# --------------------------------------------------------------------------

DRV8311S_PINS = {
    "left": [
        ("15", "INHA", "input"), ("18", "INLA", "input"),
        ("14", "INHB", "input"), ("19", "INLB", "input"),
        ("13", "INHC", "input"), ("20", "INLC", "input"),
        None,
        ("23", "SCLK", "input"), ("22", "SDI", "input"),
        ("24", "~{SCS}", "input"), ("21", "SDO", "tri_state"),
        ("1", "~{FAULT}", "open_collector"),
    ],
    "right": [
        ("10", "OUTA", "tri_state"), ("11", "OUTB", "tri_state"),
        ("12", "OUTC", "tri_state"),
        None, None,
        ("5", "SOA", "output"), ("4", "SOB", "output"), ("3", "SOC", "output"),
        None,
        ("2", "CSAREF", "input"), ("17", "AVDD", "power_out"),
        None,
    ],
    "top": [("8", "VM", "power_in"), ("7", "VIN_AVDD", "power_in"),
            ("6", "CP", "input")],
    "bottom": [("9", "PGND", "power_in"), ("25", "PGND", "passive"),
               ("16", "AGND", "power_in")],
}


def power_symbol(name, description=None):
    """A KiCad power symbol (a hidden power_in pin named after the net)."""
    desc = description or f'Power symbol creates a global label with name "{name}"'
    f = "(effects (font (size 1.27 1.27)))"
    fh = "(effects (font (size 1.27 1.27)) hide)"
    poly = ("      (polyline\n        (pts\n          (xy {0})\n          (xy {1})\n"
            "        )\n        (stroke (width 0) (type default))\n"
            "        (fill (type none))\n      )")
    return "\n".join([
        f'  (symbol {quote(name)} (power) (pin_names (offset 0)) (in_bom yes) (on_board yes)',
        f'    (property "Reference" "#PWR" (at 0 -3.81 0)', f"      {fh}", "    )",
        f'    (property "Value" {quote(name)} (at 0 3.556 0)', f"      {f}", "    )",
        f'    (property "Footprint" "" (at 0 0 0)', f"      {fh}", "    )",
        f'    (property "Datasheet" "" (at 0 0 0)', f"      {fh}", "    )",
        f'    (property "ki_keywords" "global power" (at 0 0 0)', f"      {fh}", "    )",
        f'    (property "ki_description" {quote(desc)} (at 0 0 0)', f"      {fh}", "    )",
        f'    (symbol "{name}_0_1"',
        poly.format("-0.762 1.27", "0 2.54"),
        poly.format("0 0", "0 2.54"),
        poly.format("0 2.54", "0.762 1.27"),
        "    )",
        f'    (symbol "{name}_1_1"',
        "      (pin power_in line (at 0 0 90) (length 0) hide",
        f"        (name {quote(name)} {f})",
        f"        (number \"1\" {f})",
        "      )",
        "    )",
        "  )",
    ])


def build_project_library(path):
    symbols = [
        make_ic_symbol(
            "DRV8311S", DRV8311S_PINS,
            footprint=FP["QFN24"],
            datasheet="https://www.ti.com/lit/ds/symlink/drv8311.pdf",
            description=("Three-phase PWM motor driver with integrated FETs, 3-20 V, "
                         "5 A peak, three current-sense amplifiers, SPI, WQFN-24"),
            keywords="Texas-Instruments BLDC three-phase motor driver FOC",
            fp_filters="*QFN*3x3mm*P0.4mm*",
        ),
        power_symbol("VM", "Motor supply rail downstream of fuse and reverse-polarity FET"),
        power_symbol("+3V3A", "Filtered 3.3 V analog rail for VDDA / VREF+"),
    ]
    return write_symbol_lib(path, symbols)


# --------------------------------------------------------------------------
# Sheet 2: power
# --------------------------------------------------------------------------


def build_power(lib):
    sh = new_sheet(lib, "power", "Power input, protection and rails", "2")

    # ---- input protection ------------------------------------------------
    sh.text("Input protection - 9..18 V DC (12 V nominal), 20 V absolute max", (25, 30), 2)
    j1 = sh.place("J1", "Connector_Generic:Conn_01x02", "VIN 9-18V", at=(40, 55),
                  footprint=FP["TERM2"])
    term(sh, j1, "1", "VIN_RAW", 5.08)
    term(sh, j1, "2", "@GND", 5.08)

    two(sh, sh.place("F1", "Device:Polyfuse", "3A hold", at=(62, 50), rot=90,
                     footprint=FP["FUSE"]), "VIN_RAW", "VIN_F", 3.81, 3.81)
    two(sh, sh.place("D1", "Device:D_TVS", "SMBJ18CA", at=(80, 55), rot=270,
                     footprint=FP["D_SMB"]), "VIN_F", "@GND", 3.81, 3.81)

    # Reverse-polarity P-FET: drain on the supply side, source on the load
    # side, gate held near ground.  Correct polarity turns the FET on and
    # bypasses its body diode; reversed polarity keeps Vgs >= 0 and the body
    # diode reverse-biased, so nothing conducts.
    q1 = sh.place("Q1", "Device:Q_PMOS_GSD", "AO4407A", at=(105, 50), rot=90,
                  footprint=FP["SOIC8"])
    term(sh, q1, "3", "VIN_F", 5.08)        # D
    term(sh, q1, "2", "@VM", 5.08)          # S
    term(sh, q1, "1", "VGATE", 5.08)        # G
    res(sh, "R1", "100k", (95, 72), "VGATE", "@GND")
    two(sh, sh.place("D2", "Device:D_Zener", "MMSZ5245B 15V", at=(118, 72), rot=270,
                     footprint=FP["D_SOD123"]), "@VM", "VGATE", 3.81, 3.81)

    sh.place("#FLG01", "power:PWR_FLAG", "PWR_FLAG", at=(135, 45), rot=0,
             footprint="", in_bom=False)
    sh.net(sh.comps[-1], "1", "VM", 0)
    sh.place("#FLG02", "power:PWR_FLAG", "PWR_FLAG", at=(148, 45), rot=0,
             footprint="", in_bom=False)
    sh.net(sh.comps[-1], "1", "GND", 0)

    cap_pol(sh, "C1", "220uF/35V", (165, 55), "@VM", "@GND", fp="CP")
    cap_pol(sh, "C2", "220uF/35V", (178, 55), "@VM", "@GND", fp="CP")
    cap(sh, "C3", "10uF/35V", (191, 55), "@VM", "@GND", fp="C_1206")
    cap(sh, "C4", "100nF/50V", (204, 55), "@VM", "@GND")

    # ---- 5 V buck --------------------------------------------------------
    sh.text("5 V / 2 A step-down - TPS54233, 570 kHz, non-synchronous", (25, 105), 2)
    u1 = sh.place("U1", "Regulator_Switching:TPS54233", "TPS54233", at=(90, 140),
                  footprint=FP["SOIC8"])
    term(sh, u1, "2", "@VM", 5.08)          # VIN
    term(sh, u1, "7", "@GND", 5.08)         # GND
    term(sh, u1, "1", "BOOT", 5.08)         # BOOT
    term(sh, u1, "8", "SW_5V", 5.08)        # PH
    term(sh, u1, "3", "EN_5V", 5.08)        # EN
    term(sh, u1, "4", "SS_5V", 5.08)        # SS
    term(sh, u1, "6", "COMP_5V", 5.08)      # COMP
    term(sh, u1, "5", "FB_5V", 5.08)        # FB

    cap(sh, "C5", "10uF/35V", (40, 140), "@VM", "@GND", fp="C_1206")
    # EN divider -> turn-on at roughly 1.25 V * (100k + 22k) / 22k = 6.9 V
    res(sh, "R2", "100k", (55, 122), "@VM", "EN_5V")
    res(sh, "R3", "22k", (55, 160), "EN_5V", "@GND")
    cap(sh, "C6", "10nF", (40, 168), "SS_5V", "@GND")
    res(sh, "R4", "10k", (25, 185), "COMP_5V", "COMP_MID")
    cap(sh, "C7", "3.3nF", (40, 185), "COMP_MID", "@GND")
    cap(sh, "C8", "100nF/25V", (120, 112), "BOOT", "SW_5V", rot=90)

    two(sh, sh.place("D3", "Device:D_Schottky", "SS36", at=(120, 165), rot=270,
                     footprint=FP["D_SMA"]), "SW_5V", "@GND", 3.81, 3.81)
    two(sh, sh.place("L1", "Device:L", "10uH 2.5A", at=(145, 130), rot=90,
                     footprint=FP["L_BUCK"]), "SW_5V", "@+5V", 5.08, 5.08)

    cap(sh, "C9", "22uF/16V", (165, 145), "@+5V", "@GND", fp="C_0805")
    cap(sh, "C10", "22uF/16V", (178, 145), "@+5V", "@GND", fp="C_0805")
    cap(sh, "C11", "100nF/16V", (191, 145), "@+5V", "@GND")
    sh.place("#FLG03", "power:PWR_FLAG", "PWR_FLAG", at=(204, 135), rot=0,
             footprint="", in_bom=False)
    sh.net(sh.comps[-1], "1", "+5V", 0)
    # Feedback divider -> 0.8 V * (52.3k + 10k) / 10k = 4.98 V
    res(sh, "R5", "52.3k", (150, 165), "@+5V", "FB_5V")
    res(sh, "R6", "10k", (150, 190), "FB_5V", "@GND")

    # ---- 3.3 V LDO -------------------------------------------------------
    sh.text("3.3 V logic rail and filtered analog rail", (240, 105), 2)
    u2 = sh.place("U2", "Regulator_Linear:AP2112K-3.3", "AP2112K-3.3", at=(275, 130),
                  footprint=FP["SOT23_5"])
    term(sh, u2, "1", "@+5V", 5.08)         # VIN
    term(sh, u2, "3", "@+5V", 10.16)        # EN tied high: always on
    term(sh, u2, "2", "@GND", 5.08)         # GND
    term(sh, u2, "5", "@+3V3", 5.08)        # VOUT
    sh.nc(sh.stub(u2, "4", 2.54)[0])        # NC
    cap(sh, "C12", "1uF/16V", (250, 148), "@+5V", "@GND")
    cap(sh, "C13", "10uF/10V", (300, 148), "@+3V3", "@GND", fp="C_0805")
    cap(sh, "C14", "100nF/16V", (313, 148), "@+3V3", "@GND")
    sh.place("#FLG04", "power:PWR_FLAG", "PWR_FLAG", at=(326, 120), rot=0,
             footprint="", in_bom=False)
    sh.net(sh.comps[-1], "1", "+3V3", 0)

    two(sh, sh.place("FB1", "Device:FerriteBead_Small", "600R@100MHz 1A", at=(350, 130),
                     rot=90, footprint=FP["FB"]), "@+3V3", "@+3V3A", 5.08, 5.08)
    cap(sh, "C15", "1uF/16V", (368, 148), "@+3V3A", "@GNDA", fp="C")
    cap(sh, "C16", "100nF/16V", (381, 148), "@+3V3A", "@GNDA")
    # Single-point analog/digital ground tie
    res(sh, "R7", "0R", (350, 175), "@GNDA", "@GND")
    sh.place("#FLG05", "power:PWR_FLAG", "PWR_FLAG", at=(375, 120), rot=0,
             footprint="", in_bom=False)
    sh.net(sh.comps[-1], "1", "+3V3A", 0)
    sh.place("#FLG06", "power:PWR_FLAG", "PWR_FLAG", at=(390, 120), rot=0,
             footprint="", in_bom=False)
    sh.net(sh.comps[-1], "1", "GNDA", 0)

    # ---- sensing ---------------------------------------------------------
    sh.text("Bus voltage and board temperature sensing", (25, 215), 2)
    res(sh, "R8", "100k", (45, 235), "@VM", "VBUS_SENSE")
    res(sh, "R9", "18k", (45, 262), "VBUS_SENSE", "@GND")
    cap(sh, "C17", "100nF", (62, 262), ">output:VBUS_SENSE", "@GND")

    res(sh, "R10", "10k 1%", (125, 235), "@+3V3", "TEMP_BOARD")
    sh.place("TH1", "Device:Thermistor_NTC", "10k B3380", at=(125, 262),
             footprint=FP["R"])
    two(sh, sh.comps[-1], "TEMP_BOARD", "@GND")
    cap(sh, "C18", "100nF", (142, 262), ">output:TEMP_BOARD", "@GND")

    # ---- indicator and test points --------------------------------------
    res(sh, "R11", "1k", (205, 235), "@+3V3", "LED_PWR_A")
    led = sh.place("D4", "Device:LED", "green PWR", at=(205, 258), rot=90,
                   footprint=FP["LED"])
    term(sh, led, "2", "LED_PWR_A", 3.81)   # anode
    term(sh, led, "1", "@GND", 3.81)        # cathode

    for i, (ref, net, x) in enumerate((("TP1", "VM", 245), ("TP2", "+5V", 260),
                                       ("TP3", "+3V3", 275), ("TP4", "GND", 290))):
        tp = sh.place(ref, "Connector:TestPoint", net, at=(x, 245), rot=180,
                      footprint=FP["TP"])
        term(sh, tp, "1", "@" + net, 2.54)
    return sh


# --------------------------------------------------------------------------
# Sheet 3: mcu
#
# STM32G431CBT6 pin assignment.  Peripheral choices:
#   TIM1  CH1..3 / CH1N..3N  -> six-step and centre-aligned FOC PWM
#   TIM1  BKIN                -> hardware trip from the driver fault pin
#   TIM3  CH1..3             -> Hall sensor interface / quadrature encoder
#   ADC1  IN1..IN4, IN12     -> phase currents, bus voltage, board NTC
#   ADC2  IN17               -> motor NTC
#   SPI1                     -> driver configuration and diagnostics
#   FDCAN1                   -> the actuator bus
# --------------------------------------------------------------------------

MCU_PINS = [
    # (pin, port, terminator)
    ("1",  "VBAT",  "@+3V3"),
    ("2",  "PC13",  "ADDR0"),
    ("3",  "PC14",  "ADDR1"),
    ("4",  "PC15",  "ADDR2"),
    ("5",  "PF0",   "OSC_IN"),
    ("6",  "PF1",   "OSC_OUT"),
    ("7",  "PG10",  "NRST"),
    ("8",  "PA0",   ">input:I_SENSE_A"),
    ("9",  "PA1",   ">input:I_SENSE_B"),
    ("10", "PA2",   ">input:I_SENSE_C"),
    ("11", "PA3",   ">input:VBUS_SENSE"),
    ("12", "PA4",   ">input:TEMP_MOTOR"),
    ("13", "PA5",   ">output:DRV_SCLK"),
    ("14", "PA6",   ">input:DRV_SDO"),
    ("15", "PA7",   ">output:DRV_SDI"),
    ("16", "PB0",   ">input:HALL_C"),
    ("17", "PB1",   ">input:TEMP_BOARD"),
    ("18", "PB2",   "ADDR3"),
    ("19", "VSSA",  "@GNDA"),
    ("20", "VREF+", "@+3V3A"),
    ("21", "VDDA",  "@+3V3A"),
    ("22", "PB10",  "UART_TX"),
    ("23", "VSS",   "@GND"),
    ("24", "VDD",   "@+3V3"),
    ("25", "PB11",  "UART_RX"),
    ("26", "PB12",  ">input:DRV_nFAULT"),
    ("27", "PB13",  ">output:PWM_AL"),
    ("28", "PB14",  ">output:PWM_BL"),
    ("29", "PB15",  ">output:PWM_CL"),
    ("30", "PA8",   ">output:PWM_AH"),
    ("31", "PA9",   ">output:PWM_BH"),
    ("32", "PA10",  ">output:PWM_CH"),
    ("33", "PA11",  ">input:CAN_RX"),
    ("34", "PA12",  ">output:CAN_TX"),
    ("35", "VSS",   "@GND"),
    ("36", "VDD",   "@+3V3"),
    ("37", "PA13",  "SWDIO"),
    ("38", "PA14",  "SWCLK"),
    ("39", "PA15",  ">output:DRV_nSCS"),
    ("40", "PB3",   "SWO"),
    ("41", "PB4",   ">input:HALL_A"),
    ("42", "PB5",   ">input:HALL_B"),
    ("43", "PB6",   ">input:ENC_Z"),
    ("44", "PB7",   "LED_RUN"),
    ("45", "PB8",   "BOOT0"),
    ("46", "PB9",   "LED_FAULT"),
    ("47", "VSS",   "@GND"),
    ("48", "VDD",   "@+3V3"),
]

# The supply pins sit shoulder to shoulder on the top and bottom edges, so
# their stubs are staggered to keep the rail symbols from colliding.
MCU_STUB = {"1": 5.08, "21": 10.16, "24": 15.24, "36": 20.32, "48": 25.4,
            "19": 5.08, "23": 10.16, "35": 15.24, "47": 20.32,
            "20": 7.62}


def build_mcu(lib):
    sh = new_sheet(lib, "mcu", "STM32G431CBT6, clock, debug and I/O", "3")

    u3 = sh.place("U3", "MCU_ST_STM32G4:STM32G431CBTx", "STM32G431CBT6", at=(150, 150),
                  footprint=FP["LQFP48"],
                  # keep the fields clear of the supply pins on the top edge
                  field_at={"Reference": (-15.24, 41.91), "Value": (-15.24, 44.45)})
    for pin, _port, spec in MCU_PINS:
        term(sh, u3, pin, spec, MCU_STUB.get(pin, 2.54))

    # ---- decoupling ------------------------------------------------------
    sh.text("Decoupling: one 100 nF per supply pin, placed at the pin", (25, 30), 2)
    for i, ref in enumerate(("C19", "C20", "C21", "C22")):
        cap(sh, ref, "100nF/16V", (30 + i * 13, 45), "@+3V3", "@GND")
    cap(sh, "C23", "4.7uF/16V", (82, 45), "@+3V3", "@GND", fp="C_0805")
    # Analog supply: VDDA and VREF+ share the ferrite-filtered rail
    cap(sh, "C24", "1uF/16V", (108, 45), "@+3V3A", "@GNDA")
    cap(sh, "C25", "100nF/16V", (121, 45), "@+3V3A", "@GNDA")

    # ---- 8 MHz HSE -------------------------------------------------------
    sh.text("8 MHz HSE - PLL to 170 MHz, needed for CAN bit timing", (25, 75), 2)
    y1 = sh.place("Y1", "Device:Crystal_GND24", "8MHz 10ppm", at=(60, 95), rot=0,
                  footprint=FP["XTAL"])
    term(sh, y1, "1", "OSC_IN", 3.81)
    term(sh, y1, "3", "OSC_OUT", 3.81)
    term(sh, y1, "2", "@GND", 3.81)
    term(sh, y1, "4", "@GND", 3.81)
    cap(sh, "C26", "12pF", (35, 110), "OSC_IN", "@GND")
    cap(sh, "C27", "12pF", (85, 110), "OSC_OUT", "@GND")

    # ---- reset and boot --------------------------------------------------
    cap(sh, "C28", "100nF", (35, 145), "NRST", "@GND")
    res(sh, "R12", "10k", (35, 175), "BOOT0", "@GND")
    jp1 = sh.place("JP1", "Connector_Generic:Conn_01x02", "BOOT0 sel", at=(72, 175),
                   footprint=FP["HDR2"])
    term(sh, jp1, "1", "@+3V3", 5.08)
    term(sh, jp1, "2", "BOOT0", 5.08)

    # ---- SWD and debug UART ---------------------------------------------
    sh.text("SWD (Cortex-M pinout) and debug UART", (25, 200), 2)
    j4 = sh.place("J4", "Connector_Generic:Conn_01x06", "SWD", at=(60, 225),
                  footprint=FP["SWD6"])
    for pin, spec in (("1", "@+3V3"), ("2", "SWCLK"), ("3", "@GND"),
                      ("4", "SWDIO"), ("5", "NRST"), ("6", "SWO")):
        term(sh, j4, pin, spec, 5.08)

    j5 = sh.place("J5", "Connector_Generic:Conn_01x04", "UART", at=(120, 225),
                  footprint=FP["HDR4"])
    for pin, spec in (("1", "@GND"), ("2", "UART_TX"), ("3", "UART_RX"), ("4", "@+3V3")):
        term(sh, j5, pin, spec, 5.08)

    # ---- node address DIP switch ----------------------------------------
    sh.text("Node address - 16 actuators per bus; switch closed = 0", (250, 200), 2)
    sw1 = sh.place("SW1", "Switch:SW_DIP_x04", "node addr", at=(300, 230),
                   footprint=FP["DIP4"])
    for pin, net in (("1", "ADDR0"), ("2", "ADDR1"), ("3", "ADDR2"), ("4", "ADDR3")):
        term(sh, sw1, pin, net, 5.08)
    for pin in ("5", "6", "7", "8"):
        term(sh, sw1, pin, "@GND", 5.08)
    for i, (ref, net) in enumerate((("R13", "ADDR0"), ("R14", "ADDR1"),
                                    ("R15", "ADDR2"), ("R16", "ADDR3"))):
        res(sh, ref, "10k", (250 + i * 13, 262), "@+3V3", net)

    # ---- status LEDs -----------------------------------------------------
    for ref_r, ref_d, net, colour, x in (("R17", "D5", "LED_RUN", "green RUN", 250),
                                         ("R18", "D6", "LED_FAULT", "red FAULT", 285)):
        res(sh, ref_r, "1k", (x, 45), net, f"{ref_d}_A")
        led = sh.place(ref_d, "Device:LED", colour, at=(x, 70), rot=90,
                       footprint=FP["LED"])
        term(sh, led, "2", f"{ref_d}_A", 3.81)
        term(sh, led, "1", "@GND", 3.81)
    return sh


# --------------------------------------------------------------------------
# Sheet 4: can
# --------------------------------------------------------------------------


def build_can(lib):
    sh = new_sheet(lib, "can", "CAN-FD transceiver and bus interface", "4")

    sh.text("TJA1042T/3 - 5 V bus driver with 3.3 V logic supply (VIO)", (25, 30), 2)
    u4 = sh.place("U4", "Interface_CAN_LIN:TJA1042T-3", "TJA1042T/3", at=(110, 90),
                  footprint=FP["SOIC8"])
    term(sh, u4, "1", ">input:CAN_TX", 7.62)     # TXD
    term(sh, u4, "4", ">output:CAN_RX", 7.62)    # RXD
    term(sh, u4, "3", "@+5V", 5.08)              # VCC
    term(sh, u4, "5", "@+3V3", 12.7)             # VIO
    term(sh, u4, "2", "@GND", 5.08)              # GND
    term(sh, u4, "8", "CAN_STB", 17.78)          # STB
    term(sh, u4, "7", "CANH", 5.08)
    term(sh, u4, "6", "CANL", 5.08)

    cap(sh, "C29", "100nF/16V", (75, 45), "@+5V", "@GND")
    cap(sh, "C30", "100nF/16V", (88, 45), "@+3V3", "@GND")
    # STB low keeps the transceiver in normal mode.  Lift the resistor and
    # drive the pad from a spare GPIO if bus standby is wanted.
    res(sh, "R19", "10k", (60, 120), "CAN_STB", "@GND")

    # ---- bus side: ESD clamps, split termination, daisy-chain -----------
    sh.text("Split termination (fit JP2 on the two end nodes only)", (170, 30), 2)
    d7 = sh.place("D7", "Power_Protection:NUP2105L", "NUP2105L", at=(170, 95),
                  footprint=FP["SOT23"])
    term(sh, d7, "1", "CANH", 5.08)
    term(sh, d7, "2", "CANL", 10.16)
    term(sh, d7, "3", "@GND", 5.08)

    jp2 = sh.place("JP2", "Connector_Generic:Conn_01x02", "120R term", at=(215, 78),
                   footprint=FP["HDR2"])
    term(sh, jp2, "1", "CANH", 5.08)
    term(sh, jp2, "2", "TERM_H", 5.08)
    res(sh, "R20", "60R4 1%", (240, 85), "TERM_H", "TERM_MID")
    res(sh, "R21", "60R4 1%", (240, 110), "TERM_MID", "CANL")
    cap(sh, "C31", "4.7nF/50V", (262, 98), "TERM_MID", "@GND")

    sh.text("CAN daisy-chain: J2 in, J3 out (wired in parallel)", (300, 30), 2)
    for ref, y in (("J2", 70), ("J3", 110)):
        j = sh.place(ref, "Connector_Generic:Conn_01x03", "CAN", at=(330, y),
                     footprint=FP["GH3"])
        term(sh, j, "1", "CANH", 7.62)
        term(sh, j, "2", "CANL", 7.62)
        term(sh, j, "3", "@GND", 7.62)

    for i, (ref, net) in enumerate((("TP5", "CANH"), ("TP6", "CANL"))):
        tp = sh.place(ref, "Connector:TestPoint", net, at=(300 + i * 15, 160), rot=180,
                      footprint=FP["TP"])
        term(sh, tp, "1", net, 2.54)
    return sh


# --------------------------------------------------------------------------
# Sheet 5: motor
# --------------------------------------------------------------------------


def build_motor(lib):
    sh = new_sheet(lib, "motor", "DRV8311S three-phase stage and feedback", "5")

    sh.text("DRV8311S - integrated three-phase bridge, 3..20 V, 5 A peak,", (25, 26), 2)
    sh.text("three integrated current-sense amplifiers, SPI control", (25, 32), 2)
    u5 = sh.place("U5", f"{LIBNAME}:DRV8311S", "DRV8311S", at=(150, 110),
                  footprint=FP["QFN24"])

    for pin, spec in (("15", ">input:PWM_AH"), ("18", ">input:PWM_AL"),
                      ("14", ">input:PWM_BH"), ("19", ">input:PWM_BL"),
                      ("13", ">input:PWM_CH"), ("20", ">input:PWM_CL"),
                      ("23", ">input:DRV_SCLK"), ("22", ">input:DRV_SDI"),
                      ("24", ">input:DRV_nSCS"), ("21", ">output:DRV_SDO"),
                      ("1", "DRV_nFAULT")):
        term(sh, u5, pin, spec, 5.08)

    for pin, spec in (("10", "PHASE_A"), ("11", "PHASE_B"), ("12", "PHASE_C"),
                      ("5", "SOA_RAW"), ("4", "SOB_RAW"), ("3", "SOC_RAW"),
                      ("2", "@+3V3"), ("17", "AVDD")):
        term(sh, u5, pin, spec, 5.08)

    term(sh, u5, "8", "@VM", 7.62)          # VM
    term(sh, u5, "7", "@VM", 12.7)          # VIN_AVDD: internal LDO input
    term(sh, u5, "6", "CP", 7.62)           # charge pump
    term(sh, u5, "9", "@GND", 7.62)         # PGND
    term(sh, u5, "25", "@GND", 12.7)        # PGND / exposed pad
    term(sh, u5, "16", "@GND", 17.78)       # AGND

    # ---- driver support components --------------------------------------
    cap(sh, "C32", "1uF/25V", (90, 55), "CP", "@VM")
    cap(sh, "C33", "1uF/10V", (108, 55), "AVDD", "@GND")
    cap(sh, "C34", "100nF/16V", (126, 55), "@+3V3", "@GND")
    res(sh, "R22", "10k", (60, 55), "@+3V3", ">output:DRV_nFAULT")

    cap_pol(sh, "C35", "220uF/35V", (60, 160), "@VM", "@GND", fp="CP")
    cap(sh, "C36", "10uF/35V", (78, 160), "@VM", "@GND", fp="C_1206")
    cap(sh, "C37", "100nF/50V", (96, 160), "@VM", "@GND")

    # ---- current-sense conditioning -------------------------------------
    sh.text("ADC input networks - charge reservoir for the SAR sampling", (215, 26), 2)
    sh.text("capacitor, fc ~ 1.6 MHz (settles inside the sample window)", (215, 32), 2)
    for ref_r, ref_c, raw, out, y in (("R23", "C38", "SOA_RAW", "I_SENSE_A", 55),
                                      ("R24", "C39", "SOB_RAW", "I_SENSE_B", 80),
                                      ("R25", "C40", "SOC_RAW", "I_SENSE_C", 105)):
        res(sh, ref_r, "100R", (240, y), raw, out, rot=90)
        cap(sh, ref_c, "1nF", (262, y + 12), f">output:{out}", "@GND")

    # ---- motor phase output ---------------------------------------------
    j6 = sh.place("J6", "Connector_Generic:Conn_01x03", "MOTOR A/B/C", at=(330, 105),
                  footprint=FP["TERM3"])
    term(sh, j6, "1", "PHASE_A", 7.62)
    term(sh, j6, "2", "PHASE_B", 7.62)
    term(sh, j6, "3", "PHASE_C", 7.62)
    for i, net in enumerate(("PHASE_A", "PHASE_B", "PHASE_C")):
        tp = sh.place(f"TP{7 + i}", "Connector:TestPoint", net, at=(300 + i * 15, 150),
                      rot=180, footprint=FP["TP"])
        term(sh, tp, "1", net, 2.54)

    # ---- feedback: Hall / encoder / motor NTC ---------------------------
    sh.text("Feedback: Hall (TIM3 XOR) or quadrature encoder + motor NTC", (215, 175), 2)
    j7 = sh.place("J7", "Connector_Generic:Conn_01x08", "FEEDBACK", at=(330, 215),
                  footprint=FP["GH8"])
    term(sh, j7, "1", "ENC_VCC", 7.62)
    term(sh, j7, "2", "@GND", 7.62)
    term(sh, j7, "3", "HALL_A_IN", 7.62)
    term(sh, j7, "4", "HALL_B_IN", 7.62)
    term(sh, j7, "5", "HALL_C_IN", 7.62)
    term(sh, j7, "6", "ENC_Z_IN", 7.62)
    term(sh, j7, "7", "NTC_IN", 7.62)
    term(sh, j7, "8", "@GND", 12.7)

    # Encoder supply selector: 5 V for open-collector Hall sensors, 3.3 V for
    # push-pull encoders that must not over-drive the 3.3 V inputs.
    jp3 = sh.place("JP3", "Connector_Generic:Conn_01x03", "ENC 5V/3V3", at=(250, 215),
                   footprint=FP["HDR3"])
    term(sh, jp3, "1", "@+5V", 7.62)
    term(sh, jp3, "2", "ENC_VCC", 7.62)
    term(sh, jp3, "3", "@+3V3", 7.62)

    # Inputs are pulled to 3.3 V so open-collector Hall sensors running from
    # 5 V still present a 3.3 V logic high to the MCU.
    for i, (ref_r, ref_c, ref_s, src, dst) in enumerate((
            ("R26", "C41", "R30", "HALL_A_IN", "HALL_A"),
            ("R27", "C42", "R31", "HALL_B_IN", "HALL_B"),
            ("R28", "C43", "R32", "HALL_C_IN", "HALL_C"),
            ("R29", "C44", "R33", "ENC_Z_IN", "ENC_Z"))):
        x = 40 + i * 40
        res(sh, ref_r, "2k2", (x, 205), "@+3V3", src)
        res(sh, ref_s, "100R", (x + 18, 225), src, dst, rot=90)
        cap(sh, ref_c, "1nF", (x + 30, 240), f">output:{dst}", "@GND")

    res(sh, "R34", "10k 1%", (210, 255), "@+3V3", "NTC_IN")
    res(sh, "R35", "1k", (228, 268), "NTC_IN", "TEMP_MOTOR", rot=90)
    cap(sh, "C45", "100nF", (250, 268), ">output:TEMP_MOTOR", "@GND")
    return sh


# --------------------------------------------------------------------------
# Sheet 1: root
# --------------------------------------------------------------------------

# Cross-sheet nets are carried by hierarchical labels in the child sheets and
# joined on the root sheet by plain labels of the same name, so the root stays
# readable instead of turning into a bundle of long wires.

SHEET_LAYOUT = [
    ("power", (30, 35), (95, 35), "right"),
    ("mcu",   (30, 95), (95, 140), "right"),
    ("can",   (255, 35), (95, 35), "left"),
    ("motor", (255, 95), (95, 140), "left"),
]


def build_root(lib, children):
    sh = new_sheet(lib, "root", "Top level", "1")
    sh.text("STM32G431 CAN-FD actuator node - one node per actuator", (30, 22), 3)
    sh.text("Bus: FDCAN1 at 1 Mbit/s arbitration, up to 5 Mbit/s data.", (30, 250), 2)
    sh.text("Rails: VM (9-18 V) -> 5 V buck -> 3.3 V LDO -> filtered 3.3 V analog.",
            (30, 258), 2)

    by_name = {c.name: c for c in children}
    for name, at, size, side in SHEET_LAYOUT:
        child = by_name[name]
        ref = add_sheet_ref(sh, child, at, size, child.page)
        seen = []
        for lname, shape, _x, _y, _a in child.hlabels:
            if lname not in [s[0] for s in seen]:
                seen.append((lname, shape))
        for i, (lname, shape) in enumerate(seen):
            px, py = ref.pin(lname, shape, side, 5.08 + i * 5.08)
            if side == "right":
                end = sh.wire((px, py), (px + 7.62, py))
                sh.label(lname, end, 0)
            else:
                end = sh.wire((px, py), (px - 7.62, py))
                sh.label(lname, end, 180)
    return sh


# --------------------------------------------------------------------------
# Project scaffolding
# --------------------------------------------------------------------------


def write_project(path, root):
    import json
    text = f"""{{
  "board": {{
    "design_settings": {{
      "defaults": {{}},
      "rules": {{}}
    }}
  }},
  "boards": [],
  "libraries": {{
    "pinned_footprint_libs": [],
    "pinned_symbol_libs": []
  }},
  "meta": {{
    "filename": "{PROJECT}.kicad_pro",
    "version": 1
  }},
  "net_settings": {{
    "classes": [
      {{
        "bus_width": 12,
        "clearance": 0.2,
        "diff_pair_gap": 0.25,
        "diff_pair_via_gap": 0.25,
        "diff_pair_width": 0.2,
        "line_style": 0,
        "microvia_diameter": 0.3,
        "microvia_drill": 0.1,
        "name": "Default",
        "pcb_color": "rgba(0, 0, 0, 0.000)",
        "schematic_color": "rgba(0, 0, 0, 0.000)",
        "track_width": 0.25,
        "via_diameter": 0.6,
        "via_drill": 0.3,
        "wire_width": 6
      }},
      {{
        "bus_width": 12,
        "clearance": 0.3,
        "diff_pair_gap": 0.25,
        "diff_pair_via_gap": 0.25,
        "diff_pair_width": 0.2,
        "line_style": 0,
        "microvia_diameter": 0.3,
        "microvia_drill": 0.1,
        "name": "Power",
        "pcb_color": "rgba(0, 0, 0, 0.000)",
        "schematic_color": "rgba(0, 0, 0, 0.000)",
        "track_width": 1.0,
        "via_diameter": 0.8,
        "via_drill": 0.4,
        "wire_width": 6
      }},
      {{
        "bus_width": 12,
        "clearance": 0.2,
        "diff_pair_gap": 0.2,
        "diff_pair_via_gap": 0.25,
        "diff_pair_width": 0.25,
        "line_style": 0,
        "microvia_diameter": 0.3,
        "microvia_drill": 0.1,
        "name": "CAN",
        "pcb_color": "rgba(0, 0, 0, 0.000)",
        "schematic_color": "rgba(0, 0, 0, 0.000)",
        "track_width": 0.25,
        "via_diameter": 0.6,
        "via_drill": 0.3,
        "wire_width": 6
      }}
    ],
    "meta": {{
      "version": 3
    }},
    "net_colors": null,
    "netclass_assignments": null,
    "netclass_patterns": [
      {{ "netclass": "Power", "pattern": "VM" }},
      {{ "netclass": "Power", "pattern": "GND" }},
      {{ "netclass": "Power", "pattern": "+5V" }},
      {{ "netclass": "Power", "pattern": "+3V3" }},
      {{ "netclass": "Power", "pattern": "PHASE_?" }},
      {{ "netclass": "CAN", "pattern": "CANH" }},
      {{ "netclass": "CAN", "pattern": "CANL" }}
    ]
  }},
  "pcbnew": {{
    "last_paths": {{
      "gencad": "",
      "idf": "",
      "netlist": "",
      "specctra_dsn": "",
      "step": "",
      "vrml": ""
    }},
    "page_layout_descr_file": ""
  }},
  "schematic": {{
    "annotate_start_num": 0,
    "drawing": {{
      "default_line_thickness": 6.0,
      "default_text_size": 50.0,
      "field_names": [],
      "intersheets_ref_own_page": false,
      "intersheets_ref_prefix": "",
      "intersheets_ref_short": false,
      "intersheets_ref_show": false,
      "intersheets_ref_suffix": "",
      "junction_size_choice": 3,
      "label_size_ratio": 0.375,
      "pin_symbol_size": 25.0,
      "text_offset_ratio": 0.15
    }},
    "legacy_lib_dir": "",
    "legacy_lib_list": [],
    "meta": {{
      "version": 1
    }},
    "net_format_name": "",
    "page_layout_descr_file": "",
    "plot_directory": "",
    "spice_current_sheet_as_root": false,
    "spice_external_command": "spice \\"%I\\"",
    "spice_model_current_sheet_as_root": true,
    "spice_save_all_currents": false,
    "spice_save_all_voltages": false,
    "subpart_first_id": 65,
    "subpart_id_separator": 0
  }},
  "sheets": SHEETS_PLACEHOLDER,
  "text_variables": {{}}
}}
"""
    sheet_list = [[root.uuid, ""]] + [[uuid_for("sheetobj", n), n]
                                      for n, _a, _s, _side in SHEET_LAYOUT]
    text = text.replace("SHEETS_PLACEHOLDER", json.dumps(sheet_list, indent=2))
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


SYM_LIB_TABLE = """(sym_lib_table
  (version 7)
  (lib (name "{name}")(type "KiCad")(uri "${{KIPRJMOD}}/lib/{name}.kicad_sym")(options "")(descr "Project symbols for {name}"))
)
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--symbol-dir", action="append", default=None,
                    help="KiCad symbol library directory (repeatable)")
    ap.add_argument("--out", default=ROOT, help="project directory")
    args = ap.parse_args()

    out = args.out
    os.makedirs(os.path.join(out, "lib"), exist_ok=True)
    lib_path = os.path.join(out, "lib", f"{LIBNAME}.kicad_sym")
    build_project_library(lib_path)

    lib = SymbolLib(search_dirs=args.symbol_dir, extra_libs={LIBNAME: lib_path})

    power, mcu, can, motor = build_power(lib), build_mcu(lib), build_can(lib), build_motor(lib)
    children = [power, mcu, can, motor]
    root = build_root(lib, children)
    for child in children:
        child.root_uuid = root.uuid

    written = []
    for sheet, fname in [(root, f"{PROJECT}.kicad_sch")] + [
            (c, f"{c.name}.kicad_sch") for c in children]:
        path = os.path.join(out, fname)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(render_sheet(sheet, title_block))
        written.append((fname, len(sheet.comps), len(sheet.wires), len(sheet.labels)))

    write_project(os.path.join(out, f"{PROJECT}.kicad_pro"), root)
    with open(os.path.join(out, "sym-lib-table"), "w", encoding="utf-8") as fh:
        fh.write(SYM_LIB_TABLE.format(name=LIBNAME))

    for fname, nc, nw, nl in written:
        print(f"  {fname:34s} {nc:3d} symbols  {nw:3d} wires  {nl:3d} labels")
    total = sum(1 for c in (power, mcu, can, motor) for _ in c.comps)
    print(f"  {total} placed symbols across {len(children)} child sheets")


if __name__ == "__main__":
    main()
