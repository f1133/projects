#!/usr/bin/env python3
"""Render an SVG of each board's placement, coloured by functional group."""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build as B                                             # noqa: E402
import kigen                                                  # noqa: E402
import spec                                                   # noqa: E402

COLORS = ["#4C78A8", "#F58518", "#54A24B", "#E45756", "#72B7B2",
          "#EECA3B", "#B279A2", "#FF9DA6", "#9D755D"]


def render(name, out_path):
    board = dict(spec.BOARDS[name], **B.EXTRA[name])
    W, H = board["size"]
    libs = kigen.Libs(B.SYM_DIR, B.FP_DIR,
                      f"{B.ROOT}/{name}/lib/juno.kicad_sym",
                      f"{B.ROOT}/{name}/lib/juno.pretty")
    pcb = open(f"{B.ROOT}/{name}/{name}.kicad_pcb").read()
    pos = {}
    for m in re.finditer(r'\n\t\(footprint "', pcb):
        seg, d, i = pcb[m.start():], 0, 0
        while True:
            if seg[i] == "(":
                d += 1
            elif seg[i] == ")":
                d -= 1
                if d == 0:
                    break
            i += 1
        seg = seg[:i + 1]
        r = re.search(r'\(property "Reference" "([^"]+)"', seg)
        at = re.search(r'\n\t\t\(at ([-\d.]+) ([-\d.]+)', seg)
        if r and at:
            pos[r.group(1)] = (float(at.group(1)), float(at.group(2)))

    gof = spec.group_of(board["groups"])
    gidx = {g: i for i, g in enumerate(sorted(board["groups"]))}
    S, M = 8.0, 26.0
    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W*S+2*M:.0f}" '
           f'height="{H*S+2*M+34:.0f}" viewBox="0 0 {W*S+2*M:.0f} {H*S+2*M+34:.0f}">',
           '<rect width="100%" height="100%" fill="#ffffff"/>',
           f'<text x="{M}" y="20" font-family="system-ui,sans-serif" font-size="15" '
           f'font-weight="600" fill="#111">{name} &#183; {W:.0f} x {H:.0f} mm &#183; '
           f'{len(pos)} footprints, no traces</text>',
           f'<g transform="translate({M},{M+22})">',
           f'<rect x="0" y="0" width="{W*S}" height="{H*S}" fill="#FBFBF9" '
           f'stroke="#111" stroke-width="2"/>']
    for kind, args, text in board.get("keepouts", []):
        if kind == "circle":
            cx, cy, r = args
            svg.append(f'<circle cx="{cx*S}" cy="{cy*S}" r="{r*S}" fill="none" '
                       f'stroke="#A32D2D" stroke-width="1.4" stroke-dasharray="7 6"/>')
    for hx, hy in board.get("holes", []):
        svg.append(f'<circle cx="{hx*S}" cy="{hy*S}" r="{1.1*S}" fill="none" stroke="#666"/>')
    for p in board["parts"]:
        ref = p["ref"]
        if ref not in pos:
            continue
        col = COLORS[gidx.get(gof.get(ref, ""), 0) % len(COLORS)]
        for bx in kigen.shift(kigen.courtyard_boxes(libs.footprint(*p["fp"])), *pos[ref]):
            svg.append(f'<rect x="{bx[0]*S:.1f}" y="{bx[1]*S:.1f}" '
                       f'width="{(bx[2]-bx[0])*S:.1f}" height="{(bx[3]-bx[1])*S:.1f}" '
                       f'fill="{col}" fill-opacity="0.45" stroke="{col}" stroke-width="1"/>')
        svg.append(f'<text x="{pos[ref][0]*S:.1f}" y="{pos[ref][1]*S+3:.1f}" '
                   f'text-anchor="middle" font-family="system-ui,sans-serif" '
                   f'font-size="9" fill="#111">{ref}</text>')
    svg.append('</g>')
    lx = M
    for g in sorted(board["groups"]):
        col = COLORS[gidx[g] % len(COLORS)]
        svg.append(f'<rect x="{lx}" y="{H*S+M+26}" width="11" height="11" fill="{col}" '
                   f'fill-opacity="0.6" stroke="{col}"/>')
        svg.append(f'<text x="{lx+15}" y="{H*S+M+35}" font-family="system-ui,sans-serif" '
                   f'font-size="11" fill="#333">{g}</text>')
        lx += 26 + 7 * len(g)
    svg.append('</svg>')
    open(out_path, "w").write("\n".join(svg))
    return out_path


if __name__ == "__main__":
    for n in spec.BOARDS:
        print("wrote", render(n, f"{B.ROOT}/{n}/placement.svg"))
