# 6502 bring-up

`rtl/cpu6502.v` is a new, local implementation, with a generated table of the
151 documented NMOS instructions. No old FPGA project code is used. `ce`
advances one bus cycle; `ready` stalls reads, while writes complete. Registers,
the next instruction address and an illegal-opcode halt signal are observable.

The independent functional test is Klaus Dormann's NMOS suite at revision
`7954e2dbb49c469ea286070bf46cdd71aeb29e4b`:
<https://github.com/Klaus2m5/6502_65C02_functional_tests>.
`tests/run_cpu.py` downloads its binary, listing, source and GPLv3 license into
the ignored build directory. The binary SHA-256 is pinned. This is external
test material, not the implementation of the CPU.

The simulated RTL reached success at `$3469` after 30,646,181 instructions and
96,241,378 bus cycles, including the repeated success-loop observations. An
illegal opcode injected at the entry point makes the test fail. The reset
vector is changed to `$0400` only in the test memory.

Additional bus tests check indexed and branch dummy reads, zero-page wrapping,
the NMOS indirect-JMP page-wrap behavior, the original-value write in RMW,
JSR/RTS stack accesses, read stalls, writes under RDY, IRQ/RTI and an NMI pulse
latched while the clock enable is stopped. These tests supplement the functional
suite; they do not establish transistor-level timing equivalence.

`tests/run_machine_spi.py` also runs the complete RTL system, including both
synchronous memory banks and the CPU input latch. It loads a program over SPI,
pauses and resumes in the middle of execution, checks its 256-byte page fill,
and verifies unsupported-opcode halt and reset. A separate endpoint simulation
checks maximum bridge-sized blocks, wrapping addresses, truncated commands and
memory protection while running.

## FPGA implementation

On 2026-09-26 the physical AGM AG10KL144H passed the complete independent
functional test in **96.4207 seconds at 1 MHz**. The host verified the uploaded
image before starting, observed the final `$3469` loop, paused the CPU, and
read the completion marker `$F0` at `$0200`. The paused PC was `$346A`, the
operand position in that loop. This is a hardware result, separate from the
CXXRTL simulation above. The report is `build/hardware/cpu.json`.

Before that run, all 53,248 mapped bytes passed a random-pattern write/read
test. The short CPU program separately passed page fill, decimal ADC,
stack and subroutine checks. Pico remained the transport, not the CPU.

The final timing-constrained build uses 1,896 LUTs, 421 registers and 52 of
56 BRAM blocks. It reports zero errors/warnings, final setup slack +5.320 ns
and hold slack +0.550 ns. Programming is blocked by the wrapper if the final
setup or hold timing is negative or absent.

## Current limits

- Undocumented opcodes halt explicitly; they are not silently treated as NOPs.
- Reset initializes registers, then reads the two vector bytes. Its initial
  sequence is not the seven-cycle NMOS reset sequence.
- IRQ is sampled at instruction fetch. NMOS CLI/SEI/PLP interrupt deferral,
  branch interrupt timing and NMI takeover during interrupt entry are not yet
  implemented or verified.
- Decimal arithmetic has NMOS flag semantics and passes the functional suite.
  Exhaustive invalid-BCD testing remains to be done.
- `a2_machine.v` is a development memory map with Apple keyboard and display
  switches, not a completed chipset. There is no Disk II controller, full Apple ROM, graphics scanner,
  speaker, paddle timing or language card yet.

## Memory and clock

The board's 50 MHz oscillator clocks all logic. The CPU advances every 50
clocks while running: exactly 1 MHz, not yet the Apple II's clock cadence.
There are 48 KiB at `$0000–$BFFF` and a 4 KiB writable development bank at
`$F000–$FFFF`. `$C000–$EFFF` reads as `$FF`. The top bank holds reset/interrupt
vectors and test data, not BASIC. CPU writes to it are intentional for bring-up.

Both memory banks now have independent CPU and host synchronous read ports.
Host writes are allowed only while the CPU is paused; resuming allows a complete divider interval for the
CPU read data to settle. CPU input is latched at divider 46 and consumed at
divider 49. Its path to CPU registers is constrained as three oscillator
cycles (setup 3, hold 2); other internal paths retain the 20 ns constraint.
The Windows display now uses paused snapshots, capped at 10 Hz. See
`live-display.md` for the display and keyboard milestone.

## Reproduce

From `F:/fpga/A2`:

```powershell
python tools/gen_cpu_decode.py
python tests/run_cpu.py
python tests/run_machine_spi.py
python tools/build_fpga.py
python tools/program_fpga.py
python host/pico_repl.py --port COM7 --start-bridge --backend pio --spi-hz 2000000
python host/machine.py --port COM7 --memory-test --smoke --klaus build/cpu/tests/6502_functional_test.bin --report build/hardware/cpu.json
```

The hardware memory test overwrites the development RAM, then loads test code.
It does not write either board's flash. After success the CPU stays paused,
with the test image in volatile RAM. Existing JTAG readback mismatch reporting
is retained; functional hardware results are recorded separately.

The vendor-generated synthesis Tcl is adjusted only inside `build/fpga` to
run `proc -norom` before coarse synthesis. Otherwise this SDK/Yosys combination
leaves two opcode/state lookup memories in the VQM, which the native tool
rejects. Actual writable memories still infer BRAM. An assertion rejects any
unmapped memory remaining before VQM output. The installed SDK is not edited.
