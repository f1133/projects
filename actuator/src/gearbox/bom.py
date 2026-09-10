"""The gearbox's mechanical bill of materials.

Kept separate from the electronics BOM, which lives in the project's shared
spreadsheet and covers the CAN node boards. Nothing mechanical appears there,
so this file is where bearings, dowels, fasteners and printed parts are tracked.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Part:
    ref: str
    description: str
    qty_per_gearbox: int
    source: str = ""
    note: str = ""
    have: bool = False

    def qty_for(self, gearboxes: int) -> int:
        return self.qty_per_gearbox * gearboxes


@dataclass(frozen=True)
class Bom:
    gearboxes: int
    parts: list[Part]

    def outstanding(self) -> list[Part]:
        return [p for p in self.parts if not p.have]


def load(path: str | Path) -> Bom:
    path = Path(path)
    with path.open("rb") as handle:
        raw = tomllib.load(handle)
    return Bom(
        gearboxes=int(raw.get("meta", {}).get("gearboxes", 1)),
        parts=[
            Part(
                ref=str(entry["ref"]),
                description=str(entry["description"]),
                qty_per_gearbox=int(entry["qty_per_gearbox"]),
                source=str(entry.get("source", "")),
                note=str(entry.get("note", "")),
                have=bool(entry.get("have", False)),
            )
            for entry in raw.get("part", [])
        ],
    )


def render(bom: Bom) -> str:
    """Plain-text table, totalled across every gearbox in the build."""
    lines = [
        f"Mechanical BOM  ({bom.gearboxes} gearbox"
        f"{'es' if bom.gearboxes != 1 else ''})",
        "=" * 78,
        f"  {'ref':<10} {'qty/ea':>6} {'total':>6}  {'have':<5} description",
        "  " + "-" * 74,
    ]
    for part in bom.parts:
        lines.append(
            f"  {part.ref:<10} {part.qty_per_gearbox:>6} "
            f"{part.qty_for(bom.gearboxes):>6}  {'yes' if part.have else 'no':<5} "
            f"{part.description}"
        )
        if part.note:
            lines.append(f"  {'':<10} {'':>6} {'':>6}  {'':<5} {part.note}")

    outstanding = bom.outstanding()
    lines.append("")
    lines.append(
        f"{len(outstanding)} of {len(bom.parts)} lines still to buy"
        if outstanding
        else "everything on the bench"
    )
    return "\n".join(lines)
