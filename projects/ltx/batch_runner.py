"""
Batch Runner for LTX Video Generation Workflow.

Execution Flow (Sequential per task):
    Phase 2: PREPARATION (Image preprocess + text encoding + latent creation)
    ├── For each task (sequential):
    │   ├── Generate ltx_preparation workflow -> send to ComfyUI
    │   └── Wait for ComfyUI completion via WebSocket/HTTP polling
    ├── After all tasks done: Run cleanup workflow -> creates {job_id}-2.txt
    └── Wait for cleanup completion

    Phase 3: SAMPLING (3-step: 1st sampling → upscale → 2nd sampling)
    ├── Step 3a: For each task (sequential):
    │   ├── Generate ltx_1st_sampling workflow -> send to ComfyUI
    │   └── Wait for ComfyUI completion
    ├── Step 3b: For each task (sequential):
    │   ├── Generate ltx_upscale workflow -> send to ComfyUI
    │   └── Wait for ComfyUI completion
    ├── Step 3c: For each task (sequential):
    │   ├── Generate ltx_2nd_sampling workflow -> send to ComfyUI
    │   └── Wait for ComfyUI completion
    ├── Delete image files from output/
    ├── Run cleanup workflow -> creates {job_id}-3.txt
    └── Wait for cleanup completion

    Phase 4: LATENT DECODE (LTXV)
    ├── For each task (sequential):
    │   ├── Generate ltx_decode workflow -> send to ComfyUI
    │   └── Wait for ComfyUI completion
    ├── Delete consumed latents
    ├── Run cleanup workflow -> creates {job_id}-4.txt
    └── Wait for cleanup completion
"""

import os
import json
import time
import uuid
import requests
import threading
import glob
from typing import Dict, List, Optional, Callable
from copy import deepcopy

from workflow_generator import generate_api_workflow, generate_cleanup_workflow, save_workflow
from latent_utils import delete_image_files, delete_consumed_latents
from comfyui_image_utils import wait_for_execution

# Get the directory where this script is located
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Default paths
COMFYUI_ROOT = os.environ.get("COMFYUI_ROOT", r"D:\ComfyUI_windows_portable\ComfyUI")
OUTPUT_FOLDER = os.environ.get("OUTPUT_FOLDER", os.path.join(COMFYUI_ROOT, "output"))
INPUT_FOLDER = os.environ.get("INPUT_FOLDER", os.path.join(COMFYUI_ROOT, "input"))
PROCESSED_FOLDER = os.path.join(OUTPUT_FOLDER, "processed")
LATENTS_FOLDER = os.path.join(OUTPUT_FOLDER, "latents")
CONDITIONINGS_FOLDER = os.path.join(OUTPUT_FOLDER, "conditionings")
COMFYUI_URL = os.environ.get("COMFYUI_URL", "http://192.168.4.63:8188/prompt")

# Debug workflow directory (project root level)
DEBUG_WORKFLOWS_DIR = os.path.join(os.path.dirname(os.path.dirname(SCRIPT_DIR)), "debug_workflows")


