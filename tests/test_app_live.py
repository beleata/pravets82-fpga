"""Explicit hardware/UI smoke test; run as a script, not collected by pytest."""
import json
from pathlib import Path
import sys
import time

def main():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'host'))
    import tkinter as tk
    from PIL import ImageGrab
    from app import App
    from text_screen import row_offset
    root = tk.Tk()
    app = App(root, 'COM7', demo=True)
    began = time.monotonic()
    phase = 0
    phase_at = began
    screenshot = Path(__file__).resolve().parents[1] / 'build/hardware/a2-window.png'
    failure = []

    def row(number):
        return app.page[row_offset(number):row_offset(number)+40] if app.page else b''

    def check():
        nonlocal phase, phase_at
        try:
            if app.last_error: raise RuntimeError(app.last_error)
            if time.monotonic() - began > 20: raise RuntimeError('UI test timed out at phase ' + str(phase))
            if phase == 0 and app.page and row(0).startswith(b'\xd0\xd2\xc1\xd6\xc5\xd4\xd3'):
                app.canvas.focus_force(); root.update()
                for char in 'HELLO': app.canvas.event_generate('<KeyPress>', keycode=ord(char), state=8)
                phase = 1
            elif phase == 1 and row(5).startswith(b'\xc8\xc5\xcc\xcc\xcf'):
                # Move focus to a different control, then deliver a synthetic
                # key to the canvas: its explicit focus guard must reject it.
                entry = root.winfo_children()[1].winfo_children()[0]
                entry.focus_force(); root.update()
                app.canvas.event_generate('<KeyPress>', keycode=88, state=8)
                phase_at = time.monotonic(); phase = 2
            elif phase == 2 and time.monotonic() - phase_at > 0.5:
                if row(5)[5] != 0xa0: raise RuntimeError('Key escaped the focus guard')
                app.canvas.focus_force(); root.update()
                app.canvas.event_generate('<KeyPress>', keysym='Return', state=8)
                app.canvas.event_generate('<KeyPress>', keycode=90, state=8)
                phase = 3
            elif phase == 3 and row(6).startswith(b'\xda'):
                app.render(); root.update()
                box = (root.winfo_rootx(), root.winfo_rooty(),
                       root.winfo_rootx()+root.winfo_width(), root.winfo_rooty()+root.winfo_height())
                ImageGrab.grab(bbox=box).save(screenshot)
                report = {'frames_received': app.frame_count, 'typed_via_tk_events': 'HELLO\nZ',
                          'unfocused_key_ignored': True, 'error': None, 'screenshot': str(screenshot)}
                screenshot.with_suffix('.json').write_text(json.dumps(report, indent=2)+'\n')
                print('PASS: Tk window -> keyboard -> physical CPU -> RAM -> rendered screen; focus guard', flush=True)
                app.close(); return
            root.after(50, check)
        except Exception as exc:
            failure.append(str(exc)); app.close()
    root.after(100, check)
    root.mainloop()
    if failure: raise RuntimeError(failure[0])

if __name__ == '__main__':
    main()
