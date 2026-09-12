"""Perf-board layout engine: parts on a 2.54 mm hole grid, nets, wires, images.

Coordinates
-----------
* Hole coordinates ``(col, row)`` are 1-based integers on the 2.54 mm grid,
  column 1 at the left edge, row 1 at the top edge, as seen from the
  component (top) side.  Everything that touches the board is placed on holes.
* Footprints define their pins as hole offsets from the part origin; pins may
  be off-grid (``float`` offsets) when they are pads on a module's own PCB
  (screw terminals, power pads).  Off-grid pins are drawn but never counted as
  perf-board holes; they are connected with ``Design.fly`` (a hookup wire
  soldered to the pad).
* Rotation is in 90 degree steps, clockwise as seen from the top.

Wires
-----
Nets are declared as lists of ``(ref, pin)``.  A net is either chained into
point-to-point wires (nearest neighbour from the first member, or an explicit
``chain``) or tapped onto a straight bare-wire *bus bar*.  Every wire is a
Manhattan path that leaves its pad by half a hole into the channel between
holes, runs along a column channel, turns into a row channel next to the
destination row and enters the destination pad.  Wires that would share a
channel are put into neighbouring lanes (a staircase) so that a bundle stays
readable and never crosses another pad in a way that could be mistaken for a
joint.  All routed wires live on the solder side; the "bottom" view is the
mirror image you look at while soldering.
"""

from __future__ import annotations

import csv
import math
import os
from collections import OrderedDict, defaultdict

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Circle, Polygon, Rectangle  # noqa: E402

PITCH = 2.54

# --------------------------------------------------------------------------
# Net classes: colour, line width, wire type, legend text
# --------------------------------------------------------------------------

NET_CLASSES = OrderedDict([
    ("GND",   ("#111111", 3.0, "hookup 22 AWG solid, black",  "GND (hookup wire / bare bus)")),
    ("VM",    ("#d62728", 3.0, "hookup 22 AWG solid, red",    "VM motor supply (hookup wire)")),
    ("5V",    ("#ff7f0e", 3.0, "hookup 22 AWG solid, orange", "+5 V (hookup wire)")),
    ("3V3",   ("#c8a200", 2.4, "hookup 22 AWG solid, yellow", "+3.3 V (hookup wire)")),
    ("PHASE", ("#8c564b", 3.0, "hookup 22 AWG solid, brown",  "motor phase (hookup wire)")),
    ("PWM",   ("#2ca02c", 1.3, "wire-wrap 30 AWG, green",     "PWM (wire-wrap)")),
    ("CTRL",  ("#9467bd", 1.3, "wire-wrap 30 AWG, violet",    "enable / fault / reset (wire-wrap)")),
    ("I2C",   ("#1f77b4", 1.3, "wire-wrap 30 AWG, blue",      "I2C encoder (wire-wrap)")),
    ("SENSE", ("#17becf", 1.3, "wire-wrap 30 AWG, cyan",      "analog sense (wire-wrap)")),
    ("CAN",   ("#e377c2", 1.3, "wire-wrap 30 AWG, pink",      "CAN (wire-wrap)")),
    ("DBG",   ("#7f7f7f", 1.3, "wire-wrap 30 AWG, grey",      "debug / boot / LED (wire-wrap)")),
])
POWER_CLASSES = {"GND", "VM", "5V", "3V3", "PHASE"}

PART_COLOURS = {
    "module": "#d7e6f5",
    "ic": "#e6dcf3",
    "passive": "#f0f0f0",
    "connector": "#dcefd6",
    "regulator": "#fbe0c3",
    "protection": "#f9dede",
    "switch": "#f5efc4",
}


def mm(hole):
    """Hole coordinate (col,row) -> mm (x,y), y down."""
    return ((hole[0] - 1) * PITCH, (hole[1] - 1) * PITCH)


def rot_vec(dx, dy, rot):
    rot %= 360
    if rot == 0:
        return dx, dy
    if rot == 90:
        return -dy, dx
    if rot == 180:
        return -dx, -dy
    if rot == 270:
        return dy, -dx
    raise ValueError(rot)


# --------------------------------------------------------------------------
# Footprints
# --------------------------------------------------------------------------


class Footprint:
    """Pins as hole offsets; graphics in mm relative to the origin hole."""

    def __init__(self, name, pins, outline, cls="passive", body=None, label_at=(0, -3.0),
                 pin_labels=True, pin1_square=True, display=None, label_rot=False,
                 pin_label_vertical=False):
        self.name = name
        self.label_rot = label_rot             # rotate the ref label with the part (axial parts)
        self.pin_label_vertical = pin_label_vertical   # labels above/below a pin row stand upright
        self.pins = OrderedDict(pins)          # name -> (dcol, drow), floats allowed
        self.outline = outline                 # ('rect'|'circle'|'line'|'text'|'notch'|'band', ...)
        self.cls = cls
        self.body = body                       # (x0, y0, x1, y1) mm for collision / fill
        self.label_at = label_at
        self.pin_labels = pin_labels
        self.pin1_square = pin1_square
        self.display = display or {}           # pin name -> label drawn on the picture

    def on_grid(self, pin):
        dc, dr = self.pins[pin]
        return abs(dc - round(dc)) < 1e-6 and abs(dr - round(dr)) < 1e-6

    def label(self, pin):
        return self.display.get(pin, pin)


def fp_dip(name, n, rows_apart=3, names=None, cls="ic"):
    """DIP-N, pin 1 top-left, pins run down the left column then up the right."""
    per = n // 2
    pins = []
    for i in range(per):
        pins.append((str(i + 1), (0, i)))
    for i in range(per):
        pins.append((str(per + i + 1), (rows_apart, per - 1 - i)))
    display = {}
    if names:                                   # rename pins; falsy entries keep their number
        pins = [((names[int(p) - 1] or p), off) for p, off in pins]
    w = rows_apart * PITCH
    h = (per - 1) * PITCH
    body = (-1.1, -PITCH * 0.6, w + 1.1, h + PITCH * 0.6)
    outline = [("rect", *body), ("notch", w / 2, body[1])]
    return Footprint(name, pins, outline, cls, body, label_at=(w / 2, body[1] - 1.3),
                     display=display)


def fp_header(name, n, rows=1, names=None, cls="connector", vertical=False):
    """Pin header / socket.  Horizontal: pins run to the right; vertical: down."""
    pins = []
    for r in range(rows):
        for i in range(n):
            nm = names[r * n + i] if names else str(r * n + i + 1)
            pins.append((nm, (r, i) if vertical else (i, r)))
    if vertical:
        body = (-PITCH / 2, -PITCH / 2, (rows - 1) * PITCH + PITCH / 2, (n - 1) * PITCH + PITCH / 2)
        label_at = (body[2] + 1.0, (n - 1) * PITCH / 2)
    else:
        body = (-PITCH / 2, -PITCH / 2, (n - 1) * PITCH + PITCH / 2, (rows - 1) * PITCH + PITCH / 2)
        label_at = ((body[0] + body[2]) / 2, body[1] - 1.1)
    return Footprint(name, pins, [("rect", *body)], cls, body, label_at=label_at)


