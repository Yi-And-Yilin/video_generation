"""
Integration test: Generate LTX workflows for aj5s7_scene4_p1.png

This script mimics exactly what the Video tab "Run" button does when
using the LTX engine, generating all workflow JSONs and saving them
to the debug_workflows folder for user review.
"""

import os
import sys
import json
import shutil
from copy import deepcopy

BASE_DIR = r"C:\SimpleAIHelper\video_generation"
IMAGE_PATH = os.path.join(BASE_DIR, "output_images", "aj5s7_scene4_p1.png")
DEBUG_WORKFLOWS_DIR = os.path.join(BASE_DIR, "debug_workflows")

# Add project paths for imports
sys.path.insert(0, os.path.join(BASE_DIR, "projects", "ltx"))
sys.path.insert(0, BASE_DIR)

from workflow_generator import generate_api_workflow, save_workflow
from parameter_extraction import StandardWorkflowParams


def log(msg):
    print(f"[INTEGRATION TEST] {msg}")


def get_image_metadata(image_path):
    """Extract metadata from PNG image."""
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

    if os.path.exists(image_path):
        try:
            from PIL import Image as PILImage
            pil_img = PILImage.open(image_path)
            orig_w, orig_h = pil_img.size
            height = int(width * orig_h / orig_w)
            log(f"Image dimensions: {orig_w}x{orig_h} -> calculated height: {height}")
        except Exception as e:
            log(f"Warning: Could not read image dimensions: {e}")

    metadata = get_image_metadata(image_path)
    job_id = metadata.get("job_id", work_id.split('_')[0] if '_' in work_id else work_id)
    
    # Extract main_sex_act from metadata (FIXED: this is the key fix!)
    main_sex_act = metadata.get("main_sex_act", "")
    if not main_sex_act:
        # Fallback to image_prompt's sex_act field (PNG metadata from New tab)
        main_sex_act = metadata.get("sex_act", "")
    
    # Build video_pos_prompt from metadata
    if video_prompt:
        video_pos = video_prompt
    elif isinstance(metadata.get("video_prompt"), dict):
        vp = metadata["video_prompt"]
        video_pos = f"Action: {vp.get('action', '')} Line: {vp.get('line', '')} Sound: {vp.get('female_character_sound', '')} Audio: {vp.get('audio', '')}"
    else:
        video_pos = metadata.get("prompt", "")

    log(f"Extracted sex_act from metadata: '{main_sex_act}'")
    log(f"Extracted job_id: '{job_id}'")

    return {
        "work_id": work_id,
        "job_id": job_id,
        "width": width,
        "height": height,
        "length": length,
        "fps": fps,
        "seconds": seconds,
        "prompt": metadata.get("prompt", ""),
        "video_pos_prompt": video_pos,
        "negative_prompt": "ugly, deformed, bad quality",
        "main_sex_act": main_sex_act,
        "image_path": image_path,
        "metadata": metadata
    }


def save_debug_workflow(workflow, work_id, step_name):
    """Save workflow JSON to debug_workflows folder."""
    os.makedirs(DEBUG_WORKFLOWS_DIR, exist_ok=True)
    filename = f"aj5s7_scene4_p1_{step_name}.json"
    filepath = os.path.join(DEBUG_WORKFLOWS_DIR, filename)
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(workflow, f, indent=2)
    log(f"Saved workflow: {filepath}")
    return filepath


def show_lora_nodes(workflow, step_name):
    """Show LoRA-related nodes for review."""
    print(f"\n{'='*70}")
    print(f"LORA NODES — {step_name}")
    print(f"{'='*70}")
    
    for node_id, node in sorted(workflow.items(), key=lambda x: int(x[0])):
        cls = node.get("class_type", "")
        if "LoraLoader" in cls or cls == "Lora Loader Stack (rgthree)":
            inputs = node.get("inputs", {})
            title = node.get("_meta", {}).get("title", "N/A")
            print(f"\n  Node {node_id} ({title}):")
            print(f"    class_type: {cls}")
            if "lora_name" in inputs:
                print(f"    lora_name: {inputs['lora_name']}")
            if "strength_model" in inputs:
                print(f"    strength_model: {inputs['strength_model']}")
            if "model" in inputs:
                model_ref = inputs["model"]
                if isinstance(model_ref, list):
                    print(f"    model: [{model_ref[0]}, {model_ref[1]}]")
            print()


