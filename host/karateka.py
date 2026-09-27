"""Selected single-player Karateka ProDOS release, served directly over SPI.

Only its GET_PREFIX/OPEN/READ/CLOSE calls are provided. The FPGA 6502 runs
the original decompression, animation and game logic. No Disk II or ProDOS
kernel is involved, and no CPU emulator is imported by this runtime.
"""
import hashlib
from pathlib import Path
from text_demo import Assembler

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT/'build/karateka'
DISK_SHA = '12c7990fb427f464d8ba9aa366514f505127d63d2351949318d201dae72e3efe'
ROM_SHA = '6cb7e317e0036e4e006bc1c32fa79858d6d5c030a31a52d76a301c71020a10dd'
MAILBOX = 0xf180
FILE_STATE = 0xf1a0
SIGNATURE = 0xf1c0
MAGIC = b'A2KARA01'

def assets():
    disk=(ASSETS/'prodos.po').read_bytes(); rom=(ASSETS/'appleiigo.rom').read_bytes()
    if hashlib.sha256(disk).hexdigest()!=DISK_SHA or hashlib.sha256(rom).hexdigest()!=ROM_SHA:
        raise ValueError('Unexpected Karateka/ROM image; this adapter requires the pinned release')
    files={}
    for i in range(3,10):
        entry=disk[1028+39*i:1028+39*(i+1)]
        name=entry[1:1+(entry[0]&15)].decode('ascii')
        if entry[0]>>4!=2 or entry[16]!=6: raise ValueError('Unexpected ProDOS file layout')
        key=int.from_bytes(entry[17:19],'little');size=int.from_bytes(entry[21:24],'little')
        index=disk[key*512:(key+1)*512]
        blocks=[index[j]+256*index[j+256] for j in range((size+511)//512)]
        files[name]=b''.join(disk[b*512:(b+1)*512] for b in blocks)[:size]
    if set(files)!={'KARATEKA','KARATEKA.A',*(f'KARATEKA.{n}' for n in range(1,6))}:
        raise ValueError('Incomplete Karateka files')
    return files,rom

def shim():
    """MLI ABI entry via JMP: consume inline command/pointer after caller JSR.

    Save X/Y and the temporary zero-page pointer. Advance stacked return by
    three bytes. Publish the request last; host clears it after all RAM writes.
    """
    a=Assembler(0xf100); op=a.absolute
    op(0x8e,0xf184);op(0x8c,0xf185) # STX/STY
    a.emit(0xa5,0xfa);op(0x8d,0xf186);a.emit(0xa5,0xfb);op(0x8d,0xf187)
    a.emit(0xba);op(0xbd,0x101);a.emit(0x85,0xfa);op(0xbd,0x102);a.emit(0x85,0xfb)
    a.emit(0xa0,1,0xb1,0xfa);op(0x8d,MAILBOX+1)
    a.emit(0xc8,0xb1,0xfa);op(0x8d,MAILBOX+2)
    a.emit(0xc8,0xb1,0xfa);op(0x8d,MAILBOX+3)
    a.emit(0xa5,0xfa,0x18,0x69,3);op(0x9d,0x101)
    a.emit(0xa5,0xfb,0x69,0);op(0x9d,0x102)
    op(0xad,0xf186);a.emit(0x85,0xfa);op(0xad,0xf187);a.emit(0x85,0xfb)
    a.emit(0xa9,1);op(0x8d,MAILBOX)
    a.label('wait');op(0xad,MAILBOX);a.branch(0xd0,'wait')
    op(0xae,0xf184);op(0xac,0xf185);a.emit(0xa9,0,0x18,0x60)
    code=a.finish()
    assert len(code)<=128
    return code

class Karateka:
    def __init__(self,machine):
        self.machine=machine;self.files,self.rom=assets();self.requests=[]

    def load(self):
        m=self.machine;m.control(2)
        ram=bytearray(49152);code=self.files['KARATEKA']
        ram[0x3ff6:0x3ff6+len(code)]=code
        ram[0xbf00:0xbf03]=b'\x4c\x00\xf1'
        upper=bytearray(self.rom[-4096:])
        # Reset entry, then the game's own original unpacker.
        boot=bytes.fromhex('78 d8 a2 ff 9a a9 00 4c f6 3f')
        upper[:len(boot)]=boot;stub=shim();upper[0x100:0x100+len(stub)]=stub
        upper[0x180:0x200]=bytes(128);upper[0x1c0:0x1c8]=MAGIC
        upper[0xffc:0xffe]=b'\x00\xf0'
        m.write(0,ram);m.write(0xf000,upper)
        if m.read(0,len(ram))!=ram or m.read(0xf000,4096)!=upper:
            raise RuntimeError('Karateka RAM verification failed')
        m.control(3)

    def service(self):
        m=self.machine
        request=m.read_live(MAILBOX,4)
        if request[0]==0:return False
        if request[0]!=1:raise RuntimeError('Invalid Karateka file request')
        if not m.status()['running']:return False # preserve manual pause
        m.control(0)
        # A failure deliberately leaves the CPU paused, never acknowledges
        # incomplete data, and is reported by the application.
        command=request[1];pb=int.from_bytes(request[2:4],'little')
        if not 0x100<=pb<0xbff0:raise RuntimeError('Invalid MLI parameter address')
        params=m.read(pb,8)
        def word(offset):return int.from_bytes(params[offset:offset+2],'little')
        def write(address,data):
            if not 0<=address<=address+len(data)<=0xc000:
                raise RuntimeError('File transfer outside main RAM')
            m.write(address,data)
        detail=''
        if command==0xc7 and params[0]==1: # GET_PREFIX
            write(word(1),b'\x01/')
        elif command==0xc8 and params[0]==3: # OPEN
            address=word(1)
            if address>=0xc000:raise RuntimeError('Invalid pathname address')
            length=m.read(address,1)[0]
            if not 1<=length<=64 or address+1+length>0xc000:raise RuntimeError('Invalid pathname')
            name=bytes(c&127 for c in m.read(address+1,length)).decode('ascii').split('/')[-1]
            if name not in self.files:raise RuntimeError('Unsupported Karateka file: '+name)
            encoded=name.encode();state=bytes([len(encoded)])+encoded+bytes(19-len(encoded))
            m.write(FILE_STATE,state);write(pb+5,b'\x01');detail=name
        elif command==0xca and params[0]==4 and params[1]==1: # READ
            state=m.read(FILE_STATE,20);name=state[1:1+state[0]].decode('ascii')
            if name not in self.files:raise RuntimeError('READ without OPEN')
            position=int.from_bytes(state[16:20],'little')
            data=self.files[name][position:position+word(4)]
            if not data:raise RuntimeError('Unexpected end of Karateka file')
            write(word(2),data);write(pb+6,len(data).to_bytes(2,'little'))
            m.write(FILE_STATE+16,(position+len(data)).to_bytes(4,'little'))
            detail=f'{name}: {len(data)} bytes -> ${word(2):04X}'
        elif command==0xcc and params[0]==1: # CLOSE, one supported file
            m.write(FILE_STATE,bytes(20))
        else:raise RuntimeError(f'Unsupported Karateka MLI ${command:02X}')
        self.requests.append(dict(command=command,detail=detail))
        m.write(MAILBOX,b'\x00');m.control(1)
        return True
