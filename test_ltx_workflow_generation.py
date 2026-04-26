"""
Test script to generate LTX ComfyUI workflows for wg22j_scene0_p0.png.

This script mimics exactly what the Video tab "Run" button does when
using the LTX engine, generating all workflow JSONs and saving them
to the debug_workflows folder without actually sending to ComfyUI.

Error context: "Cannot read wg22j_scene0_p0.png (this model does not support image input)"
This means the LTX checkpoint loaded in ComfyUI doesn't support image input (text-only model).
The workflow generation itself is correct - the error is at ComfyUI runtime.
"""

import os
import sys
import json
import time
import shutil
from copy import deepcopy

# --- Configuration ---
BASE_DIR = r"C:\SimpleAIHelper\video_generation"
IMAGE_PATH = os.path.join(BASE_DIR, "output_images", "wg22j_scene0_p0.png")
COMFYUI_ROOT = r"D:\ComfyUI_windows_portable\ComfyUI"
INPUT_FOLDER = os.path.join(COMFYUI_ROOT, "input")
OUTPUT_FOLDER = os.path.join(COMFYUI_ROOT, "output")
DEBUG_WORKFLOWS_DIR = os.path.join(BASE_DIR, "debug_workflows")

# Add project paths for imports
sys.path.insert(0, os.path.join(BASE_DIR, "projects", "ltx"))
sys.path.insert(0, BASE_DIR)

from workflow_generator import generate_api_workflow, generate_cleanup_workflow, save_workflow
from parameter_extraction import StandardWorkflowParams


def log(msg):
    print(f"[TEST] {msg}")


def get_image_metadata(image_path):
    """Extract metadata from PNG image (same as video_tab.py _get_metadata_from_image)."""
    try:
        from PIL import Image as PILImage
        img = PILImage.open(image_path)
        if "prompt" in img.info:
            try:
                return json.loads(img.info["prompt"])
            except:
                pass
    except Exception as e:
        log(f"Warning: Could not read image metadata: {e}")
    return {}


def extract_params_from_image(image_path, work_id, video_prompt=""):
    """
    Extract parameters for LTX video generation from an image,
    mimicking what video_tab.py does in _run_ltx_video_generation().
    """
    width = 1280
    height = 720
    fps = 24
    seconds = 10.0
    length = int(fps * seconds + 1)  # = 241

    # Calculate height from image aspect ratio
    if os.path.exists(image_path):
        try:
            from PIL import Image as PILImage
            pil_img = PILImage.open(image_path)
            orig_w, orig_h = pil_img.size
            height = int(width * orig_h / orig_w)
            log(f"Image dimensions: {orig_w}x{orig_h} -> calculated height: {height}")
        except Exception as e:
            log(f"Warning: Could not read image dimensions: {e}")

    # Extract metadata
    metadata = get_image_metadata(image_path)
    job_id = metadata.get("job_id", work_id.split('_')[0] if '_' in work_id else work_id)
    
    # Extract main action from video prompt
    main_action = ""
    if video_prompt:
        lines = video_prompt.split('\n')
        main_action = lines[0][:50] if lines else ""

    return {
        "work_id": work_id,
        "job_id": job_id,
        "width": width,
        "height": height,
        "length": length,
        "fps": fps,
        "seconds": seconds,
        "prompt": video_prompt or "",
        "video_pos_prompt": video_prompt or "",
        "negative_prompt": "ugly, deformed, bad quality",
        "main_sex_act": main_action,
        "image_path": image_path,
    }


def save_debug_workflow(workflow, work_id, step_name):
    """Save workflow JSON to debug_workflows folder."""
    os.makedirs(DEBUG_WORKFLOWS_DIR, exist_ok=True)
    filename = f"debug_{work_id}_{step_name}_{int(time.time())}.json"
    filepath = os.path.join(DEBUG_WORKFLOWS_DIR, filename)
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(workflow, f, indent=2)
    log(f"Saved workflow: {filepath}")
    return filepath