def fp_axial(name, span, cls="passive", body_len=None):
    """Two-lead axial part with ``span`` holes between the leads (pin 1 left)."""
    L = body_len or max(2.0, span * PITCH - 3.4)
    x0 = (span * PITCH - L) / 2
    body = (x0, -1.3, x0 + L, 1.3)
    outline = [("line", 0, 0, x0, 0), ("line", x0 + L, 0, span * PITCH, 0), ("rect", *body)]
    return Footprint(name, [("1", (0, 0)), ("2", (span, 0))], outline, cls, body,
                     label_at=(span * PITCH / 2, -2.5), pin_labels=False, pin1_square=False,
                     label_rot=True)


def fp_diode(name, span, cls="protection", body_len=None):
    """Axial diode, cathode (band) at pin K = left hole."""
    fp = fp_axial(name, span, cls, body_len)
    L = fp.body[2] - fp.body[0]
    fp.outline.append(("band", fp.body[0] + L * 0.12, -1.3, fp.body[0] + L * 0.24, 1.3))
    fp.pin_labels = True
    fp.pins = OrderedDict([("K", (0, 0)), ("A", (span, 0))])
    return fp


def fp_radial(name, span=1, dia=5.0, cls="passive", polarized=False):
    """Radial capacitor / PTC; pin 1 (or +) at the origin, pin 2 ``span`` holes right."""
    cx = span * PITCH / 2
    outline = [("circle", cx, 0, dia / 2)]
    if polarized:
        outline.append(("text", cx - dia / 2 - 1.5, -0.3, "+", 2.4))
    body = (cx - dia / 2, -dia / 2, cx + dia / 2, dia / 2)
    pins = [("+", (0, 0)), ("-", (span, 0))] if polarized else [("1", (0, 0)), ("2", (span, 0))]
    return Footprint(name, pins, outline, cls, body, label_at=(cx, -dia / 2 - 1.3),
                     pin_labels=polarized, pin1_square=False, label_rot=True)


def fp_ceramic(name, span=1, cls="passive"):
    w = span * PITCH
    body = (-1.2, -1.6, w + 1.2, 1.6)
    return Footprint(name, [("1", (0, 0)), ("2", (span, 0))], [("rect", *body)], cls, body,
                     label_at=(w / 2, -2.8), pin_labels=False, pin1_square=False, label_rot=True)


def fp_to220(name, names=("1", "2", "3"), cls="regulator", heatsink=True):
    """TO-220 standing upright, pins left->right, tab (and heatsink) behind (towards -y)."""
    pins = [(names[0], (0, 0)), (names[1], (1, 0)), (names[2], (2, 0))]
    body = (-2.3, -PITCH * 0.6, 2 * PITCH + 2.3, PITCH * 0.6)
    outline = [("rect", *body)]
    label_at = (PITCH, -PITCH * 1.4)
    if heatsink:
        hs = (-3.4, -PITCH * 3.4, 2 * PITCH + 3.4, -PITCH * 0.6)
        outline.append(("rect", *hs))
        outline.append(("text", PITCH, -PITCH * 2.6, "+ heatsink", 1.3))
        body = (hs[0], hs[1], hs[2], body[3])
        label_at = (PITCH, -PITCH * 1.6)
    return Footprint(name, pins, outline, cls, body, label_at=label_at)


def fp_led(name, cls="passive"):
    body = (-1.7, -1.7, PITCH + 1.7, 1.7)
    return Footprint(name, [("K", (0, 0)), ("A", (1, 0))],
                     [("circle", PITCH / 2, 0, 1.7), ("text", PITCH / 2, 0.15, "LED", 1.2)],
                     cls, body, label_at=(PITCH / 2, -2.8), pin1_square=False)


def fp_terminal(name, n, cls="connector", names=None):
    """Screw terminal, 5.08 mm pitch (two holes per position), wire entry towards -y."""
    pins = [(names[i] if names else str(i + 1), (2 * i, 0)) for i in range(n)]
    w = (n - 1) * 2 * PITCH
    body = (-PITCH, -4.2, w + PITCH, 3.4)
    outline = [("rect", *body)] + [("circle", 2 * i * PITCH, -1.0, 1.5) for i in range(n)]
    return Footprint(name, pins, outline, cls, body, label_at=(w / 2, body[3] + 1.3))


def fp_dip_switch4(name):
    """4-position DIP switch in a DIP-8 footprint: pins 1-4 down the left, the
    matching commons 1b-4b opposite them on the right."""
    fp = fp_dip(name, 8, rows_apart=3, names=["1", "2", "3", "4", "4b", "3b", "2b", "1b"],
                cls="switch")
    fp.outline.append(("text", 1.5 * PITCH, 1.5 * PITCH, "ADDR", 1.6))
    return fp


def fp_tactile(name):
    """6x6 mm tactile switch pushed into a 3x2 hole pattern (legs bend 0.6 mm).
    A1/A2 are joined internally, so are B1/B2; pressing joins A to B."""
    pins = [("A1", (0, 0)), ("A2", (3, 0)), ("B1", (0, 2)), ("B2", (3, 2))]
    body = (-1.0, -0.8, 3 * PITCH + 1.0, 2 * PITCH + 0.8)
    outline = [("rect", *body), ("circle", 1.5 * PITCH, PITCH, 1.8)]
    return Footprint(name, pins, outline, "switch", body, label_at=(1.5 * PITCH, body[1] - 1.2),
                     pin1_square=False)


def fp_crystal(name):
    """HC-49S crystal lying flat (11.5 x 4.7 mm), leads bent to 2.54 mm."""
    body = (-4.5, -1.9, PITCH + 4.5, 1.9)
    return Footprint(name, [("1", (0, 0)), ("2", (1, 0))],
                     [("rect", *body), ("text", PITCH / 2, 0.15, "XTAL", 1.2)],
                     "passive", body, label_at=(PITCH / 2, -3.2), pin_labels=False,
                     pin1_square=False)


def fp_blackpill(name):
    """WeAct Black Pill V3.0 seen from above, USB-C on the left.

    Two rows of 20 pins, rows 6 holes apart (599 mil), board 52.38 x 20.78 mm.
    Origin = top-left pin (5V).  Mount on two 1x20 female header strips.
    """
    top = ["5V", "G", "3V3", "B10", "B2", "B1", "B0", "A7", "A6", "A5",
           "A4", "A3", "A2", "A1", "A0", "R", "C15", "C14", "C13", "VB"]
    bot = ["B12", "B13", "B14", "B15", "A8", "A9", "A10", "A11", "A12", "A15",
           "B3", "B4", "B5", "B6", "B7", "B8", "B9", "5V", "G", "3V3"]
    pins, display = [], {}
    for i, nm in enumerate(top):
        key = "T_" + nm if nm in ("5V", "G", "3V3") else nm
        pins.append((key, (i, 0)))
        display[key] = nm
    for i, nm in enumerate(bot):
        key = "B_" + nm if nm in ("5V", "G", "3V3") else nm
        pins.append((key, (i, 6)))
        display[key] = nm
    x0, x1 = -2.06, 48.26 + 2.06                # 52.38 long, pins span 48.26
    y0, y1 = -(20.78 - 15.24) / 2, 15.24 + (20.78 - 15.24) / 2
    body = (x0, y0, x1, y1)
    outline = [
        ("rect", *body),
        ("rect", x0 - 1.5, 3.6, x0 + 6.5, 11.6),           # USB-C plug shadow
        ("text", x0 + 2.5, 7.6, "USB-C", 1.4, 90),
        ("rect", 19.0, 3.6, 27.0, 11.6),                    # MCU
        ("text", 23.0, 7.6, "F401", 1.6),
        ("rect", 7.0, 2.8, 10.6, 5.6), ("text", 8.8, 1.7, "NRST", 1.2),
        ("rect", 7.0, 9.8, 10.6, 12.6), ("text", 8.8, 13.9, "BOOT0", 1.2),
        ("rect", 38.0, 6.0, 41.6, 9.2), ("text", 39.8, 5.0, "KEY", 1.2),
        ("rect", x1 - 4.4, 2.6, x1 - 1.4, 12.6),            # SWD header at the right end
        ("text", x1 - 2.9, 7.6, "SWD", 1.2, 90),
        ("text", 24.0, 13.0, "WeAct Black Pill V3.0  (STM32F401CCU6)", 1.6),
    ]
    return Footprint(name, pins, outline, "module", body, label_at=(24.0, y0 - 1.5),
                     pin1_square=False, display=display)


