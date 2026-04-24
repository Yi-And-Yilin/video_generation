"""
Workflow Generator for ComfyUI API

Generates dynamic workflow JSON files based on template, actions, and parameters.
Uses the StandardWorkflowParams interface for consistent parameter exchange.
"""

import json
import os
import csv
import random
from typing import Dict, List, Any, Optional
from copy import deepcopy

# Get the directory where this script is located
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Wan workflow base directory (projects/wan/workflow/)
WAN_WORKFLOW_BASE = os.path.join(os.path.dirname(SCRIPT_DIR), "wan", "workflow")
WAN_WORKFLOW_IMAGE_DIR = os.path.join(WAN_WORKFLOW_BASE, "image")
WAN_WORKFLOW_VIDEO_DIR = os.path.join(WAN_WORKFLOW_BASE, "video")


def _resolve_wan_template_path(template_name: str) -> Optional[str]:
    """
    Resolve the full path for a WAN workflow template by searching
    root, image/, and video/ subfolders.

    Resolution order:
    1. Root (shared templates: FlashSVR, clean_up, final_upscale)
    2. image/ (wan_image)
    3. video/ (wan_2.1_*, wan_2.2_*, etc.)

    Returns the full file path, or None if not found.
    """
    # Root (shared)
    root_path = os.path.join(WAN_WORKFLOW_BASE, f"{template_name}.json")
    if os.path.exists(root_path):
        return root_path
    # Image subfolder
    img_path = os.path.join(WAN_WORKFLOW_IMAGE_DIR, f"{template_name}.json")
    if os.path.exists(img_path):
        return img_path
    # Video subfolder
    vid_path = os.path.join(WAN_WORKFLOW_VIDEO_DIR, f"{template_name}.json")
    if os.path.exists(vid_path):
        return vid_path
    return None

# Import parameter extraction module (same directory as workflow_generator.py)
import sys
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)


def _resolve_lora_params(acts: List[str], csv_name: str, workflow_name: str = None,
                         extra_lora_names: List[str] = None,
                         extra_lora_strengths: List[float] = None) -> Dict[str, Any]:
    """
    Resolve LoRA names and strengths from acts + CSV lookup.
    Returns dict with lora1_name..lora5_name and lora1_strength..lora5_strength.
    """
    if extra_lora_names is None:
        extra_lora_names = []
    if extra_lora_strengths is None:
        extra_lora_strengths = []

    loras = list(zip(extra_lora_names, extra_lora_strengths))

    csv_path = os.path.join(os.path.dirname(SCRIPT_DIR), "lookup", csv_name)
    if csv_path and os.path.exists(csv_path):
        lookup = load_lora_lookup(csv_path, filter_type="image" if csv_name == "image_lora_lookup.csv" else "video",
                                  workflow_name=workflow_name)
        for act in acts:
            act_lower = act.lower().strip()
            if act_lower in lookup:
                loras.extend(lookup[act_lower])

    result = {}
    for i in range(1, 6):
        idx = i - 1
        if idx < len(loras):
            lora = loras[idx]
            if isinstance(lora, dict):
                result[f'lora{i}_name'] = lora['name']
                result[f'lora{i}_strength'] = lora['strength']
            else:
                result[f'lora{i}_name'] = lora[0]
                result[f'lora{i}_strength'] = lora[1]
        else:
            result[f'lora{i}_name'] = "xl\\add-detail.safetensors"
            result[f'lora{i}_strength'] = 0.0
    return result


