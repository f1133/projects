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

ACTUATOR_PINNED = {}        # nothing on the node has a fixed spot any more:
                            # the gearbox clearance applies to the back face,
                            # and every part sits on the front.

# Parts that must hug another part for electrical reasons, not tidiness.
ACTUATOR_NEAR = {
    "Y1": "U1", "C1": "Y1", "C2": "Y1",              # crystal loop, keep it tiny
    "C3": "U1", "C4": "U1", "C5": "U1", "C6": "U1",  # VDD decoupling
    "C7": "U1", "C16": "U1", "C17": "U1", "C18": "U1", "C13": "U1",
    "C10": "U2", "R12": "U2", "JP1": "U2",           # CAN transceiver
    "R1": "U4", "C8": "U4",                          # shunt A: Kelvin tap
    "R2": "U5", "C9": "U5",                          # shunt B
    "C19": "M1", "R7": "M1",                         # bulk at the driver VIN
    "C11": "U6", "C12": "U6", "C20": "U6", "C21": "U6", "C22": "U6",
    "R3": "R4", "R5": "J7", "C14": "R4", "C15": "R5",
    "R13": "D1", "R14": "D2",
}

BRAIN_NEAR = {
    "C4": "U1", "R5": "U1", "JP1": "U1",
    "C1": "A2", "C2": "A2", "C3": "A2",
    "R1": "A1", "R2": "A1", "C5": "A1",
    "R3": "Q2", "R4": "Q2",
    "D1": "Q1", "R6": "Q1",
    "R7": "D2", "R8": "D3",
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
