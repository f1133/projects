#!/usr/bin/env python3
"""Render a .kicad_pcb to SVG: assembly, copper and detail views.

No dependencies beyond the repo's own s-expression reader. Whatever copper is
in the file gets drawn, so once the board is routed these same views show the
traces without any change here.
"""

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sexp                                                   # noqa: E402

C = dict(
    bg="#10171C", substrate="#0E4A38", substrate_edge="#DCE5E2",
    pad="#E0B963", pad_edge="#A8822F", drill="#0B0F12",
    fcu="#D4813F", bcu="#4A8FD1", via="#E8C77A",
    silk="#F5F5F2", fab="#7FA396", body="#8FB3A5",
    ref="#FFFFFF", dim="#FFD166", keepout="#E05C5C", pour="#123F31",
    note="#9FB4AD",
)


def rot(x, y, deg):
    if not deg:
        return x, y
    r = math.radians(-deg)
    return x * math.cos(r) - y * math.sin(r), x * math.sin(r) + y * math.cos(r)


def esc(t):
    return (str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


class PCB:
    def __init__(self, path):
        self.root = sexp.parse(open(path).read())
        self.edges, self.circles, self.texts = [], [], []
        for g in sexp.findall(self.root, "gr_line"):
            if str(sexp.val(g, "layer")) == "Edge.Cuts":
                s, e = sexp.find(g, "start"), sexp.find(g, "end")
                self.edges.append(((float(s[1]), float(s[2])),
                                   (float(e[1]), float(e[2]))))
        for g in sexp.findall(self.root, "gr_circle"):
            c, e = sexp.find(g, "center"), sexp.find(g, "end")
            self.circles.append((float(c[1]), float(c[2]),
                                 math.dist((float(c[1]), float(c[2])),
                                           (float(e[1]), float(e[2]))),
                                 str(sexp.val(g, "layer"))))
        for g in sexp.findall(self.root, "gr_text"):
            a = sexp.find(g, "at")
            self.texts.append((str(g[1]), float(a[1]), float(a[2]),
                               str(sexp.val(g, "layer"))))
        self.segs = []
        for s in sexp.findall(self.root, "segment"):
            a, b = sexp.find(s, "start"), sexp.find(s, "end")
            self.segs.append(((float(a[1]), float(a[2])),
                              (float(b[1]), float(b[2])),
                              float(sexp.val(s, "width")),
                              str(sexp.val(s, "layer"))))
        self.vias = []
        for v in sexp.findall(self.root, "via"):
            a = sexp.find(v, "at")
            self.vias.append((float(a[1]), float(a[2]),
                              float(sexp.val(v, "size")),
                              float(sexp.val(v, "drill"))))
        self.zones = []
        for z in sexp.findall(self.root, "zone"):
            poly = sexp.find(z, "polygon")
            if not poly:
                continue
            pts = sexp.find(poly, "pts")
            self.zones.append(([(float(p[1]), float(p[2]))
                                for p in sexp.findall(pts, "xy")],
                               str(sexp.val(z, "layer"))))
        self.parts = []
        for f in sexp.findall(self.root, "footprint"):
            at = sexp.find(f, "at")
            fx, fy = float(at[1]), float(at[2])
            fr = float(at[3]) if len(at) > 3 else 0.0
            ref = ""
            refpos = None
            for p in sexp.findall(f, "property"):
                if str(p[1]) == "Reference":
                    ref = str(p[2])
                    pa = sexp.find(p, "at")
                    eff = sexp.find(p, "effects")
                    hidden = eff is not None and sexp.find(eff, "hide") is not None
                    if pa and not hidden:
                        refpos = (float(pa[1]), float(pa[2]))
            pads, gfx = [], []
            for p in sexp.findall(f, "pad"):
                pa, sz = sexp.find(p, "at"), sexp.find(p, "size")
                dr = sexp.find(p, "drill")
                rr = sexp.find(p, "roundrect_rratio")
                pads.append(dict(num=str(p[1]), ptype=str(p[2]), shape=str(p[3]),
                                 x=float(pa[1]), y=float(pa[2]),
                                 rot=float(pa[3]) if len(pa) > 3 else 0.0,
                                 w=float(sz[1]), h=float(sz[2]),
                                 drill=float(dr[1]) if dr else None,
                                 rr=float(rr[1]) if rr else 0.0))
            for g in f:
                if not (isinstance(g, list) and str(g[0]).startswith("fp_")):
                    continue
                kind = str(g[0])
                layer = str(sexp.val(g, "layer") or "")
                if kind == "fp_line":
                    s, e = sexp.find(g, "start"), sexp.find(g, "end")
                    gfx.append(("line", (float(s[1]), float(s[2])),
                                (float(e[1]), float(e[2])), layer))
                elif kind == "fp_circle":
                    c, e = sexp.find(g, "center"), sexp.find(g, "end")
                    gfx.append(("circle", (float(c[1]), float(c[2])),
                                math.dist((float(c[1]), float(c[2])),
                                          (float(e[1]), float(e[2]))), layer))
                elif kind == "fp_arc":
                    s, m, e = (sexp.find(g, "start"), sexp.find(g, "mid"),
                               sexp.find(g, "end"))
                    if s and m and e:
                        gfx.append(("arc", (float(s[1]), float(s[2])),
                                    (float(m[1]), float(m[2])),
                                    (float(e[1]), float(e[2])), layer))
                elif kind == "fp_poly":
                    pts = sexp.find(g, "pts")
                    gfx.append(("poly", [(float(p[1]), float(p[2]))
                                         for p in sexp.findall(pts, "xy")],
                                layer))
            self.parts.append(dict(ref=ref, x=fx, y=fy, rot=fr, pads=pads,
                                   gfx=gfx, refpos=refpos, lib=str(f[1])))

    def extent(self):
        xs = [p[0] for e in self.edges for p in e]
        ys = [p[1] for e in self.edges for p in e]
        return min(xs), min(ys), max(xs), max(ys)


class Canvas:
    """Board millimetres in, SVG out. `mirror` flips X for a bottom view."""

    def __init__(self, x0, y0, x1, y1, scale=14.0, pad=11.0, mirror=False,
                 title="", subtitle=""):
        self.bx0, self.by0, self.bx1, self.by1 = x0 - pad, y0 - pad, x1 + pad, y1 + pad
        self.s = scale
        self.mirror = mirror
        self.w = (self.bx1 - self.bx0) * scale
        self.h = (self.by1 - self.by0) * scale
        self.head = 52
        self.foot = 34
        self.o = []
        self.title, self.subtitle = title, subtitle

    def X(self, x):
        # Reflect about the view box, not about the origin: X() subtracts bx0
        # on the way out, so adding it back here shifted the whole bottom
        # view left by the padding width.
        x = (self.bx1 - (x - self.bx0)) if self.mirror else x
        return (x - self.bx0) * self.s

    def Y(self, y):
        return (y - self.by0) * self.s + self.head

    def L(self, mm):
        return mm * self.s

    def line(self, a, b, col, w, cap="round", op=1.0, dash=None):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        self.o.append(f'<line x1="{self.X(a[0]):.2f}" y1="{self.Y(a[1]):.2f}" '
                      f'x2="{self.X(b[0]):.2f}" y2="{self.Y(b[1]):.2f}" '
                      f'stroke="{col}" stroke-width="{self.L(w):.2f}" '
                      f'stroke-linecap="{cap}" opacity="{op}"{d}/>')

    def circ(self, x, y, r, fill="none", stroke="none", w=0.0, op=1.0):
        self.o.append(f'<circle cx="{self.X(x):.2f}" cy="{self.Y(y):.2f}" '
                      f'r="{self.L(r):.2f}" fill="{fill}" stroke="{stroke}" '
                      f'stroke-width="{self.L(w):.2f}" opacity="{op}"/>')

    def rect(self, x, y, w, h, rx, ang, fill, stroke="none", sw=0.0, op=1.0):
        cx, cy = self.X(x), self.Y(y)
        a = -ang if self.mirror else ang
        self.o.append(
            f'<rect x="{-self.L(w) / 2:.2f}" y="{-self.L(h) / 2:.2f}" '
            f'width="{self.L(w):.2f}" height="{self.L(h):.2f}" rx="{self.L(rx):.2f}" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="{self.L(sw):.2f}" '
            f'opacity="{op}" transform="translate({cx:.2f},{cy:.2f}) rotate({-a:.2f})"/>')

    def poly(self, pts, fill, stroke="none", w=0.0, op=1.0):
        d = " ".join(f"{self.X(p[0]):.2f},{self.Y(p[1]):.2f}" for p in pts)
        self.o.append(f'<polygon points="{d}" fill="{fill}" stroke="{stroke}" '
                      f'stroke-width="{self.L(w):.2f}" opacity="{op}"/>')

    def text(self, x, y, t, col, px, anchor="middle", weight="400", op=1.0):
        self.o.append(f'<text x="{self.X(x):.2f}" y="{self.Y(y) + px * 0.35:.2f}" '
                      f'text-anchor="{anchor}" font-family="ui-sans-serif,system-ui,'
                      f'Segoe UI,Roboto,sans-serif" font-size="{px:.1f}" '
                      f'font-weight="{weight}" fill="{col}" opacity="{op}">{esc(t)}</text>')

    def raw(self, s):
        self.o.append(s)

    def svg(self, legend=()):
        H = self.h + self.head + self.foot
        parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w:.0f}" '
                 f'height="{H:.0f}" viewBox="0 0 {self.w:.0f} {H:.0f}">',
                 '<defs><marker id="ah" markerWidth="7" markerHeight="7" refX="6" '
                 f'refY="3.5" orient="auto"><path d="M0,0 L7,3.5 L0,7 z" fill="{C["dim"]}"/>'
                 '</marker></defs>',
                 f'<rect width="100%" height="100%" fill="{C["bg"]}"/>',
                 f'<text x="16" y="26" font-family="ui-sans-serif,system-ui,sans-serif" '
                 f'font-size="17" font-weight="650" fill="#F2F5F4">{esc(self.title)}</text>',
                 f'<text x="16" y="43" font-family="ui-sans-serif,system-ui,sans-serif" '
                 f'font-size="12" fill="{C["note"]}">{esc(self.subtitle)}</text>']
        parts += self.o
        x = 16
        for col, label in legend:
            parts.append(f'<rect x="{x}" y="{H - 21}" width="11" height="11" rx="2" '
                         f'fill="{col}"/>')
            parts.append(f'<text x="{x + 16}" y="{H - 12}" font-family="ui-sans-serif,'
                         f'system-ui,sans-serif" font-size="11" fill="{C["note"]}">'
                         f'{esc(label)}</text>')
            x += 30 + 6.6 * len(label)
        parts.append("</svg>")
        return "\n".join(parts)


