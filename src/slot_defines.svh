// The Z80's pads per slot. The power pads are the wafer.space template's and
// their places are fixed (slot_*.yaml); the signal pads are the Z80's: no
// analog pads, every signal pad an input or a bidir pad:
//   inputs  0..3  WAIT INT NMI BUSRQ, the rest unused (pulled down)
//   bidir   0..7  D0..D7, 8..23 A0..A15, 24..31 M1 MREQ IORQ RD WR RFSH HALT BUSAK
// plus the clock and reset pads.

`ifdef SLOT_1X1

// Power/ground pads for core and I/O
`define NUM_DVDD_PADS 6
`define NUM_DVSS_PADS 8

`define NUM_VDD_PADS 2
`define NUM_VSS_PADS 2

// Signal pads: 22 + 32 (+ clock and reset) = 56
`define NUM_INPUT_PADS 22
`define NUM_BIDIR_PADS 32

`endif

`ifdef SLOT_0P5X1

// Power/ground pads for core and I/O
`define NUM_DVDD_PADS 7
`define NUM_DVSS_PADS 7

`define NUM_VDD_PADS 1
`define NUM_VSS_PADS 1

// Signal pads: 22 + 32 (+ clock and reset) = 56
`define NUM_INPUT_PADS 22
`define NUM_BIDIR_PADS 32

`endif

`ifdef SLOT_1X0P5

// No Z80 pad mapping for this slot (slot_1x0p5.yaml is the template's)

// Power/ground pads for core and I/O
`define NUM_DVDD_PADS 7
`define NUM_DVSS_PADS 7

`define NUM_VDD_PADS 1
`define NUM_VSS_PADS 1

// Signal pads
`define NUM_INPUT_PADS 22
`define NUM_BIDIR_PADS 32

`endif

`ifdef SLOT_0P5X0P5

// Power/ground pads for core and I/O
`define NUM_DVDD_PADS 3
`define NUM_DVSS_PADS 3

`define NUM_VDD_PADS 1
`define NUM_VSS_PADS 1

// Signal pads: 14 + 32 (+ clock and reset) = 48
`define NUM_INPUT_PADS 14
`define NUM_BIDIR_PADS 32

`endif
