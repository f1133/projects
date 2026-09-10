# Actuator — cycloidal gearbox

Design and analysis for the gearbox in the CAN joint node actuator. Three
joints, one gearbox each: a single-stage cycloidal drive, 24:1, inside a Ø48
envelope, with the wiring running down the middle.

The design lives in one file. `config/gearbox.toml` is the only input — the
checks, the report, the profile export and the CAD all read it, so the numbers
and the solid cannot drift apart.

## Quick start

```bash
cd actuator
python -m gearbox report          # full design report and checks
python -m gearbox check           # checks only; exit 1 if any fail
python -m gearbox profile -o out/disc.svg    # also .csv and .dxf
python -m gearbox bom             # mechanical bill of materials
```

Nothing above needs anything installed. The analysis is standard library only
(Python 3.11+, for `tomllib`), which is deliberate: the numbers should be
checkable on any machine without a toolchain.

CAD is the one exception:

```bash
pip install build123d
python cad/disc.py --out out --stl    # disc_a, disc_b and ring_housing, STEP + STL
```

Tests:

```bash
pip install pytest && python -m pytest
```

## One check fails on purpose

`python -m gearbox check` currently exits 1 on `ring contact stress vs disc`,
and only that. The disc material is a genuine open decision: at the placeholder
torque constant, a printed disc does not survive the contact stress in any
common filament. Setting the material to steel would make the check pass and
hide the finding, so it is left failing until the real motor is measured.
[docs/design-log.md](docs/design-log.md) has the numbers and the breakeven.

## What is here

```
config/gearbox.toml     every design input
config/bom.toml         mechanical BOM (the electronics BOM has no mechanical lines)
src/gearbox/
  config.py             inputs, derived quantities, validation
  cycloid.py            disc profile, curvature, undercut, contact geometry
  loads.py              pin forces, bearing loads, Hertzian contact stress
  report.py             design rules as pass/fail checks
  cli.py                the commands above
cad/disc.py             parametric solids, reads the same config
docs/requirements.md    what it has to do, and what is still unknown
docs/design-log.md      what was decided, with the numbers behind it
docs/decisions/         why cycloidal, and not the alternatives
tests/                  47 tests, mostly against closed forms
```

## How the design is checked

The load model shares each pin's force in proportion to its lever arm about the
disc centre, counting only the half of the ring that can push. That is an
assumption about compliance, not a derivation, so the tests check the things
that hold regardless of it:

- **Equilibrium closes.** Ring pins and output pins are sized independently
  from the same torque; their moments cancel to 1 part in 10⁶.
- **Power balances.** The eccentric bearing force across the eccentricity,
  times the eccentricity, equals the input torque exactly — even though nothing
  in the model imposes it. The bearing load falls out of force equilibrium and
  the reduction comes from the geometry.
- **It agrees with the textbook.** Output pin force lands within 0.2% of the
  standard `F_max = 4T/(zR)`.
- **The geometry matches closed forms.** Profile radii, lobe count, moment arm,
  and the result that the largest lever arm any ring pin can reach is exactly
  the disc's pitch radius, at `cos φ = K`.

## The one number that matters

`K = e·Zp/Rp`, the curtate ratio, is the pitch circle as a fraction of the pin
circle. It has to stay under 1 or the profile loops; 0.5–0.8 is usable. Raising
it lowers the pressure angle and eats the undercut margin. Almost every other
choice follows from it. This design sits at K = 0.75.
