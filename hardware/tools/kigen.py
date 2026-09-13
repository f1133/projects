"""KiCad 8 project generator.

Emits .kicad_pro, .kicad_sch and .kicad_pcb from a board spec. Symbol and
footprint definitions are copied out of the stock KiCad 8.0.9 libraries into
the project itself, so each project opens standalone with no library setup.

UUIDs are derived from the board name and the object, so regenerating a board
produces a byte-identical file and a diff shows real changes only.
"""

from __future__ import annotations

import hashlib
import json
import os
import re

SCH_VERSION = 20231120
PCB_VERSION = 20240108
PAPER = "A3"


# ---------------------------------------------------------------------------
# S-expression helpers
# ---------------------------------------------------------------------------

def uid(board: str, *parts) -> str:
    h = hashlib.sha256(("juno|" + board + "|" + "|".join(str(p) for p in parts))
                       .encode()).hexdigest()
    return f"{h[0:8]}-{h[8:12]}-4{h[13:16]}-a{h[17:20]}-{h[20:32]}"


def num(v) -> str:
    s = f"{round(float(v), 4):.4f}".rstrip("0").rstrip(".")
    return "0" if s in ("", "-0") else s


def block(text: str) -> list:
    """Split a library file into top-level (symbol ...) / (footprint ...) blocks."""
    out, i, n = [], 0, len(text)
    while i < n:
        if text[i] == "(":
            d, j, instr = 1, i + 1, False
            while d:
                c = text[j]
                if instr:
                    if c == "\\":
                        j += 1
                    elif c == '"':
                        instr = False
                elif c == '"':
                    instr = True
                elif c == "(":
                    d += 1
                elif c == ")":
                    d -= 1
                j += 1
            out.append(text[i:j])
            i = j
        else:
            i += 1
    return out


def top_blocks(text: str, tag: str) -> dict:
    """Map entryName -> raw s-expression for every top-level `(tag "name" ...)`."""
    inner = text[text.index("(") + 1:]
    res = {}
    for b in block(inner):
        m = re.match(r'\(\s*' + tag + r'\s+"((?:[^"\\]|\\.)*)"', b)
        if m:
            res[m.group(1).replace('\\"', '"')] = b
    return res


# ---------------------------------------------------------------------------
# Symbol library access
# ---------------------------------------------------------------------------

class Libs:
    def __init__(self, sym_dir: str, fp_dir: str, extra_sym: str, extra_fp: str):
        self.sym_dir, self.fp_dir = sym_dir, fp_dir
        self.extra_sym, self.extra_fp = extra_sym, extra_fp
        self._sym_cache: dict = {}

    def _lib_text(self, lib: str) -> str:
        path = (self.extra_sym if lib == "juno"
                else os.path.join(self.sym_dir, f"{lib}.kicad_sym"))
        with open(path) as f:
            return f.read()

    def raw_symbol(self, lib: str, name: str) -> str:
        """Symbol body, flattened so a derived symbol carries its parent's pins."""
        key = (lib, name)
        if key in self._sym_cache:
            return self._sym_cache[key]
        blocks = top_blocks(self._lib_text(lib), "symbol")
        if name not in blocks:
            raise KeyError(f"symbol {lib}:{name} not found")
        body = blocks[name]
        m = re.search(r'\(extends "([^"]+)"\)', body)
        if m:
            parent = blocks[m.group(1)]
            # take the parent's drawing units, drop its identity properties
            units = [b for b in block(parent[parent.index("(") + 1:])
                     if b.lstrip().startswith('(symbol "')]
            renamed = []
            for u in units:
                suffix = re.match(r'\(symbol "([^"]+)"', u.strip()).group(1)
                suffix = suffix[len(m.group(1)):]          # "_0_1" / "_1_1"
                renamed.append(re.sub(r'\(symbol "[^"]+"',
                                      f'(symbol "{name}{suffix}"', u, count=1))
            body = body.replace(f'\t\t(extends "{m.group(1)}")\n', "")
            body = body.rstrip()[:-1].rstrip() + "\n" + "\n".join(renamed) + "\n\t)"
        self._sym_cache[key] = body
        return body

    def pins(self, lib: str, name: str) -> list:
        """[(number, pinname, x, y, angle)] in library coordinates."""
        body = self.raw_symbol(lib, name)
        out = []
        for pb in re.finditer(r'\(pin\s+\w+\s+\w+\s*\n', body):
            seg = body[pb.start():pb.start() + 700]
            at = re.search(r'\(at ([-\d.]+) ([-\d.]+) (\d+)\)', seg)
            nm = re.search(r'\(name "((?:[^"\\]|\\.)*)"', seg)
            nu = re.search(r'\(number "((?:[^"\\]|\\.)*)"', seg)
            if at and nm and nu:
                out.append((nu.group(1), nm.group(1),
                            float(at.group(1)), float(at.group(2)), int(at.group(3))))
        return out

    def footprint(self, lib: str, name: str) -> str:
        path = (os.path.join(self.extra_fp, f"{name}.kicad_mod") if lib == "juno"
                else os.path.join(self.fp_dir, f"{lib}.pretty", f"{name}.kicad_mod"))
        with open(path) as f:
            return f.read()


# ---------------------------------------------------------------------------
# Net resolution
# ---------------------------------------------------------------------------

