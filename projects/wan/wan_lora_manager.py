"""
Unified LoRA Manager for Video Generation System

This module provides a SINGLE, CONSISTENT protocol for LoRA lookup and workflow
placeholder replacement across ALL generation types:
  - Image generation (wan_image, z-image, pornmaster_proSDXLV8)
  - WAN video generation (wan_2.1_step*, wan_2.2_step*)
  - LTX video generation (ltx_1st_sampling, ltx_2nd_sampling, ltx_upscale, etc.)

## Unified LoRA Protocol

All workflow templates now use the same placeholder pattern:

  **lora1_name**, **lora1_strength**
  **lora2_name**, **lora2_strength**
  **lora3_name**, **lora3_strength**
  **lora4_name**, **lora4_strength**
  **lora5_name**, **lora5_strength**

Plus one "Dynamic LoRA chain start" placeholder node for chaining:
  **dynamic_lora_chain_start** (replaced with lora1_name)
  **dynamic_lora_chain_strength** (replaced with lora1_strength)

## Usage

```python
from wan_lora_manager import (
    load_lora_lookup,
    resolve_lora_params,
    apply_lora_placeholders,
    apply_dynamic_lora_chaining,
)

# 1. Resolve LoRA params from acts + CSV lookup
acts = ["lying_on_tummy_doggy"]
params = resolve_lora_params(
    acts=acts,
    csv_name="lora_lookup.csv",        # or "image_lora_lookup.csv" for image gen
    workflow_name="ltx_1st_sampling",   # or None for no workflow filter
    filter_type="video",                # or "image"
)
# Returns: {lora1_name, lora1_strength, ..., lora5_name, lora5_strength,
#           dynamic_lora_count}

# 2. Load workflow template
with open("workflows/video/ltx_1st_sampling.json") as f:
    workflow = json.load(f)

# 3. Apply placeholders (including LoRA names/strengths)
workflow = apply_lora_placeholders(workflow, params)

# 4. Apply dynamic LoRA chaining (generate multiple LoRA nodes if count > 1)
workflow = apply_dynamic_lora_chaining(workflow, params["dynamic_lora_count"])
```

## Key Design Decisions

1. **Placeholder naming**: All LoRA placeholders use `**loraX_name**` / `**loraX_strength**`
   format (matching WAN image convention).

2. **Dynamic LoRA chain**: One placeholder node per workflow that gets expanded
   into N actual LoraLoaderModelOnly nodes when count > 1.

3. **CSV lookup**: Single function `load_lora_lookup()` filters by `type` and
   `workflow name` columns.

4. **Default fallback**: If no LoRA found, defaults to `xl\\add-detail.safetensors`
   with strength 0.0.

5. **Protection**: Nodes WITHOUT `**...**` placeholders are never modified.
   This protects hardcoded LoRA paths (e.g., Distill LoRA).
"""

import os
import csv
import re
from typing import Dict, List, Any, Optional, Tuple
from copy import deepcopy


# ============================================================================
# Constants
# ============================================================================

# Default LoRA used when no match is found in CSV
DEFAULT_LORA_NAME = "xl\\add-detail.safetensors"
DEFAULT_LORA_STRENGTH = 0.0

# Maximum number of LoRA slots
MAX_LORA_SLOTS = 5

# Dynamic LoRA chain node placeholder prefix
DYNAMIC_LORA_CHAIN_PREFIX = "**dynamic_lora_chain_start**"
DYNAMIC_LORA_CHAIN_STRENGTH_PREFIX = "**dynamic_lora_chain_strength**"


# ============================================================================
# CSV Lookup
# ============================================================================

