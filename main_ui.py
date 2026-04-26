import os
import glob
import subprocess
import shutil

import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog
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

from new_tab_workflow import run_new_tab_workflow

# Import workflow generator
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "projects", "ltx"))
from workflow_generator import generate_api_workflow, generate_workflow_for_wan_image, load_lora_lookup

# Unified workflow selector
from workflow_selector import TemplateCatalog, apply_placeholders_unified

# --- Configuration ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
COMFYUI_ROOT = os.environ.get("COMFYUI_ROOT", r"D:\ComfyUI_windows_portable\ComfyUI")
MMAUDIO_ROOT = os.environ.get("MMAUDIO_ROOT", r"D:\MMAudio")

# --- Internal paths ---
LOG_FILE = os.path.join(SCRIPT_DIR, "main_ui.log")
VIDEO_OUTPUT_FOLDER = os.path.join(COMFYUI_ROOT, "output", "video")
INPUT_FOLDER = os.path.join(COMFYUI_ROOT, "input")
OUTPUT_FOLDER = os.path.join(COMFYUI_ROOT, "output")
LATENT_OUTPUT_FOLDER = os.path.join(COMFYUI_ROOT, "output", "latents")
CONDITIONING_OUTPUT_FOLDER = os.path.join(COMFYUI_ROOT, "output", "conditionings")
WORKFLOW_TEMPLATE_DIR = os.path.join(SCRIPT_DIR, "workflows")
PROCESSED_WORKFLOW_FOLDER = os.path.join(COMFYUI_ROOT, "output", "processed")
TASK_STEPS_CSV = os.path.join(SCRIPT_DIR, "task_steps.csv")
VIDEO_PROMPT_TSV = os.path.join(SCRIPT_DIR, "video_prompt.tsv")
AUDIO_PROMPT_TSV = os.path.join(SCRIPT_DIR, "audio_prompt.tsv")
AUDIO_GENERATION_REQUESTS_TSV = os.path.join(SCRIPT_DIR, "audio_generation_requests.tsv")
STATE_FILE = os.path.join(SCRIPT_DIR, "main_ui_state.json")
VIDEO_STATE_FILE = os.path.join(SCRIPT_DIR, "video_tab_state.json")
COMFYUI_URL = os.environ.get("COMFYUI_URL", "http://192.168.4.22:8188/prompt")

from llm_utils import LLMUtils
from comfyui_image_utils import download_image_from_comfyui, wait_for_execution

# --- LTX Project Paths ---
LTX_PROJECT_DIR = os.path.join(SCRIPT_DIR, "projects", "ltx")
LTX_PROMPTS_DIR = os.path.join(LTX_PROJECT_DIR, "prompts")
LTX_WORKFLOW_DIR = os.path.join(SCRIPT_DIR, "workflows", "video")
LTX_PROCESS_FILE = os.path.join(LTX_PROJECT_DIR, "process.json")
LTX_LOG_FILE = os.path.join(LTX_PROJECT_DIR, "ltx.log")
LTX_TASK_JSON = os.path.join(LTX_PROJECT_DIR, "task.json")
CONVERSATION_LOG_FILE = os.path.join(LTX_PROJECT_DIR, "conversation.log")

class StreamChunk:
    def __init__(self, content): self.content = content

class VideoGenerationApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Video Generation UI")
        self.root.geometry("800x800")
        self.rows = []
        self.log_queue = Queue()
        self.is_running = False
        self.cancel_event = threading.Event()
        self._save_state_timer = None
        self.setup_logging()

        self.main_notebook = ttk.Notebook(root)
        self.main_notebook.pack(fill=tk.BOTH, expand=True)

        # New Tab (first tab, default active)
        self.new_tab = tk.Frame(self.main_notebook)
        self.main_notebook.add(self.new_tab, text="New")
        self.main_notebook.select(self.new_tab)

        # --- New tab: split into left (input) and right (log) panes ---
        new_split = tk.Frame(self.new_tab)
        new_split.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Left pane: requirement input + buttons
        new_left = tk.Frame(new_split)
        new_left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))

        btn_frame = tk.Frame(new_left)
        btn_frame.pack(fill=tk.X, pady=(0, 5))
        self.new_run_button = tk.Button(btn_frame, text="Run", command=self.new_tab_run)
        self.new_run_button.pack(side=tk.LEFT, padx=(0, 5))
        self.new_stop_button = tk.Button(btn_frame, text="Stop", command=self.new_tab_stop, state=tk.DISABLED)
        self.new_stop_button.pack(side=tk.LEFT, padx=(0, 5))
        self.new_status_var = tk.StringVar(value="")
        tk.Label(btn_frame, textvariable=self.new_status_var, font=('Helvetica', 9)).pack(side=tk.LEFT, padx=10)

        # New tab: Type selector (Tag / Z)
        self.new_tab_mode_frame = tk.Frame(new_left)
        self.new_tab_mode_frame.pack(fill=tk.X, pady=(0, 5))
        tk.Label(self.new_tab_mode_frame, text="Type:").pack(side=tk.LEFT, padx=(0, 5))
        self.new_tab_mode_var = tk.StringVar(value="Z")
        self.new_tab_mode_dropdown = ttk.Combobox(self.new_tab_mode_frame, textvariable=self.new_tab_mode_var, state="readonly", width=10)
        self.new_tab_mode_dropdown['values'] = ("Tag", "Z")
        self.new_tab_mode_dropdown.pack(side=tk.LEFT, padx=(0, 5))
        self.new_tab_mode_dropdown.bind("<<ComboboxSelected>>", self._on_mode_change)

        tk.Label(new_left, text="User Requirement:").pack(anchor=tk.W, pady=(0, 5))
        self.new_requirement_box = scrolledtext.ScrolledText(new_left, height=20, width=80)
        self.new_requirement_box.pack(fill=tk.BOTH, expand=True)

        # Task Action Bar - for opening/running task.json after workflow completes
        task_action_frame = tk.Frame(new_left)
        task_action_frame.pack(fill=tk.X, pady=(5, 0))
        self.new_open_json_button = tk.Button(task_action_frame, text="Open JSON", command=self.new_tab_open_task, state=tk.DISABLED)
        self.new_open_json_button.pack(side=tk.LEFT, padx=(0, 5))
        self.new_run_comfyui_button = tk.Button(task_action_frame, text="Run ComfyUI", command=self.new_tab_run_comfyui, state=tk.DISABLED)
        self.new_run_comfyui_button.pack(side=tk.LEFT, padx=(0, 5))
        self.new_stop_comfyui_button = tk.Button(task_action_frame, text="Stop", command=self.new_tab_stop_comfyui, state=tk.DISABLED)
        self.new_stop_comfyui_button.pack(side=tk.LEFT, padx=(0, 5))
        self.new_browse_task_button = tk.Button(task_action_frame, text="Browse Task", command=self.new_tab_browse_task)
        self.new_browse_task_button.pack(side=tk.LEFT, padx=(0, 5))
        self.new_task_path_var = tk.StringVar(value="No task loaded")
        tk.Label(task_action_frame, textvariable=self.new_task_path_var, font=('Helvetica', 8), fg='#666666').pack(side=tk.LEFT, padx=(10, 0))

        # ComfyUI workflow template selector
        self.comfyui_frame = tk.Frame(new_left)
        self.comfyui_frame.pack(fill=tk.X, pady=(5, 0))
        tk.Label(self.comfyui_frame, text="ComfyUI:").pack(side=tk.LEFT, padx=(0, 5))
        self.comfyui_template_var = tk.StringVar(value="wan_image")
        self.comfyui_template_dropdown = ttk.Combobox(self.comfyui_frame, textvariable=self.comfyui_template_var, state="readonly", width=20)
        self.comfyui_template_dropdown.pack(side=tk.LEFT, padx=(0, 5))

        # Right pane: log panel
        new_right = tk.Frame(new_split)
        new_right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(5, 0))
        tk.Label(new_right, text="Log:", anchor=tk.W).pack(anchor=tk.W, pady=(0, 3))
        self.new_log_window = scrolledtext.ScrolledText(new_right, height=20, state='disabled', width=60)
        self.new_log_window.pack(fill=tk.BOTH, expand=True)
        self.new_log_queue = Queue()
        self.new_tab_last_job_id = None

        # Copy Log button (New tab)
        new_log_btn_frame = tk.Frame(new_right)
        new_log_btn_frame.pack(fill=tk.X, pady=(5, 0))
        self.new_copy_log_button = tk.Button(
            new_log_btn_frame, text="Copy Log", command=self._new_tab_copy_log, width=10
        )
        self.new_copy_log_button.pack(side=tk.LEFT, padx=(0, 5))

        # WAN Tab
        wan_tab = tk.Frame(self.main_notebook)
        self.main_notebook.add(wan_tab, text="WAN")

        # LTX Tab
        self.ltx_tab = tk.Frame(self.main_notebook)
        self.main_notebook.add(self.ltx_tab, text="LTX")

        # Prompt Tab
        self.prompt_tab = tk.Frame(self.main_notebook)
        self.main_notebook.add(self.prompt_tab, text="Prompt")

        # Image Tab
        self.image_tab = tk.Frame(self.main_notebook)
        self.main_notebook.add(self.image_tab, text="Image")

        # --- Video Tab ---
        self.video_tab = tk.Frame(self.main_notebook)
        self.main_notebook.add(self.video_tab, text="Video")
        from video_tab import create_video_tab
        self.video_tab_ui = create_video_tab(self.video_tab, self.root)

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
        self.canvas = tk.Canvas(wan_list)
        self.scrollbar = tk.Scrollbar(wan_list, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = tk.Frame(self.canvas)
        self.scrollable_frame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas_window = self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        self.scrollable_frame.bind_all("<MouseWheel>", self._on_mousewheel)
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
        self.root.bind_all("<Control-v>", self.handle_paste, add="+"); self.root.after(100, self.process_log_queue); self.root.after(100, self.ltx_process_log_queue); self.root.after(100, self.prompt_process_log_queue); self.root.after(100, self.image_process_log_queue); self.root.after(100, self.new_tab_process_log_queue); self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        os.makedirs(INPUT_FOLDER, exist_ok=True); os.makedirs(OUTPUT_FOLDER, exist_ok=True); os.makedirs(WORKFLOW_TEMPLATE_DIR, exist_ok=True); os.makedirs(PROCESSED_WORKFLOW_FOLDER, exist_ok=True); os.makedirs(LTX_PROJECT_DIR, exist_ok=True); os.makedirs(LTX_WORKFLOW_DIR, exist_ok=True); os.makedirs(os.path.join(SCRIPT_DIR, "debug_workflows"), exist_ok=True)
        self.ltx_running = False; self.ltx_paused = False; self.ltx_cancel_event = threading.Event(); self.ltx_log_queue = Queue(); self.prompt_running = False; self.prompt_log_queue = Queue(); self.image_running = False; self.image_log_queue = Queue()
        self.new_tab_comfyui_cancel_event = threading.Event()
        self.new_tab_comfyui_running = False
        self.load_state(); self._load_and_populate_task_types(); self._load_prompt_templates(); self._load_image_tasks(); self.load_logs_into_ui()
        # Populate ComfyUI workflow dropdown with checkpoint options
        checkpoint_options = TemplateCatalog.get_checkpoint_options()
        if checkpoint_options:
            self.comfyui_template_dropdown['values'] = checkpoint_options
            self.comfyui_template_var.set(checkpoint_options[0])
        else:
            self.comfyui_template_dropdown['values'] = []
            self.comfyui_template_var.set("pornmaster_proSDXLV8.safetensors")
        self.conditioning_files = {}; self.latent_files = {}
        # New tab task tracking
        self.new_tab_current_task = ""

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
                if task_names:
                    self.task_type_dropdown['values'] = task_names
                    # Default to wan2.2 if available, otherwise use first task
                    default_task = 'wan2.2' if 'wan2.2' in task_names else task_names[0]
                    self.task_type_var.set(default_task)
        except: pass

    def _run_audio_inference(self, row_id, pos, neg):
        try:
            fe = os.path.exists(AUDIO_GENERATION_REQUESTS_TSV)
            with open(AUDIO_GENERATION_REQUESTS_TSV, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f, delimiter='	')
                if not fe: writer.writerow(["file_id", "positive_prompt", "negative_prompt"])
                writer.writerow([row_id, pos, neg])
        except Exception as e: self.log(f"ERROR saving audio request: {e}")

    def _on_canvas_configure(self, event):
        self.canvas.itemconfig(self.canvas_window, width=event.width)

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
            video_prompt_val = state.get("video_prompt", ""); audio_prompt_val = state.get("audio_prompt", ""); seconds_val = state.get("seconds", "6"); width_val = state.get("width", state.get("side", "720")); category_val = state.get("category", "NA"); upscale_val = state.get("upscale", False); audio_val = state.get("audio", False); batch_val = state.get("batch", "1")
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
            current_image_path = os.path.join(INPUT_FOLDER, filename); video_prompt_val, audio_prompt_val = "", ""; seconds_val, width_val = "6", "720"; category_val, upscale_val, audio_val = "NA", False, False; batch_val = "1"
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
        tk.Label(info_frame, text="Width:").grid(row=2, column=2, sticky=tk.W)
        width_ent = tk.Entry(info_frame); width_ent.insert(0, width_val); width_ent.grid(row=2, column=3, sticky=tk.EW)
        tk.Label(info_frame, text="Cat:").grid(row=3, column=0, sticky=tk.W)
        cats = ["NA", "Sitting_panites", "Standing_panties","Standing_butt", "Masturbation", "Oral", "Cowgirl",  "Kiss", "Doggy", "Missionary"]
        cat_var = tk.StringVar(value=category_val); ttk.Combobox(info_frame, textvariable=cat_var, values=cats, state="readonly").grid(row=3, column=1, columnspan=3, sticky=tk.EW)
        tk.Label(info_frame, text="Batch:").grid(row=4, column=0, sticky=tk.W)
        batch_ent = tk.Entry(info_frame); batch_ent.insert(0, batch_val); batch_ent.grid(row=4, column=1, sticky=tk.EW)
        ctrl_frame = tk.Frame(row_frame); ctrl_frame.pack(side=tk.RIGHT, padx=5)
        up_var = tk.BooleanVar(value=upscale_val); tk.Checkbutton(ctrl_frame, text="Up", var=up_var).pack(anchor=tk.W)
        aud_var = tk.BooleanVar(value=audio_val); tk.Checkbutton(ctrl_frame, text="Aud", var=aud_var).pack(anchor=tk.W)
        tk.Button(ctrl_frame, text="Del", command=lambda: self.delete_row(row_frame)).pack()
        row_data = {"frame": row_frame, "image_path": current_image_path, "filename_base": filename_base, "filename": fn_ent, "video_prompt": vp_ent, "audio_prompt": ap_ent, "seconds": sec_ent, "width": width_ent, "category": cat_var, "upscale": up_var, "audio": aud_var, "batch": batch_ent}
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
            to_save.append({"image_path": r["image_path"], "filename": r["filename"].get(), "filename_base": r["filename_base"], "video_prompt": r["video_prompt"].get(), "audio_prompt": r["audio_prompt"].get(), "seconds": r["seconds"].get(), "width": r["width"].get(), "category": r["category"].get(), "upscale": r["upscale"].get(), "audio": r["audio"].get(), "batch": r["batch"].get()})
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
            configs.append({"filename_base": r["filename_base"], "image_path": r["image_path"], "video_prompt": r["video_prompt"].get(), "audio_prompt": r["audio_prompt"].get(), "seconds": r["seconds"].get(), "width": r["width"].get(), "category": r["category"].get(), "upscale": r["upscale"].get(), "audio": r["audio"].get(), "batch": r["batch"].get()})
        self.cancel_event.clear(); self.set_ui_state(True)
        threading.Thread(target=self._run_processing_thread, args=(sel_task, configs), daemon=True).start()

    def wait_for_completion(self, prompt_id, timeout=3600, cancel_event=None):
        """Wait for a ComfyUI workflow to complete.
        
        Uses WebSocket for real-time detection, with HTTP polling as fallback.
        Returns the history entry dict, or None if timed out or cancelled.
        """
        # Use the new WebSocket-based waiter from comfyui_image_utils
        # Use provided cancel_event or default to self.cancel_event
        target_cancel = cancel_event if cancel_event is not None else self.cancel_event
        
        result = wait_for_execution(
            comfyui_url=COMFYUI_URL,
            prompt_id=prompt_id,
            cancel_event=target_cancel,
            timeout=timeout
        )
        return result

    def cancel_processing(self):
        if self.is_running: self.log("--- Cancellation requested ---"); self.cancel_event.set()

    def clear_all_rows(self):
        if not self.is_running:
            for r in self.rows: r["frame"].destroy()
            self.rows.clear()

    def _apply_placeholders(self, wf_json, jid, row, vp=None, ap=None, job_files=None, prev_step_suffix="", step_suffix="", step_random_number=None, wf_name="", selected_task=""):
        if job_files is None: job_files = {}
        if step_random_number is None: step_random_number = random.randint(1, 999999999999999)

        # ========== LoRA & Checkpoint Lookup ==========
        lora_replacements = {}
        cat = row.get("category", "NA")
        if (cat == "NA" or not cat) and "main_sex_act" in row:
             acts = row["main_sex_act"]
             if isinstance(acts, list) and acts: cat = acts[0]
             elif isinstance(acts, str): cat = acts
        
        if cat and cat != "NA":
            is_image = "image" in selected_task.lower() or "image" in wf_name.lower()
            csv_name = "image_lora_lookup.csv" if is_image else "lora_lookup.csv"
            csv_path = os.path.join(SCRIPT_DIR, "lookup", csv_name)
            if os.path.exists(csv_path):
                t_filter = "image" if is_image else "video"
                w_filter = wf_name if is_image else None
                try:
                    lookup_data = load_lora_lookup(csv_path=csv_path, filter_type=t_filter, workflow_name=w_filter)
                    cat_loras = lookup_data.get(cat.lower())
                    if cat_loras:
                        for i, lora in enumerate(cat_loras):
                            if i < 5:
                                lora_replacements[f"**lora{i+1}_name**"] = lora['name']
                                lora_replacements[f"**lora{i+1}_strength**"] = lora['strength']
                except Exception as e: self.log(f"DEBUG: LoRA lookup error: {e}")
        
        # Defaults for missing LoRAs
        for i in range(1, 6):
            if f"**lora{i}_name**" not in lora_replacements:
                lora_replacements[f"**lora{i}_name**"] = "xl\\add-detail.safetensors"
                lora_replacements[f"**lora{i}_strength**"] = 0.0
        
        checkpoint_val = "pornmaster_proSDXLV8.safetensors"
        # ========== END LoRA Lookup ==========

        # Define all possible replacements
        replacements = {
            "**prompt**": vp if vp else row.get("video_prompt", row.get("first_frame_image_prompt", "")),
            "**width**": row.get("width", "1024"),
            "**height**": row.get("height", row.get("width", "1024")),
            "**length**": row.get("length", "241"),
            "**fps**": row.get("fps", "24"),
            "**image**": job_files.get("image", f"{jid}.png"),
            "**work_id**": jid,
            "**video_width**": row.get("width", "1024"),
            "**video_height**": row.get("height", row.get("width", "1024")),
            "**video_seconds**": row.get("seconds", "6"),
            "**video_pos_prompt**": vp if vp else row.get("video_prompt", row.get("first_frame_image_prompt", "")),
            "**image_pos_prompt**": vp if vp else row.get("video_prompt", row.get("first_frame_image_prompt", "")),
            "**image_neg_prompt**": "lowres, bad anatomy, bad hands, text, error, missing fingers, extra digit, fewer digits, cropped, worst quality, low quality, normal quality, jpeg artifacts, signature, watermark, username, blurry",
            "**negative_prompt**": "lowres, bad anatomy, bad hands, text, error, missing fingers, extra digit, fewer digits, cropped, worst quality, low quality, normal quality, jpeg artifacts, signature, watermark, username, blurry",
            "**audio_prompt**": ap if ap else row.get("audio_prompt", ""),
            "**load_pos_conditioning**": job_files.get("pos", f"pos_{jid}"),
            "**load_neg_conditioning**": job_files.get("neg", f"neg_{jid}"),
            "**save_pos_conditioning**": f"pos_{jid}",
            "**save_neg_conditioning**": f"neg_{jid}",
            "**load_latent**": job_files.get("lat") if job_files.get("lat") else f"lat_{jid}{prev_step_suffix}_00001_.latent",
            "**save_latent**": f"lat_{jid}{step_suffix}",
            "**load_image**": f"{jid}.png",
            "**save_video**": jid,
            "**job_id_in**": jid,
            "**job_id_out**": jid + "_upscaled",
            "**row_id**": jid,
            "**finish_indicator**": jid,
            "**random_number**": step_random_number,
            "**checkpoint**": checkpoint_val
        }
        replacements.update(lora_replacements)

        for node_id, node in wf_json.items():
            cls = node.get("class_type", "")
            inputs = node.get("inputs", {})
            for k, v in inputs.items():
                if not isinstance(v, str): continue
                new_val = v
                for placeholder, repl_val in replacements.items():
                    if placeholder in new_val:
                        if cls == "JWInteger" or placeholder == "**random_number**" or "strength" in placeholder:
                            try:
                                if "strength" in placeholder: new_val = float(repl_val)
                                else: new_val = int(repl_val)
                            except: new_val = str(repl_val)
                            break 
                        else:
                            new_val = new_val.replace(placeholder, str(repl_val))
                inputs[k] = new_val
        return wf_json

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
            task_steps = self.get_task_steps(selected_task)
            
            for step_idx, (wf_name, save_video, use_cat) in enumerate(task_steps):
                if self.cancel_event.is_set(): break
                self.log(f"--- Step {step_idx + 1}/{len(task_steps)}: '{wf_name}' ---")

                for job in flat_jobs:
                    if self.cancel_event.is_set(): break
                    jid = job["job_id"]; row = job["row_ref"]
                    
                    if wf_name == 'audio_generation':
                        if row["audio"]:
                            c = row["category"]; p = self._get_prompt_from_tsv(AUDIO_PROMPT_TSV, c) if c != "NA" else None
                            self._run_audio_inference(jid, p if p else row["audio_prompt"], "harsh, music, noise")
                        else: self.log(f"DEBUG: Skipping audio for {jid}")
                        continue

                    if wf_name == 'FlashSVR' and not row["upscale"]:
                        self.log(f"DEBUG: Skipping FlashSVR for {jid}"); continue

                    wf_path = TemplateCatalog._resolve_template_path(wf_name)
                    if wf_path is None:
                        # Fallback: try category-specific variant in root
                        if use_cat == 'yes' and row["category"] != 'NA':
                            spec = os.path.join(WORKFLOW_TEMPLATE_DIR, f"{wf_name}_{row['category'].lower()}.json")
                            if os.path.exists(spec): wf_path = spec
                    if wf_path is None: continue
                    
                    try:
                        with open(wf_path, 'r', encoding='utf-8') as f: wf_str = f.read()
                        wf_json = json.loads(wf_str)
                    except: continue

                    vp = self._get_prompt_from_tsv(VIDEO_PROMPT_TSV, row["category"]) if row["category"] != "NA" else None
                    ap = self._get_prompt_from_tsv(AUDIO_PROMPT_TSV, row["category"]) if row["category"] != "NA" else None
                    job_files = self.discovered_outputs.get(jid, {})
                    
                    actual_step_idx = step_idx
                    if "_step" in wf_name:
                        try:
                            parts = wf_name.split("_step"); num_part = parts[-1]; num_str = ""
                            for char in num_part:
                                if char.isdigit(): num_str += char
                                else: break
                            if num_str: actual_step_idx = int(num_str)
                        except: pass
                    
                    prev_step_suffix = f"_s{actual_step_idx - 1}"; step_suffix = f"_s{actual_step_idx}"
                    step_random_number = random.randint(1, 999999999999999)

                    wf_json = self._apply_placeholders(wf_json, jid, row, vp=vp, ap=ap, job_files=job_files, prev_step_suffix=prev_step_suffix, step_suffix=step_suffix, step_random_number=step_random_number, wf_name=wf_name, selected_task=selected_task)

                    wf_str = json.dumps(wf_json, indent=4)
                    with open(os.path.join(debug_dir, f"{jid}_step{actual_step_idx}_{wf_name}.json"), 'w', encoding='utf-8') as f: f.write(wf_str)

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
            if resp.ok: 
                return payload['prompt_id']
            else:
                msg = f"ComfyUI Error: {resp.status_code} - {resp.text}"
                self.new_log_queue.put(msg)
                self.log(msg)
        except Exception as e:
            msg = f"Error sending to ComfyUI: {e}"
            self.new_log_queue.put(msg)
            self.log(msg)
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
        general_md_path = os.path.join(LTX_PROMPTS_DIR, "multiple-scene-videos.md"); user_prompt_md_path = os.path.join(LTX_PROMPTS_DIR, "user-prompt.md"); general_json_path = os.path.join(LTX_PROMPTS_DIR, "multiple-scene-videos.json")
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
        self.prompt_template_dropdown['values'] = TemplateCatalog.get_prompt_template_options()
        if self.prompt_template_dropdown['values']:
            self.prompt_template_var.set(self.prompt_template_dropdown['values'][0])

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
        self.image_task_dropdown['values'] = TemplateCatalog.get_image_task_options()
        if self.image_task_dropdown['values']:
            self.image_task_var.set(self.image_task_dropdown['values'][0])

    def _refresh_image_tasks(self): self._load_image_tasks()
    def image_process_log_queue(self):
        if self.image_log_queue.empty(): self.root.after(100, self.image_process_log_queue); return
        self.image_log_window.configure(state='normal')
        while not self.image_log_queue.empty():
            item = self.image_log_queue.get_nowait(); self.image_log_window.insert(tk.END, str(item) + "\n")
        self.image_log_window.configure(state='disabled'); self.image_log_window.see(tk.END); self.root.after(100, self.image_process_log_queue)

    def new_tab_process_log_queue(self):
        if self.new_log_queue.empty():
            self.root.after(100, self.new_tab_process_log_queue)
            return
        self.new_log_window.configure(state='normal')
        while not self.new_log_queue.empty():
            item = self.new_log_queue.get_nowait()
            if isinstance(item, StreamChunk):
                self.new_log_window.insert(tk.END, item.content)
            else:
                self.new_log_window.insert(tk.END, str(item) + "\n")
        lc = self.new_log_window.get("1.0", tk.END)
        lines = lc.count('\n')
        if lines > 2000:
            self.new_log_window.delete("1.0", f"{lines - 1000}.0")
        self.new_log_window.configure(state='disabled')
        self.new_log_window.see(tk.END)
        self.root.after(100, self.new_tab_process_log_queue)

    def _on_mode_change(self, event=None):
        """Handle Type dropdown change - grey out ComfyUI template in Z mode."""
        mode = self.new_tab_mode_var.get()
        if mode == "Z":
            self.comfyui_template_dropdown.config(state="disabled")
            self.comfyui_template_var.set("z-image")
        else:
            self.comfyui_template_dropdown.config(state="readonly")
            try:
                options = TemplateCatalog.get_wan_workflow_options()
                if options:
                    self.comfyui_template_dropdown['values'] = options
                    if self.comfyui_template_var.get() not in options:
                        self.comfyui_template_var.set(options[0] if options else "wan_image")
            except:
                pass

    def new_tab_stop(self):
        """Called when the user clicks the Stop button."""
        if hasattr(self, 'new_tab_stop_event') and self.new_tab_stop_event:
            self.new_tab_stop_event.set()
            self.new_status_var.set("Stopping...")

    def new_tab_stop_comfyui(self):
        """Called when the user clicks the Stop button during ComfyUI execution."""
        if hasattr(self, 'new_tab_comfyui_cancel_event') and self.new_tab_comfyui_cancel_event:
            self.new_tab_comfyui_cancel_event.set()
            self.new_status_var.set("Stopping ComfyUI...")

    def image_start_run(self):
        if self.image_running: return
        self.image_running = True; self.image_run_button.config(state=tk.DISABLED)
        threading.Thread(target=self._image_run_thread, daemon=True).start()

    def _image_run_thread(self):
        try:
            task_file = self.image_task_var.get()
            with open(os.path.join(LTX_PROJECT_DIR, "tasks", task_file), 'r', encoding='utf-8') as f: data = json.load(f)
            scenes = data.get("scenes", []); job_id = time.strftime("%Y%m%d_%H%M%S")
            
            wf_path = os.path.join(WORKFLOW_TEMPLATE_DIR, "image", "pornmaster_proSDXLV8.json")
            if not os.path.exists(wf_path):
                self.log(f"ERROR: pornmaster_proSDXLV8.json template not found at {wf_path}"); return

            res = self.image_resolution_var.get().split('*')
            width = res[0]; height = res[1] if len(res) > 1 else res[0]

            for idx, sc in enumerate(scenes):
                jid = f"{job_id}_{idx+1}"
                with open(wf_path, 'r', encoding='utf-8') as f: wf_json = json.load(f)
                
                row = {
                    "width": width, "height": height,
                    "first_frame_image_prompt": sc.get("first_frame_image_prompt", ""),
                    "main_sex_act": sc.get("main_sex_act", sc.get("sex_loras", []))
                }
                
                wf_json = self._apply_placeholders(wf_json, jid, row, wf_name="wan_image", selected_task="wan_image")
                wf_str = json.dumps(wf_json, indent=4)
                
                debug_dir = os.path.join(SCRIPT_DIR, "debug_workflows"); os.makedirs(debug_dir, exist_ok=True)
                with open(os.path.join(debug_dir, f"{jid}_pornmaster_proSDXLV8.json"), 'w', encoding='utf-8') as f: f.write(wf_str)
                
                self.send_workflow_to_comfyui(wf_str, jid)
                self.log(f"Sent {jid} to ComfyUI (Image process)")
                time.sleep(0.5)
        except Exception as e: self.log(f"Image Error: {e}")
        finally: self.image_running = False; self.root.after(0, lambda: self.image_run_button.config(state=tk.NORMAL))

    def _edit_long_text(self, entry, title="Edit Text"):
        win = tk.Toplevel(self.root); win.title(title); win.geometry("500x300")
        txt = scrolledtext.ScrolledText(win, wrap=tk.WORD, height=10); txt.insert(tk.END, entry.get()); txt.pack(expand=True, fill=tk.BOTH)
        def save(): entry.delete(0, tk.END); entry.insert(0, txt.get("1.0", tk.END).strip()); win.destroy()
        tk.Button(win, text="Save", command=save).pack(side=tk.LEFT, padx=20); tk.Button(win, text="Cancel", command=win.destroy).pack(side=tk.RIGHT, padx=20)

    def new_tab_select_task(self, task_path):
        """Load a task.json file path and enable the action buttons."""
        self.new_tab_current_task = task_path
        self.new_task_path_var.set(task_path)
        if os.path.exists(task_path):
            self.new_open_json_button.config(state=tk.NORMAL)
            self.new_run_comfyui_button.config(state=tk.NORMAL)
        else:
            self.new_open_json_button.config(state=tk.DISABLED)
            self.new_run_comfyui_button.config(state=tk.DISABLED)

    def new_tab_open_task(self):
        """Open the current task.json in the system default text editor."""
        task_path = self.new_tab_current_task
        if not task_path or not os.path.exists(task_path):
            self.new_status_var.set("No task loaded")
            return
        try:
            if os.name == 'nt':
                os.startfile(task_path)
            elif os.name == 'posix':
                subprocess.call(['open', task_path])
            else:
                subprocess.call(['xdg-open', task_path])
        except Exception as e:
            self.new_status_var.set(f"Error opening: {e}")

    def new_tab_browse_task(self):
        """Show file dialog to manually select a task.json file."""
        initial_dir = os.path.dirname(self.new_tab_current_task) if self.new_tab_current_task and os.path.dirname(self.new_tab_current_task) else os.path.join(SCRIPT_DIR, "tasks")
        file_path = filedialog.askopenfilename(
            title="Select Task JSON",
            initialdir=initial_dir,
            filetypes=[("JSON Files", "*.json"), ("All Files", "*.*")]
        )
        if file_path:
            self.new_tab_select_task(file_path)
            self.new_status_var.set(f"Selected task: {os.path.basename(file_path)}")

    def new_tab_run_comfyui(self):
        """Run ComfyUI image generation for each scene in the loaded task.json.
        
        Sends workflows one-by-one, waits for completion (like WAN tab), and
        logs progress for each job.
        """
        task_path = self.new_tab_current_task
        if not task_path or not os.path.exists(task_path):
            self.new_status_var.set("No task loaded")
            return
        self.new_run_comfyui_button.config(state=tk.DISABLED)
        self.new_stop_comfyui_button.config(state=tk.NORMAL)
        self.new_status_var.set("Generating workflows...")
        selected_template = self.comfyui_template_var.get()

        def run_thread():
            try:
                with open(task_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                job_id = data.get("job_id", "unknown")
                locations = data.get("location_design", {}).get("locations", [])
                task_mode = data.get("mode", "Tag")
                num_locations = len(locations)
                resolution = self.image_resolution_var.get()  # e.g., "1024*1024"

                self.new_log_queue.put(f"--- Starting ComfyUI: {job_id} ---")
                self.root.after(0, lambda: self.new_status_var.set(
                    f"Processing {job_id}: {num_locations} location(s) in {task_mode} mode..."))

                # Count total workflows for progress reporting
                total_workflows = 0
                for loc in locations:
                    prompts = loc.get("prompts", [])
                    total_workflows += len(prompts) if prompts else 1

                current_workflow = 0
                self.new_tab_comfyui_cancel_event.clear()

                for scene_idx in range(num_locations):
                    if self.new_tab_comfyui_cancel_event.is_set():
                        self.new_log_queue.put("--- ComfyUI cancelled ---")
                        self.root.after(0, lambda: self.new_status_var.set("Cancelled"))
                        break

                    loc = locations[scene_idx]
                    loc_name = loc.get("location", f"location_{scene_idx}")

                    prompts = loc.get("prompts", [])
                    num_prompts = len(prompts) if prompts else 1
                    base_name = f"{job_id}_scene{scene_idx}"

                    for prompt_idx in range(num_prompts):
                        if self.new_tab_comfyui_cancel_event.is_set():
                            self.new_log_queue.put("--- ComfyUI cancelled ---")
                            self.root.after(0, lambda: self.new_status_var.set("Cancelled"))
                            break

                        current_workflow += 1
                        display_idx = scene_idx + 1
                        prompt_label = f"Prompt {prompt_idx+1}/{num_prompts}"
                        progress_label = f"{current_workflow}/{total_workflows}"

                        self.new_log_queue.put(
                            f"[{progress_label}] Scene {display_idx}/{num_locations} ({prompt_label}): {loc_name}")
                        self.root.after(0, lambda n=loc_name, i=display_idx, p=prompt_label, t=total_workflows, c=current_workflow:
                            self.new_status_var.set(
                                f"Scene {i}/{num_locations} ({p}) [{c}/{t}]: {n}"))

                        actual_prompt_idx = min(prompt_idx, len(prompts) - 1) if prompts else 0

                        from parameter_extraction import extract_params_from_new_tab_task
                        params = extract_params_from_new_tab_task(
                            task_path,
                            scene_index=scene_idx,
                            resolution=resolution,
                            prompt_index=actual_prompt_idx
                        )

                        if task_mode == "Z":
                            workflow = TemplateCatalog.load_template("z-image")
                            params_dict = dict(params.for_wan_image())
                            params_dict["width"] = params.width
                            params_dict["height"] = params.height
                            params_dict["steps"] = 8
                            params_dict["cfg"] = 1
                            params_dict["sampler_name"] = "res_multistep"
                            params_dict["scheduler"] = "simple"
                            params_dict["checkpoint"] = "zImageTurboNSFW_50BF16Diffusion.safetensors"
                            params_dict["random_number"] = params.random_number
                            for i in range(1, 6):
                                params_dict[f"lora{i}_name"] = "xl\\add-detail.safetensors"
                                params_dict[f"lora{i}_strength"] = 0.0
                        else:
                            params_dict = dict(params.for_wan_image())
                            lora_names = [p.get("lora_name", "") for p in getattr(params, "sex_loras", [])]
                            lora_strengths = [0.7] * len(getattr(params, "sex_loras", []))
                            from workflow_generator import _resolve_lora_params
                            lora_resolved = _resolve_lora_params(
                                params.main_sex_act if hasattr(params, 'main_sex_act') else [],
                                "image_lora_lookup.csv",
                                workflow_name=selected_template,
                                extra_lora_names=lora_names,
                                extra_lora_strengths=lora_strengths,
                            )
                            params_dict.update(lora_resolved)
                            params_dict["checkpoint"] = selected_template
                            workflow = TemplateCatalog.load_template("wan_image")

                        workflow = apply_placeholders_unified(workflow, params_dict)
                        debug_filename = f"{base_name}_p{actual_prompt_idx}" + ("_z" if task_mode == "Z" else f"_{selected_template}")

                        workflow_str = json.dumps(workflow)

                        debug_dir = os.path.join(SCRIPT_DIR, "debug_workflows")
                        os.makedirs(debug_dir, exist_ok=True)
                        scene_file = os.path.join(debug_dir, debug_filename)
                        with open(scene_file, 'w', encoding='utf-8') as f:
                            f.write(workflow_str)

                        # Send to ComfyUI and get prompt_id
                        prompt_id = self.send_workflow_to_comfyui(workflow_str, f"{base_name}_p{actual_prompt_idx}")
                        if not prompt_id:
                            self.new_log_queue.put(f"ERROR sending Scene {display_idx} ({prompt_label}) to ComfyUI")
                            continue

                        self.new_log_queue.put(
                            f"[{progress_label}] Scene {display_idx} ({prompt_label}) queued (prompt_id: {prompt_id})")

                        # Wait for completion (blocking, like WAN tab)
                        hist = self.wait_for_completion(prompt_id, cancel_event=self.new_tab_comfyui_cancel_event)
                        if self.new_tab_comfyui_cancel_event.is_set():
                            self.new_log_queue.put("--- ComfyUI cancelled during wait ---")
                            self.root.after(0, lambda: self.new_status_var.set("Cancelled"))
                            break

                        if hist:
                            status = hist.get("status", {})
                            errors = status.get("errors", {})
                            if errors:
                                error_msg = str(errors)
                                self.new_log_queue.put(
                                    f"[{progress_label}] Scene {display_idx} ({prompt_label}) FAILED: {error_msg}")
                            else:
                                self.new_log_queue.put(
                                    f"[{progress_label}] Scene {display_idx} ({prompt_label}) done")
                        else:
                            self.new_log_queue.put(
                                f"[{progress_label}] Scene {display_idx} ({prompt_label}) timed out or cancelled")

                        # Discover and save generated image with metadata
                        try:
                            saved_image_path = self._discover_and_save_image_with_metadata(
                                hist, 
                                f"{base_name}_p{actual_prompt_idx}",
                                loc,
                                prompt_label,
                                progress_label,
                                prompt_index=actual_prompt_idx
                            )
                            if saved_image_path:
                                self.new_log_queue.put(
                                    f"[{progress_label}] Image saved: {os.path.basename(saved_image_path)}")
                        except Exception as e:
                            self.new_log_queue.put(
                                f"[{progress_label}] Warning: Could not save image metadata: {e}")

                        time.sleep(0.5)  # Small delay between jobs (like WAN tab)

                # Final status
                if not self.new_tab_comfyui_cancel_event.is_set():
                    self.new_log_queue.put(f"--- Done: {total_workflows} workflows processed ---")
                    self.root.after(0, lambda: self.new_status_var.set(f"Done: {total_workflows} workflows"))
                    self.new_tab_last_job_id = job_id

            except Exception as e:
                import traceback
                self.new_log_queue.put(f"Error: {e}\n{traceback.format_exc()}")
                self.root.after(0, lambda: self.new_status_var.set(f"Error: {str(e)[:50]}"))
            finally:
                self.root.after(0, lambda: self.new_run_comfyui_button.config(state=tk.NORMAL))
                self.root.after(0, lambda: self.new_stop_comfyui_button.config(state=tk.DISABLED))

        threading.Thread(target=run_thread, daemon=True).start()

    def new_tab_run_ltx_video_generation(self):
        """
        Entry point to start LTX video generation from the New Tab workflow.
        Reads task.json, converts to batch tasks, and starts the batch runner.
        """
        import threading
        from projects.ltx.batch_runner import BatchRunner
        from projects.ltx.parameter_extraction import new_tab_task_to_ltx_batch_tasks
        
        if not hasattr(self, 'new_tab_last_job_id') or not self.new_tab_last_job_id:
            self.new_log_queue.put("No job to run — please complete the New Tab workflow first.")
            return
        
        job_id = self.new_tab_last_job_id
        task_path = os.path.join("tasks", job_id, "task.json")
        
        if not os.path.exists(task_path):
            self.new_log_queue.put(f"task.json not found: {task_path}")
            return
        
        try:
            tasks = new_tab_task_to_ltx_batch_tasks(task_path)
            self.new_log_queue.put(f"Converted {len(tasks)} tasks for LTX video generation")
            
            if not tasks:
                self.new_log_queue.put("No tasks to run for video generation.")
                return
            
            # Start batch runner in background
            def run_ltx_batch():
                runner = BatchRunner(
                    comfyui_url=self.comfyui_url if hasattr(self, 'comfyui_url') else None,
                    output_folder=self.output_folder if hasattr(self, 'output_folder') else None,
                    input_folder=self.input_folder if hasattr(self, 'input_folder') else None,
                    processed_folder=self.processed_folder if hasattr(self, 'processed_folder') else None,
                    log_func=lambda msg: self.root.after(0, lambda m=msg: self.new_log_queue.put(f"[LTX] {m}"))
                )
                result = runner.run_batch(
                    job_id=job_id,
                    tasks=tasks,
                    width=1280,
                    height=720,
                    length=241,
                    fps=24,
                    image_model="pornmaster_proSDXLV8"
                )
                self.root.after(0, lambda: self.new_log_queue.put(
                    f"LTX batch complete: {len(result['completed'])} completed, "
                    f"{len(result['failed'])} failed"
                ))
            
            threading.Thread(target=run_ltx_batch, daemon=True).start()
            self.new_log_queue.put("LTX video generation started in background")
            
        except Exception as e:
            import traceback
            self.new_log_queue.put(f"Error starting LTX video generation: {e}\n{traceback.format_exc()}")

    def _discover_and_save_image_with_metadata(self, history, filename_prefix, location, prompt_label, progress_label, prompt_index=0):
        """
        Discover the generated image from ComfyUI history, download it via
        the /view API, inject metadata, and save it locally.
        
        This method downloads images from a remote ComfyUI server using the
        /view endpoint instead of trying to read from a local filesystem path.
        
        Args:
            history: The ComfyUI history response dict (initial)
            filename_prefix: Prefix for the output filename
            location: The location dict from task.json
            prompt_label: Human-readable prompt label
            progress_label: Progress label like "1/6"
            prompt_index: Index of the current prompt within the location
        
        Returns:
            str: Path to the saved image, or None on failure
        """
        try:
            from PIL import Image as PILImage
            import json
            import time
            import requests
            
            # Extract server address from COMFYUI_URL
            server_address = COMFYUI_URL.split("//")[1].split("/")[0]
            base_url = COMFYUI_URL.split("/prompt")[0]
            
            # Retry loop to get history with outputs (ComfyUI race condition)
            current_history = history
            prompt_id = None
            if current_history and "prompt" in current_history:
                # current_history format: [node_id, prompt_id, prompt_data, extra_data, outputs]
                # Actually, wait_for_execution returns history[prompt_id]
                # which is a dict: {"prompt": [...], "outputs": {...}, "status": {...}}
                pass 
            
            # Try to get prompt_id from history if we need to re-fetch
            # But we don't necessarily have it easily available here unless we pass it.
            # Fortunately, wait_for_execution usually returns the full dict.
            
            for attempt in range(3):
                if current_history and current_history.get("outputs"):
                    break
                
                if attempt < 2:
                    self.new_log_queue.put(f"[{progress_label}] Info: Outputs missing from history, retrying... (Attempt {attempt+1})")
                    time.sleep(2.0)
                    # We can't easily re-fetch without prompt_id. 
                    # Let's hope the initial 'history' we passed was just slightly early.
                
            if not current_history:
                self.new_log_queue.put(f"[{progress_label}] Error: No history object received for job.")
                return None
                
            outputs = current_history.get("outputs", {})
            if not outputs:
                self.new_log_queue.put(f"[{progress_label}] Error: ComfyUI history has no outputs for this job.")
                return None
                
            image_filename = None
            image_subfolder = None
            image_type = "output"
            found_node_id = None
            
            # Priority: find node with 'images' output
            for node_id, node_output in outputs.items():
                if "images" in node_output:
                    for img_info in node_output["images"]:
                        if not image_filename or img_info.get("type") == "output":
                            image_filename = img_info.get("filename")
                            image_subfolder = img_info.get("subfolder", "")
                            image_type = img_info.get("type", "output")
                            found_node_id = node_id
                            if image_type == "output":
                                break
                if image_filename and image_type == "output":
                    break
            
            if not image_filename:
                self.new_log_queue.put(f"[{progress_label}] Warning: No image found in ComfyUI history (Node IDs checked: {list(outputs.keys())})")
                return None
            
            self.new_log_queue.put(f"[{progress_label}] Found image: {image_filename} on node {found_node_id}")
            
            # Download the image via ComfyUI's /view API
            image_data = download_image_from_comfyui(
                server_address=server_address,
                filename=image_filename,
                subfolder=image_subfolder,
                folder_type=image_type
            )
            
            if not image_data:
                self.new_log_queue.put(f"[{progress_label}] Error: Failed to download image {image_filename} from {server_address}")
                return None
            
            self.new_log_queue.put(f"[{progress_label}] Downloaded {len(image_data)} bytes")
            
            # Extract prompts from location
            prompts = location.get("prompts", [])
            image_prompt = ""
            video_prompt = ""
            sex_act = ""
            
            if prompts:
                # Use prompt_index to get the correct metadata
                p_idx = min(prompt_index, len(prompts) - 1)
                current_prompt = prompts[p_idx]
                if isinstance(current_prompt, dict):
                    image_prompt = current_prompt.get("image_prompt", "")
                    video_prompt = current_prompt.get("video_prompt", "")
                    # Try to extract sex_act
                    if "sex_act" in current_prompt:
                        sex_act = current_prompt["sex_act"]
                    elif current_prompt.get("prompt"):
                        if not image_prompt:
                            image_prompt = current_prompt["prompt"]
                else:
                    image_prompt = current_prompt
            
            # Extract sex_act from location metadata if available
            if not sex_act:
                main_sex_act = location.get("main_sex_act", [])
                if main_sex_act:
                    sex_act = main_sex_act[0] if isinstance(main_sex_act[0], str) else str(main_sex_act[0])
            
            # Build metadata dict
            metadata = {
                "prompt": image_prompt,
                "video_prompt": video_prompt,
                "sex_act": sex_act,
                "location": location.get("location", ""),
                "job_id": location.get("job_id", ""),
                "node_id": node_id if 'node_id' in locals() else "unknown"
            }
            
            # Inject metadata into PNG file
            metadata_str = json.dumps(metadata, ensure_ascii=False)
            
            # Decode image from bytes using PIL
            img = PILImage.open(io.BytesIO(image_data))
            
            # Convert to RGBA if needed for PNG
            if img.mode not in ("RGB", "RGBA", "L"):
                img = img.convert("RGBA")
            
            # Create new PNG with metadata
            output_img = PILImage.new("RGBA", img.size)
            output_img.paste(img)
            
            # Save locally with metadata
            output_dir = os.path.join(SCRIPT_DIR, "output_images")
            os.makedirs(output_dir, exist_ok=True)
            
            output_filename = f"{filename_prefix}.png"
            output_path = os.path.join(output_dir, output_filename)
            
            # Save with metadata
            from PIL.PngImagePlugin import PngInfo
            png_info = PngInfo()
            png_info.add_text("prompt", metadata_str)
            output_img.save(output_path, pnginfo=png_info)
            
            return output_path
            
        except Exception as e:
            import traceback
            self.new_log_queue.put(f"[{progress_label}] Error saving image with metadata: {e}")
            print(f"Error saving image with metadata: {e}\n{traceback.format_exc()}")
            return None

    def new_tab_run(self):
        if hasattr(self, 'new_tab_running') and self.new_tab_running:
            return
        requirements = self.new_requirement_box.get("1.0", tk.END).strip()
        if not requirements:
            self.new_status_var.set("Please enter requirements")
            return
        self.new_tab_running = True
        self.new_tab_stop_event = threading.Event()
        self.new_run_button.config(state=tk.DISABLED)
        self.new_stop_button.config(state=tk.NORMAL)
        self.new_status_var.set("Running...")
        # Clear log
        self.new_log_window.configure(state='normal')
        self.new_log_window.delete('1.0', tk.END)
        self.new_log_window.configure(state='disabled')

        mode = self.new_tab_mode_var.get()

        def status_callback(msg, end="\n"):
            self.root.after(0, lambda m=msg, e=end: self.new_log_queue.put(m + e))

        def run_thread():
            try:
                result = run_new_tab_workflow(requirements, status_callback, self.new_tab_stop_event, mode=mode)
                job_id = result.get('job_id', 'unknown')
                task_path = os.path.join(SCRIPT_DIR, "tasks", job_id, "task.json")
                self.root.after(0, lambda: self.new_status_var.set(f"Done: {job_id}"))
                self.root.after(0, lambda: self.new_tab_select_task(task_path))
            except Exception as e:
                self.root.after(0, lambda: self.new_status_var.set(f"Error: {str(e)[:50]}"))
            finally:
                self.new_tab_running = False
                self.root.after(0, lambda: self.new_run_button.config(state=tk.NORMAL))
                self.root.after(0, lambda: self.new_stop_button.config(state=tk.DISABLED))

        threading.Thread(target=run_thread, daemon=True).start()

    def _new_tab_copy_log(self):
        """Copy the New tab log to clipboard."""
        try:
            self.new_log_window.configure(state='normal')
            log_text = self.new_log_window.get("1.0", tk.END)
            self.new_log_window.configure(state='disabled')
            if log_text.strip():
                self.root.clipboard_clear()
                self.root.clipboard_append(log_text)
                self.root.update()
                self.root.after(0, lambda: self.new_status_var.set("Log copied to clipboard"))
            else:
                self.root.after(0, lambda: self.new_status_var.set("Log is empty"))
        except Exception as e:
            self.root.after(0, lambda: self.new_status_var.set(f"Error copying log: {e}"))

if __name__ == "__main__":
    root = tk.Tk(); app = VideoGenerationApp(root); root.mainloop()
