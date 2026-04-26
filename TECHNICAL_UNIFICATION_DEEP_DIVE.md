# Technical Deep Dive: WAN & LTX Workflow Unification

## 1. Executive Summary & Conceptual Shift
This session successfully executed a complete "Decommission and Rebuild" of the LTX image generation pipeline. The system has moved from an **Imperative Discovery Pattern** (where code actively searched for nodes by title to modify them) to a **Declarative Replacement Pattern** (where workflows are pre-configured with `**XXX**` placeholders).

### The "Change Idea":
- **Eliminate Fragmented Logic:** Previously, the "WAN" tab and "Image" tab used entirely different codebases to talk to ComfyUI.
- **Unified Protocol:** All workflows now utilize the `**XXX**` string-replacement protocol.
- **LoRA Transparency:** Instead of the code "injecting" nodes into a JSON, the nodes are now permanent parts of the template, and the code simply "activates" them by filling in names and strengths (or deactivates them by setting strength to 0).

---

## 2. Detailed Technical Changes

### A. The Core Logic Engine (`main_ui.py`)
A new high-level method `_apply_placeholders` was implemented to act as the central brain for workflow preparation.
- **Category Intelligence:** The logic was expanded to detect categories from both the WAN UI dropdown and the LTX LLM-generated `main_sex_act` field. It normalizes these to lowercase for reliable CSV lookup.
- **Context-Aware LoRA Lookup:** The engine now detects if a workflow is "Image" or "Video" based on the task name or template filename. It then automatically selects either `image_lora_lookup.csv` (for SDXL) or `lora_lookup.csv` (for LTX/WAN).
- **Graceful LoRA Degradation:** If the lookup finds fewer than 5 LoRAs, the remaining nodes are automatically filled with `xl\add-detail.safetensors` at `0.0` strength to maintain a valid workflow chain without affecting the image.
- **Type-Safe Replacement:** The replacement loop now includes explicit logic to convert string placeholders to `int` for seeds/dimensions and `float` for LoRA strengths, ensuring ComfyUI API compatibility.

### B. Image Tab Modernization
The LTX Image tab was completely re-wired:
- **Template Migration:** It now points exclusively to the `wan_image.json` template.
- **Data Mapping:** A translation layer was added to map LLM scene data (like `first_frame_image_prompt` and `sex_loras`) into the "row" format expected by the unification engine.
- **Resolution Handling:** The UI resolution selector (e.g., "1024*1024") is now split and mapped to `**video_width**` and `**video_height**` placeholders dynamically.

### C. Workflow Generator Refactor (`projects/ltx/workflow_generator.py`)
The generator was stripped of its legacy LTX "node title" search functions and replaced with the WAN protocol:
- **`apply_wan_placeholders` Implementation:** A standalone utility that replicates the UI's placeholder logic for CLI use.
- **Unified `generate_api_workflow`:** This function now acts as a router. If `type="image"` is passed, it ignores the requested template and forces the use of `wan_image`, applying the standard 5-LoRA lookup.
- **Parameter Enrichment:** The generator now injects a wider array of default parameters, including random 15-digit seeds, default checkpoints, and standardized negative prompts.

### D. Workflow Template Overhaul
Every major template in the project was edited to follow the new standard:
- **`wan_image.json` (New):** A professional-grade SDXL workflow featuring a static 5-LoRA chain and unified placeholders for every key input.
- **`ltx_sampling.json`:** This was the most complex change. The dynamic "anchor node" injection was removed. It now features a fixed chain of 5 LoRA nodes (`**lora1_name**`...`**lora5_name**`). All global parameters (Width, Height, Length, FPS, Prompts) were moved to the `**XXX**` pattern.
- **`ltx_latent.json`:** Converted VAE decoding and latent loading to use `**video_latent**`, `**audio_latent**`, and `**fps**`.
- **`ltx-text-encoding.json`:** Converted to use `**prompt**`, `**negative_prompt**`, and conditioning filename placeholders.
- **`wan_2.1_step1_missionary.json` / `wan_2.1_step1_masturbation.json`:** Converted hardcoded conditioning paths to `**load_pos_conditioning**` / `**load_neg_conditioning**` placeholders.

### E. LTX Naming Unification (v2.2)
LTX templates previously used different placeholder names than WAN templates. All LTX templates now use the WAN naming convention:

| Old LTX Naming | New WAN Naming |
|---------------|----------------|
| `**positive_conditioning_load**` | `**load_pos_conditioning**` |
| `**negative_conditioning_load**` | `**load_neg_conditioning**` |
| `**positive_conditioning**` | `**save_pos_conditioning**` |
| `**negative_conditioning**` | `**save_neg_conditioning**` |

This ensures a single `_apply_placeholders` function can handle both WAN and LTX templates without naming conflicts.

---

## 3. Data & Mapping Updates

### `lookup/image_lora_lookup.csv`
Added exhaustive mappings for the WAN UI categories to support the Image Tab:
- **Categories mapped:** `masturbation`, `oral`, `cowgirl`, `kiss`, `doggy`, `sitting_panites`, `standing_panties`, `standing_butt`.
- Each category was assigned 1-2 relevant SDXL LoRAs with optimized strengths.

