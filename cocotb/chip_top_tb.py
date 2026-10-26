# SPDX-FileCopyrightText: © 2025 Project Template Contributors
# SPDX-License-Identifier: Apache-2.0

import os
import random
import logging
from pathlib import Path

import sys
import subprocess
import cocotb
from cocotb.types import LogicArray
from cocotb.clock import Clock
from cocotb.triggers import Timer, Edge, RisingEdge, FallingEdge, ClockCycles
from cocotb.handle import Force, Release
from cocotb.utils import get_sim_time
from cocotb_tools.runner import get_runner

sim = os.getenv("SIM", "icarus")
gl = os.getenv("GL", False)
pdk_root = os.getenv("PDK_ROOT", Path(__file__).resolve().parent / "../gf180mcu")
pdk = os.getenv("PDK", "gf180mcuD")
scl = os.getenv("SCL", "gf180mcu_fd_sc_mcu7t5v0") # the Z80 chip's (the template's default)
pad = os.getenv("PAD", "gf180mcu_fd_io")
sram = os.getenv("SRAM", "gf180mcu_fd_ip_sram")
slot = os.getenv("SLOT", "1x1")

hdl_toplevel = "chip_top"

Z80_FREQ = 4 # in MHz

CONFIG_EARLY_SIGNALS = 0b10_00_10
BUS_READY = (CONFIG_EARLY_SIGNALS << 4) | 0b1111 # not BUSRQ, not NMI, not INT, not WAIT
BUS_WAIT  = (CONFIG_EARLY_SIGNALS << 4) | 0b1110 # not BUSRQ, not NMI, not INT,     WAIT
BUS_INT   = (CONFIG_EARLY_SIGNALS << 4) | 0b1101 # not BUSRQ, not NMI,     INT, not WAIT
BUS_NMI   = (CONFIG_EARLY_SIGNALS << 4) | 0b1011 # not BUSRQ,     NMI, not INT, not WAIT
BUS_REQ   = (CONFIG_EARLY_SIGNALS << 4) | 0b0111 #     BUSRQ, not NMI, not INT, not WAIT
OPCODE_NOP  = 0x00
OPCODE_LDHL = 0x21
OPCODE_STHL = 0x77
OPCODE_XOR  = 0xAF
OPCODE_OUT  = 0xD3
OPCODE_IN   = 0xDB
OPCODE_EI   = 0xFB

####### SIGNALS ###############################################################################################################
#
# RESET, BUSREQ
# 
@cocotb.test()
async def test__RESET_sequence(dut):
    await set_defaults(dut)   # the Z80's inputs inactive, RESET low from power-on

    dut._log.info("Test RESET")
    if gl:
        await enable_power(dut)
    await start_clock(dut.clk_PAD, Z80_FREQ)
    await power_on(dut)

    def print_pins(dut):
        data = dut.bidir_PAD.value[7:0]
        addr = dut.bidir_PAD.value[23:8]
        ctrl = dut.bidir_PAD.value[31:24]
        print (f"{' ' * 84}  pins:{ctrl}|{addr}|{data}")

    cocotb.log.info("Reset asserted...")
    await set_reset(dut, 0)   # (low from power-on: set_defaults)

    await ClockCycles(dut.clk_PAD, 4) # wait at least 3 cycles with RESET asserted according to Z80 Manual

    # perfectz80 (event_sweep_pz80 of z80-from-schematics on NOPs, RESET low from T10.25 to T22.25
    # counted from the first T1, half-cycles 27-49): once the M-cycle
    # in hand ends, the die idles in RESET with its address and data pads not driven and
    # MREQ IORQ RD WR M1 RFSH HALT BUSAK driven high
    for i in range(8):
        print_pins(dut)
        data = dut.bidir_PAD.value[7:0]
        addr = dut.bidir_PAD.value[23:8]
        ctrl = dut.bidir_PAD.value[31:24]
        assert str(addr) == "Z" * 16    # ADDRESS bus is floating during RESET
        assert str(data) == "Z" * 8     # DATA    bus is floating during RESET
        assert str(ctrl) == "1" * 8     # control signals are deasserted (active low) during RESET
        await ClockCycles(dut.clk_PAD, 1)

    await set_reset(dut, 1)   # a quarter clock after a rising edge
    cocotb.log.info("Reset deasserted.")

    # perfectz80 (the same run: RESET raised a quarter clock after a rising edge, T22.25,
    # WAIT low from then on): the first rising edge after the release samples RESET high,
    # the die idles through it and the next, and starts T1 of the first M1, at 0000, on the
    # third (half-cycle 50). Read at each rising edge, the pins show the idle at steps 0-2
    # (address not driven, M1 MREQ RD high) and T1's low half at step 3 (M1 MREQ RD low,
    # address 0000; half-cycle 51). Was: address 0000 from step 0, M1 from step 1 (TV80).
    for i in range(4):
        controls, addr, data = await z80_step(dut, BUS_WAIT, 'Z'*8, i, verbose=False)
        print_pins(dut)
        if i < 3:
            assert str(addr) == "Z" * 16    # pz80: still idling, address pads not driven
            assert controls["m1"] == 0      # pz80: M1 MREQ RD high in the idle
            assert controls["mreq"] == 0
            assert controls["rd"] == 0
        else:
            assert controls["m1"] == 1      # pz80: T1 of the first M1 (half-cycle 51)
            assert controls["mreq"] == 1
            assert controls["rd"] == 1
            assert str(addr) == "0" * 16    # pz80: the first fetch is at 0000

    for i in range(4, 16):
        controls, addr, data = await z80_step(dut, BUS_READY, OPCODE_NOP, i, verbose=False)
        print_pins(dut)

@cocotb.test()
async def test__NMI_sequence(dut):
    await set_defaults(dut)   # the Z80's inputs inactive, RESET low from power-on

    dut._log.info("Test NMI")
    if gl:
        await enable_power(dut)
    await start_clock(dut.clk_PAD, Z80_FREQ)
    await power_on(dut)

    cocotb.log.info("Reset asserted...")
    await set_reset(dut, 0)
    await ClockCycles(dut.clk_PAD, 16) # wait at least 3 cycles with RESET asserted according to Z80 Manual

    await set_reset(dut, 1)   # a quarter clock after a rising edge
    cocotb.log.info("Reset deasserted.")

    def print_pins(dut):
        data = dut.bidir_PAD.value[7:0]
        addr = dut.bidir_PAD.value[23:8]
        ctrl = dut.bidir_PAD.value[31:24]
        print (f"{' ' * 84}  pins:{ctrl}|{addr}|{data}")


    z80_cycle = 0
    for i in range(4):
        controls, addr, data = await z80_step(dut, BUS_READY, OPCODE_NOP, z80_cycle, verbose=False)
        print_pins(dut)
        z80_cycle += 1
        if controls["m1"] == 1:
            break

    for int_cycle in range(1, 5):
        reached_nmi_routine = False
        for i in range(64):
            controls, addr, data = await z80_step(dut, (BUS_NMI if i == int_cycle else BUS_READY), OPCODE_NOP, z80_cycle, verbose=True)
            if addr.to_unsigned() == 0x0066:
                reached_nmi_routine = True
                for j in range(4):
                    await z80_step(dut, BUS_READY, OPCODE_NOP, z80_cycle, verbose=True)
                    z80_cycle += 1
                break
            z80_cycle += 1

        assert reached_nmi_routine == True



