// Directed external bus tests supplement the independent instruction suite.
#include <array>
#include <iostream>
#include <stdexcept>
#include <vector>
#include "cpu_model.cc"
struct Bus { unsigned addr, data; bool write; };
struct Machine {
    cxxrtl_design::p_cpu6502 cpu;
    std::array<unsigned char,65536> mem{};
    Machine() {
        mem.fill(0xea); mem[0xfffc]=0; mem[0xfffd]=2;
        cpu.p_ce.set<bool>(true); cpu.p_ready.set<bool>(true);
        cpu.p_reset.set<bool>(true); tick(); cpu.p_reset.set<bool>(false);
        tick(); tick();
    }
    Bus tick() {
        cpu.p_clk.set<bool>(false); cpu.step();
        unsigned address=cpu.p_addr.get<unsigned>();
        cpu.p_data__in.set<unsigned>(mem[address]); cpu.step();
        Bus b{address,cpu.p_data__out.get<unsigned>(),cpu.p_write.get<bool>()};
        if (b.write && cpu.p_ce.get<bool>()) mem[address]=b.data;
        cpu.p_clk.set<bool>(true); cpu.step();
        return b;
    }
    void code(std::initializer_list<unsigned char> bytes) { std::copy(bytes.begin(),bytes.end(),mem.begin()+0x200); }
    void expect(std::initializer_list<unsigned> addresses) {
        for (auto expected: addresses) {
            auto got=tick();
            if (got.addr!=expected) {
                std::cerr<<"address $"<<std::hex<<got.addr<<" expected $"<<expected<<"\n";
                throw std::runtime_error("bus address mismatch");
            }
        }
    }
};
void require(bool yes) { if(!yes) throw std::runtime_error("bus assertion failed"); }
int main() { try {
    { Machine m; m.code({0xa2,1,0xbd,0xff,0x12,0x9d,0x00,0x13}); m.mem[0x1300]=0x5a;
      m.expect({0x200,0x201,0x202,0x203,0x204,0x1200,0x1300});
      require(m.cpu.p_debug__a.get<unsigned>()==0x5a);
      m.expect({0x205,0x206,0x207,0x1301}); auto b=m.tick();
      require(b.write && b.addr==0x1301 && b.data==0x5a); }
    { Machine m; m.code({0x6c,0xff,0x12}); m.mem[0x12ff]=0x45; m.mem[0x1200]=0x23; m.mem[0x1300]=0x99;
      m.expect({0x200,0x201,0x202,0x12ff,0x1200}); require(m.cpu.p_debug__pc.get<unsigned>()==0x2345); }
    { Machine m; m.code({0x06,0x80}); m.mem[0x80]=0x81;
      m.expect({0x200,0x201,0x80}); auto old=m.tick(), val=m.tick();
      require(old.write && old.addr==0x80 && old.data==0x81);
      require(val.write && val.addr==0x80 && val.data==2); }
    { Machine m; m.code({0xa2,2,0xb5,0xff}); m.mem[1]=0x78;
      m.expect({0x200,0x201,0x202,0x203,0xff,1}); require(m.cpu.p_debug__a.get<unsigned>()==0x78); }
    { Machine m; m.code({0x4c,0xfd,0x02}); m.mem[0x2fd]=0xd0; m.mem[0x2fe]=2;
      m.expect({0x200,0x201,0x202,0x2fd,0x2fe,0x2ff,0x201}); require(m.cpu.p_debug__pc.get<unsigned>()==0x301); }
    { Machine m; m.code({0x20,0x00,0x03}); m.mem[0x300]=0x60;
      m.expect({0x200,0x201,0x1fd,0x1fd,0x1fc,0x202,0x300,0x301,0x1fb,0x1fc,0x1fd,0x202});
      require(m.cpu.p_debug__pc.get<unsigned>()==0x203 && m.mem[0x1fd]==2 && m.mem[0x1fc]==2); }
    { Machine m; m.code({0xa9,0x5a,0x85,0x10}); m.cpu.p_ready.set<bool>(false);
      m.expect({0x200,0x200,0x200}); require(m.cpu.p_debug__pc.get<unsigned>()==0x200);
      m.cpu.p_ready.set<bool>(true); m.expect({0x200,0x201,0x202,0x203});
      m.cpu.p_ready.set<bool>(false); auto b=m.tick(); require(b.write && m.mem[0x10]==0x5a);
      require(m.cpu.p_sync.get<bool>()); }
    { Machine m; m.code({0x58,0xea}); m.mem[0xfffe]=0; m.mem[0xffff]=4; m.mem[0x400]=0x40;
      m.expect({0x200,0x201}); m.cpu.p_irq.set<bool>(true);
      m.expect({0x201,0x201,0x1fd,0x1fc,0x1fb,0xfffe,0xffff});
      require(m.cpu.p_debug__pc.get<unsigned>()==0x400 && m.mem[0x1fc]==1 && !(m.mem[0x1fb]&0x10));
      m.cpu.p_irq.set<bool>(false); m.expect({0x400,0x401,0x1fa,0x1fb,0x1fc,0x1fd});
      require(m.cpu.p_debug__pc.get<unsigned>()==0x201); }
    { Machine m; m.mem[0xfffa]=0; m.mem[0xfffb]=5; m.cpu.p_ce.set<bool>(false);
      m.cpu.p_nmi.set<bool>(true); m.tick(); m.cpu.p_nmi.set<bool>(false); m.tick();
      m.cpu.p_ce.set<bool>(true); m.expect({0x200,0x200,0x1fd,0x1fc,0x1fb,0xfffa,0xfffb});
      require(m.cpu.p_debug__pc.get<unsigned>()==0x500); }
    std::cout<<"PASS: indexed/dummy cycles, page and zero-page wrap, RMW writes, JSR/RTS, RDY, IRQ/RTI, latched NMI\n";
    return 0;
} catch(const std::exception &e) { std::cerr<<"FAIL: "<<e.what()<<"\n"; return 1; } }
