import binascii
import importlib.util
import io
from pathlib import Path
import struct
import sys
import types
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'host'))
from transport import encode, Link

@pytest.fixture
def bridge(monkeypatch):
    monkeypatch.setitem(sys.modules,'micropython',types.SimpleNamespace(kbd_intr=lambda n:None))
    spec=importlib.util.spec_from_file_location('test_binary_pico',Path(__file__).resolve().parents[1]/'pico/binary_bridge.py')
    module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module

class Fragmented(io.BytesIO):
    def readinto(self, view): return super().readinto(view[:7])
    def write(self,data): return super().write(data[:11])

def decode_frames(data):
    frames=[]
    while data:
        header=data[:8]; magic,seq,size=struct.unpack('<4sHH',header)
        payload=data[8:8+size]; checksum=struct.unpack('<I',data[8+size:12+size])[0]
        assert checksum==binascii.crc32(payload,binascii.crc32(header))&0xffffffff
        frames.append((magic,seq,payload)); data=data[12+size:]
    return frames

def test_fragmented_full_byte_range_and_maximum_frame(bridge):
    data=bytes(range(256))*64
    source=Fragmented(encode(data,1)+encode(b'',65535)); sink=Fragmented(); calls=[]
    def spi(payload): calls.append(bytes(payload)); return payload[::-1]
    bridge.serve(source,sink,spi)
    assert calls==[data]
    assert decode_frames(sink.getvalue())==[(b'A2R!',1,data[::-1]),(b'A2R!',65535,b'')]

def test_bad_crc_and_oversize_never_touch_spi_and_resynchronize(bridge):
    bad=bytearray(encode(b'\x41\x20\x00\xff',1)); bad[-1]^=1
    oversized=b'A2B!'+struct.pack('<HH',2,65535)
    source=io.BytesIO(b'noise'+bad+oversized+encode(b'\x10',3)+encode(b'',65535))
    sink=io.BytesIO(); calls=[]
    def spi(data): calls.append(bytes(data)); return data
    bridge.serve(source,sink,spi)
    assert calls==[b'\x10']
    assert [f[0] for f in decode_frames(sink.getvalue())]==[b'A2E!',b'A2E!',b'A2R!',b'A2R!']

def test_compact_read_preserves_address_and_does_not_write(bridge):
    calls=[]
    def spi(data): calls.append(bytes(data)); return bytes(4)+bytes(range(16))
    source=io.BytesIO(encode(struct.pack('>HH',0x2000,16),4,b'A2M!')+encode(b'',65535)); sink=io.BytesIO()
    bridge.serve(source,sink,spi)
    assert calls==[b'\x40\x20\x00\x00'+bytes(16)]
    assert decode_frames(sink.getvalue())[0]==(b'A2R!',4,bytes(range(16)))

def test_host_crc_failure_is_not_retried(monkeypatch):
    import transport
    reply=bytearray(encode(b'\xa5',1,b'A2R!')); reply[-1]^=1
    class Serial:
        def __init__(self,*args,**kwargs): self.rx=io.BytesIO(reply); self.writes=[]
        def read(self,n): return self.rx.read(min(n,2))
        def write(self,data): self.writes.append(data); return len(data)
    monkeypatch.setattr(transport.serial,'Serial',Serial)
    link=Link('fake')
    with pytest.raises(RuntimeError,match='CRC'): link.exchange(b'\x10')
    with pytest.raises(RuntimeError,match='lost framing'): link.exchange(b'\x10')
    assert len(link.port.writes)==1
