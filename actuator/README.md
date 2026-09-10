# Actuator — cycloidal gearbox

Checks for the Juno joint actuator's gearbox: a single-stage cycloidal drive,
15:1, inside a Ø48 envelope. Three joints, one gearbox each.

**The upstream design is Juno's `03_mechanical/V2_SPEC.md`.** `config/gearbox.toml`
is that spec transcribed, so the checks run against what will actually be
printed. If the two disagree, the spec wins until someone reconciles them.

Everything here reads that one file — the checks, the report, the profile export
and the CAD — so the numbers and the solid cannot drift apart.

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

## What it currently says

`python -m gearbox check` exits 1. One of the failures blocks printing:

**`web: hole to disc profile` is −0.75 mm.** The six output holes on the Ø30 PCD
reach past the lobe roots, and three of them cut through the rim. 15 lobes
against 6 holes share a factor of 3, so no rotation of the pattern fixes it —
the best phase still leaves −0.35 mm. And while the cam bearing is a 608, no
bolt circle clears both the rim and the Ø21.85 bore. A **688ZZ (8 × 16 × 5)**
with the PCD at Ø26 clears both by 1.5 mm and 2.7 mm, and is 2 mm shorter.
Keep the disc at 7 mm: at 5 mm the peak contact pressure rises from 61 to
71 MPa.

The rest are soft. The pressure angle is 46.3° against a 45° rule of thumb, a
consequence of choosing K = 0.674 to match builds known to print. The web to the
centre bore is 1.77 mm against a 2 mm minimum, which the 688ZZ change fixes
anyway. And the torque margin reads 0.993× because the spec's own 0.68 N·m and
its 0.06 × 15 × 0.75 are the same number rounded differently.

Contact stress **passes** at 61 MPa against 92. See
[docs/design-log.md](docs/design-log.md) for why that limit is 92 and not 55.

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
tests/                  54 tests, mostly against closed forms
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

## Two numbers that matter

`K = e·Zp/Rp`, the curtate ratio, is the pitch circle as a fraction of the pin
circle. It has to stay under 1 or the profile loops; 0.5–0.8 is usable. Raising
it lowers the pressure angle and eats the undercut margin. Juno v2 sits at
K = 0.674, chosen to match two third-party builds known to print and work.

`1.67 σ_y` is the Hertzian peak pressure at which a material first yields under
a line contact — the contact is triaxially confined, so it carries well past
uniaxial yield. Comparing peak pressure straight against tensile strength
understates a polymer's capacity by that factor, and comparing it against
*projected bearing pressure* compares two different quantities entirely. The
report names which criterion each material is judged by.
