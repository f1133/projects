"""Test coupons to print before committing to a full gearbox.

Three prints, in the order they are worth doing:

``fit_gauge``
    Every press and slip fit in the gearbox, as stepped bores. One print tells
    you what your printer actually produces, and every other dimension follows
    from that. Do this first -- it is the cheapest hour in the project.

``mesh_disc`` + ``mesh_ring``
    A 3 mm slice of the real disc and ring. With the ring dowels in place you
    can roll the disc by hand, feel the mesh and measure backlash, without
    committing seven hours to a full-height set. The split variant also answers
    whether the adjustable ring flexes without cracking.

``disc``
    The real disc, full height.

Geometry comes from the design TOML, so the coupons and the analysis cannot
drift apart::

    pip install build123d
    python cad/coupons.py --config config/gearbox_688.toml --out out
"""

from __future__ import annotations

import argparse
import math
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from gearbox import config, cycloid  # noqa: E402

try:
    from build123d import (  # noqa: E402
        Box,
        Cylinder,
        Polyline,
        Pos,
        Rot,
        Text,
        export_stl,
        extrude,
        make_face,
    )
except ImportError:  # pragma: no cover - only hit without the dependency
    sys.exit(
        "build123d is not installed.\n"
        "  pip install build123d\n"
        "Only the CAD needs it; the analysis and profile export do not."
    )

LABEL_HEIGHT = 3.2
LABEL_DEPTH = 0.6
TAB_THICKNESS = 1.5


def _label(text: str, x: float, y: float, z: float):
    """Raised text sitting on top of ``z``, left-aligned from ``x``.

    Raised rather than engraved: engraved text this small fills in with the
    first layer printed over it and stops being readable.
    """
    return Pos(x, y, z) * extrude(Text(text, font_size=LABEL_HEIGHT), amount=LABEL_DEPTH)


PIN_EMBED_MM = 1.2
"""How much of a ring pin's diameter is buried in the housing wall."""

TAB_OVERLAP = 3.0
"""How far a label tab reaches into the body it labels.

Enough to meet real material rather than the tangent point of a circle. Overlap
at the tangent looks like contact on screen and unions into two separate solids,
which is what happens if this is too small.
"""


def _label_tab(text: str, x: float, top_y: float):
    """A label on a tab whose top edge sits at ``top_y``.

    Bare extruded text is a 0.6 mm island the slicer will drop or print as
    something that snaps off the bed, so the text needs a base; the base in turn
    has to reach into the body it labels or the two stay separate parts.
    """
    height = 10.0
    tab = Pos(x, top_y - height / 2, TAB_THICKNESS / 2) * Box(
        18.0, height, TAB_THICKNESS
    )
    return tab + _label(text, x - 6.0, top_y - height + 2.6, TAB_THICKNESS)


