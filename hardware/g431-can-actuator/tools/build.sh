#!/bin/sh
# Regenerate the schematic, then validate it with KiCad and check the netlist.
set -e
cd "$(dirname "$0")/.."
mkdir -p build
python3 tools/gen_schematic.py
kicad-cli sch export netlist --output build/net.net g431-can-actuator.kicad_sch >/dev/null
kicad-cli sch export pdf --output docs/schematic.pdf g431-can-actuator.kicad_sch >/dev/null
python3 tools/gen_bom.py build/net.net docs/bom.csv
python3 tools/check_netlist.py build/net.net
