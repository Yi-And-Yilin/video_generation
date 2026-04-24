"""
Workflow Generator for ComfyUI API

Generates dynamic workflow JSON files based on template, actions, and parameters.
"""

import json
import os
import csv
from typing import Dict, List, Any, Optional
from copy import deepcopy

# Get the directory where this script is located
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


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
    **kwargs
) -> Dict:
    """
    Generate a ComfyUI API workflow JSON using WAN-style dynamic placeholders.
    """
    if acts is None: acts = []
    
    if type == "image":
        template_dir = os.path.join(os.path.dirname(SCRIPT_DIR), "wan", "workflow")
        template = "wan_image"
    elif template_dir is None:
        template_dir = os.path.join(SCRIPT_DIR, "workflow", type)
    
    template_path = os.path.join(template_dir, f"{template}.json")
    try:
        with open(template_path, 'r', encoding='utf-8') as f: workflow = json.load(f)
    except Exception as e: raise ValueError(f"Failed to load template '{template_path}': {e}")
    
    workflow = deepcopy(workflow)
    import random
    params = {
        'prompt': prompt,
        'image_pos_prompt': prompt,
        'video_pos_prompt': prompt,
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
    cleanup_path = os.path.join(SCRIPT_DIR, "workflow", "clean_up.json")
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