def fp_sfmini(name, version="v1.1", flip=False):
    """SimpleFOC Mini (DRV8313) seen from above, component side up, male pins
    soldered downwards into the perf board (or into 1x6/1x5/1x3 sockets).

    Origin = the IN1 pin of the upper control row.  Pin positions come from the
    module's pick-and-place / silkscreen data: the lower row is one hole below
    the upper row, the motor header 6.95 holes below (0.13 mm off-grid on v1.1,
    ~1 mm sideways on v1.0 -> bend the pins slightly).  The 5.0 mm power
    terminal (VIN-/VIN+) is on the module's own PCB, off the perf grid.

    ``flip=True`` mirrors the pin order for a module that was delivered with
    female headers and therefore has to be plugged in upside-down.
    """
    if version == "v1.1":
        upper = [("IN1", 0), ("IN2", 1), ("IN3", 2), ("EN", 3), ("GND", 4), ("GND2", 5)]
    else:
        upper = [("EN", 0), ("IN3", 1), ("IN2", 2), ("IN1", 3), ("GND", 4)]
    lower = [("nFT", 0), ("nSP", 1), ("nRT", 2), ("GNDb", 3), ("3V3", 4)]
    pins = [(n, (x, 0)) for n, x in upper] + [(n, (x, 1)) for n, x in lower]
    pins += [("M1", (1, 7)), ("M2", (2, 7)), ("M3", (3, 7))]
    pins += [("VIN-", (6.9, 1.55)), ("VIN+", (6.9, 3.5))]
    left, right, top, bottom = -3.56, 19.45, -1.91, 19.05
    if flip:
        pins = [(n, (-x, y)) for n, (x, y) in pins]
        left, right = -right, -left
    body = (left, top, right, bottom)
    px = (left + right) / 2
    tx = left + 21.6 if not flip else left + 1.4
    outline = [
        ("rect", *body),
        ("text", px, 9.6, f"SimpleFOC Mini {version}", 1.5),
        ("text", px, 7.0, "DRV8313  8-24 V  2.5 A", 1.3),
        ("text", px, 11.9, "(upside-down)" if flip else "(component side up)", 1.2),
        ("text", tx, 0.0, "-", 2.2), ("text", tx, 12.4, "+", 2.2),
        ("text", tx, 6.2, "VIN", 1.2, 90),
        ("text", px + (2.0 if flip else -2.0), 15.2, "M1  M2  M3", 1.2),
    ]
    return Footprint(name, pins, outline, "module", body, label_at=(px, top - 1.5),
                     pin1_square=False, display={"GND2": "GND", "GNDb": "GND"})


def fp_acs712(name):
    """ACS712 breakout lying flat: its 1x3 header (VCC OUT GND) plugs into a
    female socket on the perf board, the 5.08 mm screw terminal (IP+ / IP-) is
    at the far end of the 31 x 13 mm module, 24 mm away from the header."""
    pins = [("VCC", (0, 0)), ("OUT", (1, 0)), ("GND", (2, 0)),
            ("IP+", (0.0, 9.5)), ("IP-", (2.0, 9.5))]
    body = (PITCH - 6.5, -1.8, PITCH + 6.5, 29.2)
    outline = [("rect", *body),
               ("rect", PITCH - 6.5, 19.6, PITCH + 6.5, 29.2),
               ("text", PITCH, 12.0, "ACS712-05B", 1.4),
               ("text", PITCH, 15.0, "(module, flat)", 1.2),
               ("text", PITCH, 18.0, "hall current sensor", 1.1)]
    return Footprint(name, pins, outline, "module", body, label_at=(PITCH, 7.0),
                     pin1_square=False)


def fp_point(name):
    """A single hole used as a solder joint: a hookup wire comes up through it
    to reach a module pad or screw terminal on the top side."""
    return Footprint(name, [("1", (0, 0))], [("circle", 0, 0, 1.15)], "connector", None,
                     label_at=(0, -2.1), pin_labels=False, pin1_square=False)


def fp_qfp48_adapter(name, pitch_rows=13, names=None):
    """LQFP48 (0.5 mm) to DIP adapter: 12 header pins per side, pins numbered
    anticlockwise like the chip (1-12 down the left side, 13-24 along the
    bottom, 25-36 up the right side, 37-48 along the top).  Opposite pin rows
    are ``pitch_rows`` holes apart (13 = 33 mm square adapter); the corner
    holes are empty."""
    n = pitch_rows
    pins = []
    for i in range(12):
        pins.append((str(i + 1), (0, i + 1)))                 # left, top -> bottom
    for i in range(12):
        pins.append((str(13 + i), (i + 1, n)))                # bottom, left -> right
    for i in range(12):
        pins.append((str(25 + i), (n, n - 1 - i)))            # right, bottom -> top
    for i in range(12):
        pins.append((str(37 + i), (n - 1 - i, 0)))            # top, right -> left
    w = n * PITCH
    body = (-PITCH * 0.3, -PITCH * 0.3, w + PITCH * 0.3, w + PITCH * 0.3)
    outline = [("rect", *body),
               ("rect", w / 2 - 4.5, w / 2 - 4.5, w / 2 + 4.5, w / 2 + 4.5),
               ("text", w / 2, w / 2 + 0.3, "STM32G431CBT6", 1.4),
               ("text", w / 2, w / 2 - 7.0, "LQFP48 -> DIP adapter", 1.3),
               ("text", w / 2, w / 2 + 7.0, "pin 1 = top-left, anticlockwise", 1.1),
               ("circle", PITCH * 0.5, PITCH * 0.5, 0.7)]
    return Footprint(name, pins, outline, "module", body, label_at=(w / 2, body[1] - 1.5),
                     pin1_square=False, display=dict(names or {}), pin_label_vertical=True)


# --------------------------------------------------------------------------
# Parts, nets, design
# --------------------------------------------------------------------------