def resolve(board_name: str, parts: list, nets: dict, libs: Libs):
    """Turn (ref, pinname) references into (ref, pin_number) and validate.

    A reference that names a pin the symbol does not have is a hard error -
    that is the whole point of writing the spec by name.
    """
    by_ref = {p["ref"]: p for p in parts}
    pinmap = {}
    for ref, p in by_ref.items():
        pins = libs.pins(p["lib"], p["sym"])
        if not pins:
            raise ValueError(f"{ref}: symbol {p['lib']}:{p['sym']} has no pins")
        pinmap[ref] = pins

    resolved, errors = {}, []
    assigned = {}          # (ref, number) -> net
    for net, conns in nets.items():
        got = []
        for ref, want in conns:
            if ref not in by_ref:
                errors.append(f"net {net}: no part {ref}")
                continue
            pins = pinmap[ref]
            if want.endswith("*"):
                stem = want[:-1]
                hits = [n for n, nm, *_ in pins if nm == stem]
            else:
                hits = [n for n, nm, *_ in pins if nm == want]
                if not hits:
                    hits = [n for n, nm, *_ in pins if n == want]
            if not hits:
                names = sorted({nm for _, nm, *_ in pins})
                errors.append(f"net {net}: {ref} has no pin '{want}' (has {names})")
                continue
            if len(hits) > 1 and not want.endswith("*"):
                errors.append(f"net {net}: {ref} pin '{want}' is ambiguous -> {hits}")
                continue
            for h in hits:
                if (ref, h) in assigned:
                    errors.append(f"{ref} pin {h} is on both '{assigned[(ref, h)]}' "
                                  f"and '{net}'")
                assigned[(ref, h)] = net
                got.append((ref, h))
        resolved[net] = got

    if errors:
        raise ValueError(f"{board_name}: netlist errors:\n  " + "\n  ".join(errors))

    # every pin that is not on a net, so the caller can report floats
    floating = []
    for ref, pins in pinmap.items():
        for n, nm, *_ in pins:
            if (ref, n) not in assigned:
                floating.append((ref, n, nm))
    return resolved, assigned, pinmap, floating


# ---------------------------------------------------------------------------
# Layout helpers
# ---------------------------------------------------------------------------

POWER_RAILS = {
    "GND": "GND", "+3V3": "+3V3", "+5V": "+5V",
    "+19V": "+VDC", "+19V_RAW": "+VDC",
}
GRID = 2.54
STUB = 2.54


def extent(pins):
    xs = [p[2] for p in pins] or [0]
    ys = [p[3] for p in pins] or [0]
    return min(xs), max(xs), min(ys), max(ys)


def outward(angle):
    """Pins point at the body; a stub leaves in the opposite direction."""
    return {0: (-1, 0), 90: (0, 1), 180: (1, 0), 270: (0, -1)}[angle % 360]


def snap(v):
    return round(v / GRID) * GRID


# ---------------------------------------------------------------------------
# Schematic
# ---------------------------------------------------------------------------

