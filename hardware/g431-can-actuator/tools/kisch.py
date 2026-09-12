"""Minimal KiCad 7 (.kicad_sch, version 20230121) schematic writer.

Only the subset needed to bootstrap this project is implemented: symbol
placement with exact pin-endpoint geometry, wires, junctions, net labels,
hierarchical labels/pins and sheet symbols.

Coordinate systems
------------------
Symbol libraries use a Y-up coordinate system; schematics use Y-down.  A pin
declared at ``(at px py angle)`` in the library has its *electrical* endpoint
at ``(px, py)``; the drawn pin line runs from there towards the symbol body in
the direction ``angle``.  Placing a symbol at ``(X, Y)`` with rotation ``rot``
maps a library point through :func:`lin` and then translates by ``(X, Y)``.
"""

from __future__ import annotations

import hashlib
import math
import os
import re

# --------------------------------------------------------------------------
# S-expression parsing (just enough for .kicad_sym)
# --------------------------------------------------------------------------


def parse_sexp(text: str):
    i, n = 0, len(text)

    def skip(i):
        while i < n and text[i] in " \t\r\n":
            i += 1
        return i

    def node(i):
        i = skip(i)
        if text[i] == "(":
            i += 1
            out = []
            while True:
                i = skip(i)
                if text[i] == ")":
                    return out, i + 1
                v, i = node(i)
                out.append(v)
        if text[i] == '"':
            i += 1
            buf = []
            while text[i] != '"':
                if text[i] == "\\":
                    buf.append(text[i + 1])
                    i += 2
                else:
                    buf.append(text[i])
                    i += 1
            return "".join(buf), i + 1
        j = i
        while i < n and text[i] not in " \t\r\n()":
            i += 1
        return text[j:i], i

    v, _ = node(0)
    return v


def quote(s: str) -> str:
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"') + '"'


def num(v: float) -> str:
    """Format a coordinate the way KiCad does (trim trailing zeros)."""
    s = f"{round(float(v), 4):.4f}".rstrip("0").rstrip(".")
    return "0" if s in ("", "-0") else s


# --------------------------------------------------------------------------
# Deterministic UUIDs -- regenerating the project must not churn the diff.
# --------------------------------------------------------------------------

_UUID_SALT = "g431-can-actuator"


def uuid_for(*parts) -> str:
    h = hashlib.sha256((_UUID_SALT + "|" + "|".join(str(p) for p in parts)).encode()).hexdigest()
    return f"{h[0:8]}-{h[8:12]}-4{h[13:16]}-a{h[17:20]}-{h[20:32]}"


# --------------------------------------------------------------------------
# Placement transform
# --------------------------------------------------------------------------


def lin(x: float, y: float, rot: int):
    """Linear part of the library->schematic transform for ``rot`` degrees."""
    rot %= 360
    if rot == 0:
        return (x, -y)
    if rot == 90:
        return (-y, -x)
    if rot == 180:
        return (-x, y)
    if rot == 270:
        return (y, x)
    raise ValueError(f"unsupported rotation {rot}")


def dir_vec(angle_deg: float, rot: int):
    """Unit direction of a library angle, expressed in schematic space."""
    a = math.radians(angle_deg)
    return lin(math.cos(a), math.sin(a), rot)


def snap(v: float) -> float:
    return round(v, 4)


# --------------------------------------------------------------------------
# Symbol library access
# --------------------------------------------------------------------------

DEFAULT_SYMBOL_DIRS = [
    os.environ.get("KICAD_SYMBOL_DIR", ""),
    "/usr/share/kicad/symbols",
    "/usr/share/kicad/library",
]