def load_lora_lookup(
    csv_path: str,
    filter_type: Optional[str] = None,
    workflow_name: Optional[str] = None,
) -> Dict[str, List[Dict]]:
    """
    Load LoRA lookup table from CSV.

    The CSV format:
        tag1, tag2, type, workflow name, lora1_name, lora1_strength, ..., lora5_name, lora5_strength

    Filtering:
        - filter_type: "image" or "video" — only include rows matching this type.
          If None, include all rows regardless of type.
        - workflow_name: e.g., "ltx_1st_sampling", "z-image", "pornmaster_proSDXLV8".
          For LTX templates starting with "ltx_", matches any "ltx_*" or "ltx_standard" row.
          For exact matches, the workflow name must match exactly.

    Returns
    -------
    Dict[str, List[Dict]]
        Mapping from tag key (lowercase) to list of LoRA dicts:
        [{"name": "...", "strength": 0.9}, {"name": "...", "strength": 0.3}, ...]
    """
    lookup = {}

    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                row_type = row.get('type', '').strip().lower()
                if filter_type and row_type and row_type != filter_type.lower():
                    continue

                row_workflow = row.get('workflow name', '').strip()
                if workflow_name and row_workflow:
                    # LTX matching: all ltx_* templates match ltx_standard and vice versa
                    if workflow_name.startswith("ltx_") or row_workflow.startswith("ltx_"):
                        if not (row_workflow.startswith("ltx") or row_workflow == "ltx_standard"):
                            continue
                    elif row_workflow != workflow_name:
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
                for i in range(1, MAX_LORA_SLOTS + 1):
                    name = row.get(f'lora{i}_name', '').strip()
                    strength = row.get(f'lora{i}_strength', '').strip()
                    if name:
                        try:
                            strength_val = float(strength) if strength else 1.0
                        except ValueError:
                            strength_val = 1.0
                        loras.append({
                            'name': name,
                            'strength': strength_val,
                        })

                if loras:
                    lookup[key] = loras
                    # Also add tag1 alone as a key
                    if tag1 and tag1 not in lookup:
                        lookup[tag1] = loras

    except Exception as e:
        print(f"Error loading lora_lookup.csv from {csv_path}: {e}")

    return lookup


def resolve_lora_params(
    acts: List[str],
    csv_name: str,
    workflow_name: str = None,
    extra_lora_names: List[str] = None,
    extra_lora_strengths: List[float] = None,
    filter_type: str = None,
    csv_dir: str = None,
) -> Dict[str, Any]:
    """
    Resolve LoRA names and strengths from acts + CSV lookup.

    This is the canonical function for resolving LoRA parameters. It:
    1. Optionally prepends extra LoRA names/strengths
    2. Loads the CSV lookup table via load_lora_lookup()
    3. Iterates through each act, looking up matching tags
    4. Returns a dict with lora1..5_name, lora1..5_strength, and dynamic_lora_count

    Parameters
    ----------
    acts : List[str]
        List of action tags (e.g., sex acts) to look up in the CSV.
    csv_name : str
        Filename of the LoRA lookup CSV (e.g., "lora_lookup.csv" or
        "image_lora_lookup.csv").
    workflow_name : str, optional
        Workflow name filter for the CSV (e.g., "z-image", "pornmaster_proSDXLV8",
        "ltx_1st_sampling").
    extra_lora_names : List[str], optional
        Additional LoRA names to prepend before CSV lookups.
    extra_lora_strengths : List[float], optional
        Additional LoRA strengths (aligned with extra_lora_names).
    filter_type : str, optional
        Type filter for the CSV ("image" or "video"). Defaults to "image" if
        csv_name is "image_lora_lookup.csv", "video" otherwise.
    csv_dir : str, optional
        Directory containing the CSV file. If None, uses the lookup/ directory
        relative to this module's location.

    Returns
    -------
    Dict[str, Any]
        Dict with keys:
          - lora1_name, lora1_strength, ..., lora5_name, lora5_strength
          - dynamic_lora_count (number of LoRAs found)
    """
    if extra_lora_names is None:
        extra_lora_names = []
    if extra_lora_strengths is None:
        extra_lora_strengths = []
    if filter_type is None:
        filter_type = "image" if csv_name == "image_lora_lookup.csv" else "video"

    # Prepend extra LoRAs
    loras = list(zip(extra_lora_names, extra_lora_strengths))

    # Resolve CSV path
    if csv_dir is None:
        module_dir = os.path.dirname(os.path.abspath(__file__))
        # Go up from projects/wan/ to project root
        csv_dir = os.path.join(module_dir, "..", "..", "..", "lookup")
        csv_dir = os.path.normpath(csv_dir)

    csv_path = os.path.join(csv_dir, csv_name)
    if csv_path and os.path.exists(csv_path):
        lookup = load_lora_lookup(
            csv_path, filter_type=filter_type, workflow_name=workflow_name
        )
        print(f"DEBUG: resolve_lora_params: lookup has {len(lookup)} entries, acts={acts}, workflow_name={workflow_name}, filter_type={filter_type}")
        for act in acts:
            act_lower = act.lower().strip()
            if act_lower in lookup:
                print(f"DEBUG: Found '{act_lower}' in lookup, adding {len(lookup[act_lower])} loras")
                loras.extend(lookup[act_lower])
            else:
                print(f"DEBUG: '{act_lower}' NOT in lookup")

    result = {}
    dynamic_count = len(loras)

    for i in range(1, MAX_LORA_SLOTS + 1):
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
            result[f'lora{i}_name'] = DEFAULT_LORA_NAME
            result[f'lora{i}_strength'] = DEFAULT_LORA_STRENGTH

    result['dynamic_lora_count'] = dynamic_count
    return result