def gen_sch(board, name, parts, nets_resolved, pinmap, libs, root_uuid):
    """One flat sheet. Every pin gets a short stub and a net label.

    Deliberately label-driven rather than wire-driven: a 53-part board routed
    with wires across one page is unreadable, and labels give exactly the same
    netlist with each block legible on its own.
    """
    by_ref = {p["ref"]: p for p in parts}
    # net for each (ref, pin)
    net_of = {}
    for net, conns in nets_resolved.items():
        for ref, pin in conns:
            net_of[(ref, pin)] = net

    # ---- place parts on a shelf grid, grouped by reference prefix ----------
    # Paper is chosen to fit rather than fixed: 53 parts with a stub and a
    # label on every pin do not go on an A3, and content off the page edge is
    # content you cannot see.
    order = sorted(by_ref, key=lambda r: (re.sub(r"\d+", "", r),
                                          int(re.sub(r"\D", "", r) or 0)))

    def layout(page_w):
        placed, x, y, shelf_h = {}, 30.0, 30.0, 0.0
        for ref in order:
            x0, x1, y0, y1 = extent(pinmap[ref])
            w = (x1 - x0) + 4 * STUB + 24      # room for stubs and labels
            h = (y1 - y0) + 4 * STUB + 14
            if x + w > page_w and shelf_h:
                x, y, shelf_h = 30.0, y + shelf_h + 6, 0.0
            placed[ref] = (snap(x + w / 2 - (x0 + x1) / 2),
                           snap(y + h / 2 + (y0 + y1) / 2))
            x += w
            shelf_h = max(shelf_h, h)
        return placed, y + shelf_h + 30

    for paper, page_w, page_h in (("A4", 250.0, 210.0), ("A3", 380.0, 297.0),
                                  ("A2", 550.0, 420.0), ("A1", 800.0, 594.0)):
        placed, sheet_h = layout(page_w)
        if sheet_h < page_h - 25:
            break

    # ---- lib_symbols -------------------------------------------------------
    used = {}
    for p in parts:
        used[f"{p['lib']}:{p['sym']}"] = (p["lib"], p["sym"])
    for rail in sorted({POWER_RAILS[n] for n in nets_resolved if n in POWER_RAILS}):
        used[f"power:{rail}"] = ("power", rail)
    used["power:PWR_FLAG"] = ("power", "PWR_FLAG")

    out = [f'(kicad_sch\n\t(version {SCH_VERSION})\n\t(generator "juno")\n'
           f'\t(generator_version "8.0")\n\t(uuid "{root_uuid}")\n\t(paper "{paper}")\n'
           f'\t(title_block\n\t\t(title "{board["title"]}")\n\t\t(rev "A")\n'
           f'\t\t(comment 1 "{board["desc"]}")\n'
           f'\t\t(comment 2 "Generated from the Juno build console - not yet ERC checked")\n\t)\n']

    out.append("\t(lib_symbols\n")
    for lib_id, (lib, sym) in sorted(used.items()):
        body = libs.raw_symbol(lib, sym)
        body = re.sub(r'\(symbol "' + re.escape(sym) + r'"',
                      f'(symbol "{lib_id}"', body, count=1)
        out.append("\t\t" + body.strip().replace("\n", "\n\t") + "\n")
    out.append("\t)\n")

    wires, labels, syms = [], [], []

    def wire(a, b, tag):
        wires.append(f'\t(wire\n\t\t(pts\n\t\t\t(xy {num(a[0])} {num(a[1])}) '
                     f'(xy {num(b[0])} {num(b[1])})\n\t\t)\n'
                     f'\t\t(stroke\n\t\t\t(width 0)\n\t\t\t(type default)\n\t\t)\n'
                     f'\t\t(uuid "{uid(name, "w", tag)}")\n\t)\n')

    def label(pos, text, angle, tag):
        just = {0: "left bottom", 90: "left bottom",
                180: "right bottom", 270: "right bottom"}[angle]
        labels.append(f'\t(label "{text}"\n\t\t(at {num(pos[0])} {num(pos[1])} {angle})\n'
                      f'\t\t(effects\n\t\t\t(font\n\t\t\t\t(size 1.27 1.27)\n\t\t\t)\n'
                      f'\t\t\t(justify {just})\n\t\t)\n'
                      f'\t\t(uuid "{uid(name, "l", tag)}")\n\t)\n')

    def place(lib_id, ref, value, fp, at, tag, props=True, hide_ref=False):
        px, py = at
        u = uid(name, "s", tag)
        s = [f'\t(symbol\n\t\t(lib_id "{lib_id}")\n\t\t(at {num(px)} {num(py)} 0)\n'
             f'\t\t(unit 1)\n\t\t(exclude_from_sim no)\n\t\t(in_bom yes)\n'
             f'\t\t(on_board yes)\n\t\t(dnp no)\n\t\t(uuid "{u}")\n']
        hid = '\n\t\t\t\t(hide yes)'
        s.append(f'\t\t(property "Reference" "{ref}"\n\t\t\t(at {num(px)} {num(py - 12.7)} 0)\n'
                 f'\t\t\t(effects\n\t\t\t\t(font\n\t\t\t\t\t(size 1.27 1.27)\n\t\t\t\t)'
                 f'{hid if hide_ref else ""}\n\t\t\t)\n\t\t)\n')
        s.append(f'\t\t(property "Value" "{value}"\n\t\t\t(at {num(px)} {num(py + 12.7)} 0)\n'
                 f'\t\t\t(effects\n\t\t\t\t(font\n\t\t\t\t\t(size 1.27 1.27)\n\t\t\t\t)\n\t\t\t)\n\t\t)\n')
        if props:
            s.append(f'\t\t(property "Footprint" "{fp}"\n\t\t\t(at {num(px)} {num(py)} 0)\n'
                     f'\t\t\t(effects\n\t\t\t\t(font\n\t\t\t\t\t(size 1.27 1.27)\n\t\t\t\t)'
                     f'{hid}\n\t\t\t)\n\t\t)\n')
            s.append(f'\t\t(property "Datasheet" "~"\n\t\t\t(at {num(px)} {num(py)} 0)\n'
                     f'\t\t\t(effects\n\t\t\t\t(font\n\t\t\t\t\t(size 1.27 1.27)\n\t\t\t\t)'
                     f'{hid}\n\t\t\t)\n\t\t)\n')
        for pnum, *_ in (pinmap.get(ref) or [("1",)]):
            s.append(f'\t\t(pin "{pnum}"\n\t\t\t(uuid "{uid(name, "p", tag, pnum)}")\n\t\t)\n')
        s.append(f'\t\t(instances\n\t\t\t(project "{name}"\n'
                 f'\t\t\t\t(path "/{root_uuid}"\n\t\t\t\t\t(reference "{ref}")\n'
                 f'\t\t\t\t\t(unit 1)\n\t\t\t\t)\n\t\t\t)\n\t\t)\n\t)\n')
        syms.append("".join(s))

    # ---- the parts ---------------------------------------------------------
    for ref in order:
        p = by_ref[ref]
        sx, sy = placed[ref]
        place(f"{p['lib']}:{p['sym']}", ref, p["value"],
              f"{p['fp'][0]}:{p['fp'][1]}", (sx, sy), ref)
        for pnum, pname, lx, ly, ang in pinmap[ref]:
            net = net_of.get((ref, pnum))
            if not net:
                continue
            ex, ey = sx + lx, sy - ly              # library Y-up -> sheet Y-down
            dx, dy = outward(ang)
            tx, ty = ex + dx * STUB, ey - dy * STUB
            wire((ex, ey), (tx, ty), f"{ref}.{pnum}")
            ang_l = {(-1, 0): 180, (1, 0): 0, (0, 1): 90, (0, -1): 270}[(dx, dy)]
            label((tx, ty), net, ang_l, f"{ref}.{pnum}")

    # ---- one power stake per rail, so ERC sees a driver --------------------
    px, py = 30.0, sheet_h - 16
    for netname in sorted(n for n in nets_resolved if n in POWER_RAILS):
        rail = POWER_RAILS[netname]
        rp = libs.pins("power", rail)[0]
        fp_ = libs.pins("power", "PWR_FLAG")[0]
        anchor = (px, py)
        place(f"power:{rail}", f"#PWR{abs(hash(netname)) % 900 + 100}", netname, "",
              (anchor[0] - rp[2], anchor[1] + rp[3]), f"pwr{netname}",
              props=False, hide_ref=True)
        place("power:PWR_FLAG", f"#FLG{abs(hash(netname)) % 900 + 100}", "PWR_FLAG", "",
              (anchor[0] + 12.7 - fp_[2], anchor[1] + fp_[3]), f"flg{netname}",
              props=False, hide_ref=True)
        wire(anchor, (anchor[0] + 12.7, anchor[1]), f"pwr{netname}")
        label((anchor[0] + 5.08, anchor[1]), netname, 0, f"pwr{netname}")
        px += 38.1
        if px > 340:
            px, py = 30.0, py - 20.32

    out += wires + labels + syms
    out.append('\t(sheet_instances\n\t\t(path "/"\n\t\t\t(page "1")\n\t\t)\n\t)\n)\n')
    return "".join(out)


# ---------------------------------------------------------------------------
# PCB
# ---------------------------------------------------------------------------

