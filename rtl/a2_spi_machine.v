// SPI mode 0 endpoint. Reads are live; writes require paused CPU.
// Fixed diagnostics remain compatible with the standalone endpoint.
module a2_spi_machine (
    input wire clk, reset, sck, cs_n, mosi,
    output wire miso,
    output reg [15:0] host_addr,
    output reg [7:0] host_data,
    output reg host_write,
    input wire [7:0] host_read,
    output reg key_valid,
    output reg [6:0] key_data,
    input wire key_ready,
    input wire [3:0] video_mode,
    output reg running, cpu_reset,
    input wire halted,
    input wire [15:0] debug_pc,
    input wire [7:0] debug_a, debug_x, debug_y, debug_sp, debug_p
);
    (* async_reg = "true" *) reg [1:0] sck_sync, cs_sync, mosi_sync;
    reg sck_previous;
    wire rise = sck_sync[1] && !sck_previous;
    wire fall = !sck_sync[1] && sck_previous;
    reg [31:0] cycles, reply;
    reg [7:0] opcode, rx_shift, tx_shift, echo_byte;
    reg [2:0] bit_index, phase;
    reg [7:0] address_high;
    reg [79:0] status;
    wire [7:0] received = {rx_shift[6:0], mosi_sync[1]};
    assign miso = cs_n ? 1'b0 : tx_shift[7];

    always @(posedge clk) begin
        if (reset) begin
            sck_sync <= 0; cs_sync <= 3; mosi_sync <= 0;
            sck_previous <= 0; cycles <= 0;
        end else begin
            sck_sync <= {sck_sync[0], sck}; cs_sync <= {cs_sync[0], cs_n};
            mosi_sync <= {mosi_sync[0], mosi}; sck_previous <= sck_sync[1];
            cycles <= cycles + 1'b1;
        end
    end
    always @(posedge clk) begin
        host_write <= 0;
        cpu_reset <= 0;
        key_valid <= 0;
        // Keep write address stable until the synchronous RAM has consumed it.
        if (host_write) host_addr <= host_addr + 16'd1;
        if (reset) begin
            running <= 0; cpu_reset <= 1; host_addr <= 0; host_data <= 0; key_data <= 0;
        end
        if (reset || cs_sync[1]) begin
            opcode <= 0; rx_shift <= 0; tx_shift <= 0; echo_byte <= 0;
            bit_index <= 0; phase <= 0; address_high <= 0; reply <= 0; status <= 0;
        end else begin
            if (rise) begin
                rx_shift <= received;
                bit_index <= bit_index + 1'b1;
                if (bit_index == 7) begin
                    if (phase == 0) begin
                        opcode <= received; phase <= 1;
                        // 10 bytes, captured together at command boundary.
                        status <= {8'h02, 6'b0, halted, running, debug_pc,
                                   debug_a, debug_x, debug_y, debug_sp, debug_p, 8'h00};
                        case (received)
                            8'h00: reply <= 32'h41320100;
                            8'h10: reply <= 32'hA5C33C5A;
                            8'h20: reply <= cycles;
                            8'h30, 8'h40, 8'h41, 8'h42, 8'h43, 8'h44: reply <= 0;
                            8'h45: reply <= {8'h02, 4'b0, video_mode, 7'b0, !key_ready, 8'h00};
                            default: reply <= 32'hBAD0C0DE;
                        endcase
                    end else begin
                        echo_byte <= received;
                        reply <= {reply[23:0], 8'h00};
                        status <= {status[71:0], 8'h00};
                        if (phase < 5) phase <= phase + 1'b1;
                        if (opcode == 8'h40 || opcode == 8'h41) begin
                            if (phase == 1) address_high <= received;
                            if (phase == 2) host_addr <= {address_high, received};
                            if (opcode == 8'h41 && phase >= 3 && !running) begin
                                host_data <= received; host_write <= 1;
                            end
                            if (opcode == 8'h40 && phase >= 4) host_addr <= host_addr + 16'd1;
                        end
                        if (opcode == 8'h42 && phase == 1) begin
                            // 0 pause, 1 run, 2 reset+pause, 3 reset+run.
                            running <= received[0]; cpu_reset <= received[1];
                        end
                        if (opcode == 8'h44 && phase == 1) begin
                            // The following byte returns 1 accepted / 0 busy.
                            key_data <= received[6:0]; key_valid <= key_ready;
                            reply <= {7'b0, key_ready, 24'b0};
                        end
                    end
                end
            end
            if (fall) begin
                if (bit_index == 0) begin
                    case (opcode)
                        8'h30: tx_shift <= echo_byte;
                        8'h40: tx_shift <= phase >= 4 ? host_read : 8'h00;
                        8'h43: tx_shift <= status[79:72];
                        default: tx_shift <= reply[31:24];
                    endcase
                end else tx_shift <= {tx_shift[6:0], 1'b0};
            end
        end
    end
endmodule
