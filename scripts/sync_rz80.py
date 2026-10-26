#!/usr/bin/env python3
# SPDX-FileCopyrightText: © 2026 Renaldas Zioma
# SPDX-License-Identifier: Apache-2.0
"""Copy RZ80's files from the rz80/ submodule into ws3's own folders.

usage: scripts/sync_rz80.py           write every copy (patching where listed)
       scripts/sync_rz80.py --check   change nothing; exit 1 if a copy differs
                                      from what the sync would write (CI)

rz80/ is https://github.com/rejunity/z80-from-schematics, pinned as a git
submodule. The chip's sources stand alone: the LibreLane flow and the tests
read src/rz80/, tests/rz80/ and timing/, never the submodule. What this
script copies is only what the RTL, its synthesis and the tapeout tests use
(no C model and no perfectz80 simulator). Test data under a third-party
licence (the ZEX, FUSE, BASIC and z80test programs, the sigrok captures,
perfectz80's recorded traces) is not copied: the tests read it from the
submodule.

Files come from the submodule's commit (FILES, "main"), or, for the glue
of RZ80's chip flows that lives on its asic-gf180mcu branch, from that
branch at ASIC_COMMIT ("asic"). A patch is an exact (old, new) text
replacement that must match once: when RZ80 changes the text, the sync
stops and the patch is updated by hand.
"""
import os, subprocess, sys

WS3 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SUB = os.path.join(WS3, "rz80")
REPO = "https://github.com/rejunity/z80-from-schematics"
ASIC_COMMIT = "c88cc6bcee12d43ca3031d0ff86c374c7ee992f2"   # asic-gf180mcu, 2026-10-25

# --- patches -----------------------------------------------------------------

# a copied script under tests/rz80/scripts/: its data from the submodule
# (ROOT), the RTL from src/rz80/, builds in build/rz80/ (WS3)
PY_ROOT = ("ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))",
           "# ws3 (scripts/sync_rz80.py): RZ80's data from the rz80/ submodule (ROOT),\n"
           "# the RTL from src/rz80/ and the builds in build/rz80/ (WS3)\n"
           "WS3 = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))\n"
           "ROOT = os.path.join(WS3, \"rz80\")\n"
           "BUILD = os.path.join(WS3, \"build\", \"rz80\")")

COMPARE_FUSE_RTL = [
    PY_ROOT,
    ('GEN  = os.path.join(ROOT, "scripts/gen_fuse_tb.py")',
     'GEN  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gen_fuse_tb.py")'),
    ('TB_V = os.environ.get("FUSE_TB")       or os.path.join(ROOT, "tests/iverilog/tb_fuse.v")\n'
     'VVP  = os.environ.get("FUSE_VVP")      or os.path.join(ROOT, "build/tb_fuse.vvp")',
     'TB_V = os.environ.get("FUSE_TB")       or os.path.join(BUILD, "tb_fuse.v")\n'
     'VVP  = os.environ.get("FUSE_VVP")      or os.path.join(BUILD, "tb_fuse.vvp")\n'
     'os.environ["FUSE_TB"] = TB_V            # where gen_fuse_tb.py writes it\n'
     'os.makedirs(os.path.dirname(VVP), exist_ok=True)'),
    ('    rtl = sorted(os.path.relpath(p, ROOT) for p in glob.glob(os.path.join(ROOT, "rtl", "*.v")))\n'
     '    subprocess.check_call(["iverilog", "-g2001", "-Irtl", "-o", VVP] + rtl +\n'
     '                          [TB_V], cwd=ROOT)\n'
     '    print("running iverilog vvp ...")\n'
     '    proc = subprocess.run(["vvp", VVP], cwd=ROOT, capture_output=True, text=True)',
     '    rtl = sorted(os.path.relpath(p, WS3) for p in glob.glob(os.path.join(WS3, "src", "rz80", "*.v")))\n'
     '    subprocess.check_call(["iverilog", "-g2001", "-Isrc/rz80", "-o", VVP] + rtl +\n'
     '                          [TB_V], cwd=WS3)\n'
     '    print("running iverilog vvp ...")\n'
     '    proc = subprocess.run(["vvp", VVP], cwd=WS3, capture_output=True, text=True)'),
]

