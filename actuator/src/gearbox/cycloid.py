"""Geometry of the cycloidal disc.

The disc profile is the curve traced a fixed distance inside a hypotrochoid --
the "equidistant" curve. Rolling a circle of radius ``r2 = e*(Zp-1)`` inside a
circle of radius ``r1 = e*Zp`` generates the base trochoid; offsetting it
inward by the ring-pin radius gives a profile that stays in conjugate contact
with circular pins sitting on the pin circle.

Symbols used throughout, matching the cycloidal-drive literature:

======  ==========================================================
``Rp``  pin circle radius -- where the ring-pin centres sit
``Rr``  ring-pin radius
``e``   eccentricity of the input crank
``Zp``  number of ring pins; the disc has ``Zp - 1`` lobes
``K``   curtate ratio ``e*Zp/Rp``, equal to ``r1/Rp``
======  ==========================================================
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .config import Geometry

Point = tuple[float, float]


@dataclass(frozen=True)
class Profile:
    """A sampled disc profile plus the geometry it came from."""

    points: list[Point]
    geometry: Geometry

    @property
    def outer_radius_mm(self) -> float:
        return max(math.hypot(x, y) for x, y in self.points)

    @property
    def root_radius_mm(self) -> float:
        return min(math.hypot(x, y) for x, y in self.points)


def normal_angle(t: float, geom: Geometry) -> float:
    """Angle ``psi`` between the radius at parameter ``t`` and the surface normal.

    Derived by requiring the offset direction to be perpendicular to the base
    trochoid's tangent. With ``K < 1`` the denominator never reaches zero, so
    ``psi`` stays in the principal branch and the profile is generated without
    the wraparound artefacts a plain ``atan`` would introduce.
    """
    zp = geom.n_ring_pins
    k = geom.curtate_ratio
    phase = (1 - zp) * t
    return math.atan2(math.sin(phase), (1.0 / k) - math.cos(phase))


def base_point(t: float, geom: Geometry) -> Point:
    """Point on the base trochoid, before offsetting for the pin radius."""
    rp = geom.pin_circle_radius_mm
    e = geom.eccentricity_mm
    zp = geom.n_ring_pins
    return (
        rp * math.cos(t) - e * math.cos(zp * t),
        -rp * math.sin(t) + e * math.sin(zp * t),
    )


def profile_point(t: float, geom: Geometry) -> Point:
    """Point on the finished disc profile at parameter ``t``.

    ``profile_offset_mm`` is folded in as extra pin radius, which removes
    material uniformly along the normal -- the fit allowance you actually want
    rather than a radial scale that would distort the lobes.
    """
    rp = geom.pin_circle_radius_mm
    rr = geom.ring_pin_radius_mm + geom.profile_offset_mm
    e = geom.eccentricity_mm
    zp = geom.n_ring_pins
    psi = normal_angle(t, geom)
    return (
        rp * math.cos(t) - rr * math.cos(t + psi) - e * math.cos(zp * t),
        -rp * math.sin(t) + rr * math.sin(t + psi) + e * math.sin(zp * t),
    )


def profile(geom: Geometry, samples_per_lobe: int = 60) -> Profile:
    """Sample one full disc profile.

    Sampling is per lobe rather than per revolution so that resolution does not
    silently drop as the tooth count rises.
    """
    if samples_per_lobe < 8:
        raise ValueError("samples_per_lobe must be at least 8 to resolve a lobe")
    count = samples_per_lobe * geom.n_lobes
    step = 2 * math.pi / count
    return Profile(
        points=[profile_point(i * step, geom) for i in range(count)],
        geometry=geom,
    )


def base_curvature_radius(t: float, geom: Geometry) -> float:
    """Signed radius of curvature of the base trochoid at ``t``.

    The sign says which side the centre of curvature lies on. Positive means it
    sits outward of the curve -- the concave valleys between lobes, where
    offsetting inward for the pin radius only makes the curve blunter. Negative
    means it sits inward -- the convex lobe crests, where offsetting eats into
    the radius and is what can undercut.
    """
    rp = geom.pin_circle_radius_mm
    e = geom.eccentricity_mm
    zp = geom.n_ring_pins

    dx = -rp * math.sin(t) + e * zp * math.sin(zp * t)
    dy = -rp * math.cos(t) + e * zp * math.cos(zp * t)
    ddx = -rp * math.cos(t) + e * zp * zp * math.cos(zp * t)
    ddy = rp * math.sin(t) - e * zp * zp * math.sin(zp * t)

    speed_sq = dx * dx + dy * dy
    cross = dx * ddy - dy * ddx
    if abs(cross) < 1e-12:
        return math.inf
    return speed_sq ** 1.5 / cross


def max_pin_radius(geom: Geometry, samples: int = 4000) -> float:
    """Largest ring pin the profile tolerates before it undercuts.

    Only the convex crests constrain the pin: offsetting inward there shrinks
    the local radius of curvature, and once the pin exceeds it the offset curve
    folds back on itself. The concave valleys can be arbitrarily sharp -- the
    valley at the base of every lobe is far sharper than any usable pin, and
    counting it would reject perfectly good designs.

    One lobe is sampled because the profile repeats every ``2*pi/(Zp-1)``.
    """
    step = 2 * math.pi / geom.n_lobes / samples
    convex = [
        -rho
        for rho in (base_curvature_radius(i * step, geom) for i in range(samples + 1))
        if rho < 0
    ]
    if not convex:
        return math.inf
    return min(convex)


def undercut_margin(geom: Geometry, samples: int = 4000) -> float:
    """Ratio of the largest permissible pin to the one specified.

    Below 1.0 the profile self-intersects. The pin radius used here includes
    ``profile_offset_mm``, since removing material along the normal is
    geometrically identical to fitting a fatter pin.
    """
    effective = geom.ring_pin_radius_mm + geom.profile_offset_mm
    if effective <= 0:
        return math.inf
    return max_pin_radius(geom, samples=samples) / effective


@dataclass(frozen=True)
class Contact:
    """One ring-pin contact, in the frame where the eccentricity points along +x.

    The ring centre is the origin and the disc centre sits at ``(e, 0)``.
    """

    phi: float
    """Pin position measured from the eccentricity direction, radians."""

    point: Point
    """Where pin and disc touch."""

    normal: Point
    """Unit contact normal, pointing from the pitch point out to the pin centre."""

    moment_arm_mm: float
    """Signed lever arm of the contact force about the disc centre."""

    pressure_angle_rad: float


def contact(phi: float, geom: Geometry) -> Contact:
    """Geometry of the contact with the ring pin sitting ``phi`` off the eccentricity.

    By the law of gearing the common normal runs through the pitch point, and
    because the pin is a circle that normal also passes through the pin centre.
    Those two points fix the whole line of action, which is what makes the
    cycloidal drive tractable in closed form.
    """
    rp = geom.pin_circle_radius_mm
    rr = geom.ring_pin_radius_mm
    e = geom.eccentricity_mm
    k = geom.curtate_ratio

    pitch = (k * rp, 0.0)
    pin_center = (rp * math.cos(phi), rp * math.sin(phi))
    away = (pin_center[0] - pitch[0], pin_center[1] - pitch[1])
    away_len = math.hypot(*away)
    if away_len < 1e-12:
        # Pin sitting on the pitch point contributes no torque.
        return Contact(phi, pin_center, (1.0, 0.0), 0.0, math.pi / 2)
    normal = (away[0] / away_len, away[1] / away_len)

    point = (pin_center[0] - rr * normal[0], pin_center[1] - rr * normal[1])

    # A force's moment is the same taken anywhere on its line of action, so use
    # the pitch point: it reduces to r2 * sin(phi) / sqrt(1 + K^2 - 2K cos phi).
    lever = (pitch[0] - e, pitch[1])
    moment_arm = lever[0] * normal[1] - lever[1] * normal[0]

    radius = math.hypot(point[0] - e, point[1])
    if radius < 1e-12:
        angle = math.pi / 2
    else:
        angle = math.acos(min(1.0, abs(moment_arm) / radius))

    return Contact(phi, point, normal, moment_arm, angle)


def pressure_angle(phi: float, geom: Geometry) -> float:
    """Pressure angle at the ring pin ``phi`` off the eccentricity, radians."""
    return contact(phi, geom).pressure_angle_rad


def working_pressure_angle(geom: Geometry, samples: int = 2000) -> float:
    """Pressure angle where the drive is actually working hardest, radians.

    Quoting the worst pressure angle over every pin is not useful: it tends to
    90 degrees at the two pins entering and leaving mesh, and those carry
    essentially no load. The number that matters is the angle at the pin with
    the largest lever arm, which is where the peak contact force lands.
    """
    step = math.pi / (samples + 1)
    best = max(
        (contact((i + 1) * step, geom) for i in range(samples)),
        key=lambda c: c.moment_arm_mm,
    )
    return best.pressure_angle_rad


def max_moment_arm_mm(geom: Geometry, samples: int = 2000) -> float:
    """Largest lever arm any ring-pin contact can reach."""
    step = math.pi / (samples + 1)
    return max(
        contact((i + 1) * step, geom).moment_arm_mm for i in range(samples)
    )


def is_simple(prof: Profile) -> bool:
    """True when the profile winds once around the centre without folding back.

    An undercut profile loops inward, so its polar angle stops advancing
    monotonically. Testing the winding directly catches folds that a curvature
    bound can miss when sampling is coarse. Profiles are generated clockwise,
    so every step should be negative.
    """
    points = prof.points
    total = 0.0
    for i, (x, y) in enumerate(points):
        nx, ny = points[(i + 1) % len(points)]
        delta = math.atan2(ny, nx) - math.atan2(y, x)
        # Unwrap to the shortest equivalent step.
        delta = (delta + math.pi) % (2 * math.pi) - math.pi
        if delta > 0:
            return False
        total += delta
    return math.isclose(abs(total), 2 * math.pi, rel_tol=1e-6)