@cocotb.test()
async def test__INT_sequence(dut):
    await set_defaults(dut)   # the Z80's inputs inactive, RESET low from power-on

    dut._log.info("Test INT")
    if gl:
        await enable_power(dut)
    await start_clock(dut.clk_PAD, Z80_FREQ)
    await power_on(dut)

    cocotb.log.info("Reset asserted...")
    await set_reset(dut, 0)
    await ClockCycles(dut.clk_PAD, 16) # wait at least 3 cycles with RESET asserted according to Z80 Manual

    await set_reset(dut, 1)   # a quarter clock after a rising edge
    cocotb.log.info("Reset deasserted.")

    def print_pins(dut):
        data = dut.bidir_PAD.value[7:0]
        addr = dut.bidir_PAD.value[23:8]
        ctrl = dut.bidir_PAD.value[31:24]
        print (f"{' ' * 84}  pins:{ctrl}|{addr}|{data}")


    z80_cycle = 0
    for i in range(4):
        controls, addr, data = await z80_step(dut, BUS_READY, OPCODE_NOP, z80_cycle, verbose=False)
        print_pins(dut)
        z80_cycle += 1
        if controls["m1"] == 1:
            break

    # perfectz80 (the RESET run of test__RESET_sequence: NOPs after RESET): the first M1's T1 is read at the
    # step the loop above stops at (first_m1); the NOP at address k is fetched 4k steps
    # later, RD low in the reads of T1's and T2's low halves (steps first_m1 + 4k and + 1).
    # Was: address z80_cycle // 4, which held for the TV80's first T1 one clock earlier.
    first_m1 = z80_cycle - 1
    int_cycle = 5
    cocotb.log.info("Soft interrupts are DISABLES after RESET.")
    for i in range(16):
        controls, addr, data = await z80_step(dut, (BUS_INT if i == int_cycle else BUS_READY), OPCODE_NOP, z80_cycle, verbose=True)
        print_pins(dut)
        if controls["rd"] == 1:
            assert addr.to_unsigned() == (z80_cycle - first_m1) // 4 # no software interrupts
        z80_cycle += 1

    cocotb.log.info("Enable soft interrupts.")
    for i in range(4):
        controls, addr, data = await z80_step(dut, BUS_READY, OPCODE_EI, z80_cycle, verbose=True)
        pc = addr.to_unsigned()
        print_pins(dut)
        z80_cycle += 1

    ioreq_set = False
    # reached_int_routine = False
    cocotb.log.info("Enable soft interrupts.")
    for i in range(32):
        controls, addr, data = await z80_step(dut, (BUS_INT if i == int_cycle else BUS_READY), OPCODE_NOP, z80_cycle, verbose=True)
        if controls["ioreq"] == 1:
            ioreq_set = True
        # reached_int_routine = addr.to_unsigned() != z80_cycle // 4
        print_pins(dut)
        z80_cycle += 1

    assert ioreq_set == True
    # assert reached_int_routine == True


@cocotb.test()
async def test__BUSREQ(dut):
    await set_defaults(dut)   # the Z80's inputs inactive, RESET low from power-on

    dut._log.info("Test BUSREQ")
    if gl:
        await enable_power(dut)
    await start_clock(dut.clk_PAD, Z80_FREQ)
    await power_on(dut)

    cocotb.log.info("Reset asserted...")
    await set_reset(dut, 0)
    await ClockCycles(dut.clk_PAD, 16) # wait at least 3 cycles with RESET asserted according to Z80 Manual

    await set_reset(dut, 1)   # a quarter clock after a rising edge
    cocotb.log.info("Reset deasserted.")

    def print_pins(dut):
        data = dut.bidir_PAD.value[7:0]
        addr = dut.bidir_PAD.value[23:8]
        ctrl = dut.bidir_PAD.value[31:24]
        print (f"{' ' * 84}  pins:{ctrl}|{addr}|{data}")


    z80_cycle = 0
    for i in range(4):
        controls, addr, data = await z80_step(dut, BUS_READY, OPCODE_NOP, z80_cycle, verbose=False)
        print_pins(dut)
        z80_cycle += 1
        if controls["m1"] == 1:
            break

    for i in range(9):
        controls, addr, data = await z80_step(dut, BUS_READY, OPCODE_NOP, z80_cycle, verbose=True)
        assert controls["busak"] == 0
        z80_cycle += 1

    last_addr = 0
    last_halt = 0
    for i in range(16):
        controls, addr, data = await z80_step(dut, BUS_REQ, 'Z'*8, z80_cycle, verbose=True)
        if i == 0:
            cocotb.log.info("BUSREQ asserted...")
        if controls["busak"] == 1:
            assert str(addr) == "Z" * 16    # ADDRESS bus is floating during BUSAK
            assert str(data) == "Z" * 8     # DATA    bus is floating during BUSAK
            assert controls["m1"] == 0
            assert controls["rfsh"] == 0
            assert controls["mreq"] == "Z"
            assert controls["rd"] == "Z"
            assert controls["wr"] == "Z"
            assert controls["ioreq"] == "Z"
            assert last_halt == controls["halt"]
            break
        else:
            last_addr = addr.to_unsigned()
            last_halt = controls["halt"]

        z80_cycle += 1

    for i in range(16):
        controls, addr, data = await z80_step(dut, BUS_REQ, 'Z'*8, z80_cycle, verbose=True)
        assert controls["busak"] == 1
        assert str(addr) == "Z" * 16        # ADDRESS bus is floating during BUSAK
        assert str(data) == "Z" * 8         # DATA    bus is floating during BUSAK
        assert controls["m1"] == 0
        assert controls["rfsh"] == 0
        assert controls["mreq"] == "Z"
        assert controls["rd"] == "Z"
        assert controls["wr"] == "Z"
        assert controls["ioreq"] == "Z"
        assert last_halt == controls["halt"]

    for i in range(4):
        controls, addr, data = await z80_step(dut, BUS_READY, OPCODE_NOP, z80_cycle, verbose=True)
        if i == 0:
            cocotb.log.info("BUSREQ deasserted...")
        if controls["busak"] == 0:
            break
        assert i < 2                        # Should take not more than 1 cyle to leave BUSAK state once BUSREQ was deasserted
        assert str(addr) == "Z" * 16        # ADDRESS bus is floating during BUSAK
        assert controls["m1"] == 0
        assert controls["rfsh"] == 0
        assert controls["mreq"] == "Z"
        assert controls["rd"] == "Z"
        assert controls["wr"] == "Z"
        assert controls["ioreq"] == "Z"
        assert last_halt == controls["halt"]

    z80_cycle += 1
    controls, addr, data = await z80_step(dut, BUS_READY, OPCODE_NOP, z80_cycle, verbose=True)
    assert last_addr + 1 == addr.to_unsigned()
    assert controls["busak"] == 0
    assert controls["m1"] == 1
    assert str(addr) != "Z" * 16    # ADDRESS bus is floating during RESET

