
import os
import json
import time
import uuid
import requests
import shutil
from pathlib import Path

# --- Configuration ---
# Pulling from main_ui.py logic
COMFYUI_URL = "http://192.168.4.22:8188/prompt" 
COMFYUI_ROOT = r"D:\ComfyUI_windows_portable\ComfyUI"
INPUT_FOLDER = os.path.join(COMFYUI_ROOT, "input")
OUTPUT_FOLDER = os.path.join(COMFYUI_ROOT, "output")
PROCESSED_FOLDER = os.path.join(OUTPUT_FOLDER, "processed")

# Project paths
BASE_DIR = os.getcwd()
IMAGE_PATH = os.path.join(BASE_DIR, "output_images", "wg22j_scene0_p0.png")

import sys
sys.path.append(os.path.join(BASE_DIR, "projects", "ltx"))
from workflow_generator import generate_api_workflow, generate_cleanup_workflow
from batch_runner import BatchRunner

def run_integration_test():
    print(f"--- Starting LTX Integration Test ---")
    
    # 1. Prepare Image
    if not os.path.exists(IMAGE_PATH):
        print(f"ERROR: Image not found at {IMAGE_PATH}")
        return
    
    filename = os.path.basename(IMAGE_PATH)
    work_id = os.path.splitext(filename)[0] # wg22j_scene0_p0
    job_id = work_id.split('_')[0] # wg22j
    
    dest = os.path.join(INPUT_FOLDER, filename)
    print(f"Ensuring image in ComfyUI input: {dest}")
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    shutil.copy2(IMAGE_PATH, dest)
    
    # 2. Setup Runner with specialized logging
    def test_log(msg):
        print(f"[TEST LOG] {msg}")

    runner = BatchRunner(
        comfyui_url=COMFYUI_URL,
        output_folder=OUTPUT_FOLDER,
        input_folder=INPUT_FOLDER,
        processed_folder=PROCESSED_FOLDER,
        log_func=test_log
    )
    
    # Wrap send_workflow_to_comfyui to capture JSON
    original_send = runner.send_workflow_to_comfyui
    def debug_send(workflow, work_id=None):
        name = work_id or "unknown"
        debug_path = os.path.join(BASE_DIR, "debug_workflows", f"sent_{name}_{int(time.time())}.json")
        os.makedirs(os.path.dirname(debug_path), exist_ok=True)
        with open(debug_path, 'w', encoding='utf-8') as f:
            json.dump(workflow, f, indent=2)
        print(f"Captured workflow to {debug_path}")
        return original_send(workflow, work_id)
    
    runner.send_workflow_to_comfyui = debug_send

    # 3. Define Task
    tasks = [{
        "work_id": work_id,
        "prompt": "A tall, athletic American man with short brown hair...", 
        "video_pos_prompt": "She leans forward, grabbing his broad shoulders...",
        "negative_prompt": "ugly, deformed, bad quality",
        "main_sex_act": "lying_cowgirl",
        "scene_index": 0,
        "prompt_index": 0
    }]

    # 4. Run Batch
    print(f"\n--- Executing Batch (Phase 2 to 4) ---")
    try:
        result = runner.run_batch(
            job_id=job_id,
            tasks=tasks,
            width=1280,
            height=720,
            length=241,
            fps=24
        )
        print(f"\n--- Test Result ---")
        print(json.dumps(result, indent=2))
    except Exception as e:
        print(f"\n--- Test Crashed ---")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    run_integration_test()