class Part:
    def __init__(self, ref, fp, at, rot=0, value="", note="", cls=None, label_at=None):
        self.ref, self.fp, self.at, self.rot = ref, fp, (int(at[0]), int(at[1])), rot % 360
        self.value, self.note = value, note
        self.cls = cls or fp.cls
        self.label_at = label_at               # (dx, dy) mm from the origin, unrotated override

    def pin_hole(self, pin):
        dc, dr = self.fp.pins[pin]
        rc, rr = rot_vec(dc, dr, self.rot)
        c, r = self.at[0] + rc, self.at[1] + rr
        if abs(c - round(c)) > 1e-6 or abs(r - round(r)) > 1e-6:
            raise ValueError(f"{self.ref}.{pin} is off-grid ({c:.2f},{r:.2f}); use fly()")
        return (int(round(c)), int(round(r)))

    def pin_mm(self, pin):
        dc, dr = self.fp.pins[pin]
        rc, rr = rot_vec(dc, dr, self.rot)
        ox, oy = mm(self.at)
        return (ox + rc * PITCH, oy + rr * PITCH)

    def holes(self):
        return {self.pin_hole(p) for p in self.fp.pins if self.fp.on_grid(p)}

    def body_mm(self):
        """Axis-aligned body rectangle in absolute mm after rotation."""
        if not self.fp.body:
            return None
        x0, y0, x1, y1 = self.fp.body
        pts = [rot_vec(x, y, self.rot) for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))]
        ox, oy = mm(self.at)
        xs = [ox + p[0] for p in pts]
        ys = [oy + p[1] for p in pts]
        return (min(xs), min(ys), max(xs), max(ys))

    def body_center_mm(self):
        b = self.body_mm()
        if not b:
            return self.pin_mm(next(iter(self.fp.pins)))
        return ((b[0] + b[2]) / 2, (b[1] + b[3]) / 2)


class Wire:
    def __init__(self, net, cls, a, b, kind="wire"):
        self.net, self.cls, self.a, self.b, self.kind = net, cls, a, b, kind
        self.ha = self.hb = None       # holes
        self.path = None               # list of (x, y) in mm
        self.step = 0


