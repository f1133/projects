"""Load model tests.

The force share-out is an assumption, not a derivation, so these tests check
the things that must hold regardless of it: equilibrium closes, power balances,
and the result agrees with the textbook formula where one exists.
"""

import math

import pytest
from gearbox import loads
from gearbox.config import Material

CRANKS = (0.0, 0.031, 0.07, 0.11, 0.2)


def test_moment_equilibrium_closes(design):
    """Ring pins put in exactly what the output pins take out.

    Both sets are sized independently from the same torque, so this is a real
    check that the two models are consistent rather than a tautology.
    """
    scale = design.design_torque_nm * 1000
    for crank in CRANKS:
        assert loads.moment_residual_nmm(design, crank) == pytest.approx(
            0.0, abs=1e-6 * scale
        )


def test_power_balances_through_the_eccentric(design):
    """Bearing force across the eccentricity times e is the input torque.

    Nothing in the model imposes this: the bearing force falls out of force
    equilibrium, and the reduction comes from the geometry. That they agree is
    the strongest evidence the force model is right.
    """
    torque_per_disc_nmm = (
        design.design_torque_nm * 1000 / design.geometry.n_discs
    )
    expected = torque_per_disc_nmm / abs(design.geometry.ratio)
    for crank in CRANKS:
        fx, fy = loads.eccentric_bearing_force_n(design, crank)
        assert abs(fy) * design.geometry.eccentricity_mm == pytest.approx(
            expected, rel=1e-9
        )


def test_bearing_carries_far_more_than_the_tangential_component(design):
    """The radial share is real, and it is what sizes the input bearing.

    Estimating the eccentric bearing load as torque over eccentricity, which
    only accounts for the tangential part, understates it roughly twofold.
    """
    fx, fy = loads.eccentric_bearing_force_n(design, 0.0)
    assert abs(fx) > abs(fy)
    assert math.hypot(fx, fy) > 1.5 * abs(fy)


def test_output_pin_force_matches_the_textbook_formula(design):
    """Independent check against F_max = 4T/(z*R), the standard approximation.

    That formula assumes exactly half the pins engage and the sum of sin^2
    averages to z/4; discretely it is close but not exact, hence the tolerance.
    """
    out = design.output
    torque_per_disc_nmm = design.design_torque_nm * 1000 / design.geometry.n_discs
    textbook = 4 * torque_per_disc_nmm / (out.n_pins * out.bolt_circle_radius_mm)
    peak = max(
        max(p.force_n for p in loads.output_pin_loads(design, crank))
        for crank in CRANKS
    )
    assert peak == pytest.approx(textbook, rel=0.15)


def test_only_the_loaded_half_engages(design):
    """Pins can push but not pull, so at most half the ring is ever in play."""
    for crank in CRANKS:
        ring = loads.ring_pin_loads(design, crank)
        engaged = [p for p in ring if p.engaged]
        assert 0 < len(engaged) <= design.geometry.n_ring_pins // 2 + 1
        assert all(p.force_n == 0 for p in ring if not p.engaged)


def test_forces_scale_linearly_with_torque(design):
    a = max(p.force_n for p in loads.ring_pin_loads(design, 0.05, torque_nm=1.0))
    b = max(p.force_n for p in loads.ring_pin_loads(design, 0.05, torque_nm=3.0))
    assert b == pytest.approx(3 * a, rel=1e-12)


def test_contact_pressure_scales_with_the_square_root_of_torque(design):
    """Hertzian, so doubling the torque costs about 41% more pressure, not 100%."""
    a = loads.worst_case(design, samples=24, torque_nm=1.0)
    b = loads.worst_case(design, samples=24, torque_nm=4.0)
    assert b.max_ring_contact_pressure_mpa == pytest.approx(
        2 * a.max_ring_contact_pressure_mpa, rel=1e-9
    )


def test_hertz_matches_the_closed_form():
    """p0 = sqrt(P' E* / (pi R)) for a line contact."""
    steel = Material("steel", 200000.0, 0.29, 1100.0)
    e_star = loads.effective_modulus_mpa(steel, steel)
    assert e_star == pytest.approx(200000 / (2 * (1 - 0.29**2)))

    force, length, radius = 500.0, 10.0, 4.0
    expected = math.sqrt((force / length) * e_star / (math.pi * radius))
    assert loads.hertz_line_pressure_mpa(force, length, radius, e_star) == pytest.approx(
        expected
    )


def test_hertz_declines_to_guess_at_conformal_contact():
    """A negative or infinite relative radius is outside Hertz theory.

    Returning zero lets the report say "conformal" instead of printing a
    number that looks like a stress but is not one.
    """
    steel = Material("steel", 200000.0, 0.29, 1100.0)
    e_star = loads.effective_modulus_mpa(steel, steel)
    assert loads.hertz_line_pressure_mpa(500.0, 10.0, -4.0, e_star) == 0.0
    assert loads.hertz_line_pressure_mpa(500.0, 10.0, math.inf, e_star) == 0.0
    assert loads.hertz_line_pressure_mpa(0.0, 10.0, 4.0, e_star) == 0.0


def test_flank_curvature_follows_the_offset_rule(design):
    """rho_flank = -(rho_base + Rr): convex at the crests, concave in the roots."""
    from gearbox import cycloid

    geom = design.geometry
    for phi in (0.2, 0.9, 1.7, 2.6):
        rho_base = cycloid.base_curvature_radius(phi / geom.n_lobes, geom)
        assert loads.profile_radius_mm(phi, design) == pytest.approx(
            -(rho_base + geom.ring_pin_radius_mm)
        )


def test_worst_case_is_at_least_as_bad_as_any_sample(design):
    worst = loads.worst_case(design, samples=90)
    span = 2 * math.pi / design.geometry.n_ring_pins
    for i in range(30):
        crank = span * i / 30
        peak = max(p.contact_pressure_mpa for p in loads.ring_pin_loads(design, crank))
        assert peak <= worst.max_ring_contact_pressure_mpa * (1 + 1e-9)


def test_worst_case_needs_at_least_one_sample(design):
    with pytest.raises(ValueError):
        loads.worst_case(design, samples=0)
