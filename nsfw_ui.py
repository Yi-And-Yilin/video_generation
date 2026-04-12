
import os
import glob

import tkinter as tk
from tkinter import ttk, scrolledtext
from PIL import Image, ImageTk, ImageGrab
import random
import string
import io
import os
import shutil
import threading
import time
import requests
import uuid
import csv
import json
from queue import Queue
from collections import deque
from typing import Dict

from pathlib import Path
import logging

# Import workflow generator
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "projects", "ltx"))
from workflow_generator import generate_api_workflow

# --- Configuration ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
COMFYUI_ROOT = os.environ.get("COMFYUI_ROOT", r"D:\ComfyUI_windows_portable\ComfyUI")
MMAUDIO_ROOT = os.environ.get("MMAUDIO_ROOT", r"D:\MMAudio")

# --- Internal paths ---
LOG_FILE = os.path.join(SCRIPT_DIR, "nsfw_ui.log")
VIDEO_OUTPUT_FOLDER = os.path.join(COMFYUI_ROOT, "output", "video")
INPUT_FOLDER = os.path.join(COMFYUI_ROOT, "input")
OUTPUT_FOLDER = os.path.join(COMFYUI_ROOT, "output")
LATENT_OUTPUT_FOLDER = os.path.join(COMFYUI_ROOT, "output", "latents")
CONDITIONING_OUTPUT_FOLDER = os.path.join(COMFYUI_ROOT, "output", "conditionings")
WORKFLOW_TEMPLATE_DIR = os.path.join(SCRIPT_DIR, "projects", "wan", "workflow")
PROCESSED_WORKFLOW_FOLDER = os.path.join(COMFYUI_ROOT, "output", "processed")
PARAMS_CSV = os.path.join(SCRIPT_DIR, "projects", "wan", "workflow", "workflow_params.csv")
TASK_STEPS_CSV = os.path.join(SCRIPT_DIR, "task_steps.csv")
VIDEO_PROMPT_TSV = os.path.join(SCRIPT_DIR, "video_prompt.tsv")
AUDIO_PROMPT_TSV = os.path.join(SCRIPT_DIR, "audio_prompt.tsv")
AUDIO_GENERATION_REQUESTS_TSV = os.path.join(SCRIPT_DIR, "audio_generation_requests.tsv")
STATE_FILE = os.path.join(SCRIPT_DIR, "nsfw_ui_state.json")
COMFYUI_URL = os.environ.get("COMFYUI_URL", "http://192.168.4.22:8188/prompt")

from llm_utils import LLMUtils

# --- LTX Project Paths ---
LTX_PROJECT_DIR = os.path.join(SCRIPT_DIR, "projects", "ltx")
LTX_PROMPTS_DIR = os.path.join(LTX_PROJECT_DIR, "prompts")
LTX_WORKFLOW_DIR = os.path.join(LTX_PROJECT_DIR, "workflow")
LTX_PROCESS_FILE = os.path.join(LTX_PROJECT_DIR, "process.json")
LTX_LOG_FILE = os.path.join(LTX_PROJECT_DIR, "ltx.log")
LTX_TASK_JSON = os.path.join(LTX_PROJECT_DIR, "task.json")
CONVERSATION_LOG_FILE = os.path.join(LTX_PROJECT_DIR, "conversation.log")

class StreamChunk:
    def __init__(self, content): self.content = content