def main():
    print("=" * 70)
    print("LTX INTEGRATION TEST: aj5s7_scene4_p1")
    print("=" * 70)

    if not os.path.exists(IMAGE_PATH):
        log(f"ERROR: Image not found at {IMAGE_PATH}")
        return

    log(f"Using image: {IMAGE_PATH}")
    filename = os.path.basename(IMAGE_PATH)
    work_id = os.path.splitext(filename)[0]  # aj5s7_scene4_p1
    job_id = work_id.split('_')[0]  # aj5s7

    log(f"work_id={work_id}, job_id={job_id}")

    # Extract parameters
    video_prompt = ""
    params = extract_params_from_image(IMAGE_PATH, work_id, video_prompt)
    
    acts = [params["main_sex_act"]] if params["main_sex_act"] else []
    log(f"Acts for CSV lookup: {acts}")

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
        acts=acts,
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
    show_lora_nodes(workflow_prep, "prep")

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
        acts=acts,
        width=params["width"],
        height=params["height"],
        length=params["length"],
        prompt=params["prompt"],
        video_pos_prompt=params["video_pos_prompt"],
        negative_prompt=params["negative_prompt"],
        work_id=work_id,
        fps=params["fps"],
    )
    save_debug_workflow(workflow_s1, work_id, "1st_sampling")
    show_lora_nodes(workflow_s1, "1st_sampling")

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
        acts=acts,
        width=params["width"],
        height=params["height"],
        length=params["length"],
        prompt=params["prompt"],
        video_pos_prompt=params["video_pos_prompt"],
        negative_prompt=params["negative_prompt"],
        work_id=work_id,
        fps=params["fps"],
        load_image=f"{work_id}.png",
    )
    save_debug_workflow(workflow_up, work_id, "upscale")
    show_lora_nodes(workflow_up, "upscale")

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
        acts=acts,
        width=params["width"],
        height=params["height"],
        length=params["length"],
        prompt=params["prompt"],
        video_pos_prompt=params["video_pos_prompt"],
        negative_prompt=params["negative_prompt"],
        work_id=work_id,
        fps=params["fps"],
    )
    save_debug_workflow(workflow_s2, work_id, "2nd_sampling")
    show_lora_nodes(workflow_s2, "2nd_sampling")

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
        acts=acts,
        width=params["width"],
        height=params["height"],
        length=params["length"],
        prompt=params["prompt"],
        video_pos_prompt=params["video_pos_prompt"],
        negative_prompt=params["negative_prompt"],
        work_id=work_id,
        fps=params["fps"],
    )
    save_debug_workflow(workflow_decode, work_id, "decode")
    show_lora_nodes(workflow_decode, "decode")

    # ============================================================
    # VERIFICATION
    # ============================================================
    log("")
    log("=" * 70)
    log("VERIFICATION SUMMARY")
    log("=" * 70)
    
    all_ok = True
    
    for step in ["prep", "1st_sampling", "upscale", "2nd_sampling", "decode"]:
        if step in ["prep", "decode"]:
            # These templates may not have LoRA nodes, skip
            continue
        
        wf = json.load(open(os.path.join(DEBUG_WORKFLOWS_DIR, f"aj5s7_scene4_p1_{step}.json")))
        
        # Find Distill Lora node (node 9 in 1st_sampling, node 2 in 2nd_sampling)
        distill_node_id = "9" if step == "1st_sampling" else "2"
        lora2_node_id = "10" if step == "1st_sampling" else "3"
        
        distill_name = wf[distill_node_id]["inputs"].get("lora_name", "N/A")
        distill_strength = wf[distill_node_id]["inputs"].get("strength_model", "N/A")
        lora2_name = wf[lora2_node_id]["inputs"].get("lora_name", "N/A")
        lora2_strength = wf[lora2_node_id]["inputs"].get("strength_model", "N/A")
        
        print(f"\n  [{step}]")
        print(f"    Distill LoRA (node {distill_node_id}): {distill_name} (strength: {distill_strength})")
        print(f"    Dynamic LoRA 1 (node {lora2_node_id}): {lora2_name} (strength: {lora2_strength})")
        
        # Verify Distill LoRA is NOT replaced
        expected_distill = "ltx\\ltx-2.3-22b-distilled-lora-384-1.1.safetensors"
        if distill_name == expected_distill:
            print(f"    ✓ PASS: Distill LoRA preserved")
        else:
            print(f"    ✗ FAIL: Distill LoRA was replaced!")
            all_ok = False
        
        # Verify Dynamic LoRA 1 is from CSV lookup (lying_cowgirl -> NSFW_furryv2.safetensors)
        if "NSFW_furryv2" in str(lora2_name):
            print(f"    ✓ PASS: Dynamic LoRA from CSV lookup")
        else:
            print(f"    ✗ FAIL: Dynamic LoRA not from CSV lookup!")
            all_ok = False
    
    if all_ok:
        print("\n  ✓✓✓ ALL CHECKS PASSED ✓✓✓")
    else:
        print("\n  ✗✗✗ SOME CHECKS FAILED ✗✗✗")
    
    log("")
    log("Generated workflow files:")
    for f in sorted(os.listdir(DEBUG_WORKFLOWS_DIR)):
        if f.startswith("aj5s7_scene4_p1_"):
            fpath = os.path.join(DEBUG_WORKFLOWS_DIR, f)
            size = os.path.getsize(fpath)
            log(f"  {f} ({size} bytes)")
    
    print()


if __name__ == "__main__":
    main()
