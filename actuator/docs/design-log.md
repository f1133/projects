# Design log

Newest first. Each entry records what changed and what the numbers said, so a
decision can be re-argued later without re-deriving it.

## 2026-09-10 — first sizing inside the Ø48 envelope

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
