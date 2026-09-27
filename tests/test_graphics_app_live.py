"""Run explicitly: real FPGA graphics displayed by the Windows application."""
import json
from pathlib import Path
import sys
import time

def main():
    rootdir=Path(__file__).resolve().parents[1]
    sys.path.insert(0,str(rootdir/'host'))
    import tkinter as tk
    from PIL import ImageGrab
    from app import App
    from graphics import hires_offset
    root=tk.Tk(); app=App(root,'COM7'); app.commands.put('graphics')
    began=time.monotonic(); phase=0; changed=set(); failure=[]; phase_at=began
    def key(code):
        app.canvas.focus_force(); root.update()
        app.canvas.event_generate('<KeyPress>',keycode=code,state=8)
    def tick():
        nonlocal phase,phase_at
        try:
            if app.last_error: raise RuntimeError(app.last_error)
            if time.monotonic()-began>20: raise RuntimeError('Graphics UI timed out: '+str(phase))
            if app.graphics_page:
                changed.add(hash(app.graphics_page))
                assert app.video['synced']
                rows = [app.graphics_page[hires_offset(y):hires_offset(y)+40] for y in range(112,124)]
                assert all(row == rows[0] for row in rows), 'Split sprite in GUI frame'
                col = rows[0].find(b'\x7f'*4)
                assert 0 <= col <= 36 and rows[0] == bytes(col)+b'\x7f'*4+bytes(36-col)
            if phase==0 and app.video and app.video['mode']==10 and len(changed)>3:
                key(ord('2')); phase=1
            elif phase==1 and app.video['page']==2:
                key(ord('L')); phase=2
            elif phase==2 and not app.video['hires']:
                assert app.photo is not None
                key(ord('M')); phase=3
            elif phase==3 and not app.video['mixed']:
                key(ord('H')); phase=4
            elif phase==4 and app.video['hires']:
                key(ord('1')); phase=5
            elif phase==5 and app.video['page']==1:
                key(ord('M')); phase=6
            elif phase==6 and app.video['mixed'] and app.frame_count>=40:
                phase_at=time.monotonic(); phase=7
            elif phase==7 and time.monotonic()-phase_at>0.6:
                app.render(); root.update()
                path=rootdir/'build/hardware/graphics-window.png'
                ImageGrab.grab(bbox=(root.winfo_rootx(),root.winfo_rooty(),
                    root.winfo_rootx()+root.winfo_width(),root.winfo_rooty()+root.winfo_height())).save(path)
                report=dict(frames=app.frame_count,ui_fps=app.fps,animation_images=len(changed),
                            graphics_switches=True,numlock_keyboard=True,physical_fpga=True,
                            complete_sprites=True,captured_while_moving=True)
                path.with_suffix('.json').write_text(json.dumps(report,indent=2)+'\n')
                print('PASS: Windows HIRES/LORES/MIXED/page switching, physical FPGA animation, Num Lock keyboard')
                print(json.dumps(report,indent=2)); phase_at=time.monotonic(); phase=8
            elif phase==8 and time.monotonic()-phase_at>0.15:
                app.close(); return
            root.after(50,tick)
        except Exception as exc: failure.append(str(exc)); app.close()
    root.after(100,tick); root.mainloop()
    if failure: raise RuntimeError(failure[0])

if __name__=='__main__': main()
