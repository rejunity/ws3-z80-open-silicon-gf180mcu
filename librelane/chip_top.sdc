current_design $::env(DESIGN_NAME)
set_units -time ns

set clock_port __VIRTUAL_CLK__
if { [info exists ::env(CLOCK_PORT)] } {
    set port_count [llength $::env(CLOCK_PORT)]

    if { $port_count == "0" } {
        puts "\[WARNING] No CLOCK_PORT found. A dummy clock will be used."
    } elseif { $port_count != "1" } {
        puts "\[WARNING] Multi-clock files are not currently supported by the base SDC file. Only the first clock will be constrained."
    }

    if { $port_count > "0" } {
        set ::clock_port [lindex $::env(CLOCK_PORT) 0]
    }
}

if { $::env(CLOCK_PORT) == $::env(CLOCK_NET) } {
    set port_args [get_ports $clock_port]
} else {
    # This should actually use CLOCK_PIN?
    set port_args [get_pins [lindex $::env(CLOCK_NET) 0]]
}

puts "\[INFO] Using clock $clock_port…"
create_clock {*}$port_args -name $clock_port -period $::env(CLOCK_PERIOD)

set input_delay_value [expr $::env(CLOCK_PERIOD) * $::env(IO_DELAY_CONSTRAINT) / 100]
set output_delay_value [expr $::env(CLOCK_PERIOD) * $::env(IO_DELAY_CONSTRAINT) / 100]
puts "\[INFO] Setting output delay to: $output_delay_value"
puts "\[INFO] Setting input delay to: $input_delay_value"

set_max_fanout $::env(MAX_FANOUT_CONSTRAINT) [current_design]
if { [info exists ::env(MAX_TRANSITION_CONSTRAINT)] } {
    set_max_transition $::env(MAX_TRANSITION_CONSTRAINT) [current_design]
}
if { [info exists ::env(MAX_CAPACITANCE_CONSTRAINT)] } {
    set_max_capacitance $::env(MAX_CAPACITANCE_CONSTRAINT) [current_design]
}

set clocks [get_clocks $clock_port]

# Bidirectional pads
set clk_core_inout_ports [get_ports { 
    bidir_PAD[*]
}] 

set_input_delay -min 0 -clock $clocks $clk_core_inout_ports
set_input_delay -max $input_delay_value -clock $clocks $clk_core_inout_ports
set_output_delay $output_delay_value -clock $clocks $clk_core_inout_ports

# Input-only pads
set clk_core_input_ports [get_ports { 
    rst_n_PAD
    input_PAD[*]
}] 

set_input_delay -min 0 -clock $clocks $clk_core_input_ports
set_input_delay -max $input_delay_value -clock $clocks $clk_core_input_ports

# Output load
set cap_load [expr $::env(OUTPUT_CAP_LOAD) / 1000.0]
puts "\[INFO] Setting load to: $cap_load"
set_load $cap_load [all_outputs]

puts "\[INFO] Setting clock uncertainty to: $::env(CLOCK_UNCERTAINTY_CONSTRAINT)"
set_clock_uncertainty $::env(CLOCK_UNCERTAINTY_CONSTRAINT) $clocks

puts "\[INFO] Setting clock transition to: $::env(CLOCK_TRANSITION_CONSTRAINT)"
set_clock_transition $::env(CLOCK_TRANSITION_CONSTRAINT) $clocks

puts "\[INFO] Setting timing derate to: $::env(TIME_DERATING_CONSTRAINT)%"
set_timing_derate -early [expr 1-[expr $::env(TIME_DERATING_CONSTRAINT) / 100]]
set_timing_derate -late [expr 1+[expr $::env(TIME_DERATING_CONSTRAINT) / 100]]

if { [info exists ::env(OPENLANE_SDC_IDEAL_CLOCKS)] && $::env(OPENLANE_SDC_IDEAL_CLOCKS) } {
    unset_propagated_clock [all_clocks]
} else {
    set_propagated_clock [all_clocks]
}


# The bidir pads' input enables follow the CPU's data drive: the input buffers
# turn on when the CPU stops driving the bus, a half cycle or more before the
# next read samples the pads. The IE -> Y arc is no path the Z80 depends on;
# timed as a half-cycle path from z80_top's falling-edge pin former it limited
# the clock at the slow corner for nothing.
set ie_pins [get_pins -hierarchical */IE]
if { [llength $ie_pins] > 0 } {
    puts "\[INFO] False path through [llength $ie_pins] pad input enables (IE)"
    set_false_path -through $ie_pins
}

# The pins as the NMOS Z80's datasheet has them (Zilog PS0178's AC test
# conditions; timing/pin_timing.py, `make pin-timing`, checks every parameter at
# every corner): 15 ns edges on CLK and the inputs.
set_input_transition 15 [get_ports {clk_PAD rst_n_PAD input_PAD[*] bidir_PAD[*]}]

# WAIT (input_PAD[0]) as the Z80 samples it, on CLK's falling edge (P17
# TsWAIT(Cf), P18 ThWAIT(Cf) = 0): set up from the falling edge before (MREQ and
# IORQ fall on one edge, WAIT is sampled on the next), and free to change right
# at the CLK pin's falling edge. That edge reaches clk_pad/Y, where this SDC's
# clock starts, 6.2-7.3 ns later: the Schmitt CLK pad on a 15 ns edge, as RZ80
# simulated it at transistor level (spice/pads/gf180mcu/; the PDK's library
# says 6.8-8.1 ns). So WAIT is held 6 ns past the edge at Y; at 0 the flow left
# it 0.6-2.1 ns short of the datasheet's hold at the pin.
unset_input_delay [get_ports {input_PAD[0]}]
set_input_delay -clock $clocks -clock_fall -max 0 [get_ports {input_PAD[0]}]
set_input_delay -clock $clocks -clock_fall -min -6 [get_ports {input_PAD[0]}]