GEN_FUSE_TB = [
    PY_ROOT,
    ('TB_PATH  = os.environ.get("FUSE_TB")       or os.path.join(ROOT, "tests/iverilog/tb_fuse.v")',
     'TB_PATH  = os.environ.get("FUSE_TB")       or os.path.join(BUILD, "tb_fuse.v")'),
]

EVENT_SWEEP = [
    PY_ROOT,
    ('TB_VVP = os.path.join(ROOT, "build", "tb_event_sweep.vvp")',
     'TB_VVP = os.path.join(BUILD, "tb_event_sweep.vvp")'),
    ('OUT = os.path.join(ROOT, "build", "event_sweep")',
     'OUT = os.path.join(BUILD, "event_sweep")'),
    # perfectz80 only as RZ80 recorded it: no live runs, no C model
    ('    for exe in (TB_VVP, PZ80) + ((CMODEL,) if a.c_model else ()):',
     '    if a.c_model or a.record or a.no_cache or a.verify_recorded:\n'
     '        sys.exit("ws3 compares the RTL with the perfectz80 traces RZ80 recorded "\n'
     '                 "(rz80/tests/event_sweep/pz80/) only: no C model, no live perfectz80")\n'
     '    for exe in (TB_VVP,):'),
    ('    hits = sum(1 for c in pz_cases.values() if cache_key(c, hid) in cache)\n',
     '    hits = sum(1 for c in pz_cases.values() if cache_key(c, hid) in cache)\n'
     '    if hits < len(pz_cases):\n'
     '        sys.exit(f"{len(pz_cases) - hits} of {len(pz_cases)} cases have no recorded perfectz80 "\n'
     '                 f"trace in rz80/tests/event_sweep/pz80/: record them in RZ80 first")\n'),
    ('report: {os.path.relpath(os.path.join(OUT, \'report.md\'), ROOT)}',
     'report: {os.path.relpath(os.path.join(OUT, \'report.md\'), WS3)}'),
]

RUN_BASIC = [
    ('ROOT="$(cd "$(dirname "$0")/../.." && pwd)"',
     '# ws3 (scripts/sync_rz80.py): the ROMs and scripts from the rz80/ submodule,\n'
     '# the simulators from build/rz80/\n'
     'WS3="$(cd "$(dirname "$0")/../../.." && pwd)"\n'
     'ROOT="$WS3/rz80"'),
    ('BIN="$ROOT/build/bin/basicrunner"\n    SUITE_NAME="C model"',
     'echo "ws3 runs BASIC through the RTL and the chip\'s netlist only (no C model)" >&2; exit 2\n'
     '    BIN=""\n    SUITE_NAME="C model"'),
    ('BIN="$ROOT/build/obj_dir_basic/sim_basic"', 'BIN="$WS3/build/rz80/obj_dir_basic/sim_basic"'),
]