LAYERS = """\t(layers
\t\t(0 "F.Cu" signal)
\t\t(31 "B.Cu" signal)
\t\t(32 "B.Adhes" user "B.Adhesive")
\t\t(33 "F.Adhes" user "F.Adhesive")
\t\t(34 "B.Paste" user)
\t\t(35 "F.Paste" user)
\t\t(36 "B.SilkS" user "B.Silkscreen")
\t\t(37 "F.SilkS" user "F.Silkscreen")
\t\t(38 "B.Mask" user)
\t\t(39 "F.Mask" user)
\t\t(40 "Dwgs.User" user "User.Drawings")
\t\t(41 "Cmts.User" user "User.Comments")
\t\t(42 "Eco1.User" user "User.Eco1")
\t\t(43 "Eco2.User" user "User.Eco2")
\t\t(44 "Edge.Cuts" user)
\t\t(45 "Margin" user)
\t\t(46 "B.CrtYd" user "B.Courtyard")
\t\t(47 "F.CrtYd" user "F.Courtyard")
\t\t(48 "B.Fab" user)
\t\t(49 "F.Fab" user)
\t)
"""


def strip_tokens(body, tags):
    for t in tags:
        body = re.sub(r'\n\t\(' + t + r'[^\n]*\)', "", body)
    return body


def instance_footprint(raw, lib_id, ref, value, at, netmap, tag, name, layer="F.Cu"):
    """Turn a .kicad_mod body into a placed, netted footprint inside a board."""
    body = raw.strip()
    body = re.sub(r'^\(footprint "[^"]*"', f'(footprint "{lib_id}"', body, count=1)
    body = strip_tokens(body, ["version ", "generator ", "generator_version "])

    # deterministic uuids: two instances of the same part must not collide
    seen = {}

    def fresh(m):
        seen[len(seen)] = 1
        return f'(uuid "{uid(name, "fp", tag, len(seen))}")'
    body = re.sub(r'\(uuid "[^"]*"\)', fresh, body)

    # placement, right after the footprint's layer
    body = re.sub(r'(\(layer "[^"]*"\)\n)',
                  r'\1\t(uuid "' + uid(name, "fpr", tag) + '")\n'
                  f'\t(at {num(at[0])} {num(at[1])})\n', body, count=1)

    body = body.replace('(property "Reference" "REF**"', f'(property "Reference" "{ref}"')
    body = re.sub(r'\(property "Value" "[^"]*"', f'(property "Value" "{value}"', body, count=1)

    # nets onto pads
    def padnet(m):
        pnum = m.group(1)
        net = netmap.get(pnum)
        if net is None:
            return m.group(0)
        nid, nname = net
        return m.group(0).rstrip() + f'\n\t\t(net {nid} "{nname}")'
    body = re.sub(r'\(pad "([^"]+)"[^\n]*\n(?:\t\t[^\n]*\n)*?\t\t\(layers[^\n]*\)',
                  padnet, body)
    if layer == "B.Cu":
        body = re.sub(r'^\(footprint "([^"]*)"\n\t\(layer "F.Cu"\)',
                      r'(footprint "\1"\n\t(layer "B.Cu")', body, count=1)
    return "\t" + body.replace("\n", "\n\t") + "\n"


