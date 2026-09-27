"""Windows live display for the physical A2 FPGA. No CPU emulation or local echo."""
import argparse
import queue
import threading
import time
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk
from diagnose import Link
from machine import Machine
from text_demo import load
from text_screen import decode_page, keyboard_code
from graphics import hires_image, lores_image

class App:
    def __init__(self, root, port='COM7', demo=False):
        self.root = root
        self.stop = threading.Event()
        self.commands = queue.Queue()
        self.keys = queue.Queue(maxsize=256)
        self.key_sequence = 0
        self.events = queue.SimpleQueue()
        self.frames = queue.Queue(maxsize=1)
        self.worker = None
        self.page = None
        self.video = None
        self.graphics_page = None
        self.graphics_cache = None
        self.last_mode = None
        self.photo = None
        self.color = tk.BooleanVar(value=True)
        self.fps_started = time.monotonic()
        self.fps_count = 0
        self.fps = 0.0
        self.previous = {}
        self.frame_count = 0
        self.last_error = None
        self.closed = False
        root.title('Правец 82 · FPGA')
        root.configure(bg='#131b20')
        root.resizable(False, False)
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('TButton', padding=(10, 7))
        top = tk.Frame(root, bg='#131b20', padx=20, pady=16)
        top.pack(fill='x')
        tk.Label(top, text='ПРАВЕЦ 82', fg='#d5eee0', bg='#131b20',
                 font=('Segoe UI', 19, 'bold')).pack(side='left')
        tk.Label(top, text='APPLE II  /  ЖИВА FPGA', fg='#8ca99a', bg='#131b20',
                 font=('Segoe UI', 10)).pack(side='right')
        bar = tk.Frame(root, bg='#131b20', padx=20)
        bar.pack(fill='x')
        self.port = tk.StringVar(value=port)
        ttk.Entry(bar, textvariable=self.port, width=8).pack(side='left', padx=(0, 8))
        ttk.Button(bar, text='Свържи', command=self.connect).pack(side='left')
        ttk.Button(bar, text='Текст', command=lambda: self.command('demo')).pack(side='left', padx=6)
        ttk.Button(bar, text='Графика', command=lambda: self.command('graphics')).pack(side='left', padx=(0,6))
        ttk.Button(bar, text='Пауза', command=lambda: self.command('pause')).pack(side='left')
        ttk.Button(bar, text='Продължи', command=lambda: self.command('resume')).pack(side='left', padx=8)
        ttk.Checkbutton(bar, text='Цвят', variable=self.color).pack(side='left')
        gamebar = tk.Frame(root, bg='#131b20', padx=20, pady=6)
        gamebar.pack(fill='x')
        ttk.Button(gamebar, text='Karateka', command=lambda: self.command('karateka')).pack(side='left')
        tk.Label(gamebar, text='Enter: начало · K: клавиатура · ←/→: движение\nQ/A/Z: удар · W/S/X: ритник · Space: стойка',
                 fg='#aac6b6', bg='#131b20', font=('Segoe UI', 9)).pack(side='left', padx=10)
        self.canvas = tk.Canvas(root, width=680, height=520, bg='#06130c',
                                highlightthickness=1, highlightbackground='#294c39', takefocus=True)
        self.canvas.pack(padx=20, pady=(16, 8))
        self.image_item = self.canvas.create_image(20, 20, anchor='nw', state='hidden')
        self.rectangles, self.glyphs = {}, {}
        for row in range(24):
            for col in range(40):
                x, y = 20 + col * 16, 20 + row * 20
                self.rectangles[row, col] = self.canvas.create_rectangle(x, y, x+16, y+20, fill='#06130c', outline='', tags=('row'+str(row),))
                self.glyphs[row, col] = self.canvas.create_text(x+8, y+10, text=' ',
                    font=('Consolas', -18), fill='#80ec9d', tags=('row'+str(row),))
        self.overlay = self.canvas.create_text(340, 250, text='Свързване с FPGA…',
            fill='#80ec9d', font=('Segoe UI', 16), width=600, justify='center')
        self.status = tk.StringVar(value='Свързване…')
        self.focus_status = tk.StringVar(value='Щракни върху екрана, за да пишеш.')
        tk.Label(root, textvariable=self.status, fg='#aac6b6', bg='#131b20',
                 font=('Segoe UI', 10), wraplength=680, justify='left').pack(anchor='w', padx=20)
        tk.Label(root, textvariable=self.focus_status, fg='#80ec9d', bg='#131b20',
                 font=('Segoe UI', 10), pady=10).pack(anchor='w', padx=20)
        self.canvas.bind('<Button-1>', lambda event: self.canvas.focus_set())
        self.canvas.bind('<KeyPress>', self.on_key)
        self.canvas.bind('<FocusIn>', lambda event: self.focus_status.set('Клавиатурата е активна за FPGA.'))
        root.bind('<FocusOut>', self.focus_lost, add='+')
        root.protocol('WM_DELETE_WINDOW', self.close)
        self.connect()
        if demo:
            self.commands.put('demo')
        root.after(35, self.update)

    def clear_keys(self):
        while True:
            try: self.keys.get_nowait()
            except queue.Empty: break

    def focus_lost(self, event=None):
        self.clear_keys()
        self.focus_status.set('Клавиатурата е освободена. Щракни върху екрана, за да пишеш.')

    def on_key(self, event):
        # No global hooks. Bind only to this app's focused screen widget.
        if self.root.focus_get() is not self.canvas:
            return None
        code = keyboard_code(event.keysym, event.char, event.state, event.keycode)
        if code is not None and self.worker and self.worker.is_alive():
            self.key_sequence += 1
            try: self.keys.put_nowait((self.key_sequence, code))
            except queue.Full: self.focus_status.set('Опашката за клавиши е пълна; изчакай.')
        return 'break'

    def command(self, name):
        self.clear_keys()
        if self.worker and self.worker.is_alive():
            self.commands.put(name)
            self.canvas.focus_set()
        else:
            self.status.set('Няма връзка. Провери порта и натисни „Свържи“.')

    def connect(self):
        if self.worker and self.worker.is_alive():
            return
        self.clear_keys()
        self.last_error = None
        try: self.frames.get_nowait()
        except queue.Empty: pass
        self.status.set('Свързване с ' + self.port.get() + '…')
        self.worker = threading.Thread(target=self.io_loop, args=(self.port.get(),), daemon=True)
        self.worker.start()

    def io_loop(self, port):
        link = None
        try:
            link = Link(port)
            machine = Machine(link)
            machine.video()
            # Reconnection opts into the fence only for the exact known program.
            from graphics_demo import program as graphics_program, FRAME_FENCE
            demo_code = graphics_program()
            pc = machine.status()['pc']
            known_demo = (0x1000 <= pc < 0x1000 + len(demo_code)
                          and machine.read_live(0x1000, len(demo_code)) == demo_code)
            fence = FRAME_FENCE if known_demo else None
            from karateka import Karateka, SIGNATURE, MAGIC, shim
            game = None
            if machine.read_live(SIGNATURE,len(MAGIC)) == MAGIC and machine.read_live(0xf100,len(shim())) == shim():
                game = Karateka(machine)
            while not self.stop.is_set():
                began = time.monotonic()
                while not self.commands.empty():
                    command = self.commands.get_nowait()
                    if command == 'demo':
                        self.events.put(('info', 'Зареждане на 6502 теста…'))
                        load(machine)
                        fence = None
                        game = None
                    elif command == 'graphics':
                        from graphics_demo import load as load_graphics
                        self.events.put(('info', 'Зареждане на графичния 6502 тест…'))
                        load_graphics(machine)
                        fence = FRAME_FENCE
                        game = None
                    elif command == 'karateka':
                        self.events.put(('info', 'Зареждане на Karateka в FPGA…'))
                        game = Karateka(machine)
                        game.load()
                        fence = None
                    elif command == 'pause': machine.control(0)
                    elif command == 'resume': machine.control(1)
                # Keep unaccepted key at the head; FPGA has a one-key latch.
                for _ in range(16):
                    with self.keys.mutex:
                        key = self.keys.queue[0] if self.keys.queue else None
                    if key is None or not machine.key(key[1]):
                        break
                    with self.keys.mutex:
                        if self.keys.queue and self.keys.queue[0] == key:
                            self.keys.queue.popleft()
                if game is not None:
                    game.service()
                frame = machine.snapshot(fence)
                if frame is not None:
                    try: self.frames.get_nowait()
                    except queue.Empty: pass
                    self.frames.put_nowait(frame)
                self.stop.wait(max(0, 0.1 - (time.monotonic() - began)))
        except Exception as exc:
            self.events.put(('error', str(exc)))
        finally:
            if link:
                link.port.close()

    def render(self):
        if self.page is None:
            return
        cells = decode_page(self.page, bool(int(time.monotonic() * 2) & 1))
        text_mode = self.video['text']
        if self.last_mode != self.video['mode']:
            self.canvas.itemconfigure(self.image_item, state='hidden' if text_mode else 'normal')
            for row in range(24):
                visible = text_mode or (self.video['mixed'] and row >= 20)
                self.canvas.itemconfigure('row'+str(row), state='normal' if visible else 'hidden')
            self.last_mode = self.video['mode']
        if not text_mode:
            raw = self.graphics_page if self.video['hires'] else self.page
            key = (raw, self.video['hires'], self.color.get())
            if key != self.graphics_cache and raw is not None:
                bitmap = hires_image(raw, self.color.get()) if self.video['hires'] else lores_image(raw)
                self.photo = ImageTk.PhotoImage(bitmap.resize((640,480), Image.Resampling.NEAREST))
                self.canvas.itemconfigure(self.image_item, image=self.photo)
                self.graphics_cache = key
        for row in range(24):
            for col in range(40):
                char, inverse = cells[row][col]
                if not text_mode and not (self.video['mixed'] and row >= 20):
                    char, inverse = ' ', False
                if self.previous.get((row, col)) == (char, inverse):
                    continue
                self.previous[row, col] = (char, inverse)
                self.canvas.itemconfigure(self.rectangles[row, col], fill='#80ec9d' if inverse else '#06130c')
                self.canvas.itemconfigure(self.glyphs[row, col], text=char, fill='#06130c' if inverse else '#80ec9d')
        self.canvas.itemconfigure(self.overlay, text='')

    def update(self):
        if self.closed:
            return
        while not self.events.empty():
            kind, text = self.events.get_nowait()
            self.status.set(text)
            if kind == 'error':
                self.last_error = text
                self.canvas.itemconfigure(self.overlay, text='Връзката е прекъсната.\n' + text)
                self.page = None
                self.clear_keys()
        try:
            page, video, state, graphics_page = self.frames.get_nowait()
            if self.last_error is not None:
                self.root.after(35, self.update)
                return
            self.page, self.video = page, video
            self.graphics_page = graphics_page
            self.frame_count += 1
            self.fps_count += 1
            elapsed = time.monotonic() - self.fps_started
            if elapsed >= 1:
                self.fps = self.fps_count / elapsed
                self.fps_count = 0; self.fps_started = time.monotonic()
            mode = 'СПРЯН: НЕПОДДЪРЖАНА ИНСТРУКЦИЯ' if state['halted'] else 'Работи' if state['running'] else 'Пауза'
            display = 'TEXT' if video['text'] else 'HIRES' if video['hires'] else 'LORES'
            sync = 'готов кадър' if video['synced'] else 'RAM снимка'
            self.status.set(f"{self.port.get()} · {mode} · {display} {video['page']} · PC ${state['pc']:04X} · {self.fps:.1f}/10 кадъра/s · {sync} · стоп {video['pause_us']/1000:.0f} ms")
        except queue.Empty:
            pass
        self.render()
        self.root.after(35, self.update)

    def close(self):
        self.closed = True
        self.stop.set()
        self.clear_keys()
        if self.worker and self.worker.is_alive():
            self.worker.join(timeout=3.5)
        self.root.destroy()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', default='COM7')
    parser.add_argument('--demo', action='store_true', help='load our ROM-free 6502 text test')
    args = parser.parse_args()
    root = tk.Tk()
    App(root, args.port, args.demo)
    root.mainloop()

if __name__ == '__main__':
    main()
