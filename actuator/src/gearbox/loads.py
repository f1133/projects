"""Contact forces, bearing loads and Hertzian stress in the cycloidal stage.

Force model
-----------
Every ring pin touches the disc at once, so the load has to be shared out by
some assumption about compliance. The standard one, used here, is that contact
deflection grows with distance from the instantaneous centre, which makes each
pin force proportional to its own lever arm about the disc centre::

    F_i = F_max * a_i / a_max        T = sum(F_i * a_i)
    =>  F_max = T * a_max / sum(a_i**2)

Pins can only push, so only the half of the ring on the loaded side is counted.
The same reasoning gives the output pin forces, and there it reproduces the
textbook ``F_max = 4T/(z*R)`` in the many-pin limit.

Torque balance on one disc closes as: the ring pins feed in the output torque,
the output pins take it away, and the eccentric bearing carries whatever force
is left over -- it acts through the disc centre and so contributes no moment.

Sign convention
---------------
Everything is computed in the frame where the eccentricity points along +x,
with the ring centre at the origin and the disc centre at ``(e, 0)``. Advancing
the crank angle rotates the pins backwards through this frame. Only one torque
direction is worked out; reversing it mirrors the engaged set about the x axis
and leaves every magnitude unchanged.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from . import cycloid
from .config import Design, Material

MM_PER_M = 1000.0


def effective_modulus_mpa(a: Material, b: Material) -> float:
    """Contact modulus ``E*`` from ``1/E* = (1-v1^2)/E1 + (1-v2^2)/E2``."""
    compliance = (1 - a.poisson_ratio**2) / a.youngs_modulus_mpa + (
        1 - b.poisson_ratio**2
    ) / b.youngs_modulus_mpa
    return 1.0 / compliance


def hertz_line_pressure_mpa(
    force_n: float,
    length_mm: float,
    relative_radius_mm: float,
    e_star_mpa: float,
) -> float:
    """Peak pressure for a cylinder-on-cylinder line contact.

    ``p0 = sqrt(P' * E* / (pi * R))`` with ``P'`` the load per unit length.
    A negative or infinite relative radius means the surfaces conform rather
    than touch on a line, which Hertz theory does not cover; those return 0.0
    so callers can report "conformal" instead of a fabricated number.
    """
    if force_n <= 0 or length_mm <= 0:
        return 0.0
    if relative_radius_mm <= 0 or math.isinf(relative_radius_mm):
        return 0.0
    load_per_mm = force_n / length_mm
    return math.sqrt(load_per_mm * e_star_mpa / (math.pi * relative_radius_mm))


def hertz_half_width_mm(
    force_n: float,
    length_mm: float,
    relative_radius_mm: float,
    e_star_mpa: float,
) -> float:
    """Half-width of the contact patch, ``a = sqrt(4 P' R / (pi E*))``."""
    if force_n <= 0 or length_mm <= 0:
        return 0.0
    if relative_radius_mm <= 0 or math.isinf(relative_radius_mm):
        return 0.0
    load_per_mm = force_n / length_mm
    return math.sqrt(4 * load_per_mm * relative_radius_mm / (math.pi * e_star_mpa))


def profile_radius_mm(phi: float, design: Design) -> float:
    """Radius of curvature of the disc flank at the pin sitting ``phi`` off centre.

    Positive is convex, negative concave. The pin centres are exactly the base
    trochoid in the disc's own frame, and pin ``phi`` sits at trochoid parameter
    ``phi / n_lobes``, so the flank curvature follows from offsetting the base
    curvature by the pin radius: ``rho_flank = -(rho_base + Rr)``.
    """
    geom = design.geometry
    rr = geom.ring_pin_radius_mm + geom.profile_offset_mm
    rho_base = cycloid.base_curvature_radius(phi / geom.n_lobes, geom)
    if math.isinf(rho_base):
        return -math.inf
    return -(rho_base + rr)


def relative_radius_mm(phi: float, design: Design) -> float:
    """Hertz relative radius between a ring pin and the flank it touches.

    In the lobe valleys the flank cups the pin closely enough that the pair is
    effectively conformal; the reciprocal sum then goes to zero or negative and
    the caller gets ``inf``.
    """
    rr = design.geometry.ring_pin_radius_mm
    flank = profile_radius_mm(phi, design)
    if math.isinf(flank):
        return rr
    curvature_sum = 1.0 / rr + 1.0 / flank
    if curvature_sum <= 1e-12:
        return math.inf
    return 1.0 / curvature_sum


@dataclass(frozen=True)
class PinLoad:
    """Load on a single pin at one crank position."""

    index: int
    angle_rad: float
    """Position measured from the eccentricity direction."""

    force_n: float
    moment_arm_mm: float
    direction: tuple[float, float]
    """Unit vector of the force the pin applies to the disc."""

    contact_pressure_mpa: float
    contact_half_width_mm: float
    pressure_angle_rad: float

    @property
    def engaged(self) -> bool:
        return self.force_n > 0


def _share_load(arms: list[float], torque_nmm: float) -> list[float]:
    """Split a torque across levers with force proportional to lever arm."""
    engaged = [a for a in arms if a > 0]
    if not engaged:
        return [0.0] * len(arms)
    arm_max = max(engaged)
    sum_sq = sum(a * a for a in engaged)
    force_max = torque_nmm * arm_max / sum_sq
    return [force_max * a / arm_max if a > 0 else 0.0 for a in arms]


def ring_pin_loads(
    design: Design, crank_angle_rad: float, torque_nm: float | None = None
) -> list[PinLoad]:
    """Load on every ring pin at one crank position, for one disc.

    ``torque_nm`` is the torque on the whole output; it is divided across the
    discs before the pins share it out.
    """
    geom = design.geometry
    torque = design.design_torque_nm if torque_nm is None else torque_nm
    torque_nmm = torque * MM_PER_M / geom.n_discs

    contacts = [
        cycloid.contact(2 * math.pi * i / geom.n_ring_pins - crank_angle_rad, geom)
        for i in range(geom.n_ring_pins)
    ]
    # Pins push the disc inward, along -normal, so a pin drives the disc
    # forwards when its signed lever arm is negative.
    arms = [-c.moment_arm_mm for c in contacts]
    forces = _share_load(arms, torque_nmm)

    e_star = effective_modulus_mpa(
        design.materials["disc"], design.materials["ring_pin"]
    )
    length = geom.disc_thickness_mm

    loads: list[PinLoad] = []
    for i, (c, force) in enumerate(zip(contacts, forces)):
        radius = relative_radius_mm(c.phi, design)
        loads.append(
            PinLoad(
                index=i,
                angle_rad=c.phi,
                force_n=force,
                moment_arm_mm=arms[i],
                direction=(-c.normal[0], -c.normal[1]),
                contact_pressure_mpa=hertz_line_pressure_mpa(
                    force, length, radius, e_star
                ),
                contact_half_width_mm=hertz_half_width_mm(
                    force, length, radius, e_star
                ),
                pressure_angle_rad=c.pressure_angle_rad,
            )
        )
    return loads


def output_pin_loads(
    design: Design, crank_angle_rad: float, torque_nm: float | None = None
) -> list[PinLoad]:
    """Load on every output pin at one crank position, for one disc.

    The disc's motion relative to the output flange is a pure circular
    translation -- it orbits without turning relative to it -- so every engaged
    pin bears on its hole along the same direction, the eccentricity. That is
    what makes the lever arm simply the pin's offset across that direction.
    """
    geom = design.geometry
    out = design.output
    torque = design.design_torque_nm if torque_nm is None else torque_nm
    torque_nmm = torque * MM_PER_M / geom.n_discs

    angles = [a - crank_angle_rad for a in out.hole_angles_rad()]
    arms = [out.bolt_circle_radius_mm * math.sin(a) for a in angles]
    forces = _share_load(arms, torque_nmm)

    e_star = effective_modulus_mpa(
        design.materials["disc"],
        design.materials.get("output_pin", design.materials["ring_pin"]),
    )
    length = geom.disc_thickness_mm
    hole_r = out.hole_radius_mm(geom.eccentricity_mm)
    # Pin convex in a concave hole; the eccentricity is the whole clearance,
    # so the pair is close to conformal and the pressure stays modest.
    curvature_sum = 1.0 / out.pin_radius_mm - 1.0 / hole_r
    radius = 1.0 / curvature_sum if curvature_sum > 1e-12 else math.inf

    return [
        PinLoad(
            index=j,
            angle_rad=angles[j],
            force_n=forces[j],
            moment_arm_mm=arms[j],
            direction=(1.0, 0.0),
            contact_pressure_mpa=hertz_line_pressure_mpa(
                forces[j], length, radius, e_star
            ),
            contact_half_width_mm=hertz_half_width_mm(
                forces[j], length, radius, e_star
            ),
            pressure_angle_rad=0.0,
        )
        for j in range(out.n_pins)
    ]


def eccentric_bearing_force_n(
    design: Design, crank_angle_rad: float, torque_nm: float | None = None
) -> tuple[float, float]:
    """Force the input eccentric bearing carries, for one disc.

    Found by closing force equilibrium on the disc. The bearing acts through
    the disc centre, so it takes no share of the moment and simply absorbs
    whatever the ring and output pins do not cancel between them.
    """
    ring = ring_pin_loads(design, crank_angle_rad, torque_nm)
    out = output_pin_loads(design, crank_angle_rad, torque_nm)
    fx = sum(p.force_n * p.direction[0] for p in ring + out)
    fy = sum(p.force_n * p.direction[1] for p in ring + out)
    return (-fx, -fy)


def moment_residual_nmm(
    design: Design, crank_angle_rad: float, torque_nm: float | None = None
) -> float:
    """Net moment on the disc about its own centre; should be zero.

    Kept as a live check rather than a comment: the ring and output pins are
    sized independently, and this is what proves they actually balance.
    """
    ring = ring_pin_loads(design, crank_angle_rad, torque_nm)
    out = output_pin_loads(design, crank_angle_rad, torque_nm)
    return sum(p.force_n * p.moment_arm_mm for p in ring) - sum(
        p.force_n * p.moment_arm_mm for p in out
    )


@dataclass(frozen=True)
class WorstCase:
    """Peak loads found by sweeping the crank through one pin pitch.

    A single crank position understates the loads: as the pins walk through
    the mesh the share-out ripples, and the peak is what has to be designed to.
    """

    crank_angle_rad: float
    max_ring_pin_force_n: float
    max_ring_contact_pressure_mpa: float
    max_ring_half_width_mm: float
    working_pressure_angle_rad: float
    n_ring_pins_engaged: int
    max_output_pin_force_n: float
    max_output_contact_pressure_mpa: float
    n_output_pins_engaged: int
    eccentric_bearing_force_n: float

    @property
    def eccentric_bearing_force_per_disc_n(self) -> float:
        return self.eccentric_bearing_force_n


def worst_case(
    design: Design, samples: int = 180, torque_nm: float | None = None
) -> WorstCase:
    """Sweep one pin pitch and report the worst load found.

    Sweeping a single pitch is enough: the mesh repeats every ``2*pi/Zp`` of
    crank rotation.
    """
    if samples < 1:
        raise ValueError("samples must be at least 1")
    geom = design.geometry
    span = 2 * math.pi / geom.n_ring_pins
    best: WorstCase | None = None

    for i in range(samples):
        angle = span * i / samples
        ring = ring_pin_loads(design, angle, torque_nm)
        out = output_pin_loads(design, angle, torque_nm)
        peak = max(ring, key=lambda p: p.force_n)
        bearing = eccentric_bearing_force_n(design, angle, torque_nm)
        candidate = WorstCase(
            crank_angle_rad=angle,
            max_ring_pin_force_n=peak.force_n,
            max_ring_contact_pressure_mpa=max(
                p.contact_pressure_mpa for p in ring
            ),
            max_ring_half_width_mm=max(p.contact_half_width_mm for p in ring),
            working_pressure_angle_rad=peak.pressure_angle_rad,
            n_ring_pins_engaged=sum(1 for p in ring if p.engaged),
            max_output_pin_force_n=max(p.force_n for p in out),
            max_output_contact_pressure_mpa=max(
                p.contact_pressure_mpa for p in out
            ),
            n_output_pins_engaged=sum(1 for p in out if p.engaged),
            eccentric_bearing_force_n=math.hypot(*bearing),
        )
        if best is None or (
            candidate.max_ring_contact_pressure_mpa
            > best.max_ring_contact_pressure_mpa
        ):
            best = candidate

    assert best is not None  # guaranteed by the samples >= 1 check above
    return best