def dim_h(cv, x0, x1, y, label):
    """Horizontal dimension line with witness lines and arrowheads."""
    for x in (x0, x1):
        cv.line((x, y - 1.6), (x, y + 1.2), C["dim"], 0.12, op=0.75)
    a, b = cv.X(x0), cv.X(x1)
    yy = cv.Y(y)
    cv.raw(f'<line x1="{a:.2f}" y1="{yy:.2f}" x2="{b:.2f}" y2="{yy:.2f}" '
           f'stroke="{C["dim"]}" stroke-width="1.1" marker-end="url(#ah)"/>')
    cv.raw(f'<line x1="{b:.2f}" y1="{yy:.2f}" x2="{a:.2f}" y2="{yy:.2f}" '
           f'stroke="{C["dim"]}" stroke-width="1.1" marker-end="url(#ah)"/>')
    cv.text((x0 + x1) / 2, y - 1.6, label, C["dim"], 12, weight="600")


def dim_v(cv, y0, y1, x, label):
    for y in (y0, y1):
        cv.line((x - 1.2, y), (x + 1.6, y), C["dim"], 0.12, op=0.75)
    a, b = cv.Y(y0), cv.Y(y1)
    xx = cv.X(x)
    cv.raw(f'<line x1="{xx:.2f}" y1="{a:.2f}" x2="{xx:.2f}" y2="{b:.2f}" '
           f'stroke="{C["dim"]}" stroke-width="1.1" marker-end="url(#ah)"/>')
    cv.raw(f'<line x1="{xx:.2f}" y1="{b:.2f}" x2="{xx:.2f}" y2="{a:.2f}" '
           f'stroke="{C["dim"]}" stroke-width="1.1" marker-end="url(#ah)"/>')
    cv.raw(f'<text transform="translate({xx - 7:.2f},{(a + b) / 2:.2f}) rotate(-90)" '
           f'text-anchor="middle" font-family="ui-sans-serif,system-ui,sans-serif" '
           f'font-size="12" font-weight="600" fill="{C["dim"]}">{esc(label)}</text>')


