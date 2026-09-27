"""CRC-framed USB/SPI bridge, run from RAM after pio_spi.py."""
import sys
import struct
import binascii
import micropython
import time

MAGIC = b'A2B!'
MAX_TRANSFER = 16384

def memory_read(transfer, address, count):
    tx = bytearray(count + 4)
    tx[0] = 0x40; tx[1] = address >> 8; tx[2] = address & 255
    return memoryview(transfer(tx))[4:]

def snapshot(transfer, fence):
    """Freeze on Pico, copy video, resume before any USB response is written.

    Optional RAM byte equals 1 only between complete draws in an opted-in demo.
    Read it again AFTER pausing to close the check/pause race. A busy fence
    drops this capture; it never falls back to publishing a half-drawn frame.
    """
    initial = transfer(b'\x43' + bytes(10))[1:]
    running = bool(initial[1] & 1)
    gated = fence != 65535 and running and not initial[1] & 2
    deadline = time.ticks_us()
    paused_us = 0
    while True:
        if gated and time.ticks_diff(time.ticks_us(), deadline) >= 150000:
            return b'\x01\x02' + struct.pack('<I', paused_us) + bytes(14)
        if gated and memory_read(transfer, fence, 1)[0] != 1:
            time.sleep_ms(1)
            continue
        began = time.ticks_us()
        try:
            if running:
                transfer(b'\x42\x00')
            # A fence can become busy between the first read and the pause.
            if gated and memory_read(transfer, fence, 1)[0] != 1:
                continue
            state = bytearray(transfer(b'\x43' + bytes(10))[1:])
            state[1] = (state[1] & ~1) | int(running)
            video = transfer(b'\x45' + bytes(4))[1:]
            hires = not video[1] & 1 and bool(video[1] & 8)
            page2 = bool(video[1] & 4)
            result = bytearray(20 + 1024 + (8192 if hires else 0))
            result[0] = 1; result[1] = int(gated)
            result[6:16] = state; result[16:20] = video
            result[20:1044] = memory_read(transfer, 0x800 if page2 else 0x400, 1024)
            if hires:
                result[1044:] = memory_read(transfer, 0x4000 if page2 else 0x2000, 8192)
        finally:
            # Includes failures during pause/read. Never resume a user's pause.
            if running:
                transfer(b'\x42\x01')
                paused_us += time.ticks_diff(time.ticks_us(), began)
        result[2:6] = struct.pack('<I', paused_us)
        return result

def read_exact(stream, size):
    data = bytearray(size)
    view = memoryview(data)
    offset = 0
    while offset < size:
        count = stream.readinto(view[offset:])
        if not count:
            raise EOFError('USB stream ended inside a frame')
        offset += count
    return data

def write_all(stream, data):
    view = memoryview(data)
    offset = 0
    while offset < len(data):
        count = stream.write(view[offset:])
        if not count:
            raise OSError('USB write failed')
        offset += count

def frame(stream, magic, sequence, data):
    header = magic + struct.pack('<HH', sequence, len(data))
    checksum = binascii.crc32(data, binascii.crc32(header)) & 0xffffffff
    write_all(stream, header)
    write_all(stream, data)
    write_all(stream, struct.pack('<I', checksum))

def serve(source, sink, transfer):
    while True:
        # Bounded resynchronization; normal traffic reads a header in one call.
        head = read_exact(source, 4)
        while head not in (MAGIC, b'A2M!', b'A2S!'):
            head = head[1:] + read_exact(source, 1)
        rest = read_exact(source, 4)
        sequence, size = struct.unpack('<HH', rest)
        if size > MAX_TRANSFER:
            frame(sink, b'A2E!', sequence, b'length')
            continue
        payload = read_exact(source, size)
        expected = struct.unpack('<I', read_exact(source, 4))[0]
        actual = binascii.crc32(payload, binascii.crc32(head + rest)) & 0xffffffff
        if expected != actual:
            frame(sink, b'A2E!', sequence, b'crc')
            continue  # Bad USB data must never cause a SPI write.
        if head == MAGIC and size == 0 and sequence == 65535:
            frame(sink, b'A2R!', sequence, b'')
            return
        if size == 0:
            frame(sink, b'A2E!', sequence, b'empty')
            continue
        if head == b'A2S!':
            if len(payload) != 2:
                frame(sink, b'A2E!', sequence, b'snapshot length'); continue
            fence = struct.unpack('>H', payload)[0]
            if fence != 65535 and fence >= 0xc000:
                frame(sink, b'A2E!', sequence, b'fence range'); continue
            response = snapshot(transfer, fence)
            frame(sink, b'A2R!', sequence, response)
        elif head == b'A2M!':
            if len(payload) != 4:
                frame(sink, b'A2E!', sequence, b'read length'); continue
            address, count = struct.unpack('>HH', payload)
            if not 1 <= count <= MAX_TRANSFER-4 or address + count > 65536:
                frame(sink, b'A2E!', sequence, b'read range'); continue
            tx = bytearray(count+4)
            tx[0] = 0x40; tx[1] = address >> 8; tx[2] = address & 255
            response = transfer(tx)
            frame(sink, b'A2R!', sequence, memoryview(response)[4:])
        else:
            frame(sink, b'A2R!', sequence, transfer(payload))

if __name__ == '__main__':
    bus = A2PioSPI(A2_PIO_HZ)
    micropython.kbd_intr(-1)  # $03 is valid CPU data, not a Ctrl-C interrupt.
    try:
        serve(sys.stdin.buffer, sys.stdout.buffer, bus.transfer)
    finally:
        bus.close()
        micropython.kbd_intr(3)
