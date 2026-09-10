# Design log

Newest first. Each entry records what changed and what the numbers said, so a
decision can be re-argued later without re-deriving it.

## 2026-09-10 — reconciled against the Juno starter pack

The Juno pack arrived with a mature v2 gearbox spec
(`03_mechanical/V2_SPEC.md`) and the real motor. Both of the previous entry's
headline findings were built on a guessed motor, and one of them was also
measured against the wrong limit. This entry supersedes it.

**The design here is now Juno v2, transcribed.** 15:1, 16 pins, R19, e = 0.80,
one 7 mm disc, split adjustable ring. The previous 24:1 geometry was invented
from the electronics BOM alone and is gone; the spec is upstream and this repo
is downstream of it.

**The motor is a 2804 gimbal at 0.06 N·m, not the 0.125 N·m assumed.** Kt is
0.024 N·m/A at the driver's 2.5 A, not 0.05. Every load scales with this, so
the previous entry's numbers were roughly twice what they should have been.

**Comparing Hertzian peak pressure against tensile strength was wrong.** A
Hertzian contact is triaxially confined, so it carries well past uniaxial
yield: for a 2D line contact the greatest shear is `0.300·p₀` below the
surface, and by Tresca first yield arrives at

```
p₀ = σ_y / (2 × 0.300) = 1.67 σ_y
```

For PLA at σ_y = 55 MPa that is 92 MPa, not 55. The previous entry's "a printed
disc does not survive" was the product of both errors together. Corrected, on
Juno v2 geometry at the design torque, the disc runs **61 MPa against a 92 MPa
limit — a 1.5× margin. It passes.** `Material` now takes either an explicit
surface-fatigue allowable (right for steel) or a yield strength it derives the
contact limit from (right for polymers, which have no fatigue data), and the
report names which criterion it used.

**The output holes break out of the disc.** This is the one real finding, and
it blocks printing.

The spec puts 6 × Ø4.6 holes on a Ø30 PCD. The lobe roots sit at R16.55, and a
hole at R15 reaches R17.30 — so a hole centred on a root **breaks through the
rim by 0.75 mm**. Three of the six do: 15 lobes against 6 holes share a factor
of 3, so the pattern repeats every 120° with holes alternately on a root and
between roots. The SCAD places them at 0°, 60°, 120° … and generates a root at
0°, so it is the as-drawn phase, not a hypothetical one.

Rotating the pattern does not rescue it. Swept over a full hole pitch, the best
phase still leaves −0.35 mm. With `gcd(6, 15) = 3` the holes cannot all sit on
crests at any rotation.

Nor can the bolt circle simply move, while the cam bearing is a 608:

| PCD | web to lobes | web to the Ø21.85 bore |
|---|---|---|
| Ø30 (as drawn) | −0.33 | +1.77 |
| Ø28 | +0.56 | +0.77 |
| Ø26 | +1.49 | −0.23 |

There is no PCD that clears both. The SCAD comment says as much without drawing
the conclusion — `out_pin_pcd = 30.0; // pushed out from 24: the 608 bore is
22 mm`. Pushing the holes out to clear the bearing pushed them into the rim.

The way out is a smaller cam bearing, which the spec already lists for an
unrelated reason (height). A **688ZZ (8 × 16 × 5)** drops the bore to Ø16 and
frees the PCD to come in to Ø26, giving **+1.49 mm to the lobes and +2.70 mm to
the bore** — both clear, and 2 mm shorter. Keep the disc at 7 mm rather than
matching the bearing width: at 5 mm the contact patch shortens and peak pressure
rises from 61 to 71 MPa. A 5 mm bearing in a 7 mm disc just needs a counterbore.

**Forces run 2–3× the spec's figures, and the spec's conclusion survives
anyway.** At 0.68 N·m on v2 geometry:

| | spec | here |
|---|---|---|
| ring pin peak | 4.4 N | 14.3 N |
| output pin peak | 15 N | 27.1 N |
| cam bearing | 57 N | 92.1 N |

The cam bearing figure is diagnostic: 57 N is exactly `T_in/e`, the tangential
component alone. The ring pins also push a large net force outward, and closing
force equilibrium adds a 72 N radial term. The output pin figure looks like
`T/(3R)` — half the pins each at full lever arm — where sharing the load in
proportion to lever arm gives the textbook `4T/(zR)`, about twice as much.

None of this changes the spec's judgement. At 92 N the 608 still has ~15× on its
static rating, so **"nothing in this gearbox is close to a strength limit" holds**
— the margins are 8–50× rather than 20–150×. The conclusion that every change
should buy accuracy rather than strength is unaffected.

**On the 0.71 MPa figure.** That is projected bearing pressure, `F/(d·t)`, and
this repo computes 0.68 MPa for the same thing — the two agree. What does not
follow is comparing it to ~55 MPa: that limit belongs to the Hertzian peak,
which is 61 MPa here, not to a projected pressure. Different quantities, and the
78× margin is an artefact of pairing them. The real margin is 1.5×, which is
still fine, and the number worth watching is not strength but bedding-in: at
61 MPa the flanks will yield locally and conform, and that shows up as backlash
growth — which is exactly what v2 set out to protect.

