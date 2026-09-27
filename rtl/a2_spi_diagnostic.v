// Independent A2 diagnostic endpoint. See docs/protocol.md for timing.
module a2_spi_diagnostic (
    input wire clk,
    input wire reset,
    input wire sck,
    input wire cs_n,
    input wire mosi,
    output wire miso,
    output wire irq
);
    (* async_reg = "true" *) reg [1:0] sck_sync;
    (* async_reg = "true" *) reg [1:0] cs_sync;
    (* async_reg = "true" *) reg [1:0] mosi_sync;
    reg sck_previous;
    wire rise = sck_sync[1] && !sck_previous;
    wire fall = !sck_sync[1] && sck_previous;

    reg [31:0] cycles;
    reg command_seen;
    reg echo_mode;
    reg [2:0] bit_index;
    reg [7:0] receive_shift;
    reg [7:0] transmit_shift;
    reg [7:0] echo_byte;
    reg [31:0] reply;
    wire [7:0] received = {receive_shift[6:0], mosi_sync[1]};

    // The first synchronizer stages are never consumed by protocol logic.
    always @(posedge clk) begin
        if (reset) begin
            sck_sync <= 0;
            cs_sync <= 2'b11;
            mosi_sync <= 0;
            sck_previous <= 0;
            cycles <= 0;
        end else begin
            sck_sync <= {sck_sync[0], sck};
            cs_sync <= {cs_sync[0], cs_n};
            mosi_sync <= {mosi_sync[0], mosi};
            sck_previous <= sck_sync[1];
            cycles <= cycles + 1'b1;
        end
    end

    always @(posedge clk) begin
        if (reset || cs_sync[1]) begin
            command_seen <= 0;
            echo_mode <= 0;
            bit_index <= 0;
            receive_shift <= 0;
            transmit_shift <= 0;
            echo_byte <= 0;
            reply <= 0;
        end else begin
            if (rise) begin
                receive_shift <= received;
                bit_index <= bit_index + 1'b1;
                if (bit_index == 7) begin
                    if (!command_seen) begin
                        command_seen <= 1;
                        echo_mode <= (received == 8'h30);
                        case (received)
                            8'h00: reply <= 32'h41320100;
                            8'h10: reply <= 32'hA5C33C5A;
                            8'h20: reply <= cycles;
                            8'h30: reply <= 0;
                            default: reply <= 32'hBAD0C0DE;
                        endcase
                    end else begin
                        echo_byte <= received;
                        reply <= {reply[23:0], 8'h00};
                    end
                end
            end
            if (fall) begin
                // bit_index wrapped at the eighth rising edge. The reply
                // has already been prepared before this falling edge.
                if (bit_index == 0)
                    transmit_shift <= echo_mode ? echo_byte : reply[31:24];
                else
                    transmit_shift <= {transmit_shift[6:0], 1'b0};
            end
        end
    end

    // Dedicated point-to-point MISO. Inactive CS forces a deterministic zero.
    assign miso = cs_n ? 1'b0 : transmit_shift[7];
    assign irq = 1'b0;
endmodule
