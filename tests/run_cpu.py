"""Run independent NMOS 6502 functional tests against our actual RTL."""
import argparse
import hashlib
from pathlib import Path
import subprocess
import urllib.request

ROOT = Path(__file__).resolve().parents[1]

def run(command, cwd, log):
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True)
    log.write_text(result.stdout + result.stderr)
    if result.returncode:
        print((result.stdout + result.stderr)[-6000:])
        raise SystemExit(result.returncode)
    return result.stdout

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--yosys', default='F:/fpga/AgRV_pio/AgRV_pio/packages/tool-agrv_logic/map/bin/yosys.exe')
    args = parser.parse_args()
    build = ROOT / 'build/cpu'
    build.mkdir(parents=True, exist_ok=True)
    fixture = build / 'tests'
    fixture.mkdir(exist_ok=True)
    revision = '7954e2dbb49c469ea286070bf46cdd71aeb29e4b'
    source = f'https://raw.githubusercontent.com/Klaus2m5/6502_65C02_functional_tests/{revision}/'
    for name in ('bin_files/6502_functional_test.bin', 'bin_files/6502_functional_test.lst',
                 '6502_functional_test.a65', 'license.txt'):
        target = fixture / Path(name).name
        if not target.exists():
            target.write_bytes(urllib.request.urlopen(source + name, timeout=30).read())
    (fixture / 'revision.txt').write_text(revision + '\n')
    digest = hashlib.sha256((fixture / '6502_functional_test.bin').read_bytes()).hexdigest()
    if digest != 'fa12bfc761e6f9057e4cc01a665a7b800ff01ae91f598af1e39a1201d01953fd':
        raise RuntimeError('Unexpected external test image hash')
    runtime = ROOT / 'build/simulation/runtime'
    base = 'https://raw.githubusercontent.com/YosysHQ/yosys/v0.52/backends/cxxrtl/runtime/'
    for name in ('cxxrtl/cxxrtl.h', 'cxxrtl/capi/cxxrtl_capi.h'):
        target = runtime / name
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(urllib.request.urlopen(base + name, timeout=30).read())
    script = (f'read_verilog -I{(ROOT / "rtl").as_posix()} "{(ROOT / "rtl/cpu6502.v").as_posix()}"; '
              'prep -top cpu6502; check -assert; write_cxxrtl cpu_model.cc')
    run([args.yosys, '-Q', '-T', '-p', script], build, build / 'yosys.log')
    exe = build / 'cpu_test.exe'
    run(['g++', '-std=c++17', '-O2', '-I', str(runtime), '-I', str(build),
         str(ROOT / 'tests/cpu_driver.cc'), '-o', str(exe)], build, build / 'compiler.log')
    bus_exe = build / 'cpu_bus_test.exe'
    run(['g++', '-std=c++17', '-O2', '-I', str(runtime), '-I', str(build),
         str(ROOT / 'tests/cpu_bus_driver.cc'), '-o', str(bus_exe)], build, build / 'bus-compiler.log')
    print(run([str(bus_exe)], build, build / 'bus-result.log'), end='')
    print(run([str(exe)], build, build / 'result.log'), end='')
    negative = subprocess.run([str(exe), 'tests/6502_functional_test.bin', 'negative'], cwd=build,
                              capture_output=True, text=True)
    (build / 'negative-control.log').write_text(negative.stdout + negative.stderr)
    if negative.returncode != 1 or 'illegal opcode' not in negative.stderr:
        raise RuntimeError('CPU negative control failed')
    print('PASS: negative control rejects an illegal instruction')

if __name__ == '__main__':
    main()
