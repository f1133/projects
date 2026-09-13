"""Juno board specifications.

The single machine-readable source for both KiCad projects. Transcribed from
the build console (`vendor/build_console.html`): its Schematic tab wiring
diagrams define connectivity, its BOM tab defines parts, and `06_electrical.md`
defines the pin assignment.

Pins are named, not numbered. Every reference is resolved against the real
symbol at generation time and an unknown pin is a hard error, so a typo cannot
silently become a missing connection. `NAME*` matches every pin with that name
(the G431 has three VSS pins and three VDD pins).

Deviations from the console are marked DEVIATION and explained. Contradictions
found in the source are marked CONFLICT and resolved explicitly.
"""

# ---------------------------------------------------------------------------
# Library shorthand
# ---------------------------------------------------------------------------
DEV, CONN, JUMP = "Device", "Connector_Generic", "Jumper"
R_1206 = ("Resistor_SMD", "R_1206_3216Metric")
C_1206 = ("Capacitor_SMD", "C_1206_3216Metric")
LED_1206 = ("LED_SMD", "LED_1206_3216Metric")
SOIC8 = ("Package_SO", "SOIC-8_3.9x4.9mm_P1.27mm")


def R(ref, val, fp=R_1206, **kw):
    return dict(ref=ref, value=val, lib=DEV, sym="R", fp=fp, **kw)


def C(ref, val, fp=C_1206, **kw):
    return dict(ref=ref, value=val, lib=DEV, sym="C", fp=fp, **kw)


# ===========================================================================
# ACTUATOR NODE  —  STM32G431 CAN-FD joint controller
# ===========================================================================
# Board is 50 x 45 mm. The gearbox occupies a O48 circle centred on the board
# with only 5.5 mm of height under it; every through-hole part therefore lives
# in a corner, outside that circle, where height is unlimited.

