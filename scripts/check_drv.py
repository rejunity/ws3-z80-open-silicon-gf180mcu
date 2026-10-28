#!/usr/bin/env python3
# SPDX-FileCopyrightText: © 2026 Renaldas Zioma
# SPDX-License-Identifier: Apache-2.0
"""Every pin's edge, load and fanout within its limits, at every corner.

usage: scripts/check_drv.py RUN   (a LibreLane run directory)

Reads the run's sign-off STA counts (final/metrics.json): the max slew, max
capacitance and max fanout violations at each of the run's STA corners
(resolved.json's STA_CORNERS). The limits are every cell's own: the
standard cells' are the PDK's flow limits (scripts/cell_limits.py), the
pads' the range RZ80 simulated them over (spice/pads/). Exit 0 when every
count at every corner is 0, 1 otherwise (2 when a count is missing).
"""
import json, os, sys

CHECKS = (("max slew", "design__max_slew_violation__count"),
          ("max capacitance", "design__max_cap_violation__count"),
          ("max fanout", "design__max_fanout_violation__count"))


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__.split("\n\n")[1])
    run = sys.argv[1]
    try:
        metrics = json.load(open(os.path.join(run, "final", "metrics.json")))
        corners = json.load(open(os.path.join(run, "resolved.json")))["STA_CORNERS"]
    except (OSError, ValueError, KeyError) as e:
        print(f"check_drv: {run}: {e}")
        return 2
    print(f"{'corner':20s}" + "".join(f"{name:>17s}" for name, _ in CHECKS))
    bad, missing = 0, 0
    for c in corners:
        row = f"{c:20s}"
        for name, key in CHECKS:
            v = metrics.get(f"{key}__corner:{c}")
            if v is None:
                missing += 1
                row += f"{'missing':>17s}"
            else:
                bad += v != 0
                row += f"{v:>17}"
        print(row)
    if missing:
        print(f"check_drv: {missing} counts missing from {run}/final/metrics.json")
        return 2
    print(f"check_drv: {'every pin within its limits at every corner' if not bad else f'{bad} counts above 0'}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
