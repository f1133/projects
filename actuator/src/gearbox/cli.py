"""Command line entry point: ``python -m gearbox <command>``.

Commands
--------
``report``   design report and pass/fail checks
``check``    checks only; exit status 1 if any fail, for use in CI
``profile``  export the disc profile as CSV, SVG or DXF
``bom``      render the mechanical bill of materials
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

from . import bom as bom_module
from . import config, cycloid, report

DEFAULT_CONFIG = Path("config/gearbox.toml")
DEFAULT_BOM = Path("config/bom.toml")


def _load(path: Path) -> config.Design:
    try:
        return config.load(path)
    except FileNotFoundError:
        sys.exit(f"no design file at {path}")
    except config.ConfigError as exc:
        sys.exit(f"invalid design: {exc}")


def _output_holes(design: config.Design) -> list[tuple[float, float, float]]:
    """Centres and radii of the output-pin holes, in the disc's own frame."""
    out = design.output
    hole_r = out.hole_radius_mm(design.geometry.eccentricity_mm)
    return [
        (
            out.bolt_circle_radius_mm * math.cos(2 * math.pi * j / out.n_pins),
            out.bolt_circle_radius_mm * math.sin(2 * math.pi * j / out.n_pins),
            hole_r,
        )
        for j in range(out.n_pins)
    ]


def _write_csv(prof: cycloid.Profile, design: config.Design, out: Path) -> None:
    """Profile points only -- the format exists to be read by other tools."""
    lines = ["x_mm,y_mm"]
    lines += [f"{x:.6f},{y:.6f}" for x, y in prof.points]
    out.write_text("\n".join(lines) + "\n")


def _write_svg(prof: cycloid.Profile, design: config.Design, out: Path) -> None:
    """A look at the whole mesh in a browser, not a manufacturing output.

    Draws the disc where it actually sits -- offset by the eccentricity -- with
    the ring pins around it, because a disc on its own tells you nothing about
    whether the mesh is sensible. DXF and CSV stay geometry-only.

    SVG's y axis points down, so everything is mirrored to keep the same
    handedness as the CAD and the CSV.
    """
    geom = design.geometry
    env = design.envelope
    e = geom.eccentricity_mm
    pad = 2.0
    size = 2 * (env.housing_od_mm / 2 + pad)

    path = " ".join(
        f"{'M' if i == 0 else 'L'}{x + e:.4f},{-y:.4f}"
        for i, (x, y) in enumerate(prof.points)
    )
    pins = "".join(
        '<circle cx="{:.4f}" cy="{:.4f}" r="{:.4f}"/>'.format(
            geom.pin_circle_radius_mm * math.cos(2 * math.pi * i / geom.n_ring_pins),
            -geom.pin_circle_radius_mm * math.sin(2 * math.pi * i / geom.n_ring_pins),
            geom.ring_pin_radius_mm,
        )
        for i in range(geom.n_ring_pins)
    )
    holes = "".join(
        f'<circle cx="{x + e:.4f}" cy="{-y:.4f}" r="{r:.4f}"/>'
        for x, y, r in _output_holes(design)
    )
    out_pins = "".join(
        '<circle cx="{:.4f}" cy="{:.4f}" r="{:.4f}"/>'.format(
            design.output.bolt_circle_radius_mm
            * math.cos(2 * math.pi * j / design.output.n_pins),
            -design.output.bolt_circle_radius_mm
            * math.sin(2 * math.pi * j / design.output.n_pins),
            design.output.pin_radius_mm,
        )
        for j in range(design.output.n_pins)
    )

    out.write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="640" height="640" '
        f'viewBox="{-size / 2:.3f} {-size / 2:.3f} {size:.3f} {size:.3f}">'
        f'<circle cx="0" cy="0" r="{env.housing_od_mm / 2:.4f}" '
        f'fill="none" stroke="#bbb" stroke-width="0.3"/>'
        f'<g fill="#e8eef5" stroke="#2b4c6f" stroke-width="0.25">'
        f'<path d="{path} Z"/></g>'
        f'<g fill="#fff" stroke="#2b4c6f" stroke-width="0.2">'
        f'<circle cx="{e:.4f}" cy="0" r="{geom.center_bore_radius_mm:.4f}"/>'
        f"{holes}</g>"
        f'<g fill="#c0392b" stroke="none">{pins}</g>'
        f'<g fill="#7f8c8d" stroke="none">{out_pins}</g>'
        f'<circle cx="0" cy="0" r="0.4" fill="#111"/>'
        f'<circle cx="{e:.4f}" cy="0" r="0.4" fill="#c0392b"/>'
        f"</svg>\n"
    )