ACTUATOR_PARTS = [
    # --- core ---------------------------------------------------------------
    dict(ref="U1", value="STM32G431CBT6", lib="MCU_ST_STM32G4", sym="STM32G431CBTx",
         fp=("Package_QFP", "LQFP-48_7x7mm_P0.5mm"),
         note="170 MHz M4F. 8 kHz FOC current loop."),
    dict(ref="U2", value="SN65HVD230", lib="Interface_CAN_LIN", sym="SN65HVD230", fp=SOIC8,
         note="3.3 V CAN transceiver. Rs to GND = high speed."),
    dict(ref="U4", value="INA240A1D", lib="Amplifier_Current", sym="INA240A1D", fp=SOIC8,
         note="Phase A current sense, gain 20 V/V."),
    dict(ref="U5", value="INA240A1D", lib="Amplifier_Current", sym="INA240A1D", fp=SOIC8,
         note="Phase B current sense, gain 20 V/V."),
    dict(ref="U6", value="AMS1117-3.3", lib="Regulator_Linear", sym="AMS1117-3.3",
         fp=("Package_TO_SOT_SMD", "SOT-223-3_TabPin2"),
         note="5 V from the CAN harness down to 3.3 V local."),
    # Reference is A1, not M1: the module's own silkscreen calls its three
    # motor pads M1/M2/M3, and ("M1", "M1") in a netlist helps nobody.
    dict(ref="A1", value="SimpleFOC Mini v1.0", lib="juno", sym="SimpleFOC_Mini",
         fp=("juno", "SimpleFOC_Mini_Socket"),
         note="DRV8313 module on female headers. Geometry and pinout are read "
              "from the vendor's EasyEDA exports; see CONFLICT-4."),

    # --- clock --------------------------------------------------------------
    dict(ref="Y1", value="8 MHz", lib=DEV, sym="Crystal",
         fp=("Crystal", "Crystal_SMD_HC49-SD_HandSoldering"),
         note="20 pF load. Not optional: FDCAN bit timing needs it."),
    C("C1", "30 pF"), C("C2", "30 pF"),

    # --- current sense ------------------------------------------------------
    R("R1", "30 mR"), R("R2", "30 mR"),

    # --- analog dividers ----------------------------------------------------
    R("R3", "100k"),   # Vbus divider top, off the 19 V rail
    R("R4", "4k7"),    # Vbus divider bottom
    R("R5", "4k7"),    # NTC pull-up to 3V3

    # --- pull resistors -----------------------------------------------------
    R("R6", "10k"),    # PB8 / BOOT0 pull-down, see CONFLICT-2
    R("R7", "10k"),    # driver EN pull-down: unpowered controller means motors off
    R("R8", "10k"), R("R9", "10k"), R("R10", "10k"),   # node ID pull-ups
    R("R12", "120R"),  # CAN termination, behind a solder jumper
    R("R13", "120R"),  # status LED series, sized for Vf 2.4 V

    # XL-3216SURC: red, 1206, Vf 2.4 V at 20 mA, 225 mcd. Only 0.9 V of
    # headroom on a 3.3 V rail, so the series value sets the current sharply.
    # 120 R gives 7.5 mA - bright, inside the LED's 20 mA and well inside what
    # a G431 pin will source - and it is a value already in stock.
    dict(ref="D1", value="XL-3216SURC red", lib=DEV, sym="LED", fp=LED_1206,
         note="status / functioning, driven from PC13"),
    # ADDED: the console has one LED. A rail that is simply on or off is the
    # first thing you want to see when a board does not enumerate, so the 3V3
    # rail gets its own indicator that owes nothing to firmware.
    dict(ref="D2", value="XL-3216SURC red", lib=DEV, sym="LED", fp=LED_1206,
         note="ADDED: 3V3 present. Lit means the LDO is up, firmware or not."),
    R("R14", "120R"),
    dict(ref="JP1", value="TERM", lib=JUMP, sym="SolderJumper_2_Open",
         fp=("Jumper", "SolderJumper-2_P1.3mm_Open_Pad1.0x1.5mm"),
         note="Close on the two physical ends of the bus only."),
    dict(ref="JP2", value="ID0", lib=JUMP, sym="SolderJumper_2_Open",
         fp=("Jumper", "SolderJumper-2_P1.3mm_Open_Pad1.0x1.5mm")),
    dict(ref="JP3", value="ID1", lib=JUMP, sym="SolderJumper_2_Open",
         fp=("Jumper", "SolderJumper-2_P1.3mm_Open_Pad1.0x1.5mm")),
    dict(ref="JP4", value="ID2", lib=JUMP, sym="SolderJumper_2_Open",
         fp=("Jumper", "SolderJumper-2_P1.3mm_Open_Pad1.0x1.5mm")),

    # --- bulk and decoupling ------------------------------------------------
    dict(ref="C19", value="470uF/50V", lib=DEV, sym="C_Polarized",
         fp=("Capacitor_SMD", "CP_Elec_10x10.5"),
         note="Bulk at the Mini VIN. Polarised - check orientation twice."),
    C("C20", "10uF"), C("C21", "10uF"), C("C22", "10uF"),
    C("C17", "1uF"), C("C18", "1uF"),                       # VDDA and VREF+
]
# 100 nF decoupling: 3x VDD, VDDA, VREF+, 2x INA, CAN, LDO in/out, NRST,
# Vbus filter, NTC filter.
ACTUATOR_PARTS += [C(f"C{n}", "100nF") for n in range(3, 17)]

