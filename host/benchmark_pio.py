"""Run long echo transfers on Pico/FPGA, excluding USB/JSON overhead."""
import argparse
import json
from pathlib import Path
import serial

from pico_repl import enter, execute

ROOT = Path(__file__).resolve().parents[1]
CODE = '''
import time, json
for hz in (100000, 500000, 1000000, 2000000):
    bus = A2PioSPI(hz)
    try:
        actual = bus.transfer(bytes((0,0,0,0,0)))
        if actual != bytes((0,0x41,0x32,1,0)):
            raise ValueError("identity mismatch %r" % actual)
        payload = bytes(range(256)) * 16
        tx = bytes((0x30,)) + payload + bytes((0,))
        expected = bytes((0,0)) + payload
        rounds = 16
        began = time.ticks_us()
        for i in range(rounds):
            if bus.transfer(tx) != expected:
                raise ValueError("echo mismatch at %d Hz, round %d" % (hz,i))
        elapsed = time.ticks_diff(time.ticks_us(), began)
        print(json.dumps({"spi_hz":hz,"rounds":rounds,"bytes_per_round":len(tx),
              "elapsed_us":elapsed,"payload_bytes_per_second":len(payload)*rounds*1000000//elapsed,
              "errors":0}))
    finally:
        bus.close()
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True)
    args = parser.parse_args()
    with serial.Serial(args.port, 115200, timeout=0.1, write_timeout=2) as port:
        enter(port)
        execute(port, (ROOT / "pico" / "pio_spi.py").read_text(encoding="utf-8"))
        output = execute(port, CODE, timeout=30)
        port.write(b"\x02")
    results = [json.loads(line) for line in output.splitlines() if line.strip()]
    if len(results) != 4:
        raise RuntimeError("Incomplete speed sweep")
    destination = ROOT / "build" / "hardware" / "pio-benchmark.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
