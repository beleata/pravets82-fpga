// A2 documented-instruction NMOS 6502 core, written from scratch.
// One enabled transition is one external bus cycle. data_in must be stable
// before it. ready stalls reads; writes always complete. See docs/cpu.md.
module cpu6502 (
    input wire clk, reset, ce, ready, irq, nmi,
    input wire [7:0] data_in,
    output reg [15:0] addr,
    output reg [7:0] data_out,
    output reg write,
    output wire sync, halted,
    output wire [15:0] debug_pc,
    output wire [7:0] debug_a, debug_x, debug_y, debug_sp, debug_p
);
`include "cpu6502_decode.vh"
localparam [5:0]
    RESET_LO=0, RESET_HI=1, FETCH=2, IMPLIED=3, IMMEDIATE=4,
    ZP_ADDR=5, ZP_INDEX=6, ABS_LO=7, ABS_HI=8, INDEX_DUMMY=9,
    MEM_READ=10, MEM_WRITE=11, PTR_BASE=12, PTR_INDEX=13,
    PTR_LO=14, PTR_HI=15, JMP_LO=16, JMP_HI=17,
    RMW_READ=18, RMW_DUMMY=19, RMW_WRITE=20,
    RELATIVE=21, BRANCH_DUMMY=22, BRANCH_FIX=23,
    JSR_LO=24, JSR_DUMMY=25, JSR_PUSH_H=26, JSR_PUSH_L=27, JSR_HI=28,
    PUSH_DUMMY=29, PUSH=30, PULL_DUMMY=31, PULL_STACK=32,
    PULL_VALUE=33, PULL_LO=34, PULL_HI=35, RTS_FINAL=36,
    BRK_PAD=37, INT_DUMMY=38, INT_PCH=39, INT_PCL=40, INT_P=41,
    VECTOR_LO=42, VECTOR_HI=43, STOP=44;
reg [5:0] state, op;
reg [3:0] mode;
reg [7:0] a, x, y, sp, p, lo, zp, old_value, new_value;
reg [15:0] pc, effective, dummy, target, vector;
reg crossed, interrupt_brk, nmi_last, nmi_pending;
wire [9:0] decoded = decode(data_in);
wire [5:0] decoded_op = decoded[9:4];
wire [3:0] decoded_mode = decoded[3:0];
wire store_op = op == OP_STA || op == OP_STX || op == OP_STY;
wire rmw_op = op == OP_ASL || op == OP_LSR || op == OP_ROL ||
              op == OP_ROR || op == OP_INC || op == OP_DEC;
wire [5:0] memory_state = store_op ? MEM_WRITE : rmw_op ? RMW_READ : MEM_READ;
wire [7:0] index_value = (mode == M_ABY || mode == M_ZPY || mode == M_INY) ? y : x;
wire [15:0] base_address = {data_in, lo};
wire [15:0] indexed_address = base_address + {8'b0, index_value};
wire [15:0] next_pc = pc + 16'd1;
wire [15:0] relative_target = next_pc + {{8{data_in[7]}}, data_in};
wire branch_taken = (op == OP_BPL && !p[7]) || (op == OP_BMI && p[7]) ||
    (op == OP_BVC && !p[6]) || (op == OP_BVS && p[6]) ||
    (op == OP_BCC && !p[0]) || (op == OP_BCS && p[0]) ||
    (op == OP_BNE && !p[1]) || (op == OP_BEQ && p[1]);
assign sync = state == FETCH;
assign halted = state == STOP;
assign debug_pc = pc;
assign debug_a = a;
assign debug_x = x;
assign debug_y = y;
assign debug_sp = sp;
assign debug_p = p;

always @* begin
    addr = pc;
    data_out = 0;
    write = 0;
    case (state)
        RESET_LO: addr = 16'hfffc;
        RESET_HI: addr = 16'hfffd;
        ZP_INDEX, PTR_INDEX, PTR_LO: addr = {8'b0, zp};
        PTR_HI: addr = {8'b0, (zp + 8'd1)};
        INDEX_DUMMY, BRANCH_FIX: addr = dummy;
        MEM_READ, MEM_WRITE, RMW_READ, RMW_DUMMY, RMW_WRITE,
        JMP_LO, RTS_FINAL: addr = effective;
        JMP_HI: addr = {effective[15:8], (effective[7:0] + 8'd1)};
        JSR_DUMMY, JSR_PUSH_H, JSR_PUSH_L, PUSH, PULL_STACK,
        PULL_VALUE, PULL_LO, PULL_HI, INT_PCH, INT_PCL, INT_P:
            addr = {8'h01, sp};
        VECTOR_LO: addr = vector;
        VECTOR_HI: addr = vector + 16'd1;
        default: addr = pc;
    endcase
    case (state)
        MEM_WRITE: begin write = 1; data_out = op == OP_STA ? a : op == OP_STX ? x : y; end
        RMW_DUMMY: begin write = 1; data_out = old_value; end
        RMW_WRITE: begin write = 1; data_out = new_value; end
        JSR_PUSH_H, INT_PCH: begin write = 1; data_out = pc[15:8]; end
        JSR_PUSH_L, INT_PCL: begin write = 1; data_out = pc[7:0]; end
        PUSH: begin write = 1; data_out = op == OP_PHA ? a : p | 8'h30; end
        INT_P: begin write = 1; data_out = interrupt_brk ? p | 8'h30 : (p | 8'h20) & 8'hef; end
        default: begin end
    endcase
end

task set_nz;
    input [7:0] value;
    begin p[7] <= value[7]; p[1] <= value == 0; end
endtask

// NMOS decimal N/V/Z differ from the later CMOS 65C02.
task arithmetic;
    input [7:0] value;
    reg [8:0] sum;
    reg [7:0] result, intermediate, lhs;
    reg [5:0] low_digit, high_digit;
    begin
        case (op)
            OP_ORA: begin a <= a | value; set_nz(a | value); end
            OP_AND: begin a <= a & value; set_nz(a & value); end
            OP_EOR: begin a <= a ^ value; set_nz(a ^ value); end
            OP_LDA: begin a <= value; set_nz(value); end
            OP_LDX: begin x <= value; set_nz(value); end
            OP_LDY: begin y <= value; set_nz(value); end
            OP_BIT: begin p[7:6] <= value[7:6]; p[1] <= (a & value) == 0; end
            OP_CMP, OP_CPX, OP_CPY: begin
                lhs = op == OP_CMP ? a : op == OP_CPX ? x : y;
                sum = {1'b0, lhs} + {1'b0, ~value} + 9'd1;
                p[0] <= sum[8]; set_nz(sum[7:0]);
            end
            OP_ADC: begin
                sum = {1'b0, a} + {1'b0, value} + {8'b0, p[0]};
                result = sum[7:0];
                if (p[3]) begin
                    low_digit = {2'b0, a[3:0]} + {2'b0, value[3:0]} + {5'b0, p[0]};
                    high_digit = {2'b0, a[7:4]} + {2'b0, value[7:4]} + (low_digit > 9 ? 6'd1 : 6'd0);
                    if (low_digit > 9) low_digit = low_digit + 6'd6;
                    intermediate = {high_digit[3:0], low_digit[3:0]};
                    p[7] <= intermediate[7];
                    p[6] <= (~(a[7] ^ value[7])) & (a[7] ^ intermediate[7]);
                    p[1] <= result == 0;
                    p[0] <= high_digit > 9;
                    if (high_digit > 9) high_digit = high_digit + 6'd6;
                    a <= {high_digit[3:0], low_digit[3:0]};
                end else begin
                    a <= result; set_nz(result); p[0] <= sum[8];
                    p[6] <= (~(a[7] ^ value[7])) & (a[7] ^ result[7]);
                end
            end
            OP_SBC: begin
                sum = {1'b0, a} + {1'b0, ~value} + {8'b0, p[0]};
                result = sum[7:0];
                p[0] <= sum[8]; set_nz(result);
                p[6] <= (a[7] ^ value[7]) & (a[7] ^ result[7]);
                if (p[3]) begin
                    low_digit = {2'b0, a[3:0]} - {2'b0, value[3:0]} - (p[0] ? 6'd0 : 6'd1);
                    high_digit = {2'b0, a[7:4]} - {2'b0, value[7:4]} - (low_digit[5] ? 6'd1 : 6'd0);
                    if (low_digit[5]) low_digit = low_digit - 6'd6;
                    if (high_digit[5]) high_digit = high_digit - 6'd6;
                    a <= {high_digit[3:0], low_digit[3:0]};
                end else a <= result;
            end
            default: begin end
        endcase
    end
endtask

function [7:0] modified;
    input [7:0] value;
    begin
        case (op)
            OP_ASL: modified = {value[6:0], 1'b0};
            OP_LSR: modified = {1'b0, value[7:1]};
            OP_ROL: modified = {value[6:0], p[0]};
            OP_ROR: modified = {p[0], value[7:1]};
            OP_INC: modified = value + 8'd1;
            default: modified = value - 8'd1;
        endcase
    end
endfunction
task modify_flags;
    input [7:0] value;
    begin
        set_nz(modified(value));
        if (op == OP_ASL || op == OP_ROL) p[0] <= value[7];
        if (op == OP_LSR || op == OP_ROR) p[0] <= value[0];
    end
endtask

always @(posedge clk) begin
    if (reset) begin
        state <= RESET_LO; op <= OP_NOP; mode <= M_IMP;
        a <= 0; x <= 0; y <= 0; sp <= 8'hfd; p <= 8'h24; pc <= 0;
        lo <= 0; zp <= 0; old_value <= 0; new_value <= 0;
        effective <= 0; dummy <= 0; target <= 0; vector <= 16'hfffe;
        crossed <= 0; interrupt_brk <= 0; nmi_last <= 0; nmi_pending <= 0;
    end else begin
        nmi_last <= nmi;
        if (nmi && !nmi_last) nmi_pending <= 1;
        if (ce && (ready || write)) begin
            case (state)
                RESET_LO: begin lo <= data_in; state <= RESET_HI; end
                RESET_HI: begin pc <= {data_in, lo}; state <= FETCH; end
                FETCH: begin
                    if (nmi_pending || (irq && !p[2])) begin
                        vector <= nmi_pending ? 16'hfffa : 16'hfffe;
                        if (nmi_pending) nmi_pending <= nmi && !nmi_last;
                        interrupt_brk <= 0; state <= INT_DUMMY;
                    end else begin
                        op <= decoded_op; mode <= decoded_mode; pc <= next_pc;
                        case (decoded_op)
                            OP_ILL: state <= STOP;
                            OP_BRK: begin state <= BRK_PAD; vector <= 16'hfffe; interrupt_brk <= 1; end
                            OP_JSR: state <= JSR_LO;
                            OP_PHA, OP_PHP: state <= PUSH_DUMMY;
                            OP_PLA, OP_PLP, OP_RTS, OP_RTI: state <= PULL_DUMMY;
                            default: case (decoded_mode)
                                M_IMP, M_ACC: state <= IMPLIED;
                                M_IMM: state <= IMMEDIATE;
                                M_ZP, M_ZPX, M_ZPY: state <= ZP_ADDR;
                                M_ABS, M_ABX, M_ABY, M_IND: state <= ABS_LO;
                                M_INX, M_INY: state <= PTR_BASE;
                                M_REL: state <= RELATIVE;
                                default: state <= STOP;
                            endcase
                        endcase
                    end
                end
                IMPLIED: begin
                    state <= FETCH;
                    case (op)
                        OP_ASL, OP_LSR, OP_ROL, OP_ROR: begin a <= modified(a); modify_flags(a); end
                        OP_CLC: p[0] <= 0;
                        OP_SEC: p[0] <= 1;
                        OP_CLI: p[2] <= 0;
                        OP_SEI: p[2] <= 1;
                        OP_CLD: p[3] <= 0;
                        OP_SED: p[3] <= 1;
                        OP_CLV: p[6] <= 0;
                        OP_TAX: begin x <= a; set_nz(a); end
                        OP_TAY: begin y <= a; set_nz(a); end
                        OP_TXA: begin a <= x; set_nz(x); end
                        OP_TYA: begin a <= y; set_nz(y); end
                        OP_TSX: begin x <= sp; set_nz(sp); end
                        OP_TXS: sp <= x;
                        OP_INX: begin x <= x + 8'd1; set_nz(x + 8'd1); end
                        OP_INY: begin y <= y + 8'd1; set_nz(y + 8'd1); end
                        OP_DEX: begin x <= x - 8'd1; set_nz(x - 8'd1); end
                        OP_DEY: begin y <= y - 8'd1; set_nz(y - 8'd1); end
                        default: begin end
                    endcase
                end
                IMMEDIATE: begin arithmetic(data_in); pc <= next_pc; state <= FETCH; end
                ZP_ADDR: begin
                    zp <= data_in; effective <= {8'b0, data_in}; pc <= next_pc;
                    state <= mode == M_ZP ? memory_state : ZP_INDEX;
                end
                ZP_INDEX: begin effective <= {8'b0, (zp + index_value)}; state <= memory_state; end
                ABS_LO: begin lo <= data_in; pc <= next_pc; state <= ABS_HI; end
                ABS_HI: begin
                    pc <= next_pc;
                    if (op == OP_JMP) begin
                        if (mode == M_IND) begin effective <= base_address; state <= JMP_LO; end
                        else begin pc <= base_address; state <= FETCH; end
                    end else if (mode == M_ABX || mode == M_ABY) begin
                        effective <= indexed_address; dummy <= {data_in, indexed_address[7:0]};
                        state <= (indexed_address[15:8] != data_in || store_op || rmw_op) ? INDEX_DUMMY : memory_state;
                    end else begin effective <= base_address; state <= memory_state; end
                end
                INDEX_DUMMY: state <= memory_state;
                PTR_BASE: begin zp <= data_in; pc <= next_pc; state <= mode == M_INX ? PTR_INDEX : PTR_LO; end
                PTR_INDEX: begin zp <= zp + x; state <= PTR_LO; end
                PTR_LO: begin lo <= data_in; state <= PTR_HI; end
                PTR_HI: begin
                    if (mode == M_INY) begin
                        effective <= indexed_address; dummy <= {data_in, indexed_address[7:0]};
                        state <= (indexed_address[15:8] != data_in || store_op) ? INDEX_DUMMY : MEM_READ;
                    end else begin effective <= base_address; state <= memory_state; end
                end
                JMP_LO: begin lo <= data_in; state <= JMP_HI; end
                JMP_HI: begin pc <= base_address; state <= FETCH; end
                MEM_READ: begin arithmetic(data_in); state <= FETCH; end
                MEM_WRITE: state <= FETCH;
                RMW_READ: begin
                    old_value <= data_in; new_value <= modified(data_in);
                    modify_flags(data_in); state <= RMW_DUMMY;
                end
                RMW_DUMMY: state <= RMW_WRITE;
                RMW_WRITE: state <= FETCH;
                RELATIVE: begin
                    pc <= next_pc; target <= relative_target;
                    crossed <= next_pc[15:8] != relative_target[15:8];
                    dummy <= {next_pc[15:8], relative_target[7:0]};
                    state <= branch_taken ? BRANCH_DUMMY : FETCH;
                end
                BRANCH_DUMMY: begin
                    if (crossed) state <= BRANCH_FIX;
                    else begin pc <= target; state <= FETCH; end
                end
                BRANCH_FIX: begin pc <= target; state <= FETCH; end
                JSR_LO: begin lo <= data_in; pc <= next_pc; state <= JSR_DUMMY; end
                JSR_DUMMY: state <= JSR_PUSH_H;
                JSR_PUSH_H: begin sp <= sp - 8'd1; state <= JSR_PUSH_L; end
                JSR_PUSH_L: begin sp <= sp - 8'd1; state <= JSR_HI; end
                JSR_HI: begin pc <= base_address; state <= FETCH; end
                PUSH_DUMMY: state <= PUSH;
                PUSH: begin sp <= sp - 8'd1; state <= FETCH; end
                PULL_DUMMY: state <= PULL_STACK;
                PULL_STACK: begin sp <= sp + 8'd1; state <= op == OP_RTS ? PULL_LO : PULL_VALUE; end
                PULL_VALUE: begin
                    if (op == OP_PLA) begin a <= data_in; set_nz(data_in); state <= FETCH; end
                    else begin
                        p <= (data_in | 8'h20) & 8'hef;
                        if (op == OP_RTI) begin sp <= sp + 8'd1; state <= PULL_LO; end
                        else state <= FETCH;
                    end
                end
                PULL_LO: begin lo <= data_in; sp <= sp + 8'd1; state <= PULL_HI; end
                PULL_HI: begin
                    if (op == OP_RTI) begin pc <= base_address; state <= FETCH; end
                    else begin effective <= base_address; state <= RTS_FINAL; end
                end
                RTS_FINAL: begin pc <= effective + 16'd1; state <= FETCH; end
                BRK_PAD: begin pc <= next_pc; state <= INT_PCH; end
                INT_DUMMY: state <= INT_PCH;
                INT_PCH: begin sp <= sp - 8'd1; state <= INT_PCL; end
                INT_PCL: begin sp <= sp - 8'd1; state <= INT_P; end
                INT_P: begin sp <= sp - 8'd1; p[2] <= 1; state <= VECTOR_LO; end
                VECTOR_LO: begin lo <= data_in; state <= VECTOR_HI; end
                VECTOR_HI: begin pc <= base_address; state <= FETCH; end
                default: state <= STOP;
            endcase
        end
    end
end
endmodule
