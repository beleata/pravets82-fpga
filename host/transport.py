"""Binary USB frames with sequence, bounded length and CRC; generic SPI payloads."""
import binascii
import struct
import time
import serial

MAX_TRANSFER = 16384

def encode(payload, sequence, magic=b'A2B!'):
    header = magic + struct.pack('<HH', sequence, len(payload))
    crc = binascii.crc32(payload, binascii.crc32(header)) & 0xffffffff
    return header + payload + struct.pack('<I', crc)

class Link:
    def __init__(self, port):
        self.port = serial.Serial(port, 115200, timeout=0.05, write_timeout=3)
        self.sequence = 0
        self.failed = False

    def read_exact(self, size, deadline):
        data = bytearray()
        while len(data) < size:
            part = self.port.read(size-len(data))
            data.extend(part)
            if time.monotonic() > deadline:
                raise TimeoutError('Binary Pico bridge did not answer; start it with --transport binary')
        return bytes(data)

    def exchange(self, payload):
        return self.request(payload, b'A2B!', len(payload))

    def read_memory(self, address, count):
        if not 1 <= count <= MAX_TRANSFER-4 or not 0 <= address <= address + count <= 65536:
            raise ValueError('Invalid memory read range')
        return self.request(struct.pack('>HH', address, count), b'A2M!', count)

    def snapshot(self, fence=None):
        if fence is not None and not 0 <= fence < 0xc000:
            raise ValueError('Frame fence must be in main RAM')
        data = self.request(struct.pack('>H', 65535 if fence is None else fence), b'A2S!', None)
        if len(data) < 20 or data[0] != 1 or data[1] & ~3:
            raise RuntimeError('Invalid snapshot header')
        if data[1] & 2:
            if len(data) != 20: raise RuntimeError('Invalid skipped snapshot')
            return None
        mode = data[17]
        size = 9236 if not mode & 1 and mode & 8 else 1044
        if len(data) != size or data[6] != 2 or data[16] != 2:
            raise RuntimeError('Invalid snapshot video data')
        return data

    def request(self, payload, magic, expected_size):
        if self.failed:
            raise RuntimeError('Transport lost framing; reconnect/restart bridge before retrying')
        if not 1 <= len(payload) <= MAX_TRANSFER:
            raise ValueError('SPI payload must be 1..16384 bytes')
        self.sequence = self.sequence % 65534 + 1
        try:
            outgoing = encode(payload, self.sequence, magic)
            if self.port.write(outgoing) != len(outgoing):
                raise OSError('Short USB request write')
            deadline = time.monotonic() + 3
            header = self.read_exact(8, deadline)
            magic, seq, size = struct.unpack('<4sHH', header)
            if magic not in (b'A2R!', b'A2E!') or seq != self.sequence or size > MAX_TRANSFER:
                raise RuntimeError('Unexpected USB response header')
            data = self.read_exact(size, deadline)
            expected = struct.unpack('<I', self.read_exact(4, deadline))[0]
            actual = binascii.crc32(data, binascii.crc32(header)) & 0xffffffff
            if actual != expected:
                raise RuntimeError('USB response CRC mismatch')
            if magic == b'A2E!':
                raise RuntimeError('Pico rejected request: ' + data.decode('ascii', 'replace'))
            if expected_size is not None and len(data) != expected_size:
                raise RuntimeError('SPI response length mismatch')
            return data
        except Exception:
            # Never silently resend a possibly completed memory/keyboard write.
            self.failed = True
            raise
