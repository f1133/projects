#!/usr/bin/env python3
"""Group a KiCad netlist into a BOM CSV.

    kicad-cli sch export netlist --output build/net.net g431-can-actuator.kicad_sch
    python3 tools/gen_bom.py build/net.net docs/bom.csv
"""
import csv
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from check_netlist import load  # noqa: E402


def sort_key(ref):
    m = re.match(r"([A-Za-z_#]+)(\d+)", ref)
    return (m.group(1), int(m.group(2))) if m else (ref, 0)


def main(netlist, out):
    _nets, comps = load(netlist)
    groups = {}
    for ref, (value, fp) in comps.items():
        if ref.startswith("#"):          # power symbols and flags
            continue
        groups.setdefault((value, fp), []).append(ref)

    rows = []
    for (value, fp), refs in groups.items():
        refs.sort(key=sort_key)
        rows.append({
            "Qty": len(refs),
            "References": " ".join(refs),
            "Value": value,
            "Footprint": fp,
        })
    rows.sort(key=lambda r: sort_key(r["References"].split()[0]))

    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["Qty", "References", "Value", "Footprint"])
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)} BOM lines, {sum(r['Qty'] for r in rows)} placed parts -> {out}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "docs/bom.csv")