def fit_gauge():
    """Stepped bores for every fit in the gearbox, labelled with its size.

    Bearing seats are printed at full bearing width so the press is
    representative -- a shallow test bore is easier to enter than the real one
    and will tell you the fit is looser than it is.

    Read it by trying the real part in each bore. The one that needs firm thumb
    pressure and stays put is your size; take the difference from nominal as
    your printer's offset and apply it everywhere else.
    """
    parts = []

    # --- bearing seats: 608ZZ (Ø22 x 7) and 688ZZ (Ø16 x 5) -------------------
    for row, (nominal, width, sizes) in enumerate(
        [
            (22.0, 7.0, (21.70, 21.85, 22.00)),
            (16.0, 5.0, (15.70, 15.85, 16.00)),
        ]
    ):
        outer = nominal + 7.0
        pitch = outer + 3.0
        y = -row * 40.0
        for i, bore in enumerate(sizes):
            x = i * pitch
            body = Pos(x, y, width / 2) * Cylinder(radius=outer / 2, height=width)
            body += _label_tab(f"{bore:.2f}", x, y - outer / 2 + TAB_OVERLAP)
            # Bore cut last, so the tab can reach in without ever blocking it.
            body -= Pos(x, y, width / 2) * Cylinder(
                radius=bore / 2, height=width * 3
            )
            parts.append(body)

    # --- through holes: dowel fits, output hole, heat-set inserts -------------
    holes = [
        (2.90, "dowel"), (2.95, ""), (3.00, ""), (3.05, ""),
        (3.10, "ring"), (3.15, ""), (3.20, ""),
        (4.60, "out"), (4.00, "M3"), (4.20, ""),
    ]
    bar_t = 5.0
    pitch = 9.0
    length = pitch * len(holes) + 6.0
    y = -84.0
    bar = Pos(length / 2 - pitch / 2 - 3.0, y, bar_t / 2) * Box(length, 20.0, bar_t)
    for i, (dia, _) in enumerate(holes):
        bar -= Pos(i * pitch, y + 3.5, bar_t / 2) * Cylinder(
            radius=dia / 2, height=bar_t * 2
        )
    parts.append(bar)
    # Labels ride on the bar's own top face, so they need no tab.
    for i, (dia, _) in enumerate(holes):
        parts.append(_label(f"{dia:.2f}", i * pitch - 4.4, y - 7.4, bar_t))

    solid = parts[0]
    for extra in parts[1:]:
        solid += extra
    return solid


def _disc(
    design: config.Design,
    thickness: float,
    samples: int = 120,
    output_holes: bool = True,
):
    """The disc profile at an arbitrary thickness, with bore and output holes.

    ``output_holes=False`` leaves the rim untouched, which is what the mesh
    coupons want: the profile depends only on the ring geometry, so a coupon
    without them meshes identically whichever output coupling is chosen, and the
    backlash it measures carries over.
    """
    geom = design.geometry
    out = design.output
    points = cycloid.profile(geom, samples_per_lobe=samples).points

    disc = extrude(make_face(Polyline(*points, close=True)), amount=thickness)
    through = thickness * 3
    disc -= Pos(0, 0, thickness / 2) * Cylinder(
        radius=geom.center_bore_radius_mm, height=through
    )
    if output_holes:
        hole_r = out.hole_radius_mm(geom.eccentricity_mm)
        for angle in out.hole_angles_rad():
            disc -= Pos(
                out.bolt_circle_radius_mm * math.cos(angle),
                out.bolt_circle_radius_mm * math.sin(angle),
                thickness / 2,
            ) * Cylinder(radius=hole_r, height=through)
    return disc


