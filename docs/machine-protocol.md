# CPU/display endpoint, version 2

SPI mode 0, MSB first, active-low CS. Electrical timing and diagnostic opcodes
`00`, `10`, `20`, `30` remain as in `protocol.md`. These commands are new and
independent of the abandoned pre-A2 design. USB currently uses the binary
bridge described in `binary-transport.md`; these FPGA SPI commands are unchanged.

| Opcode | MOSI bytes after opcode | MISO response | Purpose |
|---|---|---|---|
| `40` | address high, address low, dummy, N dummies | N bytes at RX offset 4 | Live memory read, CPU keeps running |
| `41` | address high, address low, N data bytes | Ignore | Memory write, paused CPU only |
| `42` | one control byte | Ignore | 0 pause, 1 resume, 2 reset+pause, 3 reset+run |
| `43` | ten dummy bytes | ten status bytes at RX offset 1 | Snapshot CPU registers |
| `44` | seven-bit key code, dummy | RX byte 2: 1 accepted, 0 busy | Keyboard latch, retry if busy |
| `45` | four dummies | RX 1..4: version, video flags, key pending, zero | Observe display and keyboard |

Status: version (`02`), flags (bit0 running, bit1 halted), PC high, PC low,
A, X, Y, SP, P, reserved zero. The complete snapshot is taken at the last bit
of the opcode. PC is the current internal PC and can point at operand bytes
when paused mid-instruction. The status command does not pause execution.

Video flags: bit0 TEXT, bit1 MIXED, bit2 PAGE2, bit3 HIRES. Keyboard pending
is the current strobe (0/1). The video snapshot is captured at opcode completion.
The keyboard acknowledge is returned after the data byte; the latch is not
overwritten if busy. Version 1 did not have these commands or live memory reads.

Block addresses increment and wrap at 16 bits. A write while running is
ignored. `host/machine.py` checks paused state for writes and splits transfers
into 4096-byte blocks. `read_live` uses the independent read port. Writes are streaming, not
atomic: completed bytes survive an interrupted transaction. Partial address
bytes do not write memory. A new CS starts a fresh command.

Pause freezes the next CPU bus transition without resetting registers. Reset
does not clear RAM. IRQ output now reports an unsupported-opcode CPU halt; it
is not yet a disk or keyboard interrupt line.
