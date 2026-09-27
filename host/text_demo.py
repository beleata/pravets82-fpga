"""Our ROM-free 6502 keyboard/text demo; all echo is performed by the FPGA CPU."""
from text_screen import row_offset

class Assembler:
    def __init__(self, origin=0x1000):
        self.origin, self.data, self.labels, self.fixups = origin, bytearray(), {}, []
    def label(self, name):
        self.labels[name] = self.origin + len(self.data)
    def emit(self, *values):
        self.data.extend(values)
    def absolute(self, opcode, target):
        self.emit(opcode)
        if isinstance(target, str):
            self.fixups.append((len(self.data), target, False)); self.emit(0, 0)
        else:
            self.emit(target & 255, target >> 8)
    def branch(self, opcode, target):
        self.emit(opcode); self.fixups.append((len(self.data), target, True)); self.emit(0)
    def finish(self):
        for offset, target, relative in self.fixups:
            address = self.labels[target]
            if relative:
                delta = address - (self.origin + offset + 1)
                if not -128 <= delta <= 127:
                    raise ValueError('branch too far: ' + target)
                self.data[offset] = delta & 255
            else:
                self.data[offset:offset+2] = address.to_bytes(2, 'little')
        return bytes(self.data)

def program():
    a = Assembler()
    a.label('start'); a.emit(0x78, 0xd8, 0xa2, 0, 0xa9, 0xa0)  # SEI CLD LDX0 LDAspace
    a.label('clear')
    for address in range(0x400, 0xc00, 0x100):
        a.absolute(0x9d, address)  # STA abs,X
    a.emit(0xe8); a.branch(0xd0, 'clear')
    for address in (0xc051, 0xc054, 0xc052):
        a.absolute(0xad, address)
    a.emit(0xa2, 0); a.label('headings')
    for row in range(3):
        a.absolute(0xbd, 'heading' + str(row)); a.absolute(0x9d, 0x400 + row_offset(row))
    a.emit(0xe8, 0xe0, 40); a.branch(0xd0, 'headings')
    a.emit(0xa9, 5, 0x85, 0x13, 0xa9, 0, 0x85, 0x14); a.absolute(0x4c, 'pointer')
    a.label('poll'); a.absolute(0xad, 0xc000); a.branch(0x10, 'poll')
    a.emit(0x85, 0x12); a.absolute(0x2c, 0xc010); a.emit(0xa5, 0x12, 0x29, 0x7f)
    a.emit(0xc9, 13); a.branch(0xf0, 'newline')
    a.emit(0xc9, 8); a.branch(0xf0, 'backspace')
    a.emit(0xc9, 27); a.branch(0xd0, 'print'); a.absolute(0x4c, 'start')
    a.label('print'); a.emit(0x09, 0x80, 0xa4, 0x14, 0x91, 0x10, 0xe6, 0x14,
                           0xa5, 0x14, 0xc9, 40); a.branch(0x90, 'poll')
    a.label('newline'); a.emit(0xa9, 0, 0x85, 0x14, 0xe6, 0x13, 0xa5, 0x13, 0xc9, 24)
    a.branch(0x90, 'pointer'); a.emit(0xa9, 5, 0x85, 0x13)
    a.label('pointer'); a.emit(0xa6, 0x13); a.absolute(0xbd, 'rowlow'); a.emit(0x85, 0x10)
    a.absolute(0xbd, 'rowhigh'); a.emit(0x85, 0x11); a.absolute(0x4c, 'poll')
    a.label('backspace'); a.emit(0xa5, 0x14); a.branch(0xf0, 'poll')
    a.emit(0xc6, 0x14, 0xa4, 0x14, 0xa9, 0xa0, 0x91, 0x10); a.absolute(0x4c, 'poll')
    for row, text in enumerate(('PRAVETS 82 / APPLE II - FPGA 6502',
                                'LIVE RAM DISPLAY - TYPE BELOW',
                                'ENTER: NEW LINE   ESC: CLEAR')):
        a.label('heading' + str(row)); a.emit(*(ord(c) | 128 for c in text.ljust(40)))
    a.label('rowlow'); a.emit(*((0x400 + row_offset(row)) & 255 for row in range(24)))
    a.label('rowhigh'); a.emit(*((0x400 + row_offset(row)) >> 8 for row in range(24)))
    return a.finish()

def load(machine):
    machine.video()  # Require new endpoint before touching RAM.
    machine.control(2)
    machine.write(0xf1c0,bytes(8))  # invalidate a previous game service signature
    data = program()
    machine.write(0x1000, data)
    if machine.read(0x1000, len(data)) != data:
        raise RuntimeError('Text program readback mismatch')
    machine.write(0xfffc, b'\x00\x10')
    machine.control(3)

if __name__ == '__main__':
    from pathlib import Path
    target = Path(__file__).resolve().parents[1] / 'build/text-demo.bin'
    target.parent.mkdir(exist_ok=True)
    target.write_bytes(program())
    print(f'{len(program())} bytes: {target}')
