"""Physical FPGA graphics + binary USB throughput verification."""
import hashlib
import json
from pathlib import Path
import time
from diagnose import Link
from machine import Machine
from graphics_demo import load
from graphics import hires_offset,hires_image,lores_image
from test_live_text import wait_for,send

def main():
    root=Path(__file__).resolve().parents[1]
    link=Link('COM7'); machine=Machine(link)
    try:
        machine.memory_test(); machine.smoke(); load(machine)
        wait_for(lambda: machine.video()['mode']==10,'Graphics program did not start')
        page1=machine.read_live(0x2000,8192); page2=machine.read_live(0x4000,8192)
        assert page1[hires_offset(32):hires_offset(32)+5]==bytes(5)
        assert page2[hires_offset(32):hires_offset(32)+5]==b'\xff'*5
        assert page1!=page2
        hashes=set(); started=time.perf_counter()
        for _ in range(24):
            page=machine.read_live(0x2000,8192)
            hashes.add(hashlib.sha256(page).hexdigest())
        elapsed=time.perf_counter()-started
        assert len(hashes)>2, 'FPGA animation did not change graphics RAM'
        assert machine.status()['running'] and not machine.status()['halted']
        for code,predicate in ((ord('2'),lambda v:v['page']==2),
                               (ord('L'),lambda v:not v['hires']),
                               (ord('M'),lambda v:not v['mixed']),
                               (ord('H'),lambda v:v['hires']),
                               (ord('1'),lambda v:v['page']==1),
                               (ord('M'),lambda v:v['mixed'])):
            send(machine,code); wait_for(lambda:predicate(machine.video()),'Graphics switch key failed')
        send(machine,ord('A')); wait_for(lambda:not machine.video()['key_pending'],'A not acknowledged')
        time.sleep(0.02); left=machine.read_live(0x20,1)[0]
        send(machine,ord('D')); wait_for(lambda:not machine.video()['key_pending'],'D not acknowledged')
        time.sleep(0.02); right=machine.read_live(0x20,1)[0]
        assert right==left+1, (left,right)
        time.sleep(0.15); assert machine.read_live(0x20,1)[0]==right, 'Manual movement did not disable auto'
        hires_image(machine.read_live(0x2000,8192)).resize((840,576)).save(root/'build/hardware/hires-frame.png')
        lores_image(machine.read_live(0x400,1024)).resize((640,480)).save(root/'build/hardware/lores-frame.png')
        send(machine,32)  # leave motion enabled
        report=dict(physical_fpga=True,graphics_pages=2,hires=True,lores=True,mixed=True,
                    keyboard_movement=True,animation_hashes=len(hashes),frames_read=24,
                    seconds=elapsed,read_bytes_per_second=24*8192/elapsed,
                    hires_read_fps=24/elapsed,status=machine.status())
        (root/'build/hardware/graphics.json').write_text(json.dumps(report,indent=2)+'\n')
        print('PASS: physical FPGA HIRES/LORES, page/mixed switches, animation and keyboard movement')
        print(json.dumps(report,indent=2))
    finally: link.port.close()

if __name__=='__main__': main()
