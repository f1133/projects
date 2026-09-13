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
    # --- ports, all on the perimeter ---------------------------------------
    # Every JST here is a right-angle part, and a right-angle body opens toward
    # +Y at 0 degrees, so the rotation is what decides which way the cable
    # leaves the board: 0 bottom, 180 top, 90 right, 270 left. The 2.54 mm pin
    # headers are turned the same way so their row runs along the edge rather
    # than into the board.
    "J2": (11.0, 23.0, 270),   # CAN in   - left edge, cable exits left
    "J3": (59.0, 35.0, 90),    # CAN ext  - right edge, directly opposite J2
    "J4": (12.0, 15.0, 180),   # 19 V in  - top edge, VH is 16.4 mm deep
    "J5": (19.0, 4.0, 90),     # SWD      - top edge, beside power
    # The motor loom leaves together along the bottom edge: phases, stator
    # thermistor, encoder, and the SPI header for an upgraded encoder.
    "J1": (9.0, 49.0, 0),      # phases
    "J7": (22.0, 49.0, 0),     # NTC
    "J6": (33.0, 55.0, 90),    # encoder
    "J8": (45.0, 55.0, 90),    # SPI

    # --- the floorplan ------------------------------------------------------
    # Left to group placement these land wherever the perimeter leaves room,
    # which put the crystal 15 mm from the MCU and a shunt 16 mm from its
    # amplifier. Placed by hand instead.
    "A1": (42.0, 15.0),        # driver socket, 20.3 x 20.9 mm courtyard
    # The Mini stands 8.5 mm off the board on its sockets, so the 17 x 12 mm
    # pocket between its pad rows is usable. R7 is the one part that belongs
    # there: it holds the driver disabled while the MCU is in reset, and the
    # shorter that pull-down the less chance of a glitch enabling the bridge.
    "R7": (44.0, 19.0),        # driver EN pull-down, clear of every A1 pad
    "C19": (61.0, 13.0),       # 470 uF bulk, beside the driver's VM
    "U1": (24.0, 31.0),        # STM32G431
    # The LDO runs off the 5 V that arrives on the CAN harness, so it belongs
    # by J3 and not by the 19 V input - and keeping it out from under the
    # driver means its dissipation and the bridge's do not stack.
    "U6": (53.0, 44.0),        # AMS1117-3.3
    "R6": (16.5, 33.0),        # BOOT0 pull-down, in the column beside the MCU
    # The crystal's hand-solder pads put its two terminals 11.9 mm apart, so
    # one load cap per terminal rather than both at one end.
    "Y1": (22.0, 40.0),        # 8 MHz crystal, hard against the MCU
    "C1": (16.1, 44.1),        # under Y1 pad 1
    "C2": (27.9, 44.1),        # under Y1 pad 2
    # Current sense. Each shunt sits beside its own amplifier because the sense
    # tap has to land on the shunt's end caps - at 30 mOhm, 20 mm of copper is
    # a 5 percent error - and the pair sits between the driver and the phases.
    "R1": (36.0, 30.0), "U4": (44.0, 30.0),
    "R2": (36.0, 37.5), "U5": (44.0, 37.5),
    # Node ID. Each jumper next to the pull-up it fights, in the clear block
    # between the SWD header and the driver socket: left to itself the placer
    # filed the jumpers down the 6 mm strip beside the left mounting hole and
    # stranded the resistors 13 mm away.
    "JP2": (17.0, 8.0), "R8": (22.5, 8.0),     # ID0
    "JP3": (17.0, 11.0), "R9": (22.5, 11.0),   # ID1
    "JP4": (28.0, 8.0), "R10": (28.0, 11.0),   # ID2
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
    "R8": "JP2", "R9": "JP3", "R10": "JP4",          # each ID pull-up by its jumper
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
