# USB binary transport, v1

The FPGA SPI protocol is unchanged. `pico/binary_bridge.py` replaces JSON on
USB only; `host/transport.py` is used by the GUI and hardware clients.
Both sides validate frame boundaries, sequence, bounded length and CRC-32.
SPI remains PIO/DMA at the physically tested 2 MHz, on the same verified pins.

Frame: magic (4 bytes), sequence (little-endian uint16), payload length
(little-endian uint16), payload, CRC-32 (little-endian uint32). CRC covers
the eight-byte header followed by the payload; it uses the ZIP/binascii
algorithm, initial value zero. Maximum payload is 16384 bytes.

| Magic | Meaning |
|---|---|
| `A2B!` | Generic SPI transaction; response contains all received SPI bytes |
| `A2M!` | Compact memory read: payload is address and count, both big-endian uint16 |
| `A2S!` | Paused video snapshot; payload is optional fence address, big-endian uint16 (`FFFF` disables) |
| `A2R!` | Successful response, matching sequence |
| `A2E!` | Error response; small ASCII reason |

`A2M!` accepts 1..16380 bytes within the 16-bit address space. Pico creates
SPI `40 address-high address-low dummy ...`, then returns just the RAM data.
The host avoids sending thousands of dummy bytes across USB. It is read-only.

`A2S!` pauses a running CPU, copies the selected video pages into Pico RAM,
and restores the original run state in `finally`, BEFORE writing any USB
response. It does not resume a CPU the user paused. A fence in main RAM is
optional: the byte must be 1 both before and after pause; otherwise resume
and retry. After 150 ms without a safe point, return a skipped frame. Halted
or manually paused CPUs bypass the fence. The host opts in only for our
exact known graphics demo, whose completed-draw marker is at `$0300`.

Response: byte 0 snapshot version 1; byte 1 flags (bit 0 completed-draw
fence used, bit 1 skipped); bytes 2..5 total CPU pause microseconds LE32;
bytes 6..15 SPI CPU status (running bit describes state restored after capture);
bytes 16..19 SPI video status; bytes 20..1043 selected text/lores page;
optional bytes 1044..9235 selected HIRES page if graphics+HIRES enabled.
Skipped responses are exactly 20 bytes with zero status/video and no image.
Normal responses are 1044 or 9236 bytes. CPU and video registers and all image
bytes are from the same pause. A plain atomic snapshot is not a guarantee
that arbitrary software has finished drawing; the optional fence supplies
that additional guarantee only for cooperating programs.

Physical measurements: 43.4 ms mean HIRES pause at 2 MHz SPI; 9.78 frames/s
including one skipped startup frame, 42.4% CPU paused time. GUI capped at 10 Hz.
See `build/hardware/snapshot.json`; unit tests also cover a fence changing
between check and pause, read exceptions, and a user's existing pause.

Empty `A2B!` sequence 65535, with a valid CRC, cleanly exits the bridge,
closes DMA and restores Ctrl-C. Normal host sequences use 1..65534.
`micropython.kbd_intr(-1)` is essential while serving frames: binary `$03`
must reach SPI instead of interrupting MicroPython. The loader sends the exit
frame before entering raw REPL. No files are installed in Pico flash.

Bad CRC never executes SPI. Invalid lengths are rejected before allocation;
the parser scans for the next magic with bounded memory. The host fails closed
after a framing/CRC/timeout error; it never silently repeats a possible write.
A truncated request may leave Pico waiting for the rest of its bounded body.
For that case `--recover-binary` pads/drains the outstanding request, then exits
the bridge and reloads it. It may return a CRC error before reaching the exit.

```powershell
python host/pico_repl.py --port COM7 --start-bridge --backend pio --spi-hz 2000000 --transport binary
# Recovery after killing a client in the middle of a request:
python host/pico_repl.py --port COM7 --recover-binary --start-bridge --spi-hz 2000000
```

The old JSON bridge is retained for diagnostics:

```powershell
python host/pico_repl.py --port COM7 --start-bridge --transport json --backend gpio
python host/diagnose.py --port COM7 --json
```

The current GUI requires binary mode; restore it after JSON diagnostics.
Close the GUI before any command-line client uses COM7.

Recovery was physically verified by sending only the first 32 bytes of an
8192-byte echo request, closing the serial port, running `--recover-binary`,
and then passing identity, pattern, live counter and 20 echo rounds. The
FPGA continued running throughout. Report: `build/hardware/binary-recovery.json`.

Measured generic full-duplex 8192-byte echo: about 69 KB/s; compact 8192-byte
RAM read: about 164 KB/s. These are different workloads. Both include Windows,
USB, MicroPython, actual SPI, and the FPGA, rather than just local DMA timing.

API references: [MicroPython CRC-32](https://docs.micropython.org/en/v1.29.0/library/binascii.html)
and [keyboard interrupt control](https://docs.micropython.org/en/v1.29.0/library/micropython.html#micropython.kbd_intr).
