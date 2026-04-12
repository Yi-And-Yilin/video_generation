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


def find_all_dynamic_nodes(workflow: Dict) -> Dict[str, List[tuple]]:
    """
    Find all nodes with _meta.title starting with '**'.
    Returns a dict mapping title (without **) to list of (node_id, node_data) tuples.
    """
    dynamic_nodes = {}
    for node_id, node_data in workflow.items():
        meta = node_data.get('_meta', {})
        title = meta.get('title', '')
        if title.startswith('**'):
            param_name = title[2:]  # Remove '**' prefix
            if param_name not in dynamic_nodes:
                dynamic_nodes[param_name] = []
            dynamic_nodes[param_name].append((node_id, node_data))
    return dynamic_nodes


def find_anchor_lora_node(workflow: Dict) -> Optional[tuple]:
    """
    Find the anchor LoRA node (title starting with '**lora' or '**LoRA').
    Returns (node_id, node_data) or None.
    """
    for node_id, node_data in workflow.items():
        class_type = node_data.get('class_type', '')
        meta = node_data.get('_meta', {})
        title = meta.get('title', '').lower()
        
        if class_type in ['LoraLoader', 'LoraLoaderModelOnly']:
            if title.startswith('**lora'):
                return (node_id, node_data)
    return None


def find_downstream_nodes(workflow: Dict, source_node_id: str) -> List[tuple]:
    """
    Find all nodes that take input from the given source node.
    Returns list of (node_id, input_key, output_index) tuples.
    """
    downstream = []
    for node_id, node_data in workflow.items():
        inputs = node_data.get('inputs', {})
        for input_key, input_value in inputs.items():
            if isinstance(input_value, list) and len(input_value) >= 2:
                if input_value[0] == source_node_id:
                    downstream.append((node_id, input_key, input_value[1]))
    return downstream


def create_lora_node(node_id: str, lora_name: str, strength: float, 
                     model_input: list, clip_input: list = None,
                     model_only: bool = True) -> Dict:
    """
    Create a LoRA node.
    """
    if model_only:
        return {
            "inputs": {
                "lora_name": lora_name,
                "strength_model": strength,
                "model": model_input
            },
            "class_type": "LoraLoaderModelOnly",
            "_meta": {
                "title": f"LoRA - {os.path.basename(lora_name)}"
            }
        }
    else:
        return {
            "inputs": {
                "lora_name": lora_name,
                "strength_model": strength,
                "strength_clip": strength,
                "model": model_input,
                "clip": clip_input
            },
            "class_type": "LoraLoader",
            "_meta": {
                "title": f"LoRA - {os.path.basename(lora_name)}"
            }
        }


def update_node_value(node_data: Dict, value: Any) -> None:
    """
    Update a node's input value based on its class_type.
    """
    class_type = node_data.get('class_type', '')
    inputs = node_data.get('inputs', {})
    
    if class_type in ['StringConstant', 'CR Text', 'JjkText']:
        # Text nodes use 'string' or 'text'
        if 'string' in inputs:
            node_data['inputs']['string'] = value
        elif 'text' in inputs:
            node_data['inputs']['text'] = value
    elif class_type == 'String':
        node_data['inputs']['String'] = value
    elif class_type == 'Int':
        node_data['inputs']['Number'] = str(value)
    elif class_type == 'Float':
        node_data['inputs']['Number'] = str(value)
    elif class_type == 'PrimitiveInt':
        node_data['inputs']['value'] = value
    elif class_type == 'PrimitiveBoolean':
        node_data['inputs']['value'] = value
    elif class_type == 'LoadImage':
        node_data['inputs']['image'] = value
    elif class_type == 'SaveLatent':
        node_data['inputs']['filename_prefix'] = value
    elif class_type == 'LoadLatent':
        node_data['inputs']['latent'] = value
    elif class_type == 'StarConditioningSaver':
        node_data['inputs']['filename'] = value
    elif class_type == 'StarConditioningLoader':
        node_data['inputs']['conditioning_file'] = value
    elif class_type == 'Save Text File':
        node_data['inputs']['filename_prefix'] = value
    elif class_type == 'VHS_VideoCombine':
        node_data['inputs']['filename_prefix'] = value
    else:
        # Generic: try to find a suitable input key
        for key in ['value', 'string', 'text', 'filename', 'filename_prefix']:
            if key in inputs:
                node_data['inputs'][key] = value
                break


