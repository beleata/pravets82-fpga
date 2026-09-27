"""Minimal raw-REPL loader. Runs code in RAM; does not modify Pico flash."""
import argparse
from pathlib import Path
import time

import serial


def read_until(port, marker, timeout=5):
    data = bytearray()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        data.extend(port.read(1))
        if data.endswith(marker):
            return bytes(data)
        if len(data) > 100000:
            raise RuntimeError("Unexpectedly large raw REPL response")
    raise TimeoutError("raw REPL waiting for %r, got %r" % (marker, bytes(data)[-300:]))


def enter(port):
    # Cleanly stop the binary loop before Ctrl-C (which it deliberately disables).
    from transport import encode
    port.write(encode(b'', 65535))
    time.sleep(0.05)
    port.write(b"\r\x03\x03")
    time.sleep(0.15)
    port.reset_input_buffer()
    port.write(b"\r\x01")
    read_until(port, b"raw REPL; CTRL-B to exit\r\n>")


def execute(port, source, background=False, timeout=5):
    data = source.encode("utf-8")
    for offset in range(0, len(data), 128):
        port.write(data[offset:offset + 128])
        time.sleep(0.005)
    port.write(b"\x04")
    read_until(port, b"OK")
    if background:
        return ""
    output = read_until(port, b"\x04", timeout)[:-1]
    errors = read_until(port, b"\x04")[:-1]
    read_until(port, b">")
    if errors:
        raise RuntimeError(errors.decode("utf-8", "replace"))
    return output.decode("utf-8", "replace")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True)
    parser.add_argument("--start-bridge", action="store_true")
    parser.add_argument("--idle", action="store_true", help="release all five FPGA-connected pins")
    parser.add_argument("--backend", choices=("gpio", "pio"), default="pio")
    parser.add_argument("--spi-hz", type=int, default=1000000)
    parser.add_argument('--transport', choices=('binary', 'json'), default='binary')
    parser.add_argument('--recover-binary', action='store_true', help='drain a truncated binary frame before entering REPL')
    args = parser.parse_args()
    with serial.Serial(args.port, 115200, timeout=0.1, write_timeout=2) as port:
        if args.recover_binary:
            port.write(bytes(16400))
        enter(port)
        print(execute(port, "import sys, machine\nprint(sys.implementation)\nprint(machine.unique_id())"))
        if args.idle:
            execute(port, "from machine import Pin\nfor gp in (18,19,20,21,16): Pin(gp, Pin.IN)")
        if args.start_bridge:
            if args.transport == 'binary' and args.backend != 'pio':
                raise ValueError('binary bridge requires --backend pio')
            pico = Path(__file__).resolve().parents[1] / "pico"
            execute(port, "globals().pop('A2_PIO_HZ', None)")
            if args.backend == "pio":
                execute(port, (pico / "pio_spi.py").read_text(encoding="utf-8"))
                execute(port, "A2_PIO_HZ = %d" % args.spi_hz)
            source = (pico / ('binary_bridge.py' if args.transport == 'binary' else 'bridge.py')).read_text(encoding='utf-8')
            execute(port, source, background=True)
            print("A2 bridge started in Pico RAM")
        else:
            port.write(b"\x02")


if __name__ == "__main__":
    main()