class SymbolLib:
    """Reads ``.kicad_sym`` libraries and extracts self-contained symbols."""

    def __init__(self, search_dirs=None, extra_libs=None):
        self.dirs = [d for d in (search_dirs or DEFAULT_SYMBOL_DIRS) if d and os.path.isdir(d)]
        if not self.dirs:
            raise SystemExit(
                "No KiCad symbol directory found. Install KiCad or set KICAD_SYMBOL_DIR."
            )
        # extra_libs: {"LibNick": "/path/to/file.kicad_sym"}
        self.extra = dict(extra_libs or {})
        self._files = {}
        self._cache = {}
        self._fields = {}

    def _text(self, nick: str) -> str:
        if nick in self._files:
            return self._files[nick]
        path = self.extra.get(nick)
        if path is None:
            for d in self.dirs:
                cand = os.path.join(d, nick + ".kicad_sym")
                if os.path.isfile(cand):
                    path = cand
                    break
        if path is None:
            raise KeyError(f"symbol library {nick!r} not found in {self.dirs}")
        self._files[nick] = open(path, encoding="utf-8").read()
        return self._files[nick]

    @staticmethod
    def _slice(text: str, name: str) -> str:
        """Return the raw text of a top-level ``(symbol "name" ...)`` block."""
        m = re.search(r'\n[ \t]*\(symbol "' + re.escape(name) + r'"[ \n\t]', text)
        if not m:
            raise KeyError(f"symbol {name!r} not present")
        i = text.index("(", m.start())
        depth, j = 0, i
        while True:
            c = text[j]
            if c == '"':                      # skip strings
                j += 1
                while text[j] != '"':
                    j += 2 if text[j] == "\\" else 1
            elif c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
                if depth == 0:
                    return text[i : j + 1]
            j += 1

    def get(self, lib_id: str):
        """Return ``(lib_symbols_text, pins, props)`` for ``Lib:Name``."""
        if lib_id in self._cache:
            return self._cache[lib_id]
        nick, name = lib_id.split(":", 1)
        text = self._text(nick)
        raw = self._slice(text, name)
        tree = parse_sexp(raw)

        # An "extends" symbol inherits every graphic and pin from its parent.
        parent = next((e[1] for e in tree[1:] if isinstance(e, list) and e[0] == "extends"), None)
        geom_name = name
        if parent:
            geom_name = parent
            base_raw = self._slice(text, parent)
            base_tree = parse_sexp(base_raw)
        else:
            base_tree = tree

        pins = self._pins(base_tree, geom_name, text)
        props = {e[1]: e[2] for e in tree[1:] if isinstance(e, list) and e[0] == "property"}
        if parent:
            base_props = {
                e[1]: e[2] for e in base_tree[1:] if isinstance(e, list) and e[0] == "property"
            }
            for k, v in base_props.items():
                props.setdefault(k, v)

        body = self._flatten(lib_id, name, raw, base_raw if parent else raw, geom_name)
        self._fields[lib_id] = self._field_geom(raw, base_raw if parent else raw)
        self._cache[lib_id] = (body, pins, props)
        return self._cache[lib_id]

    def fields(self, lib_id):
        """{property: (x, y, angle, hidden)} as declared by the library."""
        if lib_id not in self._fields:
            self.get(lib_id)
        return self._fields[lib_id]

    def _field_geom(self, raw, base_raw):
        out = {}
        for src in ((base_raw,) if base_raw is raw else (base_raw, raw)):
            for blk, _col in self._children(src, "property"):
                key = self._prop_key(blk)
                m = re.search(r"\(at\s+(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)\)", blk)
                if key is None or m is None:
                    continue
                # A bare "hide" token anywhere in the property marks it
                # invisible; strip quoted strings first so a value that
                # happens to contain the word does not count.
                bare = re.sub(r'"(?:[^"\\]|\\.)*"', '""', blk)
                hidden = re.search(r"(?<![\w-])hide(?![\w-])", bare) is not None
                out[key] = (float(m.group(1)), float(m.group(2)),
                            int(float(m.group(3))), hidden)
        return out

    @staticmethod
    def _unit_names(name: str, text: str):
        pat = re.compile(r'\n[ \t]*\(symbol "' + re.escape(name) + r'_(\d+)_(\d+)"')
        return [f"{name}_{m.group(1)}_{m.group(2)}" for m in pat.finditer(text)]

    def _pins(self, base_tree, geom_name: str, text: str):
        """{pin_number: (x, y, angle, unit)} in library coordinates."""
        out = {}

        def walk(node, unit):
            for x in node:
                if not isinstance(x, list):
                    continue
                if x[0] == "pin":
                    at = next(y for y in x if isinstance(y, list) and y[0] == "at")
                    number = next(y[1] for y in x if isinstance(y, list) and y[0] == "number")
                    out[number] = (float(at[1]), float(at[2]), int(float(at[3])), unit)
                elif x[0] == "symbol":
                    m = re.match(re.escape(geom_name) + r"_(\d+)_(\d+)$", x[1])
                    walk(x, int(m.group(1)) if m else unit)
                else:
                    walk(x, unit)

        walk(base_tree, 1)
        return out

    # -- text-level flattening -------------------------------------------
    # Re-serialising a parsed s-expression would lose the difference between
    # a quoted string and a bare token, so symbol bodies are assembled from
    # raw text slices instead.

    @staticmethod
    def _children(raw: str, head: str):
        """Top-level ``(head ...)`` blocks inside a symbol block, as raw text."""
        out, depth, i, n = [], 0, 0, len(raw)
        start = None
        while i < n:
            c = raw[i]
            if c == '"':
                i += 1
                while raw[i] != '"':
                    i += 2 if raw[i] == "\\" else 1
            elif c == "(":
                depth += 1
                if depth == 2 and raw.startswith("(" + head, i):
                    nxt = raw[i + 1 + len(head)]
                    if nxt in ' \t\n"()':
                        start = i
            elif c == ")":
                if depth == 2 and start is not None:
                    col = start - (raw.rfind("\n", 0, start) + 1)
                    out.append((raw[start : i + 1], col))
                    start = None
                depth -= 1
            i += 1
        return out

    @staticmethod
    def _prop_key(block: str):
        m = re.match(r'\(property\s+"((?:[^"\\]|\\.)*)"', block)
        return m.group(1) if m else None

    @staticmethod
    def _header_flags(raw: str, name: str):
        flags = []
        for head in ("pin_numbers", "pin_names", "in_bom", "on_board"):
            for blk, _col in SymbolLib._children(raw, head):
                flags.append(blk)
        return flags

    def _flatten(self, lib_id, name, raw, base_raw, geom_name):
        """Build a self-contained ``lib_symbols`` entry keyed by ``lib_id``."""
        flags = self._header_flags(base_raw, geom_name)
        if base_raw is not raw:
            own = self._header_flags(raw, name)
            seen = {b.split()[0] for b in own}
            flags = own + [b for b in flags if b.split()[0] not in seen]

        props = {}
        order = []
        for src in ((base_raw,) if base_raw is raw else (base_raw, raw)):
            for blk, col in self._children(src, "property"):
                key = self._prop_key(blk)
                if key is None:
                    continue
                if key not in props:
                    order.append(key)
                props[key] = (blk, col)

        units = []
        for blk, col in self._children(base_raw, "symbol"):
            m = re.match(r'\(symbol\s+"' + re.escape(geom_name) + r'(_\d+_\d+)"', blk)
            if not m:
                continue
            renamed = blk[: m.start(1)].replace('"' + geom_name, '"' + name, 1) + blk[m.start(1):]
            units.append((renamed, col))

        head = f"    (symbol {quote(lib_id)}"
        if flags:
            head += " " + " ".join(flags)
        body = [reindent(props[k][0], props[k][1], 6) for k in order]
        body += [reindent(u, col, 6) for u, col in units]
        return "\n".join([head] + body + ["    )"])


