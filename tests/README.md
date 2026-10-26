# Tests

What checks the chip, where it runs and against what. The RTL under test is
always `src/rz80/` (RZ80's `rtl/`, copied by `scripts/sync_rz80.py`), and the
gate-level netlist is the chip's own (`final/pnl/chip_top.pnl.v`, through its
pads). Expectations come from the Zilog die (perfectz80, the transistor-level
netlist of the Visual Z80 die scan, as RZ80 recorded it) or from real Z80s.
Nothing is allowed to fail.

| Test | Expectation from | Runner | RTL / gate level | Runs |
|---|---|---|---|---|
| ws0's 14 pin-level tests: RESET, NMI, INT, BUSREQ, fetch / read / write timing, single instructions, a program (`cocotb/chip_top_tb.py`) | perfectz80, per test | cocotb (iverilog) | both | every push |
| Signs of life: a 37-byte program, memory, ALU, loop, I/O, stack, HALT, no RD+WR / MREQ+IORQ overlap (`test__sign_of_life`, RZ80's `asic/tb_sign_of_life.v`) | the program's own results | cocotb (iverilog) | both | every push |
| HALT to INT acknowledge, 10 INT placements (`test__halt2int`, as Woodmass's HALT2INT) | perfectz80: 6 5 4 7 6 5 4 7 6 5 T-states, as RZ80's `scripts/halt2int_probe.c` records them | cocotb (iverilog) | both | every push |
| KC 85/4 capture: every instruction of a real Z80's (U880) logic-analyser trace, T-states per M1 cycle (`test__sigrok_kc85`) | the real chip | cocotb (iverilog) | both | every push |
| prelim, Cringle's preliminary tests under a minimal CP/M (`cocotb/system_tb.py`) | the program's own checks | cocotb (iverilog) | both | every push |
| RTL elaboration, bus controls: WAIT latch, write hold, INT acknowledge IM 0/1/2 (`make rz80-elab rz80-bus`) | the testbenches | iverilog | RTL | every push |
| FUSE's 1356 tests, with the die's values where they differ from FUSE's (`make rz80-fuse`) | FUSE + perfectz80 (`silicon.expected`) | iverilog | RTL | every push |
| The X / Y flag corpus, 4061 cases (`make rz80-xyflags`) | perfectz80 | iverilog | RTL | every push |
| The 14 trace programs, half-cycle by half-cycle: the 7 control pins and the address in every half-cycle, the data under WR (`make rz80-traces`) | perfectz80's recorded traces (`rz80/tests/traces/pz80/`) | iverilog (`compare_signal_timing.py --recorded`) | RTL | every push |
| The 15 pin scenarios: INT IM 0/1/2, NMI, WAIT, BUSREQ, RESET, EI delay, ... with their `.events` (`make rz80-traces`) | perfectz80's recorded traces | iverilog | RTL | every push |
| The same 29 programs on the chip's netlist through its pads (`make rz80-traces-gl`) | perfectz80's recorded traces | iverilog | gate level | every push |
| The pin sweep: every opcode, timing class, RESET / INT / NMI / WAIT / BUSREQ event, half-cycle by half-cycle, 51,126 cases in 4 parts (`make rz80-sweep`) | perfectz80's recorded traces (`rz80/tests/event_sweep/pz80/`, `--recorded-only`) | iverilog | RTL | every push |
| The pin sweep's `opcodes_reset` group: RESET at every half-cycle of every opcode, 27,768 cases in 4 parts (`make rz80-sweep SWEEP_GROUPS=opcodes_reset`) | perfectz80's recorded traces | iverilog | RTL | nightly |
| Patrik Rak's z80test: doc, flags, memptr, full, ccf (`make rz80-z80test`) | real Z80s (the CRCs in the program) | Verilator | RTL | every push |
| NASCOM BASIC 4.7 and Tiny BASIC, canned scripts (`make rz80-basic`) | the scripts' expected output | Verilator | RTL | every push |
| ZEXALL, 14 of its tests (`make rz80-zex ZEX=zexall ZEX_TESTS=...`) | real Z80s (the CRCs in the program) | Verilator | RTL | every push |
| ZEXDOC and ZEXALL, all 67 tests each, in parts (`make rz80-zex`) | real Z80s | Verilator | RTL | main, nightly |
| Sign-off: route / Magic / KLayout DRC, LVS, antenna, XOR, hold at every corner, setup at the typical one (`tests/rz80/scripts/summary.py`) | LibreLane | LibreLane | layout | every push |
| The pins against the NMOS Z80's datasheet at 4 MHz, every corner (`make pin-timing`) | Zilog PS0178 (`timing/z8400_nmos.json`) | OpenSTA | layout | every push |
| wafer.space precheck (`make precheck`) | wafer.space | LibreLane / KLayout / Magic | layout | every push |
| The copies of RZ80's files (`make sync-check`) | `rz80/` | Python | - | every push |
| The whole chip at transistor level (`.github/workflows/transistor.yml`) | the RTL and the datasheet | ngspice | layout | on demand |

Locally: `make sim`, `make sim-gl` (after the flow), `make sim-system`,
`make sim-system-gl`, `make rz80-elab rz80-bus rz80-fuse rz80-xyflags
rz80-traces rz80-sweep`, `make rz80-traces-gl` (after the flow), `make rz80-z80test Z80TEST=z80full`, `make rz80-basic`,
`make rz80-zex ZEX=zexdoc`, `make pin-timing`, `make precheck`.

## Not in ws3

RZ80's tests that need its C model, its cfast engine, the perfectz80 simulator
or the reference emulators running live: lockstep and parity against the C
model, the C model's own suites (ctest, FUSE, ZEX, z80test, prelim and
HALT-to-INT on the C model), every run of perfectz80 itself (recording and
re-verifying its traces: `compare_signal_timing.py --record` /
`--verify-recorded`, `event_sweep.py --record` / `--verify-recorded` and its
fresh-seed fuzz, `fuse_pz80`, `xyflags_pz80`), the X / Y oracle study,
cfast's benchmarks, the FPGA LUT counts. Their RTL counterparts above cover
the RTL; RZ80's CI checks the recordings against perfectz80.

perfectz80's side of every comparison is a recording RZ80 made and checks
in its own CI (`rz80/tests/traces/pz80/`, `rz80/tests/event_sweep/pz80/`):
the recordings carry the sha1 of the program and `.events` they were made
with, and RZ80's scripts fail on a missing or stale one (`--recorded`,
`--recorded-only`). ws3 never runs perfectz80.

At gate level, RZ80's `tb_z80_netlist.v` runs on `chip_top` through
`cocotb/chip_shim.v` (z80_top's ports on the chip's pads). It clocks at 4 ns
and reads the pins 1 ns after each edge, so the PDK's pad models are taken
without their 1 ns gate delays (the cells are zero-delay too, `FUNCTIONAL`),
and a pin whose pad floats keeps its last level, as the die's floating pad
node does in perfectz80's traces: the address and MREQ IORQ RD WR in a bus
grant (`prog15_busreq_m1`), the address while RESET is low (`prog17_reset`).
