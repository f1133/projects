"""Check a routed board: is every net actually joined by copper?

An autorouter reports its own unrouted count, but that is its bookkeeping, not
the board's. This works from the emitted .kicad_pcb instead - pads, segments and
vias - and unions everything that physically touches. What it reports is what
the fab would build.
"""

import math
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sexp                                                   # noqa: E402

TOL = 0.02          # mm; endpoints that land this close are the same point


class DSU:
    def __init__(self):
        self.p = {}

    def find(self, a):
        self.p.setdefault(a, a)
        while self.p[a] != a:
            self.p[a] = self.p[self.p[a]]
            a = self.p[a]
        return a

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[ra] = rb


def _rot(x, y, deg):
    r = math.radians(deg)
    return x * math.cos(r) + y * math.sin(r), -x * math.sin(r) + y * math.cos(r)


def analyse(pcb_path):
    root = sexp.parse(open(pcb_path).read())
    net_name = {int(n[1]): (str(n[2]) if len(n) > 2 else "") for n in sexp.findall(root, "net")}

    pads = []          # (net, x, y, hw, hh, layers)
    for f in sexp.findall(root, "footprint"):
        at = sexp.find(f, "at")
        fx, fy = float(at[1]), float(at[2])
        frot = float(at[3]) if len(at) > 3 else 0.0
        for p in sexp.findall(f, "pad"):
            net = sexp.find(p, "net")
            if not net:
                continue
            pat = sexp.find(p, "at")
            size = sexp.find(p, "size")
            px, py = _rot(float(pat[1]), float(pat[2]), frot)
            lay = sexp.find(p, "layers")
            through = p[2] == "thru_hole"
            pads.append(dict(net=int(net[1]), x=fx + px, y=fy + py,
                             hw=float(size[1]) / 2, hh=float(size[2]) / 2,
                             through=through,
                             layer="F.Cu" if not through else "*"))

    segs = []
    for s in sexp.findall(root, "segment"):
        a = sexp.find(s, "start"); b = sexp.find(s, "end")
        segs.append(dict(net=int(sexp.find(s, "net")[1]),
                         a=(float(a[1]), float(a[2])), b=(float(b[1]), float(b[2])),
                         layer=str(sexp.val(s, "layer"))))
    vias = []
    for v in sexp.findall(root, "via"):
        a = sexp.find(v, "at")
        vias.append(dict(net=int(sexp.find(v, "net")[1]),
                         at=(float(a[1]), float(a[2]))))

    # union everything that touches, per net
    dsu = DSU()
    nodes = {}
    for i, p in enumerate(pads):
        nodes.setdefault(p["net"], []).append(("pad", i))
    for i, s in enumerate(segs):
        nodes.setdefault(s["net"], []).append(("seg", i))

    def near(p, q):
        return abs(p[0] - q[0]) <= TOL and abs(p[1] - q[1]) <= TOL

    def in_pad(pt, pad, layer):
        if not pad["through"] and layer != "F.Cu":
            return False
        return (abs(pt[0] - pad["x"]) <= pad["hw"] + TOL
                and abs(pt[1] - pad["y"]) <= pad["hh"] + TOL)

    for si, s in enumerate(segs):
        dsu.union(("seg", si), ("seg", si))
        for pi, p in enumerate(pads):
            if p["net"] != s["net"]:
                continue
            if in_pad(s["a"], p, s["layer"]) or in_pad(s["b"], p, s["layer"]):
                dsu.union(("seg", si), ("pad", pi))
        for sj in range(si + 1, len(segs)):
            t = segs[sj]
            if t["net"] != s["net"] or t["layer"] != s["layer"]:
                continue
            if any(near(x, y) for x in (s["a"], s["b"]) for y in (t["a"], t["b"])):
                dsu.union(("seg", si), ("seg", sj))
    # a via joins whatever touches it on either layer
    for v in vias:
        touching = [("seg", i) for i, s in enumerate(segs)
                    if s["net"] == v["net"] and (near(s["a"], v["at"])
                                                 or near(s["b"], v["at"]))]
        for t in touching[1:]:
            dsu.union(touching[0], t)

    report = {}
    for net, members in nodes.items():
        name = net_name.get(net, "")
        if not name or len([m for m in members if m[0] == "pad"]) < 2:
            continue
        roots = {dsu.find(m) for m in members if m[0] == "pad"}
        report[name] = len(roots)
    return report, len(segs), len(vias)


if __name__ == "__main__":
    rep, ns, nv = analyse(sys.argv[1])
    bad = {k: v for k, v in rep.items() if v > 1}
    print(f"{ns} segments, {nv} vias, {len(rep)} nets with 2+ pads")
    if bad:
        print(f"{len(bad)} net(s) NOT fully joined by copper:")
        for k, v in sorted(bad.items(), key=lambda kv: -kv[1]):
            print(f"   {k:<14} {v} separate islands")
    else:
        print("every net is a single connected island")
