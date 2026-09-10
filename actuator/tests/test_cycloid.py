"""Geometry tests.

Most of these check the sampled profile against a closed form derived
independently, rather than against a stored number -- a regression test that
only compares to last week's output cannot tell you the maths was ever right.
"""

import math

import pytest
from gearbox import cycloid
from gearbox.config import Geometry


def make_geom(**overrides) -> Geometry:
    base = dict(
        pin_circle_radius_mm=20.0,
        n_ring_pins=25,
        ring_pin_radius_mm=1.5,
        eccentricity_mm=0.6,
        disc_thickness_mm=6.0,
        n_discs=2,
        profile_offset_mm=0.0,
        center_bore_radius_mm=9.0,
    )
    base.update(overrides)
    return Geometry(**base)


def test_reduction_is_the_lobe_count(geom):
    assert geom.n_lobes == geom.n_ring_pins - 1
    assert abs(geom.ratio) == geom.n_lobes


def test_curtate_ratio_is_the_pitch_radius_fraction(geom):
    assert geom.curtate_ratio == pytest.approx(
        geom.ring_pitch_radius_mm / geom.pin_circle_radius_mm
    )
    # Pitch circles roll on each other: they differ by exactly one eccentricity.
    assert geom.ring_pitch_radius_mm - geom.disc_pitch_radius_mm == pytest.approx(
        geom.eccentricity_mm
    )


def test_base_trochoid_matches_closed_form_radius(geom):
    """r(t)^2 = Rp^2 + e^2 - 2*Rp*e*cos((Zp-1)t), which also fixes the lobe count."""
    for i in range(60):
        t = i * 0.11
        x, y = cycloid.base_point(t, geom)
        expected = math.sqrt(
            geom.pin_circle_radius_mm**2
            + geom.eccentricity_mm**2
            - 2
            * geom.pin_circle_radius_mm
            * geom.eccentricity_mm
            * math.cos(geom.n_lobes * t)
        )
        assert math.hypot(x, y) == pytest.approx(expected, abs=1e-12)


def test_profile_has_one_lobe_per_reduction_step(geom):
    prof = cycloid.profile(geom, samples_per_lobe=80)
    radii = [math.hypot(x, y) for x, y in prof.points]
    n = len(radii)
    peaks = sum(
        1 for i in range(n) if radii[i] > radii[i - 1] and radii[i] >= radii[(i + 1) % n]
    )
    assert peaks == geom.n_lobes


def test_profile_spans_the_expected_radii(geom):
    prof = cycloid.profile(geom, samples_per_lobe=120)
    assert prof.outer_radius_mm == pytest.approx(geom.disc_outer_radius_mm, abs=1e-9)
    assert prof.root_radius_mm == pytest.approx(geom.disc_root_radius_mm, abs=1e-9)
    assert geom.disc_outer_radius_mm - geom.disc_root_radius_mm == pytest.approx(
        2 * geom.eccentricity_mm
    )


def test_profile_offset_removes_material_uniformly(geom):
    offset = 0.2
    shrunk = make_geom(
        pin_circle_radius_mm=geom.pin_circle_radius_mm,
        n_ring_pins=geom.n_ring_pins,
        ring_pin_radius_mm=geom.ring_pin_radius_mm,
        eccentricity_mm=geom.eccentricity_mm,
        profile_offset_mm=offset,
    )
    for i in range(40):
        t = i * 0.07
        x0, y0 = cycloid.profile_point(t, geom)
        x1, y1 = cycloid.profile_point(t, shrunk)
        assert math.dist((x0, y0), (x1, y1)) == pytest.approx(offset, abs=1e-9)


def test_undercut_limit_is_where_the_profile_stops_being_simple():
    """The curvature bound and the winding test have to agree on the boundary."""
    geom = make_geom(ring_pin_radius_mm=1.5)
    limit = cycloid.max_pin_radius(geom)

    safe = make_geom(ring_pin_radius_mm=limit * 0.9)
    assert cycloid.undercut_margin(safe) > 1.0
    assert cycloid.is_simple(cycloid.profile(safe, samples_per_lobe=200))

    undercut = make_geom(ring_pin_radius_mm=limit * 1.15)
    assert cycloid.undercut_margin(undercut) < 1.0
    assert not cycloid.is_simple(cycloid.profile(undercut, samples_per_lobe=200))


def test_committed_design_does_not_undercut(geom):
    assert cycloid.undercut_margin(geom) > 1.0
    assert cycloid.is_simple(cycloid.profile(geom, samples_per_lobe=200))


def test_moment_arm_matches_closed_form(geom):
    """l(phi) = r2 * sin(phi) / sqrt(1 + K^2 - 2K cos phi)."""
    k = geom.curtate_ratio
    r2 = geom.disc_pitch_radius_mm
    for i in range(1, 60):
        phi = i * 0.1
        expected = (
            r2 * math.sin(phi) / math.sqrt(1 + k * k - 2 * k * math.cos(phi))
        )
        assert cycloid.contact(phi, geom).moment_arm_mm == pytest.approx(
            expected, abs=1e-9
        )


def test_moment_arm_peaks_at_the_disc_pitch_radius(geom):
    """Setting dl/dphi = 0 gives cos(phi) = K, where l is exactly r2.

    A neat consequence: the best lever arm a ring pin can ever have is the
    disc's own pitch radius, no matter how the drive is proportioned.
    """
    assert cycloid.max_moment_arm_mm(geom) == pytest.approx(
        geom.disc_pitch_radius_mm, rel=1e-6
    )
    best = cycloid.contact(math.acos(geom.curtate_ratio), geom)
    assert best.moment_arm_mm == pytest.approx(geom.disc_pitch_radius_mm, abs=1e-9)


def test_pin_angle_maps_to_trochoid_parameter(geom):
    """Pin at angle phi touches the flank at trochoid parameter phi/n_lobes.

    This is what lets the Hertz calculation find the local flank curvature, so
    it is worth pinning down rather than trusting.
    """
    e = geom.eccentricity_mm
    for phi in (0.2, 0.7, 1.2, 1.9, 2.5, 3.0):
        c = cycloid.contact(phi, geom)
        from_contact = math.hypot(c.point[0] - e, c.point[1])
        x, y = cycloid.profile_point(phi / geom.n_lobes, geom)
        assert from_contact == pytest.approx(math.hypot(x, y), abs=1e-9)


def test_contact_normal_passes_through_the_pitch_point(geom):
    """The law of gearing, which every force in loads.py rests on."""
    pitch = (geom.curtate_ratio * geom.pin_circle_radius_mm, 0.0)
    for phi in (0.3, 1.1, 2.2, 2.9):
        c = cycloid.contact(phi, geom)
        to_pitch = (pitch[0] - c.point[0], pitch[1] - c.point[1])
        cross = to_pitch[0] * c.normal[1] - to_pitch[1] * c.normal[0]
        assert cross == pytest.approx(0.0, abs=1e-9)


def test_pressure_angle_falls_as_curtate_ratio_rises(geom):
    """The core trade: more eccentricity buys a better angle, at the cost of margin."""
    angles = [
        cycloid.working_pressure_angle(make_geom(eccentricity_mm=e))
        for e in (0.45, 0.55, 0.65)
    ]
    assert angles == sorted(angles, reverse=True)


def test_profile_needs_enough_samples_to_resolve_a_lobe(geom):
    with pytest.raises(ValueError):
        cycloid.profile(geom, samples_per_lobe=4)
