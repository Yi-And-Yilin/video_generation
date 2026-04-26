# Unified LoRA Protocol

> **Purpose**: Standardizes LoRA handling across all generation types (image, WAN video, LTX video) with a unified placeholder-based protocol and dynamic chaining support.

> **Last Updated**: 2026-04-26

---

## Table of Contents

1. [Background: The Problem](#background-the-problem)
2. [The Solution: Unified LoRA Protocol](#the-solution-unified-lora-protocol)
3. [Template Protocol](#template-protocol)
4. [CSV Lookup Format](#csv-lookup-format)
5. [Code Usage Examples](#code-usage-examples)
6. [Dynamic LoRA Chaining Logic](#dynamic-lora-chaining-logic)
7. [Migration Guide](#migration-guide)
8. [Template Examples](#template-examples)

---

## Background: The Problem

Prior to the unified LoRA protocol, LoRA handling was scattered and inconsistent across three generation systems:

- **Image generation (WAN)**: Used 5 hardcoded LoRA loader nodes (`lora1_name`, `lora1_strength` through `lora5_name`, `lora5_strength`) with static values in the workflow template.
- **WAN video generation**: Used hardcoded LoRA references (e.g., `"lora_name": "**dynamic_lora_chain_start**"`) but lacked a standardized runtime resolution mechanism.
- **LTX video generation**: Used hardcoded LoRA references (e.g., `"lora_name": "ltx\\ltx-2.3-22b-distilled-lora-384-1.1.safetensors"`) with no dynamic override support.

This fragmentation led to:
- Inconsistent placeholder naming conventions
- No shared runtime resolution pipeline
- Difficulty adding new generation types or LoRA workflows
- Template-specific code scattered across modules

---

## The Solution: Unified LoRA Protocol

All generation types now share the same LoRA handling pipeline:

### 1. Workflow Templates Use Placeholder Tokens

Templates use `**placeholder**` tokens (double-asterisk delimiters) for LoRA values:

| Placeholder | Purpose |
|---|---|
| `lora1_name` | First LoRA model name |
| `lora1_strength` | First LoRA strength (applies to model and/or clip) |
| `lora2_name` ... `lora5_name` | Second through fifth LoRA model names |
| `lora2_strength` ... `lora5_strength` | Second through fifth LoRA strengths |
| `dynamic_lora_chain_start` | Identifier for the Dynamic LoRA chain start node |
| `dynamic_lora_chain_strength` | Strength value for the Dynamic LoRA chain start node |

### 2. One Dynamic LoRA Placeholder Node Per Workflow

Each workflow template includes exactly one **"Dynamic LoRA (chain start)"** placeholder node:

- **class_type**: `"LoraLoaderModelOnly"`
- **_meta.title**: `"Dynamic LoRA (chain start)"`
- **model input**: Points to the upstream node (e.g., `UnetLoader` or `Distill LoRA`)

### 3. Runtime Processing Pipeline

At runtime, the LoRA resolution follows this pipeline:

1. **`load_lora_lookup()`** — Reads `lora_lookup.csv` and returns `{tag -> [{name, strength}, ...]}`
2. **`resolve_lora_params()`** — Converts CSV results to `{lora1_name, lora1_strength, ..., lora5_name, lora5_strength, dynamic_lora_count}`
3. **`apply_lora_placeholders()`** — Replaces all `**placeholder**` tokens in the workflow JSON with resolved values
4. **`apply_dynamic_lora_chaining()`** — Generates N LoRA nodes when `dynamic_lora_count > 1`

---

## Template Protocol

### How to Add/Modify LoRA Placeholders in Workflow JSON Templates

#### For Dynamic LoRA Chain (Video)

Add or modify a `LoraLoaderModelOnly` node in the template:

```json
"NODE_ID": {
  "inputs": {
    "lora_name": "**dynamic_lora_chain_start**",
    "strength_model": "**dynamic_lora_chain_strength**",
    "model": ["UPSTREAM_NODE_ID", 0]
  },
  "class_type": "LoraLoaderModelOnly",
  "_meta": {"title": "Dynamic LoRA (chain start)"}
}
```

- Replace `NODE_ID` with the actual node ID in your workflow
- Replace `UPSTREAM_NODE_ID` with the node that provides the model (e.g., `UnetLoaderGGUF`, `DistillLoRA`)
- The placeholder values (`**dynamic_lora_chain_start**`, `**dynamic_lora_chain_strength**`) are replaced at runtime by `apply_lora_placeholders()`

#### For Image Generation (5 Separate LoRAs)

Use the standard 5-LoRA placeholders in a `LoraLoader` node:

```json
"NODE_ID": {
  "inputs": {
    "lora_name": "**lora1_name**",
    "strength_model": "**lora1_strength**",
    "strength_clip": "**lora1_strength**",
    "model": ["UPSTREAM_NODE_ID", 0]
  },
  "class_type": "LoraLoader"
}
```

Note: Image generation uses **5 separate LoRA loader nodes** (`lora1` through `lora5`), not the Dynamic LoRA chain. This matches the WAN image workflow's existing structure.

### Placeholder Naming Convention

| Component | Pattern | Example |
|---|---|---|
| LoRA name | `**loraN_name**` | `**lora1_name**`, `**lora3_name**` |
| LoRA strength | `**loraN_strength**` | `**lora1_strength**`, `**lora5_strength**` |
| Chain start | `**dynamic_lora_chain_start**` | Single placeholder for chain node |
| Chain strength | `**dynamic_lora_chain_strength**` | Single placeholder for chain node |

---

## CSV Lookup Format

### Structure

`lora_lookup.csv` uses the following column layout:

| Column | Description |
|---|---|
| `tag1` | Primary identifier (used for lookup) |
| `tag2` | Secondary identifier / variant |
| `type` | `"image"` or `"video"` — filters applicable workflows |
| `workflow name` | Workflow identifier for scoped matching |
| `lora1_name` | First LoRA model filename (relative to LoRA directory) |
| `lora1_strength` | First LoRA strength (float, e.g., `0.7`) |
| `lora2_name` | Second LoRA model filename (optional) |
| `lora2_strength` | Second LoRA strength (optional) |
| `lora3_name`, `lora3_strength`, ... | Additional LoRAs (optional, up to 5) |

### Workflow Name Filtering

The `workflow name` column supports scoped matching:

| Workflow Name | Matches |
|---|---|
| `"ltx_standard"` | All `ltx_*` and `wan_*` video workflow templates |
| `"z-image"` | `z-image` workflow template |
| `"pornmaster_proSDXLV8"` | Only that specific image workflow |

### Example CSV Row

```csv
tag1_value,variant,video,ltx_standard,lora1.safetensors,0.8,lora2.safetensors,0.5,,
```

---

## Code Usage Examples

### Loading and Resolving LoRA Parameters

```python
from lora_lookup import load_lora_lookup, resolve_lora_params

# Load the lookup table
lora_table = load_lora_lookup("lora_lookup.csv")

# Resolve parameters for a tag in a video workflow
params = resolve_lora_params(lora_table, "my_tag", type="video", workflow="ltx_standard")

print(params)
# Output:
# {
#   "lora1_name": "lora1.safetensors",
#   "lora1_strength": 0.8,
#   "lora2_name": "lora2.safetensors",
#   "lora2_strength": 0.5,
#   "lora3_name": None,
#   "lora3_strength": None,
#   "lora4_name": None,
#   "lora4_strength": None,
#   "lora5_name": None,
#   "lora5_strength": None,
#   "dynamic_lora_count": 2
# }
```

### Applying Placeholders to a Workflow Template

```python
from workflow_template import load_template, apply_lora_placeholders

template = load_template("workflows/video/ltx_1st_sampling.json")
resolved_params = resolve_lora_params(lora_table, "my_tag", type="video", workflow="ltx_standard")
final_workflow = apply_lora_placeholders(template, resolved_params)
```

### Applying Dynamic LoRA Chaining

```python
from lora_chaining import apply_dynamic_lora_chaining

workflow = apply_lora_placeholders(template, resolved_params)
workflow = apply_dynamic_lora_chaining(workflow, resolved_params)
```

### Full Pipeline

```python
def build_workflow(tag, workflow_type, workflow_name):
    lora_table = load_lora_lookup("lora_lookup.csv")
    params = resolve_lora_params(lora_table, tag, type=workflow_type, workflow=workflow_name)
    
    template = load_template(determine_template_path(workflow_type, workflow_name))
    workflow = apply_lora_placeholders(template, params)
    workflow = apply_dynamic_lora_chaining(workflow, params)
    
    return workflow
```

---

## Dynamic LoRA Chaining Logic

When `dynamic_lora_count > 1`, the protocol generates N chained `LoraLoaderModelOnly` nodes:

### Case 1: `count == 0`

- **Action**: Remove the Dynamic LoRA node entirely
- **Effect**: Bypass the upstream node directly to downstream nodes
- **Use case**: No LoRA applied

### Case 2: `count == 1`

- **Action**: Single LoRA node passes through unchanged
- **Effect**: The placeholder node becomes the active LoRA loader
- **Use case**: Single LoRA applied

### Case 3: `count > 1`

- **Action**: Generate N `LoraLoaderModelOnly` nodes chained together

| Node | model input | lora input | strength input |
|------|------------|------------|----------------|
| Node 1 (replaces placeholder) | upstream_node → `[UPSTREAM, 0]` | `lora1` | `lora1_strength` |
| Node 2 | `[Node1, 0]` | `lora2` | `lora2_strength` |
| Node 3 | `[Node2, 0]` | `lora3` | `lora3_strength` |
| ... | ... | ... | ... |
| Node N | `[Node(N-1), 0]` | `loraN` | `loraN_strength` |

Downstream nodes reference **Node N**'s output.

### Example: 3 LoRA Chaining

```
upstream (UnetLoaderGGUF)
    ↓
LoraLoaderModelOnly (Node 1) — lora1, strength1
    ↓
LoraLoaderModelOnly (Node 2) — lora2, strength2
    ↓
LoraLoaderModelOnly (Node 3) — lora3, strength3
    ↓
downstream nodes (reference Node 3)
```

---

## Template Examples

### WAN Video (`wan_2.1_step1.json`)

```json
"28": {
  "inputs": {"model": ["29", 0]},
  "class_type": "wanBlockSwap"
},
"29": {
  "inputs": {
    "lora_name": "**dynamic_lora_chain_start**",
    "strength_model": "**dynamic_lora_chain_strength**",
    "model": ["32", 0]
  },
  "class_type": "LoraLoaderModelOnly",
  "_meta": {"title": "Dynamic LoRA (chain start)"}
},
"32": {
  "inputs": {"unet_name": "wan2.1-i2v-14b-720p-Q6_K.gguf"},
  "class_type": "UnetLoaderGGUF"
}
```

**Flow**: `UnetLoaderGGUF (32)` → `Dynamic LoRA placeholder (29)` → `wanBlockSwap (28)`

### LTX Video (`ltx_1st_sampling.json`)

```json
"9": {
  "inputs": {
    "lora_name": "ltx\\ltx-2.3-22b-distilled-lora-384-1.1.safetensors",
    "strength_model": 0.5,
    "model": ["19", 0]
  },
  "class_type": "LoraLoaderModelOnly",
  "_meta": {"title": "Distill Lora"}
},
"10": {
  "inputs": {
    "lora_name": "**dynamic_lora_chain_start**",
    "strength_model": "**dynamic_lora_chain_strength**",
    "model": ["9", 0]
  },
  "class_type": "LoraLoaderModelOnly",
  "_meta": {"title": "Dynamic LoRA (chain start)"}
}
```

**Flow**: `Distill LoRA (9)` → `Dynamic LoRA placeholder (10)` → downstream

### Image Generation (`wan_image.json`)

```json
"59": {
  "inputs": {
    "lora_name": "**lora1_name**",
    "strength_model": "**lora1_strength**",
    "strength_clip": "**lora1_strength**",
    "model": ["58", 0]
  },
  "class_type": "LoraLoader"
}
```

**Note**: Image generation uses **5 separate LoRA loader nodes** (`lora1` through `lora5`), not the Dynamic LoRA chain. This is because the WAN image workflow has 5 explicit LoRA loader nodes built into its template.

---

## Migration Guide

### For Existing Templates Without Dynamic LoRA Placeholders

1. **Identify** the LoRA loader node in the template
2. **Replace** hardcoded `lora_name` and `strength_model` values with placeholders:
   - For video: `"**dynamic_lora_chain_start**"` and `"**dynamic_lora_chain_strength**"`
   - For image: `"**lora1_name**"` and `"**lora1_strength**"` (or `lora2_name` etc. for additional nodes)
3. **Add** the `_meta` field with `{"title": "Dynamic LoRA (chain start)"}` for video templates
4. **Verify** the `model` input still points to the correct upstream node

### For Templates Already Using Dynamic LoRA Placeholders

- Ensure the placeholder values match the protocol: `**dynamic_lora_chain_start**` and `**dynamic_lora_chain_strength**`
- No other changes needed; the runtime pipeline will handle resolution

### For LTX Video Templates with Hardcoded LoRA

- Replace the hardcoded `lora_name` path with `"**dynamic_lora_chain_start**"`
- Replace the hardcoded `strength_model` value with `"**dynamic_lora_chain_strength**"`
- Add `"**lora1_name**"` and `"**lora1_strength**"` if using the 5-LoRA image-style approach (not recommended for LTX video — use Dynamic LoRA chain instead)

### For Image Templates Already Using 5-LoRA Pattern

- Verify placeholder names: `**lora1_name**` through `**lora5_name**` and `**lora1_strength**` through `**lora5_strength**`
- No changes to the chaining logic needed (image generation does not use Dynamic LoRA chaining)

---

## Quick Reference

| Concept | Video | Image |
|---------|-------|-------|
| LoRA placeholder pattern | `**dynamic_lora_chain_start**` | `**loraN_name**` |
| Strength placeholder pattern | `**dynamic_lora_chain_strength**` | `**loraN_strength**` |
| Max LoRAs | Dynamic (determined at runtime) | 5 fixed |
| Chaining | Automatic when count > 1 | Not used |
| Node class_type | `LoraLoaderModelOnly` | `LoraLoader` |
| Meta title | `"Dynamic LoRA (chain start)"` | (none) |

---

*Documentation last updated: 2026-04-26*
