"""
Video Tab Module
Handles video generation from selected images using either Wan or LTX ComfyUI workflows.
Integrated into main_ui.py via the Video tab notebook.
"""
import os
import json
import random
import string
import threading
import time
import csv
import requests
import tkinter as tk
from tkinter import ttk, filedialog
from tkinter import scrolledtext
from PIL import Image, ImageTk
from pathlib import Path


class VideoTabUI:
    """Video generation tab UI with Wan/LTX workflow support."""
    
    def _mu(self):
        """Lazy import main_ui module to avoid circular import."""
        import main_ui
        return main_ui
    
    def _c(self):
        """Get constants from main_ui lazily."""
        mu = self._mu()
        return {
            "COMFYUI_URL": mu.COMFYUI_URL,
            "COMFYUI_ROOT": mu.COMFYUI_ROOT,
            "INPUT_FOLDER": mu.INPUT_FOLDER,
            "OUTPUT_FOLDER": mu.OUTPUT_FOLDER,
            "WORKFLOW_TEMPLATE_DIR": mu.WORKFLOW_TEMPLATE_DIR,
            "LTX_WORKFLOW_DIR": mu.LTX_WORKFLOW_DIR,
            "VIDEO_OUTPUT_FOLDER": mu.VIDEO_OUTPUT_FOLDER,
            "STATE_FILE": mu.VIDEO_STATE_FILE,
            "TASK_STEPS_CSV": mu.TASK_STEPS_CSV,
            "AUDIO_PROMPT_TSV": mu.AUDIO_PROMPT_TSV,
            "TemplateCatalog": mu.TemplateCatalog,
            "StreamChunk": mu.StreamChunk,
            "generate_api_workflow": mu.generate_api_workflow,
        }
    
    def __init__(self, parent_notebook, root):
        self.root = root
        # If parent_notebook is a Notebook (has .add()), create a new tab.
        # If it's a Frame, use it directly as the container.
        if hasattr(parent_notebook, 'add'):
            self.tab = tk.Frame(parent_notebook)
            parent_notebook.add(self.tab, text="Video")
        else:
            self.tab = parent_notebook
        
        self.rows = []
        self.cancel_event = threading.Event()
        self.is_running = False
        
        # LTX-style parameter variables
        self.video_engine_var = tk.StringVar(value="LTX")
        self.resolution_var = tk.StringVar(value="1280*720")
        self.sec_var = tk.StringVar(value="10")
        self.fps_var = tk.StringVar(value="24")
        self.batch_var = tk.StringVar(value="1")
 
        self.video_length_var = tk.StringVar(value="241")
        self.lang_var = tk.StringVar(value="Chinese")
        self.task_type_var = tk.StringVar(value="wan2.2")
        
        # State
        self._save_state_timer = None
        
        self._build_ui()
        self._load_state()
        
        # Populate dropdowns
        self._populate_task_types()
    
    def _build_ui(self):
        """Build the Video tab UI layout."""
        # --- Top Action Bar ---
        top_frame = tk.Frame(self.tab)
        top_frame.pack(fill=tk.X, pady=(5, 5), padx=5)
        
        # Engine selector
        tk.Label(top_frame, text="Engine:").pack(side=tk.LEFT, padx=(0, 5))
        engine_dd = ttk.Combobox(top_frame, textvariable=self.video_engine_var, state="readonly", width=10)
        engine_dd['values'] = ("LTX", "WAN")
        engine_dd.pack(side=tk.LEFT, padx=5)
        engine_dd.bind("<<ComboboxSelected>>", self._on_engine_change)
        
        tk.Label(top_frame, text="Task:").pack(side=tk.LEFT, padx=(15, 5))
        self.task_type_dropdown = ttk.Combobox(top_frame, state="readonly", width=35)
        self.task_type_dropdown.pack(side=tk.LEFT, padx=5)
        
        tk.Button(top_frame, text="Run", command=self.start_video_generation, width=10).pack(side=tk.LEFT, padx=5)
        tk.Button(top_frame, text="Cancel", command=self.cancel_generation, width=10).pack(side=tk.LEFT, padx=5)
        tk.Button(top_frame, text="Clear All", command=self.clear_all_rows, width=10).pack(side=tk.LEFT, padx=5)
        
        # Status
        self.status_var = tk.StringVar(value="Ready")
        tk.Label(top_frame, textvariable=self.status_var, font=('Helvetica', 10, 'bold')).pack(side=tk.RIGHT, padx=10)
        
        # --- Settings Row (LTX-style parameters) ---
        settings_frame = tk.Frame(self.tab)
        settings_frame.pack(fill=tk.X, pady=(2, 5), padx=5)
        
        tk.Label(settings_frame, text="Width:").pack(side=tk.LEFT, padx=(5, 2))
        self.width_entry = tk.Entry(settings_frame, textvariable=self.resolution_var, width=8)
        self.width_entry.pack(side=tk.LEFT, padx=5)
        
        tk.Label(settings_frame, text="SEC:").pack(side=tk.LEFT, padx=(5, 2))
        self.sec_entry = tk.Entry(settings_frame, textvariable=self.sec_var, width=5)
        self.sec_entry.pack(side=tk.LEFT, padx=5)
        
        tk.Label(settings_frame, text="FPS:").pack(side=tk.LEFT, padx=(5, 2))
        self.fps_entry = tk.Entry(settings_frame, textvariable=self.fps_var, width=5)
        self.fps_entry.pack(side=tk.LEFT, padx=5)
        
        tk.Label(settings_frame, text="Len:").pack(side=tk.LEFT, padx=(5, 2))
        self.length_entry = tk.Entry(settings_frame, textvariable=self.video_length_var, width=5)
        self.length_entry.pack(side=tk.LEFT, padx=5)
        
        tk.Label(settings_frame, text="Batch:").pack(side=tk.LEFT, padx=(10, 2))
        self.batch_entry = tk.Entry(settings_frame, textvariable=self.batch_var, width=5)
        self.batch_entry.pack(side=tk.LEFT, padx=5)
        
        self.upscale_var = tk.BooleanVar(value=False)
        tk.Checkbutton(settings_frame, text="Up", var=self.upscale_var).pack(side=tk.LEFT, padx=5)
        
        # --- Image Selection Area ---
        btn_row = tk.Frame(self.tab)
        btn_row.pack(fill=tk.X, pady=(2, 5), padx=5)
        
        tk.Button(btn_row, text="Add Images", command=self.add_images_from_file, width=15).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_row, text="Load Task.json", command=self.load_from_task_json, width=15).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_row, text="Browse Output", command=self.browse_output_images, width=15).pack(side=tk.LEFT, padx=5)
        tk.Label(btn_row, text="← Images →", font=('Helvetica', 8), fg='#666666').pack(side=tk.LEFT, padx=(10, 0))
        
        # --- Scrollable Row Area ---
        list_frame = tk.Frame(self.tab)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.canvas = tk.Canvas(list_frame)
        self.scrollbar = tk.Scrollbar(list_frame, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = tk.Frame(self.canvas)
        self.scrollable_frame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas_window = self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")
        
        # Mouse wheel support
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        self.scrollable_frame.bind_all("<MouseWheel>", self._on_mousewheel)
        
        # --- Log Window ---
        self.video_log_window = scrolledtext.ScrolledText(self.tab, height=10, state='disabled')
        self.video_log_window.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Queue for log processing
        self.video_log_queue = []
        self.root.after(100, self._process_video_log_queue)
    
    def _on_engine_change(self, event=None):
        """Toggle settings based on Wan/LTX engine selection."""
        engine = self.video_engine_var.get()
        self.task_type_dropdown.pack(side=tk.LEFT, padx=(5, 5))
        if engine == "WAN":
            self.task_type_dropdown.config(state="readonly")
        else:
            self.task_type_dropdown.config(state="disabled")
    
    def _populate_task_types(self):
        """Load task types from CSV for Wan video generation."""
        c = self._c()
        try:
            with open(c["TASK_STEPS_CSV"], mode='r', encoding='utf-8') as f:
                reader = csv.reader(f)
                next(reader, None)  # skip header
                task_names = sorted(list(set(row[0].strip() for row in reader if row)))
            if task_names:
                self.task_type_dropdown['values'] = task_names
                default_task = 'wan2.2' if 'wan2.2' in task_names else task_names[0]
                self.task_type_var.set(default_task)
        except Exception:
            pass
    
    def _on_canvas_configure(self, event):
        self.canvas.itemconfig(self.canvas_window, width=event.width)
    
    def _on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
    
    def _process_video_log_queue(self):
        """Process the log queue and display in the log window."""
        if not self.video_log_queue:
            self.root.after(100, self._process_video_log_queue)
            return
        
        self.video_log_window.configure(state='normal')
        while self.video_log_queue:
            item = self.video_log_queue.pop(0)
            if isinstance(item, self._mu().StreamChunk):
                self.video_log_window.insert(tk.END, item.content)
            else:
                self.video_log_window.insert(tk.END, str(item) + "\n")
        content = self.video_log_window.get("1.0", tk.END)
        lines = content.count('\n')
        if lines > 2000:
            self.video_log_window.delete("1.0", f"{lines - 1000}.0")
        self.video_log_window.configure(state='disabled')
        self.video_log_window.see(tk.END)
        
        self.root.after(100, self._process_video_log_queue)
    
    def video_log(self, message):
        """Log a message to the video tab log."""
        self.video_log_queue.append(message)
    
    def add_images_from_file(self):
        """Open file dialog to select images."""
        c = self._c()
        paths = filedialog.askopenfilenames(
            title="Select Images",
            filetypes=[("Images", "*.png *.jpg *.jpeg *.gif *.bmp"), ("All", "*.*")],
            initialdir=c["OUTPUT_FOLDER"] if os.path.exists(c["OUTPUT_FOLDER"]) else os.getcwd()
        )
        if paths:
            import shutil
            for path in paths:
                try:
                    filename = os.path.basename(path)
                    filename_base = os.path.splitext(filename)[0]
                    dest = os.path.join(c["INPUT_FOLDER"], filename)
                    if not os.path.exists(dest) or not os.path.samefile(path, dest):
                        os.makedirs(os.path.dirname(dest), exist_ok=True)
                        shutil.copy2(path, dest)
                    img = Image.open(dest)
                    self.add_row(image_path=dest, image=img, filename_base=filename_base)
                except Exception as e:
                    self.video_log(f"Error adding image {path}: {e}")
    
    def load_from_task_json(self):
        """Load images and video prompts from a task.json file."""
        c = self._c()
        task_path = filedialog.askopenfilename(
            title="Select task.json",
            filetypes=[("JSON", "*.json")],
            initialdir=os.path.join(os.getcwd(), "tasks")
        )
        if not task_path:
            return
        
        try:
            with open(task_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            self.video_log(f"Error loading task.json: {e}")
            return
        
        locations = data.get('location_design', {}).get('locations', [])
        output_dir = os.path.join(os.getcwd(), "output_images")
        os.makedirs(output_dir, exist_ok=True)
        
        import shutil
        for loc in locations:
            loc_name = loc.get('location', 'Unknown')
            for p_idx, prompt in enumerate(loc.get('prompts', [])):
                video_prompt_data = prompt.get('video_prompt', {})
                
                # Construct video prompt string
                video_prompt = ""
                if isinstance(video_prompt_data, dict):
                    video_prompt = video_prompt_data.get('action', '')
                    line = video_prompt_data.get('line', '')
                    sound = video_prompt_data.get('female_character_sound', '')
                    audio = video_prompt_data.get('audio', '')
                    if line:
                        if video_prompt: video_prompt += "\n"
                        video_prompt += f"She says: {line}"
                    if sound:
                        if video_prompt: video_prompt += "\n"
                        video_prompt += f"Sound: {sound}"
                    if audio:
                        if video_prompt: video_prompt += "\n"
                        video_prompt += f"Audio: {audio}"
                
                # Look for corresponding image file
                scene_idx = locations.index(loc)
                filename_base = f"{loc_name}_scene{scene_idx}_p{p_idx}"
                
                # Try to find the image
                image_path = None
                for ext in ['.png', '.jpg', '.jpeg']:
                    candidate = os.path.join(output_dir, filename_base + ext)
                    if os.path.exists(candidate):
                        image_path = candidate
                        break
                
                if image_path and os.path.exists(image_path):
                    try:
                        # Copy to input folder for ComfyUI
                        dest = os.path.join(c["INPUT_FOLDER"], os.path.basename(image_path))
                        if not os.path.exists(dest) or not os.path.samefile(image_path, dest):
                            shutil.copy2(image_path, dest)
                            
                        img = Image.open(dest)
                        self.add_row(
                            image_path=dest,
                            image=img,
                            video_prompt=video_prompt,
                            filename_base=filename_base
                        )
                    except:
                        pass
    
    def browse_output_images(self):
        """Open file explorer to the output_images folder."""
        import subprocess
        output_dir = os.path.join(os.getcwd(), "output_images")
        if os.path.exists(output_dir):
            subprocess.Popen(['explorer', output_dir])
        else:
            self.video_log("Output images folder not found.")
    
    def _load_lora_lookup(self):
        """Load sex acts from lora_lookup.csv for validation."""
        c = self._c()
        sex_acts = set()
        try:
            with open("lookup/lora_lookup.csv", mode='r', encoding='utf-8') as f:
                reader = csv.reader(f)
                header = next(reader, None)
                if header:
                    try:
                        tag1_idx = header.index('tag1')
                        tag2_idx = header.index('tag2')
                        type_idx = header.index('type')
                    except ValueError:
                        tag1_idx, tag2_idx, type_idx = 0, 1, 2
                    
                    for row in reader:
                        if len(row) > max(tag1_idx, tag2_idx, type_idx):
                            if row[type_idx].strip().lower() == 'video':
                                if row[tag1_idx]: sex_acts.add(row[tag1_idx].strip())
                                if row[tag2_idx]: sex_acts.add(row[tag2_idx].strip())
        except Exception as e:
            self.video_log(f"Error loading LoRA lookup: {e}")
        return sex_acts

    def add_row(self, image=None, is_empty=False, state=None, image_path=None, video_prompt="", filename_base="", sex_act=""):
        """Add a row to the scrollable list for an image."""
        c = self._c()
        row_frame = tk.Frame(self.scrollable_frame, borderwidth=2, relief="sunken")
        row_frame.pack(fill=tk.X, padx=5, pady=5)
        
        thumb_label = tk.Label(row_frame)
        thumb_label.pack(side=tk.LEFT, padx=5, pady=5)
        
        if state:
            current_image_path = state.get("image_path", "")
            filename_base = state.get("filename_base", "")
            if not filename_base and current_image_path:
                filename_base = os.path.splitext(os.path.basename(current_image_path))[0]
            
            video_prompt_val = state.get("video_prompt", "")
            sex_act_val = state.get("sex_act", "")
            seconds_val = state.get("seconds", "6")
            width_val = state.get("width", "1024")
            upscale_val = state.get("upscale", False)
            batch_val = state.get("batch", "1")
        else:
            if image_path:
                current_image_path = image_path
                if not filename_base:
                    filename_base = os.path.splitext(os.path.basename(image_path))[0]
            else:
                filename_base = filename_base or ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
                current_image_path = os.path.join(c["INPUT_FOLDER"], f"{filename_base}.png")
            
            video_prompt_val = video_prompt if video_prompt else ""
            sex_act_val = sex_act
            
            if current_image_path and os.path.exists(current_image_path):
                metadata = self._get_metadata_from_image(current_image_path)
                if not video_prompt_val:
                    video_prompt_val = self._format_video_prompt(metadata)
                if not sex_act_val:
                    sex_act_val = metadata.get("sex_act", "")
            
            seconds_val = self.sec_var.get()
            width_val = self.resolution_var.get()
            if not width_val.isdigit():
                width_val = "1280"
            upscale_val = self.upscale_var.get()
            batch_val = self.batch_var.get()
        
        if current_image_path and os.path.exists(current_image_path):
            try:
                img = Image.open(current_image_path)
                img.thumbnail((100, 100))
                photo = ImageTk.PhotoImage(img)
                thumb_label.config(image=photo)
                thumb_label.image = photo
            except:
                pass
        
        info_frame = tk.Frame(row_frame)
        info_frame.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        info_frame.grid_columnconfigure(1, weight=1)
        
        tk.Label(info_frame, text="File Name:").grid(row=0, column=0, sticky=tk.W)
        fn_ent = tk.Entry(info_frame)
        fn_ent.insert(0, os.path.basename(current_image_path) if current_image_path else "")
        fn_ent.config(state='readonly')
        fn_ent.grid(row=0, column=1, sticky=tk.EW)
        
        tk.Label(info_frame, text="Sex Act:").grid(row=1, column=0, sticky=tk.W)
        sa_ent = tk.Entry(info_frame)
        sa_ent.insert(0, sex_act_val)
        sa_ent.grid(row=1, column=1, sticky=tk.EW)
        
        # Color coding for sex act
        valid_sex_acts = self._load_lora_lookup()
        def validate_sa(*args):
            val = sa_ent.get().strip()
            if val in valid_sex_acts:
                sa_ent.config(bg="#ccffcc") # Light green
            else:
                sa_ent.config(bg="#ffcccc") # Light red
            self._schedule_save_state()

        sa_ent.bind("<KeyRelease>", validate_sa)
        validate_sa()

        tk.Label(info_frame, text="Video Prompt:").grid(row=2, column=0, sticky=tk.W)
        vp_ent = tk.Entry(info_frame)
        vp_ent.insert(0, video_prompt_val)
        vp_ent.grid(row=2, column=1, sticky=tk.EW)
        vp_ent.bind("<KeyRelease>", self._schedule_save_state)
        tk.Button(info_frame, text="...", command=lambda: self._edit_long_text(vp_ent)).grid(row=2, column=2)
        
        params_row = tk.Frame(info_frame)
        params_row.grid(row=3, column=0, columnspan=3, sticky=tk.W)
        
        tk.Label(params_row, text="Sec:").pack(side=tk.LEFT)
        sec_ent = tk.Entry(params_row, width=5)
        sec_ent.insert(0, seconds_val)
        sec_ent.pack(side=tk.LEFT, padx=(0, 10))
        sec_ent.bind("<KeyRelease>", self._schedule_save_state)
        
        tk.Label(params_row, text="Width:").pack(side=tk.LEFT)
        width_ent = tk.Entry(params_row, width=8)
        width_ent.insert(0, width_val)
        width_ent.pack(side=tk.LEFT, padx=(0, 10))
        width_ent.bind("<KeyRelease>", self._schedule_save_state)
        
        tk.Label(params_row, text="Batch:").pack(side=tk.LEFT)
        batch_ent = tk.Entry(params_row, width=5)
        batch_ent.insert(0, batch_val)
        batch_ent.pack(side=tk.LEFT)
        batch_ent.bind("<KeyRelease>", self._schedule_save_state)
        
        ctrl_frame = tk.Frame(row_frame)
        ctrl_frame.pack(side=tk.RIGHT, padx=5)
        
        up_var = tk.BooleanVar(value=upscale_val)
        tk.Checkbutton(ctrl_frame, text="Up", var=up_var, command=self._schedule_save_state).pack(anchor=tk.W)
        
        tk.Button(ctrl_frame, text="Del", command=lambda: self.delete_row(row_frame)).pack()
        
        row_data = {
            "frame": row_frame,
            "image_path": current_image_path,
            "filename_base": filename_base,
            "filename": fn_ent,
            "sex_act": sa_ent,
            "video_prompt": vp_ent,
            "seconds": sec_ent,
            "width": width_ent,
            "upscale": up_var,
            "batch": batch_ent
        }
        self.rows.append(row_data)
        self._schedule_save_state()
        self.root.after(100, lambda: self.canvas.yview_moveto(1.0))

    def _get_metadata_from_image(self, image_path):
        """Extract metadata dictionary from PNG."""
        try:
            from PIL import Image as PILImage
            img = PILImage.open(image_path)
            metadata_str = img.info.get("prompt", "") if img.info else ""
            if not metadata_str:
                return {}
            import json
            return json.loads(metadata_str)
        except:
            return {}

    def _format_video_prompt(self, metadata):
        """Format video prompt from metadata dict."""
        video_prompt_data = metadata.get("video_prompt", {})
        if isinstance(video_prompt_data, dict):
            action = video_prompt_data.get("action", "")
            line = video_prompt_data.get("line", "")
            female_sound = video_prompt_data.get("female_character_sound", "")
            audio = video_prompt_data.get("audio", "")
        else:
            action = video_prompt_data
            line = metadata.get("line", "")
            female_sound = metadata.get("female_character_sound", "")
            audio = metadata.get("audio", "")
        
        result = action
        if line:
            if result: result += "\n"
            result += "She says: " + line
        if female_sound:
            if result: result += "\n"
            result += "Sound: " + female_sound
        if audio:
            if result: result += "\n"
            result += "Audio: " + audio
        return result
    
    def _get_video_prompt_from_image_metadata(self, image_path):
        """Extract video prompt from PNG metadata if available."""
        metadata = self._get_metadata_from_image(image_path)
        return self._format_video_prompt(metadata)

    def _edit_long_text(self, entry):
        """Open a dialog to edit long text fields."""
        dialog = tk.Toplevel(self.root)
        dialog.title("Edit Text")
        dialog.geometry("600x400")
        
        current_text = entry.get()
        text_widget = scrolledtext.ScrolledText(dialog, width=70, height=20)
        text_widget.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)
        text_widget.insert(tk.END, current_text)
        
        def save():
            entry.delete(0, tk.END)
            entry.insert(0, text_widget.get("1.0", tk.END))
            dialog.destroy()
        
        save_btn = tk.Button(dialog, text="Save", command=save, width=10)
        save_btn.pack(side=tk.RIGHT, padx=10, pady=10)
        
        cancel_btn = tk.Button(dialog, text="Cancel", command=dialog.destroy, width=10)
        cancel_btn.pack(side=tk.RIGHT, padx=(0, 10), pady=10)
    
    def delete_row(self, frame):
        """Delete a row from the scrollable list."""
        for i, r in enumerate(self.rows):
            if r["frame"] == frame:
                self.rows.pop(i)
                frame.destroy()
                self._schedule_save_state()
                break
    
    def clear_all_rows(self):
        """Clear all rows from the scrollable list."""
        if not self.is_running:
            for r in self.rows:
                r["frame"].destroy()
            self.rows.clear()
    
    def _schedule_save_state(self, *args):
        """Schedule saving state to avoid excessive writes."""
        if self._save_state_timer:
            self.root.after_cancel(self._save_state_timer)
        self._save_state_timer = self.root.after(500, self.save_state)
    
    def save_state(self):
        """Save the current state of all rows."""
        c = self._c()
        to_save = []
        for r in self.rows:
            to_save.append({
                "image_path": r["image_path"],
                "filename": r["filename"].get(),
                "filename_base": r["filename_base"],
                "sex_act": r["sex_act"].get(),
                "video_prompt": r["video_prompt"].get(),
                "seconds": r["seconds"].get(),
                "width": r["width"].get(),
                "upscale": r["upscale"].get(),
                "batch": r["batch"].get()
            })
        try:
            with open(c["STATE_FILE"], 'w', encoding='utf-8') as f:
                json.dump(to_save, f, indent=4)
        except:
            pass
    
    def _load_state(self):
        """Load saved state from file."""
        c = self._c()
        if not os.path.exists(c["STATE_FILE"]):
            return
        try:
            with open(c["STATE_FILE"], 'r', encoding='utf-8') as f:
                saved = json.load(f)
            for s in saved:
                self.add_row(state=s)
        except:
            pass
    
    def set_ui_state(self, is_running):
        """Set the UI state for running/stopped."""
        self.is_running = is_running
    
    def cancel_generation(self):
        """Cancel the current generation."""
        if self.is_running:
            self.video_log("--- Cancellation requested ---")
            self.cancel_event.set()
    
    def start_video_generation(self):
        """Start the video generation process."""
        if self.is_running:
            return
        
        if not self.rows:
            self.video_log("WARNING: No rows added.")
            return
        
        engine = self.video_engine_var.get()
        self.video_log(f"Starting {engine} video generation with {len(self.rows)} images...")
        
        self.cancel_event.clear()
        self.set_ui_state(True)
        self.status_var.set("Running")
        
        # Start background thread
        threading.Thread(
            target=self._run_video_generation_thread,
            args=(engine,),
            daemon=True
        ).start()
    
    def _run_video_generation_thread(self, engine):
        """Run the video generation thread."""
        try:
            if engine == "LTX":
                self._run_ltx_video_generation()
            elif engine == "WAN":
                self._run_wan_video_generation()
        except Exception as e:
            self.video_log(f"Error: {e}")
        finally:
            self.set_ui_state(False)
            self.status_var.set("Ready")
    
    def _run_ltx_video_generation(self):
        """Run LTX video generation for all rows."""
        c = self._c()

        self.video_log("Starting LTX video generation...")
        
        for i, row in enumerate(self.rows):
            if self.cancel_event.is_set():
                self.video_log("Batch cancelled.")
                return
            
            # Consolidate IDs: 
            # work_id = the specific sub-task ID (e.g. wg22j_scene0_p0)
            # job_id  = the overarching task ID (e.g. wg22j)
            work_id = row["filename_base"]
            current_image_path = row["image_path"]
            
            if not work_id and current_image_path:
                work_id = os.path.splitext(os.path.basename(current_image_path))[0]
            
            if not work_id:
                work_id = f"video_{i}_{random.randint(1000,9999)}"
            
            # Try to extract job_id from metadata if not already known
            job_id = ""
            if current_image_path and os.path.exists(current_image_path):
                metadata = self._get_metadata_from_image(current_image_path)
                job_id = metadata.get("job_id", "") or metadata.get("work_id", "").split('_')[0]
            
            if not job_id:
                job_id = work_id.split('_')[0] if '_' in work_id else work_id

            video_prompt = row["video_prompt"].get()
            
            self.video_log(f"Processing {i+1}/{len(self.rows)}: work_id={work_id}, job_id={job_id}")
            
           # Parse width, seconds and fps
            try:
                width = int(row["width"].get())
            except:
                width = 1280
            
            try:
                seconds = float(row["seconds"].get())
            except:
                seconds = 10.0
                
            try:
                fps = int(self.fps_var.get())
            except:
                fps = 24

            # Video length calculation: fps * sec + 1
            length = int(fps * seconds + 1)
            
            # Calculate height from image aspect ratio
            height = width  # default square
            if current_image_path and os.path.exists(current_image_path):
                try:
                    from PIL import Image as PILImage
                    pil_img = PILImage.open(current_image_path)
                    orig_w, orig_h = pil_img.size
                    height = int(width * orig_h / orig_w)
                except:
                    pass
            
            try:
                from projects.ltx.batch_runner import BatchRunner
                
                # Extract main action from video prompt (first line or first 50 chars)
                main_action = ""
                if video_prompt:
                    lines = video_prompt.split('\n')
                    main_action = lines[0][:50] if lines else ""
                
                # Build task from row
                tasks = [{
                    "work_id": work_id,
                    "prompt": video_prompt or row.get("image_path", ""),
                    "video_pos_prompt": video_prompt,
                    "negative_prompt": "ugly, deformed, bad quality",
                    "main_sex_act": main_action,
                    "scene_index": i,
                    "prompt_index": 0
                }]
                
                runner = BatchRunner(
                    comfyui_url=c["COMFYUI_URL"],
                    output_folder=c["OUTPUT_FOLDER"],
                    input_folder=c["INPUT_FOLDER"],
                    processed_folder=os.path.join(c["OUTPUT_FOLDER"], "processed"),
                    log_func=lambda msg: self.video_log(f"[LTX] {msg}")
                )
                
                result = runner.run_batch(
                    job_id=job_id,
                    tasks=tasks,
                    width=int(width),
                    height=int(height),
                    length=int(length),
                    fps=int(fps)
                )
                
                completed = len(result.get('completed', []))
                failed = len(result.get('failed', []))
                self.video_log(f"Completed {completed}, Failed {failed}")
                
            except Exception as e:
                self.video_log(f"Error for {work_id}: {e}")
    
    def _run_wan_video_generation(self):
        """Run Wan video generation for all rows."""
        self.video_log("Starting WAN video generation...")
        
        selected_task = getattr(self, 'task_type_var', None)
        if selected_task and hasattr(selected_task, 'get'):
            task_name = selected_task.get()
        else:
            task_name = "wan2.2"
        
        self.video_log(f"Using Wan task: {task_name}")
        
        # Get task steps
        task_steps = self._get_task_steps(task_name)
        if not task_steps:
            self.video_log(f"Warning: No task steps found for '{task_name}'")
            return
        
        for i, row in enumerate(self.rows):
            if self.cancel_event.is_set():
                self.video_log("Batch cancelled.")
                return
            
            work_id = row["filename_base"]
            current_image_path = row["image_path"]
            if not work_id and current_image_path:
                work_id = os.path.splitext(os.path.basename(current_image_path))[0]
            
            if not work_id:
                work_id = f"video_{i}_{random.randint(1000,9999)}"
                
            video_prompt = row["video_prompt"].get()
            
            self.video_log(f"Processing {i+1}/{len(self.rows)}: {work_id}")
            
            # For each step in the task
            for step_idx, wf_name in enumerate(task_steps):
                if self.cancel_event.is_set():
                    break
                
                self.video_log(f"  Step {step_idx+1}: {wf_name}")
                
                if wf_name == 'audio_generation':
                    continue
                
                if wf_name == 'FlashSVR' and not row["upscale"].get():
                    continue
                
                # Load workflow template using TemplateCatalog
                try:
                    mu = self._mu()
                    TemplateCatalog = mu.TemplateCatalog
                    apply_placeholders_unified = mu.apply_placeholders_unified
                    
                    wf_json = TemplateCatalog.load_template(wf_name)
                except Exception as e:
                    self.video_log(f"  Warning: Failed to load template {wf_name}: {e}")
                    continue

                # Calculate height from width and first row's image aspect ratio
                try:
                    width = int(self.resolution_var.get())
                except:
                    width = 1280
                height = width  # default square
                if self.rows:
                    first_img_path = self.rows[0].get("image_path", "")
                    if first_img_path and os.path.exists(first_img_path):
                        try:
                            from PIL import Image as PILImage
                            pil_img = PILImage.open(first_img_path)
                            orig_w, orig_h = pil_img.size
                            height = int(width * orig_h / orig_w)
                        except:
                            pass
                    else:
                        height = width
                else:
                    height = int(row["width"].get())

                # Prepare parameters dict for unified placeholder application
                params_dict = {
                    "prompt": video_prompt or "",
                    "video_pos_prompt": video_prompt or "",
                    "image": work_id + ".png",
                    "work_id": work_id,
                    "video_width": int(row["width"].get()),
                    "video_height": height,
                    "video_seconds": float(row["seconds"].get()),
                    "fps": int(self.fps_var.get()),
                    "load_image": work_id + ".png",
                    "save_video": work_id,
                    "row_id": work_id,
                    "finish_indicator": work_id,
                    "save_pos_conditioning": f"pos_{work_id}",
                    "save_neg_conditioning": f"neg_{work_id}",
                    "load_pos_conditioning": f"pos_{work_id}",
                    "load_neg_conditioning": f"neg_{work_id}",
                    "save_latent": work_id,
                    "load_latent": work_id,
                }

                # Apply placeholders using unified function
                wf_json = apply_placeholders_unified(wf_json, params_dict)
                
                # Send to ComfyUI
                try:
                    prompt_id = self._send_workflow_to_comfyui(wf_json, work_id, template_name=wf_name)
                    if not prompt_id:
                        self.video_log(f"  Warning: Failed to queue for {work_id}")
                        continue
                    
                    # Wait for completion
                    history = self._wait_for_completion(prompt_id)
                    if history:
                        self.video_log(f"  Completed {work_id}")
                    else:
                        self.video_log(f"  Timeout for {work_id}")
                except Exception as e:
                    self.video_log(f"  Error: {e}")
    
    def _get_task_steps(self, task_name):
        """Get task steps from CSV."""
        c = self._c()
        try:
            with open(c["TASK_STEPS_CSV"], mode='r', encoding='utf-8') as f:
                reader = csv.reader(f)
                header = next(reader, None)
                idx_wf = header.index('workflow_name')
                steps = []
                for row in reader:
                    if row[0].strip() == task_name:
                        steps.append(row[idx_wf].strip())
                return steps
        except:
            return None
    
    def _resolve_template_path(self, wf_name):
        """Resolve the workflow template path."""
        c = self._c()
        # Try direct path
        wf_path = os.path.join(c["WORKFLOW_TEMPLATE_DIR"], wf_name + ".json")
        if os.path.exists(wf_path):
            return wf_path
        
        # Try Wan 2.1/2.2 step files
        for suffix in ["_step1", "_step2", "_step3", "_step0"]:
            candidate = os.path.join(c["WORKFLOW_TEMPLATE_DIR"], wf_name + suffix + ".json")
            if os.path.exists(candidate):
                return candidate
        
        return None
    
    def _send_workflow_to_comfyui(self, workflow, work_id, template_name=None):
        """Send workflow to ComfyUI and return prompt_id.
        
        Also saves a debug copy to debug_workflows/ for troubleshooting.
        """
        c = self._c()
        import uuid
        try:
            prompt_id = str(uuid.uuid4())
            payload = {"prompt": workflow, "prompt_id": prompt_id}
            
            # Save debug workflow copy
            os.makedirs(os.path.join(os.path.dirname(__file__), "debug_workflows"), exist_ok=True)
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            safe_work_id = work_id.replace("/", "_").replace("\\", "_")
            debug_filename = f"{safe_work_id}_{template_name or 'workflow'}_{timestamp}.json"
            debug_path = os.path.join(os.path.dirname(__file__), "debug_workflows", debug_filename)
            with open(debug_path, 'w', encoding='utf-8') as f:
                json.dump(workflow, f, indent=2)
            self.video_log(f"Debug workflow saved: {debug_filename}")
            
            resp = requests.post(c["COMFYUI_URL"], json=payload, timeout=30)
            if resp.ok:
                return prompt_id
        except Exception:
            pass
        return None
    
    def _wait_for_completion(self, prompt_id, timeout=3600):
        """Wait for ComfyUI completion."""
        c = self._c()
        start_time = time.time()
        hist_url = c["COMFYUI_URL"].replace("/prompt", f"/history/{prompt_id}")
        
        while time.time() - start_time < timeout:
            if self.cancel_event.is_set():
                return 'cancelled'
            try:
                resp = requests.get(hist_url, timeout=10)
                if resp.ok:
                    data = resp.json()
                    if prompt_id in data:
                        return data[prompt_id]
            except:
                pass
            time.sleep(5)
        return None


def create_video_tab(parent_notebook, root):
    """Factory function to create the Video tab."""
    return VideoTabUI(parent_notebook, root)