class BatchRunner:
    """
    Batch runner for LTX video generation workflow.
    """
    
    # Step numbers for each phase
    STEP_IMAGE = 1
    STEP_TEXT_ENCODING = 2
    STEP_SAMPLING = 3
    STEP_LATENT_DECODE = 4
    
    def __init__(self, 
                 comfyui_url: str = None,
                 output_folder: str = None,
                 input_folder: str = None,
                 processed_folder: str = None,
                 log_func: Callable = None):
        """
        Initialize the batch runner.
        
        Args:
            comfyui_url: ComfyUI API URL
            output_folder: ComfyUI output folder
            input_folder: ComfyUI input folder
            processed_folder: Processed indicator folder
            log_func: Logging function (e.g., print)
        """
        self.comfyui_url = comfyui_url or COMFYUI_URL
        self.output_folder = output_folder or OUTPUT_FOLDER
        self.input_folder = input_folder or INPUT_FOLDER
        self.processed_folder = processed_folder or PROCESSED_FOLDER
        self.log_func = log_func or print
        self.cancel_event = threading.Event()
        self.running = False
    
    def log(self, message: str):
        """Log a message."""
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        self.log_func(f"[{timestamp}] {message}")
    
    def send_workflow_to_comfyui(self, workflow: Dict, work_id: str = None, template_name: str = None) -> Optional[str]:
        """
        Send a workflow to ComfyUI server.
        
        Args:
            workflow: The workflow JSON dict
            work_id: Optional work ID for tracking
            template_name: Optional template name for debug logging
            
        Returns:
            prompt_id if successful, None otherwise
        """
        prompt_id = str(uuid.uuid4())
        
        # Save debug workflow copy
        if work_id:
            os.makedirs(DEBUG_WORKFLOWS_DIR, exist_ok=True)
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            safe_work_id = work_id.replace("/", "_").replace("\\", "_")
            debug_filename = f"{safe_work_id}_{template_name or 'workflow'}_{timestamp}.json"
            debug_path = os.path.join(DEBUG_WORKFLOWS_DIR, debug_filename)
            try:
                with open(debug_path, 'w', encoding='utf-8') as f:
                    json.dump(workflow, f, indent=2)
                self.log(f"Debug workflow saved: {debug_filename}")
            except Exception as e:
                self.log(f"Warning: Could not save debug workflow: {e}")
        
        payload = {
            "prompt": workflow,
            "prompt_id": prompt_id,
            "client_id": work_id or prompt_id
        }
        
        try:
            response = requests.post(self.comfyui_url, json=payload, timeout=30)
            if response.ok:
                self.log(f"Task queued successfully: {work_id or prompt_id}")
                return prompt_id
            else:
                self.log(f"Failed to queue task. Status: {response.status_code}, Response: {response.text}")
                return None
        except Exception as e:
            self.log(f"Error sending workflow to ComfyUI: {e}")
            return None
    
    def poll_for_step_completion(self, job_id: str, step_number: int, 
                                  timeout_seconds: int = 3600,
                                  check_interval: int = 10) -> bool:
        """
        Poll for step completion indicator file.
        
        Indicator file: {processed_folder}/{job_id}-{step_number}.txt
        
        Args:
            job_id: The major job ID
            step_number: The step number (1, 2, 3, 4)
            timeout_seconds: Maximum wait time in seconds
            check_interval: Interval between checks in seconds
            
        Returns:
            True if completed, False if timeout or cancelled
        """
        indicator_file = os.path.join(self.processed_folder, f"{job_id}-{step_number}.txt")
        start_time = time.time()
        
        while time.time() - start_time < timeout_seconds:
            if self.cancel_event.is_set():
                self.log(f"Cancelled while waiting for step {step_number}")
                return False
            
            if os.path.exists(indicator_file):
                self.log(f"Step {step_number} completed: {job_id}-{step_number}.txt")
                try:
                    os.remove(indicator_file)
                except Exception as e:
                    self.log(f"Error removing indicator file: {e}")
                return True
            
            time.sleep(check_interval)
        
        self.log(f"Timeout waiting for step {step_number} completion")
        return False
    
    def poll_for_latent_files(self, work_id: str, timeout_seconds: int = 3600,
                              check_interval: int = 10) -> bool:
        """
        Poll for video and audio latent file creation.
        
        Args:
            work_id: The work ID to poll for
            timeout_seconds: Maximum wait time in seconds
            check_interval: Interval between checks in seconds
            
        Returns:
            True if both latent files found, False if timeout or cancelled
        """
        video_latent = os.path.join(LATENTS_FOLDER, f"video_{work_id}")
        audio_latent = os.path.join(LATENTS_FOLDER, f"audio_{work_id}")
        
        start_time = time.time()
        
        while time.time() - start_time < timeout_seconds:
            if self.cancel_event.is_set():
                self.log(f"Cancelled while waiting for latents: {work_id}")
                return False
            
            # Check for latent files (ComfyUI adds suffix like _00001_)
            video_matches = glob.glob(os.path.join(LATENTS_FOLDER, f"video_{work_id}*.latent"))
            audio_matches = glob.glob(os.path.join(LATENTS_FOLDER, f"audio_{work_id}*.latent"))
            
            if video_matches and audio_matches:
                self.log(f"Latent files created for {work_id}")
                return True
            
            time.sleep(check_interval)
        
        self.log(f"Timeout waiting for latents: {work_id}")
        return False
    
    def wait_for_comfyui_completion(self, prompt_id: str, timeout: int = 1800) -> Optional[dict]:
        """
        Wait for a ComfyUI workflow to complete using the existing WebSocket + HTTP polling mechanism.
        
        This reuses the same robust wait_for_execution function from comfyui_image_utils.py
        that is used in the New tab and WAN tab for image/video generation.
        
        Args:
            prompt_id: The prompt_id returned from ComfyUI /prompt endpoint
            timeout: Maximum wait time in seconds (default 1800 = 30 minutes)
        
        Returns:
            The history entry dict if completed, None if timed out or cancelled.
        """
        try:
            result = wait_for_execution(
                comfyui_url=self.comfyui_url,
                prompt_id=prompt_id,
                cancel_event=self.cancel_event,
                timeout=timeout
            )
            return result
        except Exception as e:
            self.log(f"Error waiting for ComfyUI completion (prompt_id={prompt_id}): {e}")
            return None
    
    def save_output_image_with_metadata(self, work_id: str, prompt: str,
                                          video_pos_prompt: str = "", main_sex_act: str = "",
                                          scene_index: int = 0, prompt_index: int = 0,
                                          output_images_base: str = None) -> Optional[str]:
        """
        Discover the generated image from ComfyUI history, save it to output_images/{work_id}/
        with metadata including prompt information.
        """
        if output_images_base is None:
            output_images_base = os.path.join(SCRIPT_DIR, "..", "..", "output_images")
        output_images_base = os.path.normpath(output_images_base)
        output_dir = os.path.join(output_images_base, work_id)
        os.makedirs(output_dir, exist_ok=True)
        
        try:
            from PIL import Image as PILImage
            
            metadata = {
                "prompt": prompt,
                "video_prompt": video_pos_prompt,
                "sex_act": main_sex_act,
                "scene_index": scene_index,
                "prompt_index": prompt_index,
                "work_id": work_id,
            }
            
            metadata_str = json.dumps(metadata, ensure_ascii=False)
            
            image_candidates = []
            output_comfy = OUTPUT_FOLDER
            
            if os.path.exists(output_comfy):
                for f in os.listdir(output_comfy):
                    if f.startswith(f"{work_id}.") and f.lower().endswith(('.png', '.jpg', '.jpeg')):
                        image_candidates.append(os.path.join(output_comfy, f))
            
            if not image_candidates:
                self.log(f"Warning: No image found for work_id={work_id}")
                return None
            
            image_src = max(image_candidates, key=lambda p: os.path.getmtime(p))
            
            img = PILImage.open(image_src)
            if img.mode not in ("RGB", "RGBA"):
                img = img.convert("RGBA")
            
            output_path = os.path.join(output_dir, f"{work_id}.png")
            img.save(output_path, pnginfo=(("prompt", metadata_str),))
            
            self.log(f"Saved image with metadata: {os.path.basename(output_path)}")
            return output_path
            
        except Exception as e:
            self.log(f"Error saving image with metadata for {work_id}: {e}")
            return None
    
    def save_output_video_with_metadata(self, work_id: str, prompt: str,
                                          video_pos_prompt: str = "", main_sex_act: str = "",
                                          output_images_base: str = None) -> Optional[str]:
        """
        Discover the generated video from ComfyUI history, save it to output_images/{work_id}/
        """
        if output_images_base is None:
            output_images_base = os.path.join(SCRIPT_DIR, "..", "..", "output_images")
        output_images_base = os.path.normpath(output_images_base)
        output_dir = os.path.join(output_images_base, work_id)
        os.makedirs(output_dir, exist_ok=True)
        
        try:
            video_src = None
            video_output = os.path.join(OUTPUT_FOLDER, "video")
            
            if os.path.exists(video_output):
                for f in os.listdir(video_output):
                    if f.startswith(f"{work_id}.") and f.lower().endswith(('.mp4', '.gif', '.webm')):
                        video_src = os.path.join(video_output, f)
                        break
            
            if not video_src:
                self.log(f"Warning: No video found for work_id={work_id}")
                return None
            
            output_path = os.path.join(output_dir, f"{work_id}.mp4")
            import shutil
            shutil.copy2(video_src, output_path)
            
            self.log(f"Saved video: {os.path.basename(output_path)}")
            return output_path
            
        except Exception as e:
            self.log(f"Error saving video for {work_id}: {e}")
            return None
    
    def run_cleanup(self, job_id: str, step_number: int) -> bool:
        """
        Run cleanup workflow for a step.
        
        Args:
            job_id: The major job ID
            step_number: The step number (1, 2, 3, 4)
            
        Returns:
            True if cleanup completed, False otherwise
        """
        self.log(f"Running cleanup for step {step_number}...")
        
        workflow = generate_cleanup_workflow(job_id, step_number)
        
        prompt_id = self.send_workflow_to_comfyui(workflow, f"cleanup-{job_id}-{step_number}")
        if not prompt_id:
            self.log(f"Failed to queue cleanup workflow for step {step_number}")
            return False
        
        # Wait for cleanup completion
        return self.poll_for_step_completion(job_id, step_number)
    
    def run_batch(self, 
                  job_id: str,
                  tasks: List[Dict], 
                  width: int = 1280, 
                  height: int = 720, 
                  length: int = 241,
                  fps: int = 24,
                  image_model: str = "pornmaster_proSDXLV8") -> Dict:
        """
        Run a batch of tasks through the full 4-phase pipeline.
        
        Args:
            job_id: Major job ID for tracking
            tasks: List of task dicts, each containing:
                - work_id: Unique identifier for this sub-work
                - main_sex_act: Action tag for LoRA selection
                - prompt: Positive prompt text
                - negative_prompt: (optional) Negative prompt text
            width: Image/video width
            height: Image/video height
            length: Video length in frames
            fps: Frames per second
            image_model: Image generation model/template name
            
        Returns:
            Dict with 'completed', 'failed', 'errors' lists
        """
        self.running = True
        self.cancel_event.clear()
        
        # Ensure folders exist
        os.makedirs(self.processed_folder, exist_ok=True)
        os.makedirs(LATENTS_FOLDER, exist_ok=True)
        os.makedirs(CONDITIONINGS_FOLDER, exist_ok=True)
        
        result = {
            'job_id': job_id,
            'completed': [],
            'failed': [],
            'errors': []
        }
        
        if not tasks:
            self.log("No tasks to run.")
            return result
        
        self.log(f"Starting batch run: job_id={job_id}, {len(tasks)} tasks")
        
        # ========== PHASE 2: PREPARATION (Image preprocess + text encoding + latent creation) ==========
        # Each task is sent sequentially, waited for ComfyUI completion, then next task begins
        self.log("=" * 50)
        self.log("PHASE 2: PREPARATION")
        self.log("=" * 50)

        for i, task in enumerate(tasks):
            if self.cancel_event.is_set():
                self.log("Batch cancelled during Phase 2")
                return result
            
            work_id = task.get('work_id')
            if work_id in result['failed']:
                continue

            prompt = task.get('prompt', '')
            self.log(f"Phase 2 [{i+1}/{len(tasks)}]: Queuing preparation for {work_id}...")

            try:
                workflow = generate_api_workflow(
                    project="ltx",
                    type="video",
                    template="ltx_preparation",
                    acts=[],
                    width=width,
                    height=height,
                    length=length,
                    prompt=prompt,
                    video_pos_prompt=task.get("video_pos_prompt", ""),
                    work_id=work_id
                )

                prompt_id = self.send_workflow_to_comfyui(workflow, work_id, template_name="ltx_preparation")
                if not prompt_id:
                    result['failed'].append(work_id)
                    result['errors'].append({'work_id': work_id, 'phase': 'preparation', 'error': 'Failed to queue'})
                    continue

                # Wait for ComfyUI to actually complete this task (WebSocket + HTTP polling)
                self.log(f"Phase 2 [{i+1}/{len(tasks)}]: Waiting for {work_id} (prompt_id={prompt_id})...")
                hist = self.wait_for_comfyui_completion(prompt_id, timeout=1800)
                
                if hist is None:
                    # Timed out or cancelled
                    if self.cancel_event.is_set():
                        self.log("Batch cancelled during Phase 2 wait")
                        return result
                    result['failed'].append(work_id)
                    result['errors'].append({'work_id': work_id, 'phase': 'preparation', 'error': 'Timeout waiting for ComfyUI'})
                    continue
                
                # Check for errors in ComfyUI history
                status = hist.get("status", {})
                errors = status.get("errors", {})
                if errors:
                    result['failed'].append(work_id)
                    result['errors'].append({'work_id': work_id, 'phase': 'preparation', 'error': str(errors)})
                    continue
                
                self.log(f"Phase 2 [{i+1}/{len(tasks)}]: {work_id} done")
                time.sleep(0.5)  # Small delay between tasks (consistent with WAN/New tab behavior)

            except Exception as e:
                self.log(f"Error generating preparation workflow for {work_id}: {e}")
                result['failed'].append(work_id)
                result['errors'].append({'work_id': work_id, 'phase': 'preparation', 'error': str(e)})

        # Run cleanup and wait for Phase 2 completion
        if not self.run_cleanup(job_id, self.STEP_TEXT_ENCODING):
            self.log("Phase 2 cleanup failed or cancelled")
            return result
        
        if self.cancel_event.is_set():
            self.log("Batch cancelled after Phase 2")
            return result
        
        self.log(f"Phase 2 complete. {len([t for t in tasks if t['work_id'] not in result['failed']])}/{len(tasks)} text encodings done.")
        
        # ========== PHASE 3: SAMPLING (3-step: 1st sampling → upscale → 2nd sampling) ==========
        # Each sub-step processes tasks sequentially: send → wait for ComfyUI → next task
        self.log("=" * 50)
        self.log("PHASE 3: SAMPLING (3-step)")
        self.log("=" * 50)

        # --- Step 3a: 1st Sampling (ltx_1st_sampling) ---
        self.log("Phase 3a: 1st Sampling...")
        for i, task in enumerate(tasks):
            if self.cancel_event.is_set():
                self.log("Batch cancelled during Phase 3a")
                return result
            
            work_id = task.get('work_id')
            if work_id in result['failed']:
                continue

            main_sex_act = task.get('main_sex_act', '')
            prompt = task.get('prompt', '')
            acts = [main_sex_act] if main_sex_act else []

            self.log(f"Phase 3a [{i+1}/{len(tasks)}]: Queuing 1st sampling for {work_id}...")
            try:
                workflow = generate_api_workflow(
                    project="ltx",
                    type="video",
                    template="ltx_1st_sampling",
                    acts=acts,
                    width=width,
                    height=height,
                    length=length,
                    prompt=prompt,
                    video_pos_prompt=task.get("video_pos_prompt", ""),
                    work_id=work_id
                )

                prompt_id = self.send_workflow_to_comfyui(workflow, work_id, template_name="ltx_1st_sampling")
                if not prompt_id:
                    result['failed'].append(work_id)
                    result['errors'].append({'work_id': work_id, 'phase': '1st_sampling', 'error': 'Failed to queue'})
                    continue

                # Wait for ComfyUI to complete this task
                self.log(f"Phase 3a [{i+1}/{len(tasks)}]: Waiting for {work_id}...")
                hist = self.wait_for_comfyui_completion(prompt_id, timeout=1800)
                
                if hist is None:
                    if self.cancel_event.is_set():
                        self.log("Batch cancelled during Phase 3a wait")
                        return result
                    result['failed'].append(work_id)
                    result['errors'].append({'work_id': work_id, 'phase': '1st_sampling', 'error': 'Timeout waiting for ComfyUI'})
                    continue
                
                status = hist.get("status", {})
                errors = status.get("errors", {})
                if errors:
                    result['failed'].append(work_id)
                    result['errors'].append({'work_id': work_id, 'phase': '1st_sampling', 'error': str(errors)})
                    continue
                
                self.log(f"Phase 3a [{i+1}/{len(tasks)}]: {work_id} done")
                time.sleep(0.5)

            except Exception as e:
                self.log(f"Error generating 1st sampling workflow for {work_id}: {e}")
                result['failed'].append(work_id)
                result['errors'].append({'work_id': work_id, 'phase': '1st_sampling', 'error': str(e)})

        if self.cancel_event.is_set():
            self.log("Batch cancelled after Phase 3a")
            return result

        # --- Step 3b: Upscale (ltx_upscale) ---
        self.log("Phase 3b: Upscale...")
        for i, task in enumerate(tasks):
            if self.cancel_event.is_set():
                self.log("Batch cancelled during Phase 3b")
                return result
            
            work_id = task.get('work_id')
            if work_id in result['failed']:
                continue

            main_sex_act = task.get('main_sex_act', '')
            prompt = task.get('prompt', '')
            acts = [main_sex_act] if main_sex_act else []

            self.log(f"Phase 3b [{i+1}/{len(tasks)}]: Queuing upscale for {work_id}...")
            try:
                workflow = generate_api_workflow(
                    project="ltx",
                    type="video",
                    template="ltx_upscale",
                    acts=acts,
                    width=width,
                    height=height,
                    length=length,
                    prompt=prompt,
                    video_pos_prompt=task.get("video_pos_prompt", ""),
                    work_id=work_id,
                    load_image=f"{work_id}.png",
                    upscale_model_name="ltx-2.3-spatial-upscaler-x2-1.1.safetensors"
                )

                prompt_id = self.send_workflow_to_comfyui(workflow, work_id, template_name="ltx_upscale")
                if not prompt_id:
                    result['failed'].append(work_id)
                    result['errors'].append({'work_id': work_id, 'phase': 'upscale', 'error': 'Failed to queue'})
                    continue

                # Wait for ComfyUI to complete this task
                self.log(f"Phase 3b [{i+1}/{len(tasks)}]: Waiting for {work_id}...")
                hist = self.wait_for_comfyui_completion(prompt_id, timeout=1800)
                
                if hist is None:
                    if self.cancel_event.is_set():
                        self.log("Batch cancelled during Phase 3b wait")
                        return result
                    result['failed'].append(work_id)
                    result['errors'].append({'work_id': work_id, 'phase': 'upscale', 'error': 'Timeout waiting for ComfyUI'})
                    continue
                
                status = hist.get("status", {})
                errors = status.get("errors", {})
                if errors:
                    result['failed'].append(work_id)
                    result['errors'].append({'work_id': work_id, 'phase': 'upscale', 'error': str(errors)})
                    continue
                
                self.log(f"Phase 3b [{i+1}/{len(tasks)}]: {work_id} done")
                time.sleep(0.5)

            except Exception as e:
                self.log(f"Error generating upscale workflow for {work_id}: {e}")
                result['failed'].append(work_id)
                result['errors'].append({'work_id': work_id, 'phase': 'upscale', 'error': str(e)})

        if self.cancel_event.is_set():
            self.log("Batch cancelled after Phase 3b")
            return result

        # Delete image files after sampling steps
        self.log("Deleting source image files...")
        for task in tasks:
            work_id = task.get('work_id')
            if work_id not in result['failed']:
                delete_image_files(work_id, self.output_folder, self.log)

        # --- Step 3c: 2nd Sampling (ltx_2nd_sampling) ---
        self.log("Phase 3c: 2nd Sampling...")
        for i, task in enumerate(tasks):
            if self.cancel_event.is_set():
                self.log("Batch cancelled during Phase 3c")
                return result
            
            work_id = task.get('work_id')
            if work_id in result['failed']:
                continue

            main_sex_act = task.get('main_sex_act', '')
            prompt = task.get('prompt', '')
            acts = [main_sex_act] if main_sex_act else []

            self.log(f"Phase 3c [{i+1}/{len(tasks)}]: Queuing 2nd sampling for {work_id}...")
            try:
                workflow = generate_api_workflow(
                    project="ltx",
                    type="video",
                    template="ltx_2nd_sampling",
                    acts=acts,
                    width=width,
                    height=height,
                    length=length,
                    prompt=prompt,
                    video_pos_prompt=task.get("video_pos_prompt", ""),
                    work_id=work_id
                )

                prompt_id = self.send_workflow_to_comfyui(workflow, work_id, template_name="ltx_2nd_sampling")
                if not prompt_id:
                    result['failed'].append(work_id)
                    result['errors'].append({'work_id': work_id, 'phase': '2nd_sampling', 'error': 'Failed to queue'})
                    continue

                # Wait for ComfyUI to complete this task
                self.log(f"Phase 3c [{i+1}/{len(tasks)}]: Waiting for {work_id}...")
                hist = self.wait_for_comfyui_completion(prompt_id, timeout=1800)
                
                if hist is None:
                    if self.cancel_event.is_set():
                        self.log("Batch cancelled during Phase 3c wait")
                        return result
                    result['failed'].append(work_id)
                    result['errors'].append({'work_id': work_id, 'phase': '2nd_sampling', 'error': 'Timeout waiting for ComfyUI'})
                    continue
                
                status = hist.get("status", {})
                errors = status.get("errors", {})
                if errors:
                    result['failed'].append(work_id)
                    result['errors'].append({'work_id': work_id, 'phase': '2nd_sampling', 'error': str(errors)})
                    continue
                
                self.log(f"Phase 3c [{i+1}/{len(tasks)}]: {work_id} done")
                time.sleep(0.5)

            except Exception as e:
                self.log(f"Error generating 2nd sampling workflow for {work_id}: {e}")
                result['failed'].append(work_id)
                result['errors'].append({'work_id': work_id, 'phase': '2nd_sampling', 'error': str(e)})

        if self.cancel_event.is_set():
            self.log("Batch cancelled after Phase 3c")
            return result

        # Run cleanup and wait for Phase 3 completion
        if not self.run_cleanup(job_id, self.STEP_SAMPLING):
            self.log("Phase 3 cleanup failed or cancelled")
            return result

        self.log(f"Phase 3 complete. {len([t for t in tasks if t['work_id'] not in result['failed']])}/{len(tasks)} samplings done.")
        
        # ========== PHASE 4: LATENT DECODE (LTXV) ==========
        # Each task is sent sequentially, waited for ComfyUI completion, then next task begins
        self.log("=" * 50)
        self.log("PHASE 4: LATENT DECODE")
        self.log("=" * 50)

        for i, task in enumerate(tasks):
            if self.cancel_event.is_set():
                self.log("Batch cancelled during Phase 4")
                return result
            
            work_id = task.get('work_id')
            if work_id in result['failed']:
                continue

            self.log(f"Phase 4 [{i+1}/{len(tasks)}]: Queuing latent decode for {work_id}...")
            try:
                workflow = generate_api_workflow(
                    project="ltx",
                    type="video",
                    template="ltx_decode",
                    acts=[],
                    width=width,
                    height=height,
                    length=length,
                    fps=fps,
                    work_id=work_id,
                    latent_in=f"{work_id}_s2_00001_.latent",
                    output=f"video/{work_id}"
                )

                prompt_id = self.send_workflow_to_comfyui(workflow, work_id, template_name="ltx_decode")
                if not prompt_id:
                    result['failed'].append(work_id)
                    result['errors'].append({'work_id': work_id, 'phase': 'latent_decode', 'error': 'Failed to queue'})
                    continue

                # Wait for ComfyUI to complete this task
                self.log(f"Phase 4 [{i+1}/{len(tasks)}]: Waiting for {work_id}...")
                hist = self.wait_for_comfyui_completion(prompt_id, timeout=1800)
                
                if hist is None:
                    if self.cancel_event.is_set():
                        self.log("Batch cancelled during Phase 4 wait")
                        return result
                    result['failed'].append(work_id)
                    result['errors'].append({'work_id': work_id, 'phase': 'latent_decode', 'error': 'Timeout waiting for ComfyUI'})
                    continue
                
                status = hist.get("status", {})
                errors = status.get("errors", {})
                if errors:
                    result['failed'].append(work_id)
                    result['errors'].append({'work_id': work_id, 'phase': 'latent_decode', 'error': str(errors)})
                    continue
                
                self.log(f"Phase 4 [{i+1}/{len(tasks)}]: {work_id} done")
                time.sleep(0.5)

            except Exception as e:
                self.log(f"Error generating latent decode workflow for {work_id}: {e}")
                result['failed'].append(work_id)
                result['errors'].append({'work_id': work_id, 'phase': 'latent_decode', 'error': str(e)})

        if self.cancel_event.is_set():
            self.log("Batch cancelled after Phase 4 tasks")
            return result
        
        # Run cleanup and wait for Phase 4 completion
        if not self.run_cleanup(job_id, self.STEP_LATENT_DECODE):
            self.log("Phase 4 cleanup failed or cancelled")
            return result
        
        # Delete consumed latent files
        self.log("Deleting consumed latent files...")
        for task in tasks:
            work_id = task.get('work_id')
            if work_id not in result['failed']:
                delete_consumed_latents(work_id, LATENTS_FOLDER, self.input_folder, self.log)
        
        # Final results
        result['completed'] = [t['work_id'] for t in tasks if t['work_id'] not in result['failed']]
        
        for task in tasks:
            work_id = task.get('work_id')
            if work_id in result['failed']:
                continue
            try:
                self.save_output_video_with_metadata(
                    work_id=work_id,
                    prompt=task.get('prompt', ''),
                    video_pos_prompt=task.get('video_pos_prompt', ''),
                    main_sex_act=task.get('main_sex_act', '')
                )
            except Exception as e:
                self.log(f"Warning: Could not save video for {work_id}: {e}")
        
        self.log("=" * 50)
        self.log(f"BATCH COMPLETE: job_id={job_id}")
        self.log(f"Completed: {len(result['completed'])}/{len(tasks)} tasks")
        if result['failed']:
            self.log(f"Failed: {result['failed']}")
        self.log("=" * 50)
        
        self.running = False
        return result
    
    def cancel(self):
        """Cancel the running batch."""
        self.log("Cancellation requested...")
        self.cancel_event.set()
    
    def is_running(self) -> bool:
        """Check if a batch is currently running."""
        return self.running
    
    def check_step_completed(self, job_id: str, step_number: int) -> bool:
        """
        Check if a specific step has already been completed.
        
        Args:
            job_id: The major job ID
            step_number: The step number (1, 2, 3, 4)
            
        Returns:
            True if the step indicator file exists
        """
        indicator_file = os.path.join(self.processed_folder, f"{job_id}-{step_number}.txt")
        return os.path.exists(indicator_file)


# Example usage
if __name__ == "__main__":
    # Example task list
    tasks = [
        {
            "work_id": "video001",
            "main_sex_act": "fingering",
            "prompt": "1girl, beautiful woman, nude",
            "negative_prompt": "ugly, deformed, bad quality"
        },
        {
            "work_id": "video002", 
            "main_sex_act": "kiss",
            "prompt": "1girl, beautiful woman, kissing",
            "negative_prompt": "ugly, deformed, bad quality"
        }
    ]
    
    runner = BatchRunner()
    
    # Run batch with job_id
    def run():
        result = runner.run_batch(
            job_id="job_20260327_001",
            tasks=tasks
        )
        print("Final result:", result)
    
    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    thread.join()
