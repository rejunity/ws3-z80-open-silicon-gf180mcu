// SPDX-FileCopyrightText: © 2026 Renaldas Zioma
// SPDX-License-Identifier: Apache-2.0
//
// z80_system.v - the chip (cocotb/chip_shim.v around chip_top: the RTL, or
// the gate-level netlist with -DGL) with 64 KB of RAM, for the long cocotb
// tests (system_tb.py). Memory, console and the end of the program are here
// in Verilog, so the simulator runs at its own speed; cocotb only loads the
// program (+prog=<hex>), waits for `done` and reads the console (+console=).
//   - console: a memory write to FFF0h prints its byte (a program's BDOS or
//     ROM print routine, written in Z80 code by system_tb.py, ends there);
//   - end: an opcode fetch from 0000h once the program has run (CP/M's warm
//     boot), or HALT; or +max_cycles=N clocks, which sets `timeout` too.
`timescale 1ns/1ps
`default_nettype none
module z80_system;
    reg clk = 1'b0;
    always #125 clk = ~clk;                      // 4 MHz
    reg por_n = 1'b0, reset_n = 1'b0;
    wire [15:0] addr;
    wire [7:0]  data_out;
    wire        data_drive;
    wire        m1_n, mreq_n, iorq_n, rd_n, wr_n, rfsh_n, halt_n, busack_n;
    reg  [7:0]  mem [0:65535];
    wire [7:0]  data_in = (!mreq_n && !rd_n) ? mem[addr] : 8'hFF;
    z80_chip_shim dut (
        .clk(clk), .por_n(por_n), .reset_n(reset_n),
        .addr(addr), .data_in(data_in), .data_out(data_out), .data_drive(data_drive),
        .m1_n(m1_n), .mreq_n(mreq_n), .iorq_n(iorq_n), .rd_n(rd_n), .wr_n(wr_n),
        .rfsh_n(rfsh_n), .halt_n(halt_n), .busack_n(busack_n),
        .wait_n(1'b1), .int_n(1'b1), .nmi_n(1'b1), .busreq_n(1'b1),
        .dbg_t(), .dbg_m()
    );
    reg done = 1'b0, timeout = 1'b0, halted = 1'b0, ran = 1'b0, wr_prev = 1'b0;
    reg [1023:0] progf, consf;
    integer fd, i, max_cycles, cycles = 0;
    initial begin
        for (i = 0; i < 65536; i = i + 1) mem[i] = 8'h00;
        if (!$value$plusargs("prog=%s", progf)) $fatal(1, "z80_system: no +prog=");
        if (!$value$plusargs("console=%s", consf)) consf = "console.txt";
        if (!$value$plusargs("max_cycles=%d", max_cycles)) max_cycles = 100000000;
        $readmemh(progf, mem);
        fd = $fopen(consf, "w");
        repeat (2) @(negedge clk);
        por_n = 1'b1;
        repeat (4) @(negedge clk);
        reset_n = 1'b1;
    end
    // memory writes and the console, at every falling edge
    always @(negedge clk) if (reset_n && !done) begin
        if (!mreq_n && !wr_n) begin
            mem[addr] <= data_out;
            if (addr == 16'hFFF0 && !wr_prev) begin $fwrite(fd, "%c", data_out); $fflush(fd); end
        end
        wr_prev <= !mreq_n && !wr_n;
    end
    always @(posedge clk) if (reset_n && !done) begin
        cycles = cycles + 1;
        if (!m1_n && !mreq_n && !rd_n) begin
            if (addr != 16'h0000) ran <= 1'b1;
            else if (ran) begin done <= 1'b1; $fclose(fd); end
        end
        if (!halt_n) begin halted <= 1'b1; done <= 1'b1; $fclose(fd); end
        if (cycles >= max_cycles) begin timeout <= 1'b1; done <= 1'b1; $fclose(fd); end
    end
endmodule
`default_nettype wire