def generate_api_workflow(
    project: str,
    type: str,
    template: str,
    acts: List[str] = None,
    width: int = 1280,
    height: int = 720,
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
    Generate a ComfyUI API workflow JSON.
    
    Args:
        project: Project name (e.g., "ltx")
        type: Workflow type (e.g., "image", "video")
        template: Template filename without extension (e.g., "pornmaster_proSDXLV8")
        acts: List of action tags for LoRA selection (e.g., ["fingering", "kiss"])
        width: Image/video width
        height: Image/video height
        length: Video length (frames)
        prompt: Positive prompt text
        negative_prompt: Negative prompt text
        work_id: Work ID for file naming
        job_id: Job ID for cleanup workflow finish signal
        step_number: Step number for cleanup workflow
        fps: Frames per second for video
        workflow_name: Workflow name to filter LoRA lookup (for image_lora_lookup.csv)
        lora_lookup_path: Path to lora_lookup.csv (optional)
        template_dir: Path to template directory (optional)
        **kwargs: Additional dynamic parameters (e.g., image="abc.png")
    
    Returns:
        Dict: The generated workflow JSON
    """
    if acts is None:
        acts = []
    
    # Set default paths
    if template_dir is None:
        template_dir = os.path.join(SCRIPT_DIR, "workflow", type)
    
    # Load template
    template_path = os.path.join(template_dir, f"{template}.json")
    try:
        with open(template_path, 'r', encoding='utf-8') as f:
            workflow = json.load(f)
    except Exception as e:
        raise ValueError(f"Failed to load template '{template_path}': {e}")
    
    # Make a deep copy to avoid modifying original
    workflow = deepcopy(workflow)
    
    # === Step 1: Build parameter mapping ===
    params = {
        'prompt': prompt,
        'negative_prompt': negative_prompt,
        'width': width,
        'height': height,
        'length': length,
        'work_id': work_id,
        'fps': fps,
    }
    
    # Add kwargs to params
    params.update(kwargs)
    
    # Special handling for common patterns
    if work_id:
        params['image'] = f"{work_id}.png"
        # For text encoding workflow (saving)
        params['positive_conditioning'] = f"positive_conditioning_{work_id}"
        params['negative_conditioning'] = f"negative_conditioning_{work_id}"
        # For sampling workflow (loading)
        params['positive_conditioning_load'] = f"positive_conditioning_{work_id}.pt"
        params['negative_conditioning_load'] = f"negative_conditioning_{work_id}.pt"
        params['vidoe_latent'] = f"latents/video_{work_id}"  # Note: typo in workflow
        params['video_latent'] = f"video_{work_id}_00001_.latent"  # For loading
        params['audio_latent'] = f"audio_{work_id}_00001_.latent"
    
    if job_id and step_number:
        params['finish_signal'] = f"{job_id}-{step_number}"
    
    # === Step 2: Find and update all dynamic nodes ===
    dynamic_nodes = find_all_dynamic_nodes(workflow)
    
    for param_name, nodes in dynamic_nodes.items():
        if param_name in params:
            for node_id, node_data in nodes:
                update_node_value(node_data, params[param_name])
    
    # === Step 3: Handle LoRA insertion ===
    
    # Load LoRA lookup, filtered by type and/or workflow_name
    lora_lookup = load_lora_lookup(lora_lookup_path, filter_type=type, workflow_name=workflow_name)
    
    # Collect LoRAs for all actions
    loras_to_insert = []
    for act in acts:
        act_lower = act.lower().strip()
        if act_lower in lora_lookup:
            loras_to_insert.extend(lora_lookup[act_lower])
    
    # Find anchor LoRA node (always, even if no LoRAs to insert)
    anchor_result = find_anchor_lora_node(workflow)
    
    if anchor_result:
        anchor_id, anchor_data = anchor_result
        
        # Find downstream nodes that use the anchor's output
        downstream_nodes = find_downstream_nodes(workflow, anchor_id)
        
        # Get anchor's input model and clip
        anchor_inputs = anchor_data.get('inputs', {})
        model_input = anchor_inputs.get('model')
        clip_input = anchor_inputs.get('clip')
        
        is_model_only = anchor_data.get('class_type') == 'LoraLoaderModelOnly'
    
        if loras_to_insert:
            # Determine starting ID for new nodes (start from 200)
            existing_ids = []
            for nid in workflow.keys():
                try:
                    # Handle both simple IDs and compound IDs like "267:219"
                    base_id = nid.split(':')[0] if ':' in nid else nid
                    existing_ids.append(int(base_id))
                except ValueError:
                    pass
            next_id = max(200, max(existing_ids) + 1) if existing_ids else 200
            
            # Chain: anchor's input -> new LoRA 1 -> new LoRA 2 -> ... -> last new LoRA
            current_model = model_input
            current_clip = clip_input
            last_new_id = None
            
            for lora_info in loras_to_insert:
                new_id = str(next_id)
                next_id += 1
                
                # Create new LoRA node
                if is_model_only:
                    new_node = create_lora_node(
                        new_id,
                        lora_info['name'],
                        lora_info['strength'],
                        current_model,
                        model_only=True
                    )
                    current_model = [new_id, 0]
                else:
                    new_node = create_lora_node(
                        new_id,
                        lora_info['name'],
                        lora_info['strength'],
                        current_model,
                        current_clip,
                        model_only=False
                    )
                    current_model = [new_id, 0]
                    current_clip = [new_id, 1]
                
                workflow[new_id] = new_node
                last_new_id = new_id
            
            # Update downstream nodes to use the last new LoRA's output
            if last_new_id and downstream_nodes:
                for node_id, input_key, output_idx in downstream_nodes:
                    workflow[node_id]['inputs'][input_key] = [last_new_id, output_idx]
        else:
            # No LoRAs to insert - bypass anchor node by connecting its input to downstream
            if downstream_nodes:
                for node_id, input_key, output_idx in downstream_nodes:
                    if output_idx == 0:
                        workflow[node_id]['inputs'][input_key] = model_input
                    elif output_idx == 1 and clip_input:
                        workflow[node_id]['inputs'][input_key] = clip_input
        
        # Remove the anchor LoRA node
        if anchor_id in workflow:
            del workflow[anchor_id]
    
    return workflow


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