def gen_pcb(board, name, parts, nets_resolved, pinmap, libs):
    by_ref = {p["ref"]: p for p in parts}
    W, H = board["size"]

    net_ids = {"": 0}
    for i, n in enumerate(sorted(nets_resolved), start=1):
        net_ids[n] = i
    pad_net = {}
    for n, conns in nets_resolved.items():
        for ref, pin in conns:
            pad_net.setdefault(ref, {})[pin] = (net_ids[n], n)

    out = [f'(kicad_pcb\n\t(version {PCB_VERSION})\n\t(generator "juno")\n'
           f'\t(generator_version "8.0")\n'
           f'\t(general\n\t\t(thickness 1.6)\n\t\t(legacy_teardrops no)\n\t)\n'
           f'\t(paper "A4")\n']
    out.append(LAYERS)
    out.append('\t(setup\n\t\t(pad_to_mask_clearance 0)\n'
               '\t\t(allow_soldermask_bridges_in_footprints no)\n'
               '\t\t(aux_axis_origin 0 0)\n'
               '\t\t(grid_origin 0 0)\n\t)\n')
    for n, i in sorted(net_ids.items(), key=lambda kv: kv[1]):
        out.append(f'\t(net {i} "{n}")\n')

    # ---- placement ---------------------------------------------------------
    placed, spilled, regions, fill = place_by_group(
        parts, libs, board["groups"], W, H, board["edge_groups"],
        pinned=board.get("pinned"), near=board.get("near"))
    print(f"  {name}: courtyards occupy {fill * 100:.0f}% of the board area")
    if spilled:
        print(f"  {name}: {len(spilled)} parts did not fit and are parked "
              f"beside the board: {' '.join(sorted(spilled))}")

    for ref in sorted(by_ref):
        p = by_ref[ref]
        raw = libs.footprint(*p["fp"])
        out.append(instance_footprint(raw, f"{p['fp'][0]}:{p['fp'][1]}", ref,
                                      p["value"], placed[ref],
                                      pad_net.get(ref, {}), ref, name))

    # ---- group labels ------------------------------------------------------
    for g, (rx1, ry1, rx2, ry2) in sorted(regions.items()):
        out.append(f'\t(gr_text "{g}"\n\t\t(at {num(rx1 + 1)} {num(ry1 + 1.6)})\n'
                   f'\t\t(layer "Cmts.User")\n\t\t(uuid "{uid(name, "grp", g)}")\n'
                   f'\t\t(effects\n\t\t\t(font\n\t\t\t\t(size 1.4 1.4)\n'
                   f'\t\t\t\t(thickness 0.2)\n\t\t\t)\n'
                   f'\t\t\t(justify left top)\n\t\t)\n\t)\n')

    # ---- board outline -----------------------------------------------------
    def gr(kind, body, layer, tag):
        return (f'\t(gr_{kind}\n{body}\n\t\t(stroke\n\t\t\t(width 0.1)\n'
                f'\t\t\t(type default)\n\t\t)\n\t\t(layer "{layer}")\n'
                f'\t\t(uuid "{uid(name, "gr", tag)}")\n\t)\n')

    for i, (a, b) in enumerate([((0, 0), (W, 0)), ((W, 0), (W, H)),
                                ((W, H), (0, H)), ((0, H), (0, 0))]):
        out.append(gr("line", f'\t\t(start {num(a[0])} {num(a[1])})\n'
                              f'\t\t(end {num(b[0])} {num(b[1])})', "Edge.Cuts", f"edge{i}"))
    for note in board.get("keepouts", []):
        kind, args, text = note
        if kind == "circle":
            ccx, ccy, r = args
            out.append(gr("circle", f'\t\t(center {num(ccx)} {num(ccy)})\n'
                                    f'\t\t(end {num(ccx + r)} {num(ccy)})',
                          "Cmts.User", f"ko{text}"))
        out.append(f'\t(gr_text "{text}"\n\t\t(at {num(args[0])} {num(args[1])})\n'
                   f'\t\t(layer "Cmts.User")\n\t\t(uuid "{uid(name, "kt", text)}")\n'
                   f'\t\t(effects\n\t\t\t(font\n\t\t\t\t(size 1 1)\n'
                   f'\t\t\t\t(thickness 0.15)\n\t\t\t)\n\t\t)\n\t)\n')
    # ---- ground pour ------------------------------------------------------
    # The whole argument for a 2-layer board over single-sided etch was the
    # return path: CAN, the shared mic clock, the ESP32-S3 antenna and the
    # current sense all want unbroken ground under them. Filled on B.Cu so the
    # front stays free for signal routing. Delete it if you would rather pour
    # your own - it is one click.
    if "GND" in net_ids:
        z = 0.5
        out.append(
            f'\t(zone\n\t\t(net {net_ids["GND"]})\n\t\t(net_name "GND")\n'
            f'\t\t(layer "B.Cu")\n\t\t(uuid "{uid(name, "zone", "gnd")}")\n'
            f'\t\t(name "GND pour")\n\t\t(hatch edge 0.5)\n'
            f'\t\t(connect_pads\n\t\t\t(clearance 0.3)\n\t\t)\n'
            f'\t\t(min_thickness 0.25)\n\t\t(filled_areas_thickness no)\n'
            f'\t\t(fill\n\t\t\t(thermal_gap 0.4)\n\t\t\t(thermal_bridge_width 0.6)\n\t\t)\n'
            f'\t\t(polygon\n\t\t\t(pts\n'
            f'\t\t\t\t(xy {num(z)} {num(z)}) (xy {num(W - z)} {num(z)}) '
            f'(xy {num(W - z)} {num(H - z)}) (xy {num(z)} {num(H - z)})\n'
            f'\t\t\t)\n\t\t)\n\t)\n')

    for i, (hx, hy) in enumerate(board.get("holes", [])):
        out.append(f'\t(footprint "MountingHole:MountingHole_2.2mm_M2"\n'
                   f'\t\t(layer "F.Cu")\n\t\t(uuid "{uid(name, "mh", i)}")\n'
                   f'\t\t(at {num(hx)} {num(hy)})\n\t\t(attr exclude_from_pos_files)\n'
                   f'\t\t(pad "" np_thru_hole circle\n\t\t\t(at 0 0)\n\t\t\t(size 2.2 2.2)\n'
                   f'\t\t\t(drill 2.2)\n\t\t\t(layers "F&B.Cu" "*.Mask")\n'
                   f'\t\t\t(uuid "{uid(name, "mhp", i)}")\n\t\t)\n\t)\n')
    out.append(")\n")
    return "".join(out)


# ---------------------------------------------------------------------------
# Project file: netclasses and design rules
# ---------------------------------------------------------------------------
# Sized from IPC-2221 for 1 oz outer copper at a 10 C rise:
#   0.25 mm ~ 0.9 A   0.5 mm ~ 1.5 A   1.0 mm ~ 2.4 A   2.0 mm ~ 4.0 A
# All of it sits far above JLCPCB's floor (0.0889 mm track and space,
# 0.3 mm drill), so the order stays in the cheapest tier.

NETCLASSES = [
    dict(name="Default", clearance=0.2, track_width=0.25, via_diameter=0.6,
         via_drill=0.3, pcb_color="rgba(0, 0, 0, 0.000)", wire_width=6,
         bus_width=12, line_style=0, schematic_color="rgba(0, 0, 0, 0.000)"),
    dict(name="Analog", clearance=0.25, track_width=0.25, via_diameter=0.6,
         via_drill=0.3),
    dict(name="CAN", clearance=0.25, track_width=0.25, via_diameter=0.6,
         via_drill=0.3, diff_pair_width=0.25, diff_pair_gap=0.2),
    dict(name="Power", clearance=0.3, track_width=1.0, via_diameter=0.8,
         via_drill=0.4),
    dict(name="HV", clearance=0.5, track_width=2.0, via_diameter=1.0,
         via_drill=0.5),
    dict(name="Motor", clearance=0.4, track_width=1.5, via_diameter=1.0,
         via_drill=0.5),
]

PATTERNS = [
    ("HV", "+19V"), ("HV", "+19V_RAW"),
    ("Power", "+5V"), ("Power", "+3V3"), ("Power", "GND"),
    ("Motor", "PH_*"),
    ("CAN", "CAN*"),
    ("Analog", "ISENSE_*"), ("Analog", "VBUS_SENSE"), ("Analog", "NTC_SENSE"),
]


