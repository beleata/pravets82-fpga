"""Generate independent SPI stimuli and simulate the actual RTL with Yosys."""
import argparse
from pathlib import Path
import random
import subprocess
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


class Stimulus:
    def __init__(self):
        self.words = []
        self.transactions = 0
        self.checked = 0

    def hold(self, count, cs=0, sck=0, mosi=0, reset=0, expected=None):
        word = (reset << 5) | (cs << 4) | (sck << 3) | (mosi << 2)
        if expected is not None:
            word |= 2 | expected
            self.checked += count
        self.words.extend([word] * count)

    def start(self, half):
        self.hold(half, cs=1, expected=0)
        self.hold(half)

    def bit(self, value, expected, half):
        self.hold(half, mosi=value)
        self.hold(half, sck=1, mosi=value, expected=expected)
        # Keep MOSI stable through the falling edge, like a conventional master.
        self.hold(half, mosi=value)

    def transaction(self, tx, rx, half):
        assert len(tx) == len(rx)
        self.start(half)
        for outgoing, incoming in zip(tx, rx):
            for bit in range(7, -1, -1):
                self.bit((outgoing >> bit) & 1, (incoming >> bit) & 1, half)
        self.hold(half, cs=1, expected=0)
        self.transactions += 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--yosys", default="yosys")
    parser.add_argument("--cxx", default="g++")
    parser.add_argument("--interpreted", action="store_true",
                        help="use the much slower built-in Yosys simulator")
    args = parser.parse_args()
    build = ROOT / "build" / "simulation"
    build.mkdir(parents=True, exist_ok=True)
    s = Stimulus()
    s.hold(12, reset=1, cs=1)
    s.hold(12, cs=1, expected=0)
    rng = random.Random(1982)
    for half in (8, 11, 23):
        # Nonzero dummy bytes must not affect fixed replies. Extra response
        # clocks return zeros and must not start a new command under one CS.
        for opcode, reply in ((0, "41320100"), (0x10, "a5c33c5a"),
                              (0xFF, "bad0c0de")):
            s.transaction(bytes([opcode]) + b"\xff" * 6,
                          b"\0" + bytes.fromhex(reply) + b"\0\0", half)
        payload = bytes(range(256)) if half == 8 else bytes.fromhex("00ff55aa8001")
        s.transaction(b"\x30" + payload + b"\0", b"\0\0" + payload, half)
        for _ in range(4):
            payload = bytes(rng.randrange(256) for _ in range(rng.randrange(1, 17)))
            s.transaction(b"\x30" + payload + b"\0", b"\0\0" + payload, half)

        # Abort a command at every possible partial-byte length, sometimes
        # while SCK is still high. The next command must be decoded afresh.
        for length in range(1, 8):
            s.start(half)
            for _ in range(length):
                s.bit(1, 0, half)
            s.hold(half, cs=1, sck=length % 2, expected=0)
            s.transaction(b"\x10\0\0\0\0", bytes.fromhex("00a5c33c5a"), half)

        # Abort halfway through a response, then issue an unrelated command.
        s.start(half)
        for bit in range(7, -1, -1):
            s.bit((0x10 >> bit) & 1, 0, half)
        for bit in range(7, 3, -1):
            s.bit(0, (0xA5 >> bit) & 1, half)
        s.hold(half, cs=1, expected=0)
        s.transaction(b"\0" * 5, bytes.fromhex("0041320100"), half)

        # Reset during a command, then restart with CS idle.
        s.start(half)
        s.bit(1, 0, half)
        s.hold(12, cs=1, reset=1)
        s.transaction(b"\x10\0\0\0\0", bytes.fromhex("00a5c33c5a"), half)

    # Pause both in the high and low phases, keeping an already-present bit.
    s.start(8)
    for bit in range(7, -1, -1):
        s.bit((0x10 >> bit) & 1, 0, 8)
    s.hold(500, expected=1)
    s.hold(500, sck=1, expected=1)
    s.hold(8)
    for bit in range(30, -1, -1):
        s.bit(0, (0xA5C33C5A >> bit) & 1, 8)
    s.hold(16, cs=1, expected=0)

    # Store run lengths, not half a million duplicate samples. Yosys' built-in
    # simulator handles small stimulus memories much more efficiently.
    runs = []
    for word in s.words:
        if runs and runs[-1][0] == word and runs[-1][1] < 65535:
            runs[-1][1] += 1
        else:
            runs.append([word, 1])
    (build / "stimulus.hex").write_text(
        "\n".join("%06x" % ((length << 6) | word) for word, length in runs) + "\n")
    count = len(s.words)
    (build / "tb.v").write_text('''module tb(input clk);
    reg [21:0] stimulus [0:RUNS-1];
    initial $readmemh("stimulus.hex", stimulus);
    reg [31:0] step = 0;
    reg [15:0] elapsed = 0;
    wire [21:0] entry = stimulus[step];
    wire [5:0] sample = entry[5:0];
    wire miso, irq;
    a2_spi_diagnostic dut(.clk(clk), .reset(sample[5]), .cs_n(sample[4]),
        .sck(sample[3]), .mosi(sample[2]), .miso(miso), .irq(irq));
    always @(posedge clk) begin
        if (elapsed + 1 >= entry[21:6]) begin
            if (step < RUNS-1) step <= step + 1;
            elapsed <= 0;
        end else elapsed <= elapsed + 1;
    end
    always @* begin
        if (sample[1]) assert(miso == sample[0]);
        assert(irq == 0);
    end
endmodule
'''.replace("RUNS", str(len(runs))))
    source = (ROOT / "rtl" / "a2_spi_diagnostic.v").as_posix()
    script = ('read_verilog -formal "%s" tb.v; prep -top tb; '
              'chformal -lower; check -assert; sim -clock clk -n %d -assert -q') % (source, count + 2)
    if not args.interpreted:
        script = ('read_verilog "%s"; prep -top a2_spi_diagnostic; '
                  'check -assert; write_cxxrtl model.cc') % source
    result = subprocess.run([args.yosys, "-Q", "-T", "-p", script], cwd=build,
                            capture_output=True, text=True)
    (build / "yosys.log").write_text(result.stdout + result.stderr)
    if result.returncode:
        print((result.stdout + result.stderr)[-6000:])
        raise SystemExit(result.returncode)
    if not args.interpreted:
        runtime = build / "runtime"
        # Official Yosys simulator runtime, not application/FPGA source.
        base = "https://raw.githubusercontent.com/YosysHQ/yosys/v0.52/backends/cxxrtl/runtime/"
        for name in ("cxxrtl/cxxrtl.h", "cxxrtl/capi/cxxrtl_capi.h"):
            target = runtime / name
            if not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                with urllib.request.urlopen(base + name, timeout=30) as response:
                    target.write_bytes(response.read())
        executable = build / "spi_test.exe"
        compiled = subprocess.run(
            [args.cxx, "-std=c++17", "-O2", "-I", str(runtime), "-I", str(build),
             str(ROOT / "tests" / "cxxrtl_driver.cc"), "-o", str(executable)],
            capture_output=True, text=True)
        (build / "compiler.log").write_text(compiled.stdout + compiled.stderr)
        if compiled.returncode:
            print(compiled.stderr)
            raise SystemExit(compiled.returncode)
        simulated = subprocess.run([str(executable)], cwd=build,
                                   capture_output=True, text=True)
        (build / "result.log").write_text(simulated.stdout + simulated.stderr)
        if simulated.returncode:
            print(simulated.stdout + simulated.stderr)
            raise SystemExit(simulated.returncode)
        # Negative control for this exact model/driver: corrupt one expected
        # bit and demand a failing run. Restore the reproducible stimulus.
        stimulus_path = build / "stimulus.hex"
        original = stimulus_path.read_text()
        lines = original.splitlines()
        for index, line in enumerate(lines):
            value = int(line, 16)
            if value & 2:
                lines[index] = "%06x" % (value ^ 1)
                break
        try:
            stimulus_path.write_text("\n".join(lines) + "\n")
            negative = subprocess.run([str(executable)], cwd=build,
                                      capture_output=True, text=True)
        finally:
            stimulus_path.write_text(original)
        if negative.returncode != 1 or "FAIL at cycle" not in negative.stderr:
            raise RuntimeError("Negative control did not detect an incorrect bit")
        (build / "negative-control.log").write_text(negative.stderr)
    print("PASS: %d complete transactions, abort/reset/pause cases, "
          "%d checked sample intervals, %d core cycles" %
          (s.transactions, s.checked, count))


if __name__ == "__main__":
    main()
