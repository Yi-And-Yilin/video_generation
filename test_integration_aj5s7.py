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
    import codecs
    sys.stdout.buffer.write(("[INTEGRATION TEST] " + msg + "\n").encode("utf-8"))


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
    
    # Extract main_sex_act from metadata
    main_sex_act = metadata.get("main_sex_act", "")
    if not main_sex_act:
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
        if cls == "LoraLoaderModelOnly" or cls == "Lora Loader Stack (rgthree)":
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


def count_dynamic_lora_nodes(workflow):
    """Count the number of Dynamic LoRA nodes in a workflow."""
    count = 0
    for node_id, node in workflow.items():
        title = node.get("_meta", {}).get("title", "")
        cls = node.get("class_type", "")
        if cls == "LoraLoaderModelOnly" and title.startswith("Dynamic LoRA"):
            count += 1
    return count


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
    n_lora_s1 = count_dynamic_lora_nodes(workflow_s1)
    log(f"  Dynamic LoRA nodes in 1st_sampling: {n_lora_s1}")

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
    n_lora_up = count_dynamic_lora_nodes(workflow_up)
    log(f"  Dynamic LoRA nodes in upscale: {n_lora_up}")

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
    n_lora_s2 = count_dynamic_lora_nodes(workflow_s2)
    log(f"  Dynamic LoRA nodes in 2nd_sampling: {n_lora_s2}")

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
            # These templates don't have LoRA nodes, skip
            continue
        
        wf = json.load(open(os.path.join(DEBUG_WORKFLOWS_DIR, f"aj5s7_scene4_p1_{step}.json")))
        
        # Find all LoRA nodes
        distill_nodes = []
        dynamic_lora_nodes = []
        for nid, node in wf.items():
            title = node.get("_meta", {}).get("title", "")
            cls = node.get("class_type", "")
            if cls == "LoraLoaderModelOnly":
                if title == "Distill Lora":
                    distill_nodes.append(nid)
                elif title.startswith("Dynamic LoRA"):
                    dynamic_lora_nodes.append(nid)
        
        n_dynamic = len(dynamic_lora_nodes)
        log(f"\n  [{step}]")
        log(f"    Distill LoRA nodes: {distill_nodes}")
        log(f"    Dynamic LoRA nodes: {dynamic_lora_nodes} (count: {n_dynamic})")
        
        # Verify Distill LoRA is NOT replaced
        for distill_id in distill_nodes:
            distill_name = wf[distill_id]["inputs"].get("lora_name", "N/A")
            expected_distill = "ltx\\ltx-2.3-22b-distilled-lora-384-1.1.safetensors"
            if distill_name == expected_distill:
                log(f"    [PASS] Distill LoRA (node {distill_id}) preserved: {distill_name}")
            else:
                log(f"    [FAIL] Distill LoRA was replaced! Expected {expected_distill}, got {distill_name}")
                all_ok = False
        
        # Verify Dynamic LoRA nodes use correct LoRA names from CSV
        for dlora_id in dynamic_lora_nodes:
            dlora_name = wf[dlora_id]["inputs"].get("lora_name", "N/A")
            dlora_strength = wf[dlora_id]["inputs"].get("strength_model", "N/A")
            log(f"    Dynamic LoRA node {dlora_id}: {dlora_name} (strength: {dlora_strength})")
            
            # Check that NSFW_furryv2 is in the first LoRA
            if dlora_id == dynamic_lora_nodes[0]:
                if "NSFW_furryv2" in str(dlora_name):
                    log(f"    [PASS] First LoRA uses NSFW_furryv2 from CSV")
                else:
                    log(f"    [FAIL] First LoRA should use NSFW_furryv2 but got: {dlora_name}")
                    all_ok = False
    
    if all_ok:
        log("\n  *** ALL CHECKS PASSED ***")
    else:
        log("\n  *** SOME CHECKS FAILED ***")
    
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
