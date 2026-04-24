"""
Batch Runner for LTX Video Generation Workflow.

Execution Flow:
    Phase 1: IMAGE GENERATION
    ├── For each task: generate workflow -> send to ComfyUI
    ├── Run cleanup workflow -> creates {job_id}-1.txt
    └── Wait for cleanup completion

    Phase 2: TEXT ENCODING
    ├── For each task: generate workflow -> send to ComfyUI
    ├── Run cleanup workflow -> creates {job_id}-2.txt
    └── Wait for cleanup completion

    Phase 3: SAMPLING
    ├── For each task: generate workflow -> send to ComfyUI
    ├── Wait for all latents complete
    ├── Delete image files from output/
    ├── Run cleanup workflow -> creates {job_id}-3.txt
    └── Wait for cleanup completion

    Phase 4: LATENT DECODE
    ├── For each task: generate workflow -> send to ComfyUI
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
    
    def send_workflow_to_comfyui(self, workflow: Dict, work_id: str = None) -> Optional[str]:
        """
        Send a workflow to ComfyUI server.
        
        Args:
            workflow: The workflow JSON dict
            work_id: Optional work ID for tracking
            
        Returns:
            prompt_id if successful, None otherwise
        """
        prompt_id = str(uuid.uuid4())
        
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
        
        # ========== PHASE 1: IMAGE GENERATION ==========
        self.log("=" * 50)
        self.log("PHASE 1: IMAGE GENERATION")
        self.log("=" * 50)
        
        for task in tasks:
            if self.cancel_event.is_set():
                self.log("Batch cancelled during Phase 1")
                return result
            
            work_id = task.get('work_id')
            main_sex_act = task.get('main_sex_act', '')
            prompt = task.get('prompt', '')
            negative_prompt = task.get('negative_prompt', 'ugly, deformed, bad quality')
            
            acts = [main_sex_act] if main_sex_act else []
            
            try:
                workflow = generate_api_workflow(
                    project="ltx",
                    type="image",
                    template=image_model,
                    acts=acts,
                    width=width,
                    height=height,
                    length=length,
                    prompt=prompt,
                    negative_prompt=negative_prompt,
                    work_id=work_id
                )
                
                prompt_id = self.send_workflow_to_comfyui(workflow, work_id)
                if not prompt_id:
                    result['failed'].append(work_id)
                    result['errors'].append({'work_id': work_id, 'phase': 'image', 'error': 'Failed to queue'})
                    
            except Exception as e:
                self.log(f"Error generating image workflow for {work_id}: {e}")
                result['failed'].append(work_id)
                result['errors'].append({'work_id': work_id, 'phase': 'image', 'error': str(e)})
        
        # Run cleanup and wait for Phase 1 completion
        if not self.run_cleanup(job_id, self.STEP_IMAGE):
            self.log("Phase 1 cleanup failed or cancelled")
            return result
        
        if self.cancel_event.is_set():
            self.log("Batch cancelled after Phase 1")
            return result
        
        succeeded_work_ids = [t['work_id'] for t in tasks if t['work_id'] not in result['failed']]
        self.log(f"Phase 1 complete. {len(succeeded_work_ids)}/{len(tasks)} images generated.")
        
        # ========== PHASE 2: TEXT ENCODING ==========
        self.log("=" * 50)
        self.log("PHASE 2: TEXT ENCODING")
        self.log("=" * 50)
        
        for task in tasks:
            work_id = task.get('work_id')
            if work_id in result['failed']:
                continue
            
            prompt = task.get('prompt', '')
            
            try:
                workflow = generate_api_workflow(
                    project="ltx",
                    type="video",
                    template="ltx-text-encoding",
                    acts=[],
                    width=width,
                    height=height,
                    length=length,
                    prompt=prompt,
                    video_pos_prompt=task.get("video_pos_prompt", ""),
                    work_id=work_id
                )
                
                prompt_id = self.send_workflow_to_comfyui(workflow, work_id)
                if not prompt_id:
                    result['failed'].append(work_id)
                    result['errors'].append({'work_id': work_id, 'phase': 'text_encoding', 'error': 'Failed to queue'})
                    
            except Exception as e:
                self.log(f"Error generating text encoding workflow for {work_id}: {e}")
                result['failed'].append(work_id)
                result['errors'].append({'work_id': work_id, 'phase': 'text_encoding', 'error': str(e)})
        
        # Run cleanup and wait for Phase 2 completion
        if not self.run_cleanup(job_id, self.STEP_TEXT_ENCODING):
            self.log("Phase 2 cleanup failed or cancelled")
            return result
        
        if self.cancel_event.is_set():
            self.log("Batch cancelled after Phase 2")
            return result
        
        self.log(f"Phase 2 complete. {len([t for t in tasks if t['work_id'] not in result['failed']])} text encodings done.")
        
        # ========== PHASE 3: SAMPLING ==========
        self.log("=" * 50)
        self.log("PHASE 3: SAMPLING")
        self.log("=" * 50)
        
        for task in tasks:
            work_id = task.get('work_id')
            if work_id in result['failed']:
                continue
            
            main_sex_act = task.get('main_sex_act', '')
            prompt = task.get('prompt', '')
            acts = [main_sex_act] if main_sex_act else []
            
            try:
                workflow = generate_api_workflow(
                    project="ltx",
                    type="video",
                    template="ltx_sampling",
                    acts=acts,
                    width=width,
                    height=height,
                    length=length,
                    prompt=prompt,
                    video_pos_prompt=task.get("video_pos_prompt", ""),
                    work_id=work_id
                )
                
                prompt_id = self.send_workflow_to_comfyui(workflow, work_id)
                if not prompt_id:
                    result['failed'].append(work_id)
                    result['errors'].append({'work_id': work_id, 'phase': 'sampling', 'error': 'Failed to queue'})
                    
            except Exception as e:
                self.log(f"Error generating sampling workflow for {work_id}: {e}")
                result['failed'].append(work_id)
                result['errors'].append({'work_id': work_id, 'phase': 'sampling', 'error': str(e)})
        
        # Wait for all latents to be created
        self.log("Waiting for all latents to be created...")
        for task in tasks:
            work_id = task.get('work_id')
            if work_id not in result['failed']:
                if not self.poll_for_latent_files(work_id):
                    result['failed'].append(work_id)
                    result['errors'].append({'work_id': work_id, 'phase': 'sampling', 'error': 'Timeout waiting for latents'})
        
        if self.cancel_event.is_set():
            self.log("Batch cancelled during Phase 3")
            return result
        
        # Delete image files after sampling
        self.log("Deleting source image files...")
        for task in tasks:
            work_id = task.get('work_id')
            if work_id not in result['failed']:
                delete_image_files(work_id, self.output_folder, self.log)
        
        # Run cleanup and wait for Phase 3 completion
        if not self.run_cleanup(job_id, self.STEP_SAMPLING):
            self.log("Phase 3 cleanup failed or cancelled")
            return result
        
        self.log(f"Phase 3 complete. {len([t for t in tasks if t['work_id'] not in result['failed']])} samplings done.")
        
        # ========== PHASE 4: LATENT DECODE ==========
        self.log("=" * 50)
        self.log("PHASE 4: LATENT DECODE")
        self.log("=" * 50)
        
        for task in tasks:
            work_id = task.get('work_id')
            if work_id in result['failed']:
                continue
            
            try:
                workflow = generate_api_workflow(
                    project="ltx",
                    type="video",
                    template="ltx_latent",
                    acts=[],
                    width=width,
                    height=height,
                    length=length,
                    fps=fps,
                    work_id=work_id
                )
                
                prompt_id = self.send_workflow_to_comfyui(workflow, work_id)
                if not prompt_id:
                    result['failed'].append(work_id)
                    result['errors'].append({'work_id': work_id, 'phase': 'latent_decode', 'error': 'Failed to queue'})
                    
            except Exception as e:
                self.log(f"Error generating latent decode workflow for {work_id}: {e}")
                result['failed'].append(work_id)
                result['errors'].append({'work_id': work_id, 'phase': 'latent_decode', 'error': str(e)})
        
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
