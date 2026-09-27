"""Capture safety: CPU restoration, drawing fence races, and complete USB frames."""
import io
import struct
import types
import pytest
from test_binary_bridge import bridge, decode_frames
from transport import encode, Link
from machine import Machine

class Clock:
    def __init__(self): self.now = 0
    def ticks_us(self): self.now += 100; return self.now
    def ticks_diff(self, a, b): return a-b
    def sleep_ms(self, n): self.now += n*1000

class FPGA:
    def __init__(self, running=True, mode=10):
        self.running = running; self.mode = mode; self.calls = []
        self.fence = 1; self.race = False; self.fail = False
    def __call__(self, tx):
        tx = bytes(tx); self.calls.append(tx)
        if tx[0] == 0x43:
            return bytes([0,2,int(self.running),0x12,0x34,1,2,3,0xff,0x24,0])
        if tx[0] == 0x45:
            assert not self.running
            return bytes([0,2,self.mode,0,0])
        if tx[0] == 0x42:
            self.running = bool(tx[1])
            if self.race and not self.running: self.fence = 0; self.race = False
            elif self.running: self.fence = 1
            return bytes(2)
        assert tx[0] == 0x40
        address = int.from_bytes(tx[1:3], 'big'); count = len(tx)-4
        if address == 0x300: return bytes(4)+bytes([self.fence])
        assert not self.running, 'Every video read must be under pause'
        if self.fail: raise OSError('SPI read failed')
        return bytes(4) + bytes([address >> 8])*count

@pytest.mark.parametrize('mode,size,text,graphics', [(10,9236,4,32),(14,9236,8,64),(1,1044,4,None),(6,1044,8,None)])
def test_capture_restores_before_usb_and_captures_selected_page(bridge,mode,size,text,graphics):
    bridge.time = Clock(); fpga = FPGA(mode=mode)
    class Sink(io.BytesIO):
        def write(self, data):
            assert fpga.running, 'USB must never hold the CPU paused'
            return super().write(data)
    sink = Sink()
    bridge.serve(io.BytesIO(encode(b'\x03\x00',1,b'A2S!')+encode(b'',65535)),sink,fpga)
    data = decode_frames(sink.getvalue())[0][2]
    assert len(data) == size and data[1] == 1 and data[7] & 1
    assert data[20:1044] == bytes([text])*1024
    assert data[1044:] == (bytes([graphics])*8192 if graphics else b'')

def test_pause_race_retries_instead_of_capturing_partial_draw(bridge):
    bridge.time = Clock(); fpga = FPGA(); fpga.race = True
    data = bridge.snapshot(fpga,0x300)
    assert data[1] == 1 and fpga.running
    assert fpga.calls.count(b'\x42\x00') == 2

def test_busy_fence_drops_frame_and_user_pause_never_resumes(bridge):
    bridge.time = Clock(); fpga = FPGA(); fpga.fence = 0
    assert bridge.snapshot(fpga,0x300)[1] == 2
    assert fpga.running and not any(c[0] == 0x42 for c in fpga.calls)
    fpga = FPGA(running=False); fpga.fence = 0
    data = bridge.snapshot(fpga,0x300)
    assert not fpga.running and data[1] == 0 and data[7] == 0
    assert not any(c[0] == 0x42 for c in fpga.calls)

def test_read_exception_resumes_cpu(bridge):
    bridge.time = Clock(); fpga = FPGA(); fpga.fail = True
    with pytest.raises(OSError, match='SPI read failed'): bridge.snapshot(fpga,65535)
    assert fpga.running and fpga.calls[-1] == b'\x42\x01'

def test_host_parses_variable_frame_and_skip(bridge):
    bridge.time = Clock(); fpga = FPGA()
    data = bridge.snapshot(fpga,0x300)
    link = object.__new__(Link)
    link.request = lambda payload, magic, size: data
    page, video, state, graphics = Machine(link).snapshot(0x300)
    assert len(page) == 1024 and len(graphics) == 8192
    assert video['synced'] and video['pause_us'] > 0 and state['running']
    data = b'\x01\x02'+bytes(18)
    assert Machine(link).snapshot(0x300) is None
