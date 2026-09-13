#!/usr/bin/env python3
"""Produce a routed copy of a board: DSN out, freerouting, SES back in.

The unrouted projects stay exactly as they are. This writes a sibling project
with the same schematic, symbols and footprints, and the copper filled in.

freerouting is an autorouter, not a person. It honours the netclass widths and
clearances it is given - so power and motor nets come out fat and signal nets
thin - but it will not make the aesthetic choices a human would. Treat its
output as a routed starting point to tidy, not as a finished board.
"""

import os
import shutil
import subprocess
import sys
import fnmatch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dsn                                                    # noqa: E402
import kigen                                                  # noqa: E402
import ses                                                    # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
JAR = os.environ.get("FREEROUTING_JAR", "/tmp/fr.jar")

RULES = {c["name"]: dict(track=c.get("track_width", 0.25),
                         clearance=c.get("clearance", 0.2))
         for c in kigen.NETCLASSES}


def netclass_of(name):
    for cls, pat in kigen.PATTERNS:
        if fnmatch.fnmatch(name, pat):
            return cls
    return "Default"


def route(board, passes=20, timeout=3000):
    src = os.path.join(ROOT, board)
    dst = os.path.join(ROOT, board + "-routed")
    os.makedirs(dst, exist_ok=True)
    for name in os.listdir(src):
        s, d = os.path.join(src, name), os.path.join(dst, name)
        if os.path.isdir(s):
            shutil.rmtree(d, ignore_errors=True)
            shutil.copytree(s, d)
        elif name.endswith((".kicad_sch", ".kicad_pro", "-lib-table", ".md", ".svg")):
            shutil.copy2(s, d.replace(board, board + "-routed")
                         if name.startswith(board) else d)

    pcb = os.path.join(src, f"{board}.kicad_pcb")
    dsn_path = os.path.join(dst, f"{board}.dsn")
    ses_path = os.path.join(dst, f"{board}.ses")
    out_pcb = os.path.join(dst, f"{board}-routed.kicad_pcb")

    dsn.export(pcb, dsn_path, netclass_of, RULES)
    print(f"  exported {dsn_path}")

    cmd = ["java", "-jar", JAR, "-de", dsn_path, "-do", ses_path,
           "-mp", str(passes)]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    log = (r.stdout or "") + (r.stderr or "")
    for line in log.splitlines():
        if any(k in line for k in ("incomplete", "Incomplete", "unrouted",
                                   "Board is completed", "ERROR", "pass")):
            print("   fr:", line.strip()[:130])
    if not os.path.exists(ses_path) or os.path.getsize(ses_path) == 0:
        raise SystemExit(f"freerouting produced no session file for {board}")

    wires, vias = ses.read(ses_path)
    nseg, nvia = ses.inject(pcb, out_pcb, wires, vias)
    print(f"  {board}: {nseg} segments, {nvia} vias -> {out_pcb}")
    return out_pcb, wires, vias


if __name__ == "__main__":
    for b in sys.argv[1:] or ["actuator-node"]:
        route(b)
