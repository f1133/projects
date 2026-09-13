# vendor

Source files that the KiCad projects are generated from. These are inputs, not
outputs — nothing here is edited by the generators.

| File | Purpose |
|---|---|
| `build_console.html` | Source of truth. Schematic tab defines connectivity; BOM tab defines parts. |
| `SimpleFOC_Mini.kicad_sym` | Symbol for the SimpleFOC Mini driver module, which mounts on female headers. |

## Adding them

From a clone of this repository, on this branch:

```sh
cp /c/Users/<you>/.../01_tracker/build_console.html  hardware/vendor/
cp /c/Users/<you>/.../SimpleFOC_Mini.kicad_sym       hardware/vendor/
git add hardware/vendor
git commit -m "Add build console and SimpleFOC Mini symbol"
git push
```

## Still needed

A **footprint** for the SimpleFOC Mini. The `.kicad_sym` gives the symbol and
pin names but not the physical geometry of the female headers it sits on. If a
`.kicad_mod` exists, drop it here too; otherwise it is built from the module
outline and header positions and must be checked against the real part with a
1:1 printout before ordering.