def draw_pad(cv, p, px, py, prot, copper=True):
    if p["ptype"] == "np_thru_hole":
        cv.circ(px, py, p["drill"] / 2, fill=C["drill"], stroke=C["substrate_edge"],
                w=0.12)
        return
    if copper:
        if p["shape"] == "circle":
            cv.circ(px, py, p["w"] / 2, fill=C["pad"], stroke=C["pad_edge"], w=0.06)
        elif p["shape"] in ("oval",):
            cv.rect(px, py, p["w"], p["h"], min(p["w"], p["h"]) / 2, prot,
                    C["pad"], C["pad_edge"], 0.06)
        else:
            rx = min(p["w"], p["h"]) * (p["rr"] or 0.0)
            cv.rect(px, py, p["w"], p["h"], rx, prot, C["pad"], C["pad_edge"], 0.06)
    if p["drill"]:
        cv.circ(px, py, p["drill"] / 2, fill=C["drill"])


def draw_board(cv, pcb, *, silk=True, bodies=True, refs=True, copper=True,
               pour=True, mirror_bottom=False):
    x0, y0, x1, y1 = pcb.extent()
    # Take the min in SCREEN space, not board space: on a mirrored view X() is
    # decreasing, so X(min(x0, x1)) is the right-hand edge and the substrate
    # rect grew off the far side of the board.
    sx = min(cv.X(x0), cv.X(x1))
    cv.raw(f'<rect x="{sx:.2f}" y="{cv.Y(y0):.2f}" '
           f'width="{cv.L(abs(x1 - x0)):.2f}" height="{cv.L(y1 - y0):.2f}" '
           f'rx="{cv.L(1.2):.2f}" fill="{C["substrate"]}"/>')
    if pour:
        for pts, layer in pcb.zones:
            if layer == "B.Cu":
                cv.poly(pts, C["pour"], C["pour"], 0.1, op=0.95)
    for a, b, w, layer in pcb.segs:
        cv.line(a, b, C["bcu"] if layer == "B.Cu" else C["fcu"], w,
                op=0.9 if layer == "F.Cu" else 0.6)
    for x, y, size, drill in pcb.vias:
        cv.circ(x, y, size / 2, fill=C["via"])
        cv.circ(x, y, drill / 2, fill=C["drill"])
    for part in pcb.parts:
        for p in part["pads"]:
            # KiCad keeps a pad's x/y in unrotated footprint space but stores
            # its angle absolutely, so the footprint rotation turns the offset
            # and nothing else - adding it to p["rot"] would count it twice.
            dx, dy = rot(p["x"], p["y"], part["rot"])
            draw_pad(cv, p, part["x"] + dx, part["y"] + dy,
                     p["rot"], copper=copper)
    if bodies:
        for part in pcb.parts:
            pts = [g for g in part["gfx"] if g[-1] == "F.Fab"]
            for g in pts:
                if g[0] == "line":
                    a = rot(*g[1], part["rot"]); b = rot(*g[2], part["rot"])
                    cv.line((part["x"] + a[0], part["y"] + a[1]),
                            (part["x"] + b[0], part["y"] + b[1]),
                            C["body"], 0.09, op=0.55)
                elif g[0] == "poly":
                    pp = [rot(*q, part["rot"]) for q in g[1]]
                    cv.poly([(part["x"] + q[0], part["y"] + q[1]) for q in pp],
                            C["body"], "none", 0, op=0.3)
    if silk:
        for part in pcb.parts:
            for g in part["gfx"]:
                if g[-1] != "F.SilkS":
                    continue
                if g[0] == "line":
                    a = rot(*g[1], part["rot"]); b = rot(*g[2], part["rot"])
                    cv.line((part["x"] + a[0], part["y"] + a[1]),
                            (part["x"] + b[0], part["y"] + b[1]), C["silk"], 0.12)
                elif g[0] == "circle":
                    c = rot(*g[1], part["rot"])
                    cv.circ(part["x"] + c[0], part["y"] + c[1], g[2],
                            stroke=C["silk"], w=0.12)
                elif g[0] == "arc":
                    a = rot(*g[1], part["rot"]); e = rot(*g[3], part["rot"])
                    cv.line((part["x"] + a[0], part["y"] + a[1]),
                            (part["x"] + e[0], part["y"] + e[1]), C["silk"], 0.12)
    for cx, cy, r, layer in pcb.circles:
        cv.circ(cx, cy, r, stroke=C["keepout"], w=0.18, op=0.8)
    for a, b in pcb.edges:
        cv.line(a, b, C["substrate_edge"], 0.22, cap="square")
    if refs:
        for part in pcb.parts:
            if not part["ref"] or not part["refpos"]:
                continue
            d = rot(*part["refpos"], part["rot"])
            cv.text(part["x"] + d[0], part["y"] + d[1], part["ref"], C["ref"],
                    max(7.0, cv.L(0.95)), weight="600")


