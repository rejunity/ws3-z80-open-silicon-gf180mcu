# SPDX-FileCopyrightText: © 2026 Renaldas Zioma
# SPDX-License-Identifier: Apache-2.0
"""Whole programs on the chip (z80_system.v: the RTL, or the gate-level netlist with
GL=1), with the memory, the console and the end of the run in Verilog: cocotb loads
the program, waits for the end and checks what it printed.

    python3 system_tb.py [test ...]      (make sim-system / sim-system-gl)

test__prelim: Frank Cringle's preliminary Z80 tests (prelim.com, read from the rz80/
submodule, GPL-2.0-or-later), the ones ZEXDOC / ZEXALL rely on, under a CP/M of a
few bytes: BDOS functions 2 and 9 in Z80 code at FF00h printing through the console
address, the warm boot (a jump to 0000h) ending the run. It must print its banner,
"Preliminary tests complete", and nothing else.
"""
import os
import sys
from pathlib import Path

import cocotb
from cocotb.triggers import RisingEdge

HERE = Path(__file__).resolve().parent
WS3 = HERE.parent
BUILD = WS3 / "build" / "system"
gl = bool(os.getenv("GL"))

# BDOS at FF00h (0005h jumps there): C=2 prints E, C=9 the string at DE up to '$',
# through the console address FFF0h (z80_system.v)
BDOS = bytes.fromhex("79" "FE02" "2805" "FE09" "2806" "C9"     # LD A,C / CP 2 / JR Z,chr / CP 9 / JR Z,str / RET
                     "7B" "32F0FF" "C9"                        # chr: LD A,E / LD (FFF0),A / RET
                     "1A" "FE24" "C8" "32F0FF" "13" "18F6")    # str: LD A,(DE) / CP '$' / RET Z / LD (FFF0),A / INC DE / JR str


def cpm_image(com):
    """The memory of a CP/M machine with `com` loaded at 0100h: 0000h jumps to the
    program (and, reached again, ends the run), 0005h to the BDOS."""
    mem = {0x0000: 0xC3, 0x0001: 0x00, 0x0002: 0x01, 0x0005: 0xC3, 0x0006: 0x00, 0x0007: 0xFF}
    mem.update({0x0100 + i: b for i, b in enumerate(Path(com).read_bytes())})
    mem.update({0xFF00 + i: b for i, b in enumerate(BDOS)})
    return mem


def write_hex(mem, path):
    lines, last = [], None
    for a in sorted(mem):
        if last is None or a != last + 1:
            lines.append(f"@{a:04x}")
        lines.append(f"{mem[a]:02x}")
        last = a
    Path(path).write_text("\n".join(lines) + "\n")


async def run_to_end(dut):
    """Wait for z80_system.v's end of the program; returns what it printed."""
    await RisingEdge(dut.done)
    text = Path(cocotb.plusargs["console"]).read_text(errors="replace")
    assert not int(dut.timeout.value), f"no end within +max_cycles={cocotb.plusargs['max_cycles']}: {text!r}"
    return text


@cocotb.test()
async def test__prelim(dut):
    text = await run_to_end(dut)
    dut._log.info(f"console: {text!r}")
    assert text.replace("\r", "").strip() == "Preliminary tests complete", text


# --- runner ------------------------------------------------------------------------

def runner(tests):
    from cocotb_tools.runner import get_runner
    pdk_root = Path(os.getenv("PDK_ROOT", WS3 / "gf180mcu"))
    pdk = os.getenv("PDK", "gf180mcuD")
    scl = os.getenv("SCL", "gf180mcu_fd_sc_mcu7t5v0")
    pad = os.getenv("PAD", "gf180mcu_fd_io")
    libs = pdk_root / pdk / "libs.ref"
    defines = {"SLOT_0P5X0P5": True, f"PDK_{pdk}": True, f"SCL_{scl}": True, f"PAD_{pad}": True,
               "SRAM_gf180mcu_fd_ip_sram": True}
    sources = [HERE / "z80_system.v", HERE / "chip_shim.v", libs / pad / "verilog" / f"{pad}.v"]
    sources += [WS3 / f"ip/gf180mcu_ws_ip__{m}/vh/gf180mcu_ws_ip__{m}.v"
                for m in ("logo", "marker", "qrcode_id", "shuttle_id", "project_id")]
    if gl:
        sources += [libs / scl / "verilog" / f"{scl}.v", libs / scl / "verilog" / "primitives.v",
                    WS3 / "final/pnl/chip_top.pnl.v"]
        defines.update({"FUNCTIONAL": True, "USE_POWER_PINS": True, "GL": True})
    else:
        sources += [WS3 / "src/chip_top.sv", WS3 / "src/chip_core.sv"] + sorted((WS3 / "src/rz80").glob("*.v"))
    build = BUILD / ("gl" if gl else "rtl")
    r = get_runner("icarus")
    r.build(sources=sources, hdl_toplevel="z80_system", defines=defines, always=True,
            includes=[WS3 / "src", WS3 / "src/rz80"], build_dir=build, timescale=("1ns", "1ps"))
    programs = {"test__prelim": (cpm_image(WS3 / "rz80/tests/zex/prelim.com"), 20_000_000)}
    failed = 0
    for t in tests or list(programs):
        mem, max_cycles = programs[t]
        write_hex(mem, build / f"{t}.hex")
        xml = r.test(hdl_toplevel="z80_system", test_module="system_tb", test_filter=f"\\.{t}$",
                     build_dir=build, test_dir=HERE, results_xml=str(build / f"{t}.xml"),
                     plusargs=[f"+prog={build / f'{t}.hex'}", f"+console={build / f'{t}.txt'}",
                               f"+max_cycles={max_cycles}"])
        failed += "<failure" in Path(xml).read_text()
    return failed


if __name__ == "__main__":
    sys.exit(1 if runner(sys.argv[1:]) else 0)