def ser(node, _depth=0) -> str:
    """Serialise a parsed s-expression back to compact KiCad text."""
    if isinstance(node, str):
        # Bare atoms (yes/no/numbers/keywords) must not be quoted.
        if re.fullmatch(r"-?\d+(\.\d+)?(e-?\d+)?", node) or re.fullmatch(r"[A-Za-z_][\w.+-]*", node):
            return node
        return quote(node)
    head = node[0] if node else ""
    inner = " ".join(ser(x, _depth + 1) for x in node)
    if head in ("property", "pin", "symbol", "rectangle", "polyline", "circle", "arc", "text"):
        # keep these on one line; KiCad reformats on save anyway
        return "(" + inner + ")"
    return "(" + inner + ")"


def indent(text: str, spaces: int) -> str:
    pad = " " * spaces
    return "\n".join(pad + ln if ln.strip() else ln for ln in text.split("\n"))


def reindent(block: str, orig_col: int, target_col: int) -> str:
    """Move a raw text block from ``orig_col`` to ``target_col``, keeping shape."""
    shift = target_col - orig_col
    lines = block.split("\n")
    out = [" " * target_col + lines[0]]
    for ln in lines[1:]:
        if not ln.strip():
            out.append("")
        elif shift >= 0:
            out.append(" " * shift + ln)
        else:
            out.append(ln[min(-shift, len(ln) - len(ln.lstrip())):])
    return "\n".join(out)


