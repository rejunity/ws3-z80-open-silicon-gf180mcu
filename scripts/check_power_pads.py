#!/usr/bin/env python3
# SPDX-FileCopyrightText: © 2026 Renaldas Zioma
# SPDX-License-Identifier: Apache-2.0
"""Every power and ground pad of the chip, against the wafer.space template's.

usage: scripts/check_power_pads.py [--ref REF ...]
       (default: the template commit ws3 was made from, TEMPLATE_COMMIT;
        --ref main checks the template's current main as well)

wafer.space bonds, packages and tests every chip of a slot alike, from the
template's supply pads: they must not move, change or be connected
otherwise. For every slot configuration ws3 carries, and every file of the
template that places, counts, builds or connects supply pads, this compares:

  librelane/slots/slot_*.yaml  each supply pad (an instance of a generate
                               block of supply cells in chip_top.sv:
                               dvss_pads, dvdd_pads, vss_pads, vdd_pads): its
                               side and position in that side's pad order,
                               and how many pads each side has (a pad's place
                               along its side follows from both)
  src/slot_defines.svh         how many of each supply pad every slot has
  src/chip_top.sv              the supply cells for each pad library, their
                               generate blocks (count, attributes, cell,
                               instance name) and every connection of theirs,
                               the supply ports and the I/O-to-core short
  librelane/config.yaml        the power nets and the core ring's settings
                               (it connects to the supply pads)
  librelane/pdn/pdn_cfg.tcl    the core ring's construction

The template's files are read from GitHub (raw.githubusercontent.com, no
credentials). Exit 0 when every one matches, 1 on a difference, 2 when a
file cannot be read.
"""
import argparse, os, re, sys, urllib.request

TEMPLATE = "wafer-space/gf180mcu-project-template"
TEMPLATE_COMMIT = "d99f6e1ba14e549e80d5d83e113fbd82ed37ed5c"   # ws3 was made from it
WS3 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SLOTS = "librelane/slots/slot_{}.yaml"
SIDES = ("PAD_SOUTH", "PAD_EAST", "PAD_NORTH", "PAD_WEST")
SUPPLY_CELL = re.compile(r"_io__(dvdd|dvss|vdd|vss)$")


class Unreadable(Exception):
    pass


def reader(ref):
    """path -> text: ws3's own file (ref None) or the template's at ref"""
    def read(path):
        if ref is None:
            try:
                return open(os.path.join(WS3, path)).read()
            except OSError as e:
                raise Unreadable(f"ws3 has no {path} ({e.strerror})")
        url = f"https://raw.githubusercontent.com/{TEMPLATE}/{ref}/{path}"
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                return r.read().decode()
        except Exception as e:
            raise Unreadable(f"cannot read the template's {path} at {ref} ({url}: {e})")
    return read


# ------------------------------------------------------------------ chip_top.sv
def directives(text):
    """[(line number, the `ifdef / `ifndef / `elsif conditions in force)]"""
    out, stack = [], []
    for line in text.splitlines():
        s = line.strip()
        m = re.match(r"`(ifdef|ifndef)\s+(\w+)", s)
        if m:
            stack.append(("!" if m.group(1) == "ifndef" else "") + m.group(2))
        elif s.startswith("`else") and stack:
            stack[-1] = "else " + stack[-1]
        elif re.match(r"`elsif\s+(\w+)", s) and stack:
            stack[-1] = "elsif " + re.match(r"`elsif\s+(\w+)", s).group(1)
        elif s.startswith("`endif") and stack:
            stack.pop()
        out.append(tuple(stack))
    return out


