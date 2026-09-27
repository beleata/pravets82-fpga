"""Real Tk -> FPGA Karateka launch, keyboard selection and display.

Movement through SPI is checked separately in host/test_karateka.py. Synthetic
Tk events do not establish that physical Windows keys were delivered.
"""
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace

def main():
    rootdir=Path(__file__).resolve().parents[1];sys.path.insert(0,str(rootdir/'host'))
    import tkinter as tk
    from PIL import ImageTk
    from app import App
    root=tk.Tk();root.withdraw();app=App(root,'COM7');app.commands.put('karateka')
    start=time.monotonic();phase=0;images=set();failure=[]
    def key(code):
        # Isolated callback injection: do not steal focus from the user's apps.
        # Focus gating itself is tested separately; real key delivery is not
        # claimed by this hardware transport/render test.
        saved=root.focus_get;root.focus_get=lambda:app.canvas
        try:
            sym={13:'Return',39:'Right',32:'space'}.get(code,chr(code))
            char='' if code in (13,39) else chr(code)
            app.on_key(SimpleNamespace(keysym=sym,char=char,state=8,keycode=code))
        finally:root.focus_get=saved
    def tick():
        nonlocal phase
        try:
            if app.last_error:raise RuntimeError(app.last_error)
            elapsed=time.monotonic()-start
            if app.graphics_page:images.add(hash(app.graphics_page))
            if phase==0 and elapsed>12:
                key(ord('K'));phase=1
            elif phase==1 and elapsed>13:
                key(13);phase=2
            # The original startup tune runs on the 6502 even without audio
            # output. Wait for it to finish before checking player movement.
            elif phase==2 and elapsed>60:
                key(39);phase=3 # Windows VK_RIGHT
            elif phase==3 and elapsed>61:
                key(39);phase=4
            elif phase==4 and elapsed>62:
                key(39);phase=5
            elif phase==5 and elapsed>64:
                key(32);phase=6
            elif phase==6 and elapsed>66:
                assert app.video and app.video['hires'] and not app.video['text']
                assert len(images)>8
                app.render();root.update()
                target=rootdir/'build/hardware/karateka-app-frame.png'
                # Read our actual Tk image, even if another app covers the window.
                ImageTk.getimage(app.photo).save(target)
                report=dict(physical_fpga=True,frames=app.frame_count,ui_fps=app.fps,
                            distinct_images=len(images),isolated_key_callbacks=True,error=app.last_error)
                app.close()
                from diagnose import Link
                from machine import Machine
                link=Link('COM7');m=Machine(link)
                try:
                    report['state']=m.status();report['level']=m.read_live(0xd2,1)[0]
                    report['keyboard_mode']=m.read_live(0xc4,1)[0]
                    report['player_position']=m.read_live(0x50,4).hex()
                    assert report['level']==1 and report['keyboard_mode']==1
                    assert not report['state']['halted']
                    assert report['player_position']!='01fe3000', 'Tk arrows did not move the player'
                finally:link.port.close()
                target.with_suffix('.json').write_text(json.dumps(report,indent=2)+'\n')
                print(json.dumps(report,indent=2));return
            root.after(50,tick)
        except Exception as exc:
            failure.append(str(exc))
            if not app.closed:app.close()
    root.after(100,tick);root.mainloop()
    if failure:raise RuntimeError(failure[0])

if __name__=='__main__':main()
