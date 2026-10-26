# Files from RZ80

Written by `scripts/sync_rz80.py`; do not edit. RZ80 is the `rz80/`
submodule, [https://github.com/rejunity/z80-from-schematics](https://github.com/rejunity/z80-from-schematics):

| | commit |
|---|---|
| main (the submodule) | [`f88c75e`](https://github.com/rejunity/z80-from-schematics/commit/f88c75e098c00ae95572647130dbad023463088c) (2026-10-25 Merge xy-flags: Q, F and WZ against the die; X / Y against every oracle) |
| asic-gf180mcu (the chip flows' glue) | [`c88cc6b`](https://github.com/rejunity/z80-from-schematics/commit/c88cc6bcee12d43ca3031d0ff86c374c7ee992f2) |

| ws3 | RZ80 | from | |
|---|---|---|---|
| `src/rz80/z80_top.v` | `rtl/z80_top.v` | main | copied |
| `src/rz80/z80_core.v` | `rtl/z80_core.v` | main | copied |
| `src/rz80/z80_timing.v` | `rtl/z80_timing.v` | main | copied |
| `src/rz80/z80_pla.v` | `rtl/z80_pla.v` | main | copied |
| `src/rz80/z80_execute.v` | `rtl/z80_execute.v` | main | copied |
| `src/rz80/z80_regfile.v` | `rtl/z80_regfile.v` | main | copied |
| `src/rz80/z80_addr.v` | `rtl/z80_addr.v` | main | copied |
| `src/rz80/z80_alu.v` | `rtl/z80_alu.v` | main | copied |
| `src/rz80/z80_ctl.vh` | `rtl/z80_ctl.vh` | main | copied |
| `src/rz80/z80_defs.vh` | `rtl/z80_defs.vh` | main | copied |
| `tests/rz80/iverilog/tb_bus_controls.v` | `tests/iverilog/tb_bus_controls.v` | main | copied |
| `tests/rz80/iverilog/tb_wait_edge.v` | `tests/iverilog/tb_wait_edge.v` | main | copied |
| `tests/rz80/iverilog/tb_wait_write.v` | `tests/iverilog/tb_wait_write.v` | main | copied |
| `tests/rz80/iverilog/tb_int_ack.v` | `tests/iverilog/tb_int_ack.v` | main | copied |
| `tests/rz80/iverilog/tb_event_sweep.v` | `tests/iverilog/tb_event_sweep.v` | main | copied |
| `tests/rz80/scripts/compare_fuse_rtl.py` | `scripts/compare_fuse_rtl.py` | main | patched |
| `tests/rz80/scripts/gen_fuse_tb.py` | `scripts/gen_fuse_tb.py` | main | patched |
| `tests/rz80/scripts/event_sweep.py` | `scripts/event_sweep.py` | main | patched |
| `tests/rz80/verilator/sim_zex.cpp` | `tests/verilator/sim_zex.cpp` | main | copied |
| `tests/rz80/verilator/sim_z80test.cpp` | `tests/verilator/sim_z80test.cpp` | main | copied |
| `tests/rz80/verilator/sim_basic.cpp` | `tests/verilator/sim_basic.cpp` | main | copied |
| `tests/rz80/scripts/zex_make_subset.py` | `scripts/zex_make_subset.py` | main | copied |
| `tests/rz80/basic/run_basic_tests.sh` | `tests/basic/run_basic_tests.sh` | main | patched |
| `tests/rz80/scripts/sigrok_z80_decode.py` | `scripts/sigrok_z80_decode.py` | main | copied |
| `tests/rz80/scripts/summary.py` | `asic/summary.py` | asic-gf180mcu | copied |
| `timing/z8400_nmos.json` | `asic/timing/z8400_nmos.json` | main | copied |
| `timing/pin_timing.py` | `asic/timing/pin_timing.py` | main | patched |
| `spice/pads/gf180mcu/pads.json` | `asic/spice/pads/gf180mcu/pads.json` | main | copied |
| `spice/pads/gf180mcu/gf180mcu_fd_io__tt_025C_5v00.lib` | `asic/spice/pads/gf180mcu/gf180mcu_fd_io__tt_025C_5v00.lib` | main | copied |
| `spice/pads/gf180mcu/gf180mcu_fd_io__ss_125C_4v50.lib` | `asic/spice/pads/gf180mcu/gf180mcu_fd_io__ss_125C_4v50.lib` | main | copied |
| `spice/pads/gf180mcu/gf180mcu_fd_io__ff_n40C_5v50.lib` | `asic/spice/pads/gf180mcu/gf180mcu_fd_io__ff_n40C_5v50.lib` | main | copied |
| `spice/chip.py` | `asic/spice/chip.py` | main | patched |
| `spice/pads.py` | `asic/spice/pads.py` | main | patched |
| `spice/svgplot.py` | `asic/spice/svgplot.py` | main | copied |
| `spice/tb_chip_ref.v` | `asic/spice/tb_chip_ref.v` | main | copied |
| `LICENSES/CERN-OHL-W-2.0.txt` | `LICENSES/CERN-OHL-W-2.0.txt` | main | copied |
| `LICENSES/MIT.txt` | `LICENSES/MIT.txt` | main | copied |

"patched" files differ from RZ80's by the exact text replacements listed
in `scripts/sync_rz80.py`: paths (their data from the submodule, the RTL
from `src/rz80/`, builds in `build/rz80/`), and perfectz80 only as RZ80
recorded it. The C model, the perfectz80 simulator and the reference
emulators are not part of ws3.
