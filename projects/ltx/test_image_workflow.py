"""
Unit Test for Image Generation Workflow

Tests the complete flow:
1. Load task JSON file
2. Generate ComfyUI workflows for each scene
3. Send to ComfyUI server
4. Track completion
"""

import os
import sys
import json
import time
import shutil
import requests

# Add project paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LTX_PROJECT_DIR = SCRIPT_DIR  # This script is already in ltx directory
PROJECT_DIR = os.path.dirname(LTX_PROJECT_DIR)
sys.path.insert(0, LTX_PROJECT_DIR)

from workflow_generator import generate_api_workflow, load_lora_lookup

# Paths
TASKS_DIR = os.path.join(LTX_PROJECT_DIR, "tasks")
TEMP_DIR = os.path.join(LTX_PROJECT_DIR, "temp_workflows")
IMAGE_LORA_LOOKUP = os.path.join(LTX_PROJECT_DIR, "image_lora_lookup.csv")
COMFYUI_URL = os.environ.get("COMFYUI_URL", "http://192.168.4.22:8188/prompt")


def load_task_file(task_filename: str) -> dict:
    """Load a task JSON file."""
    task_path = os.path.join(TASKS_DIR, task_filename)
    with open(task_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_image_lora_lookup(csv_path: str, workflow_name: str = None) -> dict:
    """Load image LoRA lookup table from CSV."""
    import csv
    lookup = {}
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            row_workflow = row.get('workflow name', '').strip()
            if workflow_name and row_workflow != workflow_name:
                continue
            
            lora_tag = row.get('lora_tag', '').strip().lower()
            if not lora_tag:
                continue
            
            loras = []
            for i in range(1, 6):
                name = row.get(f'lora{i}_name', '').strip()
                strength = row.get(f'lora{i}_strength', '').strip()
                if name:
                    try:
                        strength_val = float(strength) if strength else 1.0
                    except ValueError:
                        strength_val = 1.0
                    loras.append({
                        'name': name,
                        'strength': strength_val
                    })
            
            if loras:
                lookup[lora_tag] = loras
    
    return lookup


def send_workflow_to_comfyui(workflow: dict, work_id: str) -> str:
    """Send workflow to ComfyUI server."""
    import uuid
    prompt_id = str(uuid.uuid4())
    
    payload = {
        "prompt": workflow,
        "prompt_id": prompt_id,
        "client_id": work_id
    }
    
    try:
        response = requests.post(COMFYUI_URL, json=payload, timeout=30)
        if response.ok:
            print(f"  [OK] Task queued: {work_id} (prompt_id: {prompt_id})")
            return prompt_id
        else:
            print(f"  [FAIL] Status: {response.status_code}, Response: {response.text}")
            return None
    except Exception as e:
        print(f"  [ERROR] {e}")
        return None


def run_test(task_filename: str = "multiple-scene-images_20260328_175631.json"):
    """Run the complete test."""
    print("=" * 60)
    print("IMAGE WORKFLOW UNIT TEST")
    print("=" * 60)
    
    # Create temp directory
    if os.path.exists(TEMP_DIR):
        shutil.rmtree(TEMP_DIR)
    os.makedirs(TEMP_DIR)
    print(f"\nCreated temp directory: {TEMP_DIR}")
    
    # Load task file
    print(f"\nLoading task file: {task_filename}")
    try:
        task_data = load_task_file(task_filename)
        print(f"  [OK] Task loaded successfully")
    except FileNotFoundError:
        print(f"  [ERROR] Task file not found: {task_filename}")
        return
    
    # Extract task info
    scenes = task_data.get("scenes", [])
    print(f"  - Total scenes: {len(scenes)}")
    print(f"  - Art type: {task_data.get('art_type')}")
    print(f"  - Location: {task_data.get('main_location')}")
    
    # Load LoRA lookup
    print(f"\nLoading LoRA lookup...")
    lora_lookup = load_image_lora_lookup(IMAGE_LORA_LOOKUP, "pornmaster_proSDXLV8")
    print(f"  [OK] Loaded {len(lora_lookup)} LoRA tags")
    print(f"  - Available tags: {list(lora_lookup.keys())}")
    
    # Generate job ID
    job_id = time.strftime("%Y%m%d_%H%M%S")
    print(f"\nJob ID: {job_id}")
    
    # Process each scene
    width, height = 1024, 1024
    all_work_ids = []
    
    print("\n" + "=" * 60)
    print("PROCESSING SCENES")
    print("=" * 60)
    
    for idx, scene in enumerate(scenes):
        work_id = f"{job_id}_{idx + 1}"
        all_work_ids.append(work_id)
        
        print(f"\n--- Scene {idx + 1}/{len(scenes)} (work_id: {work_id}) ---")
        
        # Build prompt
        base_prompt = scene.get("first_frame_image_prompt", "")
        sex_loras = scene.get("sex_loras", [])
        sex_loras = [s for s in sex_loras if s and s.lower() != "none"]
        
        if sex_loras:
            prompt = base_prompt + ", " + ", ".join(sex_loras)
        else:
            prompt = base_prompt
        
        print(f"  Prompt length: {len(prompt)} chars")
        print(f"  Sex LoRAs: {sex_loras}")
        
        # Collect LoRAs
        all_loras = []
        for lora_tag in sex_loras:
            lora_tag_lower = lora_tag.lower().strip()
            if lora_tag_lower in lora_lookup:
                found = lora_lookup[lora_tag_lower]
                all_loras.extend(found)
                print(f"  Found LoRA for '{lora_tag}': {[l['name'] for l in found]}")
            else:
                print(f"  [WARN] No LoRA found for tag '{lora_tag}'")
        
        print(f"  Total LoRAs to insert: {len(all_loras)}")
        
        # Generate workflow
        print(f"  Generating workflow...")
        workflow = generate_api_workflow(
            project="ltx",
            type="image",
            template="pornmaster_proSDXLV8",
            acts=sex_loras,
            width=width,
            height=height,
            prompt=prompt,
            negative_prompt="ugly, deformed, bad quality, low quality",
            work_id=work_id,
            workflow_name="pornmaster_proSDXLV8",
            lora_lookup_path=IMAGE_LORA_LOOKUP
        )
        
        # Save workflow to temp file
        workflow_path = os.path.join(TEMP_DIR, f"{work_id}.json")
        with open(workflow_path, 'w', encoding='utf-8') as f:
            json.dump(workflow, f, indent=2)
        print(f"  [OK] Saved workflow: {workflow_path}")
        
        # Check workflow structure
        dynamic_nodes = [nid for nid, n in workflow.items() 
                        if n.get('_meta', {}).get('title', '').startswith('**')]
        lora_nodes = [nid for nid, n in workflow.items() 
                     if n.get('class_type', '').startswith('LoraLoader')]
        
        print(f"  Workflow stats:")
        print(f"    - Total nodes: {len(workflow)}")
        print(f"    - Dynamic nodes (**): {len(dynamic_nodes)}")
        print(f"    - LoRA nodes: {len(lora_nodes)}")
        
        # Send to ComfyUI
        print(f"  Sending to ComfyUI...")
        prompt_id = send_workflow_to_comfyui(workflow, work_id)
        if not prompt_id:
            print(f"  [FAIL] Could not queue scene {idx + 1}")
    
    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    print(f"Total scenes processed: {len(scenes)}")
    print(f"Work IDs: {all_work_ids}")
    print(f"Temp workflows saved to: {TEMP_DIR}")
    print("\nYou can now check:")
    print(f"  1. Temp workflow files in: {TEMP_DIR}")
    print(f"  2. ComfyUI output for generated images")
    print("=" * 60)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Test Image Workflow Generation")
    parser.add_argument("--task", type=str, default="multiple-scene-images_20260328_175631.json",
                       help="Task JSON filename")
    
    args = parser.parse_args()
    run_test(args.task)