ACTUATOR_PARTS += [
    # --- connectors, all in the corners outside the O48 circle ---------------
    dict(ref="J1", value="PHASES", lib=CONN, sym="Conn_01x03",
         fp=("Connector_JST", "JST_XH_B3B-XH-A_1x03_P2.50mm_Vertical"),
         note="Motor phases A B C."),
    dict(ref="J2", value="CAN IN", lib=CONN, sym="Conn_01x05",
         fp=("Connector_JST", "JST_XH_B5B-XH-AM_1x05_P2.50mm_Vertical"),
         note="CANH CANL EN 5V GND."),
    dict(ref="J3", value="CAN EXT", lib=CONN, sym="Conn_01x05",
         fp=("Connector_JST", "JST_XH_B5B-XH-AM_1x05_P2.50mm_Vertical"),
         note="Daisy chain, wired in parallel with J2."),
    dict(ref="J4", value="19V IN", lib=CONN, sym="Conn_01x02",
         fp=("Connector_JST", "JST_VH_B2P-VH_1x02_P3.96mm_Vertical"),
         note="Motor bus straight from the brick."),
    dict(ref="J5", value="SWD", lib=CONN, sym="Conn_01x05",
         fp=("Connector_PinHeader_2.54mm", "PinHeader_1x05_P2.54mm_Vertical"),
         note="3V3 SWDIO SWCLK NRST GND. NRST is the one people skip and regret."),
    dict(ref="J6", value="ENCODER", lib=CONN, sym="Conn_01x04",
         fp=("Connector_PinHeader_2.54mm", "PinHeader_1x04_P2.54mm_Vertical"),
         note="DEVIATION: encoder is motor-mounted, so 3V3 GND SCL SDA leave "
              "on a cable instead of an AS5600 soldered through the board."),
    dict(ref="J7", value="NTC", lib=CONN, sym="Conn_01x02",
         fp=("Connector_JST", "JST_XH_B2B-XH-A_1x02_P2.50mm_Vertical"),
         note="Thermistor bead lives inside the stator, not on the board."),
]


# ---------------------------------------------------------------------------
# CONFLICT-1  INA240 pinout: the build console disagrees with the KiCad symbol.
#   console : 1 IN+  4 REF1  7 NC   8 IN-
#   KiCad   : 1 IN-  4 GND   7 REF1 8 IN+
#   Resolved in favour of KiCad. The console's pin numbers are demonstrably
#   unreliable (its MCU diagram gives both NRST and VSSA as pin 7), and two
#   independent sources corroborate pin 4 = GND and pin 7 = REF1. Taking the
#   console's numbering would have driven the chip's ground pin to 3V3.
#   Because every net below is written by pin NAME, the numbering comes from
#   the symbol and stays consistent with the footprint pads either way.
#   Still worth one look at the datasheet before you order.
#
# CONFLICT-2  BOOT0 does not exist as a separate pin on the LQFP-48 G431.
#   It is multiplexed onto PB8, which the pin assignment gives to FDCAN1_RX.
#   The console's MCU diagram draws a standalone BOOT0 pin with a pull-down;
#   that pin is not there. R6 is therefore a pull-down on PB8 itself.
#   By factory default nBOOT_SEL=1 and the pin is ignored, so this is latent
#   rather than broken - but if nBOOT_SEL is ever cleared, an idle (recessive)
#   bus holds the transceiver's R output high at reset and the part boots the
#   ROM bootloader instead of your firmware. FDCAN1 can move to PA11/PA12,
#   which are otherwise unused, if you want PB8 free. Settle it in CubeMX (A4).
#
# CONFLICT-3  Shunt sense polarity. The console's drawing wires IN+ to the
#   driver side of the shunt; its caption says IN+ goes to the motor side.
#   Taken as drawn: IN+ driver side, IN- motor side, so output rises above
#   mid-rail for current flowing driver -> motor. This is a firmware sign
#   constant, not a wiring hazard - the note in the console agrees ("swapped,
#   the current reads negative").
#
# NRST is pin 7 / PG10 on this package; KiCad names it PG10.
# ---------------------------------------------------------------------------

# CONFLICT-4  The driver module, twice over.
#   First, the EasyEDA export originally supplied was a "step mini" - a quad
#   half-bridge with IN1-IN4 and four outputs - not the board on the bench. The
#   real one is the SimpleFOC Mini v1.0 (DRV8313, three phases, 2022-04), and
#   its export is what vendor/simplefoc_mini_v1.json now holds.
#   Second, and the reason this matters beyond pad positions: the module's 3V3
#   header pin is DRV8313 pin 15, V3P3OUT - an internal 3.3 V REGULATOR OUTPUT,
#   confirmed from the vendor schematic. An earlier revision of this file tied
#   it to the carrier's 3.3 V rail on the assumption it was a supply input,
#   which would have connected the AMS1117's output to the module's regulator.
#   It is left open. The module's nSlp / nRes / nFlt pull-ups are fed from it
#   internally, which is why those three pins need no connection to idle in the
#   running state.