# --------------------------------------------------------------------------
# Placed symbols and sheets
# --------------------------------------------------------------------------

STROKE = "(stroke (width 0) (type default))"
FONT = "(effects (font (size 1.27 1.27)))"


class Comp:
    """A symbol instance placed on a sheet."""

    def __init__(self, sheet, ref, lib_id, value, at, rot, unit, fields, dnp, in_bom,
                 field_at=None):
        self.sheet, self.ref, self.lib_id, self.value = sheet, ref, lib_id, value
        self.x, self.y, self.rot, self.unit = at[0], at[1], rot % 360, unit
        self.fields, self.dnp, self.in_bom = fields, dnp, in_bom
        # Library field positions can collide with a dense pin fan-out; this
        # overrides them in library (Y-up) coordinates.
        self.field_at = dict(field_at or {})
        self.body, self.pins, self.props = sheet.lib.get(lib_id)
        self.uuid = uuid_for(sheet.name, "sym", ref, unit)

    # -- geometry ---------------------------------------------------------
    def pin(self, number):
        """Schematic-space electrical endpoint of ``number``."""
        px, py, _pa, _u = self._pin(number)
        dx, dy = lin(px, py, self.rot)
        return (snap(self.x + dx), snap(self.y + dy))

    def pin_dir(self, number):
        """Unit vector pointing away from the body along the pin."""
        _px, _py, pa, _u = self._pin(number)
        dx, dy = dir_vec(pa + 180, self.rot)
        return (round(dx), round(dy))

    def _pin(self, number):
        try:
            return self.pins[str(number)]
        except KeyError:
            raise KeyError(f"{self.ref} ({self.lib_id}) has no pin {number!r}; "
                           f"available: {sorted(self.pins)}") from None

    def pin_numbers(self):
        return sorted(self.pins, key=lambda p: (len(p), p))

    # -- emit -------------------------------------------------------------
    def render(self, project, root_uuid, sheet_path):
        geom = self.sheet.lib.fields(self.lib_id)

        def place_field(key, default_off, default_hide):
            gx, gy, ga, hidden = geom.get(key, (default_off[0], default_off[1], 0,
                                                default_hide))
            if key in self.field_at:
                gx, gy = self.field_at[key]
            dx, dy = lin(gx, gy, self.rot)
            return (snap(self.x + dx), snap(self.y + dy), (ga + self.rot) % 180, hidden)

        lines = [
            f"  (symbol (lib_id {quote(self.lib_id)}) (at {num(self.x)} {num(self.y)}"
            f" {self.rot}) (unit {self.unit})",
            f"    (in_bom {'yes' if self.in_bom else 'no'}) (on_board yes)"
            f" (dnp {'yes' if self.dnp else 'no'})",
            f"    (uuid {self.uuid})",
        ]
        shown = [("Reference", self.ref, (0, 5.08), False),
                 ("Value", self.value, (0, -5.08), False),
                 ("Footprint", self.fields.get("Footprint",
                                               self.props.get("Footprint", "")),
                  (0, 0), True),
                 ("Datasheet", self.fields.get("Datasheet",
                                               self.props.get("Datasheet", "~")),
                  (0, 0), True)]
        for key, val in self.fields.items():
            if key not in ("Footprint", "Datasheet"):
                shown.append((key, val, (0, 0), True))
        for key, val, default_off, default_hide in shown:
            fx, fy, fa, hidden = place_field(key, default_off, default_hide)
            eff = ("(effects (font (size 1.27 1.27)) hide)" if hidden
                   else "(effects (font (size 1.27 1.27)))")
            lines.append(
                f"    (property {quote(key)} {quote(val)} (at {num(fx)} {num(fy)} {fa}) {eff})"
            )
        for p in self.pin_numbers():
            lines.append(f"    (pin {quote(p)} (uuid {uuid_for(self.uuid, 'pin', p)}))")
        lines.append("    (instances")
        lines.append(f"      (project {quote(project)}")
        lines.append(
            f"        (path {quote(sheet_path)} (reference {quote(self.ref)}) (unit {self.unit}))"
        )
        lines.append("      )")
        lines.append("    )")
        lines.append("  )")
        return "\n".join(lines)