### `task_steps.csv`
- Added the `wan_image` task type to enable it in the WAN tab's task selector.

---

## 4. Placeholder Reference Map
The following placeholders are now globally supported across all unified workflows:

| Placeholder | Typical Usage |
|-------------|---------------|
| `**checkpoint**` | Base model (.safetensors) |
| `**prompt**` | Video/image prompt text |
| `**negative_prompt**` | Standard quality exclusions |
| `**image_pos_prompt**` | Main positive description |
| `**image_neg_prompt**` | Standard quality exclusions |
| `**video_width**` / `**video_height**` | Dimensional control |
| `**width**` / `**height**` | Generic dimensions (LTX) |
| `**length**` | Number of frames (LTX) |
| `**fps**` | Frame rate |
| `**random_number**` | Seeds (15-digit int) |
| `**lora[1-5]_name**` | LoRA filename |
| `**lora[1-5]_strength**` | LoRA weight (float) |
| `**save_video**` / `**save_image**` | Output filename prefix |
| `**load_image**` / `**image**` | Input image path |
| `**work_id**` | Work identifier |
| `**load_pos_conditioning**` | Load positive conditioning |
| `**load_neg_conditioning**` | Load negative conditioning |
| `**save_pos_conditioning**` | Save positive conditioning |
| `**save_neg_conditioning**` | Save negative conditioning |
| `**video_latent**` / `**audio_latent**` | Intermediate .latent files |

---

## 5. Impact on Maintenance
- **Decoupled IDs:** Node IDs (e.g., "node_id": "10") no longer matter for the logic; the code only cares about the strings *inside* the values.
- **Unified Debugging:** All tabs now generate debug JSONs in the `debug_workflows/` folder using the exact same naming convention, making multi-step troubleshooting much faster.
- **Script Portability:** Standalone scripts like `comfyui_job.py` are now effectively "upgraded" to the full LoRA-capable system by simply calling the unified generator.

---

## F. Parameter Extraction Architecture

### Pipeline Overview
All workflow generation funnels through a standardized pipeline:

```
task.json (source)
    ↓
extract_params_from_new_tab_task() / extract_params_from_scene_task() / extract_params_for_wan_video()
    ↓
StandardWorkflowParams dataclass (canonical interface)
    ↓
params.for_wan_image() / params.for_wan_video_step0() / etc. (typed dict subsets)
    ↓
generate_workflow_from_standard_params(template, params_dict, type, acts, ...)
    ↓
placeholder replacement → workflow JSON → ComfyUI API
```

### Three Extractors

1. **`extract_params_from_new_tab_task(task_path, scene_index, resolution)`**
   - Reads New tab task.json with `character_design`, `location_design`, `locations` structure
   - Extracts prompts from `location[scene_index].prompts[scene_index]`
   - Maps character metadata, sex_loras, category, and scene_index
   - Default negative prompt: SDXL quality exclusions

2. **`extract_params_from_scene_task(task_path, resolution)`**
   - Reads LTX scene-style task.json with `scenes` array
   - Extracts `first_frame_image_prompt`, `main_sex_act`, `sex_loras`
   - Similar defaults and field population as the New tab extractor

3. **`extract_params_for_wan_video(task_path, work_id, resolution, seconds)`**
   - Simplified extractor for the WAN video pipeline (img2vid)
   - Extracts `video_pos_prompt` from `location_design.locations[0].prompts[0]`
   - Sets `load_image`, `save_pos_conditioning`, `save_neg_conditioning`, `save_latent`, `save_video` with work_id-based names
   - Defaults: `fps=16`, `seconds` from parameter

### StandardWorkflowParams Dataclass
Located in `projects/ltx/parameter_extraction.py`, the dataclass provides:
- **60+ fields** covering all placeholder names across WAN 2.1, WAN 2.2, LTX, and SDXL templates
- **Typed dict subsets** via `for_wan_image()`, `for_wan_video_step0/1/2/3()`, `for_ltx_sampling()`, `for_ltx_text_encoding()`, `for_ltx_latent_decode()`
- **Utility methods**: `to_dict()`, `from_dict(data)`, `merge(**kwargs)`
- **Defaults**: LoRA defaults to `xl\add-detail.safetensors@0.0`, checkpoint to `pornmaster_proSDXLV8.safetensors`, random_number auto-generated
- **Fallback logic**: Methods use `or` patterns (e.g., `video_pos_prompt or self.prompt`) to ensure populated fields

### Integration Points
- The New tab's "Run ComfyUI" button calls `extract_params_from_new_tab_task()` → `for_wan_image()` → `generate_workflow_from_standard_params(type="image")`
- The WAN video pipeline calls `extract_params_for_wan_video()` → `for_wan_video_step0()` through `step3()` sequentially
- The LTX pipeline calls `extract_params_from_scene_task()` → `for_ltx_sampling()` / `for_ltx_text_encoding()` / `for_ltx_latent_decode()`
