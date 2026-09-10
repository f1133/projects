"""Design inputs for the cycloidal gearbox, loaded from a TOML file.

Everything the rest of the package needs comes from here. Units are
millimetres, newtons, megapascals and amperes unless a field name says
otherwise; the suffix on each TOML key states the unit so the file stays
readable without cross-referencing this module.
"""

from __future__ import annotations

import math
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class ConfigError(ValueError):
    """Raised when a design file is missing keys or is self-inconsistent."""


@dataclass(frozen=True)
class Motor:
    """Motor and the driver in front of it.

    ``peak_current_a`` is whichever is lower, what the motor can take or what
    the driver can deliver -- the gearbox only ever sees the smaller of the two,
    and sizing to the motor alone overstates the torque it will actually meet.
    """

    part: str
    kt_nm_per_a: float
    peak_current_a: float
    continuous_current_a: float
    max_speed_rpm: float
    driver: str = ""

    @property
    def peak_torque_nm(self) -> float:
        return self.kt_nm_per_a * self.peak_current_a

    @property
    def continuous_torque_nm(self) -> float:
        return self.kt_nm_per_a * self.continuous_current_a


# For a 2D line contact the greatest shear sits below the surface at
# tau_max = 0.300 * p0, so by Tresca the first yield arrives at
# p0 = sigma_y / (2 * 0.300). Johnson, Contact Mechanics, ch. 4.
HERTZ_YIELD_FACTOR = 1.0 / (2 * 0.300)


@dataclass(frozen=True)
class Material:
    """A material, and the criterion its contact stress is judged by.

    The two criteria are not interchangeable, and picking the wrong one is an
    easy way to be badly wrong in either direction:

    ``allowable_contact_stress_mpa``
        A surface-fatigue allowable, the usual way to rate steel gears. Give it
        where such a figure exists; it already accounts for repeated loading.

    ``yield_strength_mpa``
        Used when no fatigue allowable exists, as for printed polymers. The
        contact limit is *not* the yield strength: a Hertzian contact is
        triaxially confined, so first yield does not arrive until the peak
        pressure reaches about 1.67 times it. Comparing peak pressure straight
        against tensile strength understates the capacity by that factor.
    """

    name: str
    youngs_modulus_mpa: float
    poisson_ratio: float
    allowable_contact_stress_mpa: float | None = None
    yield_strength_mpa: float | None = None

    @property
    def contact_limit_mpa(self) -> float:
        """Peak Hertzian pressure this material may see."""
        if self.allowable_contact_stress_mpa is not None:
            return self.allowable_contact_stress_mpa
        if self.yield_strength_mpa is not None:
            return HERTZ_YIELD_FACTOR * self.yield_strength_mpa
        raise ConfigError(
            f"material '{self.name}' gives neither allowable_contact_stress_mpa "
            "nor yield_strength_mpa, so its contact stress cannot be judged"
        )

    @property
    def contact_criterion(self) -> str:
        """Which of the two limits is in play, for the report to name."""
        if self.allowable_contact_stress_mpa is not None:
            return "surface fatigue allowable"
        return f"first yield, {HERTZ_YIELD_FACTOR:.2f} x sigma_y"