def generate_workflow_from_standard_params(template: str, params: Dict[str, Any],
                                            type: str = "image",
                                            acts: List[str] = None,
                                            extra_lora_names: List[str] = None,
                                            extra_lora_strengths: List[float] = None) -> Dict:
    """
    Generate a ComfyUI workflow JSON from a StandardWorkflowParams dict.

    This is the canonical entry point for workflow generation. It:
    1. Loads the template JSON
    2. Resolves LoRA lookups from acts (if provided)
    3. Merges params with LoRA resolution
    4. Applies placeholder replacement

    Parameters
    ----------
    template : str
        Template name (e.g., "wan_image", "ltx_sampling").
    params : Dict[str, Any]
        Parameters from StandardWorkflowParams (use params.to_dict() or params.for_wan_image()).
    type : str
        "image" or "video" — determines LoRA CSV and template directory.
    acts : List[str], optional
        Action tags for LoRA lookup.
    extra_lora_names : List[str], optional
        Direct LoRA names to use (bypasses CSV lookup).
    extra_lora_strengths : List[float], optional
        Direct LoRA strengths.

    Returns
    -------
    Dict
        The workflow JSON with placeholders applied.
    """
    if acts is None: acts = []
    if extra_lora_names is None: extra_lora_names = []
    if extra_lora_strengths is None: extra_lora_strengths = []

    # Determine template directory
    if type == "image":
        template = "wan_image"
    else:
        template_dir = os.path.join(SCRIPT_DIR, "workflow", type)

    if type == "image":
        # Use the new subfolder-aware resolver for wan_image
        template_path = _resolve_wan_template_path("wan_image")
        if template_path is None:
            raise ValueError(f"Failed to resolve wan_image template in projects/wan/workflow/ (root, image/, video/)")
    else:
        template_path = os.path.join(template_dir, f"{template}.json")

    try:
        with open(template_path, 'r', encoding='utf-8') as f:
            workflow = json.load(f)
    except Exception as e:
        raise ValueError(f"Failed to load template '{template_path}': {e}")

    workflow = deepcopy(workflow)

    # Start with provided params
    param_dict = dict(params)

    # Resolve LoRAs
    csv_name = "image_lora_lookup.csv" if type == "image" else "lora_lookup.csv"
    lora_resolved = _resolve_lora_params(
        acts, csv_name, workflow_name=template,
        extra_lora_names=extra_lora_names,
        extra_lora_strengths=extra_lora_strengths
    )
    param_dict.update(lora_resolved)

    # Apply placeholders
    return apply_wan_placeholders(workflow, param_dict)


def generate_workflow_for_wan_image(task_path: str, scene_index: int = 0,
                                     resolution: str = "1024*1024",
                                     prompt_index: int = 0) -> Dict:
    """
    Generate a WAN image (SDXL) workflow from a task.json file.

    This is the primary entry point for the New tab's "Run ComfyUI" button.
    It:
    1. Loads and parses the task.json
    2. Extracts StandardWorkflowParams via extract_params_from_new_tab_task
    3. Generates the wan_image workflow via generate_workflow_from_standard_params

    Parameters
    ----------
    task_path : str
        Path to the task.json file.
    scene_index : int
        Which scene/location to generate (default 0).
    resolution : str
        "WIDTH*HEIGHT" string (default "1024*1024").
    prompt_index : int
        Which prompt in the location's prompts list to use (default 0).

    Returns
    -------
    Dict
        The workflow JSON for ComfyUI API.
    """
    from parameter_extraction import (
        extract_params_from_new_tab_task,
        create_default_image_params
    )

    # Extract parameters from task.json
    params = extract_params_from_new_tab_task(task_path, scene_index=scene_index,
                                              resolution=resolution,
                                              prompt_index=prompt_index)

    # Generate workflow using standard params
    workflow = generate_workflow_from_standard_params(
        template="wan_image",
        params=params.for_wan_image(),
        type="image",
        acts=params.main_sex_act if params.main_sex_act else [],
        extra_lora_names=[p.get("lora_name", "") for p in getattr(params, "sex_loras", [])] if hasattr(params, "sex_loras") else [],
        extra_lora_strengths=[0.7] * len(getattr(params, "sex_loras", [])) if hasattr(params, "sex_loras") else []
    )

    return workflow


def generate_workflow_for_ltx_video(task_path: str, resolution: str = "1280*720",
                                      seconds: float = 10.0, step: str = "prep") -> Dict:
    """
    Generate an LTX video workflow from a task.json file.

    Parameters
    ----------
    task_path : str
        Path to the task.json file.
    resolution : str
        "WIDTH*HEIGHT" string.
    seconds : float
        Video duration in seconds.
    step : str
        Which LTX step: "prep", "encode", "sampling", "decode".

    Returns
    -------
    Dict
        The workflow JSON for ComfyUI API.
    """
    from parameter_extraction import extract_params_for_wan_video

    params = extract_params_for_wan_video(task_path, resolution=resolution, seconds=seconds)

    template_map = {
        "prep": "ltx_preparation",
        "encode": "ltx-text-encoding",
        "sampling": "ltx_sampling",
        "decode": "ltx_latent",
    }
    template = template_map.get(step, "ltx_sampling")

    return generate_workflow_from_standard_params(
        template=template,
        params=params.for_ltx_sampling() if step == "sampling" else params.to_dict(),
        type="video",
        acts=[],
    )


# Re-export for convenience
if 'parameter_extraction' in dir():
    from parameter_extraction import (
        StandardWorkflowParams,
        extract_params_from_new_tab_task,
        extract_params_from_scene_task,
        extract_params_for_wan_video,
        create_default_image_params,
    )


