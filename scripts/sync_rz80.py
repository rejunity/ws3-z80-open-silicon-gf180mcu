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
    # ws3: the flow's SDC (make sdc): one clock at the CLK pin at the flow's
    # period, the pins at the strictest of the 4/6/8 MHz grades
    (r'''def write_sdc(con, path, load, edge):
    c, g = con.clk, con.g
    T, TH = c["period"], c["th"]
    names = lambda ps: "{" + " ".join(n for p in ps for n in GROUP.get(p, [p])) + "}"
    L = [f"# Generated by asic/timing/pin_timing.py --write-sdc (grade {g} MHz); do not edit.",
         "# z80_chip's pins against the NMOS Z80's AC characteristics: Zilog",
         f"# PS0178, Z8400 (NMOS) table, {g} MHz column (z8400_nmos.json). Clock",
         f"# {T:g} ns, {c['twch']:g}/{c['twcl']:g} ns high/low, {edge:g} ns edges; {load:g} pF loads.",
         "current_design $::env(DESIGN_NAME)",
         f"create_clock -name CLK -period {T:g} -waveform {{0 {TH:g}}} [get_ports CLK]",
         f"set_input_transition {edge:g} [get_ports CLK]",
         "# the CLK pin's edges, for the I/O constraints: the CLK pad and the clock",
         "# tree are part of every I/O path, as in the datasheet's measurements",
         f"create_clock -name PIN -period {T:g} -waveform {{0 {TH:g}}}",
         "set_false_path -rise_from [get_clocks CLK] -fall_to [get_clocks PIN]",
         "set_false_path -fall_from [get_clocks CLK] -rise_to [get_clocks PIN]",
         "set_false_path -rise_from [get_clocks PIN] -fall_to [get_clocks CLK]",
         "set_false_path -fall_from [get_clocks PIN] -rise_to [get_clocks CLK]",
         f"set_load {load / 1:g} [get_ports {names(['A', 'D'] + CTRL)}]",
         f"set_input_transition {edge:g} [get_ports {names(['D', 'WAIT_n', 'INT_n', 'NMI_n', 'BUSRQ_n', 'RESET_n'])}]",
         "# NMI is edge-triggered and asynchronous (the pulse catcher in z80_top)",
         "set_false_path -from [get_ports NMI_n]",
         "# RESET floats the address bus directly (z80_chip.v), unclocked",
         "set_false_path -from [get_ports RESET_n] -to [get_ports {A[*]}]",
         "# MREQ IORQ RD WR float while BUSACK is low and come back high: their",
         "# pads, enabled by z80_top's busack_n, never turn on driving low",
         "set_false_path -rise_through [get_pins u_top/busack_n] -fall_to [get_ports {MREQ_n IORQ_n RD_n WR_n}]",
         "# read data is held until RD (IORQ in INTA) rises, not 0 ns past the",
         "# sampling edge (P16 ThD(RDr)): pin_timing.py checks the replica's hold",
         "# against its own RD / IORQ rise; the flow does not repair a hold the",
         "# datasheet does not ask for",
         "set_false_path -hold -from [get_ports {D[*]}]",
         "set_max_fanout $::env(MAX_FANOUT_CONSTRAINT) [current_design]",
         "if { [info exists ::env(MAX_TRANSITION_CONSTRAINT)] } { set_max_transition $::env(MAX_TRANSITION_CONSTRAINT) [current_design] }",
         "set_clock_uncertainty $::env(CLOCK_UNCERTAINTY_CONSTRAINT) [get_clocks CLK]",
         "set_timing_derate -early [expr 1 - $::env(TIME_DERATING_CONSTRAINT) / 100.0]",
         "set_timing_derate -late [expr 1 + $::env(TIME_DERATING_CONSTRAINT) / 100.0]",
         "# outputs: at most D after the CLK pin's edge (max T - D), and not before it"]
    for ports, ref, trans, pids in SDC_OUT:
        d = min(con.limit(i) for i in pids)
        cf = " -clock_fall" if ref == "fall" else ""
        tr = f" -{trans}" if trans else ""
        sym = ", ".join(f"P{i} {con.req[i]['symbol']}" for i in pids)
        L.append(f"set_output_delay -add_delay -clock PIN{cf}{tr} -max {T - d:g} [get_ports {names(ports)}]   ;# {sym} <= {d:g}")
        L.append(f"set_output_delay -add_delay -clock PIN{cf}{tr} -min 0 [get_ports {names(ports)}]")
    L.append("# inputs: valid S before the sampling edge (max T - S), held H after it")
    for ports, ref, sp, hp in SDC_IN:
        cf = " -clock_fall" if ref == "fall" else ""
        S_, H_ = con.limit(sp), con.limit(hp)
        L.append(f"set_input_delay -add_delay -clock PIN{cf} -max {T - S_:g} [get_ports {names(ports)}]   ;# P{sp} {con.req[sp]['symbol']} = {S_:g}")
        L.append(f"set_input_delay -add_delay -clock PIN{cf} -min {H_:g} [get_ports {names(ports)}]   ;# P{hp} {con.req[hp]['symbol']} = {H_:g}")
    open(path, "w").write("\n".join(L) + "\n")


''',
     r'''# ws3: the pads every I/O path goes through (src/chip_top.sv), named one by
# one: OpenROAD's database matches no wildcard inside escaped brackets
pad_pins = lambda ports, pin: [pad_instance(p).replace("[", "\\[").replace("]", "\\]") + "/" + pin for p in ports]
# ws3: chip_top's pad cells (src/chip_top.sv): CLK and RESET Schmitt, the
# other inputs CMOS, the bus bi_t
PAD_CELL = {"clk_PAD": "gf180mcu_fd_io__in_s", "rst_n_PAD": "gf180mcu_fd_io__in_s"}
PAD_CELL.update({p: "gf180mcu_fd_io__in_c" for p in IN_PIN.values() if p.startswith("input_PAD")})
PAD_CELL.update({p: "gf180mcu_fd_io__bi_t" for p in OUTS})
PAD_LOAD = 0.1      # pF on an input pad's Y (CLK: the CTS root buffer and its wire)


class SimPads:
    """RZ80's transistor-level pads (spice/pads/gf180mcu/pads.json), per corner:
    the datasheet's measuring levels against STA's 50 %, and the input pads'
    delays at any edge"""

    def __init__(self, load):
        doc = json.load(open(os.path.join(SPICE_PADS, "gf180mcu", "pads.json")))
        self.corners = doc["corners"]
        c = doc["conditions"]
        self.vil, self.vih = c["vil_V"], c["vih_V"]
        k = min(max(bisect.bisect_left(c["loads_pF"], load), 1), len(c["loads_pF"]) - 1)
        f = (load - c["loads_pF"][k - 1]) / (c["loads_pF"][k] - c["loads_pF"][k - 1])
        self.out = {}       # (corner, trans): 50 % -> 1.5 V at `load`, the latest of the pad's input slews
        for name, cc in self.corners.items():
            for arc, trans in (("data", "rise"), ("data", "fall"), ("enable", "1"), ("enable", "0")):
                for row in cc["cells"]["gf180mcu_fd_io__bi_t"][arc][trans]:
                    off = [r["dlev"] - r["d50"] for r in row]
                    t = "rise" if trans in ("rise", "1") else "fall"
                    v = off[k - 1] + f * (off[k] - off[k - 1])
                    self.out[name, t] = max(self.out.get((name, t), v), v)

    def d_in(self, corner, cell, trans, edge):
        """an input pad's delay, PAD 50 % to Y 50 %, on `edge` ns edges (linear between the simulated ones)"""
        i = self.corners[corner]["cells"][cell]["input"]
        li = min(range(len(i["loads"])), key=lambda j: abs(i["loads"][j] - PAD_LOAD))
        e, col = i["edges"], [row[li] for row in i[trans]["d50"]]
        j = min(max(bisect.bisect_left(e, edge), 1), len(e) - 1)
        return col[j - 1] + (edge - e[j - 1]) / (e[j] - e[j - 1]) * (col[j] - col[j - 1])

    def level(self, corner, kind, trans, edge):
        """ns from the input's datasheet level to its 50 % on `edge` ns edges,
        positive when the 50 % comes later: setup -- valid from VIH rising,
        VIL falling; hold -- the old value until VIL rising, VIH falling"""
        vio = self.corners[corner]["vio"]
        half, slope = vio / 2, 0.8 * vio / edge
        lv = self.vih if (kind, trans) in (("setup", "rise"), ("hold", "fall")) else self.vil
        return (half - lv) / slope * (1 if trans == "rise" else -1)


def write_sdc(path, load, edge, period, grades, hold_margin=0.0):
    """ws3's flow SDC: one clock, CLK, at the CLK pin at the flow's `period`
    (the core's goal); every pin parameter of SDC_OUT / SDC_IN at the strictest
    of `grades` -- each at its own AC test edge, the datasheet's levels and
    every simulated corner -- in absolute ns from the CLK pin's edges, for an
    STA with `edge` ns edges; every sampled input's hold `hold_margin` ns past
    the datasheet's"""
    cons = {g: Contract(g, load) for g in grades}
    sp = SimPads(load)
    E, T = edge, period
    sym = lambda pid: cons[grades[0]].req[pid]["symbol"]
    num = lambda x: f"{round(x, 3):g}"
    gs = "/".join(grades)
    names = lambda ps: "{" + " ".join(n for p in ps for n in GROUP.get(p, [p])) + "}"
    pins = lambda ps: [n for p in ps for n in GROUP.get(p, [p])]
    strobes = pins(["MREQ_n", "IORQ_n", "RD_n", "WR_n"])
    clk = PAD_CELL[CLK_PORT]
    # the CLK pad at a grade's edge against this STA's: later by dc (ns)
    dc = lambda k, ref, g: sp.d_in(k, clk, ref, cons[g].clk["tr"]) - sp.d_in(k, clk, ref, E)
    cases = [(g, k) for g in grades for k in sp.corners]
    L = [f"# Generated by timing/pin_timing.py --write-sdc (grades {gs} MHz, {T:g} ns); do not edit.",
         "# chip_top against the NMOS Z80's AC characteristics: Zilog PS0178, Z8400",
         "# (NMOS) table (z8400_nmos.json). Each pin parameter at the strictest of the",
         f"# {gs} MHz grades, each at its own AC test conditions -- its edges ("
         + ", ".join(f"{cons[g].clk['tr']:g}" for g in grades) + " ns),",
         "# inputs valid at 2.0 / 0.8 V, outputs at 1.5 V into "
         f"{load:g} pF -- at every corner, the pads as",
         "# RZ80 simulated them at transistor level (spice/pads/gf180mcu/), in ns from",
         f"# the CLK pin's 50 % for this STA's {E:g} ns edges. One clock, CLK, at the CLK pin:",
         f"# {T:g} ns ({1000 / T:g} MHz), the core's goal, timed on those edges (on 15 ns ones",
         "# the Schmitt CLK pad delays the clock's fall some 6 ns more than its rise: nothing",
         "# at 4-8 MHz, a quarter of a half-cycle at 20 MHz). The parameters that depend",
         "# on the clock (pulse widths, separations) are pin_timing.py's, at each grade's",
         "# own clock (make pin-timing).",
         "current_design $::env(DESIGN_NAME)",
         "# at the CLK pin: the CLK pad and the clock tree are in every path, the I/O",
         "# ones as in the datasheet's measurements",
         f"create_clock -name CLK -period {T:g} -waveform {{0 {T / 2:g}}} [get_ports {CLK_PORT}]",
         f"set_input_transition {E:g} [get_ports {CLK_PORT}]",
         f"set_load {load:g} [get_ports {names(['A', 'D'] + CTRL)}]",
         f"set_input_transition {E:g} [get_ports {names(['D', 'WAIT_n', 'INT_n', 'NMI_n', 'BUSRQ_n', 'RESET_n'])}]",
         "# each pin parameter is from one CLK edge: an output launched on the other",
         "# edge, an input caught on it, is not held to it (RZ80's z80_chip SDC keeps",
         "# them apart with a virtual clock for the pins; here, the paths through the",
         "# pads)",
         "set out_pads [get_pins -quiet {" + " ".join(pad_pins(OUTS, "A") + pad_pins(OUTS, "OE")) + "}]",
         "set in_pads [get_pins -quiet {" + " ".join(pad_pins(list(dict.fromkeys(INS)), "Y")) + "}]",
         "foreach pads [list $out_pads $in_pads] {",
         "    if { [llength $pads] > 0 } {",
         "        set_false_path -rise_from [get_clocks CLK] -through $pads -fall_to [get_clocks CLK]",
         "        set_false_path -fall_from [get_clocks CLK] -through $pads -rise_to [get_clocks CLK]",
         "    }",
         "}",
         "# NMI is edge-triggered and asynchronous (the pulse catcher in z80_top)",
         f"set_false_path -from [get_ports {names(['NMI_n'])}]",
         "# (z80_chip's RESET -> address false path has no counterpart: chip_top's",
         "# address pads follow z80_top's addr_drive, which RESET reaches only through",
         "# its rising-edge sampler)",
         "# MREQ IORQ RD WR float in a bus grant only and come back high: their",
         "# pads, enabled by z80_top's ctl_drive, never turn on driving low",
         "set strobe_oe [get_pins -quiet {" + " ".join(f"{OE_PADS[p]}/OE" for p in strobes) + "}]",
         "if { [llength $strobe_oe] > 0 } { set_false_path -rise_through $strobe_oe "
         f"-fall_to [get_ports {names(['MREQ_n', 'IORQ_n', 'RD_n', 'WR_n'])}] }}",
         "# read data is held until RD (IORQ in INTA) rises, not 0 ns past the",
         "# sampling edge (P16 ThD(RDr)): pin_timing.py checks the replica's hold",
         "# against its own RD / IORQ rise; the flow does not repair a hold the",
         "# datasheet does not ask for",
         f"set_false_path -hold -from [get_ports {names(['D'])}]",
         "# the data pads' input enables follow the CPU's data drive: the input",
         "# buffers turn on when the CPU stops driving the bus, a half cycle or more",
         "# before the next read samples the pads; IE -> Y is no path the Z80 uses",
         "set ie_pins [get_pins -quiet -hierarchical */IE]",
         "if { [llength $ie_pins] > 0 } { set_false_path -through $ie_pins }",
         "# no edge, load or fanout limit on the design: OpenSTA would hold every",
         "# pin to it, the pads' board side too, which drives and takes the",
         "# datasheet's 100 pF and slow edges. The core's limits (the PDK's",
         "# MAX_TRANSITION / MAX_CAPACITANCE / MAX_FANOUT_CONSTRAINT) are in the",
         "# standard cells' libraries (scripts/cell_limits.py), the pads' range in",
         "# theirs (spice/pads/)",
         "set_clock_uncertainty $::env(CLOCK_UNCERTAINTY_CONSTRAINT) [get_clocks CLK]",
         "set_clock_transition $::env(CLOCK_TRANSITION_CONSTRAINT) [get_clocks CLK]",
         "set_timing_derate -early [expr 1 - $::env(TIME_DERATING_CONSTRAINT) / 100.0]",
         "set_timing_derate -late [expr 1 + $::env(TIME_DERATING_CONSTRAINT) / 100.0]",
         "# ideal before CTS, propagated after (LibreLane's OPENLANE_SDC_IDEAL_CLOCKS)",
         "if { [info exists ::env(OPENLANE_SDC_IDEAL_CLOCKS)] && $::env(OPENLANE_SDC_IDEAL_CLOCKS) } {",
         "    unset_propagated_clock [get_clocks CLK]",
         "} else {",
         "    set_propagated_clock [get_clocks CLK]",
         "}",
         "# outputs: at 1.5 V at most D after the CLK pin's edge, and not before it:",
         "# max T - D + (50 % -> 1.5 V) + (the CLK pad at the grade's edge - at this",
         "# STA's), the strictest grade and corner; min the same CLK pad term"]
    for ports, ref, trans, pids in SDC_OUT:
        cf = " -clock_fall" if ref == "fall" else ""
        d4 = {g: min(cons[g].limit(i) for i in pids) for g in grades}
        what = ", ".join(f"P{i} {sym(i)}" for i in pids)
        for t in ([trans] if trans else ["rise", "fall"]):
            od, gw = max((T - d4[g] + sp.out[k, t] + dc(k, ref, g), g) for g, k in cases)
            L.append(f"set_output_delay -add_delay -clock CLK{cf} -{t} -max {num(od)} "
                     f"[get_ports {names(ports)}]   ;# {what} <= {d4[gw]:g} ({gw} MHz)")
        tr = f" -{trans}" if trans else ""
        L.append(f"set_output_delay -add_delay -clock CLK{cf}{tr} -min {num(min(dc(k, ref, g) for g, k in cases))} "
                 f"[get_ports {names(ports)}]")
    L += ["# inputs: valid S before the sampling edge, held H after it, at the levels:",
          "# max T - S, min H, each + (level -> 50 %) + (the input pad at the grade's",
          "# edge - at this STA's) - (the CLK pad likewise), the strictest grade and corner"]
    if hold_margin:
        L += [f"# and min H - {hold_margin:g} ns: every sampled input held {hold_margin:g} ns more than the",
              "# datasheet asks, a design margin (its own hold is the very edge, 0 ns)"]
    for ports, ref, sp_, hp in SDC_IN:
        cf = " -clock_fall" if ref == "fall" else ""
        cell = PAD_CELL[pins(ports)[0]]
        for t in ("rise", "fall"):
            di = lambda k, g: sp.d_in(k, cell, t, cons[g].clk["tr"]) - sp.d_in(k, cell, t, E)
            mx, gs_ = max((T - cons[g].limit(sp_) + sp.level(k, "setup", t, cons[g].clk["tr"]) + di(k, g) - dc(k, ref, g), g)
                          for g, k in cases)
            mn, gh = min((cons[g].limit(hp) + sp.level(k, "hold", t, cons[g].clk["tr"]) + di(k, g) - dc(k, ref, g), g)
                         for g, k in cases)
            mn -= hold_margin   # the input may change this much sooner: a harder hold
            L.append(f"set_input_delay -add_delay -clock CLK{cf} -{t} -max {num(mx)} "
                     f"[get_ports {names(ports)}]   ;# P{sp_} {sym(sp_)} = {cons[gs_].limit(sp_):g} ({gs_} MHz)")
            L.append(f"set_input_delay -add_delay -clock CLK{cf} -{t} -min {num(mn)} "
                     f"[get_ports {names(ports)}]   ;# P{hp} {sym(hp)} = {cons[gh].limit(hp):g} ({gh} MHz)"
                     + (f" - {hold_margin:g} margin" if hold_margin else ""))
    open(path, "w").write("\n".join(L) + "\n")


'''),
    (r'''    ap.add_argument("--write-sdc", metavar="FILE", help="write the flow's SDC for this grade instead (RUN is ignored)")
    a = ap.parse_args()
    if a.write_sdc:
        con = Contract(a.grade, a.load)
        write_sdc(con, a.write_sdc, a.load, a.edge if a.edge is not None else con.clk["tr"])
        return 0
''',
     r'''    ap.add_argument("--write-sdc", metavar="FILE", help="write the flow's SDC instead (RUN is ignored): one "
                    "clock at --period, the pins at the strictest of --grades")
    ap.add_argument("--hold-margin", type=float, default=0.0, help="--write-sdc: every sampled input held this "
                    "many ns past the datasheet's hold (a design margin)")
    ap.add_argument("--period", type=float, default=50.0, help="--write-sdc: the clock, ns (the core's goal)")
    ap.add_argument("--grades", default="4,6,8", help="--write-sdc: the grades whose strictest limits the pins get")
    a = ap.parse_args()
    if a.write_sdc:
        grades = [g for g in a.grades.split(",") if g]
        write_sdc(a.write_sdc, a.load, a.edge if a.edge is not None else Contract(grades[0], a.load).clk["tr"],
                  a.period, grades, a.hold_margin)
        return 0
'''),
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
    # the breakpoints over each clock edge, 1 ns longer: ws3's flat clock tree
    # reaches its flip-flops 1.4-2.1 ns after clk_pad/Y (tt, the flow's STA),
    # up to a nanosecond later than RZ80's leaves follow their root
    ('CLK_ROOT = {"tt": (2.9, 2.1), "ss": (4.3, 3.5), "ff": (2.1, 1.4)}',
     'CLK_ROOT = {"tt": (3.9, 3.1), "ss": (5.3, 4.5), "ff": (3.1, 2.4)}   # ws3: RZ80\'s + 1 ns'),
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
    # the template's PDK (make clone-pdk: --pdk-root gf180mcu/ciel)
    ('"root": "gf180mcu/versions/54435919abffb937387ec956209f9cf5fd2dfbee/gf180mcuD",',
     '"root": "gf180mcu/versions/792ef67037d74c8c51811eab3ce23cf793491296/gf180mcuD",   # ws3: the template\'s'),
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
    ("main", "tests/iverilog/tb_z80.v",          "tests/rz80/iverilog/tb_z80.v", []),
    ("main", "tests/iverilog/tb_z80_netlist.v",  "tests/rz80/iverilog/tb_z80_netlist.v", []),
    # their drivers: FUSE (and the X / Y corpus) and the pin sweep
    ("main", "scripts/compare_fuse_rtl.py", "tests/rz80/scripts/compare_fuse_rtl.py", COMPARE_FUSE_RTL),
    ("main", "scripts/gen_fuse_tb.py",      "tests/rz80/scripts/gen_fuse_tb.py", GEN_FUSE_TB),
    # the pin sweep and the trace programs against perfectz80's recordings: RZ80's
    # scripts as they are, pointed at ws3's builds and the submodule's
    # recordings by their environment overrides (EVENT_SWEEP_TB_VVP,
    # EVENT_SWEEP_PZ80; TB_VVP, TB_NETLIST_VVP, PZ80_TRACES)
    ("main", "scripts/event_sweep.py",      "tests/rz80/scripts/event_sweep.py", []),
    ("main", "scripts/compare_signal_timing.py", "tests/rz80/scripts/compare_signal_timing.py", []),
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
from `src/rz80/`, builds in `build/rz80/`) and chip_top's ports. The rest
are RZ80's own; the Makefile points them at ws3's builds and at the
submodule's data through their environment overrides. perfectz80's side of
every comparison is RZ80's recordings (`--recorded`, `--recorded-only`): the
C model, the perfectz80 simulator and the reference emulators are not part
of ws3.
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