ACTUATOR_NETS = {
    # --- rails --------------------------------------------------------------
    "+19V": [("J4", "Pin_1"), ("A1", "VM"), ("C19", "1"), ("R3", "1")],
    "+5V": [("J2", "Pin_4"), ("J3", "Pin_4"), ("U6", "VI"), ("C11", "1"), ("C20", "1")],
    "+3V3": [
        ("U6", "VO"), ("C12", "1"), ("C21", "1"), ("C22", "1"),
        ("U1", "VDD*"), ("U1", "VDDA"), ("U1", "VBAT"), ("U1", "VREF+"),
        ("C3", "1"), ("C4", "1"), ("C5", "1"), ("C6", "1"), ("C7", "1"), ("C16", "1"),
        ("C17", "1"), ("C18", "1"),
        ("U2", "VCC"), ("C10", "1"),
        ("U4", "V+"), ("C8", "1"), ("U5", "V+"), ("C9", "1"),
        ("U4", "REF1"), ("U5", "REF1"),          # REF1 high + REF2 low = mid-rail
        ("J5", "Pin_1"), ("J6", "Pin_1"),
        ("R5", "1"), ("R8", "1"), ("R9", "1"), ("R10", "1"),
        ("D2", "A"),                       # power LED straight off the rail
        # The driver module's 3V3 pin is deliberately absent here. It is
        # DRV8313 V3P3OUT, a regulator output - see CONFLICT-4.
    ],
    "GND": [
        ("J4", "Pin_2"), ("J2", "Pin_5"), ("J3", "Pin_5"), ("J5", "Pin_5"),
        ("J6", "Pin_2"), ("J7", "Pin_2"),
        ("A1", "GND*"), ("C19", "2"),
        ("U1", "VSS*"), ("U1", "VSSA"),
        ("U2", "GND"), ("U2", "Rs"),             # Rs to GND = high-speed mode
        ("U4", "GND*"), ("U5", "GND*"),
        ("U4", "REF2"), ("U5", "REF2"),
        ("U6", "GND"),
        ("C1", "2"), ("C2", "2"),
        ("C3", "2"), ("C4", "2"), ("C5", "2"), ("C6", "2"), ("C7", "2"), ("C8", "2"),
        ("C9", "2"), ("C10", "2"), ("C11", "2"), ("C12", "2"), ("C13", "2"),
        ("C14", "2"), ("C15", "2"), ("C16", "2"),
        ("C17", "2"), ("C18", "2"), ("C20", "2"), ("C21", "2"), ("C22", "2"),
        ("R4", "2"), ("R6", "2"), ("R7", "2"), ("R13", "2"), ("R14", "2"),
        ("JP2", "B"), ("JP3", "B"), ("JP4", "B"),
    ],

    # --- motor drive --------------------------------------------------------
    "PWM_A": [("U1", "PA8"), ("A1", "IN1")],
    "PWM_B": [("U1", "PA9"), ("A1", "IN2")],
    "PWM_C": [("U1", "PA10"), ("A1", "IN3")],
    # EN is the hardware kill line: it leaves on both CAN connectors so the
    # brain can pull every driver down at once, and R7 holds it off unpowered.
    "DRV_EN": [("U1", "PB12"), ("A1", "EN"), ("J2", "Pin_3"), ("J3", "Pin_3"), ("R7", "1")],

    # --- phases and current sense ------------------------------------------
    "PH_A_DRV": [("A1", "M1"), ("R1", "1"), ("U4", "+")],
    "PH_A": [("R1", "2"), ("J1", "Pin_1"), ("U4", "-")],
    "PH_B_DRV": [("A1", "M2"), ("R2", "1"), ("U5", "+")],
    "PH_B": [("R2", "2"), ("J1", "Pin_2"), ("U5", "-")],
    "PH_C": [("A1", "M3"), ("J1", "Pin_3")],
    # The module brings nFAULT out with its own pull-up. PB4 is free and this
    # is the difference between a driver that has tripped and a motor that is
    # merely not moving, so it is worth the pin.
    "DRV_nFAULT": [("A1", "nFlt"), ("U1", "PB4")],
    "ISENSE_A": [("U4", "~"), ("U1", "PA1")],
    "ISENSE_B": [("U5", "~"), ("U1", "PA3")],

    # --- encoder (motor-mounted, on a cable) --------------------------------
    "I2C_SCL": [("U1", "PB6"), ("J6", "Pin_3")],
    "I2C_SDA": [("U1", "PB7"), ("J6", "Pin_4")],

    # --- CAN ----------------------------------------------------------------
    "CAN_RX": [("U1", "PB8"), ("U2", "R"), ("R6", "1")],
    "CAN_TX": [("U1", "PB9"), ("U2", "D")],
    "CANH": [("U2", "CANH"), ("J2", "Pin_1"), ("J3", "Pin_1"), ("JP1", "A")],
    "CANL": [("U2", "CANL"), ("J2", "Pin_2"), ("J3", "Pin_2"), ("R12", "2")],
    "CAN_TERM": [("JP1", "B"), ("R12", "1")],

    # --- analog inputs ------------------------------------------------------
    "VBUS_SENSE": [("R3", "2"), ("R4", "1"), ("U1", "PB0"), ("C14", "1")],
    "NTC_SENSE": [("R5", "2"), ("J7", "Pin_1"), ("U1", "PA0"), ("C15", "1")],

    # --- node address -------------------------------------------------------
    "NODE_ID0": [("U1", "PB13"), ("R8", "2"), ("JP2", "A")],
    "NODE_ID1": [("U1", "PB14"), ("R9", "2"), ("JP3", "A")],
    "NODE_ID2": [("U1", "PB15"), ("R10", "2"), ("JP4", "A")],

    # --- debug and clock ----------------------------------------------------
    "SWDIO": [("U1", "PA13"), ("J5", "Pin_2")],
    "SWCLK": [("U1", "PA14"), ("J5", "Pin_3")],
    "NRST": [("U1", "PG10"), ("J5", "Pin_4"), ("C13", "1")],
    "OSC_IN": [("U1", "PF0"), ("Y1", "1"), ("C1", "1")],
    "OSC_OUT": [("U1", "PF1"), ("Y1", "2"), ("C2", "1")],

    # --- status -------------------------------------------------------------
    "LED_A": [("U1", "PC13"), ("D1", "A")],
    "LED_K": [("D1", "K"), ("R13", "1")],
    "PWR_LED_K": [("D2", "K"), ("R14", "1")],
}