def gen_pro(name, root_uuid):
    def cls(d):
        base = dict(bus_width=12, clearance=0.2, diff_pair_gap=0.25,
                    diff_pair_via_gap=0.25, diff_pair_width=0.2,
                    line_style=0, microvia_diameter=0.3, microvia_drill=0.1,
                    pcb_color="rgba(0, 0, 0, 0.000)",
                    schematic_color="rgba(0, 0, 0, 0.000)",
                    track_width=0.25, via_diameter=0.6, via_drill=0.3,
                    wire_width=6, priority=len(NETCLASSES))
        base.update(d)
        return base

    pro = {
        "board": {
            "3dviewports": [],
            "design_settings": {
                "defaults": {
                    "board_outline_line_width": 0.1,
                    "copper_line_width": 0.2,
                    "copper_text_size_h": 1.0,
                    "copper_text_size_v": 1.0,
                    "copper_text_thickness": 0.15,
                    "other_line_width": 0.15,
                    "silk_line_width": 0.15,
                    "silk_text_size_h": 1.0,
                    "silk_text_size_v": 1.0,
                    "silk_text_thickness": 0.15,
                },
                "diff_pair_dimensions": [],
                "drc_exclusions": [],
                "rules": {
                    "max_error": 0.005,
                    "min_clearance": 0.2,
                    "min_copper_edge_clearance": 0.5,
                    "min_hole_clearance": 0.25,
                    "min_hole_to_hole": 0.5,
                    "min_microvia_diameter": 0.2,
                    "min_microvia_drill": 0.1,
                    "min_resolved_spokes": 2,
                    "min_silk_clearance": 0.0,
                    "min_text_height": 1.0,
                    "min_text_thickness": 0.15,
                    "min_through_hole_diameter": 0.3,
                    "min_track_width": 0.15,
                    "min_via_annular_width": 0.13,
                    "min_via_diameter": 0.6,
                    "solder_mask_to_copper_clearance": 0.0,
                    "use_height_for_length_calcs": True,
                },
                "track_widths": [0.0, 0.25, 0.5, 1.0, 1.5, 2.0, 3.0],
                "via_dimensions": [{"diameter": 0.0, "drill": 0.0},
                                   {"diameter": 0.6, "drill": 0.3},
                                   {"diameter": 0.8, "drill": 0.4},
                                   {"diameter": 1.0, "drill": 0.5}],
            },
            "layer_presets": [],
            "viewports": [],
        },
        "boards": [],
        "cvpcb": {"equivalence_files": []},
        "libraries": {"pinned_footprint_libs": [], "pinned_symbol_libs": []},
        "meta": {"filename": f"{name}.kicad_pro", "version": 1},
        "net_settings": {
            "classes": [cls(c) for c in NETCLASSES],
            "meta": {"version": 3},
            "net_colors": None,
            "netclass_assignments": None,
            "netclass_patterns": [{"netclass": nc, "pattern": pat}
                                  for nc, pat in PATTERNS],
        },
        "pcbnew": {"last_paths": {}, "page_layout_descr_file": ""},
        "schematic": {
            "annotate_start_num": 0,
            "drawing": {"default_line_thickness": 6.0,
                        "default_text_size": 50.0,
                        "field_names": [],
                        "intersheets_ref_show": False},
            "legacy_lib_dir": "",
            "legacy_lib_list": [],
            "meta": {"version": 1},
            "net_format_name": "",
            "spice_current_sheet_as_root": False,
        },
        "sheets": [[root_uuid, "Root"]],
        "text_variables": {},
    }
    return json.dumps(pro, indent=2) + "\n"


def sym_lib_table(entries):
    s = "(sym_lib_table\n  (version 7)\n"
    for nick, uri in entries:
        s += f'  (lib (name "{nick}")(type "KiCad")(uri "{uri}")(options "")(descr ""))\n'
    return s + ")\n"


def fp_lib_table(entries):
    s = "(fp_lib_table\n  (version 7)\n"
    for nick, uri in entries:
        s += f'  (lib (name "{nick}")(type "KiCad")(uri "{uri}")(options "")(descr ""))\n'
    return s + ")\n"


# ---------------------------------------------------------------------------
# Placement
# ---------------------------------------------------------------------------
# The console's board drawings are schematic - its parts are drawn at readable
# sizes, not real ones - so its coordinates collide once actual footprints are
# used. They are still the right intent, so they are treated as preferences:
# each part is placed at its anchor if it fits, otherwise at the nearest free
# spot. Collision is tested on courtyards, which is what a courtyard is for.

def courtyard_boxes(raw):
    """Axis-aligned keep-out boxes for a footprint, in footprint coordinates.

    Segments are grouped into connected rectangles so a part with two separate
    courtyards - the Mini, whose header rows straddle the MCU it sits over -
    keeps the gap between them usable.
    """
    segs = []
    for m in re.finditer(r'\(fp_line\s*\n\s*\(start ([-\d.]+) ([-\d.]+)\)\s*\n'
                         r'\s*\(end ([-\d.]+) ([-\d.]+)\)[\s\S]{0,160}?'
                         r'\(layer "(F|B)\.CrtYd"\)', raw):
        segs.append(((float(m.group(1)), float(m.group(2))),
                     (float(m.group(3)), float(m.group(4)))))
    if not segs:
        pts = [(float(a), float(b), float(c), float(d)) for a, b, c, d in
               re.findall(r'\(pad "[^"]+"[^\n]*\n\s*\(at ([-\d.]+) ([-\d.]+)[^\n]*\)'
                          r'\n\s*\(size ([-\d.]+) ([-\d.]+)\)', raw)]
        if not pts:
            return []
        xs = [p[0] - p[2] / 2 for p in pts] + [p[0] + p[2] / 2 for p in pts]
        ys = [p[1] - p[3] / 2 for p in pts] + [p[1] + p[3] / 2 for p in pts]
        return [(min(xs), min(ys), max(xs), max(ys))]

    groups, used = [], [False] * len(segs)
    for i in range(len(segs)):
        if used[i]:
            continue
        stack, comp = [i], []
        used[i] = True
        while stack:
            k = stack.pop()
            comp.append(segs[k])
            for j in range(len(segs)):
                if used[j]:
                    continue
                if any(abs(p[0] - q[0]) < 1e-6 and abs(p[1] - q[1]) < 1e-6
                       for p in segs[k] for q in segs[j]):
                    used[j] = True
                    stack.append(j)
        pts = [p for s in comp for p in s]
        groups.append((min(p[0] for p in pts), min(p[1] for p in pts),
                       max(p[0] for p in pts), max(p[1] for p in pts)))
    return groups


