import tkinter as tk
from tkinter import ttk
import mss
from PIL import Image, ImageTk
import keyboard
import json
import os
import ctypes

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except:
    pass

SETTINGS_FILE = "Zoom_settings.json"

class BuffMirrorApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Buff Bar Zoom")
        self.root.geometry("450x900")
        self.root.attributes('-topmost', True)
        
        self.root.protocol("WM_DELETE_WINDOW", self.quit_app)

        self.sct = mss.mss()
        self.monitors = self.sct.monitors[1:]
        
        self.current_mon_idx = 0 
        self.monitor_offset_x = self.monitors[0]['left']
        self.monitor_offset_y = self.monitors[0]['top']
        self.screen_width = self.monitors[0]['width']
        self.screen_height = self.monitors[0]['height']

        self.mode = "SETUP" 
        self.running_thread = True
        self.mirror_windows = []

        defaults = {
            'r1_x': 100, 'r1_y': 100, 'r1_w': 200, 'r1_h': 50, 'r1_on': True,
            'r2_x': 350, 'r2_y': 100, 'r2_w': 50,  'r2_h': 50, 'r2_on': True,
            'r3_x': 450, 'r3_y': 100, 'r3_w': 50,  'r3_h': 50, 'r3_on': False,
            'r4_x': 550, 'r4_y': 100, 'r4_w': 50,  'r4_h': 50, 'r4_on': False,
            'zoom': 2.0,
            'fps': 30,
            'separate': False,
            'monitor_idx': 0
        }
        loaded = self.load_settings()
        settings = {**defaults, **loaded}

        if 0 <= settings['monitor_idx'] < len(self.monitors):
            self.current_mon_idx = settings['monitor_idx']
            self.update_monitor_vars(self.current_mon_idx)

        self.regions = []
        for i in range(1, 5):
            self.regions.append({
                'x': tk.IntVar(value=settings[f'r{i}_x']),
                'y': tk.IntVar(value=settings[f'r{i}_y']),
                'w': tk.IntVar(value=settings[f'r{i}_w']),
                'h': tk.IntVar(value=settings[f'r{i}_h']),
                'on': tk.BooleanVar(value=settings[f'r{i}_on']),
                'scale_x': None,
                'scale_y': None
            })

        self.zoom = tk.DoubleVar(value=settings['zoom'])
        self.fps = tk.IntVar(value=settings['fps'])
        self.separate = tk.BooleanVar(value=settings['separate'])

        self.separate.trace_add('write', self.rebuild_mirrors_callback)
        for r in self.regions:
            r['on'].trace_add('write', self.rebuild_mirrors_callback)

        self.overlay = tk.Toplevel(self.root)
        self.overlay.attributes('-alpha', 0.3, '-topmost', True, '-transparentcolor', 'white')
        self.overlay.overrideredirect(True)
        self.overlay_canvas = tk.Canvas(self.overlay, bg='white', highlightthickness=0)
        self.overlay_canvas.pack(fill="both", expand=True)

        self.create_widgets()
        self.update_overlay_geometry()
        
        self.rebuild_mirror_windows()
        self.update_overlay_loop()
        self.update_mirror_loop()

    def update_monitor_vars(self, index):
        m = self.monitors[index]
        self.monitor_offset_x = m['left']
        self.monitor_offset_y = m['top']
        self.screen_width = m['width']
        self.screen_height = m['height']

    def update_overlay_geometry(self):
        geo = f"{self.screen_width}x{self.screen_height}+{self.monitor_offset_x}+{self.monitor_offset_y}"
        self.overlay.geometry(geo)
        if hasattr(self, 'regions'):
            for r in self.regions:
                if r['scale_x']: r['scale_x'].configure(to=self.screen_width)
                if r['scale_y']: r['scale_y'].configure(to=self.screen_height)

    def on_monitor_change(self, event):
        idx = self.monitor_combo.current()
        if idx >= 0:
            self.current_mon_idx = idx
            self.update_monitor_vars(idx)
            self.update_overlay_geometry()

    def create_widgets(self):
        mon_frame = tk.Frame(self.root, pady=5)
        mon_frame.pack(fill="x", padx=5)
        tk.Label(mon_frame, text="Select Monitor:").pack(side="left")
        
        mon_names = [f"Monitor {i+1} ({m['width']}x{m['height']})" for i, m in enumerate(self.monitors)]
        self.monitor_combo = ttk.Combobox(mon_frame, values=mon_names, state="readonly")
        self.monitor_combo.current(self.current_mon_idx)
        self.monitor_combo.pack(side="left", fill="x", expand=True, padx=5)
        self.monitor_combo.bind("<<ComboboxSelected>>", self.on_monitor_change)

        info_frame = tk.Frame(self.root, pady=5)
        info_frame.pack(fill="x")
        
        tk.Label(info_frame, text="F1: Run").grid(row=0, column=0, padx=10, sticky="w")
        tk.Label(info_frame, text="F2: Setup").grid(row=0, column=1, padx=10, sticky="w")
        tk.Label(info_frame, text="F3: Preview").grid(row=1, column=0, padx=10, sticky="w")
        tk.Label(info_frame, text="F4: Quit").grid(row=1, column=1, padx=10, sticky="w")

        main_frame = tk.Frame(self.root)
        main_frame.pack(fill="both", expand=True, padx=5)

        for i, r_vars in enumerate(self.regions):
            lf = ttk.LabelFrame(main_frame, text=f"Region {i+1}")
            lf.pack(fill="x", pady=2)
            
            cb = ttk.Checkbutton(lf, text="Enable", variable=r_vars['on'])
            cb.pack(anchor='w')

            r_vars['scale_x'] = self.make_slider(lf, "X", r_vars['x'], self.screen_width)
            r_vars['scale_y'] = self.make_slider(lf, "Y", r_vars['y'], self.screen_height)
            self.make_slider(lf, "W", r_vars['w'], 800)
            self.make_slider(lf, "H", r_vars['h'], 300)

        lf_set = ttk.LabelFrame(main_frame, text="Settings")
        lf_set.pack(fill="x", pady=5)
        
        ttk.Label(lf_set, text="Zoom").pack()
        ttk.Scale(lf_set, from_=1.0, to=5.0, variable=self.zoom, orient='horizontal').pack(fill='x', padx=5)
        
        frame_opts = ttk.Frame(lf_set)
        frame_opts.pack(fill="x", pady=5)
        
        ttk.Label(frame_opts, text="FPS:").pack(side="left", padx=5)
        ttk.Spinbox(frame_opts, from_=1, to=144, textvariable=self.fps, width=5).pack(side="left")

        ttk.Checkbutton(frame_opts, text="Separate Windows", variable=self.separate).pack(side="right", padx=5)

        tk.Label(self.root, text="discord - spctrl, Roblox - 45LEGEND_X", font=("Arial", 8), fg="gray").pack(side="bottom", pady=5)

    def make_slider(self, parent, label, var, max_val):
        frame = ttk.Frame(parent)
        frame.pack(fill="x", padx=2, pady=1)
        ttk.Label(frame, text=label, width=2).pack(side="left")
        scale = ttk.Scale(frame, from_=0, to=max_val, variable=var, orient='horizontal')
        scale.pack(side="left", fill="x", expand=True)
        ttk.Entry(frame, textvariable=var, width=5).pack(side="right")
        return scale

    def rebuild_mirrors_callback(self, *args):
        self.root.after(10, self.rebuild_mirror_windows)

    def rebuild_mirror_windows(self):
        for win, lbl in self.mirror_windows:
            win.destroy()
        self.mirror_windows = []

        active_indices = [i for i, r in enumerate(self.regions) if r['on'].get()]
        if not active_indices: return

        if self.separate.get():
            for idx in active_indices:
                self.create_single_window(idx)
        else:
            self.create_single_window("combined")

        if self.mode == "SETUP":
            self.hide_mirrors()
        else:
            self.show_mirrors()

    def create_single_window(self, tag):
        win = tk.Toplevel(self.root)
        win.overrideredirect(True)
        win.attributes('-topmost', True)
        
        lbl = tk.Label(win, bg='black', borderwidth=0)
        lbl.pack()
        
        win.bind('<Button-1>', self.start_move)
        win.bind('<B1-Motion>', self.do_move)
        
        self.mirror_windows.append((win, lbl))

    def start_move(self, event):
        self.drag_win = event.widget.winfo_toplevel()
        self.win_x = event.x
        self.win_y = event.y

    def do_move(self, event):
        x = self.drag_win.winfo_x() + (event.x - self.win_x)
        y = self.drag_win.winfo_y() + (event.y - self.win_y)
        self.drag_win.geometry(f"+{x}+{y}")

    def update_overlay_loop(self):
        if self.mode in ["SETUP", "PREVIEW"]:
            self.overlay.deiconify()
            self.overlay_canvas.delete("all")
            colors = ["red", "blue", "green", "purple"]
            
            for i, r in enumerate(self.regions):
                if r['on'].get():
                    x, y = r['x'].get(), r['y'].get()
                    w, h = r['w'].get(), r['h'].get()
                    self.overlay_canvas.create_rectangle(x, y, x+w, y+h, outline=colors[i], width=3)
                    self.overlay_canvas.create_text(x, y-15, text=f"R{i+1}", fill=colors[i], font=("Arial", 10, "bold"), anchor="nw")
        else:
            self.overlay.withdraw()
            
        if self.running_thread:
            self.root.after(50, self.update_overlay_loop)

    def update_mirror_loop(self):
        if self.mode in ["RUNNING", "PREVIEW"] and self.mirror_windows:
            try:
                active_regions = [r for r in self.regions if r['on'].get()]
                captured_images = []
                
                for r in active_regions:
                    global_left = self.monitor_offset_x + r['x'].get()
                    global_top = self.monitor_offset_y + r['y'].get()
                    
                    monitor = {
                        'top': global_top, 
                        'left': global_left, 
                        'width': r['w'].get(), 
                        'height': r['h'].get()
                    }
                    
                    if monitor['width'] == 0 or monitor['height'] == 0: continue
                    
                    sct_img = self.sct.grab(monitor)
                    img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
                    captured_images.append(img)

                z = self.zoom.get()

                if self.separate.get():
                    for i, img in enumerate(captured_images):
                        if i < len(self.mirror_windows):
                            win, lbl = self.mirror_windows[i]
                            new_size = (int(img.width * z), int(img.height * z))
                            final_img = img.resize(new_size, Image.NEAREST)
                            photo = ImageTk.PhotoImage(final_img)
                            lbl.config(image=photo)
                            lbl.image = photo
                            win.geometry(f"{new_size[0]}x{new_size[1]}")
                else:
                    if captured_images:
                        total_w = sum(img.width for img in captured_images) + (10 * (len(captured_images)-1))
                        max_h = max(img.height for img in captured_images)
                        
                        combined = Image.new('RGB', (total_w, max_h), (0,0,0))
                        current_x = 0
                        for img in captured_images:
                            combined.paste(img, (current_x, 0))
                            current_x += img.width + 10
                        
                        win, lbl = self.mirror_windows[0]
                        new_size = (int(total_w * z), int(max_h * z))
                        final_img = combined.resize(new_size, Image.NEAREST)
                        photo = ImageTk.PhotoImage(final_img)
                        lbl.config(image=photo)
                        lbl.image = photo
                        win.geometry(f"{new_size[0]}x{new_size[1]}")

            except Exception as e:
                print(f"Error: {e}")

        delay = int(1000 / max(1, self.fps.get()))
        if self.running_thread:
            self.root.after(delay, self.update_mirror_loop)

    def show_mirrors(self):
        for win, _ in self.mirror_windows:
            win.deiconify()

    def hide_mirrors(self):
        for win, _ in self.mirror_windows:
            win.withdraw()

    def set_running(self):
        self.mode = "RUNNING"
        self.root.withdraw()
        self.show_mirrors()

    def set_setup(self):
        self.mode = "SETUP"
        self.root.deiconify()
        self.hide_mirrors()

    def set_preview(self):
        self.mode = "PREVIEW"
        self.root.deiconify()
        self.show_mirrors()

    def load_settings(self):
        if os.path.exists(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, 'r') as f:
                    return json.load(f)
            except:
                return {}
        return {}

    def quit_app(self):
        data = {
            'zoom': self.zoom.get(),
            'fps': self.fps.get(),
            'separate': self.separate.get(),
            'monitor_idx': self.current_mon_idx
        }
        for i, r in enumerate(self.regions):
            data[f'r{i+1}_x'] = r['x'].get()
            data[f'r{i+1}_y'] = r['y'].get()
            data[f'r{i+1}_w'] = r['w'].get()
            data[f'r{i+1}_h'] = r['h'].get()
            data[f'r{i+1}_on'] = r['on'].get()

        with open(SETTINGS_FILE, 'w') as f:
            json.dump(data, f)
        
        self.running_thread = False
        self.root.destroy()
        os._exit(0)

if __name__ == "__main__":
    app = BuffMirrorApp()

    keyboard.add_hotkey('f1', lambda: app.root.after(0, app.set_running))
    keyboard.add_hotkey('f2', lambda: app.root.after(0, app.set_setup))
    keyboard.add_hotkey('f3', lambda: app.root.after(0, app.set_preview))
    keyboard.add_hotkey('f4', lambda: app.root.after(0, app.quit_app))

    app.root.mainloop()