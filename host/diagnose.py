"""Windows-side diagnostic client. Pico bridge must already be running."""
import argparse
import json
import random
import time
from pathlib import Path

import serial


class JsonLink:
    def __init__(self, port):
        self.port = serial.Serial(port, 115200, timeout=0.1, write_timeout=10)
        self.request_id = 0
        self.pending = bytearray()

    def exchange(self, payload):
        self.request_id += 1
        request = {"id": self.request_id, "tx": payload.hex()}
        self.port.write((json.dumps(request) + "\n").encode("ascii"))
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if b"\n" not in self.pending:
                self.pending.extend(self.port.read(max(1, min(self.port.in_waiting, 32768))))
                if len(self.pending) > 32768:
                    raise RuntimeError("oversize response")
                continue
            line, _, remaining = self.pending.partition(b"\n")
            self.pending = bytearray(remaining)
            obj = json.loads(line)
            if obj.get("id") != self.request_id:
                continue
            if "error" in obj:
                raise RuntimeError(obj["error"])
            received = bytes.fromhex(obj["rx"])
            if len(received) != len(payload):
                raise RuntimeError("response length mismatch")
            return received
        raise TimeoutError("No matching response from A2 bridge")


from transport import Link

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True)
    parser.add_argument('--json', action='store_true', help='use the older diagnostic JSON bridge')
    parser.add_argument("--rounds", type=int, default=50)
    parser.add_argument("--payload-size", type=int, default=32)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    if args.rounds < 1:
        parser.error("--rounds must be positive")
    if not 1 <= args.payload_size <= 8192:
        parser.error("--payload-size must be 1..8192")
    link = JsonLink(args.port) if args.json else Link(args.port)
    try:
        for opcode, expected in [(0, "0041320100"), (0x10, "00a5c33c5a"),
                                  (0xFE, "00bad0c0de")]:
            actual = link.exchange(bytes([opcode, 0, 0, 0, 0]))
            if actual.hex() != expected:
                raise RuntimeError("opcode %02x: %s != %s" % (opcode, actual.hex(), expected))
        rng = random.Random(82)
        first = int.from_bytes(link.exchange(b"\x20\0\0\0\0")[1:], "big")
        time.sleep(0.025)
        second = int.from_bytes(link.exchange(b"\x20\0\0\0\0")[1:], "big")
        delta = (second - first) & 0xFFFFFFFF
        if not 0 < delta < 1000000000:
            raise RuntimeError("FPGA clock counter is not progressing")
        began = time.perf_counter()
        for _ in range(args.rounds):
            payload = bytes(rng.randrange(256) for _ in range(args.payload_size))
            received = link.exchange(b"\x30" + payload + b"\0")
            if received != b"\0\0" + payload:
                raise RuntimeError("echo mismatch: " + received.hex())
        elapsed = time.perf_counter() - began
        report = {"port": args.port, "rounds": args.rounds,
                  "payload_bytes": args.payload_size, "elapsed_seconds": elapsed,
                  "payload_bytes_per_second": args.rounds * args.payload_size / elapsed,
                  "counter_delta": delta, "errors": 0}
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print("PASS: A2 identity, bit pattern, unknown opcode, live counter and %d echo rounds" % args.rounds)
        print(json.dumps(report, indent=2))
    finally:
        link.port.close()


if __name__ == "__main__":
    main()