# Labels stay horizontal even on vertical stubs: rotated text collides with
# the reference and value fields of the part it hangs off.
LABEL_ANGLE = {(1, 0): 0, (-1, 0): 180, (0, -1): 0, (0, 1): 0}
LABEL_JUSTIFY = {0: "left", 90: "left", 180: "right", 270: "right"}


# Ground-style symbols draw *below* their pin; supply symbols draw above it, so
# the rotation that makes a symbol point along a stub differs between the two.
GND_LIKE = re.compile(r"^(GND|Earth|VSS|-)")


def power_rot(kind: str, direction) -> int:
    d = (round(direction[0]), round(direction[1]))
    if GND_LIKE.match(kind):
        return {(0, 1): 0, (1, 0): 90, (0, -1): 180, (-1, 0): 270}[d]
    return {(0, -1): 0, (-1, 0): 90, (0, 1): 180, (1, 0): 270}[d]


class Sheet:
    """One ``.kicad_sch`` file."""

    def __init__(self, name, lib, project, title="", paper="A3", page="1",
                 root_uuid=None, comment=""):
        self.name, self.lib, self.project = name, lib, project
        self.title, self.paper, self.page, self.comment = title, paper, page, comment
        self.uuid = uuid_for("sheetfile", name)
        self.root_uuid = root_uuid or self.uuid
        self.path = "/" if name == "root" else f"/{uuid_for('sheetobj', name)}"
        self.comps, self.wires, self.juncs, self.labels = [], [], [], []
        self.hlabels, self.glabels, self.ncs, self.sheets, self.texts = [], [], [], [], []
        self._lib_ids = []
        # Power symbols that live in a project library rather than "power".
        self.custom_power = {}

    # -- placement --------------------------------------------------------
    def place(self, ref, lib_id, value=None, at=(0, 0), rot=0, unit=1,
              footprint=None, fields=None, dnp=False, in_bom=True, field_at=None):
        f = dict(fields or {})
        if footprint is not None:
            f["Footprint"] = footprint
        c = Comp(self, ref, lib_id, value if value is not None else ref,
                 at, rot, unit, f, dnp, in_bom, field_at)
        self.comps.append(c)
        if lib_id not in self._lib_ids:
            self._lib_ids.append(lib_id)
        return c

    def power(self, kind, at, rot=0, tag=None):
        """Place a power symbol; its single pin is the connection point."""
        self._pwr_count = getattr(self, "_pwr_count", 0) + 1
        ref = f"#PWR{self.page}{self._pwr_count:02d}"
        lib_id = self.custom_power.get(kind, f"power:{kind}")
        return self.place(ref, lib_id, kind, at=at, rot=rot,
                          footprint="", in_bom=False)

    # -- connectivity -----------------------------------------------------
    def wire(self, p1, p2):
        p1, p2 = (snap(p1[0]), snap(p1[1])), (snap(p2[0]), snap(p2[1]))
        if p1 == p2:
            return p2
        if p1[0] != p2[0] and p1[1] != p2[1]:
            raise ValueError(f"{self.name}: diagonal wire {p1}->{p2}")
        self.wires.append((p1, p2))
        return p2

    def bus_wire(self, p1, p2, via_x=None, via_y=None):
        """Two-segment orthogonal route between arbitrary points."""
        if via_x is not None:
            self.wire(p1, (via_x, p1[1]))
            self.wire((via_x, p1[1]), (via_x, p2[1]))
            return self.wire((via_x, p2[1]), p2)
        via_y = p1[1] if via_y is None else via_y
        self.wire(p1, (p1[0], via_y))
        self.wire((p1[0], via_y), (p2[0], via_y))
        return self.wire((p2[0], via_y), p2)

    def junction(self, p):
        self.juncs.append((snap(p[0]), snap(p[1])))

    def nc(self, p):
        self.ncs.append((snap(p[0]), snap(p[1])))

    def label(self, name, at, angle=0):
        self.labels.append((name, snap(at[0]), snap(at[1]), angle))

    def hlabel(self, name, at, shape="passive", angle=0):
        self.hlabels.append((name, shape, snap(at[0]), snap(at[1]), angle))

    def text(self, body, at, size=1.27):
        self.texts.append((body, snap(at[0]), snap(at[1]), size))

    # -- high level helpers ----------------------------------------------
    def stub(self, comp, pin, length=2.54):
        """Draw a stub outward from ``pin`` and return its free end."""
        p = comp.pin(pin)
        dx, dy = comp.pin_dir(pin)
        end = (snap(p[0] + dx * length), snap(p[1] + dy * length))
        self.wire(p, end)
        return end, (dx, dy)

    def net(self, comp, pin, name, length=2.54, kind="label", shape="passive"):
        """Stub a pin outward and terminate it with a label."""
        end, (dx, dy) = self.stub(comp, pin, length)
        ang = LABEL_ANGLE[(dx, dy)]
        if kind == "label":
            self.label(name, end, ang)
        elif kind == "hier":
            self.hlabel(name, end, shape, ang)
        else:
            raise ValueError(kind)
        return end

    def to_power(self, comp, pin, kind, length=2.54):
        """Stub a pin outward and cap it with a power symbol."""
        end, d = self.stub(comp, pin, length)
        self.power(kind, end, power_rot(kind, d))
        return end

    def power_at(self, kind, at, direction=(0, -1)):
        """Drop a power symbol whose pin sits exactly on ``at``."""
        return self.power(kind, (snap(at[0]), snap(at[1])), power_rot(kind, direction))