def load_lora_lookup(csv_path: str = None, filter_type: str = None, workflow_name: str = None) -> Dict[str, List[Dict]]:
    """
    Load LoRA lookup table from CSV.
    Returns a dict mapping action tags to LoRA configurations.
    
    Supports two CSV formats:
    1. lora_lookup.csv: columns tag1, tag2, type
    2. image_lora_lookup.csv: columns lora_tag, workflow name
    
    Args:
        csv_path: Path to lora_lookup.csv or image_lora_lookup.csv
        filter_type: Filter by type column (e.g., "image", "video"). If None, returns all.
        workflow_name: Filter by workflow name column (for image_lora_lookup.csv format)
    """
    if csv_path is None:
        csv_path = os.path.join(SCRIPT_DIR, "lora_lookup.csv")
    
    lookup = {}
    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Filter by type if specified (for lora_lookup.csv format)
                row_type = row.get('type', '').strip().lower()
                if filter_type and row_type and row_type != filter_type.lower():
                    continue
                
                # Filter by workflow name if specified (for image_lora_lookup.csv format)
                row_workflow = row.get('workflow name', '').strip()
                if workflow_name and row_workflow and row_workflow != workflow_name:
                    continue
                
                # Support both lora_tag (image format) and tag1 (video format)
                lora_tag = row.get('lora_tag', '').strip().lower()
                tag1 = row.get('tag1', '').strip().lower()
                tag2 = row.get('tag2', '').strip().lower()
                
                # Use lora_tag if available, otherwise use tag1
                if lora_tag:
                    key = lora_tag
                elif tag1:
                    key = tag1
                    if tag2:
                        key = f"{tag1}+{tag2}"
                else:
                    continue
                
                # Collect all LoRAs from this row
                loras = []
                for i in range(1, 6):  # lora1_name to lora5_name
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
                    lookup[key] = loras
                    # Also store with just tag1 for simpler lookup (video format)
                    if tag1 and tag1 not in lookup:
                        lookup[tag1] = loras
        
        return lookup
    except Exception as e:
        print(f"Error loading lora_lookup.csv: {e}")
        return {}


def find_nodes_by_title_pattern(workflow: Dict, pattern: str) -> List[tuple]:
    """
    Find nodes whose _meta.title starts with the given pattern.
    Returns list of (node_id, node_data) tuples.
    """
    matches = []
    for node_id, node_data in workflow.items():
        meta = node_data.get('_meta', {})
        title = meta.get('title', '')
        if title.startswith(pattern):
            matches.append((node_id, node_data))
    return matches


def apply_wan_placeholders(workflow: Dict, params: Dict) -> Dict:
    """
    Apply WAN-style dynamic placeholder replacement to a workflow.
    Iterates through all nodes and replaces **XXX** strings in inputs.
    """
    for node_id, node in workflow.items():
        inputs = node.get("inputs", {})
        cls = node.get("class_type", "")
        for k, v in inputs.items():
            if not isinstance(v, str): continue
            
            new_val = v
            for placeholder, repl_val in params.items():
                p_key = f"**{placeholder}**"
                if p_key in new_val:
                    if cls in ["JWInteger", "Int", "PrimitiveInt", "MathExpression|pysssss", "ComfyMathExpression", "Float"] or \
                       "strength" in placeholder or "seed" in placeholder or "random" in placeholder or \
                       "width" in placeholder or "height" in placeholder or "fps" in placeholder:
                        try:
                            if "strength" in placeholder or cls == "Float": new_val = float(repl_val)
                            else: new_val = int(repl_val)
                            break 
                        except: new_val = str(repl_val)
                    else:
                        new_val = new_val.replace(p_key, str(repl_val))
            inputs[k] = new_val
    return workflow


