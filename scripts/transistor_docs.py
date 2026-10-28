#!/usr/bin/env python3
# SPDX-FileCopyrightText: © 2026 Renaldas Zioma
# SPDX-License-Identifier: Apache-2.0
"""The whole chip at transistor level, published: docs/transistor/.

usage: scripts/transistor_docs.py RESULTS --run ID --commit SHA --gds-run ID
                                  [--out docs/transistor] [--repo OWNER/NAME]

RESULTS is the Transistor workflow's artifact transistor-results
(spice/chip.py's figures: the typical corner at the top, the slow and fast
corners in ss/ and ff/, each with its results.json). It replaces OUT with
those files and writes OUT/README.md: where they came from (the workflow
run, the commit the chip's GDS was built from and the CI run that built it),
the pins against the RTL and every datasheet parameter at each corner, and
the figures. Exit 0 when every corner has no functional mismatch and every
parameter passes, 1 otherwise (the files are written either way).
"""
import argparse, json, os, shutil, sys

CORNERS = (("tt", "", "typical, 25 °C, 5.0 V"), ("ss", "ss", "slow, 125 °C, 4.5 V"),
           ("ff", "ff", "fast, -40 °C, 5.5 V"))
CAPTION = {"fetch.svg": "opcode fetch (PS0178 Figure 5)",
           "mread.svg": "memory read (Figure 6)", "mwrite.svg": "memory write (Figure 6)",
           "ioread.svg": "I/O read (Figure 7)", "iowrite.svg": "I/O write (Figure 7)"}


def ns(v):
    return "–" if v is None else f"{v:.1f}"


def main():
    ap = argparse.ArgumentParser(usage=__doc__.split("\n\n")[1])
    ap.add_argument("results")
    ap.add_argument("--run", required=True)
    ap.add_argument("--commit", required=True)
    ap.add_argument("--gds-run", required=True)
    ap.add_argument("--out", default="docs/transistor")
    ap.add_argument("--repo", default="rejunity/ws3-z80-open-silicon-gf180mcu")
    a = ap.parse_args()

    res = {}
    for c, sub, _ in CORNERS:
        f = os.path.join(a.results, sub, "results.json")
        if os.path.exists(f):
            res[c] = json.load(open(f))
    if not res:
        sys.exit(f"transistor_docs: no results.json in {a.results}")

    if os.path.isdir(a.out):
        shutil.rmtree(a.out)
    shutil.copytree(a.results, a.out)

    url = f"https://github.com/{a.repo}"
    ok = all(not r["functional_mismatches"] and all(p["pass"] for p in r["parameters"])
             for r in res.values())
    L = ["# The chip at transistor level", "",
         "The whole chip, extracted from its GDS to transistors with Magic, runs a short "
         "program in ngspice: power-up, 4 clocks of RESET, then `LD A,5Ah / LD (8000h),A / "
         "OUT (42h),A / IN A,(43h) / HALT` at 4 MHz, 15 ns clock edges, 100 pF on every pin "
         "([spice/README.md](../../spice/README.md)). The pins are checked against the RTL "
         "on every clock edge, and every output parameter of the Z8400's datasheet "
         "(Zilog PS0178) on every cycle that has it.", "",
         f"- workflow run: [{a.run}]({url}/actions/runs/{a.run}) (*Transistor*, "
         "`.github/workflows/transistor.yml`)",
         f"- the chip: commit [`{a.commit[:7]}`]({url}/commit/{a.commit}), GDS from CI run "
         f"[{a.gds_run}]({url}/actions/runs/{a.gds_run})",
         f"- verdict: **{'PASS' if ok else 'FAIL'}**", "",
         "This folder is written by the workflow's `publish` job "
         "(`scripts/transistor_docs.py`); do not edit it by hand.", "",
         "## Corners", "",
         "| corner | | pins vs RTL | datasheet parameters |", "|---|---|---|---|"]
    for c, sub, desc in CORNERS:
        if c not in res:
            continue
        r = res[c]
        mm = len(r["functional_mismatches"])
        npass = sum(p["pass"] for p in r["parameters"])
        L.append(f"| [`{c}`]({sub + '/' if sub else ''}results.json) | {desc} | "
                 f"{'every edge matches' if not mm else f'{mm} mismatches'} | "
                 f"{npass} / {len(r['parameters'])} pass |")
    L += ["", "## Datasheet parameters", "",
          "Measured on every cycle that has the parameter: the extremes over the run, in ns "
          "(outputs where they cross 1.5 V, CLK at 50 %).", ""]
    present = [c for c, _, _ in CORNERS if c in res]
    L.append("| # | parameter | limit | " + " | ".join(f"{c} min / max" for c in present) + " | |")
    L.append("|---|---|---|" + "---|" * len(present) + "---|")
    params = {c: {p["id"]: p for p in res[c]["parameters"]} for c in present}
    for pid in sorted(set().union(*(set(v) for v in params.values()))):
        any_p = next(params[c][pid] for c in present if pid in params[c])
        cells, good = [], True
        for c in present:
            p = params[c].get(pid)
            if p is None:
                cells.append("–")
                continue
            good &= p["pass"]
            cells.append(f"{ns(p['spice_min'])} / {ns(p['spice_max'])}")
        bound = "≤" if any_p["bound"] == "max" else "≥"
        L.append(f"| {pid} | `{any_p['symbol']}` | {bound} {any_p['limit']:g} | "
                 + " | ".join(cells) + f" | {'pass' if good else '**FAIL**'} |")
    L += ["", "## Figures (typical corner)", "",
          "The slow and fast corners' are in [ss/](ss/) and [ff/](ff/).", "",
          "<picture>", '  <source media="(prefers-color-scheme: dark)" srcset="program-dark.svg">',
          '  <img src="program.svg" alt="the program at transistor level, every pin">', "</picture>", ""]
    for f in res[present[0]]["figures"]:
        if f in CAPTION:
            L += [f"{CAPTION[f]}:", "", f"![{CAPTION[f]}]({f})", ""]
    open(os.path.join(a.out, "README.md"), "w").write("\n".join(L))
    print(f"transistor_docs: {a.out}: {', '.join(present)}: {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