def shift(boxes, x, y):
    return [(b[0] + x, b[1] + y, b[2] + x, b[3] + y) for b in boxes]


def overlaps(a_boxes, b_boxes, gap=0.3):
    for a in a_boxes:
        for b in b_boxes:
            if (a[0] - gap < b[2] and b[0] - gap < a[2]
                    and a[1] - gap < b[3] and b[1] - gap < a[3]):
                return True
    return False


def inside(boxes, W, H, margin=0.3):
    return all(margin <= b[0] and b[2] <= W - margin
               and margin <= b[1] and b[3] <= H - margin for b in boxes)


def place_parts(parts, libs, anchors, W, H, fixed_out=None):
    """Anchor-seeded spiral placement. Returns (positions, spilled_refs)."""
    shapes = {}
    for p in parts:
        shapes[p["ref"]] = courtyard_boxes(libs.footprint(*p["fp"]))

    # big things first: they have the fewest legal positions
    def area(r):
        return sum((b[2] - b[0]) * (b[3] - b[1]) for b in shapes[r]) or 1

    order = sorted((p["ref"] for p in parts),
                   key=lambda r: (r not in anchors, -area(r)))

    taken, pos, spilled = [], {}, []
    for ref in order:
        boxes = shapes[ref]
        if not boxes:
            pos[ref] = anchors.get(ref, (W / 2, H / 2))
            continue
        ax, ay = anchors.get(ref, (W / 2, H / 2))
        best = None
        # spiral out from the preferred spot on a 0.5 mm lattice
        for radius in range(0, 200):
            step = 0.5
            cands = ([(ax, ay)] if radius == 0 else
                     [(ax + dx * step, ay + dy * step)
                      for dx in range(-radius, radius + 1)
                      for dy in range(-radius, radius + 1)
                      if max(abs(dx), abs(dy)) == radius])
            cands.sort(key=lambda c: (c[0] - ax) ** 2 + (c[1] - ay) ** 2)
            for cx, cy in cands:
                sb = shift(boxes, cx, cy)
                if not inside(sb, W, H):
                    continue
                if any(overlaps(sb, t) for t in taken):
                    continue
                best = (round(cx, 3), round(cy, 3), sb)
                break
            if best:
                break
        if best:
            pos[ref] = (best[0], best[1])
            taken.append(best[2])
        else:
            spilled.append(ref)
    # anything that genuinely does not fit goes in a field beside the board
    cx, cy = W + 10.0, 5.0
    for ref in spilled:
        pos[ref] = (round(cx, 3), round(cy, 3))
        cy += 7.0
        if cy > H:
            cy, cx = 5.0, cx + 12.0
    return pos, spilled


# ---------------------------------------------------------------------------
# Group-aware placement
# ---------------------------------------------------------------------------
# Parts are placed by functional block rather than scattered: the CAN
# transceiver with its termination and decoupling, the crystal with its two
# load caps, each INA240 with its shunt. Every net then has a short local run
# and the long hauls are only the handful that genuinely cross the board.

SLACK = 3.4          # region area per unit of courtyard area - routing room
EDGE_MARGIN = 1.5


def region_layout(parts, libs, groups, W, H, edge_groups):
    """Shelf-pack a rectangle per group, sized in proportion to what the group
    needs and scaled so the set always fits the board. Edge groups take the
    outer shelves, where the cable and the eye can reach them."""
    shapes = {p["ref"]: courtyard_boxes(libs.footprint(*p["fp"])) for p in parts}

    def area(ref):
        return sum((b[2] - b[0]) * (b[3] - b[1]) for b in shapes[ref]) or 1.0

    weight = {g: sum(area(r) for r in refs if r in shapes)
              for g, refs in groups.items() if any(r in shapes for r in refs)}
    total = sum(weight.values()) or 1.0

    usable_w = W - 2 * EDGE_MARGIN
    usable_h = H - 2 * EDGE_MARGIN
    budget = usable_w * usable_h * 0.96

    edges = [g for g in weight if g in edge_groups]
    others = [g for g in weight if g not in edge_groups]
    half = (len(edges) + 1) // 2
    order = edges[:half] + others + edges[half:]

    # rows of roughly equal height, filled in order
    rows, row, row_w = [], [], 0.0
    target_row_w = usable_w
    for g in order:
        gw = weight[g] / total * budget
        w = min(usable_w, max(6.0, (gw * 1.6) ** 0.5))
        if row and row_w + w > target_row_w:
            rows.append(row)
            row, row_w = [], 0.0
        row.append((g, w))
        row_w += w
    if row:
        rows.append(row)

    row_weight = [sum(weight[g] for g, _ in r) for r in rows]
    tw = sum(row_weight) or 1.0
    regions, y = {}, EDGE_MARGIN
    for r, rw in zip(rows, row_weight):
        h = usable_h * rw / tw
        span = sum(w for _, w in r) or 1.0
        x = EDGE_MARGIN
        for g, w in r:
            ww = w / span * usable_w
            regions[g] = (x, y, x + ww, y + h)
            x += ww
        y += h
    fill = total / (usable_w * usable_h)
    return regions, shapes, y + EDGE_MARGIN, fill


