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

    # ---- 3. groups, pinned parts, geometry ---------------------------------
    refs = {p_["ref"] for p_ in board["parts"]}
    seen = {}
    for g, members in board["groups"].items():
        for r in members:
            if r in seen:
                bad(name, f"{r} is in both group '{seen[r]}' and '{g}'")
            seen[r] = g
    for r in sorted(refs - set(seen)):
        bad(name, f"{r} is in no functional group")
    for r in sorted(set(seen) - refs):
        bad(name, f"group '{seen[r]}' lists {r}, which is not a part")

    W, H = board["size"]

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
        at = re.search(r'\n\t\t\(at ([-\d.]+) ([-\d.]+)(?: ([-\d.]+))?\)', seg)
        if not ref or not at:
            continue
        positions[ref.group(1)] = (float(at.group(1)), float(at.group(2)),
                                   float(at.group(3) or 0))
    for p_ in board["parts"]:
        fp_boxes[p_["ref"]] = kigen.courtyard_boxes(libs.footprint(*p_["fp"]))

    refs = sorted(r for r in positions if r in fp_boxes)
    # A rotated footprint keeps its library courtyard, so turn the boxes the
    # same way before placing them or a right-angle connector reads as if it
    # still pointed the way the library drew it.
    abs_boxes = {r: kigen.shift(kigen.rotate_boxes(fp_boxes[r], positions[r][2]),
                                *positions[r][:2]) for r in refs}
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

    # ---- 3b. the two faults that produced this checker ---------------------
    # The driver module's 3V3 pin is DRV8313 V3P3OUT, a regulator output. An
    # earlier revision tied it to the carrier's 3.3 V rail, which would have
    # shorted two regulators together. It must stay on no net at all.
    for p_ in board["parts"]:
        if p_["sym"] != "SimpleFOC_Mini":
            continue
        ref = p_["ref"]
        for num, nm, *_ in pinmap[ref]:
            if nm == "3V3" and (ref, num) in {(r, q) for cs in resolved.values()
                                              for r, q in cs}:
                bad(name, f"{ref}.{num} (3V3) is on a net - it is V3P3OUT, a "
                          f"regulator output, and must be left open")
        # The step-mini export this was first built from had a fourth channel.
        # The real board has three phases; IN4/OUT4 must not reappear.
        for num, nm, *_ in pinmap[ref]:
            if nm in ("IN4", "OUT4"):
                bad(name, f"{ref} has a pin '{nm}' - that is the wrong module")
    for net_name, conns in board["nets"].items():
        for r, pin_name in conns:
            if pin_name in ("IN4", "OUT4"):
                bad(name, f"net {net_name} references {r}.{pin_name}, which "
                          f"belongs to the step-mini, not the Mini v1.0")

    # ---- 4. proximity ------------------------------------------------------
    # Measured as the GAP between courtyards, not centre to centre. An HC49-SD
    # crystal is 13 mm long, so a load cap physically touching it still sits
    # 9 mm centre to centre - a centre-based limit would be measuring the
    # crystal's length, not how close the cap is.
    def gap(a_boxes, b_boxes):
        best = None
        for a in a_boxes:
            for b in b_boxes:
                dx = max(0.0, a[0] - b[2], b[0] - a[2])
                dy = max(0.0, a[1] - b[3], b[1] - a[3])
                d = (dx * dx + dy * dy) ** 0.5
                best = d if best is None else min(best, d)
        return best

    # Default is 12 mm. Tighter where the loop area is the point: the crystal
    # load caps, and the MCU's 100 nF decoupling, which has to beat the
    # inductance of the trace it sits on rather than merely be nearby.
    LIMITS = {("Y1", "U1"): 6.0, ("C1", "Y1"): 2.0, ("C2", "Y1"): 2.0}
    LIMITS.update({(f"C{n}", "U1"): 5.0 for n in (3, 4, 5, 6, 7, 16)})
    LIMITS[("C13", "U1")] = 8.0    # NRST RC, a DC node - proximity is cosmetic
    LIMITS[("C17", "U1")] = 8.0    # 1 uF VDDA bulk
    LIMITS[("C18", "U1")] = 8.0    # 1 uF VREF+ bulk
    for ref, tgt in sorted((board.get("near") or {}).items()):
        if ref not in abs_boxes or tgt not in abs_boxes:
            continue
        d = gap(abs_boxes[ref], abs_boxes[tgt])
        limit = LIMITS.get((ref, tgt), 12.0)
        if d is not None and d > limit:
            bad(name, f"{ref} sits {d:.1f} mm clear of {tgt}, wanted within "
                      f"{limit:.0f} mm")

    for r, want_at in (board.get("pinned") or {}).items():
        px, py = want_at[0], want_at[1]
        pr = want_at[2] if len(want_at) > 2 else 0
        got_at = positions.get(r)
        if got_at is None:
            bad(name, f"pinned part {r} is not on the board")
        elif abs(got_at[0] - px) > 0.01 or abs(got_at[1] - py) > 0.01:
            bad(name, f"pinned {r} wanted ({px}, {py}) but sits at "
                      f"({got_at[0]}, {got_at[1]})")
        elif abs(got_at[2] - pr) > 0.01:
            bad(name, f"pinned {r} wanted {pr} deg but sits at {got_at[2]} deg")
    if "A6" in positions and "A7" in positions:
        d = abs(positions["A7"][0] - positions["A6"][0])
        if abs(d - 130.0) > 0.01:
            bad(name, f"microphones are {d:.2f} mm apart, must be 130.00 mm")

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