class SheetRef:
    """A hierarchical sheet symbol placed on a parent sheet."""

    def __init__(self, parent, child, at, size, page):
        self.parent, self.child = parent, child
        self.x, self.y, self.w, self.h, self.page = at[0], at[1], size[0], size[1], page
        self.uuid = uuid_for("sheetobj", child.name)
        self.pins = []          # (name, shape, x, y, angle)

    def pin(self, name, shape, side, offset):
        """Add a pin ``offset`` mm down the left/right edge; returns its point."""
        if side == "left":
            x, ang = self.x, 180
        elif side == "right":
            x, ang = self.x + self.w, 0
        else:
            raise ValueError(side)
        y = snap(self.y + offset)
        self.pins.append((name, shape, snap(x), y, ang))
        return (snap(x), y)

    def render(self, project, root_path):
        e_name = "(effects (font (size 1.27 1.27)) (justify left bottom))"
        e_file = "(effects (font (size 1.27 1.27)) (justify left top))"
        out = [
            f"  (sheet (at {num(self.x)} {num(self.y)}) (size {num(self.w)} {num(self.h)})"
            " (fields_autoplaced)",
            "    (stroke (width 0.1524) (type solid))",
            "    (fill (color 0 0 0 0.0000))",
            f"    (uuid {self.uuid})",
            f"    (property \"Sheetname\" {quote(self.child.name)} "
            f"(at {num(self.x)} {num(self.y - 0.7116)} 0) {e_name})",
            f"    (property \"Sheetfile\" {quote(self.child.name + '.kicad_sch')} "
            f"(at {num(self.x)} {num(self.y + self.h + 0.5846)} 0) {e_file})",
        ]
        for name, shape, px, py, ang in self.pins:
            just = "right" if ang == 0 else "left"
            out.append(
                f"    (pin {quote(name)} {shape} (at {num(px)} {num(py)} {ang})"
                f" (effects (font (size 1.27 1.27)) (justify {just}))"
                f" (uuid {uuid_for(self.uuid, 'pin', name)}))"
            )
        out += [
            "    (instances",
            f"      (project {quote(project)}",
            f"        (path {quote(root_path)} (page {quote(str(self.page))}))",
            "      )",
            "    )",
            "  )",
        ]
        return "\n".join(out)