# the pin timing check on chip_top: its ports and pads, not z80_chip's
PIN_TIMING = [
    ('ADDR = [f"A[{i}]" for i in range(16)]\n'
     'DATA = [f"D[{i}]" for i in range(8)]\n'
     'CTRL = ["M1_n", "MREQ_n", "IORQ_n", "RD_n", "WR_n", "RFSH_n", "HALT_n", "BUSAK_n"]\n'
     'OUTS = ADDR + DATA + CTRL\n'
     'INS = DATA + ["WAIT_n", "INT_n", "NMI_n", "BUSRQ_n", "RESET_n"]\n'
     'GROUP = {"A": ADDR, "D": DATA}\n'
     '# pads with an output enable: pad instance names follow z80_chip.v\n'
     'OE_PADS = {p: "pad_" + p.replace("[", "").replace("]", "") for p in ADDR + DATA}\n'
     'OE_PADS.update({p: "pad_" + p for p in ["MREQ_n", "IORQ_n", "RD_n", "WR_n"]})',
     '# ws3 (scripts/sync_rz80.py): the pins are chip_top\'s pads (src/chip_core.sv):\n'
     '# bidir 0..7 D0..D7, 8..23 A0..A15, 24..31 M1 MREQ IORQ RD WR RFSH HALT BUSAK;\n'
     '# inputs 0..3 WAIT INT NMI BUSRQ; the datasheet\'s names map onto them (GROUP)\n'
     'CLK_PORT = "clk_PAD"\n'
     'ADDR = [f"bidir_PAD[{8 + i}]" for i in range(16)]\n'
     'DATA = [f"bidir_PAD[{i}]" for i in range(8)]\n'
     'CTRL_PIN = {"M1_n": 24, "MREQ_n": 25, "IORQ_n": 26, "RD_n": 27, "WR_n": 28, "RFSH_n": 29,\n'
     '            "HALT_n": 30, "BUSAK_n": 31}\n'
     'IN_PIN = {"WAIT_n": "input_PAD[0]", "INT_n": "input_PAD[1]", "NMI_n": "input_PAD[2]",\n'
     '          "BUSRQ_n": "input_PAD[3]", "RESET_n": "rst_n_PAD"}\n'
     'CTRL = [f"bidir_PAD[{i}]" for i in CTRL_PIN.values()]\n'
     'OUTS = ADDR + DATA + CTRL\n'
     'INS = DATA + list(IN_PIN.values())\n'
     'GROUP = {"A": ADDR, "D": DATA}\n'
     'GROUP.update({n: [f"bidir_PAD[{i}]"] for n, i in CTRL_PIN.items()})\n'
     'GROUP.update({n: [p] for n, p in IN_PIN.items()})\n'
     '# the pads with an output enable (A, D, MREQ IORQ RD WR): chip_top\'s bidir[i].pad\n'
     'OE_PADS = {f"bidir_PAD[{i}]": f"bidir\\\\[{i}\\\\].pad" for i in list(range(24)) + [25, 26, 27, 28]}\n'
     '\n\n'
     'def pad_instance(port):\n'
     '    """chip_top\'s pad instance of a port, as the netlist names it"""\n'
     '    m = re.match(r"(bidir|input)_PAD\\[(\\d+)\\]", port)\n'
     '    if m:\n'
     '        return f"{\'bidir\' if m.group(1) == \'bidir\' else \'inputs\'}[{m.group(2)}].pad"\n'
     '    return {"clk_PAD": "clk_pad", "rst_n_PAD": "rst_n_pad"}.get(port, port)'),
    ('          f"create_clock -name CLK -period {T} -waveform {{0 {TH}}} [get_ports CLK]",\n'
     '          "set_propagated_clock [get_clocks CLK]",\n'
     '          f"set_input_transition {edge} [get_ports CLK]",',
     '          f"create_clock -name CLK -period {T} -waveform {{0 {TH}}} [get_ports {CLK_PORT}]",\n'
     '          "set_propagated_clock [get_clocks CLK]",\n'
     '          f"set_input_transition {edge} [get_ports {CLK_PORT}]",'),
    ('        self.cell = {inst: cell for cell, inst in re.findall(r"^\\s*(\\w+)\\s+(pad_\\w+)\\s*\\(", nl, re.M)}',
     '        self.cell = {inst: cell for cell, inst in re.findall(r"^\\s*(\\w+)\\s+\\\\?(\\S*pad)\\s*\\(", nl, re.M)}'),
    ('        cell = self.cell.get("pad_" + port.replace("[", "").replace("]", ""))',
     '        cell = self.cell.get(pad_instance(port))'),
]

