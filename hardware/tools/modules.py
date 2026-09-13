"""Symbols and footprints for the third-party modules.

Everything else comes from the stock KiCad 8 libraries. These five parts do
not exist there because they are boards, not chips: they plug into female
headers and what the PCB needs is the header pattern, not the module.

The pin ORDER tables below are the highest-risk thing in either project. The
schematic is correct regardless of them - nets are written by pin name - but
the footprint pads follow these tables, so a wrong order means a board that
cannot be populated. Check each against the real module with a 1:1 printout
before ordering. Where a table is unverified it says so.
"""

import hashlib


def _stable_uuid(*parts):
    h = hashlib.sha256(("junofp|" + "|".join(str(p) for p in parts)).encode()).hexdigest()
    return f"{h[0:8]}-{h[8:12]}-4{h[13:16]}-a{h[17:20]}-{h[20:32]}"


SYM_VERSION = 20231120
FP_VERSION = 20240108

# ---------------------------------------------------------------------------
# Pin order tables.  index 0 is pad 1.
# ---------------------------------------------------------------------------

# SimpleFOC Mini v1.1 (DRV8313).  Two headers: control and motor output.
# Taken from the build console's driver diagram, which lists the control side
# as IN1 IN2 IN3 EN VIN GND and the motor side as OUT A/B/C.
# UNVERIFIED against the physical module - the console gives pin names, not
# a header pitch or spacing.
SIMPLEFOC_MINI_CTRL = ["IN1", "IN2", "IN3", "EN", "VIN", "GND"]
SIMPLEFOC_MINI_OUT = ["OUTA", "OUTB", "OUTC"]
SIMPLEFOC_MINI_ROW_SPACING = 20.32   # mm between header rows, 8 x 0.1in - VERIFY

# ESP32-S3 Super Mini, 2 x 11 on 2.54 mm.
# UNVERIFIED. External sources for this board were unreachable from the
# generating environment, so this is the conventional Super Mini arrangement
# and nothing more. Check it against your board before ordering; if it is
# wrong, correcting these two lists and regenerating is the whole fix.
ESP32_S3_LEFT = ["GND", "5V", "3V3", "IO1", "IO2", "IO3",
                 "IO4", "IO5", "IO6", "IO7", "IO8"]
ESP32_S3_RIGHT = ["IO9", "IO10", "IO11", "IO12", "IO13", "IO43",
                  "IO44", "IO48", "NC1", "NC2", "NC3"]
ESP32_S3_ROW_SPACING = 15.24         # 6 x 0.1in

# MP1584EN mini buck module: four pads, in the order printed on the board.
MP1584_PINS = ["IN+", "IN-", "OUT+", "OUT-"]

# Generic I2C sensor breakout on a 1x6: covers the ToF, the touch controller
# and the IMU. Unused pins are left as NC rather than pretending to know each
# board's extras.
MODULE_I2C_PINS = ["VCC", "GND", "SCL", "SDA", "INT", "NC"]

# INMP441 I2S microphone breakout, 1x6. This one is a standard part and the
# order is the usual silkscreen order.
INMP441_PINS = ["SCK", "WS", "LR", "SD", "VDD", "GND"]


# ---------------------------------------------------------------------------
# Symbol emission
# ---------------------------------------------------------------------------

def _prop(name, value, x, y, hide=False, size=1.27):
    h = "\n\t\t\t\t(hide yes)" if hide else ""
    return (f'\t\t(property "{name}" "{value}"\n'
            f'\t\t\t(at {x} {y} 0)\n'
            f'\t\t\t(effects\n\t\t\t\t(font\n\t\t\t\t\t(size {size} {size})\n\t\t\t\t){h}\n\t\t\t)\n'
            f'\t\t)\n')


