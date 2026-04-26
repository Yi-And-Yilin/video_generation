# Session Summary: WAN & LTX Workflow Unification

## 1. Core Objectives & Change Ideas
The primary goal of this session was to standardize the project's generation logic. Previously, the system used two different approaches:
- **WAN Video System:** A modern, string-replacement pattern using `**XXX**` placeholders within workflow JSON values.
- **LTX System:** A legacy "discovery" pattern that searched for specific node titles (e.g., `**prompt`) to modify inputs.

The change idea was to **decommission the legacy LTX image generation** and unify all systems under the **WAN Dynamic Workflow Protocol**. This ensures that any workflow (Image or Video, WAN or LTX) can be updated using the same placeholder logic and dynamic LoRA/Checkpoint lookup mechanism.

---

## 2. Real Changes Implemented

### A. Architectural Unification in `main_ui.py`
- **Refactored Placeholder Logic:** Created a centralized `_apply_placeholders` method. This method now serves as the single source of truth for parameter injection. It scans the entire workflow JSON for any string containing `**XXX**` and replaces it with the corresponding value.
- **Dynamic LoRA/Checkpoint Integration:** Integrated a robust lookup system into the placeholder process. It now automatically queries `image_lora_lookup.csv` or `lora_lookup.csv` based on the task type and UI category, mapping up to 5 LoRAs and a specific checkpoint to the workflow.
- **WAN-style LTX Image Generation:** The "Image" tab no longer uses the `generate_api_workflow` legacy logic. It now loads the `wan_image.json` template and processes it through the unified placeholder method, making it functionally identical to the WAN tab's processing but powered by LTX/SDXL.

### B. Global Workflow Generator Update (`projects/ltx/workflow_generator.py`)
- **Decommissioned Title-Discovery:** Removed the complex logic that searched for nodes by `_meta.title`.
- **Implemented `apply_wan_placeholders`:** Added a new core function that implements the WAN-style string replacement.
- **Unified Image Routing:** Modified `generate_api_workflow` so that any request for an "image" type task is automatically routed to the standardized WAN image template, ensuring consistent results across CLI and GUI.

### C. Workflow Template Standardization
- **`wan_image.json` Template:** Standardized image generation template with 5-LoRA chain and specific `**XXX**` placeholders for dimensions, prompts, seeds, and models.
- **LTX Video Template Conversion:** Converted the three primary LTX video workflows (`ltx_sampling.json`, `ltx_latent.json`, and `ltx-text-encoding.json`) to use the new placeholder pattern. 
- **LoRA Chain Expansion:** Updated the LTX sampling template to include a 5-node LoRA chain to match the image generation capabilities.

### D. Category Mapping & Data
- **Expanded LoRA Lookups:** Updated `lookup/image_lora_lookup.csv` to map WAN UI categories (like "Oral", "Cowgirl", "Doggy") to specific LoRA sets. This allows the system to remain "simple" for the user (selecting a category) while being technically sophisticated in the background (applying specific LoRA combinations).

---

## 3. Files Modified or Created

### Core UI & Logic
- `main_ui.py`: Centralized placeholder logic, updated processing threads for WAN and Image tabs.
- `task_steps.csv`: Added the new `wan_image` task definition.
- `comfyui_job.py`: Updated to use the new unified workflow generator.

### Workflow Templates (`workflows/`)
- `wan_image.json`: Standardized image generation template (migrated from `projects/wan/workflow/image/`).
- `wan_2.2_step0.json`: Refined placeholder consistency.

### LTX Project Files (`projects/ltx/`)
- `workflow_generator.py`: Major refactor to use the WAN placeholder protocol.
- `workflow/video/ltx_sampling.json`: Converted to new placeholder pattern and 5-LoRA chain.
- `workflow/video/ltx_latent.json`: Converted to new placeholder pattern.
- `workflow/video/ltx-text-encoding.json`: Converted to new placeholder pattern.

### Lookup Data (`lookup/`)
- `image_lora_lookup.csv`: Added UI category-to-LoRA mappings.

---

## 4. Operational Impact
- **Standardization:** Developers only need to learn one way to add dynamic parameters to a workflow: add `**my_parameter**` to the JSON value.
- **Flexibility:** The LTX Image tab now benefits from the same "Category" LoRA logic as the WAN tab.
- **Maintenance:** The removal of hardcoded node title searches makes the system resilient to workflow changes (node ID shifts no longer break the code).