# the whole chip at transistor level (RZ80's asic/spice/chip.py) on chip_top:
# its ports for the Z80's pins, the template's PDK, ws3's RTL
CHIP_SPICE = [
    ("ROOT = os.path.dirname(os.path.dirname(HERE))",
     "ROOT = os.path.dirname(HERE)          # ws3 (scripts/sync_rz80.py): spice/ -> the repository"),
    ('PDK_ROOT = os.path.join(os.environ.get("CIEL_HOME", os.path.expanduser("~/.ciel")), "ciel",\n'
     '                        "gf180mcu/versions/54435919abffb937387ec956209f9cf5fd2dfbee/gf180mcuD")',
     '# ws3: the template\'s PDK (make clone-pdk)\n'
     'PDK_ROOT = os.path.join(os.environ.get("PDK_ROOT", os.path.join(ROOT, "gf180mcu")), os.environ.get("PDK", "gf180mcuD"))'),
    ('node = lambda p: "p_" + p.replace("[", "").replace("]", "").lower()\n',
     'node = lambda p: "p_" + p.replace("[", "").replace("]", "").lower()\n'
     '# ws3: the chip is chip_top; its ports for the Z80\'s pins (src/chip_core.sv). DVDD / DVSS\n'
     '# are the supply\'s (gf180mcu_fd_io shorts the domains), the unused inputs held low\n'
     'CHIP_PORT = {f"D[{i}]": f"bidir_PAD[{i}]" for i in range(8)}\n'
     'CHIP_PORT.update({f"A[{i}]": f"bidir_PAD[{8 + i}]" for i in range(16)})\n'
     'CHIP_PORT.update({p: f"bidir_PAD[{24 + k}]" for k, p in enumerate(\n'
     '    ["M1_n", "MREQ_n", "IORQ_n", "RD_n", "WR_n", "RFSH_n", "HALT_n", "BUSAK_n"])})\n'
     'CHIP_PORT.update({"WAIT_n": "input_PAD[0]", "INT_n": "input_PAD[1]", "NMI_n": "input_PAD[2]",\n'
     '                  "BUSRQ_n": "input_PAD[3]", "CLK": "clk_PAD", "RESET_n": "rst_n_PAD",\n'
     '                  "VDD": "VDD", "VSS": "VSS"})\n'
     '\n\n'
     'def chip_nodes(spice):\n'
     '    """the deck\'s nodes for chip_top\'s ports, in the extracted subcircuit\'s order"""\n'
     '    by_port = {v: node(k) for k, v in CHIP_PORT.items()}\n'
     '    by_port.update({"DVDD": node("VDD"), "DVSS": node("VSS")})\n'
     '    by_port.update({f"input_PAD[{i}]": "0" for i in range(4, 14)})\n'
     '    for line in open(spice).read().replace("\\n+", " ").splitlines():\n'
     '        t = line.split()\n'
     '        if len(t) > 2 and t[0].lower() == ".subckt" and t[1] == "chip_top":\n'
     '            missing = [p for p in t[2:] if p not in by_port]\n'
     '            if missing:\n'
     '                sys.exit(f"chip: chip_top ports with no node: {missing}")\n'
     '            return [by_port[p] for p in t[2:]]\n'
     '    sys.exit("chip: no .subckt chip_top in the extracted netlist")\n'),
    ("load z80_chip\n", "load chip_top\n"),
    ('    gds = os.path.abspath(gds or os.path.join(run, "final", "gds", "z80_chip.gds"))',
     '    gds = os.path.abspath(gds or os.path.join(run, "final", "gds", "chip_top.gds"))'),
    ('    rtl = os.path.join(ROOT, "rtl")\n', '    rtl = os.path.join(ROOT, "src", "rz80")\n'),
    ('    L = [f"* z80_chip at transistor level, GF180 {corner}: power-up, RESET, the program at 4 MHz",',
     '    L = [f"* chip_top (RZ80) at transistor level, GF180 {corner}: power-up, RESET, the program at 4 MHz",'),
    ('    L.append("Xchip " + " ".join(node(p) for p in PINS) + " z80_chip")',
     '    L.append("Xchip " + " ".join(chip_nodes(os.path.join(work, "z80_chip.spice"))) + " chip_top")'),
    ("{FONT}>z80_chip, GF180 layout extracted to transistors (Magic), ",
     "{FONT}>ws3 chip_top (RZ80), GF180 layout extracted to transistors (Magic), "),
    ('    title = f"z80_chip at transistor level (GF180 {corner}): power-up, RESET, the program at 4 MHz"',
     '    title = f"RZ80, ws3 chip_top at transistor level (GF180 {corner}): power-up, RESET, the program at 4 MHz"'),
]

PADS_SPICE = [
    ('LIBRELANE = "github:librelane/librelane/3.0.14"                             # Magic 8.3.623',
     '# ws3 (scripts/sync_rz80.py): Magic from the template\'s LibreLane, as its PDK\n'
     'LIBRELANE = "github:librelane/librelane/99148a9c1e648cdfdb9d7b772481af32e0dfbe8b"'),
]

