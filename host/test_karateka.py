"""Explicit physical FPGA loading/keyboard test, with diagnostic level jumps.

Forced level entry tests the file adapter and decompression. It does NOT
establish that normal gameplay transitions or an entire playthrough work.
"""
import json
from pathlib import Path
import time
from diagnose import Link
from machine import Machine
from karateka import Karateka
from graphics import hires_image

def main():
    link=Link('COM7');m=Machine(link);k=Karateka(m);report={'physical_fpga':True,'levels':[]}
    try:
        # Start with the current first playable level, already loaded normally.
        before=m.read_live(0x50,4)
        for _ in range(8):
            m.key(21);time.sleep(.15);k.service()
        after=m.read_live(0x50,4)
        report['movement_before']=before.hex();report['movement_after']=after.hex()
        assert before!=after, 'Player did not move after right-arrow input'
        for level in (2,3,4):
            m.control(0)
            # Enter the game's own level loader, preserving its common code.
            boot=bytearray.fromhex('78 d8 a2 ff 9a')
            for addr in (0xc050,0xc052,0xc054,0xc057):boot+=bytes([0xad,addr&255,addr>>8])
            boot+=bytes([0xa9,level,0x85,0xd0,0xa9,0,0x85,0xdc,0xa9,1,0x85,0xc4,0x4c,0x0c,2])
            m.write(0xf000,boot);m.control(3)
            deadline=time.monotonic()+20;loaded=False
            while time.monotonic()<deadline:
                k.service();state=m.status()
                if state['halted']:raise RuntimeError(state)
                if m.read_live(0xd2,1)[0]==level:
                    loaded=True;break
                time.sleep(.02)
            assert loaded, f'Level {level} failed to load'
            time.sleep(1)
            page,video,state,graphics=m.snapshot()
            assert graphics and not state['halted']
            hires_image(graphics).resize((1120,768)).save(f'build/hardware/karateka-level-{level}.png')
            result=dict(level=level,state=state,markers=m.read_live(0xbffd,3).hex())
            report['levels'].append(result);print('LEVEL',level,result,flush=True)
        report['requests']=k.requests
        report['normal_playthrough_verified']=False
        Path('build/hardware/karateka-levels.json').write_text(json.dumps(report,indent=2)+'\n')
    finally:link.port.close()

if __name__=='__main__':main()
