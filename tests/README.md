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
| HALT to INT acknowledge, 10 INT placements (`test__halt2int`, as Woodmass's HALT2INT) | perfectz80: 6 5 4 7 6 5 4 7 6 5 T-states | cocotb (iverilog) | both | every push |
| KC 85/4 capture: every instruction of a real Z80's (U880) logic-analyser trace, T-states per M1 cycle (`test__sigrok_kc85`) | the real chip | cocotb (iverilog) | both | every push |
| prelim, Cringle's preliminary tests under a minimal CP/M (`cocotb/system_tb.py`) | the program's own checks | cocotb (iverilog) | both | every push |
| RTL elaboration, bus controls: WAIT latch, write hold, INT acknowledge IM 0/1/2 (`make rz80-elab rz80-bus`) | the testbenches | iverilog | RTL | every push |
| FUSE's 1356 tests, with the die's values where they differ from FUSE's (`make rz80-fuse`) | FUSE + perfectz80 (`silicon.expected`) | iverilog | RTL | every push |
| The X / Y flag corpus, 4061 cases (`make rz80-xyflags`) | perfectz80 | iverilog | RTL | every push |
| The pin sweep: every opcode, timing class, RESET / INT / NMI / WAIT / BUSREQ event, half-cycle by half-cycle, 51126 cases in 4 parts (`make rz80-sweep`) | perfectz80's recorded traces (`rz80/tests/event_sweep/pz80/`) | iverilog | RTL | every push |
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
rz80-sweep`, `make rz80-z80test Z80TEST=z80full`, `make rz80-basic`,
`make rz80-zex ZEX=zexdoc`, `make pin-timing`, `make precheck`.

## Not in ws3

RZ80's tests that need its C model, its cfast engine, the perfectz80 simulator
or the reference emulators running live: lockstep and parity against the C
model, the C model's own suites (ctest, FUSE, ZEX, z80test, prelim and
HALT-to-INT on the C model), live comparisons against perfectz80
(`compare_signal_timing.py`, `fuse_pz80`), the X / Y oracle study, cfast's
benchmarks, the FPGA LUT counts. Their RTL counterparts above cover the RTL.

Waiting for recordings in RZ80: the trace programs and pin scenarios
(`tests/traces/`, `.events`, `.phases`) against perfectz80 need its traces
recorded in RZ80 first; then `scripts/sync_rz80.py` brings them and they run
here on the RTL and the gate-level netlist.
