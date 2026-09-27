// Development memory map: 48 KiB RAM + 4 KiB writable vector/test bank.
// Apple II keyboard latch and text/graphics switches; no disk/ROM chipset yet.
module a2_machine (
    input wire clk, reset, sck, cs_n, mosi,
    output wire miso, irq
);
    wire [15:0] host_addr, cpu_addr, debug_pc;
    wire [7:0] host_data, cpu_data, debug_a, debug_x, debug_y, debug_sp, debug_p;
    wire host_write, running, cpu_reset, halted, cpu_write, sync;
    wire key_valid;
    wire [6:0] key_data;
    reg [7:0] keyboard;
    reg [3:0] video_mode;
    reg [5:0] divider;
    wire ce = running && divider == 49;
    always @(posedge clk) begin
        if (reset || cpu_reset || !running || divider == 49) divider <= 0;
        else divider <= divider + 1'b1;
    end
    wire [15:0] address = running ? cpu_addr : host_addr;
    wire [7:0] wr_data = running ? cpu_data : host_data;
    wire wr = running ? (ce && cpu_write) : host_write;
    // Normalize unmapped reads into a valid physical index. Their result is
    // masked by bank, and writes remain gated by the original CPU address.
    wire [15:0] ram_address = {address[15], address[14] && !address[15], address[13:0]};
    wire [15:0] host_ram_address = {host_addr[15], host_addr[14] && !host_addr[15], host_addr[13:0]};
    reg [7:0] ram [0:49151];
    reg [7:0] vectors [0:4095];
    reg [7:0] ram_q, vectors_q;
    reg [7:0] host_ram_q, host_vectors_q;
    reg [1:0] bank;
    reg [1:0] host_bank;
    always @(posedge clk) begin
        if (wr && address < 16'hc000) ram[ram_address] <= wr_data;
        if (wr && address >= 16'hf000) vectors[address[11:0]] <= wr_data;
        // Keep read/write addresses identical so the mapper combines them
        // into one physical R/W port.
        ram_q <= ram[ram_address];
        vectors_q <= vectors[address[11:0]];
        bank <= address < 16'hc000 ? 0 : address >= 16'hf000 ? 1 : 2;
    end
    // Independent read-only second BRAM ports: video never stops the CPU.
    always @(posedge clk) begin
        host_ram_q <= ram[host_ram_address];
        host_vectors_q <= vectors[host_addr[11:0]];
        host_bank <= host_addr < 16'hc000 ? 0 : host_addr >= 16'hf000 ? 1 : 2;
    end
    // No joystick is connected: cassette input and pushbuttons are released.
    // Returning $FF here falsely held both game buttons down.
    wire [7:0] io_read = address[15:4] == 12'hc00 ? keyboard :
                         address[15:2] == 14'h3018 ? 8'h00 : 8'hff;
    wire [7:0] host_io_read = host_addr[15:4] == 12'hc00 ? keyboard :
                              host_addr[15:2] == 14'h3018 ? 8'h00 : 8'hff;
    wire [7:0] rd_data = bank == 0 ? ram_q : bank == 1 ? vectors_q : io_read;
    wire [7:0] host_rd_data = host_bank == 0 ? host_ram_q : host_bank == 1 ? host_vectors_q : host_io_read;
    always @(posedge clk) begin
        if (reset || cpu_reset) begin
            keyboard <= 0; video_mode <= 4'b0001;
        end else begin
            if (ce && cpu_addr[15:4] == 12'hc01) keyboard[7] <= 0;
            if (key_valid && !keyboard[7]) keyboard <= {1'b1, key_data};
            if (ce && cpu_addr[15:3] == 13'h180a) begin // $C050-$C057, read or write
                case (cpu_addr[2:0])
                    0: video_mode[0] <= 0;
                    1: video_mode[0] <= 1;
                    2: video_mode[1] <= 0;
                    3: video_mode[1] <= 1;
                    4: video_mode[2] <= 0;
                    5: video_mode[2] <= 1;
                    6: video_mode[3] <= 0;
                    7: video_mode[3] <= 1;
                endcase
            end
        end
    end
    // Capture CPU input three oscillator clocks before its enabled transition.
    // This makes the input-to-core multicycle relationship explicit in RTL.
    // Host reads continue to use the unlatched synchronous RAM output.
    reg [7:0] cpu_input;
    always @(posedge clk) begin
        if (reset || cpu_reset) cpu_input <= 0;
        else if (running && divider == 46) cpu_input <= rd_data;
    end
    cpu6502 cpu(.clk(clk), .reset(reset || cpu_reset), .ce(ce), .ready(1'b1),
        .irq(1'b0), .nmi(1'b0), .data_in(cpu_input), .addr(cpu_addr), .data_out(cpu_data),
        .write(cpu_write), .sync(sync), .halted(halted), .debug_pc(debug_pc),
        .debug_a(debug_a), .debug_x(debug_x), .debug_y(debug_y), .debug_sp(debug_sp), .debug_p(debug_p));
    a2_spi_machine endpoint(.clk(clk), .reset(reset), .sck(sck), .cs_n(cs_n), .mosi(mosi),
        .miso(miso), .host_addr(host_addr), .host_data(host_data), .host_write(host_write),
        .host_read(host_rd_data), .key_valid(key_valid), .key_data(key_data),
        .key_ready(!keyboard[7]), .video_mode(video_mode),
        .running(running), .cpu_reset(cpu_reset), .halted(halted),
        .debug_pc(debug_pc), .debug_a(debug_a), .debug_x(debug_x), .debug_y(debug_y),
        .debug_sp(debug_sp), .debug_p(debug_p));
    assign irq = halted;
endmodule