class Design:
    def __init__(self, name, cols, rows, title="", subtitle=""):
        self.name, self.cols, self.rows = name, cols, rows
        self.title, self.subtitle = title, subtitle
        self.parts = OrderedDict()
        self.nets = OrderedDict()      # name -> dict(cls=, members=[(ref,pin)], bus=, chain=)
        self.notes = []
        self.wires = []
        self.buses = []                # (net, cls, (c0,r0), (c1,r1))
        self.bus_solder = []           # (net, (ref,pin), hole) pins sitting on the bus line
        self.flying = []               # (net, cls, (ref,pin), (ref,pin), text)

    # -- building -------------------------------------------------------
    def add(self, ref, fp, at, rot=0, value="", note="", cls=None, label_at=None):
        if ref in self.parts:
            raise ValueError(f"duplicate ref {ref}")
        p = Part(ref, fp, at, rot, value, note, cls, label_at)
        self.parts[ref] = p
        return p

    def net(self, name, cls, *members, bus=None, chain=None, taps=None):
        """Declare a net.  ``bus=[(c0,r0),(c1,r1),...]`` is a bare-wire bus bar
        (a polyline of straight runs) that every member is tapped onto at the
        nearest point (``taps={(ref,pin): (col,row)}`` overrides the tap hole);
        ``chain`` fixes the wire order of a point-to-point net."""
        if name in self.nets:
            n = self.nets[name]
            n["members"].extend(members)
            if bus:
                n["bus"] = bus
            if taps:
                n["taps"].update(taps)
            return
        self.nets[name] = dict(cls=cls, members=list(members), bus=bus, chain=chain,
                               taps=dict(taps or {}))

    def fly(self, net, cls, a, b, text=""):
        """A connection made off the grid (module pad / screw terminal)."""
        self.flying.append((net, cls, a, b, text))
        if net not in self.nets:
            self.nets[net] = dict(cls=cls, members=[], bus=None, chain=None, taps={})

    def note(self, text):
        self.notes.append(text)

    def pin(self, ref, pin):
        return self.parts[ref].pin_hole(pin)

    # -- wires ------------------------------------------------------------
    def derive_wires(self):
        self.wires, self.buses, self.bus_solder = [], [], []
        for name, n in self.nets.items():
            members = n["members"]
            if n["bus"]:
                pts = [tuple(p) for p in n["bus"]]
                for p0, p1 in zip(pts, pts[1:]):
                    self.buses.append((name, n["cls"], p0, p1))
                for ref, pin in members:
                    h = self.pin(ref, pin)
                    target = n["taps"].get((ref, pin))
                    if target and isinstance(target[0], str):      # wire to another member
                        w = Wire(name, n["cls"], (ref, pin), tuple(target))
                        w.ha, w.hb = h, self.pin(*target)
                        self.wires.append(w)
                        continue
                    tap = target or self._bus_tap(h, pts)
                    if h == tap:
                        self.bus_solder.append((name, (ref, pin), h))
                        continue
                    w = Wire(name, n["cls"], (ref, pin), ("BUS", name), "tap")
                    w.ha, w.hb = h, tap
                    self.wires.append(w)
                continue
            order = n["chain"] or self._chain(members)
            for a, b in zip(order, order[1:]):
                w = Wire(name, n["cls"], a, b)
                w.ha, w.hb = self.pin(*a), self.pin(*b)
                self.wires.append(w)
        classes = list(NET_CLASSES)
        self.wires.sort(key=lambda w: (classes.index(w.cls), w.net, w.ha[1], w.ha[0]))
        self._occupied = set()
        for p in self.parts.values():
            self._occupied |= p.holes()
        self._h_lanes = defaultdict(list)     # y (hole units) -> [(x0, x1)]
        self._v_lanes = defaultdict(list)     # x -> [(y0, y1)]
        self._overflow = defaultdict(int)
        for w in self.wires:
            w.path = self._route(w)
        for i, w in enumerate(self.wires):
            w.step = i + 1

    def _chain(self, members):
        pts = [(m, self.pin(*m)) for m in members]
        if not pts:
            return []
        order = [pts[0]]
        rest = pts[1:]
        while rest:
            last = order[-1][1]
            rest.sort(key=lambda mp: abs(mp[1][0] - last[0]) + abs(mp[1][1] - last[1]))
            order.append(rest.pop(0))
        return [m for m, _ in order]

    @staticmethod
    def _bus_tap(h, pts):
        """Nearest hole on the bus polyline (Manhattan distance)."""
        best = None
        for p0, p1 in zip(pts, pts[1:]):
            if p0[1] == p1[1]:                       # horizontal run
                c = min(max(h[0], min(p0[0], p1[0])), max(p0[0], p1[0]))
                t = (c, p0[1])
            else:
                r = min(max(h[1], min(p0[1], p1[1])), max(p0[1], p1[1]))
                t = (p0[0], r)
            d = abs(t[0] - h[0]) + abs(t[1] - h[1])
            if best is None or d < best[0]:
                best = (d, t)
        return best[1]

    # lane helpers -------------------------------------------------------
    def _col_clear(self, c, y0, y1):
        """No occupied hole strictly between y0 and y1 in column c."""
        lo, hi = min(y0, y1), max(y0, y1)
        r = math.floor(lo) + 1
        while r < hi - 1e-6:
            if (c, r) in self._occupied and abs(r - lo) > 1e-6 and abs(r - hi) > 1e-6:
                return False
            r += 1
        return True

    def _row_clear(self, r, x0, x1):
        lo, hi = min(x0, x1), max(x0, x1)
        c = math.floor(lo) + 1
        while c < hi - 1e-6:
            if (c, r) in self._occupied and abs(c - lo) > 1e-6 and abs(c - hi) > 1e-6:
                return False
            c += 1
        return True

    @staticmethod
    def _free(intervals, a, b, margin=0.25):
        lo, hi = min(a, b) - margin, max(a, b) + margin
        return all(hi < i0 or lo > i1 for i0, i1 in intervals)

    def _take_h(self, y, x0, x1):
        self._h_lanes[round(y, 3)].append((min(x0, x1), max(x0, x1)))

    def _take_v(self, x, y0, y1):
        self._v_lanes[round(x, 3)].append((min(y0, y1), max(y0, y1)))

    def _overflow_offset(self, key):
        n = self._overflow[key]
        self._overflow[key] += 1
        # 0.30 mm steps either side of the channel centre, in hole units
        return (0.30 / PITCH) * ((n + 2) // 2) * (1 if n % 2 else -1) if n else 0.0

    def _route(self, w):
        (c1, r1), (c2, r2) = w.ha, w.hb
        if (c1, r1) == (c2, r2):
            return [mm((c1, r1))]
        if abs(c2 - c1) + abs(r2 - r1) == 1:
            w.kind = "link" if w.kind == "wire" else w.kind
            return [mm((c1, r1)), mm((c2, r2))]
        sc = 1 if c2 > c1 else -1
        sr = 1 if r2 > r1 else -1
        pref = self._side_pref(w.a)

        if r1 == r2:
            # both pads on one row: drop into a row channel, run, come back up
            for side in (pref[1], -pref[1]):
                for k in range(0, 4):
                    y = r1 + side * (0.5 + k)
                    if not (0.5 <= y <= self.rows + 0.5):
                        continue
                    if not (self._col_clear(c1, r1, y) and self._col_clear(c2, r2, y)):
                        break
                    if self._free(self._h_lanes[round(y, 3)], c1, c2):
                        self._take_h(y, c1, c2)
                        return [mm(p) for p in ((c1, r1), (c1, y), (c2, y), (c2, r2))]
            y = r1 + pref[1] * 0.5 + self._overflow_offset(("h", round(r1 + pref[1] * 0.5, 3)))
            return [mm(p) for p in ((c1, r1), (c1, y), (c2, y), (c2, r2))]

        if c1 == c2:
            for side in (pref[0], -pref[0]):
                for k in range(0, 4):
                    x = c1 + side * (0.5 + k)
                    if not (0.5 <= x <= self.cols + 0.5):
                        continue
                    if not (self._row_clear(r1, c1, x) and self._row_clear(r2, c2, x)):
                        break
                    if self._free(self._v_lanes[round(x, 3)], r1, r2):
                        self._take_v(x, r1, r2)
                        return [mm(p) for p in ((c1, r1), (x, r1), (x, r2), (c2, r2))]
            x = c1 + pref[0] * 0.5 + self._overflow_offset(("v", round(c1 + pref[0] * 0.5, 3)))
            return [mm(p) for p in ((c1, r1), (x, r1), (x, r2), (c2, r2))]

        # general: leave the pad sideways into the column channel next to it,
        # run along that channel, turn into a row channel next to the
        # destination row (staircase lanes), enter the destination pad.
        best = None
        for kx in range(0, 3):
            x = c1 + sc * (0.5 + kx)
            if sc * (c2 - x) < 0.5 - 1e-6:
                break
            if not self._row_clear(r1, c1, x):
                break
            for ky in range(0, 5):
                y = r2 - sr * (0.5 + ky)
                if sr * (y - r1) < 0.5 - 1e-6:
                    break
                if not self._col_clear(c2, y, r2):
                    break
                if (self._free(self._h_lanes[round(y, 3)], x, c2) and
                        self._free(self._v_lanes[round(x, 3)], r1, y)):
                    best = (x, y)
                    break
            if best:
                break
        if best is None:
            x = c1 + sc * 0.5 + self._overflow_offset(("v", round(c1 + sc * 0.5, 3)))
            y = r2 - sr * 0.5 + self._overflow_offset(("h", round(r2 - sr * 0.5, 3)))
        else:
            x, y = best
            self._take_v(x, r1, y)
            self._take_h(y, x, c2)
        return [mm(p) for p in ((c1, r1), (x, r1), (x, y), (c2, y), (c2, r2))]

    def _side_pref(self, member):
        """(x side, y side) away from the part's body centre: +1 = right/below."""
        ref, pin = member
        if ref == "BUS":
            return (1, 1)
        p = self.parts[ref]
        px, py = p.pin_mm(pin)
        bx, by = p.body_center_mm()
        sx = 1 if px >= bx - 1e-6 else -1
        sy = 1 if py >= by - 1e-6 else -1
        return (sx, sy)

    # -- checks -----------------------------------------------------------
    def check(self):
        problems = []
        occupied = {}
        for p in self.parts.values():
            for h in p.holes():
                if not (1 <= h[0] <= self.cols and 1 <= h[1] <= self.rows):
                    problems.append(f"{p.ref}: hole {h} outside the {self.cols}x{self.rows} board")
                if h in occupied:
                    problems.append(f"hole {h} used by both {occupied[h]} and {p.ref}")
                occupied[h] = p.ref
            b = p.body_mm()
            if b and (b[0] < -PITCH or b[1] < -PITCH or
                      b[2] > self.cols * PITCH or b[3] > self.rows * PITCH):
                problems.append(f"{p.ref}: body {tuple(round(v, 1) for v in b)} leaves the board")
        bodies = [(p.ref, p.body_mm()) for p in self.parts.values() if p.body_mm()]
        for i in range(len(bodies)):
            for j in range(i + 1, len(bodies)):
                (ra, a), (rb, b) = bodies[i], bodies[j]
                if a[0] < b[2] - 0.3 and b[0] < a[2] - 0.3 and a[1] < b[3] - 0.3 and b[1] < a[3] - 0.3:
                    problems.append(f"bodies overlap: {ra} and {rb}")
        for name, cls, p0, p1 in self.buses:
            if p0[0] != p1[0] and p0[1] != p1[1]:
                problems.append(f"bus {name} run {p0}-{p1} is not straight")
            for (c, r) in self._bus_holes(p0, p1):
                if (c, r) in occupied and not any(h == (c, r) for _, _, h in self.bus_solder):
                    problems.append(f"bus {name} runs through hole {(c, r)} of {occupied[(c, r)]}")
        for w in self.wires:
            if w.kind == "tap" and w.hb in occupied:
                ref = occupied[w.hb]
                pins = [pn for pn in self.parts[ref].fp.pins
                        if self.parts[ref].fp.on_grid(pn) and self.parts[ref].pin_hole(pn) == w.hb]
                for pn in pins:
                    owner = next((nm for nm, n in self.nets.items() if (ref, pn) in n["members"]),
                                 None)
                    if owner != w.net:
                        problems.append(f"tap of {w.net} lands on {ref}.{pn} (net {owner}) at {w.hb}")
        # every pin in at most one net; members must exist
        pin_net = {}
        for name, n in self.nets.items():
            for m in n["members"]:
                if m[0] not in self.parts:
                    problems.append(f"net {name}: unknown part {m[0]}")
                    continue
                if m[1] not in self.parts[m[0]].fp.pins:
                    problems.append(f"net {name}: {m[0]} has no pin {m[1]}")
                    continue
                if m in pin_net and pin_net[m] != name:
                    problems.append(f"{m[0]}.{m[1]} is in nets {pin_net[m]} and {name}")
                pin_net[m] = name
        for net, cls, a, b, text in self.flying:
            for m in (a, b):
                if m[0] not in self.parts or m[1] not in self.parts[m[0]].fp.pins:
                    problems.append(f"flying lead {net}: unknown pin {m}")
                    continue
                if m in pin_net and pin_net[m] != net:
                    problems.append(f"{m[0]}.{m[1]} is in nets {pin_net[m]} and {net}")
                pin_net[m] = net
        # union-find over wires must reproduce the declared nets exactly
        parent = {}

        def find(x):
            parent.setdefault(x, x)
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a, b):
            parent[find(a)] = find(b)

        for w in self.wires:
            union(w.a, w.b)
        for name, m, h in self.bus_solder:
            union(m, ("BUS", name))
        for net, cls, a, b, text in self.flying:
            union(a, b)
        for name, n in self.nets.items():
            members = [m for m in pin_net if pin_net[m] == name]
            roots = {find(m) for m in members}
            if len(members) > 1 and len(roots) != 1:
                problems.append(f"net {name} is not fully connected ({len(roots)} islands)")
        groups = defaultdict(set)
        for m, nm in pin_net.items():
            groups[find(m)].add(nm)
        for g, names in groups.items():
            if len(names) > 1:
                problems.append(f"wires short nets together: {sorted(names)}")
        return problems

    @staticmethod
    def _bus_holes(p0, p1):
        (c0, r0), (c1, r1) = p0, p1
        if r0 == r1:
            return [(c, r0) for c in range(min(c0, c1), max(c0, c1) + 1)]
        return [(c0, r) for r in range(min(r0, r1), max(r0, r1) + 1)]

    # -- exports ----------------------------------------------------------
    def wiring_rows(self):
        rows = []
        step = 0
        listed = set()
        for name, cls, p0, p1 in self.buses:
            step += 1
            length = (abs(p1[0] - p0[0]) + abs(p1[1] - p0[1])) * PITCH
            solder = [f"{m[0]}.{self.parts[m[0]].fp.label(m[1])}" for n2, m, h in self.bus_solder
                      if n2 == name]
            note = ""
            if solder and name not in listed:
                note = "leads sitting on this bus, solder them to it: " + ", ".join(solder)
                listed.add(name)
            rows.append(dict(step=step, net=name, cls=cls, kind="bus bar",
                             frm=f"hole ({p0[0]},{p0[1]})", to=f"hole ({p1[0]},{p1[1]})",
                             wire="bare tinned 22 AWG solid", length_mm=round(length + 10),
                             note=note))
        for w in self.wires:
            step += 1
            w.step = step
            col, lw, wtype, _ = NET_CLASSES[w.cls]
            length = (abs(w.hb[0] - w.ha[0]) + abs(w.hb[1] - w.ha[1])) * PITCH
            a = f"{w.a[0]}.{self.parts[w.a[0]].fp.label(w.a[1])} ({w.ha[0]},{w.ha[1]})"
            b = (f"{w.b[1]} bus at ({w.hb[0]},{w.hb[1]})" if w.b[0] == "BUS"
                 else f"{w.b[0]}.{self.parts[w.b[0]].fp.label(w.b[1])} ({w.hb[0]},{w.hb[1]})")
            kind = {"link": "link (bend the lead / short bridge)", "tap": "tap to bus",
                    "wire": "wire"}.get(w.kind, w.kind)
            rows.append(dict(step=step, net=w.net, cls=w.cls, kind=kind, frm=a, to=b,
                             wire=("bare lead / short wire" if w.kind == "link" else wtype),
                             length_mm=(0 if w.kind == "link" else round(length + 12)), note=""))
        for net, cls, a, b, text in self.flying:
            step += 1
            pa, pb = self.parts[a[0]].pin_mm(a[1]), self.parts[b[0]].pin_mm(b[1])
            length = abs(pa[0] - pb[0]) + abs(pa[1] - pb[1])
            rows.append(dict(step=step, net=net, cls=cls, kind="flying lead (top side)",
                             frm=f"{a[0]}.{a[1]}", to=f"{b[0]}.{b[1]}",
                             wire=NET_CLASSES[cls][2], length_mm=round(length + 15), note=text))
        return rows

    def write_wiring_csv(self, path):
        rows = self.wiring_rows()
        with open(path, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=["step", "net", "cls", "kind", "frm", "to", "wire",
                                               "length_mm", "note"])
            w.writeheader()
            w.writerows(rows)
        return rows

    def write_parts_csv(self, path):
        with open(path, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["ref", "value", "footprint", "origin (col,row)", "rotation", "pins (col,row)",
                        "note"])
            for p in self.parts.values():
                pins = " ".join(f"{p.fp.label(n)}=({p.pin_hole(n)[0]},{p.pin_hole(n)[1]})"
                                for n in p.fp.pins if p.fp.on_grid(n))
                w.writerow([p.ref, p.value, p.fp.name, f"({p.at[0]},{p.at[1]})", p.rot, pins,
                            p.note])

    def write_bom_csv(self, path):
        groups = OrderedDict()
        for p in self.parts.values():
            key = (p.value, p.fp.name)
            g = groups.setdefault(key, ([], []))
            g[0].append(p.ref)
            if p.note and p.note not in g[1]:
                g[1].append(p.note)
        with open(path, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["qty", "refs", "value", "footprint / mounting", "note"])
            for (val, fpn), (refs, notes) in groups.items():
                w.writerow([len(refs), " ".join(refs), val, fpn, "; ".join(notes)])

    # -- rendering --------------------------------------------------------
    def _tx(self, x, mirror):
        return (self.cols - 1) * PITCH - x if mirror else x

    def _draw_board(self, ax, mirror):
        W, H = self.cols * PITCH, self.rows * PITCH
        ax.add_patch(Rectangle((-PITCH / 2, -PITCH / 2), W, H, fc="#dccfae", ec="#6b5a3a", lw=1.5,
                               zorder=0))
        for c in range(1, self.cols + 1):
            for r in range(1, self.rows + 1):
                ax.add_patch(Circle(((c - 1) * PITCH, (r - 1) * PITCH), 0.45, fc="#b89f6e",
                                    ec="none", zorder=1))
        for c in range(1, self.cols + 1):
            if c == 1 or c % 5 == 0:
                x = self._tx((c - 1) * PITCH, mirror)
                ax.text(x, -PITCH / 2 - 0.8, str(c), ha="center", va="bottom", fontsize=6,
                        color="#333")
                ax.text(x, H - PITCH / 2 + 0.8, str(c), ha="center", va="top", fontsize=6,
                        color="#333")
        for r in range(1, self.rows + 1):
            if r == 1 or r % 5 == 0:
                y = (r - 1) * PITCH
                ax.text(-PITCH / 2 - 0.8, y, str(r), ha="right", va="center", fontsize=6,
                        color="#333")
                ax.text(W - PITCH / 2 + 0.8, y, str(r), ha="left", va="center", fontsize=6,
                        color="#333")

    def _draw_parts(self, ax, mirror, ghost=False, labels=True):
        for p in self.parts.values():
            ox, oy = mm(p.at)
            fc = PART_COLOURS.get(p.cls, "#eeeeee")
            alpha = 0.30 if ghost else 0.90
            for item in p.fp.outline:
                kind = item[0]
                if kind in ("rect", "band"):
                    x0, y0, x1, y1 = item[1:5]
                    pts = [rot_vec(x, y, p.rot) for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))]
                    poly = [(self._tx(ox + x, mirror), oy + y) for x, y in pts]
                    ax.add_patch(Polygon(poly, closed=True,
                                         fc=("#555" if kind == "band" else fc),
                                         ec="#333", lw=0.8 if kind == "rect" else 0,
                                         alpha=alpha, zorder=3))
                elif kind == "circle":
                    x, y, r = item[1:4]
                    rx, ry = rot_vec(x, y, p.rot)
                    ax.add_patch(Circle((self._tx(ox + rx, mirror), oy + ry), r, fc=fc, ec="#333",
                                        lw=0.8, alpha=alpha, zorder=3))
                elif kind == "line":
                    x0, y0, x1, y1 = item[1:5]
                    a = rot_vec(x0, y0, p.rot)
                    b = rot_vec(x1, y1, p.rot)
                    ax.plot([self._tx(ox + a[0], mirror), self._tx(ox + b[0], mirror)],
                            [oy + a[1], oy + b[1]], color="#333", lw=0.8, zorder=3, alpha=alpha)
                elif kind == "notch":
                    x, y = item[1:3]
                    rx, ry = rot_vec(x, y, p.rot)
                    ax.add_patch(Circle((self._tx(ox + rx, mirror), oy + ry), 0.9, fc="white",
                                        ec="#333", lw=0.6, zorder=4, alpha=alpha))
                elif kind == "text" and labels:
                    x, y, s, size = item[1:5]
                    trot = item[5] if len(item) > 5 else 0
                    rx, ry = rot_vec(x, y, p.rot)
                    ax.text(self._tx(ox + rx, mirror), oy + ry, s, ha="center", va="center",
                            fontsize=size * 2.3, color="#222", zorder=5, alpha=0.5 if ghost else 1,
                            rotation=(trot + (0 if p.rot in (0, 180) else 90)) % 180)
            bx, by = p.body_center_mm()
            first = True
            for name, (dc, dr) in p.fp.pins.items():
                rc, rr = rot_vec(dc, dr, p.rot)
                px, py = ox + rc * PITCH, oy + rr * PITCH
                x = self._tx(px, mirror)
                on = p.fp.on_grid(name)
                if on:
                    if first and p.fp.pin1_square:
                        ax.add_patch(Rectangle((x - 0.8, py - 0.8), 1.6, 1.6, fc="#8a6d3b",
                                               ec="#222", lw=0.5, zorder=6))
                    else:
                        ax.add_patch(Circle((x, py), 0.8, fc="#8a6d3b", ec="#222", lw=0.5,
                                            zorder=6))
                else:
                    ax.add_patch(Rectangle((x - 1.1, py - 0.8), 2.2, 1.6, fc="#c9a227", ec="#222",
                                           lw=0.5, zorder=6))
                first = False
                if labels and p.fp.pin_labels:
                    dx, dy = px - bx, py - by
                    if abs(dx) > abs(dy) + 1e-6 and len(p.fp.pins) > 4:
                        sx = 1 if dx > 0 else -1
                        ax.text(self._tx(px + sx * 1.3, mirror), py, p.fp.label(name),
                                ha=("left" if (sx > 0) != mirror else "right"), va="center",
                                fontsize=4.0, color="#111", zorder=7)
                    else:
                        sy = 1 if dy > 0 else -1
                        if p.fp.pin_label_vertical:
                            ax.text(x, py + sy * 1.3, p.fp.label(name), ha="center",
                                    va=("top" if sy > 0 else "bottom"), fontsize=3.8, color="#111",
                                    zorder=7, rotation=90)
                        else:
                            ax.text(x, py + sy * 1.25, p.fp.label(name), ha="center",
                                    va=("top" if sy > 0 else "bottom"), fontsize=4.0, color="#111",
                                    zorder=7)
            if labels:
                if p.label_at:
                    lx, ly = p.label_at
                    lrot = 0
                else:
                    lx, ly = rot_vec(*p.fp.label_at, p.rot)
                    lrot = 90 if (p.fp.label_rot and p.rot in (90, 270)) else 0
                txt = p.ref if not p.value else f"{p.ref}  {p.value}"
                ax.text(self._tx(ox + lx, mirror), oy + ly, txt, ha="center", va="center",
                        fontsize=5.0, fontweight="bold", color="#0b0b3b", zorder=8, rotation=lrot,
                        bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.75))

    def _draw_wires(self, ax, mirror, classes=None, show_steps=False):
        longest = {}
        for name, cls, p0, p1 in self.buses:
            L = abs(p1[0] - p0[0]) + abs(p1[1] - p0[1])
            if L > longest.get(name, (-1, None))[0]:
                longest[name] = (L, (p0, p1))
        for name, cls, p0, p1 in self.buses:
            if classes and cls not in classes:
                continue
            col, lw, _, _ = NET_CLASSES[cls]
            a, b = mm(p0), mm(p1)
            ax.plot([self._tx(a[0], mirror), self._tx(b[0], mirror)], [a[1], b[1]], color=col,
                    lw=lw + 1.8, solid_capstyle="round", zorder=9, alpha=0.85)
            if longest[name][1] != (p0, p1):
                continue
            tx = self._tx(a[0], mirror)
            ty = a[1]
            if a[1] == b[1]:
                ax.text(tx, ty - 1.3, f"{name} bus", ha="center", va="bottom", fontsize=4.6,
                        color="white", fontweight="bold", zorder=12,
                        bbox=dict(boxstyle="round,pad=0.15", fc=col, ec="none", alpha=0.9))
            else:
                ax.text(tx - 1.3, ty, f"{name} bus", ha="right", va="center", fontsize=4.6,
                        color="white", fontweight="bold", zorder=12,
                        bbox=dict(boxstyle="round,pad=0.15", fc=col, ec="none", alpha=0.9))
        for w in self.wires:
            if classes and w.cls not in classes:
                continue
            col, lw, _, _ = NET_CLASSES[w.cls]
            xs = [self._tx(x, mirror) for x, _ in w.path]
            ys = [y for _, y in w.path]
            ax.plot(xs, ys, color=col, lw=lw, solid_capstyle="round", solid_joinstyle="round",
                    zorder=10 if w.cls in POWER_CLASSES else 11, alpha=0.95,
                    ls=("-" if w.kind != "link" else (0, (1.5, 1.0))))
            for (x, y) in (w.path[0], w.path[-1]):
                ax.add_patch(Circle((self._tx(x, mirror), y), 0.55, fc=col, ec="none", zorder=12))
            if show_steps and len(w.path) > 1:
                # label on the longest segment
                best = max(range(len(w.path) - 1),
                           key=lambda i: abs(w.path[i + 1][0] - w.path[i][0]) +
                           abs(w.path[i + 1][1] - w.path[i][1]))
                mx = (w.path[best][0] + w.path[best + 1][0]) / 2
                my = (w.path[best][1] + w.path[best + 1][1]) / 2
                ax.text(self._tx(mx, mirror), my, str(w.step), fontsize=3.6, color="white",
                        ha="center", va="center", zorder=13,
                        bbox=dict(boxstyle="circle,pad=0.12", fc=col, ec="none"))
        for net, cls, a, b, text in self.flying:
            if classes and cls not in classes:
                continue
            col, lw, _, _ = NET_CLASSES[cls]
            pa, pb = self.parts[a[0]].pin_mm(a[1]), self.parts[b[0]].pin_mm(b[1])
            ax.plot([self._tx(pa[0], mirror), self._tx(pb[0], mirror)], [pa[1], pb[1]], color=col,
                    lw=lw, ls=(0, (3, 2)), zorder=11, alpha=0.9)
            for (x, y) in (pa, pb):
                ax.add_patch(Circle((self._tx(x, mirror), y), 0.6, fc="white", ec=col, lw=1.0,
                                    zorder=12))

    def render(self, path, view="all", mirror=False, show_steps=False, dpi=170):
        W, H = self.cols * PITCH, self.rows * PITCH
        legend_w = 46.0
        fig_w = (W + legend_w) / 25.4 * 1.75
        fig_h = (H + 3 * PITCH) / 25.4 * 1.75
        fig, ax = plt.subplots(figsize=(fig_w, fig_h))
        ax.set_aspect("equal")
        ax.set_xlim(-PITCH, W + legend_w)
        ax.set_ylim(H + PITCH, -PITCH * 4.6)
        ax.axis("off")
        self._draw_board(ax, mirror)
        if view == "place":
            self._draw_parts(ax, mirror)
        elif view == "power":
            self._draw_parts(ax, mirror)
            self._draw_wires(ax, mirror, POWER_CLASSES, show_steps)
        elif view == "signal":
            self._draw_parts(ax, mirror)
            self._draw_wires(ax, mirror, set(NET_CLASSES) - POWER_CLASSES, show_steps)
        elif view == "bottom":
            self._draw_parts(ax, mirror, ghost=True, labels=True)
            self._draw_wires(ax, mirror, None, show_steps)
        else:
            self._draw_parts(ax, mirror)
            self._draw_wires(ax, mirror, None, show_steps)
        classes_shown = (POWER_CLASSES if view == "power" else
                         set(NET_CLASSES) - POWER_CLASSES if view == "signal" else
                         set() if view == "place" else set(NET_CLASSES))
        used = {w.cls for w in self.wires} | {b[1] for b in self.buses} | {f[1] for f in self.flying}
        lx = W + PITCH * 0.6
        ly = 0.0
        ax.text(lx, ly, "wire key", fontsize=6, fontweight="bold", va="center")
        ly += 3.4
        for cls, (col, lw, wtype, legend) in NET_CLASSES.items():
            if cls in classes_shown and cls in used:
                ax.plot([lx, lx + 6], [ly, ly], color=col, lw=lw + 0.5)
                ax.text(lx + 7.5, ly, legend, fontsize=5.2, va="center")
                ly += 3.2
        if view != "place":
            ly += 1.5
            ax.plot([lx, lx + 6], [ly, ly], color="#555", lw=1.2, ls=(0, (3, 2)))
            ax.text(lx + 7.5, ly, "dashed = lead soldered to a module pad", fontsize=5.2,
                    va="center")
            ly += 3.2
            ax.text(lx, ly, "dot = solder joint at a pad / bus", fontsize=5.2, va="center")
            ly += 3.2
        ly += 2.5
        ax.text(lx, ly, "part colours", fontsize=6, fontweight="bold", va="center")
        ly += 3.2
        for cls, col in PART_COLOURS.items():
            ax.add_patch(Rectangle((lx, ly - 1.2), 6, 2.4, fc=col, ec="#333", lw=0.5))
            ax.text(lx + 7.5, ly, cls, fontsize=5.2, va="center")
            ly += 3.0
        ly += 2.5
        for line in self.notes:
            ax.text(lx, ly, line, fontsize=4.8, va="center", wrap=True)
            ly += 2.9
        side = "BOTTOM / solder side (mirrored - what you see while soldering)" if mirror \
            else "TOP / component side"
        views = {"place": "part placement", "power": "power wiring", "signal": "signal wiring",
                 "all": "all wiring", "bottom": "all wiring"}
        ax.text(-PITCH / 2, -PITCH * 4.0, f"{self.title}", fontsize=10, fontweight="bold",
                va="center")
        ax.text(-PITCH / 2, -PITCH * 3.1, f"{side}  -  {views.get(view, view)}", fontsize=7.5,
                va="center", color="#222")
        ax.text(-PITCH / 2, -PITCH * 2.3, self.subtitle, fontsize=6, va="center", color="#333")
        fig.savefig(path, dpi=dpi, bbox_inches="tight", facecolor="white")
        plt.close(fig)

    def render_template_pdf(self, path):
        """1:1 scale printable template: hole grid + part outlines + labels."""
        W, H = self.cols * PITCH, self.rows * PITCH
        fig = plt.figure(figsize=((W + 2 * PITCH) / 25.4, (H + 2 * PITCH) / 25.4))
        ax = fig.add_axes([0, 0, 1, 1])
        ax.set_aspect("equal")
        ax.set_xlim(-PITCH * 1.5, W + PITCH * 0.5)
        ax.set_ylim(H + PITCH * 0.5, -PITCH * 1.5)
        ax.axis("off")
        self._draw_board(ax, False)
        self._draw_parts(ax, False)
        ax.text(0, -PITCH * 1.1, f"{self.title} - print at 100% (no page scaling); "
                f"hole pitch 2.54 mm; check with a ruler", fontsize=6)
        fig.savefig(path, dpi=300, facecolor="white")
        plt.close(fig)


def write_outputs(design, outdir, stem):
    os.makedirs(outdir, exist_ok=True)
    design.derive_wires()
    problems = design.check()
    rows = design.write_wiring_csv(os.path.join(outdir, f"{stem}-wiring.csv"))
    design.write_bom_csv(os.path.join(outdir, f"{stem}-bom.csv"))
    design.write_parts_csv(os.path.join(outdir, f"{stem}-parts.csv"))
    design.render(os.path.join(outdir, f"{stem}-1-placement.png"), "place")
    design.render(os.path.join(outdir, f"{stem}-2-power.png"), "power", show_steps=True)
    design.render(os.path.join(outdir, f"{stem}-3-signals.png"), "signal", show_steps=True)
    design.render(os.path.join(outdir, f"{stem}-4-all-top.png"), "all")
    design.render(os.path.join(outdir, f"{stem}-5-bottom-mirrored.png"), "bottom", mirror=True,
                  show_steps=True)
    design.render_template_pdf(os.path.join(outdir, f"{stem}-template-1to1.pdf"))
    return problems, rows