# (source, path in RZ80, path in ws3, patches)
RTL = ["z80_top.v", "z80_core.v", "z80_timing.v", "z80_pla.v", "z80_execute.v",
       "z80_regfile.v", "z80_addr.v", "z80_alu.v", "z80_ctl.vh", "z80_defs.vh"]
FILES = [("main", "rtl/" + f, "src/rz80/" + f, []) for f in RTL] + [
    # iverilog testbenches of the RTL
    ("main", "tests/iverilog/tb_bus_controls.v", "tests/rz80/iverilog/tb_bus_controls.v", []),
    ("main", "tests/iverilog/tb_wait_edge.v",    "tests/rz80/iverilog/tb_wait_edge.v", []),
    ("main", "tests/iverilog/tb_wait_write.v",   "tests/rz80/iverilog/tb_wait_write.v", []),
    ("main", "tests/iverilog/tb_int_ack.v",      "tests/rz80/iverilog/tb_int_ack.v", []),
    ("main", "tests/iverilog/tb_event_sweep.v",  "tests/rz80/iverilog/tb_event_sweep.v", []),
    # their drivers: FUSE (and the X / Y corpus) and the pin sweep
    ("main", "scripts/compare_fuse_rtl.py", "tests/rz80/scripts/compare_fuse_rtl.py", COMPARE_FUSE_RTL),
    ("main", "scripts/gen_fuse_tb.py",      "tests/rz80/scripts/gen_fuse_tb.py", GEN_FUSE_TB),
    ("main", "scripts/event_sweep.py",      "tests/rz80/scripts/event_sweep.py", EVENT_SWEEP),
    # Verilator harnesses of the long suites, and the ZEX test splitter
    ("main", "tests/verilator/sim_zex.cpp",     "tests/rz80/verilator/sim_zex.cpp", []),
    ("main", "tests/verilator/sim_z80test.cpp", "tests/rz80/verilator/sim_z80test.cpp", []),
    ("main", "tests/verilator/sim_basic.cpp",   "tests/rz80/verilator/sim_basic.cpp", []),
    ("main", "scripts/zex_make_subset.py",      "tests/rz80/scripts/zex_make_subset.py", []),
    ("main", "tests/basic/run_basic_tests.sh",  "tests/rz80/basic/run_basic_tests.sh", RUN_BASIC),
    # the sigrok KC85 captures' decoder (the real Z80's bus, cycle by cycle)
    ("main", "scripts/sigrok_z80_decode.py",    "tests/rz80/scripts/sigrok_z80_decode.py", []),
    # the chip flows' sign-off summary
    ("asic", "asic/summary.py",                 "tests/rz80/scripts/summary.py", []),
    # the NMOS Z80's AC characteristics (Zilog PS0178), for the pin timing check
    ("main", "asic/timing/z8400_nmos.json",     "timing/z8400_nmos.json", []),
    ("main", "asic/timing/pin_timing.py",       "timing/pin_timing.py", PIN_TIMING),
    # the pads simulated at transistor level: Liberty tables to the datasheet's
    # 100 pF and its measuring levels (RZ80's asic/spice/pads.py)
    ("main", "asic/spice/pads/gf180mcu/pads.json", "spice/pads/gf180mcu/pads.json", []),
    ("main", "asic/spice/pads/gf180mcu/gf180mcu_fd_io__tt_025C_5v00.lib", "spice/pads/gf180mcu/gf180mcu_fd_io__tt_025C_5v00.lib", []),
    ("main", "asic/spice/pads/gf180mcu/gf180mcu_fd_io__ss_125C_4v50.lib", "spice/pads/gf180mcu/gf180mcu_fd_io__ss_125C_4v50.lib", []),
    ("main", "asic/spice/pads/gf180mcu/gf180mcu_fd_io__ff_n40C_5v50.lib", "spice/pads/gf180mcu/gf180mcu_fd_io__ff_n40C_5v50.lib", []),
    # the whole chip at transistor level (spice/README.md)
    ("main", "asic/spice/chip.py",       "spice/chip.py", CHIP_SPICE),
    ("main", "asic/spice/pads.py",       "spice/pads.py", PADS_SPICE),
    ("main", "asic/spice/svgplot.py",    "spice/svgplot.py", []),
    ("main", "asic/spice/tb_chip_ref.v", "spice/tb_chip_ref.v", []),
    # the licences of what is copied
    ("main", "LICENSES/CERN-OHL-W-2.0.txt",     "LICENSES/CERN-OHL-W-2.0.txt", []),
    ("main", "LICENSES/MIT.txt",                "LICENSES/MIT.txt", []),
]