def add_sheet_ref(parent, child, at, size, page):
    ref = SheetRef(parent, child, at, size, page)
    parent.sheets.append(ref)
    return ref


def render_sheet(sheet, title_block):
    """Serialise a Sheet to complete ``.kicad_sch`` text."""
    out = ["(kicad_sch (version 20230121) (generator eeschema)", ""]
    out.append(f"  (uuid {sheet.uuid})")
    out.append("")
    out.append(f"  (paper {quote(sheet.paper)})")
    out.append("")
    out.append(title_block(sheet))
    out.append("")
    out.append("  (lib_symbols")
    for lib_id in sheet._lib_ids:
        body, _pins, _props = sheet.lib.get(lib_id)
        out.append(body)
    out.append("  )")
    out.append("")

    for (x, y) in sheet.juncs:
        out.append(f"  (junction (at {num(x)} {num(y)}) (diameter 0) (color 0 0 0 0)")
        out.append(f"    (uuid {uuid_for(sheet.name, 'j', x, y)})")
        out.append("  )")
    for (p1, p2) in sheet.wires:
        out.append(f"  (wire (pts (xy {num(p1[0])} {num(p1[1])}) (xy {num(p2[0])} {num(p2[1])}))")
        out.append(f"    {STROKE}")
        out.append(f"    (uuid {uuid_for(sheet.name, 'w', p1, p2)})")
        out.append("  )")
    for (x, y) in sheet.ncs:
        out.append(f"  (no_connect (at {num(x)} {num(y)}) (uuid {uuid_for(sheet.name,'nc',x,y)}))")
    for (body, x, y, size) in sheet.texts:
        out.append(f"  (text {quote(body)} (at {num(x)} {num(y)} 0)")
        out.append(f"    (effects (font (size {num(size)} {num(size)})) (justify left bottom))")
        out.append(f"    (uuid {uuid_for(sheet.name,'t',x,y,body)})")
        out.append("  )")
    for (name, x, y, ang) in sheet.labels:
        just = LABEL_JUSTIFY[ang]
        out.append(f"  (label {quote(name)} (at {num(x)} {num(y)} {ang}) (fields_autoplaced)")
        out.append(f"    (effects (font (size 1.27 1.27)) (justify {just} bottom))")
        out.append(f"    (uuid {uuid_for(sheet.name,'l',name,x,y)})")
        out.append("  )")
    for (name, shape, x, y, ang) in sheet.hlabels:
        just = LABEL_JUSTIFY[ang]
        out.append(f"  (hierarchical_label {quote(name)} (shape {shape}) "
                   f"(at {num(x)} {num(y)} {ang}) (fields_autoplaced)")
        out.append(f"    (effects (font (size 1.27 1.27)) (justify {just}))")
        out.append(f"    (uuid {uuid_for(sheet.name,'h',name,x,y)})")
        out.append("  )")

    for ref in sheet.sheets:
        out.append(ref.render(sheet.project, "/" + sheet.uuid))
    for c in sheet.comps:
        out.append(c.render(sheet.project, sheet.root_uuid, sheet.path
                            if sheet.path != "/" else "/" + sheet.uuid))

    out.append("")
    if sheet.sheets:
        out.append("  (sheet_instances")
        out.append(f"    (path \"/\" (page {quote(str(sheet.page))}))")
        out.append("  )")
    else:
        out.append("  (sheet_instances")
        out.append(f"    (path \"/\" (page {quote(str(sheet.page))}))")
        out.append("  )")
    out.append(")")
    return "\n".join(out) + "\n"


