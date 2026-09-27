"""Analysis only: trace the selected ProDOS game's file requests with py65.

This is not the FPGA runtime. py65 lives only in build/analysisdeps.
"""
from pathlib import Path
import sys
from collections import Counter
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'build/analysisdeps'))
from py65.devices.mpu6502 import MPU

class Bus(list):
    def __init__(self):
        super().__init__([0]*65536); self.io=Counter(); self.key=0; self.mode=1
    def __getitem__(self,a):
        if isinstance(a,int) and 0xc000<=a<0xd000:
            self.io[a]+=1
            if a==0xc000:return self.key
            if 0xc010<=a<0xc020:self.key &= 127;return self.key
            if 0xc050<=a<=0xc057:
                bit=1<<((a-0xc050)//2)
                self.mode=(self.mode|bit) if a&1 else (self.mode&~bit)
            if 0xc064<=a<=0xc067:return 0
            return 0
        return super().__getitem__(a)
    def __setitem__(self,a,v):
        if isinstance(a,int) and 0xc000<=a<0xd000:
            self.__getitem__(a); return
        super().__setitem__(a,v)

def main():
    p=ROOT/'build/karateka';bus=Bus();cpu=MPU(memory=bus);files={};requests=[]
    code=(p/'KARATEKA').read_bytes();bus[0x3ff6:0x3ff6+len(code)]=code
    bus[0xd000:]=(p/'appleiigo.rom').read_bytes();cpu.pc=0x3ff6
    rom=Counter();frames=0
    def word(a):return bus[a]+256*bus[a+1]
    def putword(a,v):bus[a]=v&255;bus[a+1]=v>>8
    for i in range(int(sys.argv[1]) if len(sys.argv)>1 else 5000000):
        if cpu.pc==0xbf00:
            ret=word(0x100+((cpu.sp+1)&255));cmd=bus[ret+1];pb=word(ret+2)
            requests.append((hex(cmd),hex(pb)))
            if cmd==0xc7:
                address=word(pb+1);bus[address:address+2]=[1,47]
            elif cmd==0xc8:
                address=word(pb+1);name=bytes(c&127 for c in bus[address+1:address+1+bus[address]]).decode().split('/')[-1]
                files[1]=[(p/name).read_bytes(),0];bus[pb+5]=1
                print('OPEN',name,'cycle',cpu.processorCycles,flush=True)
            elif cmd==0xca:
                data,pos=files[bus[pb+1]];address=word(pb+2);count=word(pb+4)
                data=data[pos:pos+count];bus[address:address+len(data)]=data
                putword(pb+6,len(data));files[bus[pb+1]][1]+=len(data)
                print('READ',hex(address),len(data),flush=True)
            elif cmd==0xcc:files.clear()
            else:raise RuntimeError(('MLI',hex(cmd),hex(pb)))
            cpu.sp=(cpu.sp+2)&255;cpu.pc=ret+4;cpu.a=0;cpu.p=(cpu.p&~0x81)|2
            continue
        if cpu.pc>=0xd000:rom[cpu.pc]+=1
        if cpu.pc in (0x7619,0x7624):frames+=1
        if cpu.disassemble[bus[cpu.pc]][0]=='???':raise RuntimeError(('illegal',hex(cpu.pc),hex(bus[cpu.pc])))
        cpu.step()
    print('CPU',hex(cpu.pc),'cycles',cpu.processorCycles,'frames',frames,'mode',bus.mode)
    print('IO',[(hex(a),n) for a,n in bus.io.items()]);print('ROM',[(hex(a),n) for a,n in rom.items()])
    (p/'prodos-probe.bin').write_bytes(bytes(bus))

if __name__=='__main__':main()

