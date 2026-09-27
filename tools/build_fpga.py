"""Build the A2 CPU bring-up SRAM image using the installed Supra SDK."""
import argparse
from pathlib import Path
import shutil
import re
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdk", type=Path,
                        default=Path("F:/fpga/AgRV_pio/AgRV_pio/packages/tool-agrv_logic"))
    args = parser.parse_args()
    build = ROOT / "build" / "fpga"
    build.mkdir(parents=True, exist_ok=True)
    af = args.sdk / "bin" / "af.exe"
    yosys = args.sdk / "map" / "bin" / "yosys.exe"
    for name in ("a2_link.qsf", "a2_link.sdc", "a2_link.ve", "a2_link.pre.asf"):
        shutil.copyfile(ROOT / "board" / name, build / name)
    # Vendor frontend searches includes in its working directory.
    shutil.copyfile(ROOT / 'rtl/cpu6502_decode.vh', build / 'cpu6502_decode.vh')
    steps = [
        ("setup", [str(af), "--setup", "--design", "a2_link", "--top_module",
                   "a2_link_top", "--device", "AG10KL144H",
                   "--verilog", str(ROOT / "rtl" / "a2_link_top.v"),
                   str(ROOT / 'rtl/a2_machine.v'), str(ROOT / 'rtl/a2_spi_machine.v'),
                   str(ROOT / 'rtl/cpu6502.v')]),
        ("synthesis", [str(yosys), "-c", "af_map.tcl"]),
        ("route", [str(af), "--batch", "--mode", "NATIVE"]),
    ]
    for name, command in steps:
        started = time.monotonic()
        print(name + "...", flush=True)
        result = subprocess.run(command, cwd=build, capture_output=True, text=True,
                                encoding="utf-8", errors="replace")
        (build / (name + ".log")).write_text(result.stdout + result.stderr, encoding="utf-8")
        if result.returncode or re.search(r"(?m)^Error:", result.stdout + result.stderr):
            print((result.stdout + result.stderr)[-7000:])
            raise SystemExit(result.returncode or 1)
        if name == "setup":
            # The SDK generates a generic QSF during setup. Restore our
            # reviewed board settings before synthesis/placement.
            shutil.copyfile(ROOT / "board" / "a2_link.qsf", build / "a2_link.qsf")
            # This SDK/Yosys combination leaves proc_rom lookup tables as raw
            # memories in VQM. Lower source processes to muxes before its
            # coarse pass, preserving actual inferred RAM for BRAM mapping.
            script_path = build / 'af_map.tcl'
            script = script_path.read_text()
            if script.count('#coarse:') != 1 or script.count('#vqm:') != 1:
                raise RuntimeError('Unrecognized vendor synthesis script')
            script = script.replace('#coarse:', '#coarse:\n    yosys proc -norom')
            script = script.replace('#vqm:', '#vqm:\n    select -assert-none {t:$mem*}')
            script_path.write_text(script)
        print("%s completed in %.1fs" % (name, time.monotonic() - started), flush=True)
    image = build / "a2_link_sram.prg"
    if not image.is_file():
        raise RuntimeError("Build did not produce SRAM programming image")
    print(image)


if __name__ == "__main__":
    main()
