// AGM TCX wrapper. Pin and voltage settings are in board/a2_link.qsf.
module a2_link_top (
    input wire clk,
    input wire sck,
    input wire cs_n,
    input wire mosi,
    output wire miso,
    output wire irq,
    output wire led_n
);
    // Initialized flip-flops hold the core in reset for 128 oscillator clocks.
    // No dependence on PLL lock or an unverified external reset button.
    reg [7:0] startup = 0;
    always @(posedge clk)
        if (!startup[7]) startup <= startup + 1'b1;
    wire reset = !startup[7];

    reg [24:0] heartbeat = 0;
    always @(posedge clk) heartbeat <= heartbeat + 1'b1;
    assign led_n = !heartbeat[24];

    a2_machine machine (
        .clk(clk), .reset(reset), .sck(sck), .cs_n(cs_n),
        .mosi(mosi), .miso(miso), .irq(irq)
    );
endmodule