@dataclass(frozen=True)
class Geometry:
    """Cycloidal stage geometry.

    ``pin_circle_radius`` is where the ring-pin *centres* sit, not the bore
    they run in. ``profile_offset`` shrinks the disc radially: positive
    values remove material, which is how you dial in backlash or a printer's
    elephant-foot allowance without touching the nominal geometry.
    """

    pin_circle_radius_mm: float
    n_ring_pins: int
    ring_pin_radius_mm: float
    eccentricity_mm: float
    disc_thickness_mm: float
    n_discs: int
    profile_offset_mm: float
    center_bore_radius_mm: float

    @property
    def n_lobes(self) -> int:
        """Lobes on the disc. One fewer than the ring pins gives ratio = n_lobes."""
        return self.n_ring_pins - 1

    @property
    def ratio(self) -> float:
        """Reduction with the ring fixed and output taken from the disc.

        The disc turns backwards relative to the input, which the sign records.
        """
        return -float(self.n_lobes)

    @property
    def curtate_ratio(self) -> float:
        """K = e*Zp/Rp -- the single most important number in the design.

        K is also the pitch-circle radius as a fraction of the pin circle. It
        must stay below 1 for the trochoid to close without looping; 0.5-0.8
        is the usable band, and higher K trades a lower pressure angle for
        thinner, more highly stressed lobes.
        """
        return self.eccentricity_mm * self.n_ring_pins / self.pin_circle_radius_mm

    @property
    def ring_pitch_radius_mm(self) -> float:
        """Pitch circle of the ring: r1 = e*Zp."""
        return self.eccentricity_mm * self.n_ring_pins

    @property
    def disc_pitch_radius_mm(self) -> float:
        """Pitch circle of the disc: r2 = e*(Zp-1) = r1 - e."""
        return self.eccentricity_mm * self.n_lobes

    @property
    def disc_outer_radius_mm(self) -> float:
        """Largest radius the disc reaches, measured from the disc centre."""
        return (
            self.pin_circle_radius_mm
            - self.ring_pin_radius_mm
            + self.eccentricity_mm
            - self.profile_offset_mm
        )

    @property
    def disc_root_radius_mm(self) -> float:
        """Smallest radius of the lobe roots, from the disc centre."""
        return (
            self.pin_circle_radius_mm
            - self.ring_pin_radius_mm
            - self.eccentricity_mm
            - self.profile_offset_mm
        )


@dataclass(frozen=True)
class OutputCoupling:
    """Pin-and-hole (Oldham-style) coupling that pulls rotation off the disc.

    Each hole is one eccentricity larger in radius than its pin, which is what
    lets the disc orbit while the pin circle stays put.
    """

    n_pins: int
    pin_radius_mm: float
    bolt_circle_radius_mm: float
    phase_deg: float = 0.0
    """Rotation of the hole pattern relative to the lobes.

    Free to choose, and worth choosing: the profile has a lobe root at 0
    degrees, so at phase 0 a hole may sit right over one. Where the hole and
    lobe counts share a factor this cannot be avoided entirely, but the phase
    still decides how bad the worst hole is.
    """

    def hole_radius_mm(self, eccentricity_mm: float) -> float:
        return self.pin_radius_mm + eccentricity_mm

    def hole_angles_rad(self) -> list[float]:
        """Angular position of every output hole, phase included."""
        import math

        return [
            2 * math.pi * j / self.n_pins + math.radians(self.phase_deg)
            for j in range(self.n_pins)
        ]


@dataclass(frozen=True)
class Envelope:
    """The space the gearbox has to live inside.

    A cycloidal stage is easy to design if you ignore packaging and nearly
    impossible once you do not, so the envelope is a first-class input here
    rather than something checked at the end.
    """

    housing_od_mm: float
    housing_wall_mm: float
    """Material between the outermost ring pin and the outside of the housing."""

    required_bore_radius_mm: float
    """Clear radius that must stay open down the middle for wiring."""

    max_length_mm: float

    @property
    def max_pin_outer_radius_mm(self) -> float:
        """Furthest a ring pin's outer surface may sit from the axis."""
        return self.housing_od_mm / 2 - self.housing_wall_mm


@dataclass(frozen=True)
class Duty:
    efficiency: float
    safety_factor: float
    target_output_torque_nm: float


@dataclass(frozen=True)
class Design:
    name: str
    revision: str
    motor: Motor
    geometry: Geometry
    output: OutputCoupling
    envelope: Envelope
    duty: Duty
    materials: dict[str, Material] = field(default_factory=dict)
    limits: dict[str, float] = field(default_factory=dict)
    """Threshold overrides from the design file, applied over the defaults."""

    @property
    def peak_output_torque_nm(self) -> float:
        """What the motor can actually put on the output shaft."""
        return (
            self.motor.peak_torque_nm
            * abs(self.geometry.ratio)
            * self.duty.efficiency
        )

    @property
    def continuous_output_torque_nm(self) -> float:
        return (
            self.motor.continuous_torque_nm
            * abs(self.geometry.ratio)
            * self.duty.efficiency
        )

    @property
    def design_torque_nm(self) -> float:
        """Torque the stress checks are run at.

        The larger of what the motor can deliver and what the application asks
        for, then multiplied by the safety factor -- a gearbox has to survive
        a stalled motor whether or not the duty cycle calls for it.
        """
        return (
            max(self.peak_output_torque_nm, self.duty.target_output_torque_nm)
            * self.duty.safety_factor
        )

    @property
    def max_output_speed_rpm(self) -> float:
        return self.motor.max_speed_rpm / abs(self.geometry.ratio)


