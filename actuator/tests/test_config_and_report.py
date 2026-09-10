"""Validation, reporting and command line tests."""

import math
import tomllib
from copy import deepcopy
from pathlib import Path

import pytest
from gearbox import bom, cli, config, report

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture()
def raw():
    with (ROOT / "config" / "gearbox.toml").open("rb") as handle:
        return tomllib.load(handle)


def build(raw, **sections):
    """Rebuild the committed design with some tables overridden."""
    edited = deepcopy(raw)
    for table, values in sections.items():
        edited[table.replace("__", ".")].update(values)
    return config.from_dict(edited)


def test_committed_design_loads(design):
    assert design.geometry.n_ring_pins > 0
    assert design.materials["disc"].youngs_modulus_mpa > 0


def test_torque_chain(design):
    motor = design.motor
    assert motor.peak_torque_nm == pytest.approx(
        motor.kt_nm_per_a * motor.peak_current_a
    )
    assert design.peak_output_torque_nm == pytest.approx(
        motor.peak_torque_nm * abs(design.geometry.ratio) * design.duty.efficiency
    )
    # Checked at the worse of what the motor can do and what the arm asks for.
    assert design.design_torque_nm == pytest.approx(
        max(design.peak_output_torque_nm, design.duty.target_output_torque_nm)
        * design.duty.safety_factor
    )


def test_output_speed_is_input_over_ratio(design):
    assert design.max_output_speed_rpm == pytest.approx(
        design.motor.max_speed_rpm / abs(design.geometry.ratio)
    )


def test_rejects_curtate_ratio_at_or_above_one(raw):
    """K = 1 is the cusp limit: the profile collapses into self-intersection."""
    with pytest.raises(config.ConfigError, match="curtate ratio"):
        build(raw, gearbox={"eccentricity_mm": 1.25})


def test_rejects_ring_pins_that_would_overlap(raw):
    with pytest.raises(config.ConfigError, match="ring pins overlap"):
        build(raw, gearbox={"n_ring_pins": 90, "eccentricity_mm": 0.1})


def test_rejects_output_holes_that_would_overlap(raw):
    with pytest.raises(config.ConfigError, match="output holes overlap"):
        build(raw, output={"n_pins": 40})


def test_rejects_a_bore_too_small_for_the_wiring(raw):
    with pytest.raises(config.ConfigError, match="wiring needs"):
        build(raw, gearbox={"center_bore_radius_mm": 1.0})


def test_rejects_lobe_roots_inside_the_bore(raw):
    with pytest.raises(config.ConfigError, match="centre bore"):
        build(raw, gearbox={"center_bore_radius_mm": 19.0})


def test_rejects_a_missing_material(raw):
    edited = deepcopy(raw)
    del edited["materials"]["disc"]
    with pytest.raises(config.ConfigError, match="materials.disc"):
        config.from_dict(edited)


def test_reports_which_key_is_missing(raw):
    edited = deepcopy(raw)
    del edited["gearbox"]["n_ring_pins"]
    with pytest.raises(config.ConfigError, match="n_ring_pins"):
        config.from_dict(edited)


def test_clearances_are_measured_from_the_hole_edges(design):
    gaps = report.clearances(design)
    out = design.output
    hole_r = out.hole_radius_mm(design.geometry.eccentricity_mm)
    assert gaps.hole_to_bore_mm == pytest.approx(
        out.bolt_circle_radius_mm - hole_r - design.geometry.center_bore_radius_mm
    )
    assert gaps.hole_to_root_mm == pytest.approx(
        design.geometry.disc_root_radius_mm - out.bolt_circle_radius_mm - hole_r
    )


def test_every_check_is_evaluated(design):
    results = report.checks(design)
    assert len(results) >= 12
    assert all(isinstance(c.ok, bool) for c in results)
    assert {"housing OD", "undercut margin", "ring contact stress vs disc"} <= {
        c.name for c in results
    }


def test_an_undercut_design_says_so_before_quoting_stress(raw):
    """Stress on a profile that cannot exist is meaningless and must be flagged.

    A fat pin alone cannot undercut this design -- the pins would collide on
    the pin circle first, and validation rejects that -- so the eccentricity is
    raised as well to bring the undercut limit down below the pin.
    """
    design = build(
        raw, gearbox={"ring_pin_radius_mm": 2.5, "eccentricity_mm": 1.1}
    )
    results = report.checks(design)
    undercut = next(c for c in results if c.name == "undercut margin")
    assert not undercut.ok
    assert "SELF-INTERSECTS" in undercut.note
    assert results.index(undercut) < next(
        i for i, c in enumerate(results) if "contact stress" in c.name
    )


def test_tightening_the_envelope_fails_the_housing_check(raw):
    design = build(raw, envelope={"housing_od_mm": 36.0})
    housing = next(c for c in report.checks(design) if c.name == "housing OD")
    assert not housing.ok


def test_report_renders_the_whole_design(design):
    text = report.render(design)
    for heading in ("KINEMATICS", "TORQUE", "GEOMETRY", "CLEARANCES", "LOADS", "CHECKS"):
        assert heading in text
    assert design.name in text
    assert "eccentric bearing force" in text


def test_bom_totals_across_every_joint():
    parts = bom.load(ROOT / "config" / "bom.toml")
    assert parts.gearboxes >= 1
    discs = next(p for p in parts.parts if p.ref == "DISC")
    assert discs.qty_for(parts.gearboxes) == discs.qty_per_gearbox * parts.gearboxes
    assert "Mechanical BOM" in bom.render(parts)