LEGEND_ASM = ((C["substrate"], "substrate"), (C["pad"], "pad"), (C["silk"], "silkscreen"),
              (C["body"], "part body"), (C["keepout"], "gearbox keepout"),
              (C["dim"], "dimension"))
LEGEND_CU = ((C["pad"], "pad"), (C["fcu"], "F.Cu trace"), (C["bcu"], "B.Cu trace"),
             (C["via"], "via"), (C["pour"], "B.Cu ground pour"))


def view_top(pcb, name, holes, keepout):
    x0, y0, x1, y1 = pcb.extent()
    note = ""
    if keepout:
        note = (f" · red circle = gearbox ⌀{keepout[0][2] * 2:.0f} on the BACK face, "
                f"5.5 mm rear clearance")
    cv = Canvas(x0, y0, x1, y1, scale=13.0, pad=13.0,
                title=f"{name} — top assembly",
                subtitle=f"{x1 - x0:.0f} x {y1 - y0:.0f} mm · {len(pcb.parts)} parts · "
                         f"{len(pcb.segs)} traces · viewed from above{note}")
    draw_board(cv, pcb)
    dim_h(cv, x0, x1, y1 + 7.0, f"{x1 - x0:.0f} mm")
    dim_v(cv, y0, y1, x1 + 7.5, f"{y1 - y0:.0f} mm")
    if holes:
        hx = sorted({h[0] for h in holes}); hy = sorted({h[1] for h in holes})
        if len(hx) > 1:
            dim_h(cv, hx[0], hx[-1], y0 - 4.0, f"{hx[-1] - hx[0]:.0f} mm hole centres")
        if len(hy) > 1:
            dim_v(cv, hy[0], hy[-1], x0 - 4.5, f"{hy[-1] - hy[0]:.0f} mm")
    return cv.svg(LEGEND_ASM)


