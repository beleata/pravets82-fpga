"""Program only the reviewed A2 SRAM image, never the configuration flash."""
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
AF = Path("F:/fpga/AgRV_pio/AgRV_pio/packages/tool-agrv_logic/bin/af.exe")
PINS = {"clk": 23, "sck": 38, "mosi": 42, "miso": 39,
        "cs_n": 44, "irq": 43, "led_n": 141}


def main():
    build = ROOT / "build" / "fpga"
    image = build / "a2_link_sram.prg"
    report = (build / "alta_logs" / "run.log").read_text(encoding="utf-8")
    if not re.search(r"Total 0 fatals, 0 errors, 0 warnings,", report):
        raise RuntimeError("FPGA build must have no reported errors/warnings")
    for kind in ('setup', 'hold'):
        values = re.findall(r'Worst\s+' + kind + r':\s+(-?\d+\.\d+)', report)
        if not values or float(values[-1]) < 0:
            raise RuntimeError('FPGA final ' + kind + ' timing did not close')
    actual = (build / "alta_db" / "io.asf").read_text()
    for name, pin in PINS.items():
        if not re.search(r"(?m)^set_location_assignment -to " + re.escape(name)
                         + r" PIN_" + str(pin) + r"\s*$", actual):
            raise RuntimeError("Wrong/missing FPGA pin: " + name)
    with image.open("rb") as stream:
        if b"-tdo 01000011 -mask ffffffff" not in stream.read(1024):
            raise RuntimeError("Programming image does not target the H device ID")
    result = subprocess.run([str(AF), "--prg", image.as_posix(), "-X", "set DEVICE AG10KL144H"],
                            cwd=build, capture_output=True, text=True,
                            encoding="utf-8", errors="replace")
    text = result.stdout + result.stderr
    (build / "program.log").write_text(text, encoding="utf-8")
    print(text)
    if result.returncode or re.search(r"(?im)^(?:Error:|Fatal:)|did not match", text):
        raise SystemExit(result.returncode or 1)


if __name__ == "__main__":
    main()
