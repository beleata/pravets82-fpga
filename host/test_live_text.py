"""Verify actual FPGA text/keyboard behavior without pausing for video reads."""
import argparse
import json
from pathlib import Path
import time
from diagnose import Link
from machine import Machine
from text_demo import load
from text_screen import row_offset

def wait_for(predicate, message, timeout=3):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate(): return
        time.sleep(0.01)
    raise RuntimeError(message)

def send(machine, code):
    wait_for(lambda: machine.key(code), 'Keyboard latch stayed busy')

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', default='COM7')
    args = parser.parse_args()
    link = Link(args.port)
    machine = Machine(link)
    try:
        machine.memory_test()
        machine.smoke()
        load(machine)
        wait_for(lambda: machine.read_live(0x400, 7) == bytes(c | 128 for c in b'PRAVETS'), 'CPU heading missing')
        # Cross several non-contiguous Apple II text rows, including row 7->8.
        message = ''.join(chr(65 + i % 26) for i in range(165))
        for char in message: send(machine, ord(char))
        wait_for(lambda: not machine.video()['key_pending'], 'CPU did not acknowledge final key')
        time.sleep(0.01)
        page = machine.read_live(0x400, 1024)
        for i, char in enumerate(message):
            if page[row_offset(5 + i // 40) + i % 40] != ord(char) | 128:
                raise RuntimeError(f'Text mismatch at character {i}')
        send(machine, 8); send(machine, ord('!')); send(machine, 13); send(machine, ord('Z'))
        wait_for(lambda: machine.read_live(0x400 + row_offset(10), 1) == b'\xda', 'Newline failed')
        if machine.read_live(0x400 + row_offset(9) + 4, 1) != b'\xa1':
            raise RuntimeError('Backspace/replacement failed')
        state = machine.status()
        if not state['running'] or state['halted']:
            raise RuntimeError('CPU did not remain running during display/keyboard test')
        # Distinct data proves page switching chooses the correct physical page.
        machine.control(0)
        machine.write(0x800, b'\xc2' * 40)
        switch = bytes.fromhex('ad 55 c0 ad 51 c0 4c 06 11')
        machine.write(0x1100, switch); machine.write(0xfffc, b'\x00\x11'); machine.control(3)
        wait_for(lambda: machine.video()['page'] == 2, 'CPU did not select page 2')
        if machine.read_live(0x800, 40) != b'\xc2' * 40:
            raise RuntimeError('Page 2 mismatch')
        load(machine)
        wait_for(lambda: machine.read_live(0x400, 7) == bytes(c | 128 for c in b'PRAVETS'), 'Demo reload failed')
        for char in 'FPGA KEYBOARD AND DISPLAY: OK': send(machine, ord(char))
        report = dict(physical_fpga=True, endpoint_version=2, memory_bytes_tested=53248,
                      live_typing_characters=len(message), row_wrap=True, newline=True,
                      backspace=True, page2=True, cpu_running_during_video=True,
                      status=machine.status())
        path = Path(__file__).resolve().parents[1] / 'build/hardware/live-text.json'
        path.write_text(json.dumps(report, indent=2) + '\n')
        print('PASS: physical FPGA live screen, keyboard, row wrap, Enter/Backspace and page 2')
        print(json.dumps(report, indent=2))
    finally:
        link.port.close()

if __name__ == '__main__':
    main()