# ============================================================================
# Placeholder Replacement
# ============================================================================

def apply_lora_placeholders(workflow: Dict, params: Dict) -> Dict:
    """
    Apply LoRA placeholder replacement to a workflow.

    This function replaces **placeholder** tokens in workflow node inputs with
    values from params. It handles:
    - **lora1_name** through **lora5_name**
    - **lora1_strength** through **lora5_strength**
    - **dynamic_lora_chain_start** (replaced with lora1_name)
    - **dynamic_lora_chain_strength** (replaced with lora1_strength)
    - None values (from JSON null) that correspond to placeholder wrappers

    IMPORTANT: Nodes WITHOUT **...** placeholders are NEVER modified.
    This protects hardcoded LoRA paths (e.g., Distill LoRA) from being replaced.

    Parameters
    ----------
    workflow : Dict
        The workflow JSON to modify (modified in-place, also returned).
    params : Dict
        Mapping of placeholder names (without ** prefix) to their replacement values.
        Should include at least lora1_name, lora1_strength, etc.

    Returns
    -------
    Dict
        The modified workflow JSON.
    """
    for node_id, node in workflow.items():
        if not isinstance(node, dict):
            continue
        inputs = node.get("inputs", {})
        cls = node.get("class_type", "")

        # For nodes with **loraX** patterns, first determine which lora level is used
        # by scanning all **placeholder** patterns in this node's inputs.
        # e.g., "**lora2_name**" → level is 2 → use lora2_strength for None fields
        lora_level = None
        for k2, v2 in inputs.items():
            if isinstance(v2, str) and "**lora" in v2:
                match = re.search(r"\*\*lora(\d+)_", v2)
                if match:
                    lora_level = int(match.group(1))
                    break

        for k, v in inputs.items():
            # Handle non-string, non-None values
            if not isinstance(v, str) and v is not None:
                # Only handle strength_model in LoRA nodes
                if not (lora_level and k == "strength_model"):
                    continue

                # For None values, look up the matching placeholder
                matched = False
                for placeholder, repl_val in params.items():
                    p_key = f"**{placeholder}**"
                    if p_key in inputs:
                        try:
                            if "strength" in k.lower() or "strength" in placeholder:
                                new_val = float(repl_val)
                            elif "seed" in k.lower() or "width" in k.lower() or "height" in k.lower():
                                new_val = int(repl_val)
                            else:
                                new_val = str(repl_val)
                        except (ValueError, TypeError):
                            new_val = str(repl_val)
                        inputs[k] = new_val
                        matched = True
                        break

                if not matched:
                    # Infer level from node context
                    if lora_level and "strength" in k.lower():
                        key = f"lora{lora_level}_strength"
                        if key in params:
                            try:
                                inputs[k] = float(params[key])
                            except (ValueError, TypeError):
                                inputs[k] = 0.0
                        else:
                            inputs[k] = 0.0
                    elif lora_level:
                        key = f"lora{lora_level}_{k}" if not k.startswith("lora") else f"lora{lora_level}_{k.replace('lora', '')}"
                        if key in params:
                            inputs[k] = params[key]
                        elif f"lora{lora_level}_name" == k or k.endswith("_name"):
                            inputs[k] = params.get(f"lora{lora_level}_name", "")
                    inputs[k] = inputs.get(k, None)

            else:
                new_val = v
                lora_strength_overridden = False

                # Handle dynamic LoRA chain placeholders
                if DYNAMIC_LORA_CHAIN_PREFIX in str(new_val):
                    lora1_name = params.get("lora1_name", DEFAULT_LORA_NAME)
                    new_val = new_val.replace(DYNAMIC_LORA_CHAIN_PREFIX, str(lora1_name))
                if DYNAMIC_LORA_CHAIN_STRENGTH_PREFIX in str(new_val):
                    lora1_strength = params.get("lora1_strength", DEFAULT_LORA_STRENGTH)
                    try:
                        inputs[k] = float(lora1_strength)
                    except (ValueError, TypeError):
                        inputs[k] = str(lora1_strength)
                    continue  # Done with this input

                # Replace all **placeholder** tokens
                for placeholder, repl_val in params.items():
                    p_key = f"**{placeholder}**"
                    if "**" in str(new_val) and p_key in str(new_val):
                        should_convert = (cls in ["JWInteger", "Int", "PrimitiveInt",
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

                # Handle strength_model in LoRA nodes: replace hardcoded 0 with correct strength
                if lora_level and k == "strength_model" and isinstance(v, (int, float)):
                    strength_key = f"lora{lora_level}_strength"
                    if strength_key in params:
                        try:
                            inputs[k] = float(params[strength_key])
                            lora_strength_overridden = True
                        except (ValueError, TypeError):
                            inputs[k] = 0.0
                            lora_strength_overridden = True

                if not lora_strength_overridden:
                    inputs[k] = new_val

    return workflow


# ============================================================================
# Dynamic LoRA Chaining
# ============================================================================

def apply_dynamic_lora_chaining(
    workflow: Dict,
    dynamic_lora_count: int,
    lora_params: Dict = None,
) -> Dict:
    """
    Apply dynamic LoRA chaining to a workflow based on CSV lookup results.

    If dynamic_lora_count == 0:
        Removes the "Dynamic LoRA" placeholder node and bypasses upstream → downstream.

    If dynamic_lora_count >= 1:
        Replaces the single "Dynamic LoRA (chain start)" placeholder node with
        N actual LoraLoaderModelOnly nodes, each with the correct lora_name and
        lora_strength, chained together. Downstream nodes now reference the last
        LoRA node.

    Parameters
    ----------
    workflow : Dict
        The workflow JSON with placeholders already applied.
    dynamic_lora_count : int
        Number of dynamic LoRAs from CSV lookup.
    lora_params : Dict, optional
        LoRA parameters dict (lora1_name, lora1_strength, etc.).

    Returns
    -------
    Dict
        The workflow with dynamic LoRA nodes properly generated or removed.
    """
    if dynamic_lora_count < 1:
        return _remove_dynamic_lora_nodes(workflow)

    return _generate_dynamic_lora_nodes(workflow, dynamic_lora_count, lora_params or {})


def _remove_dynamic_lora_nodes(workflow: Dict) -> Dict:
    """
    Remove Dynamic LoRA placeholder nodes and bypass upstream → downstream.

    When no LoRAs are found in CSV lookup, the Dynamic LoRA placeholder node
    is removed and downstream references are updated to point to the upstream
    node.
    """
    # Find the Dynamic LoRA node
    dynamic_node_id = None
    for node_id, node in workflow.items():
        if isinstance(node, dict):
            title = node.get("_meta", {}).get("title", "")
            if title.startswith("Dynamic LoRA"):
                dynamic_node_id = node_id
                break

    if dynamic_node_id is None:
        return workflow

    # Get the model input reference from the Dynamic LoRA node
    dynamic_inputs = workflow[dynamic_node_id].get("inputs", {})
    upstream_ref = dynamic_inputs.get("model", [])
    if isinstance(upstream_ref, list):
        upstream_id = upstream_ref[0] if upstream_ref[0] != "0" else None
    else:
        upstream_id = None

    # Find downstream nodes that reference the dynamic node
    nodes_to_update = []
    for node_id, node in workflow.items():
        if node_id != dynamic_node_id and isinstance(node, dict):
            node_inputs = node.get("inputs", {})
            for k, v in node_inputs.items():
                if isinstance(v, list) and len(v) > 0 and str(v[0]) == dynamic_node_id:
                    nodes_to_update.append((node_id, k))

    # Update downstream references to point to the upstream node
    if upstream_id and nodes_to_update:
        for node_id, key in nodes_to_update:
            workflow[node_id]["inputs"][key] = [upstream_id, 0]

        # Remove the Dynamic LoRA node
        del workflow[dynamic_node_id]

    return workflow


def _generate_dynamic_lora_nodes(
    workflow: Dict,
    count: int,
    lora_params: Dict,
) -> Dict:
    """
    Generate N LoRA loader nodes chained together and replace the Dynamic LoRA placeholder.

    For count=2:
      Node A (chain start, replaces placeholder):
        model → [upstream, 0], lora → lora1, strength → lora1_strength
      Node B (new):
        model → [Node A, 0], lora → lora2, strength → lora2_strength
      Downstream nodes now reference Node B.

    Parameters
    ----------
    workflow : Dict
        The workflow JSON with placeholders already applied.
    count : int
        Number of LoRA nodes to generate (≥ 1).
    lora_params : Dict
        LoRA parameters dict (lora1_name, lora1_strength, etc.).

    Returns
    -------
    Dict
        The workflow with N LoraLoaderModelOnly nodes properly chained.
    """
    # Find the Dynamic LoRA placeholder node
    dyn_node_id = None
    dyn_node = None
    for nid, node in list(workflow.items()):
        if isinstance(node, dict) and node.get("_meta", {}).get("title", "").startswith("Dynamic LoRA"):
            dyn_node_id = nid
            dyn_node = node
            break

    if dyn_node_id is None or dyn_node is None:
        return workflow

    # Get the upstream node
    dyn_inputs = dyn_node.get("inputs", {})
    upstream_ref = dyn_inputs.get("model", [])
    if isinstance(upstream_ref, list):
        upstream_id = upstream_ref[0] if len(upstream_ref) > 0 else None
    else:
        upstream_id = None

    # Find downstream nodes that reference the dynamic node
    downstream_refs = []
    for nid, node in workflow.items():
        if nid != dyn_node_id and isinstance(node, dict):
            for k, v in node.get("inputs", {}).items():
                if isinstance(v, list) and len(v) > 0 and str(v[0]) == dyn_node_id:
                    downstream_refs.append((nid, k))

    # Build the LoRA chain
    node_ids = []
    prev_id = upstream_id

    for i in range(count):
        lora_idx = i + 1
        lora_name_key = f'lora{lora_idx}_name'
        lora_strength_key = f'lora{lora_idx}_strength'

        lora_name = lora_params.get(lora_name_key, DEFAULT_LORA_NAME)
        lora_strength = lora_params.get(lora_strength_key, DEFAULT_LORA_STRENGTH)

        model_ref = [str(prev_id), 0] if prev_id else ["9", 0]

        new_inputs = dict(dyn_node["inputs"])
        new_inputs["lora_name"] = lora_name
        new_inputs["strength_model"] = float(lora_strength)
        new_inputs["model"] = model_ref

        new_node = {
            "inputs": new_inputs,
            "class_type": "LoraLoaderModelOnly",
            "_meta": {"title": f"Dynamic LoRA {lora_idx}"},
        }

        if i == 0:
            # First node replaces the placeholder node in-place
            workflow[dyn_node_id] = new_node
            curr_id = dyn_node_id
        else:
            # New node — find a free ID
            all_ids = set(workflow.keys())
            next_id = int(dyn_node_id) + 1
            while str(next_id) in all_ids:
                next_id += 1
            workflow[str(next_id)] = new_node
            curr_id = str(next_id)

        node_ids.append(curr_id)
        prev_id = curr_id

    last_lora_id = node_ids[-1]

    # Update downstream references to point to the last LoRA node
    for nid, key in downstream_refs:
        workflow[nid]["inputs"][key] = [last_lora_id, 0]

    return workflow


# ============================================================================
# Unified Workflow Generation Helper
# ============================================================================

def generate_workflow_unified(
    template: Dict,
    acts: List[str] = None,
    csv_name: str = "lora_lookup.csv",
    workflow_name: str = None,
    extra_lora_names: List[str] = None,
    extra_lora_strengths: List[float] = None,
    filter_type: str = None,
    csv_dir: str = None,
    additional_params: Dict = None,
) -> Dict:
    """
    Generate a complete workflow with unified LoRA handling.

    This is a convenience function that combines:
    1. LoRA parameter resolution from CSV lookup
    2. Placeholder replacement in the workflow template
    3. Dynamic LoRA chaining

    Parameters
    ----------
    template : Dict
        The workflow JSON template (already loaded).
    acts : List[str], optional
        Action tags for LoRA lookup.
    csv_name : str
        Filename of the LoRA lookup CSV.
    workflow_name : str, optional
        Workflow name filter for CSV lookup.
    extra_lora_names : List[str], optional
        Additional LoRA names to prepend.
    extra_lora_strengths : List[float], optional
        Additional LoRA strengths.
    filter_type : str, optional
        Type filter for CSV ("image" or "video").
    csv_dir : str, optional
        Directory containing the CSV file.
    additional_params : Dict, optional
        Extra parameters to merge into the workflow (e.g., prompt, width, etc.).

    Returns
    -------
    Dict
        The complete workflow with LoRA placeholders applied and chain generated.
    """
    from copy import deepcopy

    if acts is None:
        acts = []
    if extra_lora_names is None:
        extra_lora_names = []
    if extra_lora_strengths is None:
        extra_lora_strengths = []
    if additional_params is None:
        additional_params = {}

    # Deep copy to avoid mutating the template
    workflow = deepcopy(template)

    # 1. Resolve LoRA params
    lora_resolved = resolve_lora_params(
        acts=acts,
        csv_name=csv_name,
        workflow_name=workflow_name,
        extra_lora_names=extra_lora_names,
        extra_lora_strengths=extra_lora_strengths,
        filter_type=filter_type,
        csv_dir=csv_dir,
    )
    dynamic_count = lora_resolved.get('dynamic_lora_count', 0)

    # 2. Merge params (additional params override LoRA defaults for non-LoRA keys)
    params = dict(additional_params)
    params.update(lora_resolved)

    # 3. Apply placeholders
    workflow = apply_lora_placeholders(workflow, params)

    # 4. Apply dynamic LoRA chaining
    workflow = apply_dynamic_lora_chaining(workflow, dynamic_count, lora_resolved)

    return workflow