def chip_top(text):
    """the supply pads as chip_top.sv defines, builds and connects them"""
    lines = text.splitlines()
    conds = directives(text)
    sig = {}
    # the supply cell of each pad-library macro, per branch of the `ifdef's
    for n, line in enumerate(lines):
        m = re.match(r"\s*`define\s+(\w+)\s+(\w+)", line)
        if m and SUPPLY_CELL.search(m.group(2)):
            sig[f"`define {m.group(1)} (under {' / '.join(conds[n]) or 'no condition'})"] = m.group(2)
    macros = {m.group(1) for m in re.finditer(r"`define\s+(\w+)\s+(\w+)", text) if SUPPLY_CELL.search(m.group(2))}
    # the generate blocks of supply cells: count, attributes, cell, instance, connections
    blocks = {}
    for m in re.finditer(r"for\s*\(\s*genvar\s+(\w+)\s*=\s*0\s*;\s*\1\s*<\s*(\w+)\s*;\s*\1\s*\+\+\s*\)\s*"
                         r"begin\s*:\s*(\w+)(.*?)\n\s*end\b", text, re.S):
        body = m.group(4)
        inst = re.search(r"((?:\(\*[^*]*\*\)\s*)*)`(\w+)\s+(\w+)\s*\((.*?)\)\s*;", body, re.S)
        if not inst or inst.group(2) not in macros:
            continue
        block = m.group(3)
        blocks[block] = inst.group(3)
        sig[f"generate block {block}: count"] = m.group(2)
        sig[f"generate block {block}: attributes"] = " ".join(inst.group(1).split())
        sig[f"generate block {block}: cell"] = "`" + inst.group(2)
        sig[f"generate block {block}: instance"] = inst.group(3)
        conns = re.findall(r"\.(\w+)\s*\(\s*([^()]*?)\s*\)", inst.group(4))
        sig[f"generate block {block}: connections"] = ", ".join(f".{p}({n})" for p, n in conns)
        sig[f"generate block {block}: conditions on its connections"] = \
            " ".join(" ".join(d.split()) for d in re.findall(r"`(?:ifdef|ifndef|elsif)[ \t]+\w+|`(?:else|endif)\b",
                                                         inst.group(4)))
    # the supply ports, the counts' parameters and the I/O-to-core short
    for n, line in enumerate(lines):
        s = " ".join(line.split())
        m = re.match(r"inout wire (VDD|VSS|DVDD|DVSS),?$", s)
        if m:
            sig[f"port {m.group(1)}"] = "inout wire (under " + (" / ".join(conds[n]) or "no condition") + ")"
        m = re.match(r"parameter (\w+) = `(\w+),?$", s)
        if m and m.group(1) in {sig.get(f"generate block {b}: count") for b in blocks}:
            sig[f"parameter {m.group(1)}"] = "`" + m.group(2)
        m = re.match(r"assign (VDD|VSS|DVDD|DVSS) = (\w+);$", s)
        if m:
            sig[f"assign {m.group(1)} (under {' / '.join(conds[n]) or 'no condition'})"] = m.group(2)
    return sig, blocks


# ------------------------------------------------------------------ slots
def side_lists(text):
    """{side: [pad instance, ...]} of a slot's YAML"""
    out = {}
    for side in SIDES:
        m = re.search(rf"^{side}\s*:\s*\[(.*?)^\s*\]", text, re.S | re.M)
        if not m:
            continue
        pads = []
        for line in m.group(1).splitlines():
            line = line.split("#")[0]
            for item in line.split(","):
                item = item.strip().strip('"').strip("'").replace("\\\\", "").replace("\\", "")
                if item:
                    pads.append(item)
        out[side] = pads
    return out


def slot_supplies(text, blocks):
    """{(side, 'pads'): count, (side, position): supply pad instance} of one slot"""
    names = {f"{b}[" for b in blocks}
    sig = {}
    for side, pads in side_lists(text).items():
        sig[(side, "pads")] = len(pads)
        for k, pad in enumerate(pads):
            if any(pad.startswith(b) for b in names):
                sig[(side, k)] = pad
    return sig


def slot_counts(text, params):
    """{slot: {macro: count}} of slot_defines.svh, for the supply counts"""
    out, slot = {}, None
    for line in text.splitlines():
        m = re.match(r"\s*`ifdef\s+SLOT_(\w+)", line)
        if m:
            slot = m.group(1).lower()
            out.setdefault(slot, {})
            continue
        if re.match(r"\s*`endif", line):
            slot = None
        m = re.match(r"\s*`define\s+(\w+)\s+(\d+)", line)
        if m and slot and m.group(1) in params:
            out[slot][m.group(1)] = int(m.group(2))
    return out


# ------------------------------------------------------------------ PDN
def config_power(text):
    """the power nets and the core ring's settings of config.yaml"""
    sig, key = {}, None
    for line in text.splitlines():
        m = re.match(r"^(VDD_NETS|GND_NETS|PDN_CORE_RING\w*)\s*:\s*(.*?)\s*(#.*)?$", line)
        if m:
            key = m.group(1)
            sig[key] = m.group(2)
            continue
        m = re.match(r"^\s*-\s*(\S+)", line)
        if key and m and sig[key] == "":
            sig[key + " list"] = sig.get(key + " list", "") + m.group(1) + " "
            continue
        if line and not line.startswith((" ", "-", "#")):
            key = None
    return sig