def test_cli_check_fails_loudly_when_a_check_fails(design, capsys, monkeypatch):
    monkeypatch.chdir(ROOT)
    code = cli.main(["check"])
    printed = capsys.readouterr().out
    assert ("FAIL" in printed) == (code == 1)


def test_cli_exports_every_supported_format(tmp_path, monkeypatch):
    monkeypatch.chdir(ROOT)
    for suffix in (".csv", ".svg", ".dxf"):
        out = tmp_path / f"disc{suffix}"
        assert cli.main(["profile", "-o", str(out), "-n", "30"]) == 0
        assert out.stat().st_size > 0


def test_cli_rejects_an_unknown_format(tmp_path, monkeypatch):
    monkeypatch.chdir(ROOT)
    with pytest.raises(SystemExit, match="cannot write"):
        cli.main(["profile", "-o", str(tmp_path / "disc.obj")])


def test_cli_reports_a_missing_design_file():
    with pytest.raises(SystemExit, match="no design file"):
        cli.main(["-c", "nope.toml", "report"])


def test_exported_csv_is_the_profile(tmp_path, monkeypatch, design):
    monkeypatch.chdir(ROOT)
    out = tmp_path / "disc.csv"
    cli.main(["profile", "-o", str(out), "-n", "40"])
    rows = out.read_text().strip().splitlines()
    assert rows[0] == "x_mm,y_mm"
    points = [tuple(float(v) for v in row.split(",")) for row in rows[1:]]
    assert len(points) == 40 * design.geometry.n_lobes
    radii = [math.hypot(x, y) for x, y in points]
    assert max(radii) == pytest.approx(design.geometry.disc_outer_radius_mm, abs=1e-6)


def test_contact_limit_prefers_an_explicit_fatigue_allowable():
    steel = config.Material("steel", 200000.0, 0.29, allowable_contact_stress_mpa=1100.0)
    assert steel.contact_limit_mpa == 1100.0
    assert "fatigue" in steel.contact_criterion


def test_contact_limit_derives_first_yield_when_only_strength_is_known():
    """A confined Hertzian contact carries well past uniaxial yield.

    Comparing peak pressure straight against tensile strength is the mistake
    this exists to prevent -- it understates a polymer's capacity by 1.67x.
    """
    pla = config.Material("PLA", 3500.0, 0.36, yield_strength_mpa=55.0)
    assert pla.contact_limit_mpa == pytest.approx(1.6667 * 55.0, rel=1e-3)
    assert pla.contact_limit_mpa > 55.0
    assert "yield" in pla.contact_criterion


def test_a_material_with_neither_limit_is_rejected(raw):
    edited = deepcopy(raw)
    edited["materials"]["disc"] = {
        "name": "mystery",
        "youngs_modulus_mpa": 3000.0,
        "poisson_ratio": 0.35,
    }
    with pytest.raises(config.ConfigError, match="yield_strength_mpa"):
        config.from_dict(edited)


def test_web_check_measures_the_real_gap_not_just_the_radial_one(design):
    """Whether a hole hits a lobe root depends on how the patterns line up.

    The radial figure assumes the worst; this measures it. They agree only when
    a hole really does sit over a root.
    """
    gaps = report.clearances(design)
    assert gaps.hole_to_profile_mm >= gaps.hole_to_root_mm - 1e-9
    assert gaps.best_hole_to_profile_mm >= gaps.hole_to_profile_mm - 1e-9


def test_rotating_the_hole_pattern_cannot_always_rescue_it(design):
    """With gcd(n_pins, n_lobes) > 1 the holes cannot all sit on crests.

    The committed Juno v2 geometry is such a case: 6 holes against 15 lobes
    share a factor of 3, so three holes always land on roots and no phase
    lifts the tightest web above zero. The bolt circle has to move instead.
    """
    out, geom = design.output, design.geometry
    assert math.gcd(out.n_pins, geom.n_lobes) > 1
    gaps = report.clearances(design)
    assert gaps.best_hole_to_profile_mm < 0


def test_moving_the_bolt_circle_in_does_open_the_web(raw):
    """The actual remedy, once rotation is exhausted."""
    tight = build(raw, output={"bolt_circle_radius_mm": 15.0})
    roomy = build(raw, output={"bolt_circle_radius_mm": 13.0})
    assert report.clearances(tight).hole_to_profile_mm < 0
    assert report.clearances(roomy).hole_to_profile_mm > 1.0


@pytest.mark.parametrize(
    "argv",
    [
        ["-c", "nope.toml", "report"],
        ["report", "-c", "nope.toml"],
    ],
)
def test_config_flag_works_on_either_side_of_the_subcommand(argv):
    """Both orders read naturally, so both have to reach the same file.

    A subparser default would be applied after the top-level flag is parsed and
    silently overwrite it, which is why the shared option suppresses its own.
    """
    with pytest.raises(SystemExit, match="no design file"):
        cli.main(argv)


def test_limits_can_be_overridden_per_design(raw):
    edited = deepcopy(raw)
    edited["limits"] = {"max_pressure_angle_deg": 90.0}
    design = config.from_dict(edited)
    assert report.limits_from(design).max_pressure_angle_deg == 90.0
    angle = next(
        c for c in report.checks(design) if c.name == "pressure angle at peak load"
    )
    assert angle.ok


def test_a_typo_in_limits_is_an_error_not_a_silent_no_op(raw):
    edited = deepcopy(raw)
    edited["limits"] = {"max_presure_angle_deg": 90.0}
    with pytest.raises(config.ConfigError, match="unknown key in .limits."):
        report.checks(config.from_dict(edited))
