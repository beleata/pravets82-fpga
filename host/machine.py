"""Load and inspect the FPGA CPU development machine through Pico #2."""
import argparse
import json
from pathlib import Path
import random
import time
from diagnose import Link

class Machine:
    def __init__(self, link):
        self.link = link

    def control(self, value):
        if value not in range(4):
            raise ValueError('control must be 0..3')
        self.link.exchange(bytes([0x42, value]))

    def status(self):
        data = self.link.exchange(b'\x43' + bytes(10))[1:]
        if data[0] not in (1, 2):
            raise RuntimeError('CPU endpoint version mismatch: ' + data.hex())
        return dict(version=data[0], running=bool(data[1] & 1), halted=bool(data[1] & 2),
                    pc=int.from_bytes(data[2:4], 'big'), a=data[4], x=data[5],
                    y=data[6], sp=data[7], p=data[8])

    def require_paused(self):
        if self.status()['running']:
            raise RuntimeError('Memory access requires a paused CPU')

    def write(self, address, data):
        self.require_paused()
        if not 0 <= address <= address + len(data) <= 65536:
            raise ValueError('memory range outside 16-bit address space')
        for offset in range(0, len(data), 4096):
            self.link.exchange(b'\x41' + (address + offset).to_bytes(2, 'big') + data[offset:offset+4096])

    def read(self, address, count):
        self.require_paused()
        return self.read_live(address, count)

    def read_live(self, address, count):
        """Requires endpoint v2, checked once by the caller before live use."""
        if not 0 <= address <= address + count <= 65536:
            raise ValueError('memory range outside 16-bit address space')
        result = bytearray()
        if hasattr(self.link, 'read_memory'):
            for offset in range(0, count, 16380):
                result.extend(self.link.read_memory(address + offset, min(16380, count-offset)))
            return bytes(result)
        for offset in range(0, count, 4096):
            size = min(4096, count - offset)
            result.extend(self.link.exchange(b'\x40' + (address + offset).to_bytes(2, 'big')
                                             + bytes(size + 1))[4:])
        return bytes(result)

    def video(self):
        data = self.link.exchange(b'\x45' + bytes(4))[1:]
        if data[0] != 2:
            raise RuntimeError('This FPGA image has no live video endpoint; load the new SRAM build')
        return dict(mode=data[1], text=bool(data[1] & 1), mixed=bool(data[1] & 2),
                    page=2 if data[1] & 4 else 1, hires=bool(data[1] & 8),
                    key_pending=bool(data[2] & 1))

    def snapshot(self, fence=None):
        data = self.link.snapshot(fence)
        if data is None:
            return None
        state = data[6:16]; mode = data[17]
        video = dict(mode=mode, text=bool(mode & 1), mixed=bool(mode & 2),
                     page=2 if mode & 4 else 1, hires=bool(mode & 8),
                     key_pending=bool(data[18] & 1), synced=bool(data[1] & 1),
                     pause_us=int.from_bytes(data[2:6], 'little'))
        status = dict(version=state[0], running=bool(state[1] & 1), halted=bool(state[1] & 2),
                      pc=int.from_bytes(state[2:4], 'big'), a=state[4], x=state[5],
                      y=state[6], sp=state[7], p=state[8])
        return data[20:1044], video, status, data[1044:] or None

    def key(self, code):
        if not 0 <= code <= 127:
            raise ValueError('Apple II keyboard code must be seven bits')
        return self.link.exchange(bytes([0x44, code, 0]))[2] == 1

    def memory_test(self):
        self.control(2)
        rng = random.Random(6502)
        regions = [(0, 49152), (0xf000, 4096)]
        # Full-range random patterns expose addressing aliases and BRAM banking.
        for address, size in regions:
            pattern = bytes(rng.randrange(256) for _ in range(size))
            self.write(address, pattern)
            got = self.read(address, size)
            if got != pattern:
                at = next(i for i, pair in enumerate(zip(got, pattern)) if pair[0] != pair[1])
                raise RuntimeError(f'RAM mismatch at ${address+at:04x}: {got[at]:02x} != {pattern[at]:02x}')
        if self.read(0xc100, 256) != b'\xff' * 256:
            raise RuntimeError('Unmapped region did not read $FF')
        print('PASS: 52 KiB FPGA memory write/read, including all 48 KiB main RAM', flush=True)

    def smoke(self):
        # Fill text-page-shaped memory, perform decimal ADC and a subroutine.
        # $0600: SEI; CLD; LDX #0; TXA; STA $0400,X; INX; BNE loop;
        # SED; CLC; LDA #$45; ADC #$55; STA $0300; PHP; PLA; STA $0301;
        # CLD; JSR $0623; STA $0302; JMP $0620; sub: LDA #$A5; RTS.
        program = bytes.fromhex('78 d8 a2 00 8a 9d 00 04 e8 d0 f9 f8 18 a9 45 69 55 '
                                '8d 00 03 08 68 8d 01 03 d8 20 23 06 8d 02 03 4c 20 06 a9 a5 60')
        self.control(2)
        self.write(0x600, program)
        self.write(0xfffc, b'\x00\x06')
        self.control(3)
        time.sleep(0.05)
        self.control(0)
        status = self.status()
        if status['halted'] or status['pc'] not in (0x620, 0x621, 0x622):
            raise RuntimeError('Smoke program did not reach its final loop: ' + repr(status))
        if self.read(0x400, 256) != bytes(range(256)):
            raise RuntimeError('CPU page fill failed')
        result = self.read(0x300, 3)
        if result[0] != 0 or result[1] & 0xc3 != 0xc1 or result[2] != 0xa5:
            raise RuntimeError('CPU arithmetic/stack/subroutine failed: ' + result.hex())
        print('PASS: FPGA CPU executed RAM loop, NMOS decimal ADC, stack, JSR/RTS', flush=True)
        return status

    def klaus(self, image):
        data = bytearray(image.read_bytes())
        if len(data) != 65536:
            raise ValueError('Klaus image must be exactly 64 KiB')
        data[0xfffc:0xfffe] = b'\x00\x04'
        self.control(2)
        for start, end in ((0, 0xc000), (0xf000, 0x10000)):
            self.write(start, data[start:end])
            if self.read(start, end-start) != data[start:end]:
                raise RuntimeError('Test image readback mismatch')
        print('Independent test image loaded and verified; running at 1 MHz...', flush=True)
        began = time.monotonic()
        self.control(3)
        deadline = began + 125
        while time.monotonic() < deadline:
            time.sleep(1)
            status = self.status()
            if status['halted']:
                raise RuntimeError('CPU halted: ' + repr(status))
            # PC may point at either operand of the JMP-to-self success loop.
            if 0x3469 <= status['pc'] <= 0x346b:
                self.control(0)
                case = self.read(0x200, 1)[0]
                if case != 0xf0:
                    raise RuntimeError(f'Unexpected success test marker ${case:02x}')
                seconds = time.monotonic() - began
                print(f'PASS: Klaus test on physical FPGA, PC=$3469, marker=$F0, {seconds:.1f}s', flush=True)
                return dict(seconds=seconds, status=self.status(), marker=case)
        self.control(0)
        raise RuntimeError('Klaus test timeout: ' + repr(self.status()) + ' case=' + self.read(0x200, 1).hex())

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', default='COM7')
    parser.add_argument('--memory-test', action='store_true')
    parser.add_argument('--smoke', action='store_true')
    parser.add_argument('--klaus', type=Path)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    link = Link(args.port)
    machine = Machine(link)
    report = {}
    try:
        if args.memory_test:
            machine.memory_test(); report['memory_bytes_tested'] = 53248
        if args.smoke:
            report['smoke'] = machine.smoke()
        if args.klaus:
            report['klaus'] = machine.klaus(args.klaus)
        report['status'] = machine.status()
        print(json.dumps(report, indent=2))
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(report, indent=2) + '\n')
    finally:
        link.port.close()

if __name__ == '__main__':
    main()