def generate_api_workflow(
    project: str,
    type: str,
    template: str,
    acts: List[str] = None,
    width: int = 1024,
    height: int = 1024,
    length: int = 241,
    prompt: str = "",
    negative_prompt: str = "",
    work_id: str = "",
    job_id: str = "",
    step_number: int = 0,
    fps: int = 24,
    workflow_name: str = None,
    lora_lookup_path: str = None,
    template_dir: str = None,
    video_pos_prompt: str = "",
    video_prompt: str = "",
    **kwargs
) -> Dict:
    """
    Generate a ComfyUI API workflow JSON using WAN-style dynamic placeholders.
    """
    if acts is None: acts = []
    
    if type == "image":
        template = "wan_image"
        template_path = _resolve_wan_template_path("wan_image")
        if template_path is None:
            raise ValueError(f"Failed to resolve wan_image template in projects/wan/workflow/")
    elif template_dir is None:
        template_dir = os.path.join(SCRIPT_DIR, "workflow", type)
        template_path = os.path.join(template_dir, f"{template}.json")
    else:
        template_path = os.path.join(template_dir, f"{template}.json")
    
    try:
        with open(template_path, 'r', encoding='utf-8') as f: workflow = json.load(f)
    except Exception as e: raise ValueError(f"Failed to load template '{template_path}': {e}")
    
    workflow = deepcopy(workflow)
    import random
    params = {
        'prompt': video_pos_prompt or video_prompt or prompt,
        'image_pos_prompt': prompt,
        'video_pos_prompt': video_pos_prompt or prompt,
        'video_prompt': video_prompt,
        'negative_prompt': negative_prompt,
        'image_neg_prompt': negative_prompt if negative_prompt else "lowres, bad anatomy, bad hands, text, error, missing fingers, extra digit, fewer digits, cropped, worst quality, low quality, normal quality, jpeg artifacts, signature, watermark, username, blurry",
        'width': width, 'video_width': width, 'height': height, 'video_height': height,
        'length': length, 'video_length': length, 'work_id': work_id, 'job_id': job_id, 'fps': fps,
        'random_number': random.randint(1, 999999999999999), 'checkpoint': "pornmaster_proSDXLV8.safetensors",
        'save_video': work_id, 'save_image': work_id, 'load_image': f"{work_id}.png",
        'save_pos_conditioning': f"pos_{work_id}",
        'save_neg_conditioning': f"neg_{work_id}",
        'load_pos_conditioning': f"pos_{work_id}",
        'load_neg_conditioning': f"neg_{work_id}",
        'image': f"{work_id}.png"
    }
    params.update(kwargs)

    csv_name = "image_lora_lookup.csv" if type == "image" else "lora_lookup.csv"
    csv_path = os.path.join(os.path.dirname(os.path.dirname(SCRIPT_DIR)), "lookup", csv_name)
    lora_lookup = load_lora_lookup(csv_path, filter_type=type, workflow_name=template if type == "image" else None)
    
    loras_to_apply = []
    for act in acts:
        act_lower = act.lower().strip()
        if act_lower in lora_lookup: loras_to_apply.extend(lora_lookup[act_lower])
    
    for i in range(1, 6):
        if i <= len(loras_to_apply):
            params[f'lora{i}_name'] = loras_to_apply[i-1]['name']
            params[f'lora{i}_strength'] = loras_to_apply[i-1]['strength']
        else:
            params[f'lora{i}_name'] = "xl\\add-detail.safetensors"
            params[f'lora{i}_strength'] = 0.0

    return apply_wan_placeholders(workflow, params)



def generate_cleanup_workflow(job_id: str, step_number: int) -> Dict:
    """
    Generate a cleanup workflow with the job_id-step_number as finish signal.
    
    Args:
        job_id: The major job ID
        step_number: The step number (1, 2, 3, 4)
    
    Returns:
        The modified cleanup workflow
    """
    cleanup_path = _resolve_wan_template_path("clean_up")
    if cleanup_path is None:
        raise FileNotFoundError("clean_up.json template not found in projects/wan/workflow/")
    with open(cleanup_path, 'r', encoding='utf-8') as f:
        workflow = json.load(f)
    
    # Find and update finish_signal node
    finish_signal = f"{job_id}-{step_number}"
    for node_id, node_data in workflow.items():
        meta = node_data.get('_meta', {})
        title = meta.get('title', '')
        if title.startswith('**finish_signal'):
            node_data['inputs']['filename_prefix'] = finish_signal
            break
    
    return workflow


def save_workflow(workflow: Dict, output_path: str):
    """Save workflow to JSON file."""
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(workflow, f, indent=2)


# Example usage
if __name__ == "__main__":
    # Test the generator with image workflow
    workflow = generate_api_workflow(
        project="ltx",
        type="image",
        template="pornmaster_proSDXLV8",
        acts=["fingering"],
        width=1280,
        height=720,
        length=241,
        prompt="1girl, beautiful woman",
        negative_prompt="ugly, deformed, bad quality",
        work_id="test001"
    )
    
    output_path = os.path.join(SCRIPT_DIR, "test_output.json")
    save_workflow(workflow, output_path)
    print(f"Generated workflow saved to: {output_path}")