# ===========================================================================
# MAIN BRAIN  —  ESP32-S3 controller in the base
# ===========================================================================
# "Everything that does not move. Two I2C devices, two microphones on a shared
# clock, the kill line and the power chain."  The mics set the board width:
# 130 mm apart is what turns two of them into a bearing.
#
# VERIFY-1  Module header geometry. The ESP32-S3 Super Mini and the SimpleFOC
#   Mini are third-party modules whose physical pin order could not be checked
#   from the generating environment. The SCHEMATIC is correct regardless -
#   every net is written by pin name - but the FOOTPRINT pad numbering follows
#   the tables in `modules.py`, which must be checked against the real board
#   with a 1:1 printout before ordering. This is the single highest-risk item
#   in both projects.

BRAIN_PARTS = [
    dict(ref="A1", value="ESP32-S3 Super Mini", lib="juno", sym="ESP32_S3_SuperMini",
         fp=("juno", "ESP32_S3_SuperMini_Socket"),
         note="Controller. 200 Hz control task, ESP-IDF."),
    dict(ref="A2", value="MP1584EN", lib="juno", sym="MP1584EN_Module",
         fp=("juno", "MP1584EN_Module"),
         note="19 V to 5 V for the whole robot. The only buck in the system."),
    dict(ref="A3", value="VL53L5CX", lib="juno", sym="Module_I2C_INT",
         fp=("juno", "Module_1x06_2.54"), note="8x8 depth imager, 0x29."),
    dict(ref="A4", value="MPR121", lib="juno", sym="Module_I2C_INT",
         fp=("juno", "Module_1x06_2.54"), note="12 touch pads, 0x5A."),
    dict(ref="A5", value="IMU", lib="juno", sym="Module_I2C_INT",
         fp=("juno", "Module_1x06_2.54"), note="0x68, glued flat in the base."),
    dict(ref="A6", value="INMP441 left", lib="juno", sym="INMP441",
         fp=("juno", "Module_1x06_2.54"), note="L/R tied low."),
    dict(ref="A7", value="INMP441 right", lib="juno", sym="INMP441",
         fp=("juno", "Module_1x06_2.54"), note="L/R tied high. 130 mm from A6."),

    dict(ref="U1", value="SN65HVD230", lib="Interface_CAN_LIN", sym="SN65HVD230", fp=SOIC8,
         note="Brain end of the CAN bus."),

    # --- power chain --------------------------------------------------------
    # Every barrel-jack footprint in the stock library has three pads, so the
    # switched symbol is the one that maps cleanly. Pin 3 is the plug-detect
    # switch, tied to the sleeve because nothing uses it.
    dict(ref="J1", value="19V", lib="Connector", sym="Barrel_Jack_Switch",
         fp=("Connector_BarrelJack", "BarrelJack_CUI_PJ-102AH_Horizontal"),
         note="5.5 x 2.1 mm, 19 V laptop brick. Star ground lands here."),
    # AO3481, the P-FET actually on hand: 30 V, 4.2 A, SOT-23. KiCad has no
    # AO3481 symbol; AO3401A is the same family and the same G/S/D pinout.
    dict(ref="Q1", value="AO3481", lib="Transistor_FET", sym="AO3401A",
         fp=("Package_TO_SOT_SMD", "SOT-23"),
         note="Reverse-polarity protection, high side."),
    # A 19 V input would sit right on the FET's gate-source rating with the
    # gate pulled to ground, so the gate is divided rather than clamped:
    # R9 source-to-gate and R6 gate-to-ground halve it to about -9.5 V, which
    # enhances the FET hard and stays well inside its rating. This replaces a
    # zener, which is not in stock, using two resistors that are.
    R("R6", "100k"),   # Q1 gate to ground
    R("R9", "100k"),   # Q1 source to gate

    # AO3400A: single N-channel, SOT-23, Vgs(th) 0.7 V so it is fully on from a
    # 3.3 V GPIO, and 30 mOhm where the job needs about 120 mA. Same family,
    # package and G/S/D pinout as Q1, which keeps the BOM tidy. A dual in
    # SOT-363 would also work electrically but puts a 0.65 mm pitch part on a
    # board meant to be hand-soldered, and leaves half a device to tie off.
    dict(ref="Q2", value="AO3400A", lib="Transistor_FET", sym="AO3400A",
         fp=("Package_TO_SOT_SMD", "SOT-23"),
         note="Hardware kill line. Deliberately not a CAN message."),
    R("R3", "10k"),    # kill gate pull-down
    R("R4", "120R"),   # kill gate series - 100R not in stock, 120R is identical here
    R("R1", "2k2"), R("R2", "2k2"),   # I2C pull-ups, master end only
    R("R5", "120R"),   # CAN termination: the brain is one physical end
    dict(ref="JP1", value="TERM", lib=JUMP, sym="SolderJumper_2_Open",
         fp=("Jumper", "SolderJumper-2_P1.3mm_Open_Pad1.0x1.5mm")),

    dict(ref="C1", value="470uF/50V", lib=DEV, sym="C_Polarized",
         fp=("Capacitor_SMD", "CP_Elec_10x10.5"), note="19 V input bulk."),
    C("C2", "10uF"), C("C3", "10uF"), C("C4", "100nF"), C("C5", "10uF"),

    # ADDED: indicators. D2 is wired to the 5 V rail rather than 3V3 so it
    # reports the buck, which is the thing that actually fails - the S3's own
    # regulator is downstream of it. D3 is a firmware heartbeat; the module has
    # an LED on IO48 but it is buried once the board is in the base.
    # Same XL-3216SURC part as the node board - it is the only LED on hand.
    # D1 runs off 5 V, where 120 R would exceed the LED's 20 mA rating, so it
    # takes 1 k for 2.6 mA. D2 is on a 3.3 V GPIO and takes 120 R for 7.5 mA.
    dict(ref="D1", value="XL-3216SURC red", lib=DEV, sym="LED", fp=LED_1206,
         note="ADDED: 5 V rail present, straight off the buck output."),
    R("R7", "1k"),
    dict(ref="D2", value="XL-3216SURC red", lib=DEV, sym="LED", fp=LED_1206,
         note="ADDED: firmware heartbeat on IO1."),
    R("R8", "120R"),

    # --- ports out to the arm ----------------------------------------------
    dict(ref="J2", value="CAN+5V", lib=CONN, sym="Conn_01x05",
         fp=("Connector_JST", "JST_XH_B5B-XH-AM_1x05_P2.50mm_Vertical"),
         note="CANH CANL EN 5V GND. Same harness the nodes expect."),
    dict(ref="J3", value="19V OUT", lib=CONN, sym="Conn_01x02",
         fp=("Connector_JST", "JST_VH_B2P-VH_1x02_P3.96mm_Vertical"),
         note="Motor bus to the arm."),
    dict(ref="J4", value="I2S OUT", lib=CONN, sym="Conn_01x05",
         fp=("Connector_PinHeader_2.54mm", "PinHeader_1x05_P2.54mm_Vertical"),
         note="5V GND DOUT BCLK WS for the speaker amp, which shares the mic bus."),
]