def _require(table: dict[str, Any], key: str, where: str) -> Any:
    if key not in table:
        raise ConfigError(f"missing key '{key}' in [{where}]")
    return table[key]


def _material(table: dict[str, Any], where: str) -> Material:
    allowable = table.get("allowable_contact_stress_mpa")
    yield_strength = table.get("yield_strength_mpa")
    if allowable is None and yield_strength is None:
        raise ConfigError(
            f"[{where}] needs allowable_contact_stress_mpa or yield_strength_mpa"
        )
    return Material(
        name=str(_require(table, "name", where)),
        youngs_modulus_mpa=float(_require(table, "youngs_modulus_mpa", where)),
        poisson_ratio=float(_require(table, "poisson_ratio", where)),
        allowable_contact_stress_mpa=(
            None if allowable is None else float(allowable)
        ),
        yield_strength_mpa=(
            None if yield_strength is None else float(yield_strength)
        ),
    )


def from_dict(raw: dict[str, Any]) -> Design:
    """Build a :class:`Design` from already-parsed TOML."""
    meta = raw.get("meta", {})
    motor_t = _require(raw, "motor", "root")
    geom_t = _require(raw, "gearbox", "root")
    out_t = _require(raw, "output", "root")
    env_t = _require(raw, "envelope", "root")
    duty_t = _require(raw, "duty", "root")
    mats_t = _require(raw, "materials", "root")

    design = Design(
        name=str(meta.get("name", "unnamed")),
        revision=str(meta.get("revision", "0")),
        motor=Motor(
            part=str(_require(motor_t, "part", "motor")),
            kt_nm_per_a=float(_require(motor_t, "kt_nm_per_a", "motor")),
            peak_current_a=float(_require(motor_t, "peak_current_a", "motor")),
            continuous_current_a=float(
                _require(motor_t, "continuous_current_a", "motor")
            ),
            max_speed_rpm=float(_require(motor_t, "max_speed_rpm", "motor")),
            driver=str(motor_t.get("driver", "")),
        ),
        geometry=Geometry(
            pin_circle_radius_mm=float(
                _require(geom_t, "pin_circle_radius_mm", "gearbox")
            ),
            n_ring_pins=int(_require(geom_t, "n_ring_pins", "gearbox")),
            ring_pin_radius_mm=float(
                _require(geom_t, "ring_pin_radius_mm", "gearbox")
            ),
            eccentricity_mm=float(_require(geom_t, "eccentricity_mm", "gearbox")),
            disc_thickness_mm=float(_require(geom_t, "disc_thickness_mm", "gearbox")),
            n_discs=int(_require(geom_t, "n_discs", "gearbox")),
            profile_offset_mm=float(geom_t.get("profile_offset_mm", 0.0)),
            center_bore_radius_mm=float(
                _require(geom_t, "center_bore_radius_mm", "gearbox")
            ),
        ),
        output=OutputCoupling(
            n_pins=int(_require(out_t, "n_pins", "output")),
            pin_radius_mm=float(_require(out_t, "pin_radius_mm", "output")),
            bolt_circle_radius_mm=float(
                _require(out_t, "bolt_circle_radius_mm", "output")
            ),
            phase_deg=float(out_t.get("phase_deg", 0.0)),
        ),
        envelope=Envelope(
            housing_od_mm=float(_require(env_t, "housing_od_mm", "envelope")),
            housing_wall_mm=float(_require(env_t, "housing_wall_mm", "envelope")),
            required_bore_radius_mm=float(
                _require(env_t, "required_bore_radius_mm", "envelope")
            ),
            max_length_mm=float(_require(env_t, "max_length_mm", "envelope")),
        ),
        duty=Duty(
            efficiency=float(_require(duty_t, "efficiency", "duty")),
            safety_factor=float(_require(duty_t, "safety_factor", "duty")),
            target_output_torque_nm=float(
                _require(duty_t, "target_output_torque_nm", "duty")
            ),
        ),
        materials={
            key: _material(value, f"materials.{key}")
            for key, value in mats_t.items()
        },
        limits={k: float(v) for k, v in raw.get("limits", {}).items()},
    )
    _validate(design)
    return design


