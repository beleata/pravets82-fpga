#include <fstream>
#include <iostream>
#include "model.cc"

int main() {
    cxxrtl_design::p_a2__spi__diagnostic dut;
    std::ifstream input("stimulus.hex");
    if (!input) return 2;
    unsigned entry;
    unsigned long cycle = 0;
    while (input >> std::hex >> entry) {
        unsigned sample = entry & 63;
        unsigned length = entry >> 6;
        for (unsigned repeat = 0; repeat < length; ++repeat, ++cycle) {
            dut.p_reset.set<bool>((sample >> 5) & 1);
            dut.p_cs__n.set<bool>((sample >> 4) & 1);
            dut.p_sck.set<bool>((sample >> 3) & 1);
            dut.p_mosi.set<bool>((sample >> 2) & 1);
            for (bool level : {false, true}) {
                dut.p_clk.set<bool>(level);
                dut.step();
                if (((sample & 2) && dut.p_miso.get<unsigned>() != (sample & 1))
                    || dut.p_irq.get<unsigned>() != 0) {
                    std::cerr << "FAIL at cycle " << cycle << ", clk=" << level
                              << ", expected=" << (sample & 1)
                              << ", MISO=" << dut.p_miso.get<unsigned>() << "\n";
                    return 1;
                }
            }
        }
    }
    std::cout << "CXXRTL checked " << cycle << " core cycles\n";
    return 0;
}