BRAIN_NETS = {
    # --- power chain --------------------------------------------------------
    "+19V_RAW": [("J1", "1"), ("Q1", "S"), ("R9", "1")],
    "Q1_GATE": [("Q1", "G"), ("R6", "1"), ("R9", "2")],
    "+19V": [("Q1", "D"), ("C1", "1"), ("A2", "IN+"), ("J3", "Pin_1")],
    "+5V": [("A2", "OUT+"), ("A1", "5V"), ("C2", "1"), ("J2", "Pin_4"),
            ("J4", "Pin_1"), ("D1", "A")],
    "+3V3": [
        ("A1", "3V3"), ("C3", "1"), ("C4", "1"), ("C5", "1"),
        ("U1", "VCC"),
        ("A3", "VCC"), ("A4", "VCC"), ("A5", "VCC"),
        ("A6", "VDD"), ("A7", "VDD"),
        ("R1", "1"), ("R2", "1"),
        ("A7", "LR"),                      # right mic: L/R high
    ],
    "GND": [
        ("J1", "2"), ("J1", "3"), ("A2", "IN-"), ("A2", "OUT-"), ("A1", "GND"), ("C1", "2"), ("C2", "2"),
        ("C3", "2"), ("C4", "2"), ("C5", "2"),
        ("R6", "2"), ("R3", "2"),
        ("Q2", "S"),
        ("U1", "GND"), ("U1", "Rs"),
        ("A3", "GND"), ("A4", "GND"), ("A5", "GND"), ("A6", "GND"), ("A7", "GND"),
        ("A6", "LR"),                      # left mic: L/R low
        ("J2", "Pin_5"), ("J3", "Pin_2"), ("J4", "Pin_2"),
        ("R7", "2"), ("R8", "2"),
    ],

    # --- I2C, master-end pull-ups only --------------------------------------
    "I2C_SDA": [("A1", "IO8"), ("A3", "SDA"), ("A4", "SDA"), ("A5", "SDA"), ("R1", "2")],
    "I2C_SCL": [("A1", "IO9"), ("A3", "SCL"), ("A4", "SCL"), ("A5", "SCL"), ("R2", "2")],
    "TOF_INT": [("A1", "IO13"), ("A3", "INT")],

    # --- I2S: both mics share the clock, both drive the same data pin -------
    "I2S_SD": [("A1", "IO2"), ("A6", "SD"), ("A7", "SD")],
    "I2S_BCLK": [("A1", "IO43"), ("A6", "SCK"), ("A7", "SCK"), ("J4", "Pin_4")],
    "I2S_WS": [("A1", "IO44"), ("A6", "WS"), ("A7", "WS"), ("J4", "Pin_5")],
    "I2S_DOUT": [("A1", "IO4"), ("J4", "Pin_3")],

    # --- hardware kill ------------------------------------------------------
    "KILL_GPIO": [("A1", "IO7"), ("R4", "1")],
    "KILL_GATE": [("R4", "2"), ("Q2", "G"), ("R3", "1")],
    "EN_BUS": [("Q2", "D"), ("J2", "Pin_3")],

    # --- indicators ---------------------------------------------------------
    "PWR_LED_K": [("D1", "K"), ("R7", "1")],
    "RUN_LED_A": [("A1", "IO1"), ("D2", "A")],
    "RUN_LED_K": [("D2", "K"), ("R8", "1")],

    # --- CAN ----------------------------------------------------------------
    "CAN_TX": [("A1", "IO5"), ("U1", "D")],
    "CAN_RX": [("A1", "IO6"), ("U1", "R")],
    "CANH": [("U1", "CANH"), ("J2", "Pin_1"), ("JP1", "A")],
    "CANL": [("U1", "CANL"), ("J2", "Pin_2"), ("R5", "2")],
    "CAN_TERM": [("JP1", "B"), ("R5", "1")],
}

