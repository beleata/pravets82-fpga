// Negative control: this simulation MUST fail. It checks that the simulator
// enforces the assertions used by run_rtl.py instead of silently ignoring them.
module assertion_probe(input clk);
    reg [3:0] ticks = 0;
    always @(posedge clk) ticks <= ticks + 1'b1;
    always @* if (ticks == 3) assert(1'b0);
endmodule