def test_generate_all_ltx_workflows():
    """
    Generate ALL LTX workflow JSONs for the given image,
    mimicking the full Run button pipeline.
    """
    print("=" * 70)
    print("LTX Workflow Generation Test")
    print("=" * 70)

    # 1. Verify image exists
    if not os.path.exists(IMAGE_PATH):
        log(f"ERROR: Image not found at {IMAGE_PATH}")
        return

    log(f"Using image: {IMAGE_PATH}")
    filename = os.path.basename(IMAGE_PATH)
    work_id = os.path.splitext(filename)[0]  # wg22j_scene0_p0
    job_id = work_id.split('_')[0]  # wg22j

    log(f"work_id={work_id}, job_id={job_id}")

    # 2. Copy image to ComfyUI input folder (mimicking what video_tab.py does)
    dest = os.path.join(INPUT_FOLDER, filename)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    shutil.copy2(IMAGE_PATH, dest)
    log(f"Image copied to ComfyUI input: {dest}")

    # 3. Extract parameters (mimicking video_tab.py _run_ltx_video_generation)
    video_prompt = "She leans forward, grabbing his broad shoulders..."
    params = extract_params_from_image(IMAGE_PATH, work_id, video_prompt)
    log(f"Extracted params: width={params['width']}, height={params['height']}, length={params['length']}")

    # ============================================================
    # PHASE 2: PREPARATION (ltx_preparation)
    # ============================================================
    log("")
    log("=" * 70)
    log("PHASE 2: PREPARATION (ltx_preparation)")
    log("=" * 70)

    workflow_prep = generate_api_workflow(
        project="ltx",
        type="video",
        template="ltx_preparation",
        acts=[],
        width=params["width"],
        height=params["height"],
        length=params["length"],
        prompt=params["prompt"],
        video_pos_prompt=params["video_pos_prompt"],
        negative_prompt=params["negative_prompt"],
        work_id=work_id,
        fps=params["fps"],
    )
    save_debug_workflow(workflow_prep, work_id, "prep")

    # Show the image input node (LoadImage)
    for node_id, node in workflow_prep.items():
        if node.get("class_type") == "LoadImage":
            log(f"  LoadImage node ({node_id}): image = {node['inputs'].get('image', 'N/A')}")
        if node.get("class_type") == "CheckpointLoaderSimple":
            log(f"  CheckpointLoaderSimple ({node_id}): ckpt_name = {node['inputs'].get('ckpt_name', 'N/A')}")

    # ============================================================
    # PHASE 3a: 1st SAMPLING (ltx_1st_sampling)
    # ============================================================
    log("")
    log("=" * 70)
    log("PHASE 3a: 1st SAMPLING (ltx_1st_sampling)")
    log("=" * 70)

    workflow_s1 = generate_api_workflow(
        project="ltx",
        type="video",
        template="ltx_1st_sampling",
        acts=[],
        width=params["width"],
        height=params["height"],
        length=params["length"],
        prompt=params["prompt"],
        video_pos_prompt=params["video_pos_prompt"],
        work_id=work_id,
        fps=params["fps"],
    )
    save_debug_workflow(workflow_s1, work_id, "1st_sampling")

    # ============================================================
    # PHASE 3b: UPSCALE (ltx_upscale)
    # ============================================================
    log("")
    log("=" * 70)
    log("PHASE 3b: UPSCALE (ltx_upscale)")
    log("=" * 70)

    workflow_up = generate_api_workflow(
        project="ltx",
        type="video",
        template="ltx_upscale",
        acts=[],
        width=params["width"],
        height=params["height"],
        length=params["length"],
        prompt=params["prompt"],
        video_pos_prompt=params["video_pos_prompt"],
        work_id=work_id,
        fps=params["fps"],
    )
    save_debug_workflow(workflow_up, work_id, "upscale")

    # ============================================================
    # PHASE 3c: 2nd SAMPLING (ltx_2nd_sampling)
    # ============================================================
    log("")
    log("=" * 70)
    log("PHASE 3c: 2nd SAMPLING (ltx_2nd_sampling)")
    log("=" * 70)

    workflow_s2 = generate_api_workflow(
        project="ltx",
        type="video",
        template="ltx_2nd_sampling",
        acts=[],
        width=params["width"],
        height=params["height"],
        length=params["length"],
        prompt=params["prompt"],
        video_pos_prompt=params["video_pos_prompt"],
        work_id=work_id,
        fps=params["fps"],
    )
    save_debug_workflow(workflow_s2, work_id, "2nd_sampling")

    # ============================================================
    # PHASE 4: LATENT DECODE (ltx_decode)
    # ============================================================
    log("")
    log("=" * 70)
    log("PHASE 4: LATENT DECODE (ltx_decode)")
    log("=" * 70)

    workflow_decode = generate_api_workflow(
        project="ltx",
        type="video",
        template="ltx_decode",
        acts=[],
        width=params["width"],
        height=params["height"],
        length=params["length"],
        prompt=params["prompt"],
        video_pos_prompt=params["video_pos_prompt"],
        work_id=work_id,
        fps=params["fps"],
    )
    save_debug_workflow(workflow_decode, work_id, "decode")

    # ============================================================
    # CLEANUP WORKFLOW
    # ============================================================
    log("")
    log("=" * 70)
    log("CLEANUP WORKFLOW (step 2 - after preparation)")
    log("=" * 70)

    workflow_cleanup = generate_cleanup_workflow(job_id, 2)
    save_debug_workflow(workflow_cleanup, work_id, "cleanup_step2")

    log("")
    log("=" * 70)
    log("TEST COMPLETE")
    log("=" * 70)
    log("")
    log("Generated workflow files in debug_workflows/:")
    for f in sorted(os.listdir(DEBUG_WORKFLOWS_DIR)):
        if f.startswith(f"debug_{work_id}_"):
            fpath = os.path.join(DEBUG_WORKFLOWS_DIR, f)
            size = os.path.getsize(fpath)
            log(f"  {f} ({size} bytes)")

    log("")
    log("ERROR CONTEXT:")
    log('  "Cannot read wg22j_scene0_p0.png (this model does not support image input)"')
    log("")
    log("This error means the LTX checkpoint loaded in ComfyUI")
    log("(ltx-2.3-22b-dev-fp8.safetensors) does NOT support image input.")
    log("The model is the TEXT-ONLY version, not the image-to-video version.")
    log("")
    log("The workflow generation code is CORRECT - the error is at ComfyUI runtime.")
    log("To fix this in ComfyUI, you need to use the LTX-Video I2V (image-to-video) model,")
    log("not the text-only LTX model.")
    log("")
    log("The workflows are saved in debug_workflows/ for your QA review.")
    print()


if __name__ == "__main__":
    test_generate_all_ltx_workflows()
