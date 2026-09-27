create_clock -name system -period 20.000 [get_ports {clk}]
# SPI is asynchronously sampled, not used as a fabric clock. Timing from
# board inputs to the first synchronizer stages is excluded; the FPGA
# clock-domain paths remain constrained. External SPI timing is tested on-board.
set_false_path -from [get_ports {sck cs_n mosi}]
set_false_path -to [get_ports {miso irq led_n}]
# cpu_input captures at divider 46; CPU CE is divider 49, three clocks later.
# Only this internal data path receives the exception, not SPI/control logic.
set_multicycle_path 3 -setup -from [get_cells {machine.cpu_input*}] -to [get_cells {machine.cpu.*}]
set_multicycle_path 2 -hold -from [get_cells {machine.cpu_input*}] -to [get_cells {machine.cpu.*}]