# ===========================================================================
# FUNCTIONAL GROUPS
# ===========================================================================
# Placement is by module, not by reference designator: a block and the passives
# that serve it sit together, so routing is short and local and you are not
# chasing a decoupling cap across the board. Every part must appear exactly
# once - `check.py` enforces it.

ACTUATOR_GROUPS = {
    # 19 V in, the 5 V that arrives on the CAN harness, and the 3.3 V local rail
    "power":    ["J4", "C19", "U6", "C11", "C12", "C20", "C21", "C22",
                 "D2", "R14"],
    # the MCU and everything it needs before it runs an instruction
    "mcu":      ["U1", "C3", "C4", "C5", "C6", "C7", "C16", "C17", "C18",
                 "C13", "R6", "J5"],
    "clock":    ["Y1", "C1", "C2"],
    "can":      ["U2", "C10", "R12", "JP1", "J2", "J3"],
    "isense":   ["U4", "U5", "R1", "R2", "C8", "C9"],
    "drive":    ["A1", "J1", "R7"],
    "analog":   ["J6", "J7", "R3", "R4", "R5", "C14", "C15"],
    "nodeid":   ["R8", "R9", "R10", "JP2", "JP3", "JP4"],
    "status":   ["D1", "R13"],
}

BRAIN_GROUPS = {
    "power":    ["J1", "Q1", "R6", "R9", "A2", "C1", "C2", "C3", "C5", "J3",
                 "D1", "R7"],
    "mcu":      ["A1"],
    "can":      ["U1", "C4", "R5", "JP1", "J2"],
    "kill":     ["Q2", "R3", "R4"],
    "i2c":      ["A3", "A4", "A5", "R1", "R2"],
    "audio":    ["A6", "A7", "J4"],
    "status":   ["D2", "R8"],
}

# Groups whose parts want a board edge: cables have to reach them, and an
# indicator you cannot see is not an indicator.
EDGE_GROUPS = {"power", "can", "drive", "analog", "audio", "status"}


def group_of(groups):
    out = {}
    for g, refs in groups.items():
        for r in refs:
            out[r] = g
    return out


BOARDS = {
    # Both boards are larger than the console's figures. The node was 50 x 45,
    # which fits but leaves almost nothing between blocks; at 70 x 60 each
    # functional group gets its own area and the routing stays local. The base
    # grows for the same reason, with the mics still exactly 130 mm apart.
    "actuator-node": dict(parts=ACTUATOR_PARTS, nets=ACTUATOR_NETS, size=(70.0, 60.0),
                          groups=ACTUATOR_GROUPS, edge_groups=EDGE_GROUPS,
                          title="Juno actuator node",
                          desc="STM32G431 CAN-FD joint controller"),
    "main-brain": dict(parts=BRAIN_PARTS, nets=BRAIN_NETS, size=(170.0, 100.0),
                       groups=BRAIN_GROUPS, edge_groups=EDGE_GROUPS,
                       title="Juno main brain",
                       desc="ESP32-S3 controller, sensors and power for the base"),
}