def symbol(name, left, right, ref="U", desc="", value=None, w=None):
    """A plain rectangular symbol with pins down the left and right sides."""
    value = value or name
    n = max(len(left), len(right))
    half_h = (n + 1) * 1.27
    half_w = (w or 12.7) / 2
    s = f'\t(symbol "{name}"\n'
    s += '\t\t(pin_names\n\t\t\t(offset 0.254)\n\t\t)\n'
    s += '\t\t(exclude_from_sim no)\n\t\t(in_bom yes)\n\t\t(on_board yes)\n'
    s += _prop("Reference", ref, 0, half_h + 1.27)
    s += _prop("Value", value, 0, -half_h - 1.27)
    s += _prop("Footprint", "", 0, 0, hide=True)
    s += _prop("Datasheet", "", 0, 0, hide=True)
    s += _prop("Description", desc, 0, 0, hide=True)
    s += f'\t\t(symbol "{name}_0_1"\n'
    s += (f'\t\t\t(rectangle\n\t\t\t\t(start {-half_w} {half_h})\n\t\t\t\t(end {half_w} {-half_h})\n'
          '\t\t\t\t(stroke\n\t\t\t\t\t(width 0.254)\n\t\t\t\t\t(type default)\n\t\t\t\t)\n'
          '\t\t\t\t(fill\n\t\t\t\t\t(type background)\n\t\t\t\t)\n\t\t\t)\n\t\t)\n')
    s += f'\t\t(symbol "{name}_1_1"\n'

    def pin(pname, num, x, y, rot):
        etype = "power_in" if pname in ("VCC", "VDD", "5V", "3V3", "VIN", "IN+") else \
                "power_out" if pname in ("OUT+",) else \
                "passive" if pname in ("GND", "IN-", "OUT-") or pname.startswith("NC") else \
                "bidirectional"
        style = "line"
        return (f'\t\t\t(pin {etype} {style}\n\t\t\t\t(at {x} {y} {rot})\n\t\t\t\t(length 2.54)\n'
                f'\t\t\t\t(name "{pname}"\n\t\t\t\t\t(effects\n\t\t\t\t\t\t(font\n\t\t\t\t\t\t\t(size 1.27 1.27)\n\t\t\t\t\t\t)\n\t\t\t\t\t)\n\t\t\t\t)\n'
                f'\t\t\t\t(number "{num}"\n\t\t\t\t\t(effects\n\t\t\t\t\t\t(font\n\t\t\t\t\t\t\t(size 1.27 1.27)\n\t\t\t\t\t\t)\n\t\t\t\t\t)\n\t\t\t\t)\n\t\t\t)\n')

    for i, (pname, num) in enumerate(left):
        y = half_h - 2.54 - i * 2.54
        s += pin(pname, num, -half_w - 2.54, y, 0)
    for i, (pname, num) in enumerate(right):
        y = half_h - 2.54 - i * 2.54
        s += pin(pname, num, half_w + 2.54, y, 180)
    s += '\t\t)\n\t)\n'
    return s


# ---------------------------------------------------------------------------
# Footprint emission
# ---------------------------------------------------------------------------
PITCH = 2.54
PAD_D = 1.7          # pad diameter, generous for hand soldering
DRILL = 1.0          # 0.9 mm headers per 06_electrical, rounded up for tolerance


def footprint(name, pads, outline, desc="", courtyards=None):
    """pads: (number, x, y). outline: silk box. courtyards: boxes, default the outline.

    They differ for the SimpleFOC Mini: its body spans the MCU because it sits
    8.5 mm above the board on headers, so the silkscreen shows the whole module
    but the courtyard hugs each header row. One box would flag a collision that
    is only ever a stack.
    """
    x1, y1, x2, y2 = outline
    s = f'(footprint "{name}"\n\t(version {FP_VERSION})\n\t(generator "juno")\n'
    s += '\t(generator_version "8.0")\n\t(layer "F.Cu")\n'
    s += f'\t(descr "{desc}")\n\t(tags "juno module socket")\n'
    s += '\t(attr through_hole)\n'
    def fp_prop(pname, pval, py, layer):
        return (f'\t(property "{pname}" "{pval}"\n\t\t(at 0 {py} 0)\n'
                f'\t\t(layer "{layer}")\n\t\t(uuid "{_stable_uuid(name, pname)}")\n'
                '\t\t(effects\n\t\t\t(font\n\t\t\t\t(size 1 1)\n'
                '\t\t\t\t(thickness 0.15)\n\t\t\t)\n\t\t)\n\t)\n')
    s += fp_prop("Reference", "REF**", round(y1 - 1.2, 4), "F.SilkS")
    s += fp_prop("Value", name, round(y2 + 1.2, 4), "F.Fab")
    s += fp_prop("Datasheet", "", 0, "F.Fab")
    s += fp_prop("Description", desc, 0, "F.Fab")
    boxes = [("F.SilkS", 0.12, outline)]
    for cy_box in (courtyards or [outline]):
        boxes.append(("F.CrtYd", 0.05, cy_box))
    for layer, width, box in boxes:
        m = 0.25 if layer == "F.CrtYd" else 0.0
        bx1, by1, bx2, by2 = box
        a, b, c, d = bx1 - m, by1 - m, bx2 + m, by2 + m
        for (sx, sy, ex, ey) in ((a, b, c, b), (c, b, c, d), (c, d, a, d), (a, d, a, b)):
            s += (f'\t(fp_line\n\t\t(start {sx} {sy})\n\t\t(end {ex} {ey})\n'
                  f'\t\t(stroke\n\t\t\t(width {width})\n\t\t\t(type solid)\n\t\t)\n'
                  f'\t\t(layer "{layer}")\n\t)\n')
    for num, px, py in pads:
        shape = "rect" if num == 1 else "circle"
        s += (f'\t(pad "{num}" thru_hole {shape}\n\t\t(at {px} {py})\n'
              f'\t\t(size {PAD_D} {PAD_D})\n\t\t(drill {DRILL})\n'
              f'\t\t(layers "*.Cu" "*.Mask")\n\t\t(remove_unused_layers no)\n\t)\n')
    s += ')\n'
    return s


def row(n_start, count, x, y0, dy=PITCH):
    return [(n_start + i, x, y0 + i * dy) for i in range(count)]


# ---------------------------------------------------------------------------
# The five modules
# ---------------------------------------------------------------------------

