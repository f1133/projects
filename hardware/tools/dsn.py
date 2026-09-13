"""Specctra DSN export, so the placed board can be handed to an autorouter.

KiCad would normally write this, but kicad-cli is not available here, so it is
built from the .kicad_pcb the generator emitted. Only what freerouting actually
reads is produced: layers, outline, placement, pad geometry, nets and classes.

Units: DSN is 1/10 um here, and its Y axis points up where KiCad's points down,
so every Y is negated on the way out.
"""

import sexp

SCALE = 10000.0            # mm -> 1/10 um
LAYERS = ("F.Cu", "B.Cu")


def u(mm):
    return int(round(float(mm) * SCALE))


class Board:
    """The parts of a .kicad_pcb that matter for routing."""

    def __init__(self, path):
        self.root = sexp.parse(open(path).read())
        self.nets = {}                       # id -> name
        for n in sexp.findall(self.root, "net"):
            self.nets[int(n[1])] = str(n[2]) if len(n) > 2 else ""
        self.footprints = []
        for f in sexp.findall(self.root, "footprint"):
            at = sexp.find(f, "at")
            rot = float(at[3]) if len(at) > 3 else 0.0
            ref = None
            for p in sexp.findall(f, "property"):
                if str(p[1]) == "Reference":
                    ref = str(p[2])
            pads = []
            for p in sexp.findall(f, "pad"):
                num = str(p[1])
                if not num:
                    continue                  # unnumbered = mounting hole
                pat = sexp.find(p, "at")
                size = sexp.find(p, "size")
                drill = sexp.find(p, "drill")
                net = sexp.find(p, "net")
                pads.append(dict(
                    num=num, ptype=p[2], shape=p[3],
                    x=float(pat[1]), y=float(pat[2]),
                    rot=float(pat[3]) if len(pat) > 3 else 0.0,
                    w=float(size[1]), h=float(size[2]),
                    drill=float(drill[1]) if drill else None,
                    net=int(net[1]) if net else 0,
                ))
            self.footprints.append(dict(lib=str(f[1]), ref=ref, x=float(at[1]),
                                        y=float(at[2]), rot=rot, pads=pads))
        self.outline = []
        for g in sexp.findall(self.root, "gr_line"):
            if str(sexp.val(g, "layer")) == "Edge.Cuts":
                s = sexp.find(g, "start")
                e = sexp.find(g, "end")
                self.outline.append(((float(s[1]), float(s[2])),
                                     (float(e[1]), float(e[2]))))


def padstack_id(pad):
    """A name per distinct pad geometry, so identical pads share a padstack."""
    kind = "Th" if pad["drill"] else "Smd"
    shape = "Round" if pad["shape"] in ("circle", "oval") else "Rect"
    d = f"_{u(pad['drill'])}" if pad["drill"] else ""
    return f"{kind}{shape}_{u(pad['w'])}x{u(pad['h'])}{d}"


def padstack_def(pad):
    pid = padstack_id(pad)
    # Integers, not floats: DSN coordinates are whole units at the declared
    # resolution, and freerouting's geometry goes haywire on "-5750.0".
    w, h = u(pad["w"] / 2), u(pad["h"] / 2)
    layers = LAYERS if pad["drill"] else ("F.Cu",)
    s = f'    (padstack "{pid}"\n'
    for ly in layers:
        if pad["shape"] in ("circle",) or (pad["shape"] == "oval"
                                           and abs(pad["w"] - pad["h"]) < 1e-6):
            s += f'      (shape (circle {ly} {u(pad["w"])}))\n'
        else:
            s += f'      (shape (rect {ly} {-w} {-h} {w} {h}))\n'
    s += "      (attach off)\n    )\n"
    return pid, s


