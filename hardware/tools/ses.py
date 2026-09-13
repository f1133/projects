"""Read a freerouting .ses session back into copper on the .kicad_pcb.

The session gives wires as polylines per layer and vias as points. Both come
back in DSN units with Y pointing up, so every coordinate is scaled and its Y
negated on the way in - the mirror of what dsn.py does going out.
"""

import hashlib
import sexp

SCALE = 10000.0


def uid(*parts):
    h = hashlib.sha256(("juno-route|" + "|".join(str(p) for p in parts))
                       .encode()).hexdigest()
    return f"{h[0:8]}-{h[8:12]}-4{h[13:16]}-a{h[17:20]}-{h[20:32]}"


def mm(v):
    return round(float(v) / SCALE, 4)


def num(v):
    s = f"{round(float(v), 4):.4f}".rstrip("0").rstrip(".")
    return "0" if s in ("", "-0") else s


def read(ses_path):
    """Returns (wires, vias). wires: (layer, width_mm, [(x,y)...], net)."""
    root = sexp.parse(open(ses_path).read())
    routes = sexp.find(root, "routes")
    if routes is None:
        return [], []
    netout = sexp.find(routes, "network_out")
    if netout is None:
        return [], []
    wires, vias = [], []
    for net in sexp.findall(netout, "net"):
        name = str(net[1])
        for w in sexp.findall(net, "wire"):
            path = sexp.find(w, "path")
            if not path:
                continue
            layer, width = str(path[1]), float(path[2])
            co = [float(x) for x in path[3:]]
            pts = [(mm(co[i]), -mm(co[i + 1])) for i in range(0, len(co) - 1, 2)]
            if len(pts) >= 2:
                wires.append((layer, mm(width), pts, name))
        for v in sexp.findall(net, "via"):
            vias.append((str(v[1]), mm(v[2]), -mm(v[3]), name))
    return wires, vias


def inject(pcb_path, out_path, wires, vias, via_pad=0.6, via_drill=0.3):
    """Write a copy of the board with the routed copper added."""
    text = open(pcb_path).read()
    root = sexp.parse(text)
    net_id = {}
    for n in sexp.findall(root, "net"):
        net_id[str(n[2]) if len(n) > 2 else ""] = int(n[1])

    body, seg_n = [], 0
    for layer, width, pts, name in wires:
        nid = net_id.get(name)
        if nid is None:
            continue
        for a, b in zip(pts, pts[1:]):
            if abs(a[0] - b[0]) < 1e-9 and abs(a[1] - b[1]) < 1e-9:
                continue
            seg_n += 1
            body.append(
                f'\t(segment\n\t\t(start {num(a[0])} {num(a[1])})\n'
                f'\t\t(end {num(b[0])} {num(b[1])})\n'
                f'\t\t(width {num(width)})\n\t\t(layer "{layer}")\n'
                f'\t\t(net {nid})\n\t\t(uuid "{uid("seg", seg_n)}")\n\t)\n')
    for i, (pad, x, y, name) in enumerate(vias):
        nid = net_id.get(name)
        if nid is None:
            continue
        body.append(
            f'\t(via\n\t\t(at {num(x)} {num(y)})\n\t\t(size {num(via_pad)})\n'
            f'\t\t(drill {num(via_drill)})\n\t\t(layers "F.Cu" "B.Cu")\n'
            f'\t\t(net {nid})\n\t\t(uuid "{uid("via", i)}")\n\t)\n')

    cut = text.rstrip()
    assert cut.endswith(")"), "board does not end with a closing paren"
    open(out_path, "w").write(cut[:-1] + "".join(body) + ")\n")
    return seg_n, len([v for v in vias if net_id.get(v[3]) is not None])