def view_bottom(pcb, name):
    x0, y0, x1, y1 = pcb.extent()
    cv = Canvas(x0, y0, x1, y1, scale=13.0, pad=13.0, mirror=True,
                title=f"{name} — bottom",
                subtitle="mirrored · ground pour and through-hole pads · "
                         "no parts mount on this face")
    draw_board(cv, pcb, silk=False, bodies=False, refs=True)
    dim_h(cv, x0, x1, y1 + 7.0, f"{x1 - x0:.0f} mm")
    return cv.svg(((C["pour"], "B.Cu ground pour"), (C["pad"], "through-hole pad"),
                   (C["drill"], "drill"), (C["substrate"], "substrate")))


def view_copper(pcb, name):
    x0, y0, x1, y1 = pcb.extent()
    n = len(pcb.segs)
    cv = Canvas(x0, y0, x1, y1, scale=13.0, pad=13.0,
                title=f"{name} — copper",
                subtitle=(f"{n} trace segments, {len(pcb.vias)} vias"
                          if n else
                          "NO COPPER ROUTED YET — pads and pour only; "
                          "traces appear here once the board is routed"))
    draw_board(cv, pcb, silk=False, bodies=False, refs=False)
    return cv.svg(LEGEND_CU)


def view_detail(pcb, name, box):
    x0, y0, x1, y1 = box
    cv = Canvas(x0, y0, x1, y1, scale=26.0, pad=3.0,
                title=f"{name} — detail: driver socket and MCU",
                subtitle="driver socket, MCU and the two current-sense chains — "
                         "the tightest pitch on the board")
    draw_board(cv, pcb)
    return cv.svg(LEGEND_ASM)