def export(pcb_path, dsn_path, netclass_of, class_rules, via_pad=0.6,
           via_drill=0.3, skip_nets=()):
    b = Board(pcb_path)
    for f in b.footprints:
        if abs(f["rot"]) > 1e-6:
            raise ValueError(f"{f['ref']} is rotated; DSN export assumes 0")

    # ---- padstacks, one per distinct geometry -----------------------------
    stacks, images = {}, {}
    for f in b.footprints:
        img = f["lib"]
        if img not in images:
            pins = []
            for p in f["pads"]:
                pid, sdef = padstack_def(p)
                stacks[pid] = sdef
                pins.append(f'      (pin "{pid}" "{p["num"]}" '
                            f'{u(p["x"])} {u(-p["y"])})\n')
            images[img] = pins
    via_id = f"Via[0-1]_{u(via_pad)}:{u(via_drill)}"
    stacks[via_id] = (f'    (padstack "{via_id}"\n'
                      + "".join(f'      (shape (circle {ly} {u(via_pad)}))\n'
                                for ly in LAYERS)
                      + "      (attach off)\n    )\n")

    out = ['(pcb "board"\n  (parser\n    (string_quote ")\n'
           '    (space_in_quoted_tokens on)\n    (host_cad "juno")\n'
           '    (host_version "1")\n  )\n']
    out.append(f"  (resolution um 10)\n  (unit um)\n")

    # ---- structure ---------------------------------------------------------
    out.append("  (structure\n")
    for i, ly in enumerate(LAYERS):
        out.append(f"    (layer {ly}\n      (type signal)\n"
                   f"      (property (index {i}))\n    )\n")
    pts = []
    if b.outline:
        chain = [b.outline[0][0], b.outline[0][1]]
        rest = list(b.outline[1:])
        while rest:
            for k, (s, e) in enumerate(rest):
                if abs(s[0] - chain[-1][0]) < 1e-6 and abs(s[1] - chain[-1][1]) < 1e-6:
                    chain.append(e); rest.pop(k); break
                if abs(e[0] - chain[-1][0]) < 1e-6 and abs(e[1] - chain[-1][1]) < 1e-6:
                    chain.append(s); rest.pop(k); break
            else:
                break
        pts = chain
    out.append("    (boundary\n      (path pcb 0")
    for (px, py) in pts:
        out.append(f"  {u(px)} {u(-py)}")
    out.append("\n      )\n    )\n")
    out.append(f'    (via "{via_id}")\n')
    d = class_rules["Default"]
    out.append(f'    (rule\n      (width {u(d["track"])})\n'
               f'      (clearance {u(d["clearance"])})\n'
               f'      (clearance {u(d["clearance"])} (type default_smd))\n'
               f'      (clearance {u(d["clearance"])} (type smd_smd))\n    )\n')
    out.append("  )\n")

    # ---- placement ---------------------------------------------------------
    out.append("  (placement\n")
    by_img = {}
    for f in b.footprints:
        by_img.setdefault(f["lib"], []).append(f)
    for img, fps in by_img.items():
        out.append(f'    (component "{img}"\n')
        for f in fps:
            out.append(f'      (place "{f["ref"]}" {u(f["x"])} {u(-f["y"])} '
                       f'front 0)\n')
        out.append("    )\n")
    out.append("  )\n")

    # ---- library -----------------------------------------------------------
    out.append("  (library\n")
    for img, pins in images.items():
        out.append(f'    (image "{img}"\n')
        out.extend(pins)
        out.append("    )\n")
    for sdef in stacks.values():
        out.append(sdef)
    out.append("  )\n")

    # ---- network -----------------------------------------------------------
    # Nets in skip_nets are left out of the routing problem entirely - GND is
    # a solid pour on the back, so asking an autorouter to also thread 52 pins
    # of it as traces doubles the search space for nothing.
    pins_of = {}
    for f in b.footprints:
        for p in f["pads"]:
            if p["net"] and b.nets[p["net"]] not in skip_nets:
                pins_of.setdefault(b.nets[p["net"]], []).append(
                    f'{f["ref"]}-{p["num"]}')
    out.append("  (network\n")
    for name, pl in sorted(pins_of.items()):
        if len(pl) < 2:
            continue
        out.append(f'    (net "{name}"\n      (pins ' + " ".join(pl) + ")\n    )\n")
    used = {}
    for name in pins_of:
        used.setdefault(netclass_of(name), []).append(name)
    for cls, names in sorted(used.items()):
        r = class_rules.get(cls, class_rules["Default"])
        members = " ".join(f'"{n}"' for n in sorted(names) if len(pins_of[n]) >= 2)
        out.append(f'    (class {cls} {members}\n'
                   f'      (circuit (use_via {via_id}))\n'
                   f'      (rule (width {u(r["track"])}) '
                   f'(clearance {u(r["clearance"])}))\n    )\n')
    out.append("  )\n")
    out.append("  (wiring\n  )\n)\n")
    open(dsn_path, "w").write("".join(out))
    return b