def build():
    syms, fps = [], {}

    # --- SimpleFOC Mini ----------------------------------------------------
    ctrl = [(n, i + 1) for i, n in enumerate(SIMPLEFOC_MINI_CTRL)]
    out = [(n, len(ctrl) + i + 1) for i, n in enumerate(SIMPLEFOC_MINI_OUT)]
    syms.append(symbol("SimpleFOC_Mini", ctrl, out, ref="M",
                       desc="SimpleFOC Mini v1.1 (DRV8313) on female headers",
                       value="SimpleFOC Mini", w=17.78))
    sp = SIMPLEFOC_MINI_ROW_SPACING
    pads = row(1, 6, -sp / 2, -(5 * PITCH) / 2) + row(7, 3, sp / 2, -(2 * PITCH) / 2)
    hh = (5 * PITCH) / 2
    fps["SimpleFOC_Mini_Socket"] = footprint(
        "SimpleFOC_Mini_Socket", pads,
        (-sp / 2 - 2.5, -hh - 2.5, sp / 2 + 2.5, hh + 2.5),
        desc="SimpleFOC Mini on 1x6 + 1x3 female headers - VERIFY row spacing",
        courtyards=[(-sp / 2 - 1.6, -hh - 1.6, -sp / 2 + 1.6, hh + 1.6),
                    (sp / 2 - 1.6, -PITCH - 1.6, sp / 2 + 1.6, PITCH + 1.6)])

    # --- ESP32-S3 Super Mini ----------------------------------------------
    left = [(n, i + 1) for i, n in enumerate(ESP32_S3_LEFT)]
    right = [(n, len(left) + i + 1) for i, n in enumerate(ESP32_S3_RIGHT)]
    syms.append(symbol("ESP32_S3_SuperMini", left, right, ref="A",
                       desc="ESP32-S3 Super Mini on female headers",
                       value="ESP32-S3 Super Mini", w=20.32))
    sp = ESP32_S3_ROW_SPACING
    nrow = len(ESP32_S3_LEFT)
    y0 = -((nrow - 1) * PITCH) / 2
    pads = row(1, nrow, -sp / 2, y0) + row(nrow + 1, len(ESP32_S3_RIGHT), sp / 2, y0)
    fps["ESP32_S3_SuperMini_Socket"] = footprint(
        "ESP32_S3_SuperMini_Socket", pads,
        (-sp / 2 - 2.5, y0 - 2.5, sp / 2 + 2.5, -y0 + 2.5),
        desc="ESP32-S3 Super Mini 2x11 female headers - VERIFY pin order")

    # --- MP1584EN buck -----------------------------------------------------
    inp = [(n, i + 1) for i, n in enumerate(MP1584_PINS[:2])]
    outp = [(n, i + 3) for i, n in enumerate(MP1584_PINS[2:])]
    syms.append(symbol("MP1584EN_Module", inp, outp, ref="A",
                       desc="MP1584EN adjustable buck module, set to 5 V",
                       value="MP1584EN", w=15.24))
    sp = 17.78
    pads = row(1, 2, -sp / 2, -PITCH / 2) + row(3, 2, sp / 2, -PITCH / 2)
    fps["MP1584EN_Module"] = footprint(
        "MP1584EN_Module", pads, (-sp / 2 - 3, -PITCH / 2 - 3, sp / 2 + 3, PITCH / 2 + 3),
        desc="MP1584EN mini buck, IN pair one end, OUT pair the other")

    # --- generic I2C breakout and the mic ----------------------------------
    for nm, pins, ref, desc in (
        ("Module_I2C_INT", MODULE_I2C_PINS, "A", "I2C sensor breakout on a 1x6 header"),
        ("INMP441", INMP441_PINS, "A", "INMP441 I2S MEMS microphone breakout"),
    ):
        half = (len(pins) + 1) // 2
        l = [(n, i + 1) for i, n in enumerate(pins[:half])]
        r = [(n, half + i + 1) for i, n in enumerate(pins[half:])]
        syms.append(symbol(nm, l, r, ref=ref, desc=desc, value=nm))

    fps["Module_1x06_2.54"] = footprint(
        "Module_1x06_2.54", row(1, 6, 0, -(5 * PITCH) / 2),
        (-2.5, -(5 * PITCH) / 2 - 2.5, 2.5, (5 * PITCH) / 2 + 2.5),
        desc="1x6 2.54 mm header for a sensor breakout")

    lib = f'(kicad_symbol_lib\n\t(version {SYM_VERSION})\n\t(generator "juno")\n\t(generator_version "8.0")\n'
    lib += "".join(syms) + ')\n'
    return lib, fps


if __name__ == "__main__":
    import os
    import sys
    out = sys.argv[1] if len(sys.argv) > 1 else "."
    lib, fps = build()
    os.makedirs(f"{out}/juno.pretty", exist_ok=True)
    open(f"{out}/juno.kicad_sym", "w").write(lib)
    for n, body in fps.items():
        open(f"{out}/juno.pretty/{n}.kicad_mod", "w").write(body)
    n_sym = lib.count('\t(symbol "')
    print(f"wrote juno.kicad_sym ({n_sym} symbols) and {len(fps)} footprints to {out}")