def mesh_ring(design: config.Design, thickness: float, split: bool):
    """The ring the disc meshes with, at coupon thickness.

    The bore clears the disc's swept radius, which is one eccentricity larger
    than the disc's own outer radius because the disc orbits as it turns. Sizing
    the bore to the disc alone is a classic way to build one that binds.

    ``split`` adds the radial slot and clamp boss so the same print also answers
    whether the adjustable ring flexes without cracking. The boss stands proud
    of Ø48; on the real housing it needs to be let into the wall.
    """
    geom = design.geometry
    env = design.envelope

    # The pins sit in pockets open to the bore, so the bore radius is set by how
    # deep the pin is embedded, not by clearing the disc. The mouth that leaves
    # is what retains the pin: narrower than the pin and it snaps in and stays,
    # wider and it drops out. A Ø3.0 pocket 1.2 mm embedded gives a 2.94 mm
    # mouth against a Ø3.0 dowel. Opening the pocket to Ø3.1 gives 3.04 and the
    # pin is no longer held.
    pin_hole = geom.ring_pin_radius_mm
    bore = geom.pin_circle_radius_mm + pin_hole - PIN_EMBED_MM

    swept = geom.disc_outer_radius_mm + geom.eccentricity_mm
    if bore < swept:
        raise ValueError(
            f"ring bore R{bore:.2f} would foul the disc, which sweeps R{swept:.2f}"
        )

    ring = Pos(0, 0, thickness / 2) * Cylinder(
        radius=env.housing_od_mm / 2, height=thickness
    )
    ring -= Pos(0, 0, thickness / 2) * Cylinder(radius=bore, height=thickness * 3)

    for i in range(geom.n_ring_pins):
        angle = 2 * math.pi * i / geom.n_ring_pins
        ring -= Pos(
            geom.pin_circle_radius_mm * math.cos(angle),
            geom.pin_circle_radius_mm * math.sin(angle),
            thickness / 2,
        ) * Cylinder(radius=pin_hole, height=thickness * 3)

    if split:
        # Slot sits midway between two pins, so it removes no pin support.
        slot_angle = math.pi / geom.n_ring_pins
        span = env.housing_od_mm / 2 - bore + 2.0
        mid = (bore + env.housing_od_mm / 2) / 2
        ring -= (
            Rot(0, 0, math.degrees(slot_angle))
            * Pos(mid, 0, thickness / 2)
            * Box(span, 1.2, thickness * 3)
        )
        boss = (
            Rot(0, 0, math.degrees(slot_angle))
            * Pos(env.housing_od_mm / 2 + 2.5, 0, thickness / 2)
            * Box(9.0, 16.0, thickness)
        )
        ring += boss
        # Tangential M3: clearance one side of the slot, pilot the other.
        clamp = Rot(0, 0, math.degrees(slot_angle)) * Pos(
            env.housing_od_mm / 2 + 2.5, 4.0, thickness / 2
        ) * Rot(90, 0, 0) * Cylinder(radius=1.7, height=9.0)
        ring -= clamp
        pilot = Rot(0, 0, math.degrees(slot_angle)) * Pos(
            env.housing_od_mm / 2 + 2.5, -4.5, thickness / 2
        ) * Rot(90, 0, 0) * Cylinder(radius=1.25, height=8.0)
        ring -= pilot
    return ring


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-c", "--config", default=str(ROOT / "config/gearbox_688.toml"))
    parser.add_argument("-o", "--out", default=str(ROOT / "out"))
    parser.add_argument("--coupon-thickness", type=float, default=3.0)
    parser.add_argument(
        "--clearances",
        type=float,
        nargs="*",
        default=[0.15, 0.20, 0.25],
        help="profile offsets to emit mesh discs at, mm",
    )
    parser.add_argument("-n", "--samples", type=int, default=120)
    args = parser.parse_args(argv)

    design = config.load(args.config)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    solids = {
        "fit_gauge": fit_gauge(),
        "mesh_ring": mesh_ring(design, args.coupon_thickness, split=False),
        "mesh_ring_split": mesh_ring(design, args.coupon_thickness, split=True),
        "disc": _disc(design, design.geometry.disc_thickness_mm, args.samples),
    }
    # One mesh disc per clearance: the cheapest way to find the fit is to print
    # the three that bracket it and see which turns freely without rattling.
    for clearance in args.clearances:
        variant = replace(
            design,
            geometry=replace(design.geometry, profile_offset_mm=clearance),
        )
        name = f"mesh_disc_{round(clearance * 100):03d}"
        solids[name] = _disc(
            variant, args.coupon_thickness, args.samples, output_holes=False
        )
    for name, solid in solids.items():
        path = out_dir / f"{name}.stl"
        # The gauge is prisms and text, where fine tessellation buys nothing but
        # file size. The disc profile is the whole point, so it keeps the default.
        coarse = name == "fit_gauge"
        export_stl(
            solid,
            str(path),
            tolerance=0.02 if coarse else 0.001,
            angular_tolerance=0.5 if coarse else 0.1,
        )
        size = solid.bounding_box().size
        print(f"wrote {path}  {size.X:.1f} x {size.Y:.1f} x {size.Z:.1f} mm, "
              f"{solid.volume / 1000:.2f} cm^3")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