def place_by_group(parts, libs, groups, W, H, edge_groups, pinned=None, near=None):
    """Returns (positions, spilled, regions, needed_height).

    `pinned` parts have a mechanical reason to be where they are - the two
    microphones must stay exactly 130 mm apart or they stop being a bearing -
    so they are placed first and everything else routes around them.
    """
    of = {}
    for g, refs in groups.items():
        for r in refs:
            of[r] = g
    regions, shapes, needed_h, fill = region_layout(parts, libs, groups, W, H, edge_groups)

    # inside a region, the biggest part first and the rest packed around it
    def area(ref):
        return sum((b[2] - b[0]) * (b[3] - b[1]) for b in shapes[ref]) or 1.0

    order = sorted((p["ref"] for p in parts),
                   key=lambda r: (of.get(r, "zz"), -area(r)))

    taken, pos, spilled = [], {}, []
    pinned = pinned or {}
    for ref, (px, py) in pinned.items():
        if ref in shapes:
            pos[ref] = (px, py)
            taken.append(shift(shapes[ref], px, py))

    def _to_box(cx, cy, box):
        dx = max(box[0] - cx, 0.0, cx - box[2])
        dy = max(box[1] - cy, 0.0, cy - box[3])
        return dx * dx + dy * dy

    def put(ref, ax, ay, reg, toward=None):
        """Place ref at the first free spot, preferring closeness to `toward`.

        `toward` is the courtyard of the part this one must hug. Ranking by
        distance to that courtyard rather than to its origin matters for long
        parts: an HC49-SD crystal's courtyard is 20 mm wide, so its origin is
        10 mm from the pads its load caps actually need to be near.
        """
        boxes = shapes.get(ref)
        if not boxes:
            return False
        for radius in range(0, 240):
            cands = ([(ax, ay)] if radius == 0 else
                     [(ax + dx * 0.5, ay + dy * 0.5)
                      for dx in range(-radius, radius + 1)
                      for dy in range(-radius, radius + 1)
                      if max(abs(dx), abs(dy)) == radius])
            if toward:
                cands.sort(key=lambda c: (not (reg[0] <= c[0] <= reg[2]
                                               and reg[1] <= c[1] <= reg[3]),
                                          min(_to_box(c[0], c[1], b) for b in toward)))
            else:
                cands.sort(key=lambda c: (not (reg[0] <= c[0] <= reg[2]
                                               and reg[1] <= c[1] <= reg[3]),
                                          (c[0] - ax) ** 2 + (c[1] - ay) ** 2))
            for cx, cy in cands:
                sb = shift(boxes, cx, cy)
                if not inside(sb, W, H, EDGE_MARGIN):
                    continue
                if any(overlaps(sb, t) for t in taken):
                    continue
                pos[ref] = (round(cx, 3), round(cy, 3))
                taken.append(sb)
                return True
        return False

    # Parts with an electrical reason to hug another part are placed against it
    # rather than merely in the same region: a crystal 30 mm from its MCU is in
    # the right group and still wrong. Targets go down first, then their
    # dependants, then everything else.
    near = {k: v for k, v in (near or {}).items() if k in shapes and v in shapes}
    free = (-W * 2, -H * 2, W * 3, H * 3)

    # Chains matter: the crystal hugs the MCU and its load caps hug the crystal,
    # so a part that is itself somebody's target must not be placed at its
    # region centre first. Roots go down by region, then dependants in order.
    roots = [t for t in dict.fromkeys(near.values()) if t not in near]
    for ref in sorted(roots, key=lambda r: -area(r)):
        if ref in pos:
            continue
        reg = regions.get(of.get(ref), (EDGE_MARGIN, EDGE_MARGIN, W, H))
        put(ref, (reg[0] + reg[2]) / 2, (reg[1] + reg[3]) / 2, reg)

    # Depth first, not breadth first. The crystal hangs off the MCU and its two
    # load caps hang off the crystal; placing every first-level dependant before
    # any second-level one lets unrelated parts take the space right beside the
    # crystal and pushes its caps out. Following each chain to its end as soon
    # as it is reachable keeps the tightest links tightest.
    children = {}
    for ref, tgt in near.items():
        children.setdefault(tgt, []).append(ref)
    for kids in children.values():
        kids.sort(key=lambda r: -area(r))

    def place_chain(tgt):
        for ref in children.get(tgt, []):
            if ref in pos:
                continue
            anchor = pos.get(tgt)
            if anchor is None:
                continue
            if not put(ref, anchor[0], anchor[1], free,
                       toward=shift(shapes[tgt], *anchor)):
                spilled.append(ref)
                continue
            place_chain(ref)

    for root in sorted(dict.fromkeys(near.values()), key=lambda r: -area(r)):
        place_chain(root)
    for ref in sorted(near, key=lambda r: -area(r)):
        if ref not in pos and ref not in spilled:
            tgt_pos = pos.get(near[ref])
            if tgt_pos is not None and not put(
                    ref, tgt_pos[0], tgt_pos[1], free,
                    toward=shift(shapes[near[ref]], *tgt_pos)):
                spilled.append(ref)

    for ref in order:
        if ref in pos or ref in spilled:
            continue
        boxes = shapes.get(ref)
        if not boxes:
            continue
        reg = regions.get(of.get(ref), (EDGE_MARGIN, EDGE_MARGIN, W, H))
        ax, ay = (reg[0] + reg[2]) / 2, (reg[1] + reg[3]) / 2
        best = None
        for radius in range(0, 240):
            step = 0.5
            cands = ([(ax, ay)] if radius == 0 else
                     [(ax + dx * step, ay + dy * step)
                      for dx in range(-radius, radius + 1)
                      for dy in range(-radius, radius + 1)
                      if max(abs(dx), abs(dy)) == radius])
            # prefer staying inside the group's own region
            cands.sort(key=lambda c: (not (reg[0] <= c[0] <= reg[2]
                                           and reg[1] <= c[1] <= reg[3]),
                                      (c[0] - ax) ** 2 + (c[1] - ay) ** 2))
            for cx, cy in cands:
                sb = shift(boxes, cx, cy)
                if not inside(sb, W, H, EDGE_MARGIN):
                    continue
                if any(overlaps(sb, t) for t in taken):
                    continue
                best = (round(cx, 3), round(cy, 3), sb)
                break
            if best:
                break
        if best:
            pos[ref] = (best[0], best[1])
            taken.append(best[2])
        else:
            spilled.append(ref)
    cx, cy = W + 10.0, 5.0
    for ref in spilled:
        pos[ref] = (round(cx, 3), round(cy, 3))
        cy += 7.0
        if cy > H:
            cy, cx = 5.0, cx + 12.0
    return pos, spilled, regions, fill
