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
        self.root.geometry("500x950")
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
        self.regions = []

        loaded_data = self.load_settings()
        
        self.fps = tk.IntVar(value=loaded_data.get('fps', 30))
        self.separate = tk.BooleanVar(value=loaded_data.get('separate', False))
        idx = loaded_data.get('monitor_idx', 0)
        
        if 0 <= idx < len(self.monitors):
            self.current_mon_idx = idx
            self.update_monitor_vars(self.current_mon_idx)

        self.key_vars = {
            'run': tk.StringVar(value=loaded_data.get('key_run', 'f1')),
            'setup': tk.StringVar(value=loaded_data.get('key_setup', 'f2')),
            'preview': tk.StringVar(value=loaded_data.get('key_preview', 'f3')),
            'quit': tk.StringVar(value=loaded_data.get('key_quit', 'f4'))
        }
        
        self.active_keys = {
            'run': self.key_vars['run'].get(),
            'setup': self.key_vars['setup'].get(),
            'preview': self.key_vars['preview'].get(),
            'quit': self.key_vars['quit'].get()
        }

        self.actions = {
            'run': lambda: self.root.after(0, self.set_running),
            'setup': lambda: self.root.after(0, self.set_setup),
            'preview': lambda: self.root.after(0, self.set_preview),
            'quit': lambda: self.root.after(0, self.quit_app)
        }

        self.separate.trace_add('write', self.rebuild_mirrors_callback)

        self.overlay = tk.Toplevel(self.root)
        self.overlay.attributes('-alpha', 0.5, '-topmost', True, '-transparentcolor', '#000001')
        self.overlay.overrideredirect(True)
        self.overlay_canvas = tk.Canvas(self.overlay, bg='#000001', highlightthickness=0)
        self.overlay_canvas.pack(fill="both", expand=True)

        self.create_main_layout()
        
        saved_regions = loaded_data.get('regions', [])
        if saved_regions:
            for r_data in saved_regions:
                self.add_region_ui(r_data)
        else:
            self.add_region_ui({'x': 100, 'y': 100, 'w': 200, 'h': 50, 'on': True, 'zoom': 2.0})
            self.add_region_ui({'x': 350, 'y': 100, 'w': 50,  'h': 50, 'on': True, 'zoom': 2.0})

        self.update_overlay_geometry()
        self.apply_hotkeys_on_start()
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
        for r in self.regions:
            if r['scale_x']: r['scale_x'].configure(to=self.screen_width)
            if r['scale_y']: r['scale_y'].configure(to=self.screen_height)

    def on_monitor_change(self, event):
        idx = self.monitor_combo.current()
        if idx >= 0:
            self.current_mon_idx = idx
            self.update_monitor_vars(idx)
            self.update_overlay_geometry()

    def create_main_layout(self):
        top_frame = tk.Frame(self.root)
        top_frame.pack(fill="x", padx=5, pady=5)

        mon_frame = tk.Frame(top_frame)
        mon_frame.pack(fill="x", pady=2)
        tk.Label(mon_frame, text="Select Monitor:").pack(side="left")
        mon_names = [f"Monitor {i+1} ({m['width']}x{m['height']})" for i, m in enumerate(self.monitors)]
        self.monitor_combo = ttk.Combobox(mon_frame, values=mon_names, state="readonly")
        self.monitor_combo.current(self.current_mon_idx)
        self.monitor_combo.pack(side="left", fill="x", expand=True, padx=5)
        self.monitor_combo.bind("<<ComboboxSelected>>", self.on_monitor_change)

        kb_frame = ttk.LabelFrame(top_frame, text="Keybinds (Press Enter to Apply)")
        kb_frame.pack(fill="x", pady=5)
        self.create_kb_row(kb_frame, "Run:", "run")
        self.create_kb_row(kb_frame, "Setup:", "setup")
        self.create_kb_row(kb_frame, "Preview:", "preview")
        self.create_kb_row(kb_frame, "Quit:", "quit")

        set_frame = ttk.LabelFrame(top_frame, text="Global Settings")
        set_frame.pack(fill="x", pady=5)
        ttk.Label(set_frame, text="FPS:").pack(side="left", padx=5)
        ttk.Spinbox(set_frame, from_=1, to=144, textvariable=self.fps, width=5).pack(side="left")
        ttk.Checkbutton(set_frame, text="Separate Windows", variable=self.separate).pack(side="right", padx=5)

        self.canvas_frame = tk.Frame(self.root)
        self.canvas_frame.pack(fill="both", expand=True, padx=5)

        self.canvas = tk.Canvas(self.canvas_frame, borderwidth=0, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(self.canvas_frame, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = tk.Frame(self.canvas)

        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )

        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw", width=460)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)

        btn_frame = tk.Frame(self.root, pady=5)
        btn_frame.pack(fill="x")
        ttk.Button(btn_frame, text="+ Add New Region", command=lambda: self.add_region_ui(None)).pack(fill="x", padx=10)
        tk.Label(self.root, text="discord - spctrl, Roblox - 45LEGEND_X", font=("Arial", 8), fg="gray").pack(pady=2)

    def _on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-1*(event.delta/120)), "units")

    def create_kb_row(self, parent, label_text, var_name):
        row = tk.Frame(parent)
        row.pack(fill="x", pady=2, padx=5)
        tk.Label(row, text=label_text, width=10, anchor="w").pack(side="left")
        entry = ttk.Entry(row, textvariable=self.key_vars[var_name])
        entry.pack(side="right", fill="x", expand=True)
        entry.bind('<Return>', lambda e, name=var_name: self.update_single_hotkey(name, entry))
        entry.bind('<FocusOut>', lambda e, name=var_name: self.update_single_hotkey(name, entry))

    def add_region_ui(self, data=None):
        if data is None:
            data = {'x': 100, 'y': 100, 'w': 100, 'h': 50, 'on': True, 'zoom': 2.0}

        r_vars = {
            'x': tk.IntVar(value=data['x']),
            'y': tk.IntVar(value=data['y']),
            'w': tk.IntVar(value=data['w']),
            'h': tk.IntVar(value=data['h']),
            'on': tk.BooleanVar(value=data['on']),
            'zoom': tk.DoubleVar(value=data['zoom']),
            'scale_x': None,
            'scale_y': None,
            'ui_frame': None
        }
        
        r_vars['on'].trace_add('write', self.rebuild_mirrors_callback)
        
        lf = ttk.LabelFrame(self.scrollable_frame, text="", padding=2)
        lf.pack(fill="x", pady=3, padx=2)
        r_vars['ui_frame'] = lf

        header = tk.Frame(lf)
        header.pack(fill="x", pady=0)
        
        cb = ttk.Checkbutton(header, text="Enable", variable=r_vars['on'])
        cb.pack(side="left")

        btn_del = ttk.Button(header, text="X", width=3, command=lambda: self.remove_region(r_vars))
        btn_del.pack(side="right", padx=2)

        is_minimized = [False] 
        content_frame = tk.Frame(lf)
        
        def toggle_minimize():
            if is_minimized[0]:
                content_frame.pack(fill="x", pady=2)
                btn_min.config(text="[-]")
                is_minimized[0] = False
            else:
                content_frame.pack_forget()
                btn_min.config(text="[+]")
                is_minimized[0] = True

        btn_min = ttk.Button(header, text="[-]", width=3, command=toggle_minimize)
        btn_min.pack(side="right", padx=2)

        content_frame.pack(fill="x", pady=2)

        r_vars['scale_x'] = self.make_slider(content_frame, "X", r_vars['x'], self.screen_width)
        r_vars['scale_y'] = self.make_slider(content_frame, "Y", r_vars['y'], self.screen_height)
        self.make_slider(content_frame, "W", r_vars['w'], 800)
        self.make_slider(content_frame, "H", r_vars['h'], 300)
        self.make_zoom_slider(content_frame, "Zoom", r_vars['zoom'])

        self.regions.append(r_vars)
        self.refresh_region_titles()
        self.rebuild_mirrors_callback()

    def remove_region(self, region_dict):
        if region_dict['ui_frame']:
            region_dict['ui_frame'].destroy()
        
        if region_dict in self.regions:
            self.regions.remove(region_dict)
        
        self.refresh_region_titles()
        self.rebuild_mirrors_callback()

    def refresh_region_titles(self):
        for i, r in enumerate(self.regions):
            if r['ui_frame']:
                r['ui_frame'].configure(text=f"Region {i+1}")

    def make_slider(self, parent, label, var, max_val):
        frame = ttk.Frame(parent)
        frame.pack(fill="x", padx=2, pady=1)
        ttk.Label(frame, text=label, width=2).pack(side="left")
        scale = ttk.Scale(frame, from_=0, to=max_val, variable=var, orient='horizontal')
        scale.pack(side="left", fill="x", expand=True)
        ttk.Entry(frame, textvariable=var, width=5).pack(side="right")
        return scale

    def make_zoom_slider(self, parent, label, var):
        frame = ttk.Frame(parent)
        frame.pack(fill="x", padx=2, pady=1)
        ttk.Label(frame, text=label, width=5).pack(side="left")
        scale = ttk.Scale(frame, from_=1.0, to=5.0, variable=var, orient='horizontal')
        scale.pack(side="left", fill="x", expand=True)
        ttk.Entry(frame, textvariable=var, width=5).pack(side="right")
        return scale

    def apply_hotkeys_on_start(self):
        for name, key in self.active_keys.items():
            try:
                keyboard.add_hotkey(key, self.actions[name])
            except Exception as e:
                print(f"Failed to bind {key}: {e}")

    def update_single_hotkey(self, name, entry_widget):
        new_key = self.key_vars[name].get().strip().lower()
        old_key = self.active_keys[name]

        if new_key == old_key: return
        if not new_key:
            self.key_vars[name].set(old_key)
            return

        try:
            try:
                keyboard.remove_hotkey(old_key)
            except:
                pass

            keyboard.add_hotkey(new_key, self.actions[name])
            self.active_keys[name] = new_key
            entry_widget.configure(foreground='black')
        except ValueError:
            try:
                keyboard.add_hotkey(old_key, self.actions[name])
            except:
                pass
            self.key_vars[name].set(old_key)
            entry_widget.configure(foreground='red')
            self.root.after(1000, lambda: entry_widget.configure(foreground='black'))

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
            
            for i, r in enumerate(self.regions):
                if r['on'].get():
                    x, y = r['x'].get(), r['y'].get()
                    w, h = r['w'].get(), r['h'].get()
                    
                    self.overlay_canvas.create_rectangle(x, y, x+w, y+h, outline='black', width=5)
                    self.overlay_canvas.create_rectangle(x, y, x+w, y+h, outline='white', width=2)
                    
                    txt = f"R{i+1}"
                    font_spec = ("Arial", 10, "bold")
                    tx, ty = x, y-18
                    for ox, oy in [(-1, -1), (-1, 1), (1, -1), (1, 1)]:
                        self.overlay_canvas.create_text(tx+ox, ty+oy, text=txt, fill='black', font=font_spec, anchor="nw")
                    self.overlay_canvas.create_text(tx, ty, text=txt, fill='white', font=font_spec, anchor="nw")
        else:
            self.overlay.withdraw()
            
        if self.running_thread:
            self.root.after(50, self.update_overlay_loop)

    def update_mirror_loop(self):
        if self.mode in ["RUNNING", "PREVIEW"] and self.mirror_windows:
            try:
                active_regions = [r for r in self.regions if r['on'].get()]
                captured_data = [] 
                
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
                    captured_data.append((img, r['zoom'].get()))

                if self.separate.get():
                    for i, (img, z) in enumerate(captured_data):
                        if i < len(self.mirror_windows):
                            win, lbl = self.mirror_windows[i]
                            new_size = (int(img.width * z), int(img.height * z))
                            final_img = img.resize(new_size, Image.NEAREST)
                            photo = ImageTk.PhotoImage(final_img)
                            lbl.config(image=photo)
                            lbl.image = photo
                            win.geometry(f"{new_size[0]}x{new_size[1]}")
                else:
                    if captured_data:
                        resized_images = []
                        total_w = 0
                        max_h = 0
                        
                        for img, z in captured_data:
                            nw = int(img.width * z)
                            nh = int(img.height * z)
                            resized = img.resize((nw, nh), Image.NEAREST)
                            resized_images.append(resized)
                            total_w += nw + 10
                            if nh > max_h: max_h = nh
                        
                        total_w -= 10
                        
                        combined = Image.new('RGB', (total_w, max_h), (0,0,0))
                        current_x = 0
                        for r_img in resized_images:
                            combined.paste(r_img, (current_x, 0))
                            current_x += r_img.width + 10
                        
                        win, lbl = self.mirror_windows[0]
                        photo = ImageTk.PhotoImage(combined)
                        lbl.config(image=photo)
                        lbl.image = photo
                        win.geometry(f"{total_w}x{max_h}")

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
            'fps': self.fps.get(),
            'separate': self.separate.get(),
            'monitor_idx': self.current_mon_idx,
            'key_run': self.active_keys['run'],
            'key_setup': self.active_keys['setup'],
            'key_preview': self.active_keys['preview'],
            'key_quit': self.active_keys['quit'],
            'regions': []
        }
        for r in self.regions:
            data['regions'].append({
                'x': r['x'].get(),
                'y': r['y'].get(),
                'w': r['w'].get(),
                'h': r['h'].get(),
                'on': r['on'].get(),
                'zoom': r['zoom'].get()
            })

        with open(SETTINGS_FILE, 'w') as f:
            json.dump(data, f)
        
        self.running_thread = False
        self.root.destroy()
        os._exit(0)

if __name__ == "__main__":
    app = BuffMirrorApp()
    app.root.mainloop()
