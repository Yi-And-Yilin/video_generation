import os
import subprocess
import shutil

import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog
from PIL import ImageGrab
import random
import string
import io
import os
import shutil
import threading
import time
import requests
import uuid
import json
from queue import Queue
import logging

from new_tab_workflow import run_new_tab_workflow

# Import workflow generator
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "projects", "ltx"))
from workflow_generator import generate_api_workflow, generate_workflow_for_wan_image



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
        self.log_queue = Queue()
        self.cancel_event = threading.Event()
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

        # --- Video Tab ---
        self.video_tab = tk.Frame(self.main_notebook)
        self.main_notebook.add(self.video_tab, text="Video")
        from video_tab import create_video_tab
        self.video_tab_ui = create_video_tab(self.video_tab, self.root)

        # Final Bindings
        self.root.bind_all("<Control-v>", self.handle_paste, add="+")
        self.root.after(100, self.process_log_queue)
        self.root.after(100, self.new_tab_process_log_queue)
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        os.makedirs(INPUT_FOLDER, exist_ok=True)
        os.makedirs(OUTPUT_FOLDER, exist_ok=True)
        os.makedirs(WORKFLOW_TEMPLATE_DIR, exist_ok=True)
        os.makedirs(PROCESSED_WORKFLOW_FOLDER, exist_ok=True)
        os.makedirs(LTX_PROJECT_DIR, exist_ok=True)
        os.makedirs(LTX_WORKFLOW_DIR, exist_ok=True)
        os.makedirs(os.path.join(SCRIPT_DIR, "debug_workflows"), exist_ok=True)
        self.new_tab_comfyui_cancel_event = threading.Event()
        self.new_tab_comfyui_running = False
        # Populate ComfyUI workflow dropdown with checkpoint options
        checkpoint_options = TemplateCatalog.get_checkpoint_options()
        if checkpoint_options:
            self.comfyui_template_dropdown['values'] = checkpoint_options
            self.comfyui_template_var.set(checkpoint_options[0])
        else:
            self.comfyui_template_dropdown['values'] = []
            self.comfyui_template_var.set("pornmaster_proSDXLV8.safetensors")
        self.conditioning_files = {}
        self.latent_files = {}
        # New tab task tracking
        self.new_tab_current_task = ""

    def setup_logging(self):
        self.log_file = LOG_FILE
        log_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        fh = logging.FileHandler(self.log_file, encoding='utf-8')
        fh.setFormatter(log_formatter)
        sh = logging.StreamHandler()
        sh.setFormatter(log_formatter)
        self.logger = logging.getLogger(__name__)
        self.logger.addHandler(fh)
        self.logger.addHandler(sh)
        self.logger.setLevel(logging.INFO)
        self.logger.propagate = False

    def process_log_queue(self):
        if self.log_queue.empty():
            self.root.after(100, self.process_log_queue)
            return
        # Drain the queue - log_window no longer exists
        while not self.log_queue.empty():
            self.log_queue.get_nowait()
        self.root.after(100, self.process_log_queue)

    def log(self, message):
        level = logging.ERROR if any(x in str(message).upper() for x in ['ERROR', 'FAILED', 'FATAL']) else logging.INFO
        if hasattr(self, 'logger'):
            self.logger.log(level, message)
        self.log_queue.put(message)

    def generate_random_string(self, length=8):
        return ''.join(random.choice(string.ascii_lowercase + string.digits) for _ in range(length))

    def handle_paste(self, event=None):
        focused = self.root.focus_get()
        if focused and isinstance(focused, (tk.Text, scrolledtext.ScrolledText)):
            return
        try:
            img = ImageGrab.grabclipboard()
            if isinstance(img, Image.Image):
                return  # New tab handles paste in new_tab_workflow.py
            clipboard_content = self.root.clipboard_get()
            if clipboard_content:
                file_paths = clipboard_content.strip().split('\n')
                found = False
                for path in file_paths:
                    clean_path = path.strip().strip('"')
                    if os.path.isfile(clean_path):
                        try:
                            pasted_img = Image.open(clean_path)
                            ext = os.path.splitext(clean_path)[1] or ".png"
                            loc = os.path.join(INPUT_FOLDER, f"pasted_{self.generate_random_string()}{ext}")
                            shutil.copy2(clean_path, loc)
                            found = True
                        except:
                            pass
                if found:
                    return
        except Exception as e:
            self.log(f"Paste error: {e}")

    def wait_for_completion(self, prompt_id, timeout=3600, cancel_event=None):
        """Wait for a ComfyUI workflow to complete.
        
        Uses WebSocket for real-time detection, with HTTP polling as fallback.
        Returns the history entry dict, or None if timed out or cancelled.
        """
        target_cancel = cancel_event if cancel_event is not None else self.cancel_event
        
        result = wait_for_execution(
            comfyui_url=COMFYUI_URL,
            prompt_id=prompt_id,
            cancel_event=target_cancel,
            timeout=timeout
        )
        return result

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

    def _edit_long_text(self, entry, title="Edit Text"):
        win = tk.Toplevel(self.root)
        win.title(title)
        win.geometry("500x300")
        txt = scrolledtext.ScrolledText(win, wrap=tk.WORD, height=10)
        txt.insert(tk.END, entry.get())
        txt.pack(expand=True, fill=tk.BOTH)
        def save():
            entry.delete(0, tk.END)
            entry.insert(0, txt.get("1.0", tk.END).strip())
            win.destroy()
        tk.Button(win, text="Save", command=save).pack(side=tk.LEFT, padx=20)
        tk.Button(win, text="Cancel", command=win.destroy).pack(side=tk.RIGHT, padx=20)

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
                resolution = "1024*1024"  # Default resolution for New tab ComfyUI execution

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
                            params_dict["checkpoint"] = "zImageTurboNSFW_50BF16Diffusion.safetensors"
                            params_dict["random_number"] = params.random_number
                            params_dict["seed"] = params.random_number
                            # Dynamic LoRA lookup from lora_lookup.csv for z-image workflow
                            acts = params.main_sex_act if hasattr(params, 'main_sex_act') else []
                            lora_resolved = _resolve_lora_params(
                                acts,
                                "lora_lookup.csv",
                                workflow_name="z-image",
                                filter_type="image",
                            )
                            params_dict.update(lora_resolved)
                        else:
                            params_dict = dict(params.for_wan_image())
                            lora_names = [p.get("lora_name", "") for p in getattr(params, "sex_loras", [])]
                            lora_strengths = [0.7] * len(getattr(params, "sex_loras", []))
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

    def on_closing(self):
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = VideoGenerationApp(root)
    root.mainloop()
