# The chip at transistor level

`chip.py` is RZ80's `asic/spice/chip.py` (copied by `scripts/sync_rz80.py`,
patched for this chip: `chip_top` and its ports, the template's PDK, the RTL in
`src/rz80/`). It runs the whole chip, extracted from its GDS to transistors,
in ngspice:

- **extract:** Magic reads `final/gds/chip_top.gds` and extracts every cell's
  transistors and the wires' capacitance;
- **reference:** the same program on the RTL (`tb_chip_ref.v`, iverilog): the
  pins at every clock edge, when the memory must drive the data bus, and what
  the transistors have to do;
- **simulate:** power-up, 4 clocks of RESET, then `LD A,5Ah / LD (8000h),A /
  OUT (42h),A / IN A,(43h) / HALT` at 4 MHz, 15 ns clock edges, 100 pF on every
  pin, at the typical, slow and fast corners (`tt` 25 °C 5 V, `ss` 125 °C
  4.5 V, `ff` -40 °C 5.5 V), in windows that each start from the node voltages
  the window before ended with;
- **figures:** the pins against the RTL on every edge, every output parameter
  of the Z8400's datasheet measured on every cycle that has it (outputs at
  1.5 V, CLK at 50 %), and the timing diagrams of Zilog PS0178's Figures 5-7.

It takes hours, so it runs apart from CI, on demand:
`.github/workflows/transistor.yml` (Actions, *Transistor*, *Run workflow*)
takes the GDS of main's latest successful CI run and leaves the results as the
artifact `transistor-results`; they are committed under `chip/gf180mcu/`
(`tt`; the other corners in `ss/` and `ff/`). Locally:

    python3 spice/chip.py ws3 --work build/transistor --gds final/gds/chip_top.gds --corner tt

`pads/gf180mcu/` holds the pads RZ80 simulated at transistor level
(`asic/spice/pads.py`): Liberty tables to the datasheet's 100 pF and its
measuring levels, which `timing/pin_timing.py` reads.
