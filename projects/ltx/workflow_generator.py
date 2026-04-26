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

# Wan workflow base directory (workflows/ — shared with wan workflows)
WAN_WORKFLOW_BASE = os.path.join(os.path.dirname(os.path.dirname(SCRIPT_DIR)), "workflows")
WAN_WORKFLOW_IMAGE_DIR = os.path.join(WAN_WORKFLOW_BASE, "image")
WAN_WORKFLOW_VIDEO_DIR = os.path.join(WAN_WORKFLOW_BASE, "video")

# LTX video workflow base directory (workflows/video/) — new modular workflow templates
# From projects/ltx/, go up two levels to project root, then into workflows/video/
LTX_WORKFLOW_BASE = os.path.join(os.path.dirname(os.path.dirname(SCRIPT_DIR)), "workflows", "video")

# Import parameter extraction module (same directory as workflow_generator.py)
import sys
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from parameter_extraction import StandardWorkflowParams


def _resolve_wan_template_path(template_name: str) -> Optional[str]:
    """
    Resolve the full path for a WAN workflow template by searching
    root, image/, and video/ subfolders.
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


def _resolve_ltx_template_path(template_name: str) -> Optional[str]:
    """
    Resolve the full path for an LTX workflow template.
    Only checks root (workflows/video/) — no subfolder fallback.
    """
    root_path = os.path.join(LTX_WORKFLOW_BASE, f"{template_name}.json")
    if os.path.exists(root_path):
        return root_path
    return None


def _resolve_lora_params(acts: List[str], csv_name: str, workflow_name: str = None,
                         extra_lora_names: List[str] = None,
                         extra_lora_strengths: List[float] = None) -> Dict[str, Any]:
    """
    Resolve LoRA names and strengths from acts + CSV lookup.
    """
    if extra_lora_names is None:
        extra_lora_names = []
    if extra_lora_strengths is None:
        extra_lora_strengths = []

    loras = list(zip(extra_lora_names, extra_lora_strengths))

    # SCRIPT_DIR is projects/ltx, so we need to go up two levels to reach root
    ROOT_DIR = os.path.dirname(os.path.dirname(SCRIPT_DIR))
    csv_path = os.path.join(ROOT_DIR, "lookup", csv_name)
    # print(f"DEBUG: _resolve_lora_params: csv_path={csv_path}, exists={os.path.exists(csv_path)}")
    if csv_path and os.path.exists(csv_path):
        lookup = load_lora_lookup(csv_path, filter_type="image" if csv_name == "image_lora_lookup.csv" else "video",
                                  workflow_name=workflow_name)
        print(f"DEBUG: lookup has {len(lookup)} entries, acts={acts}, workflow_name={workflow_name}")
        for act in acts:
            act_lower = act.lower().strip()
            if act_lower in lookup:
                print(f"DEBUG: Found '{act_lower}' in lookup, adding {len(lookup[act_lower])} loras")
                loras.extend(lookup[act_lower])
            else:
                print(f"DEBUG: '{act_lower}' NOT in lookup")

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


def apply_wan_placeholders(workflow: Dict, params: Dict) -> Dict:
    """
    Apply WAN-style dynamic placeholder replacement to a workflow.
    Iterates through all nodes and replaces **XXX** strings in inputs.
    
    Enhanced type conversion logic matching workflow_selector.py.
    """
    for node_id, node in workflow.items():
        if not isinstance(node, dict):
            continue
        inputs = node.get("inputs", {})
        cls = node.get("class_type", "")
        for k, v in inputs.items():
            if not isinstance(v, str):
                continue
            
            new_val = v
            for placeholder, repl_val in params.items():
                p_key = f"**{placeholder}**"
                if p_key in str(new_val):
                    # Type conversion check
                    should_convert = (cls in ["JWInteger", "Int", "PrimitiveInt", "MathExpression|pysssss", 
                                             "ComfyMathExpression", "Float"] or 
                                      "strength" in placeholder or "seed" in placeholder or 
                                      "random" in placeholder or "width" in placeholder or 
                                      "height" in placeholder or "fps" in placeholder or
                                      "length" in placeholder or "steps" in placeholder or
                                      "shift" in placeholder or "denoise" in placeholder or
                                      "cfg" in placeholder)

                    if should_convert:
                        try:
                            if "strength" in placeholder or cls == "Float":
                                new_val = float(repl_val)
                            else:
                                new_val = int(repl_val)
                        except (ValueError, TypeError):
                            new_val = str(repl_val)
                    else:
                        if isinstance(new_val, str):
                            new_val = new_val.replace(p_key, str(repl_val))
            
            inputs[k] = new_val
    return workflow


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
        template_path = _resolve_wan_template_path("wan_image")
        if template_path is None:
            raise ValueError(f"Failed to resolve wan_image template in projects/wan/workflow/ (root, image/, video/)")
    else:
        template_path = os.path.join(LTX_WORKFLOW_BASE, f"{template}.json")

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
    """
    from parameter_extraction import (
        extract_params_from_new_tab_task,
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
    """
    from parameter_extraction import extract_params_for_wan_video

    params = extract_params_for_wan_video(task_path, resolution=resolution, seconds=seconds)

    template_map = {
        "prep": "ltx_preparation",
        "encode": "ltx_preparation",
        "sampling": "ltx_1st_sampling",
        "decode": "ltx_decode",
    }
    template = template_map.get(step, "ltx_preparation")

    return generate_workflow_from_standard_params(
        template=template,
        params=params.to_dict(),
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
    latent_in: str = "",
    output: str = "",
    upscale_model_name: str = "",
    load_image: str = "",
    **kwargs
) -> Dict:
    """
    Generate a ComfyUI API workflow JSON using WAN-style dynamic placeholders.
    Updated to align with Wan video generation parameter injection.
    """
    if acts is None: acts = []
    
    # Resolve template path
    if type == "image":
        template_path = _resolve_wan_template_path("wan_image")
    elif template_dir:
        template_path = os.path.join(template_dir, f"{template}.json")
    else:
        template_path = _resolve_ltx_template_path(template)
    
    if not os.path.exists(template_path):
        # Try searching in project's own workflow folder as fallback
        fallback = os.path.join(SCRIPT_DIR, "workflow", f"{template}.json")
        if os.path.exists(fallback):
            template_path = fallback
        else:
            raise FileNotFoundError(f"Template not found: {template_path}")

    with open(template_path, 'r', encoding='utf-8') as f:
        workflow = json.load(f)
    
    workflow = deepcopy(workflow)
    
    # Prepare parameters based on StandardWorkflowParams defaults
    params_obj = StandardWorkflowParams(
        job_id=job_id or work_id,
        work_id=work_id,
        width=width,
        height=height,
        video_width=width,
        video_height=height,
        length=length,
        video_length=length,
        fps=fps,
        prompt=prompt,
        video_pos_prompt=video_pos_prompt or video_prompt or prompt,
        video_neg_prompt=negative_prompt or "ugly, deformed, bad quality",
        negative_prompt=negative_prompt or "ugly, deformed, bad quality",
        load_image=load_image or f"{work_id}.png",
        image=load_image or f"{work_id}.png",
        save_video=output or work_id,
        save_image=work_id,
        save_pos_conditioning=f"pos_{work_id}.pt",
        save_neg_conditioning=f"neg_{work_id}.pt",
        load_pos_conditioning=f"pos_{work_id}.pt",
        load_neg_conditioning=f"neg_{work_id}.pt",
        save_latent=work_id, # Base work_id
        load_latent=latent_in or work_id,
    )
    
    # Specific LTX step overrides for save_latent/load_latent/conditioning/video
    # All placeholders (**save_latent**, **load_latent**, **save_pos_conditioning**, etc.)
    # are resolved by apply_wan_placeholders which scans node inputs for "**..." strings.
    if template == "ltx_preparation":
        params_obj.save_latent = f"{work_id}_prep"
        params_obj.save_pos_conditioning = "positive_conditioning_preparation_1"
        params_obj.save_neg_conditioning = "negative_conditioning_preparation"
    elif template == "ltx_1st_sampling":
        params_obj.save_latent = f"{work_id}_s1"
        params_obj.load_latent = f"{work_id}_prep_00001_.latent"
        params_obj.load_pos_conditioning = "positive_conditioning_preparation_1.pt"
        params_obj.load_neg_conditioning = "negative_conditioning_preparation.pt"
    elif template == "ltx_upscale":
        params_obj.save_latent = f"{work_id}_up"
        params_obj.load_latent = f"{work_id}_s1_00001_.latent"
        params_obj.load_pos_conditioning = "positive_conditioning_preparation_1.pt"
        params_obj.load_neg_conditioning = "negative_conditioning_preparation.pt"
        params_obj.save_pos_conditioning = "positive_conditioning_cropped_1"
        params_obj.save_neg_conditioning = "negative_conditioning_cropped_1"
        # Set default upscale model name if not provided
        if not upscale_model_name:
            params_obj.upscale_model_name = "ltx-2.3-spatial-upscaler-x2-1.1.safetensors"
        else:
            params_obj.upscale_model_name = upscale_model_name
    elif template == "ltx_2nd_sampling":
        params_obj.save_latent = f"{work_id}_s2"
        params_obj.load_latent = f"{work_id}_up_00001_.latent"
        params_obj.load_pos_conditioning = "positive_conditioning_cropped_1.pt"
        params_obj.load_neg_conditioning = "negative_conditioning_cropped_1.pt"
    elif template == "ltx_decode":
        params_obj.load_latent = latent_in or f"{work_id}_s2_00001_.latent"

    params = params_obj.to_dict()
    params.update(kwargs) # Allow manual overrides

    # Resolve LoRAs
    csv_name = "image_lora_lookup.csv" if type == "image" else "lora_lookup.csv"
    lora_resolved = _resolve_lora_params(
        acts, csv_name, workflow_name=template,
    )
    params.update(lora_resolved)

    return apply_wan_placeholders(workflow, params)


def load_lora_lookup(csv_path: str = None, filter_type: str = None, workflow_name: str = None) -> Dict[str, List[Dict]]:
    """
    Load LoRA lookup table from CSV.
    """
    if csv_path is None:
        csv_path = os.path.join(os.path.dirname(SCRIPT_DIR), "lookup", "lora_lookup.csv")
    
    lookup = {}
    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                row_type = row.get('type', '').strip().lower()
                if filter_type and row_type and row_type != filter_type.lower():
                    continue
                
                row_workflow = row.get('workflow name', '').strip()
                if workflow_name and row_workflow and row_workflow != workflow_name:
                    continue
                
                lora_tag = row.get('lora_tag', '').strip().lower()
                tag1 = row.get('tag1', '').strip().lower()
                tag2 = row.get('tag2', '').strip().lower()
                
                if lora_tag:
                    key = lora_tag
                elif tag1:
                    key = tag1
                    if tag2:
                        key = f"{tag1}+{tag2}"
                else:
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
                    lookup[key] = loras
                    if tag1 and tag1 not in lookup:
                        lookup[tag1] = loras
        return lookup
    except Exception as e:
        print(f"Error loading lora_lookup.csv: {e}")
        return {}


def generate_cleanup_workflow(job_id: str, step_number: int) -> Dict:
    """
    Generate a cleanup workflow with the job_id-step_number as finish signal.
    """
    # Try LTX-specific cleanup first
    cleanup_path = os.path.join(LTX_WORKFLOW_BASE, "clean_up.json")
    if not os.path.exists(cleanup_path):
        cleanup_path = _resolve_wan_template_path("clean_up")
    
    if cleanup_path is None or not os.path.exists(cleanup_path):
        raise FileNotFoundError("clean_up.json template not found")
        
    with open(cleanup_path, 'r', encoding='utf-8') as f:
        workflow = json.load(f)
    
    # Use placeholder replacement instead of title matching if possible
    params = {
        "finish_indicator": f"{job_id}-{step_number}",
        "job_id": f"{job_id}-{step_number}"
    }
    return apply_wan_placeholders(workflow, params)


def save_workflow(workflow: Dict, output_path: str):
    """Save workflow to JSON file."""
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(workflow, f, indent=2)


if __name__ == "__main__":
    # Test
    workflow = generate_api_workflow(
        project="ltx",
        type="video",
        template="ltx_1st_sampling",
        work_id="test001"
    )
    print("LTX 1st Sampling Placeholder Test:")
    print(json.dumps(workflow["1"]["inputs"], indent=2))