# --- the sync ------------------------------------------------------------------

def git(*args, check=True):
    return subprocess.run(["git", "-C", SUB] + list(args), capture_output=True, check=check)

def commit(ref):
    if ref == "main":
        return git("rev-parse", "HEAD").stdout.decode().strip()
    if git("cat-file", "-e", ASIC_COMMIT + "^{commit}", check=False).returncode:
        git("fetch", "--quiet", "--depth=1", "origin", ASIC_COMMIT)
    return ASIC_COMMIT

def source(ref, path):
    return git("show", f"{commit(ref)}:{path}").stdout

def patched(text, patches, where):
    s = text.decode()
    for old, new in patches:
        n = s.count(old)
        if n != 1:
            sys.exit(f"sync_rz80: {where}: a patch matches {n} times, not once -- "
                     f"RZ80 changed the text; update the patch:\n{old[:200]}")
        s = s.replace(old, new)
    return s.encode()

def outputs():
    out = {}
    for ref, src, dst, patches in FILES:
        out[dst] = patched(source(ref, src), patches, src) if patches else source(ref, src)
    main = commit("main")
    log = git("log", "-1", "--format=%cs %s", main).stdout.decode().strip()
    rows = "\n".join(f"| `{dst}` | `{src}` | {'main' if ref == 'main' else 'asic-gf180mcu'} "
                     f"| {'patched' if patches else 'copied'} |" for ref, src, dst, patches in FILES)
    out["tests/rz80/README.md"] = f"""# Files from RZ80

Written by `scripts/sync_rz80.py`; do not edit. RZ80 is the `rz80/`
submodule, [{REPO}]({REPO}):

| | commit |
|---|---|
| main (the submodule) | [`{main[:7]}`]({REPO}/commit/{main}) ({log}) |
| asic-gf180mcu (the chip flows' glue) | [`{ASIC_COMMIT[:7]}`]({REPO}/commit/{ASIC_COMMIT}) |

| ws3 | RZ80 | from | |
|---|---|---|---|
{rows}

"patched" files differ from RZ80's by the exact text replacements listed
in `scripts/sync_rz80.py`: paths (their data from the submodule, the RTL
from `src/rz80/`, builds in `build/rz80/`), and perfectz80 only as RZ80
recorded it. The C model, the perfectz80 simulator and the reference
emulators are not part of ws3.
""".encode()
    out["src/rz80/README.md"] = f"""# RZ80

The Z80 core: `rtl/` of [rejunity/z80-from-schematics]({REPO}) at
[`{main[:7]}`]({REPO}/commit/{main}), unchanged, copied by
`scripts/sync_rz80.py` from the `rz80/` submodule.
Licensed CERN-OHL-W-2.0 (each file's SPDX header); see `HARDWARE_NOTICE.md`
at the top of this repository for the notices a product must carry.

`z80_top` is the chip-level Z80 that `../chip_core.sv` puts on the pads.
""".encode()
    return out

def main():
    check = sys.argv[1:] == ["--check"]
    if sys.argv[1:] not in ([], ["--check"]):
        sys.exit(__doc__)
    if not os.path.exists(os.path.join(SUB, ".git")):
        sys.exit("sync_rz80: rz80/ is not checked out (git submodule update --init)")
    bad = []
    for dst, data in outputs().items():
        path = os.path.join(WS3, dst)
        old = open(path, "rb").read() if os.path.exists(path) else None
        if old == data:
            continue
        bad.append(dst)
        if not check:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            open(path, "wb").write(data)
            if data.startswith(b"#!"):
                os.chmod(path, 0o755)
    if check and bad:
        print("sync_rz80: out of step with rz80/ (run scripts/sync_rz80.py):\n  " + "\n  ".join(bad))
        return 1
    print(f"sync_rz80: {'checked' if check else 'wrote'} {len(outputs())} files"
          + (f", {len(bad)} changed" if bad and not check else ""))
    return 0

if __name__ == "__main__":
    sys.exit(main())