def main():
    import build as B
    board = sys.argv[1] if len(sys.argv) > 1 else "actuator-node"
    pcb = PCB(os.path.join(B.ROOT, board, f"{board}.kicad_pcb"))
    extra = B.EXTRA.get(board, {})
    holes = extra.get("holes", [])
    keep = [(a[0], a[1], a[2]) for kind, a, _t in extra.get("keepouts", [])
            if kind == "circle"]
    out = os.path.join(B.ROOT, board, "views")
    os.makedirs(out, exist_ok=True)
    # frame the detail on the actual extents of the driver socket and the MCU,
    # not a guessed radius about their midpoint
    import kigen
    libs = kigen.Libs(B.SYM_DIR, B.FP_DIR,
                      os.path.join(B.ROOT, board, "lib", "juno.kicad_sym"),
                      os.path.join(B.ROOT, board, "lib", "juno.pretty"))
    spec_parts = {p["ref"]: p for p in
                  __import__("spec").BOARDS[board]["parts"]}
    xs, ys = [], []
    for ref in ("U1", "A1", "U4", "U5"):
        part = next((p for p in pcb.parts if p["ref"] == ref), None)
        if not part or ref not in spec_parts:
            continue
        for bx in kigen.shift(kigen.courtyard_boxes(
                libs.footprint(*spec_parts[ref]["fp"])), part["x"], part["y"]):
            xs += [bx[0], bx[2]]
            ys += [bx[1], bx[3]]
    box = (min(xs), min(ys), max(xs), max(ys)) if xs else (18, 8, 58, 42)
    files = {
        "1-top-assembly.svg": view_top(pcb, board, holes, keep),
        "2-bottom.svg": view_bottom(pcb, board),
        "3-copper.svg": view_copper(pcb, board),
        "4-detail-driver-mcu.svg": view_detail(pcb, board, box),
    }
    for fn, body in files.items():
        open(os.path.join(out, fn), "w").write(body)
        print(f"  {out}/{fn}  ({len(body) // 1024} KB)")
    print(f"{board}: {len(pcb.parts)} parts, {len(pcb.segs)} traces, "
          f"{len(pcb.vias)} vias, {len(pcb.zones)} zone")


if __name__ == "__main__":
    main()
