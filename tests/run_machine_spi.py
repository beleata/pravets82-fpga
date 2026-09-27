"""Exercise the CPU/memory SPI endpoint with synchronous host RAM."""
from run_cpu import ROOT, run
import sys

def main():
    build = ROOT / 'build/cpu'
    build.mkdir(parents=True, exist_ok=True)
    run([sys.executable, str(ROOT / 'host/text_demo.py')], ROOT, build / 'text-demo.log')
    source = (ROOT / 'rtl/a2_spi_machine.v').as_posix()
    yosys = 'F:/fpga/AgRV_pio/AgRV_pio/packages/tool-agrv_logic/map/bin/yosys.exe'
    run([yosys, '-Q', '-T', '-p', f'read_verilog {source}; prep -top a2_spi_machine; '
         'check -assert; write_cxxrtl machine_spi_model.cc'], build, build / 'machine-spi-yosys.log')
    exe = build / 'machine_spi_test.exe'
    run(['g++', '-std=c++17', '-O2', '-I', str(ROOT / 'build/simulation/runtime'),
         '-I', str(build), str(ROOT / 'tests/machine_spi_driver.cc'), '-o', str(exe)],
        build, build / 'machine-spi-compiler.log')
    print(run([str(exe)], build, build / 'machine-spi-result.log'), end='')
    sources = ' '.join((ROOT / 'rtl' / name).as_posix() for name in
                       ('cpu6502.v', 'a2_spi_machine.v', 'a2_machine.v'))
    run([yosys, '-Q', '-T', '-p', f'read_verilog -I{(ROOT / "rtl").as_posix()} {sources}; '
         'prep -top a2_machine; check -assert; write_cxxrtl machine_system_model.cc'],
        build, build / 'machine-system-yosys.log')
    exe = build / 'machine_system_test.exe'
    run(['g++', '-std=c++17', '-O2', '-I', str(ROOT / 'build/simulation/runtime'),
         '-I', str(build), str(ROOT / 'tests/machine_system_driver.cc'), '-o', str(exe)],
        build, build / 'machine-system-compiler.log')
    print(run([str(exe)], build, build / 'machine-system-result.log'), end='')

if __name__ == '__main__':
    main()
