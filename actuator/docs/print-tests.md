# Print tests

Three prints, in this order. Each answers a question that otherwise gets
answered by a failed assembly.

```bash
pip install build123d
python cad/coupons.py --config config/gearbox_688.toml --out out
```

## 1. `fit_gauge.stl` — what your printer actually makes

~20 cm³, one print, and every dimension downstream depends on it. Six bearing
seats and a bar of through-holes, each labelled with its nominal size.

| Feature | Sizes | For |
|---|---|---|
| Ø22 seats | 21.70 / 21.85 / 22.00 | 608ZZ press |
| Ø16 seats | 15.70 / 15.85 / 16.00 | 688ZZ press |
| Ø2.90–3.20 | 0.05 steps | Ø3 dowel, ring and output |
| Ø4.60 | — | output hole — measure it, do not assume it |
| Ø4.00, Ø4.20 | — | M3 heat-set insert |

Bearing seats are printed at full bearing width. A shallow test bore takes a
bearing more easily than a deep one and will tell you the fit is looser than it
is.

**Reading it.** Try the real part in each. The seat that takes firm thumb
pressure and then holds is your size; the difference from nominal is your
printer's offset, and it applies to every other bore in the gearbox. On the
hole bar, measure with pin gauges or the dowels themselves — what you want is
the number your printer produces for a nominal Ø3.00, not a pass/fail.

The Ø4.60 hole is worth measuring carefully. It is the output hole, and it is
pin + 2e exactly — the room the orbit needs, not clearance. A build that opened
its output holes by 0.2 mm measured 150 arcmin of backlash.

## 2. `mesh_disc_0XX.stl` + `mesh_ring.stl` — does the mesh turn

A 3 mm slice of the real disc and ring, about 2 cm³ each. With the ring dowels
dropped in you can roll the disc by hand, feel the mesh and measure backlash
without committing to a full-height set.

Three discs at 0.15, 0.20 and 0.25 mm of profile clearance. Print all three —
together they are under 7 cm³. The one that turns freely without rattling is
your clearance.

**These carry no output holes.** The profile depends only on the ring geometry,
so the same coupon is valid whichever output coupling you settle on, and the
backlash it measures carries over.

`mesh_ring_split.stl` is the same ring with the radial slot and clamp boss, so
the same print also answers whether the split ring flexes without cracking —
open question 19. Tighten in sixths of a turn, as the spec's tuning procedure
describes. The boss stands proud of Ø48; on the real housing it wants letting
into the wall.

## 3. `disc.stl` — the real disc

7 mm, full height, at the config's 0.20 mm clearance.

**This is the corrected geometry, not the spec's.** It needs a 688ZZ as the cam
bearing rather than a 608ZZ, and an output plate with its pins on a Ø26 circle
rotated 6°. The 6804ZZ output bearing is unchanged — it is a different position,
though its Ø20.05 boss is what sets Ø26 rather than anything tighter.
Printing it against the existing plan will not fit. The spec's own disc cannot
be printed as drawn — three of its six output holes cut through the rim. See
the design log.

## Two things the spec gets slightly wrong

**The pin pockets will not hold the pins.** The spec asks for Ø3.1 pin holes at
R19 with a Ø38.60 bore, and states a 2.94 mm mouth. Those three numbers do not
agree: Ø3.1 at that bore gives a 3.04 mm mouth, which is wider than the Ø3.0
dowel, so the pins drop out instead of snapping in. 2.94 is the figure for a
**Ø3.0** pocket, which is what the coupons use. Keep the bore and take the
pockets to Ø3.0, then let the fit gauge tell you what your printer needs on top.

**The bore is set by the pin, not by the disc.** Ø38.60 looks like it comes
from clearing the disc's Ø38.20 sweep, and the spec presents it that way. It
does not: it is `R19 + 1.5 − 1.2`, the radius that leaves 1.2 mm of the pin
embedded. Shrink the disc for clearance and the bore must not follow it, or the
pins stop being retained.