**Two soft flags, neither blocking.** The pressure angle at peak load is 46.3°
against a 45° rule of thumb — a consequence of choosing K = 0.674 to match
builds known to print, which is the better reason. And the web from the output
holes to the centre bore is 1.77 mm against a 2 mm minimum; the 688ZZ change
opens it to 2.70 mm anyway.


## 2026-09-10 — first sizing inside the Ø48 envelope

> **Superseded by the entry above.** Written before the Juno pack was available,
> from the electronics BOM alone. The geometry is gone, the motor was a guess at
> roughly twice the real torque, and the contact-stress conclusion used the wrong
> limit. Kept because the packaging reasoning and the eccentric-bearing result
> still hold, and because the reasoning behind a wrong answer is worth keeping.

**Starting point.** The electronics BOM fixes Ø48, a 2.5 A driver ceiling and a
wiring path through the joint. Those three between them determine most of the
gearbox.

**Pin circle.** Ø48 outside, 2.5 mm of housing wall and a 1.5 mm pin radius
leave `Rp = 48/2 − 2.5 − 1.5 = 20.0 mm`. Everything else is packed inside that.

**Ratio.** 25 ring pins gives 24:1. The ceiling is pin collision, not anything
subtle: 25 pins of Ø3 on a 20 mm circle leave 2.0 mm between neighbours, and
much above 30 pins they touch.

**Eccentricity.** Swept `e` at fixed ratio:

| e | K | undercut margin | pressure angle | max bore r |
|---|---|---|---|---|
| 0.50 | 0.625 | 2.00 | 49.6° | 11.00 |
| 0.55 | 0.688 | 1.86 | 44.6° | 10.85 |
| **0.60** | **0.750** | **1.69** | **39.1°** | **10.70** |
| 0.64 | 0.800 | 1.54 | 34.5° | 10.58 |

Took `e = 0.60`. Below it the pressure angle passes 45°; above it the undercut
margin and the bore both shrink for little further gain. The trade is the whole
design in one number — K buys pressure angle and pays in margin.

**Eccentric bearing, 6801 → 6701.** With a 6801 (Ø21 OD) the webs between the
output holes and their neighbours came out at 1.7 mm and 1.5 mm, both under the
2 mm minimum. A 6701 (12 × 18 × 4) frees 1.5 mm of radius and both webs pass at
2.6 mm and 2.1 mm. Still to do: check the 6701's dynamic load rating against the
262 N below and work out an L10 life. A 4 mm wide bearing is not obviously
enough, and if it is not, the way out is a wider bearing and a longer stack
rather than a bigger one.

**The eccentric bearing is the most loaded part in the gearbox.** Worth stating
plainly because the obvious estimate is wrong. Sizing it as
`input torque / eccentricity` counts only the force across the eccentricity and
gives 133 N. The ring pins also push a large net force radially outward, and
closing force equilibrium on the disc puts the true load at 262 N — 1.97× as
much. The tangential part still equals `T/ratio/e` exactly, which is how the
model is checked (`test_power_balances_through_the_eccentric`).

**A printed disc does not survive.** The project's fab route is the owned
printer, so a printed disc was the default. At the placeholder `Kt = 0.05
N·m/A` it fails on Hertzian contact stress for every common filament:

| disc material | peak contact stress | allowable | |
|---|---|---|---|
| printed PLA | 78 MPa | 55 | fail, 1.42× |
| printed PETG-CF | 90 MPa | 60 | fail, 1.50× |
| printed nylon-CF | 103 MPa | 90 | fail, 1.15× |
| 7075 aluminium | 300 MPa | 350 | pass |
| hardened steel | 410 MPa | 1100 | pass |

Contact stress goes with the square root of torque, so the breakeven is
sharper than it looks — a printed disc is fine below roughly:

| filament | max Kt | ≈ Kv | output torque there |
|---|---|---|---|
| PLA | 0.025 N·m/A | 333 rpm/V | 1.27 N·m |
| PETG-CF | 0.022 N·m/A | 370 rpm/V | 1.14 N·m |
| nylon-CF | 0.038 N·m/A | 218 rpm/V | 1.94 N·m |

**This is the one check left failing on purpose.** `python -m gearbox check`
exits 1 on `ring contact stress vs disc` and nothing else. The material is a
real open decision, and quietly setting it to steel would hide the finding.
Resolve it by measuring the motor: if `Kt` lands under ~0.022 N·m/A a printed
PETG-CF disc works as drawn, and if it lands higher the disc has to be cut from
aluminium or steel — or the safety factor and target torque revisited.

Everything above rests on a guessed `Kt`. Re-run the report once the real motor
is known; the conclusion could move either way.

**Gaps found in the electronics BOM.** It has no mechanical lines at all — no
bearings, dowels, cam, housing or fasteners — which is why `config/bom.toml`
exists. It is also missing a diametric magnet for the AS5600; those boards
often ship without one, and the encoder does not work without it.
