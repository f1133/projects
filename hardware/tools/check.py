#!/usr/bin/env python3
"""Verify the generated projects against the spec.

Three things, because "it parses" is not "it is wired correctly":

1. PCB pad nets match the spec net for net, pad for pad.
2. Every schematic wire stub actually touches its pin's connection point and
   carries a label - a stub that misses by a grid unit looks perfect and
   connects nothing.
3. Anchored footprints sit inside the board outline and their courtyards do
   not collide.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kigen                                                  # noqa: E402
import spec                                                   # noqa: E402
import build as B                                             # noqa: E402

FAIL = []


def bad(board, msg):
    FAIL.append(f"{board}: {msg}")


def check(name):
    out = os.path.join(B.ROOT, name)
    board = dict(spec.BOARDS[name], **{k: v for k, v in B.EXTRA[name].items()
                                       if k != "anchors"})
    libs = kigen.Libs(B.SYM_DIR, B.FP_DIR,
                      f"{out}/lib/juno.kicad_sym", f"{out}/lib/juno.pretty")
    resolved, assigned, pinmap, floating = kigen.resolve(
        name, board["parts"], board["nets"], libs)

    # ---- 1. PCB pad nets ---------------------------------------------------
    pcb = open(f"{out}/{name}.kicad_pcb").read()
    got = {}
    for fpb in re.finditer(r'\n\t\(footprint "', pcb):
        seg = pcb[fpb.start():]
        depth, i = 0, 0
        while True:
            if seg[i] == "(":
                depth += 1
            elif seg[i] == ")":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        seg = seg[:i + 1]
        ref = re.search(r'\(property "Reference" "([^"]+)"', seg)
        if not ref:
            continue
        for pm in re.finditer(r'\(pad "([^"]+)"', seg):
            d, j = 0, pm.start()
            while True:
                if seg[j] == "(":
                    d += 1
                elif seg[j] == ")":
                    d -= 1
                    if d == 0:
                        break
                j += 1
            body = seg[pm.start():j + 1]
            nm = re.search(r'\(net \d+ "([^"]*)"\)', body)
            got[(ref.group(1), pm.group(1))] = nm.group(1) if nm else None
    want = {(r, p): n for n, cs in resolved.items() for r, p in cs}
    for k, v in sorted(want.items()):
        if k not in got:
            bad(name, f"pad {k[0]}.{k[1]} has no net in the pcb (want {v})")
        elif got[k] is None:
            bad(name, f"pad {k[0]}.{k[1]} carries no net at all (want {v})")
        elif got[k] != v:
            bad(name, f"pad {k[0]}.{k[1]} is on '{got[k]}', spec says '{v}'")
    for k, v in sorted(got.items()):
        if k not in want and v:
            bad(name, f"pad {k[0]}.{k[1]} is on '{v}' but the spec leaves it open")

    # ---- 2. schematic stubs reach their pins -------------------------------
    sch = open(f"{out}/{name}.kicad_sch").read()
    wires = set()
    for m in re.finditer(r'\(xy ([-\d.]+) ([-\d.]+)\) \(xy ([-\d.]+) ([-\d.]+)\)', sch):
        a = (round(float(m.group(1)), 3), round(float(m.group(2)), 3))
        b = (round(float(m.group(3)), 3), round(float(m.group(4)), 3))
        wires.add((a, b))
    ends = {a for a, _ in wires} | {b for _, b in wires}
    labels = {}
    for m in re.finditer(r'\(label "([^"]+)"\n\t\t\(at ([-\d.]+) ([-\d.]+)', sch):
        labels.setdefault((round(float(m.group(2)), 3), round(float(m.group(3)), 3)),
                          set()).add(m.group(1))

    placed = {}
    for m in re.finditer(r'\(lib_id "([^"]+)"\)\n\t\t\(at ([-\d.]+) ([-\d.]+) \d+\)'
                         r'[\s\S]*?\(property "Reference" "([^"]+)"', sch):
        placed[m.group(4)] = (float(m.group(2)), float(m.group(3)))

    checked = 0
    for (ref, pin), net in sorted(want.items()):
        if ref not in placed:
            bad(name, f"{ref} is in the spec but not on the schematic")
            continue
        sx, sy = placed[ref]
        hit = [p for p in pinmap[ref] if p[0] == pin]
        if not hit:
            continue
        _, _, lx, ly, ang = hit[0]
        pt = (round(sx + lx, 3), round(sy - ly, 3))
        if pt not in ends:
            bad(name, f"{ref}.{pin} ({net}): no wire touches the pin at {pt}")
            continue
        dx, dy = kigen.outward(ang)
        tip = (round(pt[0] + dx * kigen.STUB, 3), round(pt[1] - dy * kigen.STUB, 3))
        if net not in labels.get(tip, set()):
            bad(name, f"{ref}.{pin}: no '{net}' label at the stub tip {tip}")
        checked += 1

    # ---- 3. anchored parts inside the outline ------------------------------
    W, H = board["size"]
    for ref, (ax, ay) in B.EXTRA[name]["anchors"].items():
        if not (0 <= ax <= W and 0 <= ay <= H):
            bad(name, f"anchor {ref} at ({ax}, {ay}) is outside the {W}x{H} board")
    # Real overlap, using the same courtyard boxes the placer used, so the
    # checker and the placer cannot disagree. Parts with two courtyards - the
    # Mini, which straddles the MCU it sits 8.5 mm above - keep their gap.
    fp_boxes, positions = {}, {}
    for m in re.finditer(r'\n\t\(footprint "', pcb):
        seg, d, i2 = pcb[m.start():], 0, 0
        while True:
            if seg[i2] == "(":
                d += 1
            elif seg[i2] == ")":
                d -= 1
                if d == 0:
                    break
            i2 += 1
        seg = seg[:i2 + 1]
        ref = re.search(r'\(property "Reference" "([^"]+)"', seg)
        at = re.search(r'\n\t\t\(at ([-\d.]+) ([-\d.]+)', seg)
        if not ref or not at:
            continue
        positions[ref.group(1)] = (float(at.group(1)), float(at.group(2)))
    for p_ in board["parts"]:
        fp_boxes[p_["ref"]] = kigen.courtyard_boxes(libs.footprint(*p_["fp"]))

    refs = sorted(r for r in positions if r in fp_boxes)
    abs_boxes = {r: kigen.shift(fp_boxes[r], *positions[r]) for r in refs}
    for a in range(len(refs)):
        for b in range(a + 1, len(refs)):
            ra, rb = refs[a], refs[b]
            if kigen.overlaps(abs_boxes[ra], abs_boxes[rb], gap=0.0):
                bad(name, f"{ra} and {rb} courtyards overlap on the board")
    on_board = [r for r in refs if all(bx[2] <= W + 0.01 and bx[0] >= -0.01
                                       for bx in abs_boxes[r])]
    for r in on_board:
        for bx in abs_boxes[r]:
            if bx[1] < -0.01 or bx[3] > H + 0.01:
                bad(name, f"{r} extends past the {W}x{H} board outline")
                break

    print(f"{name}: {len(want)} pad nets verified, {checked} schematic stubs verified, "
          f"{len(floating)} pins intentionally open")
    return floating


if __name__ == "__main__":
    for n in spec.BOARDS:
        check(n)
    if FAIL:
        print(f"\n{len(FAIL)} PROBLEM(S):")
        for f in FAIL:
            print("  -", f)
        sys.exit(1)
    print("\nall checks passed")