def pdn_ring(text):
    """the lines of pdn_cfg.tcl that build the core ring, whitespace folded"""
    lines = text.splitlines()
    start = next((k for k, l in enumerate(lines) if re.search(r"if\s*\{\s*\$::env\(PDN_CORE_RING\)", l)), None)
    if start is None:
        return {"core ring block": "absent"}
    depth, out = 0, []
    for l in lines[start:]:
        code = l.split("#")[0] if not l.lstrip().startswith("#") else ""
        depth += code.count("{") - code.count("}")
        if code.strip():
            out.append(" ".join(code.split()))
        if depth <= 0 and out:
            break
    return {f"core ring line {k + 1}": l for k, l in enumerate(out)}


# ------------------------------------------------------------------ the check
def signature(read, slots, lists=None):
    """{(file, property): value}; lists, if given, gets every slot's side lists
    (to name what a position holds where it holds no supply pad)"""
    sig = {}
    top, blocks = chip_top(read("src/chip_top.sv"))
    sig.update({("src/chip_top.sv", k): v for k, v in top.items()})
    params = {v for k, v in top.items() if k.endswith(": count")}
    for slot, counts in slot_counts(read("src/slot_defines.svh"), params).items():
        if slot in slots:
            for macro, n in counts.items():
                sig[("src/slot_defines.svh", f"slot {slot}: `{macro}")] = n
    for slot in slots:
        path = SLOTS.format(slot)
        text = read(path)
        if lists is not None:
            lists.update({(path, side): pads for side, pads in side_lists(text).items()})
        for (side, pos), pad in slot_supplies(text, blocks).items():
            what = f"{side}: number of pads" if pos == "pads" else f"{side} position {pos}"
            sig[(path, f"slot {slot}, {what}")] = pad
    sig.update({("librelane/config.yaml", k): v for k, v in config_power(read("librelane/config.yaml")).items()})
    sig.update({("librelane/pdn/pdn_cfg.tcl", k): v for k, v in pdn_ring(read("librelane/pdn/pdn_cfg.tcl")).items()})
    return sig


def compare(ref, slots):
    lo, lt = {}, {}
    ours, theirs = signature(reader(None), slots, lo), signature(reader(ref), slots, lt)

    def what(sig, lists, key):
        if key in sig:
            return sig[key]
        m = re.search(r"(PAD_\w+) position (\d+)$", str(key[1]))
        if m:                     # a position where this side has no supply pad
            pads = lists.get((key[0], m.group(1)), [])
            k = int(m.group(2))
            return f"{pads[k]} (no supply pad)" if k < len(pads) else "no pad (the side is shorter)"
        return "nothing"
    bad = []
    for key in sorted(set(ours) | set(theirs), key=lambda k: (k[0], str(k[1]))):
        a, b = what(ours, lo, key), what(theirs, lt, key)
        if a != b:
            bad.append(f"{key[0]}: {key[1]}: ws3 has {a}, the template {b}")
    return bad, len(theirs)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--ref", action="append", default=[],
                    help="also check against this template ref (branch, tag or commit), e.g. main")
    a = ap.parse_args()
    slots = sorted(re.match(r"slot_(\w+)\.yaml$", f).group(1)
                   for f in os.listdir(os.path.join(WS3, "librelane", "slots")) if re.match(r"slot_\w+\.yaml$", f))
    rc = 0
    for ref in [TEMPLATE_COMMIT] + a.ref:
        label = f"{TEMPLATE} at {ref[:7] if re.fullmatch(r'[0-9a-f]{40}', ref) else ref}"
        try:
            bad, n = compare(ref, slots)
        except Unreadable as e:
            print(f"::error::power pads: {e}")
            rc = 2
            continue
        if bad:
            print(f"power pads: {len(bad)} difference(s) from {label}:")
            for b in bad:
                print(f"::error::{b}")
            rc = max(rc, 1)
        else:
            print(f"power pads: as in {label} ({n} properties: the supply pads of slots "
                  f"{', '.join(slots)}, their cells, counts and connections, the power nets and the core ring)")
    return rc


if __name__ == "__main__":
    sys.exit(main())
