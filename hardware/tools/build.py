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

ACTUATOR_ANCHORS = {
    "U1": (25.0, 26.4),     # G431, board centre, under the driver
    "M1": (25.0, 22.5),     # Mini socket rows straddle the MCU, 8.5 mm up
    "U4": (15.3, 25.3), "U5": (15.3, 30.1),
    "R1": (9.3, 25.3), "R2": (9.3, 30.1),      # shunts, Kelvin tapped
    "U2": (34.7, 25.3),     # CAN transceiver
    "U6": (34.0, 30.0),     # LDO
    # The console puts the 470 uF at (40.7, 37.3), but there it is an SMD can
    # on the copper face while the CAN-ext connector is a through-hole body on
    # the opposite face. Both are front-side here, so the can moves clear.
    "C19": (30.0, 38.5),    # 470 uF bulk
    "Y1": (13.5, 37.5),     # crystal, kept near the MCU
    "J5": (4.4, 16.1),      # SWD pads
    # Connectors: the four corners are the only places with height, because
    # the gearbox leaves 5.5 mm over the rest of the board.
    "J1": (9.1, 5.8),       # phases
    "J2": (40.9, 5.8),      # CAN in
    "J4": (9.1, 39.2),      # 19 V
    "J3": (40.9, 39.2),     # CAN ext
    # The encoder header and the NTC are new (the encoder moved off-board), so
    # the console has no place for them. Both sit on the side edges at mid
    # height, the only other strip that clears the gearbox circle. See the
    # mechanical note in the project README - this is tight.
    "J6": (4.5, 11.0),      # encoder cable
    "J7": (45.5, 11.0),     # NTC from the stator
}

BRAIN_ANCHORS = {
    "A6": (5.0, 35.0), "A7": (135.0, 35.0),    # mics, exactly 130 mm apart
    "A1": (70.0, 35.0),     # ESP32-S3
    "A2": (35.0, 15.0),     # buck
    "J1": (10.0, 60.0),     # barrel jack, star ground lands here
    "Q1": (24.0, 60.0),     # reverse-polarity FET, right behind the jack
    "U1": (100.0, 20.0),    # CAN transceiver
    "J2": (126.0, 12.0),    # CAN + 5 V out to the arm
    "J3": (126.0, 60.0),    # 19 V out to the arm
    "A3": (55.0, 10.0),     # ToF
    "A4": (88.0, 56.0),     # touch
    "A5": (70.0, 58.0),     # IMU
    "Q2": (98.0, 42.0),     # kill line
    "J4": (108.0, 60.0),    # I2S out to the speaker amp
}

EXTRA = {
    "actuator-node": dict(
        anchors=ACTUATOR_ANCHORS,
        holes=[(3.0, 3.0), (47.0, 3.0), (3.0, 42.0), (47.0, 42.0)],
        keepouts=[("circle", (25.0, 22.5, 21.8),
                   "gearbox above - 5.5 mm ceiling inside this circle")],
    ),
    "main-brain": dict(
        anchors=BRAIN_ANCHORS,
        holes=[(4.0, 4.0), (136.0, 4.0), (4.0, 66.0), (136.0, 66.0)],
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
        board = dict(board, **{k: v for k, v in EXTRA[name].items() if k != "anchors"})
        resolved, assigned, pinmap, floating = kigen.resolve(
            name, board["parts"], board["nets"], libs)

        root = kigen.uid(name, "root")
        open(f"{out}/{name}.kicad_sch", "w").write(
            kigen.gen_sch(board, name, board["parts"], resolved, pinmap, libs, root))
        open(f"{out}/{name}.kicad_pcb", "w").write(
            kigen.gen_pcb(board, name, board["parts"], resolved, pinmap, libs,
                          EXTRA[name]["anchors"]))
        open(f"{out}/{name}.kicad_pro", "w").write(kigen.gen_pro(name, root))
        open(f"{out}/sym-lib-table", "w").write(
            kigen.sym_lib_table([("juno", "${KIPRJMOD}/lib/juno.kicad_sym")]))
        open(f"{out}/fp-lib-table", "w").write(
            kigen.fp_lib_table([("juno", "${KIPRJMOD}/lib/juno.pretty")]))

        print(f"{name}: {len(board['parts'])} parts, {len(resolved)} nets, "
              f"{len(assigned)} pin connections, {len(floating)} unused pins")


if __name__ == "__main__":
    main()
