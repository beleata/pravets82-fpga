import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'host'))
from karateka import Karateka, shim, FILE_STATE, MAILBOX

class Machine:
    def __init__(self): self.memory=bytearray(65536);self.running=True
    def read_live(self,a,n):return bytes(self.memory[a:a+n])
    read=read_live
    def write(self,a,data):
        assert not self.running
        self.memory[a:a+len(data)]=data
    def status(self):return dict(running=self.running)
    def control(self,value):self.running=bool(value&1)

def service(m):
    k=object.__new__(Karateka);k.machine=m;k.files={'KARATEKA.1':bytes(range(256))*3};k.requests=[]
    return k

def request(m,cmd,params):
    m.memory[MAILBOX:MAILBOX+4]=bytes([1,cmd,0,2]);m.memory[0x200:0x200+len(params)]=params

def test_open_partial_read_close_and_reconnect():
    m=Machine();k=service(m);m.memory[0x500:0x50b]=b'\x0aKARATEKA.\xb1'
    request(m,0xc8,b'\x03\x00\x05\x00\x20\x00');assert k.service()
    assert m.running and m.memory[0x205]==1 and m.memory[MAILBOX]==0
    request(m,0xca,b'\x04\x01\x00\x40\x00\x01\x00\x00');k.service()
    assert m.memory[0x4000:0x4100]==bytes(range(256))
    # New host service reconstructs file position from FPGA RAM.
    k=service(m);request(m,0xca,b'\x04\x01\x00\x41\xff\xff\x00\x00');k.service()
    assert m.memory[0x206:0x208]==b'\x00\x02'
    assert m.memory[0x4100:0x4300]==bytes(range(256))*2
    request(m,0xcc,b'\x01\x01');k.service()
    assert m.memory[FILE_STATE:FILE_STATE+20]==bytes(20)

def test_user_pause_and_invalid_transfer_fail_closed():
    m=Machine();k=service(m);request(m,0xc7,b'\x01\x00\x03');m.running=False
    assert not k.service() and not m.running and m.memory[MAILBOX]==1
    m.running=True;request(m,0xc7,b'\x01\xff\xff')
    with pytest.raises(RuntimeError,match='outside'):k.service()
    assert not m.running and m.memory[MAILBOX]==1

def test_shim_fits_reserved_space():
    assert len(shim())<=128