def load(path: str | Path) -> Design:
    """Read and validate a design TOML file."""
    path = Path(path)
    with path.open("rb") as handle:
        raw = tomllib.load(handle)
    try:
        return from_dict(raw)
    except ConfigError as exc:
        raise ConfigError(f"{path}: {exc}") from exc


def _validate(design: Design) -> None:
    """Reject designs that cannot exist before any analysis runs on them."""
    geom = design.geometry
    if geom.n_ring_pins < 3:
        raise ConfigError("gearbox.n_ring_pins must be at least 3")
    if geom.n_discs < 1:
        raise ConfigError("gearbox.n_discs must be at least 1")
    for label, value in (
        ("pin_circle_radius_mm", geom.pin_circle_radius_mm),
        ("ring_pin_radius_mm", geom.ring_pin_radius_mm),
        ("eccentricity_mm", geom.eccentricity_mm),
        ("disc_thickness_mm", geom.disc_thickness_mm),
        ("center_bore_radius_mm", geom.center_bore_radius_mm),
    ):
        if value <= 0:
            raise ConfigError(f"gearbox.{label} must be positive")
    if geom.curtate_ratio >= 1.0:
        raise ConfigError(
            f"curtate ratio K = e*Zp/Rp = {geom.curtate_ratio:.3f} must be < 1; "
            "reduce eccentricity_mm or increase pin_circle_radius_mm"
        )
    if geom.disc_root_radius_mm <= geom.center_bore_radius_mm:
        raise ConfigError(
            "lobe roots fall inside the centre bore: "
            f"root r={geom.disc_root_radius_mm:.2f} mm vs bore "
            f"r={geom.center_bore_radius_mm:.2f} mm"
        )

    # Ring pins must not touch each other around the pin circle.
    pin_gap = 2 * geom.pin_circle_radius_mm * math.sin(
        math.pi / geom.n_ring_pins
    ) - 2 * geom.ring_pin_radius_mm
    if pin_gap <= 0:
        raise ConfigError(
            f"ring pins overlap: {geom.n_ring_pins} pins of r="
            f"{geom.ring_pin_radius_mm} mm do not fit on a "
            f"{geom.pin_circle_radius_mm} mm circle"
        )

    out = design.output
    if out.n_pins < 3:
        raise ConfigError("output.n_pins must be at least 3")
    if out.pin_radius_mm <= 0 or out.bolt_circle_radius_mm <= 0:
        raise ConfigError("output pin radius and bolt circle must be positive")
    hole_r = out.hole_radius_mm(geom.eccentricity_mm)
    hole_gap = 2 * out.bolt_circle_radius_mm * math.sin(
        math.pi / out.n_pins
    ) - 2 * hole_r
    if hole_gap <= 0:
        raise ConfigError(
            f"output holes overlap: {out.n_pins} holes of r={hole_r:.2f} mm do "
            f"not fit on a {out.bolt_circle_radius_mm} mm circle"
        )

    env = design.envelope
    if env.housing_od_mm <= 0 or env.housing_wall_mm < 0:
        raise ConfigError("envelope.housing_od_mm must be positive")
    if geom.center_bore_radius_mm < env.required_bore_radius_mm:
        raise ConfigError(
            f"centre bore r={geom.center_bore_radius_mm:.2f} mm is smaller than "
            f"the {env.required_bore_radius_mm:.2f} mm the wiring needs"
        )

    if not 0 < design.duty.efficiency <= 1:
        raise ConfigError("duty.efficiency must be in (0, 1]")
    if design.duty.safety_factor < 1:
        raise ConfigError("duty.safety_factor must be at least 1")
    for required in ("disc", "ring_pin"):
        if required not in design.materials:
            raise ConfigError(f"missing [materials.{required}] table")
