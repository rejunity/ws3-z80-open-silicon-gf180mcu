// SPDX-FileCopyrightText: © 2026 Renaldas Zioma
// SPDX-License-Identifier: Apache-2.0
//
// chip_shim.v - z80_top's ports around chip_top and its pads, so that a
// testbench written for RZ80's z80_top runs on the whole chip: the RTL
// (src/) or the gate-level netlist (final/pnl/, with -DGL). After RZ80's
// asic/chip_shim.v. The data bus is a real tri-state bus between the D pads
// and the testbench's memory, which drives it in a read (RD low) and in an
// interrupt acknowledge (M1 and IORQ low); data_drive is the CPU's write.
// The unused input pads are held low, as their pull-downs would.
`default_nettype none
module z80_chip_shim (
    input  wire        clk,
    input  wire        por_n,      // z80_top's power-on reset: the chip ties it off
    input  wire        reset_n,
    output wire [15:0] addr,
    input  wire [7:0]  data_in,
    output wire [7:0]  data_out,
    output wire        data_drive,
    output wire        m1_n, mreq_n, iorq_n, rd_n, wr_n, rfsh_n, halt_n, busack_n,
    input  wire        wait_n, int_n, nmi_n, busreq_n,
    output wire [3:0]  dbg_t,
    output wire [2:0]  dbg_m
);
    wire [31:0] bidir;
    wire [13:0] inputs = {10'b0, busreq_n, nmi_n, int_n, wait_n};
    wire        clk_pad = clk, rst_pad = reset_n;
    assign bidir[7:0] = (!rd_n || (!m1_n && !iorq_n)) ? data_in : 8'bz;
    assign data_out   = bidir[7:0];
    assign data_drive = !wr_n;
    assign addr       = bidir[23:8];
    assign {busack_n, halt_n, rfsh_n, wr_n, rd_n, iorq_n, mreq_n, m1_n} = bidir[31:24];
    assign dbg_t      = 4'd0;
    assign dbg_m      = 3'd0;
`ifdef USE_POWER_PINS
    supply1 vdd;
    supply0 vss;
`endif
    chip_top chip (
`ifdef USE_POWER_PINS
        .VDD(vdd), .VSS(vss),           // (the netlist's: DVDD / DVSS are the same nets)
`endif
        .clk_PAD(clk_pad), .rst_n_PAD(rst_pad), .input_PAD(inputs), .bidir_PAD(bidir)
    );
    // A chip powers up with its flip-flops at random and runs: z80_top's
    // dual-edge pin former settles on the first clock edges, and RESET starts
    // the core. A simulation starts them unknown (X) instead, which the former
    // never leaves; so the chip starts in the power-up state z80_top's own
    // power-on reset gives (tied off in the chip): held low until the
    // testbench's por_n rises.
    initial begin
`ifdef GL
        force chip.\i_chip_core.por_n  = 1'b0;
        wait (por_n === 1'b1);
        release chip.\i_chip_core.por_n ;
`else
        force chip.i_chip_core.por_n = 1'b0;
        wait (por_n === 1'b1);
        release chip.i_chip_core.por_n;
`endif
    end
endmodule
`default_nettype wire