# --------------------------------------------------------------------------
# Generating a symbol that the stock libraries do not carry
# --------------------------------------------------------------------------

PITCH = 2.54


def make_ic_symbol(name, pins, footprint="", datasheet="", description="",
                   keywords="", fp_filters="", body_half_width=17.78):
    """Build a rectangular IC symbol in KiCad 7 syntax.

    ``pins`` maps a side ("left"/"right"/"top"/"bottom") to a list of
    ``(number, pin_name, electrical_type)`` tuples or ``None`` for a spacer.
    Pins are laid out on a 2.54 mm pitch, centred on each side.
    """
    lens = {s: len(pins.get(s, [])) for s in ("left", "right", "top", "bottom")}
    rows = max(lens["left"], lens["right"])
    half_h = max((rows - 1) * PITCH / 2 + PITCH, 7.62)
    half_w = body_half_width
    plen = PITCH

    def span(count):
        return [(count - 1 - 2 * i) * PITCH / 2 for i in range(count)]

    drawn = []
    for side in ("left", "right"):
        ys = span(lens[side])
        for entry, y in zip(pins.get(side, []), ys):
            if entry is None:
                continue
            numb, pname, etype = entry
            if side == "left":
                drawn.append((numb, pname, etype, -half_w - plen, y, 0))
            else:
                drawn.append((numb, pname, etype, half_w + plen, y, 180))
    for side in ("top", "bottom"):
        xs = span(lens[side])
        for entry, x in zip(pins.get(side, []), xs):
            if entry is None:
                continue
            numb, pname, etype = entry
            if side == "top":
                drawn.append((numb, pname, etype, -x, half_h + plen, 270))
            else:
                drawn.append((numb, pname, etype, -x, -half_h - plen, 90))

    f = "(effects (font (size 1.27 1.27)))"
    fh = "(effects (font (size 1.27 1.27)) hide)"
    out = [f'  (symbol {quote(name)} (in_bom yes) (on_board yes)']
    out.append(f'    (property "Reference" "U" (at {num(-half_w)} {num(half_h + 3.81)} 0)')
    out.append(f'      (effects (font (size 1.27 1.27)) (justify left bottom))')
    out.append("    )")
    out.append(f'    (property "Value" {quote(name)} (at {num(-half_w)} {num(half_h + 1.27)} 0)')
    out.append(f'      (effects (font (size 1.27 1.27)) (justify left bottom))')
    out.append("    )")
    for key, val in (("Footprint", footprint), ("Datasheet", datasheet),
                     ("ki_description", description), ("ki_keywords", keywords),
                     ("ki_fp_filters", fp_filters)):
        out.append(f'    (property {quote(key)} {quote(val)} (at 0 {num(-half_h - 5.08)} 0)')
        out.append(f"      {fh}")
        out.append("    )")
    base = name.split(":")[-1]
    out.append(f'    (symbol "{base}_0_1"')
    out.append(f"      (rectangle (start {num(-half_w)} {num(half_h)})"
               f" (end {num(half_w)} {num(-half_h)})")
    out.append("        (stroke (width 0.254) (type default))")
    out.append("        (fill (type background))")
    out.append("      )")
    out.append("    )")
    out.append(f'    (symbol "{base}_1_1"')
    for numb, pname, etype, x, y, ang in drawn:
        out.append(f"      (pin {etype} line (at {num(x)} {num(y)} {ang}) (length {num(plen)})")
        out.append(f"        (name {quote(pname)} {f})")
        out.append(f"        (number {quote(numb)} {f})")
        out.append("      )")
    out.append("    )")
    out.append("  )")
    return "\n".join(out)


def write_symbol_lib(path, symbols):
    body = "\n".join(symbols)
    text = ("(kicad_symbol_lib (version 20220914) (generator kicad_symbol_editor)\n"
            + body + "\n)\n")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return text
