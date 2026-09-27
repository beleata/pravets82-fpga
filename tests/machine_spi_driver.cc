#include <array>
#include <iostream>
#include <stdexcept>
#include <vector>
#include "machine_spi_model.cc"
struct Test {
    cxxrtl_design::p_a2__spi__machine dut;
    std::array<unsigned char,65536> mem{};
    unsigned reset_pulses=0;
    void cycle() {
        dut.p_clk.set<bool>(false); dut.step();
        unsigned address=dut.p_host__addr.get<unsigned>();
        unsigned read=mem[address];
        if(dut.p_host__write.get<bool>()) mem[address]=dut.p_host__data.get<unsigned>();
        if(dut.p_cpu__reset.get<bool>()) ++reset_pulses;
        dut.p_clk.set<bool>(true); dut.step();
        dut.p_host__read.set<unsigned>(read); dut.step();
    }
    void hold(unsigned n=12) {while(n--) cycle();}
    Test() {
        dut.p_cs__n.set<bool>(true); dut.p_reset.set<bool>(true); hold();
        dut.p_reset.set<bool>(false); hold();
        dut.p_debug__pc.set<unsigned>(0x1234); dut.p_debug__a.set<unsigned>(0x56);
        dut.p_debug__x.set<unsigned>(0x78); dut.p_debug__y.set<unsigned>(0x9a);
        dut.p_debug__sp.set<unsigned>(0xbc); dut.p_debug__p.set<unsigned>(0x24);
        dut.p_key__ready.set<bool>(true); dut.p_video__mode.set<unsigned>(1);
    }
    std::vector<unsigned char> transfer(const std::vector<unsigned char> &tx) {
        std::vector<unsigned char> rx;
        dut.p_cs__n.set<bool>(false); hold();
        for(auto byte:tx) {
            unsigned value=0;
            for(int bit=7;bit>=0;--bit) {
                dut.p_mosi.set<bool>((byte>>bit)&1); hold();
                dut.p_sck.set<bool>(true); hold();
                value=(value<<1)|dut.p_miso.get<unsigned>();
                dut.p_sck.set<bool>(false); hold();
            }
            rx.push_back(value);
        }
        dut.p_cs__n.set<bool>(true); hold(); return rx;
    }
};
void require(bool yes) {if(!yes) throw std::runtime_error("SPI machine assertion failed");}
int main() {try {
    Test t;
    require(t.transfer({0,0,0,0,0})==std::vector<unsigned char>({0,0x41,0x32,1,0}));
    std::vector<unsigned char> write{0x41,0x3f,0xf0};
    for(unsigned i=0;i<8191;++i) write.push_back((i*79+13)&255);
    t.transfer(write);
    for(unsigned i=0;i<8191;++i) require(t.mem[0x3ff0+i]==write[i+3]);
    std::vector<unsigned char> read(8194); read[0]=0x40; read[1]=0x3f; read[2]=0xf0;
    auto rx=t.transfer(read);
    for(unsigned i=0;i<8190;++i) require(rx[i+4]==write[i+3]);
    t.transfer({0x42,1}); require(t.dut.p_running.get<bool>());
    t.transfer({0x41,0x3f,0xf0,0xff}); require(t.mem[0x3ff0]==13);
    require(t.transfer({0x40,0x3f,0xf0,0,0})[4]==13);
    auto pulses=t.reset_pulses; t.transfer({0x42,2});
    require(!t.dut.p_running.get<bool>() && t.reset_pulses==pulses+1);
    rx=t.transfer(std::vector<unsigned char>{0x43,0,0,0,0,0,0,0,0,0,0});
    require(rx==std::vector<unsigned char>({0,2,0,0x12,0x34,0x56,0x78,0x9a,0xbc,0x24,0}));
    require(t.transfer({0x44,0x41,0})[2]==1);
    require(t.dut.p_key__data.get<unsigned>()==0x41);
    t.dut.p_key__ready.set<bool>(false); require(t.transfer({0x44,0x42,0})[2]==0);
    require(t.transfer({0x45,0,0,0,0})==std::vector<unsigned char>({0,2,1,1,0}));
    // Partial address must never write memory, including after the next CS.
    t.transfer({0x41,0x80}); t.transfer({0x41,0x90,0x00,0xa5});
    require(t.mem[0x9000]==0xa5 && t.mem[0x8000]==0);
    t.transfer({0x41,0xff,0xff,0x5a,0xa5}); require(t.mem[0xffff]==0x5a && t.mem[0]==0xa5);
    std::cout<<"PASS: SPI block read/write, address wrap, CPU controls/status, running protection, partial CS\n";
    return 0;
}catch(const std::exception &e){std::cerr<<"FAIL: "<<e.what()<<"\n";return 1;}}
