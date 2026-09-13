#!/usr/bin/env python3
"""Generate both KiCad projects. Run from hardware/tools."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kigen                                                  # noqa: E402
import modules                                                # noqa: E402
import spec                                                   # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CACHE = os.environ.get("KICAD_LIBS", "/tmp/kicad-libs")
SYM_DIR = f"{CACHE}/kicad-symbols"
FP_DIR = f"{CACHE}/kicad-footprints"

# ---------------------------------------------------------------------------
# Placement anchors, in board millimetres.
#
# The actuator numbers are the console's own physical drawings converted to
# scale: its copper-side view is 440 x 396 px over a 50 x 45 mm board, so
# x_mm = (px - 60) * 50/440 and y_mm = (py - 40) * 45/396. Parts it does not
# place are packed into a field beside the board for you to drag in.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Pinned positions: parts whose location is a mechanical fact, not a
# preference. Everything else is placed by functional group.
# ---------------------------------------------------------------------------

BRAIN_PINNED = {
    "A6": (20.0, 50.0),     # left microphone
    "A7": (150.0, 50.0),    # right microphone - exactly 130 mm from A6
}

# Connectors are pinned to the perimeter; everything else is placed by group.
# Three rules drive this:
#   - the two CAN connectors sit on opposite edges, because they are a
#     daisy chain and a cable should enter one side and leave the other;
#   - everything that goes to the motor - phases, encoder, the stator
#     thermistor, and the SPI header that would carry an upgraded encoder -
#     clusters on one edge, so one loom leaves the board in one direction;
#   - power and debug take the remaining edge.
ACTUATOR_PINNED = {
    # Footprint courtyards differ in shape: the JST bodies run along X from near
    # pin 1, while the 2.54 mm pin headers run along Y and stand 11-16 mm tall,
    # so the headers are placed to reach an edge rather than centred on it.
    # check.py enforces the pinned spot, the outline and the clearances.

    # --- ports, all on the perimeter ---------------------------------------
    "J2": (5.0, 30.0),      # CAN in   - left edge, mid height
    "J3": (55.0, 30.0),     # CAN ext  - right edge, directly opposite J2
    "J4": (8.0, 7.0),       # 19 V in  - top left
    "J5": (20.0, 5.0),      # SWD      - top edge, beside power
    # The motor loom leaves together on the bottom edge: phases, stator
    # thermistor, encoder, and the SPI header for an upgraded encoder.
    "J1": (8.0, 54.0),
    "J7": (20.0, 54.0),
    "J6": (30.0, 47.0),
    "J8": (38.0, 42.0),

    # --- the floorplan ------------------------------------------------------
    # Left to group placement these land wherever the perimeter leaves room,
    # which put the crystal 15 mm from the MCU and a shunt 16 mm from its
    # amplifier. Placed by hand instead.
    "A1": (44.0, 16.0),     # driver socket, 22.6 x 18.2 mm
    "C19": (62.0, 20.0),    # 470 uF bulk, beside the driver's VM
    "U1": (24.0, 31.0),     # STM32G431
    "Y1": (24.0, 41.0),     # 8 MHz crystal, hard against the MCU
    # Current sense. Each shunt sits beside its own amplifier because the sense
    # tap has to land on the shunt's end caps - at 30 mOhm, 20 mm of copper is
    # a 5 percent error - and the pair sits between the driver and the phases.
    "R1": (38.0, 30.0), "U4": (46.0, 30.0),
    "R2": (38.0, 36.0), "U5": (46.0, 36.0),
}

# Parts that must hug another part for electrical reasons, not tidiness.
ACTUATOR_NEAR = {
    "Y1": "U1", "C1": "Y1", "C2": "Y1",              # crystal loop, keep it tiny
    "C3": "U1", "C4": "U1", "C5": "U1", "C6": "U1",  # VDD decoupling
    "C7": "U1", "C16": "U1", "C17": "U1", "C18": "U1", "C13": "U1",
    "C10": "U2", "R12": "U2", "JP1": "U2",           # CAN transceiver
    "R1": "U4", "C8": "U4",                          # shunt A: Kelvin tap
    "R2": "U5", "C9": "U5",                          # shunt B
    "C19": "A1", "R7": "A1",                         # bulk at the driver VM
    "C11": "U6", "C12": "U6", "C20": "U6", "C21": "U6", "C22": "U6",
    "R3": "R4", "R5": "J7", "C14": "R4", "C15": "R5",
    "R13": "D1", "R14": "D2",
}

BRAIN_NEAR = {
    "C4": "U1", "R5": "U1", "JP1": "U1",
    "C1": "A2", "C2": "A2", "C3": "A2",
    "R1": "A1", "R2": "A1", "C5": "A1",
    "R3": "Q2", "R4": "Q2",
    "R6": "Q1", "R9": "Q1",
    "R7": "D1", "R8": "D2",
}

EXTRA = {
    "actuator-node": dict(
        pinned=ACTUATOR_PINNED, near=ACTUATOR_NEAR,
        holes=[(3.5, 3.5), (66.5, 3.5), (3.5, 56.5), (66.5, 56.5)],
        keepouts=[("circle", (35.0, 30.0, 24.0),
                   "gearbox sits over this circle on the BACK face - "
                   "keep rear protrusion under 5.5 mm")],
    ),
    "main-brain": dict(
        pinned=BRAIN_PINNED, near=BRAIN_NEAR,
        holes=[(4.0, 4.0), (166.0, 4.0), (4.0, 96.0), (166.0, 96.0)],
        keepouts=[],
    ),
}


def main():
    if not os.path.isdir(SYM_DIR):
        sys.exit(f"stock KiCad libraries not found under {CACHE}.\n"
                 "Set KICAD_LIBS, or clone tag 8.0.9 of kicad-symbols and "
                 "kicad-footprints from gitlab.com/kicad/libraries into it.")

    for name, board in spec.BOARDS.items():
        out = os.path.join(ROOT, name)
        os.makedirs(f"{out}/lib", exist_ok=True)
        lib_txt, fps = modules.build()
        os.makedirs(f"{out}/lib/juno.pretty", exist_ok=True)
        open(f"{out}/lib/juno.kicad_sym", "w").write(lib_txt)
        for fn, body in fps.items():
            open(f"{out}/lib/juno.pretty/{fn}.kicad_mod", "w").write(body)

        libs = kigen.Libs(SYM_DIR, FP_DIR,
                          f"{out}/lib/juno.kicad_sym", f"{out}/lib/juno.pretty")
        board = dict(board, **EXTRA[name])
        resolved, assigned, pinmap, floating = kigen.resolve(
            name, board["parts"], board["nets"], libs)

        root = kigen.uid(name, "root")
        open(f"{out}/{name}.kicad_sch", "w").write(
            kigen.gen_sch(board, name, board["parts"], resolved, pinmap, libs, root))
        open(f"{out}/{name}.kicad_pcb", "w").write(
            kigen.gen_pcb(board, name, board["parts"], resolved, pinmap, libs))
        open(f"{out}/{name}.kicad_pro", "w").write(kigen.gen_pro(name, root))
        open(f"{out}/sym-lib-table", "w").write(
            kigen.sym_lib_table([("juno", "${KIPRJMOD}/lib/juno.kicad_sym")]))
        open(f"{out}/fp-lib-table", "w").write(
            kigen.fp_lib_table([("juno", "${KIPRJMOD}/lib/juno.pretty")]))

        print(f"{name}: {len(board['parts'])} parts, {len(resolved)} nets, "
              f"{len(assigned)} pin connections, {len(floating)} unused pins")


if __name__ == "__main__":
    main()
