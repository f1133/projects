"""Parametric CAD for the cycloidal disc and its ring housing.

Reads the same ``config/gearbox.toml`` the analysis does, so the solid and the
numbers cannot drift apart. This is the only part of the project that needs a
dependency beyond the standard library::

    pip install build123d
    python cad/disc.py --out out

Two-disc indexing
-----------------
With two discs the cams sit 180 degrees apart, which puts the discs half a
lobe pitch apart in their own rotation -- ``180/n_lobes``, here 7.5 degrees.
The output pins are shared between both discs, so the hole pattern has to stay
put and the *profile* is what gets indexed. That is why disc B is a separate
part rather than disc A turned over.
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from gearbox import config, cycloid  # noqa: E402

try:
    from build123d import (  # noqa: E402
        Cylinder,
        Polyline,
        Pos,
        export_step,
        export_stl,
        extrude,
        make_face,
    )
except ImportError:  # pragma: no cover - exercised only without the dependency
    sys.exit(
        "build123d is not installed.\n"
        "  pip install build123d\n"
        "The analysis and the profile export do not need it; only this script does."
    )


def disc_solid(design: config.Design, profile_index_deg: float = 0.0, samples: int = 160):
    """One cycloidal disc: lobed profile, centre bore, output holes.

    ``profile_index_deg`` rotates the lobes relative to the hole pattern, which
    is what separates disc A from disc B in a two-disc stack.

    The solid is built centred on z=0 so that the cylinders cut from it, which
    build123d also centres, line up without any extra positioning.
    """
    geom = design.geometry
    out = design.output
    prof = cycloid.profile(geom, samples_per_lobe=samples)
    index = math.radians(profile_index_deg)
    cos_i, sin_i = math.cos(index), math.sin(index)
    points = [
        (x * cos_i - y * sin_i, x * sin_i + y * cos_i) for x, y in prof.points
    ]

    thickness = geom.disc_thickness_mm
    face = make_face(Polyline(*points, close=True))
    disc = extrude(face, amount=thickness / 2, both=True)

    # Cut deeper than the disc so the boolean never leaves a coincident face.
    through = thickness * 2
    disc -= Cylinder(radius=geom.center_bore_radius_mm, height=through)

    hole_r = out.hole_radius_mm(geom.eccentricity_mm)
    for j in range(out.n_pins):
        angle = 2 * math.pi * j / out.n_pins
        disc -= Pos(
            out.bolt_circle_radius_mm * math.cos(angle),
            out.bolt_circle_radius_mm * math.sin(angle),
            0.0,
        ) * Cylinder(radius=hole_r, height=through)
    return disc


def ring_housing(design: config.Design):
    """The ring the pins run in: an annulus bored for every ring pin.

    Pin bores are cut at the nominal pin radius. Put clearance in the slicer or
    in ``profile_offset_mm`` rather than here, so the CAD keeps matching the
    geometry the stress checks were run on.
    """
    geom = design.geometry
    env = design.envelope
    height = geom.n_discs * geom.disc_thickness_mm
    through = height * 2

    ring = Cylinder(radius=env.housing_od_mm / 2, height=height)
    ring -= Cylinder(
        radius=geom.pin_circle_radius_mm - geom.ring_pin_radius_mm, height=through
    )
    for i in range(geom.n_ring_pins):
        angle = 2 * math.pi * i / geom.n_ring_pins
        ring -= Pos(
            geom.pin_circle_radius_mm * math.cos(angle),
            geom.pin_circle_radius_mm * math.sin(angle),
            0.0,
        ) * Cylinder(radius=geom.ring_pin_radius_mm, height=through)
    return ring


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-c", "--config", default=str(ROOT / "config/gearbox.toml"))
    parser.add_argument("-o", "--out", default=str(ROOT / "out"))
    parser.add_argument("-n", "--samples", type=int, default=80,
                        help="profile points per lobe")
    parser.add_argument("--stl", action="store_true", help="also write STL")
    args = parser.parse_args(argv)

    design = config.load(args.config)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    index = 180.0 / design.geometry.n_lobes
    solids = {
        "disc_a": disc_solid(design, 0.0, args.samples),
        "ring_housing": ring_housing(design),
    }
    if design.geometry.n_discs > 1:
        solids["disc_b"] = disc_solid(design, index, args.samples)

    for name, solid in solids.items():
        step = out_dir / f"{name}.step"
        export_step(solid, str(step))
        print(f"wrote {step}  ({solid.volume / 1000:.2f} cm^3)")
        if args.stl:
            stl = out_dir / f"{name}.stl"
            export_stl(solid, str(stl))
            print(f"wrote {stl}")

    if design.geometry.n_discs > 1:
        print(f"\ndisc_b profile is indexed {index:.2f} deg from disc_a; "
              "assemble on cams 180 deg apart")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
