#!/usr/bin/env python3
# SPDX-FileCopyrightText: © 2026 Renaldas Zioma
# SPDX-License-Identifier: Apache-2.0
"""The standard cells' Liberty files with the flow's limits on every pin.

usage: scripts/cell_limits.py SRC DST --pdk-config CONFIG.tcl

The PDK's LibreLane configuration (CONFIG.tcl, libs.tech/librelane/<SCL>/)
limits every pin's edge, load and fanout: MAX_TRANSITION_CONSTRAINT 3 ns,
MAX_CAPACITANCE_CONSTRAINT 0.2 pF and MAX_FANOUT_CONSTRAINT 10, and
LibreLane's default SDC puts them on the whole design. OpenSTA keeps the
tightest of the design's, a port's and the library's limit on every pin, so
a design-wide limit cannot be loosened anywhere: it would also hold the
pads' board side to the core's 3 ns and 0.2 pF, where the pads drive and
take the datasheet's 100 pF and slow edges, and the pads' own libraries
(spice/pads/, as RZ80 simulated them) carry the range they were simulated
over. OpenSTA reads per-cell SDC limits for load and fanout, but not for
edges. So the core's limits are written into the cells' libraries
instead: every pin's max_transition is the tighter of the library's (its
tables' range at that corner) and MAX_TRANSITION_CONSTRAINT, every
max_capacitance the tighter of the library's and MAX_CAPACITANCE_CONSTRAINT,
and default_max_fanout (the library has no fanout limit) is
MAX_FANOUT_CONSTRAINT. The antenna diode's pin (DIODE_CELL) gets fanout_load
0: the router adds diodes after the last repair, and a diode is a junction,
not a gate input -- its capacitance still counts in every load and edge
check, but it takes no place in a driver's fanout (two on the data pads'
outputs, whose library allows one load, would otherwise count as two). The
tables are untouched: the timing is the PDK's.
The flow reads these as CELL_LIBS (librelane/config.yaml); `make cell-libs`
writes them.
"""
import argparse, os, re, sys

KEYS = {"max_transition": "MAX_TRANSITION_CONSTRAINT", "max_capacitance": "MAX_CAPACITANCE_CONSTRAINT"}


def pdk_limits(path):
    """MAX_TRANSITION_CONSTRAINT, MAX_CAPACITANCE_CONSTRAINT,
    MAX_FANOUT_CONSTRAINT and DIODE_CELL from the PDK's LibreLane
    configuration"""
    text = open(path).read()
    out = {}
    for name in list(KEYS.values()) + ["MAX_FANOUT_CONSTRAINT"]:
        m = re.search(r"^\s*set\s+::env\(" + name + r"\)\s+\{?([0-9.]+)\}?", text, re.M)
        if not m:
            sys.exit(f"cell_limits: no {name} in {path}")
        out[name] = float(m.group(1))
    m = re.search(r'^\s*set\s+::env\(DIODE_CELL\)\s+"?([^"\s]+)"?', text, re.M)
    if not m:
        sys.exit(f"cell_limits: no DIODE_CELL in {path}")
    out["DIODE_CELL"] = m.group(1)
    return out


def group_end(s, i):
    """the end of the Liberty group whose header starts at s[i]"""
    j, d = s.index("{", i), 0
    for k in range(j, len(s)):
        if s[k] == "{":
            d += 1
        elif s[k] == "}":
            d -= 1
            if d == 0:
                return k + 1
    sys.exit("cell_limits: unbalanced Liberty group")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--pdk-config", required=True, help="the PDK's libs.tech/librelane/<SCL>/config.tcl")
    a = ap.parse_args()
    lim = pdk_limits(a.pdk_config)
    lib = open(a.src).read()
    if re.search(r"\b(default_)?max_fanout\b", lib):
        sys.exit(f"cell_limits: {a.src} has a fanout limit of its own")
    if re.search(r"\bdefault_max_(transition|capacitance)\b", lib):
        sys.exit(f"cell_limits: {a.src} has a default edge or load limit")
    counts = {}

    def tighter(m):
        key, own = m.group(1), float(m.group(2))
        flow = lim[KEYS[key]]
        n = counts.setdefault(key, [0, 0])
        n[0] += 1
        if own <= flow:
            return m.group(0)
        n[1] += 1
        return f"{key} : {flow:g} ;"
    lib = re.sub(r"\b(max_transition|max_capacitance)\s*:\s*([0-9.eE+-]+)\s*;", tighter, lib)
    head = re.search(r"\blibrary\s*\(\s*\"?([^\")]*)\"?\s*\)\s*\{[^\n]*\n", lib)
    if not head:
        sys.exit(f"cell_limits: no library group in {a.src}")
    # the antenna diode: no fanout (its pin, as DIODE_CELL names it)
    cell, pin = lim["DIODE_CELL"].replace("$::env(STD_CELL_LIBRARY)", head.group(1).split("__")[0]).split("/")
    c = re.search(r"\bcell\s*\(\s*\"?" + re.escape(cell) + r"\"?\s*\)\s*\{", lib)
    if not c:
        sys.exit(f"cell_limits: no diode cell {cell} in {a.src}")
    ce = group_end(lib, c.start())
    p = re.compile(r"\bpin\s*\(\s*\"?" + re.escape(pin) + r"\"?\s*\)\s*\{[^\n]*\n").search(lib, c.start(), ce)
    if not p or re.search(r"\bfanout_load\b", lib[p.end():group_end(lib, p.start())]):
        sys.exit(f"cell_limits: no pin {pin} of {cell}, or it has a fanout_load already")
    indent = re.match(r"[ \t]*", lib[p.end():]).group(0)
    lib = lib[:p.end()] + f"{indent}fanout_load : 0 ;\n" + lib[p.end():]
    fan = f"  default_max_fanout : {lim['MAX_FANOUT_CONSTRAINT']:g} ;\n"
    lib = lib[:head.end()] + fan + lib[head.end():]
    note = (f"/* scripts/cell_limits.py: the PDK's {os.path.basename(a.src)}\n"
            f"   with the flow's limits (the PDK's LibreLane configuration) on every pin:\n"
            f"   max_transition the tighter of the library's and {lim['MAX_TRANSITION_CONSTRAINT']:g} ns, max_capacitance\n"
            f"   the tighter of the library's and {lim['MAX_CAPACITANCE_CONSTRAINT']:g} pF, default_max_fanout {lim['MAX_FANOUT_CONSTRAINT']:g}. In\n"
            f"   the cells' libraries rather than on the design, so that the pads keep\n"
            f"   their own range. The antenna diode ({cell}/{pin}) has fanout_load 0:\n"
            f"   a junction, not a gate input; its capacitance counts as before. The\n"
            f"   tables are the PDK's. Generated; do not edit. */\n")
    os.makedirs(os.path.dirname(os.path.abspath(a.dst)), exist_ok=True)
    tmp = a.dst + ".tmp"
    open(tmp, "w").write(note + lib)
    os.replace(tmp, a.dst)
    print(f"cell_limits: {os.path.basename(a.dst)}: " + ", ".join(
        f"{k} {c[1]} of {c[0]} tightened" for k, c in sorted(counts.items()))
        + f", default_max_fanout {lim['MAX_FANOUT_CONSTRAINT']:g}, {cell}/{pin} fanout_load 0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
