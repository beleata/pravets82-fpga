#include <iostream>
#include <stdexcept>
#include <vector>
#include <fstream>
#include "machine_system_model.cc"
struct Machine {
    cxxrtl_design::p_a2__machine dut;
    void hold(unsigned n=12) {
        while(n--) { dut.p_clk.set<bool>(false); dut.step(); dut.p_clk.set<bool>(true); dut.step(); }
    }
    Machine() {
        dut.p_cs__n.set<bool>(true); dut.p_reset.set<bool>(true); hold();
        dut.p_reset.set<bool>(false); hold();
    }
    std::vector<unsigned char> transfer(std::vector<unsigned char> tx) {
        std::vector<unsigned char> rx;
        dut.p_cs__n.set<bool>(false); hold();
        for(auto byte:tx) {
            unsigned value=0;
            for(int bit=7;bit>=0;--bit) {
                dut.p_mosi.set<bool>((byte>>bit)&1); hold();
                dut.p_sck.set<bool>(true); hold(); value=(value<<1)|dut.p_miso.get<unsigned>();
                dut.p_sck.set<bool>(false); hold();
            }
            rx.push_back(value);
        }
        dut.p_cs__n.set<bool>(true); hold(); return rx;
    }
    std::vector<unsigned char> read(unsigned addr,unsigned n) {
        std::vector<unsigned char> tx(n+4); tx[0]=0x40; tx[1]=addr>>8; tx[2]=addr;
        auto rx=transfer(tx); return {rx.begin()+4,rx.end()};
    }
};
void require(bool yes){if(!yes)throw std::runtime_error("integrated machine assertion failed");}
int main(){try {
    Machine m;
    // LDX #0; TXA; STA $0400,X; INX; BNE $0602; JMP $0609.
    m.transfer({0x41,6,0,0xa2,0,0x8a,0x9d,0,4,0xe8,0xd0,0xf9,0x4c,9,6});
    m.transfer({0x41,0xff,0xfc,0,6}); m.transfer({0x42,3});
    m.hold(20000); m.transfer({0x42,0});
    auto paused=m.transfer({0x43,0,0,0,0,0,0,0,0,0,0});
    m.hold(2000); require(paused==m.transfer({0x43,0,0,0,0,0,0,0,0,0,0}));
    // Resume must re-establish synchronous memory data before the next CE.
    m.transfer({0x42,1}); m.hold(160000); m.transfer({0x42,0});
    auto result=m.read(0x400,256); for(unsigned i=0;i<256;++i) require(result[i]==i);
    require(!m.dut.p_irq.get<bool>());
    require(m.read(0xc100,8)==std::vector<unsigned char>(8,0xff));
    m.transfer({0x41,6,0,2}); m.transfer({0x42,3}); m.hold(500);
    require(m.dut.p_irq.get<bool>()); m.transfer({0x42,2}); require(!m.dut.p_irq.get<bool>());
    // Load the real text demo over SPI and type while the CPU is running.
    std::ifstream file("../text-demo.bin",std::ios::binary);
    require(bool(file));
    std::vector<unsigned char> program{0x41,0x10,0};
    program.insert(program.end(),std::istreambuf_iterator<char>(file),{});
    m.transfer(program); m.transfer({0x41,0xff,0xfc,0,0x10}); m.transfer({0x42,3});
    m.hold(700000);
    auto text=m.read(0x400,40); require(text[0]==('P'|128) && text[7]==(' '|128));
    require(m.transfer({0x43,0,0,0,0,0,0,0,0,0,0})[2]==1);
    require(m.transfer({0x44,'A',0})[2]==1); m.hold(15000);
    require(m.read(0x680,1)[0]==('A'|128));
    require(m.transfer({0x44,13,0})[2]==1); m.hold(15000);
    require(m.transfer({0x44,'B',0})[2]==1); m.hold(15000);
    require(m.read(0x700,1)[0]==('B'|128));
    require(m.transfer({0x44,8,0})[2]==1); m.hold(15000); require(m.read(0x700,1)[0]==0xa0);
    require(m.read(0xc000,1)[0]==8); // data retained, strobe cleared by CPU
    m.transfer({0x42,0}); require(m.transfer({0x44,'X',0})[2]==1);
    require(m.transfer({0x44,'Y',0})[2]==0); require(m.read(0xc000,1)[0]==('X'|128));
    // Read and write accesses both toggle switches; host observation does not.
    m.transfer({0x42,2});
    m.transfer({0x41,0x10,0,0xad,0x55,0xc0,0x8d,0x50,0xc0,0xad,0x53,0xc0,
                0xad,0x57,0xc0,0x4c,0x0c,0x10}); m.transfer({0x42,3}); m.hold(3000);
    require(m.transfer({0x45,0,0,0,0})[2]==14);
    m.read(0xc051,1); require(m.transfer({0x45,0,0,0,0})[2]==14);
    std::cout<<"PASS: integrated CPU/RAM, live text while running, keyboard strobe/backpressure, newline/backspace, video switches\n";
    return 0;
}catch(const std::exception&e){std::cerr<<"FAIL: "<<e.what()<<"\n";return 1;}}