class NSFWApp:
    def __init__(self, root):
        self.root = root
        self.root.title("NSFW UI")
        self.root.geometry("800x800")
        self.rows = []
        self.log_queue = Queue()
        self.is_running = False
        self.cancel_event = threading.Event()
        self._save_state_timer = None
        self.setup_logging()

        self.main_notebook = ttk.Notebook(root)
        self.main_notebook.pack(fill=tk.BOTH, expand=True)

        # WAN Tab
        wan_tab = tk.Frame(self.main_notebook)
        self.main_notebook.add(wan_tab, text="WAN")

        # LTX Tab
        self.ltx_tab = tk.Frame(self.main_notebook)
        self.main_notebook.add(self.ltx_tab, text="LTX")
        self.main_notebook.select(self.ltx_tab)

        # Prompt Tab
        self.prompt_tab = tk.Frame(self.main_notebook)
        self.main_notebook.add(self.prompt_tab, text="Prompt")

        # Image Tab
        self.image_tab = tk.Frame(self.main_notebook)
        self.main_notebook.add(self.image_tab, text="Image")

        # --- WAN UI ---
        wan_top = tk.Frame(wan_tab); wan_top.pack(fill=tk.X, pady=5)
        self.add_button = tk.Button(wan_top, text="+", command=self.add_empty_row); self.add_button.pack(side=tk.LEFT, padx=5)
        self.add_image_button = tk.Button(wan_top, text="Add Image", command=self.add_image_from_file); self.add_image_button.pack(side=tk.LEFT, padx=5)
        self.run_button = tk.Button(wan_top, text="Run", command=self.start_run_processing); self.run_button.pack(side=tk.LEFT, padx=5)
        self.cancel_button = tk.Button(wan_top, text="Cancel", command=self.cancel_processing); self.cancel_button.pack(side=tk.LEFT, padx=5)
        self.clear_all_button = tk.Button(wan_top, text="Clear All Rows", command=self.clear_all_rows); self.clear_all_button.pack(side=tk.LEFT, padx=5)
        tk.Label(wan_top, text="Task:").pack(side=tk.LEFT, padx=(5, 2))
        self.task_type_var = tk.StringVar(); self.task_type_dropdown = ttk.Combobox(wan_top, textvariable=self.task_type_var, state="readonly", width=15); self.task_type_dropdown.pack(side=tk.LEFT, padx=5)
        
        wan_instr = tk.Frame(wan_tab); wan_instr.pack(fill=tk.X, padx=5, pady=5)
        tk.Label(wan_instr, text="User Instruction:").pack(side=tk.TOP, anchor=tk.W); self.wan_instruction_box = scrolledtext.ScrolledText(wan_instr, height=4, width=50); self.wan_instruction_box.pack(fill=tk.X, expand=True)
        wan_nb = ttk.Notebook(wan_tab); wan_nb.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        wan_main = tk.Frame(wan_nb); wan_log = tk.Frame(wan_nb); wan_nb.add(wan_main, text="Main"); wan_nb.add(wan_log, text="Log")
        wan_list = tk.Frame(wan_main); wan_list.pack(fill=tk.BOTH, expand=True)
        self.canvas = tk.Canvas(wan_list); self.scrollbar = tk.Scrollbar(wan_list, orient="vertical", command=self.canvas.yview); self.scrollable_frame = tk.Frame(self.canvas); self.scrollable_frame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))); self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw"); self.canvas.configure(yscrollcommand=self.scrollbar.set); self.canvas.pack(side="left", fill="both", expand=True); self.scrollbar.pack(side="right", fill="y"); self.canvas.bind_all("<MouseWheel>", self._on_mousewheel); self.scrollable_frame.bind_all("<MouseWheel>", self._on_mousewheel)
        self.log_window = scrolledtext.ScrolledText(wan_log, height=10, state='disabled'); self.log_window.pack(fill=tk.BOTH, expand=True)

        # --- LTX UI ---
        ltx_act = tk.Frame(self.ltx_tab); ltx_act.pack(fill=tk.X, pady=2, padx=5)
        self.ltx_run_button = tk.Button(ltx_act, text="Run", command=self.ltx_start_run, width=10); self.ltx_run_button.pack(side=tk.LEFT, padx=5)
        self.ltx_pause_button = tk.Button(ltx_act, text="Pause", command=self.ltx_pause, state=tk.DISABLED, width=10); self.ltx_pause_button.pack(side=tk.LEFT, padx=5)
        self.ltx_resume_button = tk.Button(ltx_act, text="Resume", command=self.ltx_resume, state=tk.DISABLED, width=10); self.ltx_resume_button.pack(side=tk.LEFT, padx=5)
        tk.Button(ltx_act, text="Clear Pending", command=self.clear_pending_jobs, bg="#ffcccc").pack(side=tk.LEFT, padx=5)
        self.ltx_status_var = tk.StringVar(value="Ready"); tk.Label(ltx_act, textvariable=self.ltx_status_var, font=('Helvetica', 10, 'bold')).pack(side=tk.RIGHT, padx=10)
        ltx_set = tk.Frame(self.ltx_tab); ltx_set.pack(fill=tk.X, pady=2, padx=5)
        tk.Label(ltx_set, text="Res:").pack(side=tk.LEFT, padx=(5, 2)); self.resolution_var = tk.StringVar(value="1280*720"); self.resolution_dropdown = ttk.Combobox(ltx_set, textvariable=self.resolution_var, state="readonly", width=12); self.resolution_dropdown['values'] = ["1280*720", "720*1280", "1344*768", "480*854", "854*480", "720*720", "1024*1024"]; self.resolution_dropdown.pack(side=tk.LEFT, padx=5)
        tk.Label(ltx_set, text="SEC:").pack(side=tk.LEFT, padx=(5, 2)); self.sec_var = tk.StringVar(value="10"); self.sec_entry = tk.Entry(ltx_set, textvariable=self.sec_var, width=5); self.sec_entry.pack(side=tk.LEFT, padx=5)
        tk.Label(ltx_set, text="FPS:").pack(side=tk.LEFT, padx=(5, 2)); self.fps_var = tk.StringVar(value="24"); self.fps_entry = tk.Entry(ltx_set, textvariable=self.fps_var, width=5); self.fps_entry.pack(side=tk.LEFT, padx=5)
        tk.Label(ltx_set, text="Lang:").pack(side=tk.LEFT, padx=(5, 2)); self.language_var = tk.StringVar(value="Chinese"); self.language_dropdown = ttk.Combobox(ltx_set, textvariable=self.language_var, state="readonly", width=8); self.language_dropdown['values'] = ["Chinese", "English"]; self.language_dropdown.pack(side=tk.LEFT, padx=5)
        tk.Label(ltx_set, text="Batch:").pack(side=tk.LEFT, padx=(10, 2)); self.ltx_batch_var = tk.StringVar(value="1"); self.ltx_batch_entry = tk.Entry(ltx_set, textvariable=self.ltx_batch_var, width=5); self.ltx_batch_entry.pack(side=tk.LEFT, padx=5)
        tk.Label(ltx_set, text="Img Model:").pack(side=tk.LEFT, padx=(5, 2)); self.image_model_var = tk.StringVar(); self.image_model_dropdown = ttk.Combobox(ltx_set, textvariable=self.image_model_var, state="readonly", width=15); self.image_model_dropdown.pack(side=tk.LEFT, padx=5)
        self.ltx_upscale_var = tk.BooleanVar(value=False); tk.Checkbutton(ltx_set, text="Upscale", var=self.ltx_upscale_var).pack(side=tk.LEFT, padx=5)
        ltx_instr = tk.Frame(self.ltx_tab); ltx_instr.pack(fill=tk.X, padx=5, pady=5); tk.Label(ltx_instr, text="User Instruction:").pack(side=tk.TOP, anchor=tk.W); self.ltx_instruction_box = scrolledtext.ScrolledText(ltx_instr, height=4, width=50); self.ltx_instruction_box.pack(fill=tk.X, expand=True)
        self.ltx_log_window = scrolledtext.ScrolledText(self.ltx_tab, height=10, state='disabled'); self.ltx_log_window.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # --- Prompt UI ---
        pr_act = tk.Frame(self.prompt_tab); pr_act.pack(fill=tk.X, pady=2, padx=5)
        self.prompt_run_button = tk.Button(pr_act, text="Run", command=self.prompt_start_run, width=10); self.prompt_run_button.pack(side=tk.LEFT, padx=5)
        tk.Button(pr_act, text="Open", command=self._open_latest_task_file, width=8).pack(side=tk.LEFT, padx=5)
        tk.Button(pr_act, text="Delete", command=self._delete_latest_task_file, width=8).pack(side=tk.LEFT, padx=5)
        tk.Button(pr_act, text="Clear Log", command=self._prompt_clear_log, width=10).pack(side=tk.LEFT, padx=5)
        self.prompt_status_var = tk.StringVar(value="Ready"); tk.Label(pr_act, textvariable=self.prompt_status_var, font=('Helvetica', 10, 'bold')).pack(side=tk.RIGHT, padx=10)
        pr_set = tk.Frame(self.prompt_tab); pr_set.pack(fill=tk.X, pady=2, padx=5); tk.Label(pr_set, text="Template:").pack(side=tk.LEFT, padx=(5, 2))
        self.prompt_template_var = tk.StringVar(); self.prompt_template_dropdown = ttk.Combobox(pr_set, textvariable=self.prompt_template_var, state="readonly", width=30); self.prompt_template_dropdown.pack(side=tk.LEFT, padx=5); self.prompt_template_dropdown.bind("<<ComboboxSelected>>", self._on_prompt_template_selected)
        pr_instr = tk.Frame(self.prompt_tab); pr_instr.pack(fill=tk.X, padx=5, pady=5); tk.Label(pr_instr, text="User Instruction:").pack(side=tk.TOP, anchor=tk.W); self.prompt_instruction_box = scrolledtext.ScrolledText(pr_instr, height=6, width=50); self.prompt_instruction_box.pack(fill=tk.X, expand=True)
        self.prompt_log_window = scrolledtext.ScrolledText(self.prompt_tab, height=10, state='disabled'); self.prompt_log_window.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # --- Image UI ---
        im_act = tk.Frame(self.image_tab); im_act.pack(fill=tk.X, pady=2, padx=5)
        self.image_run_button = tk.Button(im_act, text="Run", command=self.image_start_run, width=10); self.image_run_button.pack(side=tk.LEFT, padx=5)
        self.image_status_var = tk.StringVar(value="Ready"); tk.Label(im_act, textvariable=self.image_status_var, font=('Helvetica', 10, 'bold')).pack(side=tk.RIGHT, padx=10)
        im_set = tk.Frame(self.image_tab); im_set.pack(fill=tk.X, pady=2, padx=5); tk.Label(im_set, text="Task:").pack(side=tk.LEFT, padx=(5, 2)); self.image_task_var = tk.StringVar(); self.image_task_dropdown = ttk.Combobox(im_set, textvariable=self.image_task_var, state="readonly", width=35); self.image_task_dropdown.pack(side=tk.LEFT, padx=5); tk.Button(im_set, text="Refresh", command=self._refresh_image_tasks, width=8).pack(side=tk.LEFT, padx=5)
        tk.Label(im_set, text="Res:").pack(side=tk.LEFT, padx=(15, 2)); self.image_resolution_var = tk.StringVar(value="1024*1024"); self.image_resolution_dropdown = ttk.Combobox(im_set, textvariable=self.image_resolution_var, state="readonly", width=12); self.image_resolution_dropdown['values'] = ["1024*1024", "1280*720", "720*1280", "1344*768", "896*1152", "1152*896"]; self.image_resolution_dropdown.pack(side=tk.LEFT, padx=5)
        self.image_log_window = scrolledtext.ScrolledText(self.image_tab, height=10, state='disabled'); self.image_log_window.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Final Bindings
        self.root.bind_all("<Control-v>", self.handle_paste, add="+"); self.root.after(100, self.process_log_queue); self.root.after(100, self.ltx_process_log_queue); self.root.after(100, self.prompt_process_log_queue); self.root.after(100, self.image_process_log_queue); self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        os.makedirs(INPUT_FOLDER, exist_ok=True); os.makedirs(OUTPUT_FOLDER, exist_ok=True); os.makedirs(WORKFLOW_TEMPLATE_DIR, exist_ok=True); os.makedirs(PROCESSED_WORKFLOW_FOLDER, exist_ok=True); os.makedirs(LTX_PROJECT_DIR, exist_ok=True); os.makedirs(LTX_WORKFLOW_DIR, exist_ok=True); os.makedirs(os.path.join(SCRIPT_DIR, "debug_workflows"), exist_ok=True)
        self.ltx_running = False; self.ltx_paused = False; self.ltx_cancel_event = threading.Event(); self.ltx_log_queue = Queue(); self.prompt_running = False; self.prompt_log_queue = Queue(); self.image_running = False; self.image_log_queue = Queue()
        self.load_state(); self._load_and_populate_task_types(); self._load_prompt_templates(); self._load_image_tasks(); self.load_logs_into_ui()
        self.conditioning_files = {}; self.latent_files = {}

    def setup_logging(self):
        self.log_file = LOG_FILE; log_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        fh = logging.FileHandler(self.log_file, encoding='utf-8'); fh.setFormatter(log_formatter); sh = logging.StreamHandler(); sh.setFormatter(log_formatter)
        self.logger = logging.getLogger(__name__); self.logger.addHandler(fh); self.logger.addHandler(sh); self.logger.setLevel(logging.INFO); self.logger.propagate = False

    def load_logs_into_ui(self, max_lines=1000):
        if not os.path.exists(self.log_file): return
        try:
            with open(self.log_file, 'r', encoding='utf-8') as f: last_lines = deque(f, max_lines)
            log_content = "".join(last_lines); self.log_window.configure(state='normal'); self.log_window.delete('1.0', tk.END); self.log_window.insert(tk.END, log_content); self.log_window.configure(state='disabled'); self.log_window.see(tk.END)
        except Exception as e: self.log(f"Error loading logs: {e}")

    def _load_and_populate_task_types(self):
        try:
            with open(TASK_STEPS_CSV, mode='r', encoding='utf-8') as infile:
                reader = csv.reader(infile); header = next(reader, None); task_names = sorted(list(set(row[0].strip() for row in reader if row)))
                if task_names: self.task_type_dropdown['values'] = task_names; self.task_type_var.set(task_names[0])
        except: pass

    def _run_audio_inference(self, row_id, pos, neg):
        try:
            fe = os.path.exists(AUDIO_GENERATION_REQUESTS_TSV)
            with open(AUDIO_GENERATION_REQUESTS_TSV, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f, delimiter='	')
                if not fe: writer.writerow(["file_id", "positive_prompt", "negative_prompt"])
                writer.writerow([row_id, pos, neg])
        except Exception as e: self.log(f"ERROR saving audio request: {e}")

    def _on_mousewheel(self, event): self.canvas.yview_scroll(int(-1*(event.delta/120)), "units")

    def process_log_queue(self):
        if self.log_queue.empty(): self.root.after(100, self.process_log_queue); return
        self.log_window.configure(state='normal')
        while not self.log_queue.empty():
            item = self.log_queue.get_nowait()
            if isinstance(item, StreamChunk): self.log_window.insert(tk.END, item.content)
            else: self.log_window.insert(tk.END, str(item) + "\n")
        lc = self.log_window.get("1.0", tk.END); lines = lc.count('\n')
        if lines > 2000: self.log_window.delete("1.0", f"{lines - 1000}.0")
        self.log_window.configure(state='disabled'); self.log_window.see(tk.END); self.root.after(100, self.process_log_queue)

    def log(self, message):
        level = logging.ERROR if any(x in str(message).upper() for x in ['ERROR', 'FAILED', 'FATAL']) else logging.INFO
        if hasattr(self, 'logger'): self.logger.log(level, message)
        self.log_queue.put(message)

    def ltx_log_to_main(self, message): self.log_queue.put(f"[LTX] {message}")
    def ltx_stream_log(self, message): chunk = StreamChunk(message); self.log_queue.put(chunk); self.ltx_log_queue.put(chunk)

    def generate_random_string(self, length=8): return ''.join(random.choice(string.ascii_lowercase + string.digits) for _ in range(length))

    def handle_paste(self, event=None):
        focused = self.root.focus_get()
        if focused and isinstance(focused, (tk.Text, scrolledtext.ScrolledText)): return
        try:
            img = ImageGrab.grabclipboard()
            if isinstance(img, Image.Image): self.add_row(image=img); return
            clipboard_content = self.root.clipboard_get()
            if clipboard_content:
                file_paths = clipboard_content.strip().split('\n'); found = False
                for path in file_paths:
                    clean_path = path.strip().strip('"')
                    if os.path.isfile(clean_path):
                        try:
                            pasted_img = Image.open(clean_path); ext = os.path.splitext(clean_path)[1] or ".png"
                            loc = os.path.join(INPUT_FOLDER, f"pasted_{self.generate_random_string()}{ext}"); shutil.copy2(clean_path, loc); self.add_row(image=pasted_img, image_path=loc); found = True
                        except: pass
                if found: return
        except Exception as e: self.log(f"Paste error: {e}")

    def add_row(self, image=None, is_empty=False, state=None, image_path=None):
        row_frame = tk.Frame(self.scrollable_frame, borderwidth=2, relief="sunken")
        row_frame.pack(fill=tk.X, padx=5, pady=5); thumb_label = tk.Label(row_frame); thumb_label.pack(side=tk.LEFT, padx=5, pady=5)
        if state:
            filename = state.get("filename", ""); filename_base = state.get("filename_base", ""); image_path_from_state = state.get("image_path")
            video_prompt_val = state.get("video_prompt", ""); audio_prompt_val = state.get("audio_prompt", ""); seconds_val = state.get("seconds", "6"); side_val = state.get("side", "720"); category_val = state.get("category", "NA"); upscale_val = state.get("upscale", False); audio_val = state.get("audio", False); batch_val = state.get("batch", "1")
            if not image_path_from_state or not os.path.exists(image_path_from_state):
                p = os.path.join(INPUT_FOLDER, filename)
                if filename and os.path.exists(p): image_path_from_state = p
            if image_path_from_state and os.path.exists(image_path_from_state):
                try:
                    img = Image.open(image_path_from_state); img.thumbnail((100, 100)); photo = ImageTk.PhotoImage(img)
                    thumb_label.config(image=photo); thumb_label.image = photo
                except: pass
            current_image_path = image_path if image_path else image_path_from_state
        else:
            if image_path: filename_base = Path(image_path).stem; filename = Path(image_path).name
            else: filename_base = self.generate_random_string(); filename = f"{filename_base}.png"
            current_image_path = os.path.join(INPUT_FOLDER, filename); video_prompt_val, audio_prompt_val = "", ""; seconds_val, side_val = "6", "720"; category_val, upscale_val, audio_val = "NA", False, False; batch_val = "1"
            if image:
                try:
                    os.makedirs(os.path.dirname(current_image_path), exist_ok=True); image.save(current_image_path, 'PNG')
                    img_copy = image.copy(); img_copy.thumbnail((100, 100)); photo = ImageTk.PhotoImage(img_copy)
                    thumb_label.config(image=photo); thumb_label.image = photo
                except: pass
        info_frame = tk.Frame(row_frame); info_frame.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5); info_frame.grid_columnconfigure(1, weight=1); info_frame.grid_columnconfigure(3, weight=1)
        tk.Label(info_frame, text="File Name:").grid(row=0, column=0, sticky=tk.W)
        fn_ent = tk.Entry(info_frame); fn_ent.insert(0, filename); fn_ent.config(state='readonly'); fn_ent.grid(row=0, column=1, columnspan=3, sticky=tk.EW)
        tk.Label(info_frame, text="Video Prompt:").grid(row=1, column=0, sticky=tk.W)
        vp_ent = tk.Entry(info_frame); vp_ent.insert(0, video_prompt_val); vp_ent.grid(row=1, column=1, sticky=tk.EW)
        tk.Button(info_frame, text="...", command=lambda: self._edit_long_text(vp_ent)).grid(row=1, column=2)
        tk.Label(info_frame, text="Audio Prompt:").grid(row=1, column=3, sticky=tk.W)
        ap_ent = tk.Entry(info_frame); ap_ent.insert(0, audio_prompt_val); ap_ent.grid(row=1, column=4, sticky=tk.EW)
        tk.Label(info_frame, text="Sec:").grid(row=2, column=0, sticky=tk.W)
        sec_ent = tk.Entry(info_frame); sec_ent.insert(0, seconds_val); sec_ent.grid(row=2, column=1, sticky=tk.EW)
        tk.Label(info_frame, text="Side:").grid(row=2, column=2, sticky=tk.W)
        side_ent = tk.Entry(info_frame); side_ent.insert(0, side_val); side_ent.grid(row=2, column=3, sticky=tk.EW)
        tk.Label(info_frame, text="Cat:").grid(row=3, column=0, sticky=tk.W)
        cats = ["NA", "Sitting_panites", "Standing_panties","Standing_butt", "Masturbation", "Oral", "Cowgirl",  "Kiss", "Doggy", "Missionary"]
        cat_var = tk.StringVar(value=category_val); ttk.Combobox(info_frame, textvariable=cat_var, values=cats, state="readonly").grid(row=3, column=1, columnspan=3, sticky=tk.EW)
        tk.Label(info_frame, text="Batch:").grid(row=4, column=0, sticky=tk.W)
        batch_ent = tk.Entry(info_frame); batch_ent.insert(0, batch_val); batch_ent.grid(row=4, column=1, sticky=tk.EW)
        ctrl_frame = tk.Frame(row_frame); ctrl_frame.pack(side=tk.RIGHT, padx=5)
        up_var = tk.BooleanVar(value=upscale_val); tk.Checkbutton(ctrl_frame, text="Up", var=up_var).pack(anchor=tk.W)
        aud_var = tk.BooleanVar(value=audio_val); tk.Checkbutton(ctrl_frame, text="Aud", var=aud_var).pack(anchor=tk.W)
        tk.Button(ctrl_frame, text="Del", command=lambda: self.delete_row(row_frame)).pack()
        row_data = {"frame": row_frame, "image_path": current_image_path, "filename_base": filename_base, "filename": fn_ent, "video_prompt": vp_ent, "audio_prompt": ap_ent, "seconds": sec_ent, "side": side_ent, "category": cat_var, "upscale": up_var, "audio": aud_var, "batch": batch_ent}
        self.rows.append(row_data); self.root.after(100, lambda: self.canvas.yview_moveto(1.0))

    def add_empty_row(self): self.add_row(is_empty=True)
    def add_image_from_file(self):
        from tkinter import filedialog
        paths = filedialog.askopenfilenames(title="Images", filetypes=[("Images", "*.png *.jpg *.jpeg *.gif *.bmp")])
        if paths:
            for p in paths:
                try:
                    img = Image.open(p); fn = os.path.basename(p); dest = os.path.join(INPUT_FOLDER, fn)
                    shutil.copy2(p, dest); self.add_row(image=img, image_path=dest)
                except: pass

    def delete_row(self, frame):
        for i, r in enumerate(self.rows):
            if r["frame"] == frame: self.rows.pop(i); frame.destroy(); break
        self._schedule_save_state()

    def set_ui_state(self, is_running):
        self.is_running = is_running; st = tk.DISABLED if is_running else tk.NORMAL
        self.run_button.config(state=st); self.add_button.config(state=st); self.add_image_button.config(state=st); self.cancel_button.config(state=tk.NORMAL if is_running else tk.DISABLED)

    def on_closing(self): self.save_state(); self.root.destroy()
    def _schedule_save_state(self, *args):
        if self._save_state_timer: self.root.after_cancel(self._save_state_timer)
        self._save_state_timer = self.root.after(500, self.save_state)

    def save_state(self):
        to_save = []
        for r in self.rows:
            to_save.append({"image_path": r["image_path"], "filename": r["filename"].get(), "filename_base": r["filename_base"], "video_prompt": r["video_prompt"].get(), "audio_prompt": r["audio_prompt"].get(), "seconds": r["seconds"].get(), "side": r["side"].get(), "category": r["category"].get(), "upscale": r["upscale"].get(), "audio": r["audio"].get(), "batch": r["batch"].get()})
        try:
            with open(STATE_FILE, 'w', encoding='utf-8') as f: json.dump(to_save, f, indent=4)
        except: pass

    def load_state(self):
        if not os.path.exists(STATE_FILE): return
        try:
            with open(STATE_FILE, 'r', encoding='utf-8') as f:
                saved = json.load(f)
                for s in saved: self.add_row(state=s)
        except: pass

    def get_task_steps(self, task_name):
        try:
            with open(TASK_STEPS_CSV, mode='r', encoding='utf-8') as f:
                reader = csv.reader(f); header = next(reader, None); idx_wf = header.index('workflow_name'); idx_sv = header.index('save_video'); idx_cat = header.index('category')
                steps = []
                for row in reader:
                    if row[0].strip() == task_name: steps.append((row[idx_wf].strip(), row[idx_sv].strip().lower(), row[idx_cat].strip().lower()))
                return steps
        except: return None

    def get_params_map(self):
        try:
            with open(PARAMS_CSV, mode='r', encoding='utf-8') as f:
                reader = csv.reader(f); next(reader, None); p_map = {}
                for row in reader:
                    if len(row) == 3:
                        wf, find, repl = [s.strip() for s in row]
                        if wf not in p_map: p_map[wf] = []
                        p_map[wf].append({"find": find, "replace_template": repl})
                return p_map
        except: return {}

    def _get_prompt_from_tsv(self, path, cat):
        try:
            with open(path, mode='r', encoding='utf-8') as f:
                reader = csv.reader(f, delimiter='	'); next(reader, None)
                matches = [row[1].strip() for row in reader if row[0].strip().lower() == cat.lower()]
                return random.choice(matches) if matches else None
        except: return None

    def start_run_processing(self):
        if self.is_running: return
        sel_task = self.task_type_var.get(); configs = []
        if not self.rows: self.log("WARNING: No rows added."); return
        for r in self.rows:
            configs.append({"filename_base": r["filename_base"], "image_path": r["image_path"], "video_prompt": r["video_prompt"].get(), "audio_prompt": r["audio_prompt"].get(), "seconds": r["seconds"].get(), "side": r["side"].get(), "category": r["category"].get(), "upscale": r["upscale"].get(), "audio": r["audio"].get(), "batch": r["batch"].get()})
        self.cancel_event.clear(); self.set_ui_state(True)
        threading.Thread(target=self._run_processing_thread, args=(sel_task, configs), daemon=True).start()

    def wait_for_completion(self, prompt_id, timeout=3600):
        start_time = time.time(); hist_url = COMFYUI_URL.replace("/prompt", f"/history/{prompt_id}")
        while time.time() - start_time < timeout:
            if self.cancel_event.is_set(): return 'cancelled'
            try:
                resp = requests.get(hist_url, timeout=10)
                if resp.ok:
                    data = resp.json()
                    if prompt_id in data: return data[prompt_id]
            except: pass
            time.sleep(5)
        return None

    def cancel_processing(self):
        if self.is_running: self.log("--- Cancellation requested ---"); self.cancel_event.set()

    def clear_all_rows(self):
        if not self.is_running:
            for r in self.rows: r["frame"].destroy()
            self.rows.clear()

    def _run_processing_thread(self, selected_task, row_configs):
        try:
            self.log(f"--- Starting Task '{selected_task}' ---")
            debug_dir = os.path.join(SCRIPT_DIR, "debug_workflows"); os.makedirs(debug_dir, exist_ok=True)
            os.makedirs(os.path.join(INPUT_FOLDER, "latents"), exist_ok=True)
            flat_jobs = []
            for row in row_configs:
                try: batch_count = int(row["batch"])
                except: batch_count = 1
                for b_idx in range(batch_count):
                    uid = self.generate_random_string(8)
                    if row["image_path"] and os.path.exists(row["image_path"]):
                        shutil.copy2(row["image_path"], os.path.join(INPUT_FOLDER, f"{uid}.png"))
                    flat_jobs.append({"job_id": uid, "row_ref": row})

            self.discovered_outputs = {job["job_id"]: {} for job in flat_jobs}
            task_steps = self.get_task_steps(selected_task); params_map = self.get_params_map()
            
            for step_idx, (wf_name, save_video, use_cat) in enumerate(task_steps):
                if self.cancel_event.is_set(): break
                self.log(f"--- Step {step_idx + 1}/{len(task_steps)}: '{wf_name}' ---")

                for job in flat_jobs:
                    if self.cancel_event.is_set(): break
                    jid = job["job_id"]; row = job["row_ref"]
                    
                    if wf_name == 'audio_nsfw':
                        if row["audio"]:
                            c = row["category"]; p = self._get_prompt_from_tsv(AUDIO_PROMPT_TSV, c) if c != "NA" else None
                            self._run_audio_inference(jid, p if p else row["audio_prompt"], "harsh, music, noise")
                        else: self.log(f"DEBUG: Skipping audio for {jid}")
                        continue

                    if wf_name == 'FlashSVR' and not row["upscale"]:
                        self.log(f"DEBUG: Skipping FlashSVR for {jid}"); continue

                    wf_path = os.path.join(WORKFLOW_TEMPLATE_DIR, f"{wf_name}.json")
                    if use_cat == 'yes' and row["category"] != 'NA':
                        spec = os.path.join(WORKFLOW_TEMPLATE_DIR, f"{wf_name}_{row['category'].lower()}.json")
                        if os.path.exists(spec): wf_path = spec
                    
                    try:
                        with open(wf_path, 'r', encoding='utf-8') as f: wf_str = f.read()
                        wf_json = json.loads(wf_str)
                    except: continue

                    vp = self._get_prompt_from_tsv(VIDEO_PROMPT_TSV, row["category"]) if row["category"] != "NA" else None
                    ap = self._get_prompt_from_tsv(AUDIO_PROMPT_TSV, row["category"]) if row["category"] != "NA" else None
                    job_files = self.discovered_outputs.get(jid, {})
                    step_suffix = f"_s{step_idx}"

                    for node_id, node in wf_json.items():
                        cls = node.get("class_type", "")
                        inputs = node.get("inputs", {})

                        # ========== NEW: **XXX** string replacement in input values ==========
                        for k, v in inputs.items():
                            if isinstance(v, str):
                                # Width (side = width) - may need int conversion for JWInteger nodes
                                if "**width**" in v:
                                    inputs[k] = int(row["side"]) if cls == "JWInteger" else row["side"]
                                # Seconds - may need int conversion for JWInteger nodes
                                elif "**second**" in v:
                                    inputs[k] = int(row["seconds"]) if cls == "JWInteger" else row["seconds"]
                                # Prompt (video prompt from TSV or UI)
                                elif "**prompt**" in v:
                                    inputs[k] = vp if vp else row["video_prompt"]
                                # Audio prompt (from TSV or UI)
                                elif "**audio_prompt**" in v:
                                    inputs[k] = ap if ap else row["audio_prompt"]
                                # Positive conditioning file
                                elif "**pos_conditioning**" in v:
                                    inputs[k] = job_files.get("pos", f"pos_{jid}.pt")
                                # Negative conditioning file
                                elif "**neg_conditioning**" in v:
                                    inputs[k] = job_files.get("neg", f"neg_{jid}.pt")
                                # Latent input (from discovered outputs or default to step0)
                                elif "**latent_input**" in v:
                                    target_lat = job_files.get("lat")
                                    if target_lat:
                                        inputs[k] = "latents\\" + target_lat
                                    else:
                                        inputs[k] = "latents\\lat_" + jid + "_s0_00001_.latent"
                                # Latent output (with step suffix)
                                elif "**latent_output**" in v:
                                    prefix = f"lat_{jid}{step_suffix}"
                                    inputs[k] = "latents\\" + prefix
                                # Video output (job_id as filename prefix)
                                elif "**video_output**" in v:
                                    inputs[k] = "video\\" + jid
                                # Row ID (job_id) - for generic row_id usage
                                elif "**row_id**" in v:
                                    inputs[k] = jid
                                # Row ID input (for FlashSVR/final_upscale input video)
                                elif "**row_id_in**" in v:
                                    inputs[k] = jid
                                # Row ID output (for FlashSVR/final_upscale output video)
                                elif "**row_id_out**" in v:
                                    inputs[k] = jid + "_upscaled"
                                # Finish indicator (for clean_up)
                                elif "**finish_indicator**" in v:
                                    inputs[k] = jid
                        # ========== END NEW CODE ==========

                    wf_str = json.dumps(wf_json, indent=4)
                    with open(os.path.join(debug_dir, f"{jid}_step{step_idx}_{wf_name}.json"), 'w', encoding='utf-8') as f: f.write(wf_str)

                    pid = self.send_workflow_to_comfyui(wf_str, jid)
                    if pid:
                        hist = self.wait_for_completion(pid)
                        if hist == 'cancelled': break
                        if hist:
                            if os.path.exists(CONDITIONING_OUTPUT_FOLDER):
                                for p in [f"pos_{jid}", f"neg_{jid}"]:
                                    fname = f"{p}.pt"; src = os.path.join(CONDITIONING_OUTPUT_FOLDER, fname)
                                    if os.path.exists(src):
                                        self.discovered_outputs[jid]["pos" if "pos" in p else "neg"] = fname
                            if os.path.exists(LATENT_OUTPUT_FOLDER):
                                l_files = os.listdir(LATENT_OUTPUT_FOLDER)
                                cur_p = f"lat_{jid}_s{step_idx}"; matches = [f for f in l_files if f.startswith(cur_p) and f.endswith(".latent")]
                                if matches:
                                    fname = max(matches, key=lambda f: os.path.getmtime(os.path.join(LATENT_OUTPUT_FOLDER, f)))
                                    self.discovered_outputs[jid]["lat"] = fname
                                    self.log(f"DEBUG: Discovered {jid} Step {step_idx}: {fname}")
                    time.sleep(0.5)

                if save_video == 'yes': self._rename_and_cleanup_videos([j["job_id"] for j in flat_jobs])

            # Cleanup temporary files after task completion
            for job in flat_jobs:
                self._cleanup_wan_temp_files(job["job_id"])

            self.log(f"--- Task '{selected_task}' FINISHED ---")
        except Exception as e:
            self.log(f"CRITICAL ERROR: {e}"); import traceback; self.log(traceback.format_exc())
        finally: self.set_ui_state(False)

    def _rename_and_cleanup_videos(self, row_ids):
        if not os.path.exists(VIDEO_OUTPUT_FOLDER): return
        for rid in row_ids:
            rel = [f for f in os.listdir(VIDEO_OUTPUT_FOLDER) if f.startswith(f"{rid}_") and f.endswith(".mp4")]
            if not rel: continue
            fname = max(rel, key=lambda f: os.path.getmtime(os.path.join(VIDEO_OUTPUT_FOLDER, f)))
            try: os.replace(os.path.join(VIDEO_OUTPUT_FOLDER, fname), os.path.join(VIDEO_OUTPUT_FOLDER, f"{rid}.mp4"))
            except: pass

    def _cleanup_wan_temp_files(self, job_id):
        """Cleanup temporary files after WAN task completion."""
        deleted = []

        # Delete conditioning files from output/conditionings/
        if os.path.exists(CONDITIONING_OUTPUT_FOLDER):
            for prefix in [f"pos_{job_id}", f"neg_{job_id}"]:
                fpath = os.path.join(CONDITIONING_OUTPUT_FOLDER, f"{prefix}.pt")
                if os.path.exists(fpath):
                    try:
                        os.remove(fpath)
                        deleted.append(f"{prefix}.pt")
                        self.log(f"CLEANUP: Deleted {prefix}.pt")
                    except Exception as e:
                        self.log(f"CLEANUP ERROR: Could not delete {prefix}.pt: {e}")

        # Delete latent files from output/latents/ (all step indices: s0, s1, s2, s3)
        if os.path.exists(LATENT_OUTPUT_FOLDER):
            for s in range(4):
                pattern = os.path.join(LATENT_OUTPUT_FOLDER, f"lat_{job_id}_s{s}*")
                for fpath in glob.glob(pattern):
                    if os.path.isfile(fpath):
                        try:
                            os.remove(fpath)
                            deleted.append(os.path.basename(fpath))
                            self.log(f"CLEANUP: Deleted {os.path.basename(fpath)}")
                        except Exception as e:
                            self.log(f"CLEANUP ERROR: Could not delete {os.path.basename(fpath)}: {e}")

        # Delete input image from input/
        img_path = os.path.join(INPUT_FOLDER, f"{job_id}.png")
        if os.path.exists(img_path):
            try:
                os.remove(img_path)
                deleted.append(f"{job_id}.png")
                self.log(f"CLEANUP: Deleted {job_id}.png from input/")
            except Exception as e:
                self.log(f"CLEANUP ERROR: Could not delete {job_id}.png: {e}")

        return deleted

    def send_workflow_to_comfyui(self, workflow_str, work_id=None):
        try:
            payload = {"prompt": json.loads(workflow_str), "prompt_id": str(uuid.uuid4())}
            resp = requests.post(COMFYUI_URL, json=payload, timeout=60)
            if resp.ok: return payload['prompt_id']
        except: pass
        return None

    def ltx_log(self, message):
        full = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}"
        self.ltx_log_queue.put(full)
        try:
            with open(LTX_LOG_FILE, 'a', encoding='utf-8') as f: f.write(full + "\n")
        except: pass

    def ltx_process_log_queue(self):
        if self.ltx_log_queue.empty(): self.root.after(100, self.ltx_process_log_queue); return
        self.ltx_log_window.configure(state='normal')
        while not self.ltx_log_queue.empty():
            item = self.ltx_log_queue.get_nowait()
            if isinstance(item, StreamChunk): self.ltx_log_window.insert(tk.END, item.content)
            else: self.ltx_log_window.insert(tk.END, str(item) + "\n")
        self.ltx_log_window.configure(state='disabled'); self.ltx_log_window.see(tk.END); self.root.after(100, self.ltx_process_log_queue)

    def ltx_load_process(self):
        if os.path.exists(LTX_PROCESS_FILE):
            try:
                with open(LTX_PROCESS_FILE, 'r', encoding='utf-8') as f: return json.load(f)
            except: pass
        return None

    def ltx_save_process(self, data):
        try:
            os.makedirs(os.path.dirname(LTX_PROCESS_FILE), exist_ok=True)
            with open(LTX_PROCESS_FILE, 'w', encoding='utf-8') as f: json.dump(data, f, indent=4)
        except: pass

    def ltx_set_ui_state(self, run, pause=False):
        self.ltx_running = run; self.ltx_paused = pause
        st = tk.DISABLED if run else tk.NORMAL
        self.ltx_run_button.config(state=tk.DISABLED if run and not pause else tk.NORMAL)
        self.ltx_pause_button.config(state=tk.NORMAL if run and not pause else tk.DISABLED)
        self.ltx_resume_button.config(state=tk.NORMAL if run and pause else tk.DISABLED)

    def ltx_start_run(self):
        if self.ltx_running: return
        ex = self.ltx_load_process()
        if ex and ex.get("status") == "paused": self.ltx_set_ui_state(True, True); return
        try: bc = int(self.ltx_batch_var.get())
        except: bc = 1
        data = {"total_steps": bc, "current_step": 0, "status": "running"}
        self.ltx_save_process(data); self.ltx_cancel_event.clear(); self.ltx_set_ui_state(True)
        threading.Thread(target=self._ltx_run_workflow_thread, daemon=True).start()

    def _ltx_run_workflow_thread(self):
        process_data = self.ltx_load_process()
        if not process_data: return
        total_steps = process_data["total_steps"]; start_step = process_data["current_step"]
        general_md_path = os.path.join(LTX_PROMPTS_DIR, "general.md"); user_prompt_md_path = os.path.join(LTX_PROMPTS_DIR, "user_prompt.md"); general_json_path = os.path.join(LTX_PROMPTS_DIR, "general.json")
        try:
            for step in range(start_step, total_steps):
                if self.ltx_paused or self.ltx_cancel_event.is_set(): break
                self.root.after(0, lambda s=step: self.ltx_status_var.set(f"Step {s+1}/{total_steps}"))
                with open(general_md_path, 'r', encoding='utf-8') as f: sys_p = f.read()
                with open(user_prompt_md_path, 'r', encoding='utf-8') as f: usr_p = f.read()
                with open(general_json_path, 'r', encoding='utf-8') as f: schema = json.load(f)
                instr = self.ltx_instruction_box.get("1.0", tk.END).strip()
                final_p = f"{sys_p}\n\n{usr_p}\n\nInstruction: {instr}"
                full_resp = ""; formal_resp = ""
                for chunk in LLMUtils.stream(prompt=final_p, model="huihui_ai/qwen3.5-abliterated:9b", thinking=True, function_definition=schema):
                    full_resp += chunk
                    if "Formal Answer:" in full_resp: formal_resp = full_resp.split("Formal Answer:", 1)[1].strip()
                    self.ltx_stream_log(chunk)
                ai_data = json.loads(formal_resp) if formal_resp else {}
                final_task = {"parameters": {"res": self.resolution_var.get(), "sec": self.sec_var.get()}, "ai_response": ai_data}
                with open(LTX_TASK_JSON, 'w', encoding='utf-8') as f: json.dump(final_task, f, indent=4)
                process_data["current_step"] = step + 1; self.ltx_save_process(process_data)
        except Exception as e: self.ltx_log(f"LTX Error: {e}")
        finally: self.ltx_set_ui_state(False)

    def ltx_pause(self): self.ltx_paused = True; self.ltx_set_ui_state(True, True)
    def ltx_resume(self): self.ltx_paused = False; self.ltx_set_ui_state(True, False); threading.Thread(target=self._ltx_run_workflow_thread, daemon=True).start()
    def clear_pending_jobs(self):
        if os.path.exists(LTX_PROCESS_FILE): os.remove(LTX_PROCESS_FILE)
        if os.path.exists(LTX_TASK_JSON): os.remove(LTX_TASK_JSON)
        self.ltx_status_var.set("Ready")

    def _load_prompt_templates(self):
        prompts_dir = os.path.join(LTX_PROJECT_DIR, "prompts")
        if not os.path.exists(prompts_dir): return
        files = [f[:-3] for f in os.listdir(prompts_dir) if f.endswith('.md') and f != 'user_prompt.md']
        files.sort(); self.prompt_template_dropdown['values'] = files
        if files: self.prompt_template_var.set(files[0])

    def _on_prompt_template_selected(self, event): pass
    def _prompt_log(self, msg): self.prompt_log_queue.put(f"[{time.strftime('%H:%M:%S')}] {msg}")
    def _prompt_clear_log(self):
        self.prompt_log_window.configure(state='normal'); self.prompt_log_window.delete('1.0', tk.END); self.prompt_log_window.configure(state='disabled')

    def prompt_process_log_queue(self):
        if self.prompt_log_queue.empty(): self.root.after(100, self.prompt_process_log_queue); return
        self.prompt_log_window.configure(state='normal')
        while not self.prompt_log_queue.empty():
            item = self.prompt_log_queue.get_nowait()
            if isinstance(item, StreamChunk): self.prompt_log_window.insert(tk.END, item.content)
            else: self.prompt_log_window.insert(tk.END, str(item) + "\n")
        self.prompt_log_window.configure(state='disabled'); self.prompt_log_window.see(tk.END); self.root.after(100, self.prompt_process_log_queue)

    def prompt_start_run(self):
        if self.prompt_running: return
        self.prompt_running = True; self.prompt_run_button.config(state=tk.DISABLED)
        threading.Thread(target=self._prompt_run_thread, daemon=True).start()

    def _prompt_run_thread(self):
        try:
            tmpl = self.prompt_template_var.get(); schema_path = os.path.join(LTX_PROJECT_DIR, "prompts", f"{tmpl}.json")
            with open(os.path.join(LTX_PROJECT_DIR, "prompts", f"{tmpl}.md"), 'r', encoding='utf-8') as f: p_content = f.read()
            schema = json.load(open(schema_path, 'r', encoding='utf-8')) if os.path.exists(schema_path) else None
            instr = self.prompt_instruction_box.get("1.0", tk.END).strip(); final_p = p_content.replace("{{user_prompt}}", instr) if "{{user_prompt}}" in p_content else p_content + f"\n\n{instr}"
            resp = ""
            for chunk in LLMUtils.stream(prompt=final_p, model="huihui_ai/qwen3.5-abliterated:9b", function_definition=schema):
                resp += chunk; self.prompt_log_queue.put(StreamChunk(chunk))
            self._prompt_extract_and_save_response(resp, tmpl)
        except Exception as e: self._prompt_log(f"Error: {e}")
        finally: self.prompt_running = False; self.root.after(0, lambda: self.prompt_run_button.config(state=tk.NORMAL))

    def _prompt_extract_and_save_response(self, response, tmpl):
        tasks_dir = os.path.join(LTX_PROJECT_DIR, "tasks"); os.makedirs(tasks_dir, exist_ok=True)
        ts = time.strftime("%Y%m%d_%H%M%S"); out_path = os.path.join(tasks_dir, f"{tmpl}_{ts}.json")
        with open(out_path, 'w', encoding='utf-8') as f: f.write(response)

    def _get_latest_task_file(self):
        tasks_dir = os.path.join(LTX_PROJECT_DIR, "tasks")
        if not os.path.exists(tasks_dir): return None
        files = sorted([f for f in os.listdir(tasks_dir) if f.endswith('.json')], reverse=True)
        return os.path.join(tasks_dir, files[0]) if files else None

    def _open_latest_task_file(self):
        f = self._get_latest_task_file()
        if f: os.startfile(f)

    def _delete_latest_task_file(self):
        f = self._get_latest_task_file()
        if f: os.remove(f)

    def _load_image_tasks(self):
        tasks_dir = os.path.join(LTX_PROJECT_DIR, "tasks")
        if not os.path.exists(tasks_dir): return
        files = sorted([f for f in os.listdir(tasks_dir) if f.endswith('.json')], reverse=True)
        self.image_task_dropdown['values'] = files
        if files: self.image_task_var.set(files[0])

    def _refresh_image_tasks(self): self._load_image_tasks()
    def image_process_log_queue(self):
        if self.image_log_queue.empty(): self.root.after(100, self.image_process_log_queue); return
        self.image_log_window.configure(state='normal')
        while not self.image_log_queue.empty():
            item = self.image_log_queue.get_nowait(); self.image_log_window.insert(tk.END, str(item) + "\n")
        self.image_log_window.configure(state='disabled'); self.image_log_window.see(tk.END); self.root.after(100, self.image_process_log_queue)

    def image_start_run(self):
        if self.image_running: return
        self.image_running = True; self.image_run_button.config(state=tk.DISABLED)
        threading.Thread(target=self._image_run_thread, daemon=True).start()

    def _image_run_thread(self):
        try:
            task_file = self.image_task_var.get()
            with open(os.path.join(LTX_PROJECT_DIR, "tasks", task_file), 'r', encoding='utf-8') as f: data = json.load(f)
            scenes = data.get("scenes", []); job_id = time.strftime("%Y%m%d_%H%M%S")
            for idx, sc in enumerate(scenes):
                prompt = sc.get("first_frame_image_prompt", ""); wf = generate_api_workflow(project="ltx", type="image", template="pornmaster_proSDXLV8", prompt=prompt, work_id=f"{job_id}_{idx+1}")
                self.send_workflow_to_comfyui(json.dumps(wf))
        except Exception as e: self.log(f"Image Error: {e}")
        finally: self.image_running = False; self.root.after(0, lambda: self.image_run_button.config(state=tk.NORMAL))

    def _edit_long_text(self, entry, title="Edit Text"):
        win = tk.Toplevel(self.root); win.title(title); win.geometry("500x300")
        txt = scrolledtext.ScrolledText(win, wrap=tk.WORD, height=10); txt.insert(tk.END, entry.get()); txt.pack(expand=True, fill=tk.BOTH)
        def save(): entry.delete(0, tk.END); entry.insert(0, txt.get("1.0", tk.END).strip()); win.destroy()
        tk.Button(win, text="Save", command=save).pack(side=tk.LEFT, padx=20); tk.Button(win, text="Cancel", command=win.destroy).pack(side=tk.RIGHT, padx=20)

if __name__ == "__main__":
    root = tk.Tk(); app = NSFWApp(root); root.mainloop()
