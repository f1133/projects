"""Turn a design into pass/fail checks and a readable report.

The checks are the point of this module. Each one is a single number against a
single limit, so a failing design says which number to change rather than just
that something is wrong.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, fields

from . import cycloid, loads
from .config import ConfigError, Design


@dataclass(frozen=True)
class Limits:
    """Thresholds the checks are judged against.

    Defaults are ordinary practice for a cycloidal stage rather than anything
    from a standard; override them per design where you have better numbers.
    """

    min_curtate_ratio: float = 0.5
    max_curtate_ratio: float = 0.8
    min_undercut_margin: float = 1.15
    max_pressure_angle_deg: float = 45.0
    min_web_mm: float = 2.0
    """Least material to leave between an output hole and any other feature."""

    min_ring_pin_gap_mm: float = 1.0
    min_torque_margin: float = 1.0
    """Peak output torque divided by the target the application asks for."""

    end_plate_allowance_mm: float = 8.0
    """Axial space for housing plates and bearings on top of the disc stack."""


def limits_from(design: Design) -> Limits:
    """Read a design's own thresholds, falling back to the defaults.

    Defaults are general rules of thumb, and a project that has a better reason
    should be able to say so in one place rather than arguing with the tool.
    Every override belongs next to its reason in the TOML.
    """
    if not design.limits:
        return Limits()
    known = {f.name for f in fields(Limits)}
    unknown = set(design.limits) - known
    if unknown:
        raise ConfigError(
            "unknown key in [limits]: "
            + ", ".join(sorted(unknown))
            + f"; known keys are {', '.join(sorted(known))}"
        )
    return Limits(**design.limits)


@dataclass(frozen=True)
class Check:
    name: str
    value: float
    limit: float
    unit: str
    ok: bool
    note: str = ""

    def format(self) -> str:
        mark = "PASS" if self.ok else "FAIL"
        return f"  [{mark}] {self.name:<34} {self.value:>10.3f} {self.unit:<6} {self.note}"


@dataclass(frozen=True)
class Clearances:
    """Radial gaps that decide whether the disc can actually be made."""

    hole_to_bore_mm: float
    """Web between an output hole and the central eccentric-bearing bore."""

    hole_to_root_mm: float
    """Radial web between an output hole and the deepest point of a lobe root.

    The conservative reading: it assumes some hole sits right over a root.
    """

    hole_to_profile_mm: float
    """True least web from any output hole to the profile, at the drawn phase.

    Whether a hole actually lands on a root depends on how the hole pattern and
    the lobes line up, so this measures it rather than assuming it.
    """

    best_hole_phase_deg: float
    """Rotation of the hole pattern that opens the tightest web furthest."""

    best_hole_to_profile_mm: float
    """The web at that phase -- how much rotating alone can buy."""

    ring_pin_gap_mm: float
    """Circumferential gap between neighbouring ring pins."""

    pin_to_boss_mm: float | None
    """Wall in the output plate between a pin bore and the bearing boss.

    ``None`` when the design does not say where the boss is. This is a
    constraint on the output plate, not the disc, and it pushes the bolt circle
    outward while the disc's rim pushes it in -- so it has to be checked with
    the others rather than after them.
    """

    output_hole_gap_mm: float
    """Circumferential gap between neighbouring output holes."""


def _least_web_mm(design: Design, phase_rad: float, profile: list[tuple[float, float]]) -> float:
    """Smallest gap between any output hole and the disc profile at one phase."""
    out = design.output
    hole_r = out.hole_radius_mm(design.geometry.eccentricity_mm)
    least = math.inf
    for angle in [a + phase_rad for a in out.hole_angles_rad()]:
        cx = out.bolt_circle_radius_mm * math.cos(angle)
        cy = out.bolt_circle_radius_mm * math.sin(angle)
        nearest = min(math.hypot(px - cx, py - cy) for px, py in profile)
        least = min(least, nearest - hole_r)
    return least


def _best_hole_phase(design: Design, samples: int = 61) -> tuple[float, float]:
    """Search one hole pitch for the phase that opens the tightest web most.

    Rotating the pattern is free, so it is worth knowing before moving the bolt
    circle. It does not always rescue a design: with ``gcd(n_pins, n_lobes) > 1``
    the holes cannot all sit on lobe crests at once, whatever the phase.
    """
    profile = cycloid.profile(design.geometry, samples_per_lobe=200).points
    pitch = 2 * math.pi / design.output.n_pins
    best_phase, best_web = 0.0, -math.inf
    for i in range(samples):
        phase = pitch * i / samples
        web = _least_web_mm(design, phase, profile)
        if web > best_web:
            best_phase, best_web = phase, web
    # Reported as an absolute phase, not a correction to the current one.
    return math.degrees(best_phase) + design.output.phase_deg, best_web


def clearances(design: Design) -> Clearances:
    geom = design.geometry
    out = design.output
    hole_r = out.hole_radius_mm(geom.eccentricity_mm)
    profile = cycloid.profile(geom, samples_per_lobe=200).points
    best_phase_deg, best_web = _best_hole_phase(design)
    return Clearances(
        hole_to_bore_mm=(out.bolt_circle_radius_mm - hole_r)
        - geom.center_bore_radius_mm,
        hole_to_root_mm=geom.disc_root_radius_mm
        - (out.bolt_circle_radius_mm + hole_r),
        hole_to_profile_mm=_least_web_mm(design, 0.0, profile),
        best_hole_phase_deg=best_phase_deg,
        best_hole_to_profile_mm=best_web,
        pin_to_boss_mm=(
            None
            if out.boss_radius_mm is None
            else out.bolt_circle_radius_mm - out.pin_radius_mm - out.boss_radius_mm
        ),
        ring_pin_gap_mm=2 * geom.pin_circle_radius_mm
        * math.sin(math.pi / geom.n_ring_pins)
        - 2 * geom.ring_pin_radius_mm,
        output_hole_gap_mm=2 * out.bolt_circle_radius_mm
        * math.sin(math.pi / out.n_pins)
        - 2 * hole_r,
    )


def checks(
    design: Design,
    limits: Limits | None = None,
    worst: loads.WorstCase | None = None,
) -> list[Check]:
    """Every design rule, evaluated. Order runs geometry first, then stress.

    Geometry comes first on purpose: an undercut profile cannot be built, and
    the contact figures computed on one are meaningless, so a reader who stops
    at the first failure still stops at the right place.
    """
    limits = limits or limits_from(design)
    worst = worst or loads.worst_case(design)
    geom = design.geometry
    gaps = clearances(design)

    margin = cycloid.undercut_margin(geom)
    disc_mat = design.materials["disc"]
    pin_mat = design.materials["ring_pin"]
    out_mat = design.materials.get("output_pin", pin_mat)
    disc_allow = disc_mat.contact_limit_mpa
    pin_allow = pin_mat.contact_limit_mpa
    out_allow = out_mat.contact_limit_mpa
    torque_margin = (
        design.peak_output_torque_nm / design.duty.target_output_torque_nm
        if design.duty.target_output_torque_nm > 0
        else math.inf
    )
    angle_deg = math.degrees(worst.working_pressure_angle_rad)

    env = design.envelope
    pin_outer = geom.pin_circle_radius_mm + geom.ring_pin_radius_mm
    stack = geom.n_discs * geom.disc_thickness_mm + limits.end_plate_allowance_mm

    result = [
        Check(
            "housing OD",
            2 * (pin_outer + env.housing_wall_mm),
            env.housing_od_mm,
            "mm",
            pin_outer <= env.max_pin_outer_radius_mm,
            f"pins reach r={pin_outer:.2f} mm",
        ),
        Check(
            "axial length",
            stack,
            env.max_length_mm,
            "mm",
            stack <= env.max_length_mm,
            f"{geom.n_discs} x {geom.disc_thickness_mm:.1f} mm disc"
            f"{'s' if geom.n_discs != 1 else ''} + plates",
        ),
        Check(
            "centre bore for wiring",
            geom.center_bore_radius_mm,
            env.required_bore_radius_mm,
            "mm",
            geom.center_bore_radius_mm >= env.required_bore_radius_mm,
            "bearing bore; the clear hole is smaller by the eccentric cam wall",
        ),
        Check(
            "curtate ratio K",
            geom.curtate_ratio,
            limits.max_curtate_ratio,
            "",
            limits.min_curtate_ratio <= geom.curtate_ratio <= limits.max_curtate_ratio,
            f"want {limits.min_curtate_ratio}-{limits.max_curtate_ratio}",
        ),
        Check(
            "undercut margin",
            margin,
            limits.min_undercut_margin,
            "x",
            margin >= limits.min_undercut_margin,
            f"max pin r = {cycloid.max_pin_radius(geom):.3f} mm",
        ),
        Check(
            "ring pin gap",
            gaps.ring_pin_gap_mm,
            limits.min_ring_pin_gap_mm,
            "mm",
            gaps.ring_pin_gap_mm >= limits.min_ring_pin_gap_mm,
            "between neighbouring pins",
        ),
        Check(
            "output hole gap",
            gaps.output_hole_gap_mm,
            limits.min_web_mm,
            "mm",
            gaps.output_hole_gap_mm >= limits.min_web_mm,
            "between neighbouring holes",
        ),
        Check(
            "web: hole to centre bore",
            gaps.hole_to_bore_mm,
            limits.min_web_mm,
            "mm",
            gaps.hole_to_bore_mm >= limits.min_web_mm,
            "",
        ),
        Check(
            "web: hole to disc profile",
            gaps.hole_to_profile_mm,
            limits.min_web_mm,
            "mm",
            gaps.hole_to_profile_mm >= limits.min_web_mm,
            (
                ""
                if gaps.hole_to_profile_mm >= limits.min_web_mm
                else f"rotating the holes {gaps.best_hole_phase_deg:.1f} deg gets "
                f"{gaps.best_hole_to_profile_mm:+.2f} mm"
            ),
        ),
        *(
            []
            if gaps.pin_to_boss_mm is None
            else [
                Check(
                    "web: output pin to boss",
                    gaps.pin_to_boss_mm,
                    limits.min_web_mm,
                    "mm",
                    gaps.pin_to_boss_mm >= limits.min_web_mm,
                    "in the output plate, not the disc",
                )
            ]
        ),
        Check(
            "pressure angle at peak load",
            angle_deg,
            limits.max_pressure_angle_deg,
            "deg",
            angle_deg <= limits.max_pressure_angle_deg,
            "raise K to reduce",
        ),
        Check(
            "ring contact stress vs disc",
            worst.max_ring_contact_pressure_mpa,
            disc_allow,
            "MPa",
            worst.max_ring_contact_pressure_mpa <= disc_allow,
            f"{disc_mat.name} -- {disc_mat.contact_criterion}",
        ),
        Check(
            "ring contact stress vs pin",
            worst.max_ring_contact_pressure_mpa,
            pin_allow,
            "MPa",
            worst.max_ring_contact_pressure_mpa <= pin_allow,
            f"{pin_mat.name} -- {pin_mat.contact_criterion}",
        ),
        Check(
            "output pin contact stress",
            worst.max_output_contact_pressure_mpa,
            out_allow,
            "MPa",
            worst.max_output_contact_pressure_mpa <= out_allow,
            "near-conformal, Hertz is approximate",
        ),
        Check(
            "torque margin over target",
            torque_margin,
            limits.min_torque_margin,
            "x",
            torque_margin >= limits.min_torque_margin,
            f"target {design.duty.target_output_torque_nm:.1f} N.m",
        ),
    ]
    if margin < 1.0:
        result = [
            c if c.name != "undercut margin" else Check(
                c.name, c.value, c.limit, c.unit, c.ok,
                "PROFILE SELF-INTERSECTS - stress figures below are meaningless",
            )
            for c in result
        ]
    return result


def render(design: Design, limits: Limits | None = None) -> str:
    """Full design report as plain text."""
    limits = limits or limits_from(design)
    geom = design.geometry
    out = design.output
    worst = loads.worst_case(design)
    gaps = clearances(design)
    results = checks(design, limits, worst)

    lines: list[str] = []
    add = lines.append

    add(f"{design.name}  rev {design.revision}")
    add("=" * 72)

    add("")
    add("KINEMATICS")
    add(f"  ring pins / lobes            {geom.n_ring_pins} / {geom.n_lobes}")
    add(f"  reduction                    {abs(geom.ratio):.0f}:1 (output counter-rotating)")
    add(f"  discs                        {geom.n_discs}"
        f"{' at 180 deg' if geom.n_discs == 2 else ''}")
    add(f"  max output speed             {design.max_output_speed_rpm:.0f} rpm")

    add("")
    add("TORQUE")
    add(f"  motor peak / continuous      {design.motor.peak_torque_nm:.2f}"
        f" / {design.motor.continuous_torque_nm:.2f} N.m")
    add(f"  output peak / continuous     {design.peak_output_torque_nm:.1f}"
        f" / {design.continuous_output_torque_nm:.1f} N.m"
        f"   (eta = {design.duty.efficiency:.2f})")
    add(f"  application target           {design.duty.target_output_torque_nm:.1f} N.m")
    add(f"  checked at                   {design.design_torque_nm:.1f} N.m"
        f"   (worst case x SF {design.duty.safety_factor:.2f})")

    add("")
    add("GEOMETRY")
    add(f"  curtate ratio K              {geom.curtate_ratio:.3f}")
    add(f"  pin circle radius            {geom.pin_circle_radius_mm:.2f} mm")
    add(f"  ring pin radius              {geom.ring_pin_radius_mm:.2f} mm"
        f"   (max before undercut {cycloid.max_pin_radius(geom):.3f} mm)")
    add(f"  eccentricity                 {geom.eccentricity_mm:.3f} mm"
        f"   (lobe height {2 * geom.eccentricity_mm:.3f} mm)")
    add(f"  pitch radii ring / disc      {geom.ring_pitch_radius_mm:.2f}"
        f" / {geom.disc_pitch_radius_mm:.2f} mm")
    add(f"  disc outer / root radius     {geom.disc_outer_radius_mm:.2f}"
        f" / {geom.disc_root_radius_mm:.2f} mm")
    add(f"  disc thickness               {geom.disc_thickness_mm:.2f} mm")
    add(f"  profile offset               {geom.profile_offset_mm:.3f} mm")
    add(f"  centre bore radius           {geom.center_bore_radius_mm:.2f} mm")
    add(f"  housing OD                   "
        f"{2 * (geom.pin_circle_radius_mm + geom.ring_pin_radius_mm + design.envelope.housing_wall_mm):.1f}"
        f" mm   (envelope {design.envelope.housing_od_mm:.1f} mm)")

    add("")
    add("OUTPUT COUPLING")
    add(f"  pins                         {out.n_pins} at r ="
        f" {out.pin_radius_mm:.2f} mm on a {out.bolt_circle_radius_mm:.2f} mm circle")
    add(f"  hole radius                  "
        f"{out.hole_radius_mm(geom.eccentricity_mm):.2f} mm  (pin + eccentricity)")

    add("")
    add("CLEARANCES")
    add(f"  ring pin to ring pin         {gaps.ring_pin_gap_mm:.2f} mm")
    add(f"  hole to hole                 {gaps.output_hole_gap_mm:.2f} mm")
    if gaps.pin_to_boss_mm is not None:
        add(f"  output pin to bearing boss   {gaps.pin_to_boss_mm:.2f} mm"
            "   (in the output plate)")
    add(f"  hole to centre bore          {gaps.hole_to_bore_mm:.2f} mm")
    add(f"  hole to lobe root, radial    {gaps.hole_to_root_mm:.2f} mm")
    add(f"  hole to profile, measured    {gaps.hole_to_profile_mm:.2f} mm"
        f"   (best phase {gaps.best_hole_phase_deg:.1f} deg:"
        f" {gaps.best_hole_to_profile_mm:+.2f} mm)")

    add("")
    add(f"LOADS  (per disc, at {design.design_torque_nm:.1f} N.m output)")
    add(f"  ring pins engaged            {worst.n_ring_pins_engaged} of {geom.n_ring_pins}")
    add(f"  peak ring pin force          {worst.max_ring_pin_force_n:.0f} N")
    add(f"  peak ring contact pressure   {worst.max_ring_contact_pressure_mpa:.0f} MPa")
    add(f"  ring contact patch width     {2 * worst.max_ring_half_width_mm:.3f} mm")
    add(f"  pressure angle at peak load  "
        f"{math.degrees(worst.working_pressure_angle_rad):.1f} deg")
    add(f"  output pins engaged          {worst.n_output_pins_engaged} of {out.n_pins}")
    add(f"  peak output pin force        {worst.max_output_pin_force_n:.0f} N")
    add(f"  peak output contact pressure {worst.max_output_contact_pressure_mpa:.0f} MPa")
    add(f"  eccentric bearing force      {worst.eccentric_bearing_force_n:.0f} N"
        "   <- size the input bearing to this")

    add("")
    add("CHECKS")
    for check in results:
        add(check.format())

    failed = [c for c in results if not c.ok]
    add("")
    add("-" * 72)
    if failed:
        add(f"{len(failed)} of {len(results)} checks FAILED: "
            + ", ".join(c.name for c in failed))
    else:
        add(f"all {len(results)} checks pass")

    add("")
    add("Assumptions: pin forces shared in proportion to lever arm about the")
    add("disc centre, only the loaded half engaging; Hertzian line contact over")
    add("the full disc thickness; quasi-static, no friction, no manufacturing")
    add("error. Treat the output as a starting point to verify by test, not as")
    add("a substitute for one.")
    return "\n".join(lines)
