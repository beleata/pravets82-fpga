"""Explicit physical-FPGA test: no split/partial sprite in captured moving frames."""
import json
from pathlib import Path
import statistics
import time
from diagnose import Link
from machine import Machine
from graphics import hires_offset
from graphics_demo import load, program, FRAME_FENCE

def main():
    link = Link('COM7'); machine = Machine(link)
    pauses = []; positions = set(); dropped = 0; frames = 0
    try:
        load(machine)
        began = time.monotonic()
        for _ in range(100):
            start = time.monotonic()
            frame = machine.snapshot(FRAME_FENCE)
            if frame is None:
                dropped += 1
            else:
                page, video, state, graphics = frame
                assert video['synced'] and state['running'] and not state['halted']
                assert video['mode'] == 10
                rows = [graphics[hires_offset(y):hires_offset(y)+40] for y in range(112,124)]
                assert all(row == rows[0] for row in rows), 'Split sprite across rows'
                row = rows[0]; col = row.find(b'\x7f'*4)
                assert 0 <= col <= 36 and row == bytes(col)+b'\x7f'*4+bytes(36-col), 'Partial/erased sprite'
                positions.add(col); pauses.append(video['pause_us']); frames += 1
            time.sleep(max(0, .1-(time.monotonic()-start)))
        elapsed = time.monotonic()-began
        assert frames >= 90 and len(positions) >= 20
        # A user pause must remain paused across several snapshots, including an
        # explicitly busy fence. Resume must still execute the original program.
        machine.control(0); machine.write(FRAME_FENCE,b'\x00')
        pc = machine.status()['pc']
        for _ in range(3):
            frame = machine.snapshot(FRAME_FENCE)
            assert not frame[2]['running'] and frame[1]['pause_us'] == 0
            assert machine.status()['pc'] == pc
        machine.control(1)
        time.sleep(.1)
        assert machine.snapshot(FRAME_FENCE)[1]['synced']
        assert machine.read_live(0x1000,len(program())) == program(), 'Snapshot corrupted program'
        report = dict(physical_fpga=True,frames=frames,dropped=dropped,seconds=elapsed,
                      fps=frames/elapsed,distinct_positions=len(positions),partial_sprites=0,
                      pause_ms_mean=statistics.mean(pauses)/1000,pause_ms_max=max(pauses)/1000,
                      cpu_pause_fraction=sum(pauses)/1e6/elapsed,user_pause_preserved=True)
        path = Path(__file__).resolve().parents[1]/'build/hardware/snapshot.json'
        path.write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(report,indent=2))
    finally:
        link.port.close()

if __name__ == '__main__': main()
