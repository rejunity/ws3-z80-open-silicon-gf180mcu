// SPDX-FileCopyrightText: © 2025 ReJ aka Renaldas Zioma
// SPDX-License-Identifier: Apache-2.0

`default_nettype none

// The Z80 core between the pads: RZ80's z80_top (src/rz80/, the rtl/ of
// https://github.com/rejunity/z80-from-schematics, unchanged) on the pads
// of chip_top. z80_top already is the chip-level Z80: one clock, the die's
// pin timing (bus pins change on both clock edges, the inputs sampled on
// the die's edges, RESET sampled per rising edge as on the NMOS part) and
// the die's pad drivers (addr_drive, data_drive, ctl_drive). This file only
// maps its pins to the pads and sets the pads up.
//
// Pin to pad mapping (unchanged from the TV80 version; slot_*.yaml places
// the pads):
//   input_in[0..3]    WAIT INT NMI BUSRQ
//   bidir[7:0]        D7..D0
//   bidir[23:8]       A15..A0
//   bidir[24..31]     M1 MREQ IORQ RD WR RFSH HALT BUSAK
//   rst_n, clk        RESET, CLK
//   input_in[4..]     unused (pulled down); 4..9 were TV80's bus-timing
//                     configuration pins: RZ80 has the die's timing.

module chip_core #(
    parameter NUM_INPUT_PADS,
    parameter NUM_BIDIR_PADS
    )(
    `ifdef USE_POWER_PINS
    inout  wire VDD,
    inout  wire VSS,
    `endif

    input  wire clk,       // clock
    input  wire rst_n,     // reset (active low)

    input  wire [NUM_INPUT_PADS-1:0] input_in,   // Input value
    output wire [NUM_INPUT_PADS-1:0] input_pu,   // Pull-up
    output wire [NUM_INPUT_PADS-1:0] input_pd,   // Pull-down

    input  wire [NUM_BIDIR_PADS-1:0] bidir_in,   // Input value
    output wire [NUM_BIDIR_PADS-1:0] bidir_out,  // Output value
    output wire [NUM_BIDIR_PADS-1:0] bidir_oe,   // Output enable
    output wire [NUM_BIDIR_PADS-1:0] bidir_cs,   // Input type (0=CMOS Buffer, 1=Schmitt Trigger)
    output wire [NUM_BIDIR_PADS-1:0] bidir_sl,   // Slew rate (0=fast, 1=slow)
    output wire [NUM_BIDIR_PADS-1:0] bidir_ie,   // Input enable
    output wire [NUM_BIDIR_PADS-1:0] bidir_pu,   // Pull-up
    output wire [NUM_BIDIR_PADS-1:0] bidir_pd    // Pull-down
);

    // See here for usage: https://gf180mcu-pdk.readthedocs.io/en/latest/IPs/IO/gf180mcu_fd_io/digital.html

    // ---- the pads' setup ----------------------------------------------------

    // No pull-ups for the original Z80 input pins:
    //   - for both INT and BUSREQ it is explicitly stated in the Z80 Manual "requires an external pull-up for these applications"
    //   - for NMI and WAIT there is nothing in the Z80 Manual, but we assume they were implemented electrically similar to INT and BUSREQ
    // No pull-downs since the original Z80 input pins are active LOW and should NOT be pulled down
    assign input_pu[3:0] = '0;
    assign input_pd[3:0] = '0;

    // The rest of the inputs are unused: pull-ups off, pull-DOWNs on.
    // LukeW: I'd recommend a pull-down otherwise pads can float up to mid rail
    // and start drawing current. The pulls are pretty weak, like 100k or so.
    assign input_pu[NUM_INPUT_PADS-1:4] = '0;
    assign input_pd[NUM_INPUT_PADS-1:4] = '1;

    // CMOS input buffers; slow slew on every bus pad, with bi_t's 4 mA drive
    // (chip_top): as RZ80's own GF180 chip, near the NMOS Z80's drive
    assign bidir_cs = '0;
    assign bidir_sl = '1;
    assign bidir_pu = '0;
    assign bidir_pd = '0;

    // ---- the pads' outputs into the core -----------------------------------
    // Each pad output the core reads (D7..D0, WAIT INT NMI BUSRQ, RESET) drives
    // one buffer: the pad library lets a pad's Y drive one cell
    // (default_max_fanout 1), and OpenROAD's design repair, given more, puts a
    // buffer on each load rather than one in front of them all (D2's Y drove
    // five). Not CLK: the clock tree starts at its pad's Y. The flow's setup
    // repairs neither remove buffers nor clone gates (librelane/config.yaml).
    localparam NUM_PAD_Y = 13;
    wire [NUM_PAD_Y-1:0] pad_y = {rst_n, input_in[3:0], bidir_in[7:0]};
    wire [NUM_PAD_Y-1:0] core_y;
    wire [7:0] data_in = core_y[7:0];
    wire [3:0] ctl_in  = core_y[11:8];
    wire       reset_n = core_y[12];
    generate
    for (genvar i = 0; i < NUM_PAD_Y; i++) begin : pad_ybuf
    `ifdef SYNTHESIS
    `ifdef SCL_gf180mcu_fd_sc_mcu9t5v0
        (* keep *) gf180mcu_fd_sc_mcu9t5v0__buf_2 buf_y (.I(pad_y[i]), .Z(core_y[i]));
    `elsif SCL_gf180mcu_fd_sc_mcu7t5v0
        (* keep *) gf180mcu_fd_sc_mcu7t5v0__buf_2 buf_y (.I(pad_y[i]), .Z(core_y[i]));
    `else
        assign core_y[i] = pad_y[i];
    `endif
    `else
        assign core_y[i] = pad_y[i];
    `endif
    end
    endgenerate

    // ---- RZ80 -------------------------------------------------------------------

    wire [15:0] addr;
    wire        data_drive, addr_drive, ctl_drive;

    // por_n is z80_top's power-on reset (not a Z80 pin). Tied off, as RZ80's
    // own chip does: the registers come up random, like the NMOS part's, and
    // RESET alone starts the core (hold it low for 3 clocks or more after
    // power-up, as the Z80 needs). A tie cell and a buffer rather than a
    // constant keep it a net, so z80_top keeps its asynchronously reset
    // flip-flops (as in RZ80's hardened core) and a simulation can hold it low
    // at time 0: started at X, z80_top's dual-edge pin formers never settle
    // (in silicon any power-up state does).
    wire por_n;
    `ifdef SYNTHESIS
    `ifdef SCL_gf180mcu_fd_sc_mcu9t5v0
    wire por_tie;
    (* keep *) gf180mcu_fd_sc_mcu9t5v0__tieh  por_tieh (.Z(por_tie));
    (* keep *) gf180mcu_fd_sc_mcu9t5v0__buf_2 por_buf  (.I(por_tie), .Z(por_n));
    `elsif SCL_gf180mcu_fd_sc_mcu7t5v0
    wire por_tie;
    (* keep *) gf180mcu_fd_sc_mcu7t5v0__tieh  por_tieh (.Z(por_tie));
    (* keep *) gf180mcu_fd_sc_mcu7t5v0__buf_2 por_buf  (.I(por_tie), .Z(por_n));
    `else
    assign por_n = 1'b1;
    `endif
    `else
    assign por_n = 1'b1;   // the testbench forces it low at time 0
    `endif

    z80_top u_z80 (
        .clk        (clk),
        .por_n      (por_n),
        .reset_n    (reset_n),

        // NOTE: The original Z80 has a peculiar data bus pin order, keep it to minimize wire crossing on the DIP40 PCB
        // Also see: http://www.righto.com/2014/09/why-z-80s-data-pins-are-scrambled.html
        // (the order is in slot_*.yaml: bidir[i] is Di)
        .data_in    (data_in),
        .data_out   (bidir_out[7:0]),
        .data_drive (data_drive),
        .addr       (addr),

        .m1_n       (bidir_out[24 + 0]),
        .mreq_n     (bidir_out[24 + 1]),
        .iorq_n     (bidir_out[24 + 2]),
        .rd_n       (bidir_out[24 + 3]),
        .wr_n       (bidir_out[24 + 4]),
        .rfsh_n     (bidir_out[24 + 5]),
        .halt_n     (bidir_out[24 + 6]),
        .busack_n   (bidir_out[24 + 7]),

        // the die's pad enables
        .addr_drive (addr_drive),
        .ctl_drive  (ctl_drive),

        // 4 input control pins
        .wait_n     (ctl_in[0]),
        .int_n      (ctl_in[1]),
        .nmi_n      (ctl_in[2]),
        .busreq_n   (ctl_in[3]),

        .dbg_t      (),
        .dbg_m      ()
    );

    // 16 output address bus pins
    assign bidir_out[23:8] = addr;

    // Output enables, as the die drives its pads: the data bus while the CPU
    // writes; the address bus except in a bus grant and the RESET idle; MREQ
    // IORQ RD WR except in a bus grant (Figure 10 BUS Request/Acknowledge
    // Cycle); M1 RFSH HALT BUSAK always.
    assign bidir_oe[7:0]   = {8{data_drive}};
    assign bidir_oe[23:8]  = {16{addr_drive}};
    assign bidir_oe[24]    = 1'b1;              // M1
    assign bidir_oe[25+:4] = {4{ctl_drive}};    // MREQ IORQ RD WR
    assign bidir_oe[29+:3] = 3'b111;            // RFSH HALT BUSAK

    // Input buffers: on for the data bus while the CPU does not drive it; off
    // for the output-only pads, which the core never reads (and which float in
    // a bus grant and, the address, in the RESET idle).
    assign bidir_ie[7:0]                = {8{~data_drive}};
    assign bidir_ie[NUM_BIDIR_PADS-1:8] = '0;

    logic _unused;
    assign _unused = &{1'b0, input_in[NUM_INPUT_PADS-1:4], bidir_in[NUM_BIDIR_PADS-1:8]};

endmodule

`default_nettype wire