def _write_dxf(prof: cycloid.Profile, design: config.Design, out: Path) -> None:
    """Minimal DXF R12: the profile as a closed polyline, plus bore and holes.

    Written by hand rather than pulling in a library, so the export stays
    dependency-free. R12 entities are simple enough for that to be safe and
    every CAD package still reads them.
    """
    geom = design.geometry
    parts = ["0", "SECTION", "2", "ENTITIES"]

    parts += ["0", "POLYLINE", "8", "PROFILE", "66", "1", "70", "1"]
    for x, y in prof.points:
        parts += ["0", "VERTEX", "8", "PROFILE", "10", f"{x:.6f}", "20", f"{y:.6f}"]
    parts += ["0", "SEQEND"]

    parts += [
        "0", "CIRCLE", "8", "BORE",
        "10", "0.0", "20", "0.0",
        "40", f"{geom.center_bore_radius_mm:.6f}",
    ]
    for x, y, r in _output_holes(design):
        parts += [
            "0", "CIRCLE", "8", "HOLES",
            "10", f"{x:.6f}", "20", f"{y:.6f}", "40", f"{r:.6f}",
        ]

    parts += ["0", "ENDSEC", "0", "EOF"]
    out.write_text("\n".join(parts) + "\n")


def _profile_command(args: argparse.Namespace) -> int:
    design = _load(Path(args.config))
    prof = cycloid.profile(design.geometry, samples_per_lobe=args.samples)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    writers = {".csv": _write_csv, ".svg": _write_svg, ".dxf": _write_dxf}
    suffix = out.suffix.lower()
    if suffix not in writers:
        sys.exit(f"cannot write '{suffix}'; use one of {', '.join(sorted(writers))}")
    writers[suffix](prof, design, out)

    print(f"wrote {out}  ({len(prof.points)} points, "
          f"{prof.root_radius_mm:.3f}-{prof.outer_radius_mm:.3f} mm radius)")
    if not cycloid.is_simple(prof):
        print("WARNING: profile self-intersects -- it undercuts and cannot be made",
              file=sys.stderr)
        return 1
    return 0


def _report_command(args: argparse.Namespace) -> int:
    design = _load(Path(args.config))
    print(report.render(design))
    return 0


def _check_command(args: argparse.Namespace) -> int:
    design = _load(Path(args.config))
    results = report.checks(design)
    for check in results:
        print(check.format())
    failed = [c for c in results if not c.ok]
    print()
    if failed:
        print(f"{len(failed)} of {len(results)} checks FAILED")
        return 1
    print(f"all {len(results)} checks pass")
    return 0


def _bom_command(args: argparse.Namespace) -> int:
    path = Path(args.bom)
    try:
        parts = bom_module.load(path)
    except FileNotFoundError:
        sys.exit(f"no bill of materials at {path}")
    print(bom_module.render(parts))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="gearbox", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "-c", "--config", default=str(DEFAULT_CONFIG), help="design TOML"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("report", help="full design report").set_defaults(
        func=_report_command
    )
    sub.add_parser("check", help="checks only; non-zero exit on failure").set_defaults(
        func=_check_command
    )

    prof = sub.add_parser("profile", help="export the disc profile")
    prof.add_argument("-o", "--out", default="out/disc.csv", help=".csv, .svg or .dxf")
    prof.add_argument(
        "-n", "--samples", type=int, default=120, help="points per lobe"
    )
    prof.set_defaults(func=_profile_command)

    bom_parser = sub.add_parser("bom", help="render the mechanical BOM")
    bom_parser.add_argument("-b", "--bom", default=str(DEFAULT_BOM))
    bom_parser.set_defaults(func=_bom_command)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
