#include <array>
#include <fstream>
#include <iostream>
#include <iomanip>
#include "cpu_model.cc"

int main(int argc, char **argv) {
    std::array<unsigned char, 65536> mem{};
    std::ifstream file(argc > 1 ? argv[1] : "tests/6502_functional_test.bin", std::ios::binary);
    if (!file.read(reinterpret_cast<char *>(mem.data()), mem.size())) return 2;
    mem[0xfffc] = 0; mem[0xfffd] = 4;
    // Negative control deliberately replaces the entry opcode with an illegal one.
    if (argc > 2) mem[0x400] = 2;
    cxxrtl_design::p_cpu6502 cpu;
    cpu.p_ce.set<bool>(true); cpu.p_ready.set<bool>(true);
    cpu.p_irq.set<bool>(false); cpu.p_nmi.set<bool>(false);
    cpu.p_reset.set<bool>(true);
    cpu.p_clk.set<bool>(false); cpu.step();
    cpu.p_clk.set<bool>(true); cpu.step();
    cpu.p_reset.set<bool>(false);
    unsigned previous = 0xffff, repeated = 0;
    unsigned long long instructions = 0;
    for (unsigned long long cycle = 0; cycle < 150000000; ++cycle) {
        cpu.p_clk.set<bool>(false); cpu.step();
        unsigned address = cpu.p_addr.get<unsigned>();
        bool wr = cpu.p_write.get<bool>();
        if (cpu.p_sync.get<bool>()) {
            ++instructions;
            repeated = address == previous ? repeated + 1 : 0;
            previous = address;
            if (repeated > 3) {
                if (address == 0x3469) {
                    std::cout << "PASS: Klaus NMOS 6502 functional test, " << instructions
                              << " instructions, " << cycle << " bus cycles; success PC=$3469\n";
                    return 0;
                }
                std::cerr << "FAIL: trapped PC=$" << std::hex << address << " case=$" << unsigned(mem[0x200])
                          << " A=$" << cpu.p_debug__a.get<unsigned>() << " X=$" << cpu.p_debug__x.get<unsigned>()
                          << " Y=$" << cpu.p_debug__y.get<unsigned>() << " P=$" << cpu.p_debug__p.get<unsigned>()
                          << " SP=$" << cpu.p_debug__sp.get<unsigned>() << std::dec << " cycle=" << cycle << "\n";
                return 1;
            }
        }
        if (cpu.p_halted.get<bool>()) { std::cerr << "FAIL: illegal opcode\n"; return 1; }
        cpu.p_data__in.set<unsigned>(mem[address]); cpu.step();
        if (wr) mem[address] = cpu.p_data__out.get<unsigned>();
        cpu.p_clk.set<bool>(true); cpu.step();
    }
    std::cerr << "FAIL: cycle limit\n"; return 1;
}