####### TIMING ################################################################################################################
#
# FETCH, READ, WRITE...
#
@cocotb.test()
async def test__timing(dut):
    await set_defaults(dut)   # the Z80's inputs inactive, RESET low from power-on

    dut._log.info("Test TIMING")
    if gl:
        await enable_power(dut)
    await start_clock(dut.clk_PAD, Z80_FREQ)
    await power_on(dut)

    def print_pins(dut, edge=True):
        data = dut.bidir_PAD.value[7:0]
        addr = dut.bidir_PAD.value[23:8]
        ctrl = dut.bidir_PAD.value[31:24]
        posneg = '_' if dut.clk_PAD.value == 0 else '^'
        t_ns = str(cocotb.simulator.get_sim_time()[1]//100)
        print (f"clk: {str(dut.clk_PAD.value)} {t_ns} {(posneg if edge else ' ') * 70}  pins:{ctrl}|{addr}|{data}")

    cocotb.log.info("Reset asserted...")
    await set_reset(dut, 0)
    await set_inputs(dut, BUS_READY, OPCODE_NOP)

    async def release_reset():   # after 4 clocks, a quarter clock after a rising edge
        await ClockCycles(dut.clk_PAD, 4)
        await set_reset(dut, 1)
    cocotb.start_soon(release_reset())

    steps_per_cycle = 20
    time_step = 1 / Z80_FREQ * 1000 # "ns"
    time_step = time_step / steps_per_cycle
    print(time_step)
    for i in range(16 * steps_per_cycle):
        last_clk = dut.clk_PAD.value
        await Timer(time_step, "ns")
        print_pins(dut, last_clk != dut.clk_PAD.value)

@cocotb.test()
async def test__FETCH_timing(dut):
    await start_up(dut)
    dut._log.info("Test opcode FETCH timing")


    def print_pins(dut, edge=True):
        data = dut.bidir_PAD.value[7:0]
        addr = dut.bidir_PAD.value[23:8]
        ctrl = dut.bidir_PAD.value[31:24]
        posneg = '_' if dut.clk_PAD.value == 0 else '^'
        t_ns = str(cocotb.simulator.get_sim_time()[1]//100)
        print (f"clk: {str(dut.clk_PAD.value)} {t_ns} {(posneg if edge else ' ') * 70}  pins:{ctrl}|{addr}|{data}")

    def ctrl(dut):
        return convert_control_pins_to_signals(dut.bidir_PAD.value[31:24])
    def addr(dut):
        return dut.bidir_PAD.value[23:8].to_unsigned()

    dut._log.info("Assert WAIT to reach M1|T2 cycle")
    await set_inputs(dut, BUS_WAIT, OPCODE_NOP)
    await ClockCycles(dut.clk_PAD, 4)
    assert ctrl(dut)["m1"]   == 1
    assert ctrl(dut)["mreq"] == 1
    assert ctrl(dut)["rd"]   == 1
    assert addr(dut) == 0

    # We should be at T2 cycle of M1 now
    dut._log.info("Deassert WAIT")
    await set_inputs(dut, BUS_READY, OPCODE_NOP)
    await ClockCycles(dut.clk_PAD, 1) # T2->T3 
    await ClockCycles(dut.clk_PAD, 1) # T3->T4
    dut._log.info("M1|T4 cycle")

    # NOTE: MREQ might be asserted because of the REFRESH cycle during M1|T4
    assert ctrl(dut)["m1"]   == 0
    assert ctrl(dut)["rd"]   == 0
    assert addr(dut) == 0
    await FallingEdge(dut.clk_PAD); print_pins(dut)
    dut._log.info("Middle of M1|T4 cycle")
    assert ctrl(dut)["m1"]   == 0
    assert ctrl(dut)["rd"]   == 0
    assert addr(dut) == 0
    await Timer(10, "ns");         print_pins(dut, False)
    assert ctrl(dut)["m1"]   == 0
    assert ctrl(dut)["mreq"] == 0
    assert ctrl(dut)["rd"]   == 0
    assert addr(dut) == 0

    dut._log.info("FETCH of the new instruction starts here, leading into M1|T1 cycle")
    await RisingEdge(dut.clk_PAD);  print_pins(dut)                         # _/
    await Timer(100, "ns");         print_pins(dut, False)                  # _/^^ 100 ns
    assert ctrl(dut)["m1"]   == 1                                             
    assert ctrl(dut)["mreq"] == 0
    assert ctrl(dut)["rd"]   == 0
    await Timer( 10, "ns");         print_pins(dut, False)                  # _/^^ 110 ns
    assert addr(dut) == 0x01
    assert ctrl(dut)["mreq"] == 0                                                                           
    await FallingEdge(dut.clk_PAD); print_pins(dut, True)                   # _/^^^\
    assert addr(dut) == 0x01
    assert ctrl(dut)["mreq"] == 0                                                                           # @TODO: guarantee TdA(MREQf) Min 65ns
    await Timer( 85, "ns");         print_pins(dut, False)                  # _/^^^\_ 85ns
    assert ctrl(dut)["m1"]   == 1
    assert ctrl(dut)["mreq"] == 1
    assert ctrl(dut)["rd"]   == 1
    assert addr(dut) == 0x01

    await RisingEdge(dut.clk_PAD) ; print_pins(dut)                         # _/^^^\___/
    await FallingEdge(dut.clk_PAD); print_pins(dut)                         # _/^^^\___/^^^\
    assert ctrl(dut)["m1"]   == 1
    assert ctrl(dut)["mreq"] == 1
    assert ctrl(dut)["rd"]   == 1
    assert addr(dut) == 0x01

    await Timer(125-35, "ns");      print_pins(dut, False)                  # _/^^^\__ -35ns_/
    dut._log.info("DATA is expected to settle, leading into M1|T3")
    assert ctrl(dut)["m1"]   == 1
    assert ctrl(dut)["mreq"] == 1
    assert ctrl(dut)["rd"]   == 1
    assert addr(dut) == 0x01

    await RisingEdge(dut.clk_PAD);  print_pins(dut)                         # _/^^^\___/^^^\___/
    await Timer(100, "ns");         print_pins(dut, False)                  # _/^^^\___/^^^\___/^^ 100 ns
    assert ctrl(dut)["mreq"] == 0
    assert ctrl(dut)["rd"]   == 0
    assert addr(dut) == 0x01
    await Timer( 10, "ns");         print_pins(dut, False)                  # _/^^^\___/^^^\___/^^ 110 ns
    assert ctrl(dut)["m1"]   == 0
    assert addr(dut) == 0x01

@cocotb.test()
async def test__READ_timing(dut):
    await start_up(dut)
    dut._log.info("Test memory READ timing")


    def print_pins(dut, edge=True):
        data = dut.bidir_PAD.value[7:0]
        addr = dut.bidir_PAD.value[23:8]
        ctrl = dut.bidir_PAD.value[31:24]
        posneg = '_' if dut.clk_PAD.value == 0 else '^'
        t_ns = str(cocotb.simulator.get_sim_time()[1]//100)
        print (f"clk: {str(dut.clk_PAD.value)} {t_ns} {(posneg if edge else ' ') * 70}  pins:{ctrl}|{addr}|{data}")

    def ctrl(dut):
        return convert_control_pins_to_signals(dut.bidir_PAD.value[31:24])
    def addr(dut):
        return dut.bidir_PAD.value[23:8].to_unsigned()

    dut._log.info("Assert WAIT to reach M1|T2 cycle")
    await set_inputs(dut, BUS_WAIT, OPCODE_LDHL)
    await ClockCycles(dut.clk_PAD, 4)
    assert ctrl(dut)["m1"]   == 1
    assert ctrl(dut)["mreq"] == 1
    assert ctrl(dut)["rd"]   == 1
    assert addr(dut) == 0

    # We should be at T2 cycle of M1 now
    dut._log.info("Deassert WAIT")
    await set_inputs(dut, BUS_READY, OPCODE_LDHL)
    await ClockCycles(dut.clk_PAD, 1) # T2->T3 
    await ClockCycles(dut.clk_PAD, 1) # T3->T4
    dut._log.info("M1|T4 cycle")

    # NOTE: MREQ might be asserted because of the REFRESH cycle during M1|T4
    assert ctrl(dut)["m1"]   == 0
    assert ctrl(dut)["rd"]   == 0
    assert addr(dut) == 0
    await FallingEdge(dut.clk_PAD); print_pins(dut)
    dut._log.info("Middle of M1|T4 cycle")
    assert ctrl(dut)["m1"]   == 0
    assert ctrl(dut)["rd"]   == 0
    assert addr(dut) == 0
    await Timer(10, "ns");         print_pins(dut, False)
    assert ctrl(dut)["m1"]   == 0
    assert ctrl(dut)["mreq"] == 0
    assert ctrl(dut)["rd"]   == 0
    assert addr(dut) == 0

    dut._log.info("READ from memory starts here, leading into M2|T1")
    # perfectz80 (event_sweep_pz80, memory all 21, WAIT low from T1 to T2.25 counted from the
    # first T1; half-cycles counted from there) agrees with every check up to T3 below: M1 with one Tw, the refresh at
    # 0000 (I = R = 0), and the read at 0001 with MREQ and RD low from T1's falling edge.
    await RisingEdge(dut.clk_PAD);  print_pins(dut)                 # ... _/
    await Timer(100, "ns");         print_pins(dut, False)          # ... _/^^ 100 ns
    assert ctrl(dut)["m1"]   == 0                                     
    assert ctrl(dut)["mreq"] == 0
    assert ctrl(dut)["rd"]   == 0
    await Timer( 10, "ns");         print_pins(dut, False)          # ... _/^^ 110 ns
    assert addr(dut) == 0x01
    assert ctrl(dut)["mreq"] == 0     
    await FallingEdge(dut.clk_PAD); print_pins(dut, True)           # ... _/^^^\
    assert addr(dut) == 0x01
    assert ctrl(dut)["mreq"] == 0                                   # @TODO: guarantee TdA(MREQf) Min 65ns
    await Timer( 85, "ns");         print_pins(dut, False)          # ... _/^^^\_ 85ns
    assert ctrl(dut)["m1"]   == 0
    assert ctrl(dut)["mreq"] == 1
    assert ctrl(dut)["rd"]   == 1
    assert addr(dut) == 0x01


    await RisingEdge(dut.clk_PAD) ; print_pins(dut)                 # ... _/^^^\___/
    await FallingEdge(dut.clk_PAD); print_pins(dut)                 # ... _/^^^\___/^^^\
    assert ctrl(dut)["m1"]   == 0
    assert ctrl(dut)["mreq"] == 1
    assert ctrl(dut)["rd"]   == 1
    assert addr(dut) == 0x01

    await Timer(125-50, "ns");      print_pins(dut, False)          # ... _/^^^\___/^^^\__ -50ns_/
    dut._log.info("DATA is expected to settle, leading into M2|T3")
    assert ctrl(dut)["m1"]   == 0
    assert ctrl(dut)["mreq"] == 1
    assert ctrl(dut)["rd"]   == 1
    assert addr(dut) == 0x01

    await RisingEdge(dut.clk_PAD);  print_pins(dut)                 # ... _/^^^\___/^^^\___/
    await Timer(100, "ns");         print_pins(dut, False)          # ... _/^^^\___/^^^\___/^^ 100 ns
    # perfectz80 (that run, half-cycle 14, T3's high half): MREQ and RD are still
    # low; the die drops them at T3's falling edge, after it samples the data there
    # (Zilog TdCf(MREQr), TdCf(RDr)). Was: high 100 ns into T3 (TV80).
    assert ctrl(dut)["mreq"] == 1
    assert ctrl(dut)["rd"]   == 1
    assert addr(dut) == 0x01
    await Timer( 10, "ns");         print_pins(dut, False)          # ... _/^^^\___/^^^\___/^^ 110 ns
    assert ctrl(dut)["m1"]   == 0
    assert addr(dut) == 0x01                                        # @TODO: guarantee TdCTr(A) Min 80ns
    await FallingEdge(dut.clk_PAD); print_pins(dut)                 # ... _/^^^\___/^^^\___/^^^\
    await Timer( 85, "ns");         print_pins(dut, False)          # ... _/^^^\___/^^^\___/^^^\_ 85 ns
    # perfectz80 (that run, half-cycle 15, T3's low half): MREQ and RD high, address still 0001
    assert ctrl(dut)["mreq"] == 0
    assert ctrl(dut)["rd"]   == 0
    assert addr(dut) == 0x01


@cocotb.test()
async def test__WRITE_timing(dut):
    await start_up(dut)
    dut._log.info("Test memory WRITE timing")


    def print_pins(dut, edge=True):
        data = dut.bidir_PAD.value[7:0]
        addr = dut.bidir_PAD.value[23:8]
        ctrl = dut.bidir_PAD.value[31:24]
        posneg = '_' if dut.clk_PAD.value == 0 else '^'
        t_ns = str(cocotb.simulator.get_sim_time()[1]//100)
        print (f"clk: {str(dut.clk_PAD.value)} {t_ns} {(posneg if edge else ' ') * 70}  pins:{ctrl}|{addr}|{data}")

    def ctrl(dut):
        return convert_control_pins_to_signals(dut.bidir_PAD.value[31:24])
    def addr(dut):
        return dut.bidir_PAD.value[23:8].to_unsigned()
    def data(dut):
        return dut.bidir_PAD.value[7:0]

    # XOR A; LD HL, $2121; LD (HL), A from memory. perfectz80 runs the same image with the
    # same WAIT (event_sweep_pz80: WAIT low over XOR A's M1, T0-T2.25, and from a quarter clock
    # into the write's T1, T19.25-T22.25, counted from XOR A's T1; half-cycles from there). Counted from XOR A's T1:
    # LD HL's M1 at T5, its reads at T9 and T12, LD (HL),A's M1 at T15, the write's T1 at T19.
    bus.mem = {0x0000: OPCODE_XOR, 0x0001: OPCODE_LDHL, 0x0002: 0x21, 0x0003: 0x21, 0x0004: OPCODE_STHL}
    bus.fill = OPCODE_NOP
    dut._log.info("XOR A")
    await set_inputs(dut, BUS_WAIT, 'Z'*8)      # WAIT holds XOR A's M1 in Tw
    await ClockCycles(dut.clk_PAD, 4)
    await set_inputs(dut, BUS_READY, 'Z'*8)
    await ClockCycles(dut.clk_PAD, 2)            # XOR A's T3, T4
    dut._log.info("LD HL, $2121")
    await ClockCycles(dut.clk_PAD, 10)           # M1 + two reads: 4 + 3 + 3 T-states
    dut._log.info("LD (HL), A")
    await ClockCycles(dut.clk_PAD, 5)            # its M1 (4 T) and the write's T1 rising edge

    dut._log.info("Assert WAIT in the write's T1: the write waits in Tw")
    await set_inputs(dut, BUS_WAIT, 'Z'*8)
    await ClockCycles(dut.clk_PAD, 3)
    # perfectz80 (that run, half-cycle 45, the second Tw's low half): the write to 2121 with
    # MREQ and WR low (WR from T2's falling edge), RD and M1 high. Was: M1 low, WR high here,
    # the TV80's write being further along when its WAIT took hold.
    assert ctrl(dut)["m1"]   == 0
    assert ctrl(dut)["mreq"] == 1
    assert ctrl(dut)["rd"]   == 0
    assert ctrl(dut)["wr"]   == 1
    assert addr(dut) == 0x2121

    # @TODO: guarantee TdCf(D)    Max 150ns - "Clock Fall to Data Valid delay"
    # @TODO: guarantee TdD(WRf)Mw Min 80ns  - "Data stable prior to /WR Fall"
    # @TODO: guarantee TwWR       Min 220ns - "/WR pulse width"
    # @TODO: guarantee TdWRr(D)   Min 60ns  - "Data stable from /WR Rise"

    await set_inputs(dut, BUS_READY, 'Z'*8)     # WAIT high: that Tw is the last
    await RisingEdge(dut.clk_PAD);  print_pins(dut)                 # ... T3: _/
    await Timer(80, "ns");          print_pins(dut, False)          # ... _/^^ 80ns
    # perfectz80 (that run, half-cycle 46, T3's high half): MREQ and WR still low, the
    # die driving 00 (XOR A's result) at 2121. Was checked in T2; the die holds it to T3.
    assert ctrl(dut)["m1"]   == 0
    assert ctrl(dut)["mreq"] == 1
    assert ctrl(dut)["wr"]   == 1
    assert ctrl(dut)["rd"]   == 0
    assert data(dut) == '0'*8                                       # 0 - the result of XOR A,A is expected to be on the data bus at this point
    assert addr(dut) == 0x2121

    await FallingEdge(dut.clk_PAD); print_pins(dut)                 # ... _/^^^\
    await Timer(85, "ns");          print_pins(dut, False)          # ... _/^^^\_ 85 ns
    # perfectz80 (that run, half-cycle 47, T3's low half): MREQ and WR high from T3's falling
    # edge, the address still 2121. Was: high 85 ns after T3's rising edge (TV80).
    assert ctrl(dut)["mreq"] == 0
    assert ctrl(dut)["wr"]   == 0
    assert addr(dut) == 0x2121
    await Timer( 10, "ns");         print_pins(dut, False)          # ... _/^^^\_ 95 ns
    assert ctrl(dut)["m1"]   == 0
    assert addr(dut) == 0x2121                                      # @TODO: guarantee TdCTr(A) Min 80ns


####### INSTRUCTIONS ##########################################################################################################
#
# NOP, memory read & write, IN, OUT
#
@cocotb.test()
async def test__NOP(dut):
    await start_up(dut)
    dut._log.info("Test NOP")

    opcode = OPCODE_NOP
    cycles_per_instr = 4
    
    z80_cycle = 1
    for i in range(4): await z80_step(dut, BUS_WAIT, opcode)
    for i in range(32):
        controls, addr, data = await z80_step(dut, BUS_READY, opcode, z80_cycle, verbose=True)

        if z80_cycle % cycles_per_instr == 0 or \
           z80_cycle % cycles_per_instr == 1:
            assert controls['m1'] == 1
        if z80_cycle % cycles_per_instr == 1:
            assert controls['mreq'] == 1
            assert controls['rd'] == 1
        assert controls['wr'] == 0
        assert controls['ioreq'] == 0
        assert controls['halt'] == 0
        assert controls['busak'] == 0
        if z80_cycle < cycles_per_instr-1:
            assert addr == z80_cycle // 4 # Running NOPs, every 4 cycles address increases
        z80_cycle += 1

@cocotb.test()
async def test__LD_HLx2121(dut):
    await start_up(dut)
    dut._log.info("Test LD HL, $2121")

    opcode = OPCODE_LDHL
    cycles_per_instr = 10

    z80_cycle = 1
    for i in range(4): await z80_step(dut, BUS_WAIT, opcode)
    for i in range(32):
        controls, addr, data = await z80_step(dut, BUS_READY, opcode, z80_cycle, verbose=True)

        if z80_cycle % cycles_per_instr == 0 or \
           z80_cycle % cycles_per_instr == 1:
            assert controls['m1'] == 1
        if z80_cycle % cycles_per_instr == 1 or \
           z80_cycle % cycles_per_instr == 5 or \
           z80_cycle % cycles_per_instr == 8:
            assert controls['mreq'] == 1
            assert controls['rd'] == 1
        assert controls['wr'] == 0
        assert controls['ioreq'] == 0
        assert controls['halt'] == 0
        assert controls['busak'] == 0
        z80_cycle += 1


@cocotb.test()
async def test__LD_INxDB(dut):
    await start_up(dut)
    dut._log.info("Test IN A, ($DB)")

    opcode = OPCODE_IN
    cycles_per_instr = 11

    z80_cycle = 1
    for i in range(4): await z80_step(dut, BUS_WAIT, opcode)
    for i in range(32):
        controls, addr, data = await z80_step(dut, BUS_READY, opcode, z80_cycle, verbose=True)

        if z80_cycle % cycles_per_instr == 0 or \
           z80_cycle % cycles_per_instr == 1:
            assert controls['m1'] == 1
        if z80_cycle % cycles_per_instr == 1 or \
           z80_cycle % cycles_per_instr == 5:
            assert controls['mreq'] == 1
            assert controls['rd'] == 1
            assert controls['ioreq'] == 0
        if z80_cycle % cycles_per_instr == 8 or \
           z80_cycle % cycles_per_instr == 9:
            assert controls['ioreq'] == 1
            assert controls['rd'] == 1
            assert controls['mreq'] == 0
            assert addr.to_unsigned() & 0xFF == 0xDB
        assert controls['wr'] == 0
        assert controls['halt'] == 0
        assert controls['busak'] == 0
        z80_cycle += 1

@cocotb.test()
async def test__LD_OUTxD3(dut):
    await start_up(dut)
    dut._log.info("Test OUT ($D3), A")

    opcode = OPCODE_OUT
    cycles_per_instr = 11

    # XOR A, then OUT ($D3), A over and over, from memory (the bytes the test handed out
    # before, but at their addresses: the die latches a read where the test had already
    # moved on). perfectz80 runs the same image and WAIT (event_sweep_pz80: WAIT low from T2.25 to
    # T6.25 counted from XOR A's T1) and, read at the
    # rising edges this test reads at, agrees with every check below: M1 low at cycle % 11
    # = 0 and 1, MREQ and RD at 1 and 5, IORQ and WR to xxD3 at 8 and 9.
    bus.mem = {0x0000: OPCODE_XOR}
    bus.fill = OPCODE_OUT

    z80_cycle = 1
    for i in range(4): await z80_step(dut, BUS_READY, OPCODE_XOR)
    for i in range(4): await z80_step(dut, BUS_WAIT, opcode)
    for i in range(32):
        data = opcode if ((z80_cycle % cycles_per_instr) > 0) and ((z80_cycle % cycles_per_instr) < 6) else 'Z' * 8
        controls, addr, data = await z80_step(dut, BUS_READY, data, z80_cycle, verbose=True)

        if z80_cycle % cycles_per_instr == 0 or \
           z80_cycle % cycles_per_instr == 1:
            assert controls['m1'] == 1
        if z80_cycle % cycles_per_instr == 1 or \
           z80_cycle % cycles_per_instr == 5:
            assert controls['mreq'] == 1
            assert controls['rd'] == 1
            assert controls['ioreq'] == 0
            assert controls['wr'] == 0
        if z80_cycle % cycles_per_instr == 8 or \
           z80_cycle % cycles_per_instr == 9:
            assert controls['ioreq'] == 1
            assert controls['wr'] == 1
            assert controls['mreq'] == 0
            assert controls['rd'] == 0
            assert addr.to_unsigned() & 0xFF == 0xD3
        assert controls['halt'] == 0
        assert controls['busak'] == 0
        z80_cycle += 1

@cocotb.test()
async def test__LD_ptrHL_A(dut):
    await start_up(dut)
    dut._log.info("Test LD (HL), A")

    opcode = OPCODE_STHL
    cycles_per_instr = 7

    z80_cycle = 1
    for i in range(4): await z80_step(dut, BUS_READY, OPCODE_XOR)
    for i in range(4): await z80_step(dut, BUS_WAIT, opcode)
    for i in range(32):
        data = opcode if ((z80_cycle % cycles_per_instr) > 0) and ((z80_cycle % cycles_per_instr) < 3) else 'Z' * 8
        controls, addr, data = await z80_step(dut, BUS_READY, data, z80_cycle, verbose=True)

        if z80_cycle % cycles_per_instr == 0 or \
           z80_cycle % cycles_per_instr == 1:
            assert controls['m1'] == 1
        if z80_cycle % cycles_per_instr == 1:
            assert controls['mreq'] == 1
            assert controls['rd'] == 1
            assert controls['wr'] == 0
        if z80_cycle % cycles_per_instr == 5:
            assert controls['mreq'] == 1
            assert controls['wr'] == 1
            assert controls['rd'] == 0
        assert controls['halt'] == 0
        assert controls['busak'] == 0
        z80_cycle += 1

@cocotb.test()
async def test__program(dut):
    """A program from memory, through the pads: the stack, memory writes, OUT, IN, HALT.
    perfectz80 runs the same program (event_sweep_pz80; its I/O reads FF there): the same
    bus cycles, the writes to 4000, 7FFF, 7FFE, 4001 and to port 4255, then HALT."""
    await start_up(dut)
    dut._log.info("Test a program: LD SP; LD A,n; LD (nn),A; LD HL,nn; PUSH HL; OUT; IN; LD (nn),A; HALT")

    prog = bytes.fromhex("310080" "3E42" "320040" "213412" "E5" "D355" "DB66" "320140" "76")
    bus.mem = {i: b for i, b in enumerate(prog)}
    bus.fill = OPCODE_NOP
    bus.io = 0x99                           # what IN reads

    for i in range(120):
        controls, addr, data = await z80_step(dut, BUS_READY, 'Z'*8, i)
        if controls["halt"] == 1:
            break
    assert controls["halt"] == 1            # HALT reached
    assert sorted(set(bus.writes)) == [(0x4000, 0x42), (0x4001, 0x99), (0x7FFE, 0x34), (0x7FFF, 0x12)]
    assert sorted(set(bus.io_writes)) == [(0x4255, 0x42)]   # OUT ($55), A: A on the high address byte

@cocotb.test()
async def test__sign_of_life(dut):
    """RZ80's signs of life (asic/tb_sign_of_life.v on its asic-<pdk> branches, the check
    its chip flows run on every routed netlist), through the pads: write 01 02 04 .. 80 to
    8000h-8007h, read them back and add them up, OUT the sum (FFh) to port 42h, CALL a
    subroutine that OUTs 5Ah to port 43h and returns, HALT -- opcode fetch, immediate and
    memory reads, memory writes, the ALU, a DJNZ loop, I/O, the stack and HALT in ~570
    T-states. Checks the memory pattern, both I/O writes in order, the return address on
    the stack, HALT, and that RD and WR, or MREQ and IORQ, are never low together."""
    await start_up(dut)
    prog = bytes.fromhex("3100FF" "210080" "3E01" "0608"     # LD SP,FF00 / LD HL,8000 / LD A,1 / LD B,8
                         "77" "87" "23" "10FB"               # loop1: LD (HL),A / ADD A,A / INC HL / DJNZ
                         "210080" "0608" "AF"                # LD HL,8000 / LD B,8 / XOR A
                         "86" "23" "10FC"                    # loop2: ADD A,(HL) / INC HL / DJNZ
                         "D342" "CD2000" "76")               # OUT (42h),A / CALL 0020h / HALT
    bus.mem = {i: b for i, b in enumerate(prog)}
    bus.mem.update({0x20: 0x3E, 0x21: 0x5A, 0x22: 0xD3, 0x23: 0x43, 0x24: 0xC9})   # LD A,5Ah / OUT (43h),A / RET
    bus.fill = OPCODE_NOP
    for i in range(2000):
        controls, addr, data = await z80_step(dut, BUS_READY, 'Z'*8, i)
        if controls["halt"] == 1:
            break
    assert controls["halt"] == 1, "no HALT within 2000 clocks"
    for i in range(8):
        assert bus.mem.get(0x8000 + i) == 1 << i, f"mem[{0x8000 + i:04X}] = {bus.mem.get(0x8000 + i)}"
    io = [w for k, w in enumerate(bus.io_writes) if k == 0 or w != bus.io_writes[k - 1]]
    assert [(a & 0xFF, d) for a, d in io] == [(0x42, 0xFF), (0x43, 0x5A)], f"I/O writes {io}"
    assert (bus.mem.get(0xFEFE), bus.mem.get(0xFEFF)) == (0x1E, 0x00), "the return address on the stack"
    assert not bus.overlaps, f"control pins low together: {bus.overlaps[:4]}"


@cocotb.test()
async def test__halt2int(dut):
    """HALT to INT acknowledge, as Mark Woodmass's HALT2INT measures it on a Spectrum:
    IM 1 / EI / HALT, INT asserted 2, 4, .. 20 half-cycles after HALT goes low (two
    periods of the halted 4-T NOP cycle), and the T-states until IORQ falls in the INT
    acknowledge. The die's delays for the same program and INT placements (perfectz80, as
    RZ80's scripts/halt2int_probe.c records them): 6 5 4 7 6 5 4 7 6 5."""
    die = [6, 5, 4, 7, 6, 5, 4, 7, 6, 5]
    await start_up(dut)
    seen = []
    for k, dp in enumerate(range(2, 21, 2)):
        bus.mem = {0x0000: 0xED, 0x0001: 0x56, 0x0002: 0xFB, 0x0003: 0x76, 0x0038: 0x76}
        bus.fill = OPCODE_NOP
        await set_inputs(dut, BUS_READY, 'Z'*8)
        if k:
            await reset(dut)
        halt_at = int_at = inta_at = None
        for p in range(800):                 # half-cycles, read a quarter clock after each edge
            await Edge(dut.clk_PAD)
            await Timer(QUARTER_PS, "ps")
            s = str(dut.bidir_PAD.value)
            halt, iorq = s[31 - 30], s[31 - 26]
            if halt_at is None and halt == "0":
                halt_at = p
            if halt_at is not None and int_at is None and p == halt_at + dp:
                dut.input_PAD.value = BUS_INT
                int_at = p
            if int_at is not None and iorq == "0":
                inta_at = p
                dut.input_PAD.value = BUS_READY
                break
        assert inta_at is not None, f"INT at HALT + {dp} half-cycles: no INT acknowledge"
        seen.append((inta_at - int_at) // 2)
    dut._log.info(f"INT to INTA, T-states: {seen} (the die: {die})")
    assert seen == die


def kc85_instructions(sr):
    """The instructions a real Z80 (the U880 of a KC 85/4, RZ80's tests/sigrok/) runs in
    the logic analyser capture `sr`, one sample per T-state, with no WAIT state and no
    interrupt acknowledge in them: [(pc, bytes, taken, [T-states from each M1 to the
    next])], where taken says whether a conditional jump, call or return went; and the
    memory the capture read."""
    # RZ80's decoder (tests/rz80/scripts/sigrok_z80_decode.py): one line per sample,
    # i M1 MREQ IORQ RD WR addr data INT WAIT, the signals active-high
    decode = Path(__file__).resolve().parent / "../tests/rz80/scripts/sigrok_z80_decode.py"
    text = subprocess.check_output([sys.executable, str(decode), sr, "--trace", "/dev/stdout"],
                                   stderr=subprocess.DEVNULL).decode()
    cycles = []
    for ln in text.splitlines():
        if ln and not ln.startswith("#"):
            p = ln.split()
            cycles.append(dict(m1=int(p[1]), mreq=int(p[2]), iorq=int(p[3]), rd=int(p[4]),
                               addr=int(p[6], 16), data=int(p[7], 16), wait=int(p[9])))
    mem = {}
    for c in cycles:
        if c["mreq"] and c["rd"]:
            mem.setdefault(c["addr"], c["data"])
    # M1 fetches, as RZ80's scripts/sigrok_opcode_cycles.py finds them: where M1 goes
    # active, with the opcode of the M1 + MREQ + RD sample that follows within 4
    starts, prev = [], 0
    for i, c in enumerate(cycles):
        if c["m1"] and not prev:
            for cj in cycles[i:i + 4]:
                if cj["m1"] and cj["mreq"] and cj["rd"]:
                    starts.append((i, cj["addr"], cj["data"]))
                    break
        prev = c["m1"]
    groups, cur = [], []
    for k, (i, pc, op) in enumerate(starts):
        cur.append((i, pc, op))
        ops = [o for _, _, o in cur]
        more = op in (0xDD, 0xFD, 0xED) or (op == 0xCB and (len(ops) < 2 or ops[-2] not in (0xDD, 0xFD)))
        if not more:
            groups.append(cur)
            cur = []
    out = []
    for g, nxt in zip(groups[1:-1], groups[2:]):          # whole instructions only
        i0, i1 = g[0][0], nxt[0][0]
        window = cycles[i0:i1]
        if any(c["wait"] for c in window) or any(c["m1"] and c["iorq"] for c in window):
            continue
        pc = g[0][1]
        segs = [b[0] - a[0] for a, b in zip(g, g[1:] + [nxt[0]])]
        out.append((pc, nxt[0][1], segs))
    return out, mem


@cocotb.test()
async def test__sigrok_kc85(dut):
    """Every instruction a real Z80 executed in RZ80's logic-analyser capture of a KC 85/4
    (tests/sigrok/kc85-cpuclk.sr: its U880, an NMOS Z80, one sample per T-state), run on
    this chip from the same address with the memory the capture read: the T-states from
    each of its M1 cycles to the next must be the real chip's, conditional jumps, calls and
    returns going the way they went there (the flags, B for DJNZ, set to match). Windows
    with WAIT states or an interrupt acknowledge are not instructions alone."""
    root = Path(__file__).resolve().parent / "../rz80/tests/sigrok"
    insns, mem = kc85_instructions(str(root / "kc85-cpuclk.sr"))
    assert insns, "no instructions decoded from the capture"
    await start_up(dut)
    cc = {0x20: 0, 0x28: 1, 0x30: 2, 0x38: 3}              # JR cc: NZ Z NC C
    runs, done = 0, {}
    for pc, next_pc, segs in insns:
        op = mem.get(pc)
        size = {0x10: 2, 0x20: 2, 0x28: 2, 0x30: 2, 0x38: 2}.get(op, 1 if (op & 0xC7) == 0xC0 else 3)
        cond = op == 0x10 or op in cc or (op & 0xC7) in (0xC0, 0xC2, 0xC4)
        taken = cond and next_pc != (pc + size) & 0xFFFF
        key = (pc, taken)
        if key not in done:
            # the condition: Z C P/V S all set (F = FF) makes Z C PE M true, all clear NZ NC PO P
            code = cc.get(op, (op >> 3) & 7)
            f = (0xFF if code & 1 else 0x00) if taken else (0x00 if code & 1 else 0xFF)
            b = 2 if taken else 1                          # DJNZ
            stub = bytes([0x31, 0x00, 0x01, 0xF1, 0x06, b, 0xC3, pc & 0xFF, pc >> 8])  # LD SP,0100 / POP AF / LD B,b / JP pc
            assert all(a not in mem for a in range(len(stub))) or pc >= 0x0200, "the start-up code overlaps the capture's"
            bus.mem = dict(mem)
            bus.mem.update({a: v for a, v in enumerate(stub)})
            bus.mem.update({0x0100: f, 0x0101: 0x00})
            bus.fill = OPCODE_NOP
            await set_inputs(dut, BUS_READY, 'Z'*8)
            if runs:
                await reset(dut)
            runs += 1
            m1_at, prev = [], "1"
            for p in range(400):
                await Edge(dut.clk_PAD)
                await Timer(QUARTER_PS, "ps")
                s = str(dut.bidir_PAD.value)
                m1 = s[31 - 24]
                a = s[8:24]
                if prev == "1" and m1 == "0":
                    m1_at.append((p, int(a, 2) if set(a) <= set("01") else None))
                prev = m1
                firsts = [k for k, (_, x) in enumerate(m1_at) if x == pc]
                if firsts and len(m1_at) >= firsts[0] + len(segs) + 1:
                    break
            k0 = [k for k, (_, x) in enumerate(m1_at) if x == pc][0]
            got = [(m1_at[k + 1][0] - m1_at[k][0]) // 2 for k in range(k0, k0 + len(segs))]
            done[key] = got
        assert done[key] == segs, f"{pc:04X} {mem.get(pc):02X} (taken {taken}): {done[key]} T-states, the real Z80 {segs}"
    dut._log.info(f"{len(insns)} instructions of the capture, {runs} distinct runs: every one as the real Z80")


#====== ========= =============================================================================================================
#====== Utilities =============================================================================================================
#====== ========= =============================================================================================================
CLK_PS     = int(1_000_000 / Z80_FREQ)  # the clock period in ps (250 ns at 4 MHz)
QUARTER_PS = CLK_PS // 4                # inputs change a quarter clock after a rising edge:
                                        # away from both clock edges, so that in the
                                        # gate-level netlist they don't race the clock
                                        # through the pads
_clk_t0 = 0                             # sim time of the clock's first rising edge (ps)

class _Bus:
    """What the bus model hands out: by address from a program image (mem, the rest fill),
    else the byte the test last set (data); io for I/O reads; and what the CPU wrote."""
    def __init__(self):
        self.data, self.mem, self.fill, self.io = "00000000", None, None, None
        self.writes, self.io_writes = [], []
        self.overlaps = []      # (time, what): RD and WR, or MREQ and IORQ, low together

bus = _Bus()

def bits8(data_in):
    return f"{data_in:08b}" if isinstance(data_in, int) else data_in

async def at_quarter(dut):
    """Wait for the next instant a quarter clock after a rising edge (now, if this is one)."""
    delta = (QUARTER_PS - (get_sim_time("ps") - _clk_t0)) % CLK_PS
    if delta:
        await Timer(delta, "ps")

async def set_defaults(dut):
    global bus
    bus = _Bus()
    dut.input_PAD.value = BUS_READY        # the Z80's inputs inactive (was 0: all four asserted)
    dut.rst_n_PAD.value = 0                # RESET low from power-on
    dut.bidir_PAD.value = LogicArray('Z' * 32)

async def set_inputs(dut, ctrl_in, data_in):
    """The Z80's inputs and the byte the bus model hands out, a quarter clock after a
    rising edge."""
    await at_quarter(dut)
    dut.input_PAD.value = ctrl_in
    bus.data = bits8(data_in)

async def set_reset(dut, level):
    """RESET, a quarter clock after a rising edge."""
    await at_quarter(dut)
    dut.rst_n_PAD.value = level

async def enable_power(dut):
    dut.VDD.value = 1
    dut.VSS.value = 0

async def bus_model(dut):
    """The memory, the I/O devices and the interrupting device. A read (RD low with MREQ
    or IORQ) and an INTA (M1 and IORQ low) get the byte at the address from the program
    image, or else the byte the test set; once on the bus it stays there until the read
    ends, whatever the test sets meanwhile, as a memory's does: the Z80 samples a read at
    T3's falling edge, an M1 fetch and an INTA at T3's rising edge. Writes are recorded.
    Looks at the pins a quarter clock after each clock edge, when they have settled."""
    held = None
    while True:
        await Edge(dut.clk_PAD)
        await Timer(QUARTER_PS, "ps")
        s = str(dut.bidir_PAD.value)       # s[0] is bidir[31]
        pin = lambda i: s[31 - i]
        m1, mreq, iorq, rd, wr = pin(24), pin(25), pin(26), pin(27), pin(28)
        a, d = s[8:24], s[24:32]
        if rd == "0" and wr == "0":
            bus.overlaps.append((get_sim_time("ns"), "RD and WR"))
        if mreq == "0" and iorq == "0":
            bus.overlaps.append((get_sim_time("ns"), "MREQ and IORQ"))
        addr = int(a, 2) if set(a) <= set("01") else None
        if (rd == "0" and (mreq == "0" or iorq == "0")) or (m1 == "0" and iorq == "0"):
            if held is None:
                if bus.mem is not None and mreq == "0" and m1 != "Z" and addr is not None:
                    b = bits8(bus.mem.get(addr, bus.fill if bus.fill is not None else 0))
                elif bus.io is not None and iorq == "0" and m1 == "1" and addr is not None:
                    b = bits8(bus.io)
                else:
                    b = bus.data
                if b != "Z" * 8:
                    held = b
            dut.bidir_PAD.value = LogicArray("Z" * 24 + (held or "Z" * 8))
        else:
            held = None
            dut.bidir_PAD.value = LogicArray("Z" * 32)
            if wr == "0" and addr is not None and set(d) <= set("01"):
                if mreq == "0":
                    bus.writes.append((addr, int(d, 2)))
                    if bus.mem is not None:      # a program reads back what it wrote
                        bus.mem[addr] = int(d, 2)
                elif iorq == "0":
                    bus.io_writes.append((addr, int(d, 2)))

async def power_on(dut):
    """z80_top's power-on reset (por_n, tied off in the chip) held low for the
    first clocks: the simulation starts from the power-up state RZ80's own testbenches
    use. In silicon any power-up state settles once RESET is applied; from X,
    z80_top's dual-edge pin formers never do. Starts the bus model."""
    cocotb.start_soon(bus_model(dut))
    # in the flat gate-level netlist the same net has its escaped hierarchical name
    por = dut._id("\\i_chip_core.por_n ", extended=False) if gl else dut.i_chip_core.por_n
    por.value = Force(0)
    await ClockCycles(dut.clk_PAD, 2)   # (the clock's first rising edge can be at time 0)
    await at_quarter(dut)
    por.value = Release()

async def start_clock(clock, freq=50):
    """Start the clock @ freq MHz"""
    global _clk_t0
    _clk_t0 = get_sim_time("ps")
    c = Clock(clock, 1 / freq * 1000, "ns")
    cocotb.start_soon(c.start())

async def reset(dut):
    """RESET low for 4 clocks, raised a quarter clock after a rising edge; returns at the
    next rising edge, the first to sample it high (perfectz80: T1 of the first M1 starts
    on the third, two clocks later)."""
    cocotb.log.info("Reset asserted...")
    await set_reset(dut, 0)
    await ClockCycles(dut.clk_PAD, 4)
    await set_reset(dut, 1)
    cocotb.log.info("Reset deasserted.")
    await RisingEdge(dut.clk_PAD)

async def start_up(dut):
    """Startup sequence"""
    await set_defaults(dut)
    if gl:
        await enable_power(dut)
    await start_clock(dut.clk_PAD, Z80_FREQ)
    await power_on(dut)

    await reset(dut)

async def z80_step(z80, ctrl_in, data_in, cycle=-1, verbose=False):
    await set_inputs(z80, ctrl_in, data_in)    # a quarter clock after a rising edge
    await RisingEdge(z80.clk_PAD)              # the pins are read at the next one
    data = z80.bidir_PAD.value[7:0]
    addr = z80.bidir_PAD.value[23:8]
    cpin = z80.bidir_PAD.value[31:24]

    ctrl = convert_control_pins_to_signals(cpin)

    if (verbose):
        hex_addr = f"0x{addr.to_unsigned():04X}" if addr.is_resolvable else "xx----"
        print (f"clk: {cycle:3d}  {ctrl}  addr:{hex_addr}    pins:{cpin}|{addr}|{data}" \
            .replace("'", "").replace("{", "").replace("}", "").replace(",", ""))
        m1 = ctrl['m1']==True
        rd = ctrl['rd']==True
        wr = ctrl['wr']==True
        if m1 and rd:
            print(f"    OPCODE: {data_in}")
        elif rd:
            print(f"    READ DATA: {data}")
        if wr:
            print(f"    WRITE DATA: {data_in}")
    return ctrl, addr, data

def convert_control_pins_to_signals(ctrl):
    # def is_bit_active_low(byte, n):
    #     return byte & (1<<n) == 0
    def is_bit_active_low(logic_array, n):
        return str(logic_array)[-n-1] == "0"
    def is_bit_floating(logic_array, n):
        return str(logic_array)[-n-1] == "Z"

    ctrl = ['Z' if is_bit_floating(ctrl, n) else int(is_bit_active_low(ctrl, n)) for n in range(8)]
    ctrl = dict(zip(['m1', 'mreq', 'ioreq', 'rd', 'wr', 'rfsh', 'halt', 'busak'], ctrl))
    return ctrl

#====== ============ ==========================================================================================================
#====== Test Runnner ==========================================================================================================
#====== ============ ==========================================================================================================
def chip_top_runner():

    proj_path = Path(__file__).resolve().parent

    sources = []
    defines = {f"SLOT_{slot.upper()}": True}
    includes = [proj_path / "../src/", proj_path / "../src/rz80/"]

    # Set the LibreLane PDK/SCL/PAD defines
    defines[f"PDK_{pdk.replace('-','_')}"] = True
    defines[f"SCL_{scl}"] = True
    defines[f"PAD_{pad}"] = True
    defines[f"SRAM_{sram}"] = True

    if gl:
        # SCL models
        sources.append(Path(pdk_root) / pdk / "libs.ref" / scl / "verilog" / f"{scl}.v")
        if scl != "gf180mcu_as_sc_mcu7t3v3":
            sources.append(Path(pdk_root) / pdk / "libs.ref" / scl / "verilog" / "primitives.v")

        # We use the powered netlist
        sources.append(proj_path / f"../final/pnl/{hdl_toplevel}.pnl.v")

        defines.update({"FUNCTIONAL": True, "USE_POWER_PINS": True})
    else:
        # @TODO: parse and extract *.sv, *.v files from config.yaml
        sources.append(proj_path / "../src/chip_top.sv")
        sources.append(proj_path / "../src/chip_core.sv")
        # RZ80
        for f in ["z80_top", "z80_core", "z80_timing", "z80_pla", "z80_execute",
                  "z80_regfile", "z80_addr", "z80_alu"]:
            sources.append(proj_path / f"../src/rz80/{f}.v")

    sources += [
        # IO pad models
        Path(pdk_root) / pdk / f"libs.ref/{pad}/verilog/{pad}.v",
        
        # SRAM macros
        Path(pdk_root) / pdk / f"libs.ref/{sram}/verilog/{sram}__sram512x8m8wm1.v",
        
        # Custom IP
        proj_path / "../ip/gf180mcu_ws_ip__logo/vh/gf180mcu_ws_ip__logo.v",
        proj_path / "../ip/gf180mcu_ws_ip__marker/vh/gf180mcu_ws_ip__marker.v",
        proj_path / "../ip/gf180mcu_ws_ip__qrcode_id/vh/gf180mcu_ws_ip__qrcode_id.v",
        proj_path / "../ip/gf180mcu_ws_ip__shuttle_id/vh/gf180mcu_ws_ip__shuttle_id.v",
        proj_path / "../ip/gf180mcu_ws_ip__project_id/vh/gf180mcu_ws_ip__project_id.v",
        
    ]

    build_args = []

    if sim == "icarus":
        # For debugging
        # build_args = ["-Winfloop", "-pfileline=1"]
        pass

    if sim == "verilator":
        build_args = ["--timing", "--trace", "--trace-fst", "--trace-structs"]

    runner = get_runner(sim)
    runner.build(
        sources=sources,
        hdl_toplevel=hdl_toplevel,
        defines=defines,
        always=True,
        includes=includes,
        build_args=build_args,
        waves=True,
    )

    plusargs = []

    runner.test(
        hdl_toplevel=hdl_toplevel,
        test_module="chip_top_tb,",
        plusargs=plusargs,
        waves=True,
    )


if __name__ == "__main__":
    chip_top_runner()
