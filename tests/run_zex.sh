#!/usr/bin/env bash
# SPDX-FileCopyrightText: © 2026 Renaldas Zioma
# SPDX-License-Identifier: Apache-2.0
#
# run_zex.sh <zexdoc|zexall> [test index ...]
#
# Frank Cringle's ZEXDOC / ZEXALL (rz80/tests/zex/, GPL-2.0-or-later, read
# from the submodule) through the RTL in Verilator (sim_zex, RZ80's
# harness). With test indices (0..66, `rz80/scripts/zex_make_subset.py
# <file.com> /dev/null` lists them), only those tests run: the .com's test
# table is rewritten, everything else is byte-identical. Every test checks
# its CRC against the one the program carries; any ERROR fails, and so does
# a run that does not reach "Tests complete".
set -euo pipefail
cd "$(dirname "$0")/.."
zex=$1; shift
com=rz80/tests/zex/$zex.com
[ -f "$com" ] || { echo "run_zex: no $com" >&2; exit 2; }
out=build/rz80/zex; mkdir -p "$out"
name=$zex
if [ $# -gt 0 ]; then
  name="${zex}_$(echo "$@" | tr ' ' '-')"
  python3 tests/rz80/scripts/zex_make_subset.py "$com" "$out/$name.com" "$@" > /dev/null
  com=$out/$name.com
fi
log=$out/$name.log
stdbuf -oL build/rz80/obj_dir_zex/sim_zex "$com" 12000000000 2>&1 | stdbuf -oL tr -d '\r' | tee "$log"
if grep -q ERROR "$log"; then echo "::error::$name: ERROR (above)"; exit 1; fi
grep -q 'Tests complete' "$log" || { echo "::error::$name did not finish"; exit 1; }
