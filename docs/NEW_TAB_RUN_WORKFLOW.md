# New Tab Run Button Workflow

## Overview

When the user clicks **"Run"** in the **New** tab, the application initiates an automated pipeline: character design → scene/location design → image prompt generation → video prompt generation → ComfyUI image generation. All powered by a local LLM (Ollama). The workflow runs in a background thread so the UI remains responsive.

The New tab has a **split layout**: left pane for requirement input, right pane for a live log panel. A **Stop** button is available beside Run to abort the workflow between major phases. After the LLM pipeline completes, users can click **"Run ComfyUI"** to generate images via ComfyUI, selecting a workflow template from a **ComfyUI** dropdown (defaults to `wan_image`).

A **Type** dropdown allows switching between **Tag** mode (full 4-phase pipeline) and **Z** mode (LLM generates complete prompts directly, skipping Phase 3). The default mode is **Z**.

Generated images include embedded metadata (`prompt`, `video_prompt`, `sex_act`) for downstream video generation, stored in PNG files using PIL/Pillow's `pnginfo` parameter.

---

## High-Level Flow

### Tag Mode (Standard Pipeline)
```
User enters requirements → Selects Type: Tag → Clicks "Run" → Background thread executes pipeline
    → Step 0: Create task.json (before any LLM call)
    → Step 1: Generate Character Design (LLM)
    → Step 2: Generate Scene/Location Design (LLM)
    → Step 3: Generate 3 image prompts per location (CSV-based)
    → Step 4: Generate Video Prompts for each prompt (LLM)
    → Save final task.json to disk
    → Update UI log
```

### Z Mode (Direct Prompt Generation)
```
User enters requirements → Selects Type: Z (default) → Clicks "Run" → Background thread executes pipeline
    → Step 0: Create task.json (before any LLM call)
    → Step 1: Generate Character Design (LLM)
    → Step 2: Generate Scene/Location Design (LLM with complete prompts)
    → Step 3: SKIPPED — LLM already provided prompts
    → Step 4: Generate Video Prompts for each prompt (LLM)
    → Save final task.json to disk
    → Update UI log
```

---

## Step-by-Step Breakdown

### 0. Entry Point — `main_ui.py::new_tab_run()`

**File:** `main_ui.py`, line ~1107

When the button is clicked:

1. **Guard against double-click** — checks `self.new_tab_running`; if already running, returns immediately.
2. **Read user input** — grabs text from `self.new_requirement_box` (a ScrolledText widget).
3. **Read Type selection** — gets `self.new_tab_mode_var.get()` ("Tag" or "Z").
4. **Validation** — if the input is empty, sets status to `"Please enter requirements"` and stops.
5. **UI state update** — disables the Run button, enables the Stop button, clears the log panel, sets status to `"Running..."`.
6. **Stop event** — creates `self.new_tab_stop_event = threading.Event()`.
7. **Background thread** — spawns a daemon thread that calls `run_new_tab_workflow(requirements, status_callback, stop_event, mode=mode)`.
8. **Status callback** — pushes messages to `self.new_log_queue` via `root.after()` (thread-safe Tkinter updates). Messages appear in the right-pane log.
9. **Stop handler** — `new_tab_stop()` sets `stop_event`, causing the workflow to abort at the next phase boundary.
10. **Completion** — on success, status shows `"Done: <job_id>"`; on error, shows `"Error: <message>"`. The Run button is re-enabled in a `finally` block.

### Mode Switching — `main_ui.py::_on_mode_change()`

**File:** `main_ui.py`, line ~882

When the user changes the Type dropdown:

1. If **Z** mode: disables the ComfyUI template dropdown and sets it to `z-image`.
2. If **Tag** mode: re-enables the ComfyUI template dropdown with `readonly` state.

This ensures Z mode always uses the `z-image` workflow template and prevents accidental template selection.

---

### 1. Job Initialization — `new_tab_workflow.py::run_new_tab_workflow()`

**File:** `new_tab_workflow.py`, line 35

```
Input:  user_requirements (str), status_callback (callable), stop_event (threading.Event | None), mode (str = "Tag")
Output: dict with keys: job_id, user_requirements, character_design, location_design (with prompts), mode
```

| Step | Action |
|------|--------|
| 1.1 | Generate a random 5-character `job_id` (lowercase letters + digits) |
| 1.2 | Create a job directory under `tasks/<job_id>/` |
| 1.3 | **Immediately create `task.json`** with skeleton data (before any LLM call) |
| 1.4 | Initialize `LLMUtils` pointing to local Ollama at `http://localhost:8081`, model `qwen` |
| 1.5 | Store `"mode": mode` in the result dict |

---

### 1. Job Initialization — `new_tab_workflow.py::run_new_tab_workflow()`

**File:** `new_tab_workflow.py`, line 35

```
Input:  user_requirements (str), status_callback (callable), stop_event (threading.Event | None)
Output: dict with keys: job_id, user_requirements, character_design, location_design (with prompts)
```

| Step | Action |
|------|--------|
| 1.1 | Generate a random 5-character `job_id` (lowercase letters + digits) |
| 1.2 | Create a job directory under `tasks/<job_id>/` |
| 1.3 | **Immediately create `task.json`** with skeleton data (before any LLM call) |
| 1.4 | Initialize `LLMUtils` pointing to local Ollama at `http://localhost:8081`, model `qwen` |

---

### 2. Phase 1 — Character Design

**Files involved:**
- `prompts/character_design.md` — system prompt template
- `prompts/character_design.json` — tool schema (defines the `character_design` function with parameters: male/female objects, each with age, nationality, height, body_shape, hair_style, personality)

**Process:**

1. Load the character design tool schema and system prompt template (rendered with `user_requirements`).
2. Create a `Conversation` object with the system prompt and tool schema.
3. Send user message: `"Design characters based on the user requirements."`
4. Stream the LLM response chunk-by-chunk, pushing each chunk to the status callback.
5. Parse the response: look for `[TOOL_CALLS]:` marker, extract the JSON, and retrieve the `function.arguments` object.
6. Store result as `result["character_design"]`. If parsing fails, defaults to empty `{male: {}, female: {}}`.
7. **Save `task.json`** (partial save after Phase 1).
8. **Check stop event** — abort if set.

---

### 3. Phase 2 — Scene/Location Design

**Files involved:**
- **Tag mode:**
  - `prompts/location_design.md` — system prompt template
  - `prompts/location_design.json` — tool schema (defines the `location_design` function)
- **Z mode:**
  - `prompts/scene_design_z.md` — system prompt template
  - `prompts/scene_design_z.json` — tool schema (defines the `answer` function)

**Process:**

1. Extract male and female character data from Phase 1.
2. **Based on mode, load the appropriate tool schema and system prompt:**
   - **Tag mode:** Load `location_design` schema and template (rendered with `user_requirements`, male character JSON, female character JSON).
   - **Z mode:** Load `scene_design_z` schema and template (rendered with `user_requirements`, male character JSON, female character JSON).
3. Create a new `Conversation` object.
4. Send user message: `"Design the scene based on the characters and requirements."`
5. Stream the LLM response, same as Phase 1.
6. Parse `[TOOL_CALLS]:` marker, extract JSON, retrieve `function.arguments`.
7. Store result as `result["location_design"]`. If parsing fails, defaults to `{locations: []}`.
8. **Save `task.json`** (partial save after Phase 2).
9. **Check stop event** — abort if set.

**Z-mode vs Tag-mode Output Differences:**

| Aspect | Tag Mode | Z Mode |
|--------|----------|--------|
| Prompt format | Array of strings | Array of objects `{sex_act: "...", prompt: "..."}` |
| Prompt generation | CSV lookup in Phase 3 | Full prompt from LLM in Phase 2 |
| Number of prompts per location | 3 (generated in Phase 3) | Variable (1+ provided by LLM in Phase 2) |
| `sex_act` field | Inferred from CSV lookup | Explicitly provided by LLM |

---

### 4. Phase 3 — Image Prompt Generation (Tag mode only)

**Files involved:**
- `image_prompt_generator.py` — generates image prompts from location/character data

**Process (Tag mode only):**

1. For each location in `location_design["locations"]`, call `generate_prompts_for_locations(location, character_design, count=3)`.
2. Each call produces **3 different prompt strings** by selecting random rows from `image_prompt_main_lookup.csv` and assembling a full prompt using the existing `build_location_prompt()` logic.
3. Embed the prompts into each location dict under a `"prompts"` key: a list of 3 strings.
4. **Save final `task.json`** with embedded prompts.

**Z mode:** Phase 3 is **skipped entirely**. The LLM in Phase 2 already generates complete `sex_act` + `prompt` pairs, so the CSV-based prompt lookup is unnecessary.

---

### 5. Phase 4 — Video Prompt Generation

**Files involved:**
- `prompts/video_prompting.md` — system prompt template
- `prompts/video_prompting.json` — tool schema (defines the `video_prompting` function with parameters: action, line, audio, female_character_sound)

**Process:**

1. Extract prompts from `location_design` (either string list for Tag mode, or dict list with `image_prompt`/`video_prompt` for Z mode).
2. Build `first_frame_image_prompts` list for the LLM input.
3. Call the LLM with the `video_prompting` tool schema and prompt template (rendered with `user_requirements`, character design, and `first_frame_image_prompts`).
4. Stream the LLM response chunk-by-chunk, pushing each chunk to the status callback.
5. Parse LLM response: look for `[TOOL_CALLS]:` marker, extract JSON, retrieve `function.arguments` containing `action`, `line`, `audio`, `female_character_sound`.
6. Concatenate into `video_prompt = "{action} {line} {audio} {female_character_sound}".strip()`.
7. For each prompt, create an object: `{"image_prompt": "...", "video_prompt": "..."}`.
8. Replace the prompts in `location_design` with the updated dict format.
9. **Save `task.json`** with updated prompts (now dict format instead of plain strings).
10. **Check stop event** — abort if set.

**Z-mode vs Tag-mode differences for Phase 4:**

| Aspect | Tag Mode | Z Mode |
|--------|----------|--------|
| Input prompts | String list from Phase 3 CSV lookup | Dict list with `image_prompt` and `video_prompt` from Phase 2 |
| LLM input | `first_frame_image_prompts` containing `prompt` strings | `first_frame_image_prompts` containing `image_prompt`/`video_prompt` pairs |
| Output | New `video_prompt` generated by LLM based on image prompt | Refines existing `video_prompt` or leaves as-is |
| Final format | `{"image_prompt": "...", "video_prompt": "..."}` | `{"image_prompt": "...", "video_prompt": "..."}` |

---

### 5. Z-mode Prompt Format

**File:** `projects/ltx/parameter_extraction.py`, line ~327

When the mode is "Z", the LLM returns prompts as dictionaries:

```json
{
  "location": "bedroom",
  "time": "night",
  "lighting": "dim",
  "prompts": [
    {"sex_act": "kissing", "prompt": "A kissing scene in bedroom, intimate atmosphere, soft lighting..."},
    {"sex_act": "hugging", "prompt": "A hugging scene in bedroom, warm embrace, morning light..."}
  ],
  "main_sex_act": ["kissing", "hugging"]
}
```

The parameter extraction function `extract_params_from_new_tab_task()` detects this format (`isinstance(first_prompt, dict)`) and extracts both `sex_act` and `prompt` fields accordingly.

**Phase 4+ Format (After Video Prompt Generation):**

After Phase 4 completes, the prompt format is unified across both modes. The `prompt` field in the original format is replaced by `image_prompt`, and a new `video_prompt` field is added:

```json
{"image_prompt": "A kissing scene in bedroom, intimate atmosphere, soft lighting...", "video_prompt": "Two characters kissing, intimate and soft, whispers"}
```

The `extract_params_from_new_tab_task()` function detects this Phase 4+ format and prioritizes `image_prompt` over the legacy `prompt` field.

**Z-mode ComfyUI Execution:** In Z mode, the `new_tab_run_comfyui()` method uses the `z-image` workflow template (`projects/wan/workflow/image/z-image.json`) with hardcoded defaults:
- `steps`: 8
- `cfg`: 1
- `sampler_name`: "res_multistep"
- `scheduler`: "simple"
- `checkpoint`: "zImageTurboNSFW_50BF16Diffusion.safetensors"

The `z-image.json` template uses `**XXX**` placeholder tokens that are substituted by `apply_placeholders_unified()` before sending to ComfyUI.

**Metadata Injection:** After ComfyUI image generation, images are discovered from the ComfyUI history by scanning output nodes with `type == "output"` and an `images` array. Metadata JSON is injected into each image's PNG file using PIL/Pillow's `pnginfo` parameter. The metadata includes: `prompt`, `video_prompt`, `sex_act`, `male_character`, `female_character`, `location`, `job_id`, `timestamp`. Images are saved to the `output_images/` directory with structured naming: `<job_id>_scene_<index>_act_<sex_act>.png`.

---

### 5. Persistence — Save to Disk

---

### 5. Persistence — Save to Disk

**File:** `tasks/<job_id>/task.json`

**Tag mode output:**
```json
{
  "job_id": "<random 5-char>",
  "user_requirements": "<user input>",
  "character_design": { "male": {...}, "female": {...} },
  "location_design": {
    "locations": [
      {
        "location": "Traditional Japanese Garden",
        "location_major_elements": [...],
        "lighting": "...",
        "female_character": {...},
        "male_character": {...},
        "prompts": [
          "prompt string 1 for this location",
          "prompt string 2 for this location",
          "prompt string 3 for this location"
        ]
      }
    ]
  },
  "mode": "Tag"
}
```

**Z mode output:**
```json
{
  "job_id": "<random 5-char>",
  "user_requirements": "<user input>",
  "character_design": { "male": {...}, "female": {...} },
  "location_design": {
    "locations": [
      {
        "location": "bedroom",
        "time": "night",
        "lighting": "dim",
        "prompts": [
          {"sex_act": "kissing", "prompt": "A kissing scene in bedroom, intimate atmosphere..."},
          {"sex_act": "hugging", "prompt": "A hugging scene in bedroom, warm embrace..."}
        ],
        "main_sex_act": ["kissing", "hugging"]
      }
    ]
  },
  "mode": "Z"
}
```

The entire result dict is written as pretty-printed JSON with `indent=4`. Saves occur at **4 points**: immediately after directory creation, after Phase 1, after Phase 2, and (Tag mode only) after Phase 3.

---

### 6. Image Metadata Injection

**File:** `new_tab_workflow.py`, `main_ui.py::new_tab_run_comfyui()`

After ComfyUI generates images, metadata is embedded into each PNG file and organized into an `output_images/` directory.

**Image Discovery:**
Images are discovered by scanning the ComfyUI history output for nodes with `type == "output"` and an `images` array. Each image entry contains a filename and subfolder path.

**Metadata Structure:**
```json
{
  "prompt": "...",
  "video_prompt": "...",
  "sex_act": "...",
  "male_character": {...},
  "female_character": {...},
  "location": "...",
  "job_id": "...",
  "timestamp": "..."
}
```

**File Naming Convention:**
Output files follow the pattern: `<job_id>_scene_<index>_act_<sex_act>.png` (with safe character sanitization for filesystem compatibility).

**Embedding Process:**
1. Load the PNG image using PIL/Pillow.
2. Serialize the metadata to JSON.
3. Encode the JSON as a bytes string.
4. Create a `PngImagePlugin.PngInfo` object and add the metadata with `add_text("Prompt", ...)`.
5. Save the image with `pil_image.save(output_path, pnginfo=metadata)`.

---

## Run ComfyUI

After the LLM pipeline completes and `task.json` is saved, users can click **"Run ComfyUI"** to send generated image workflows to a ComfyUI instance.

### ComfyUI Workflow Selector

Before clicking "Run ComfyUI", users can select a workflow template from the **ComfyUI** dropdown:

- **Discovery**: `TemplateCatalog.get_wan_workflow_options()` scans `projects/wan/workflow/` (root, `image/`, and `video/` subfolders) and returns templates with priority ordering (`FlashSVR`, `clean_up`, `final_upscale`, `wan_image`, then alphabetically sorted others)
- **Default**: `wan_image` (SDXL image generation)
- **Loading**: `TemplateCatalog.load_template(template_name)` loads the JSON template file
- **Placeholder substitution**: `apply_placeholders_unified(workflow, params_dict)` replaces `**placeholder**` tokens with actual values extracted from `task.json`

### Run ComfyUI Flow

**File:** `main_ui.py`, line ~990

1. **Read task.json**: Opens the current task file and extracts `location_design.locations`
2. **Detect task mode**: Reads `task["mode"]` to determine Tag or Z mode
3. **For each scene/prompt combination**:
   - **Z mode**: Loads the `z-image` template via `TemplateCatalog.load_template("z-image")`, fills hardcoded defaults (steps=8, cfg=1, etc.), then applies placeholders via `apply_placeholders_unified()`
   - **Tag mode + wan_image template**: Uses `generate_workflow_for_wan_image()` from `workflow_generator.py`
   - **Tag mode + other templates**: Uses `TemplateCatalog.load_template()` + `apply_placeholders_unified()` with params from `parameter_extraction.extract_params_from_new_tab_task()`
4. **LoRA resolution**: Resolves LoRA names and strengths via `_resolve_lora_params()` and `image_lora_lookup.csv`
5. **Debug save**: Writes the generated workflow to `debug_workflows/` for inspection
6. **Send to ComfyUI**: Posts the workflow JSON to the ComfyUI API endpoint

### Parameter Extraction

The `StandardWorkflowParams` dataclass (from `projects/ltx/parameter_extraction.py`) provides a unified parameter interface across all workflow templates:

| Method | Returns For |
|--------|-------------|
| `for_wan_image()` | SDXL image generation params (checkpoint, dimensions, prompts, LoRA) |
| `for_wan_video_step0()` | WAN 2.2 Step 0 video prep params |
| `for_wan_video_step1()` | WAN 2.2 Step 1 params |
| `for_wan_video_step2()` | WAN 2.2 Step 2 params |
| `for_wan_video_step3()` | WAN 2.2 Step 3 decode params |

### Architecture Diagram

```
┌────────────────────────────────────────────────────────────────────────┐
│                      main_ui.py (New Tab)                              │
│  ┌──────────────────────────┐    ┌──────────────────────────────┐     │
│  │  Left Pane (Input)       │    │  Right Pane (Log)            │     │
│  │  ┌────────────────────┐  │    │  ┌────────────────────────┐  │     │
│  │  │ Run | Stop │ Status│  │    │  │ ScrolledText (disabled)│  │     │
│  │  ├────────────────────┤  │    │  │                        │  │     │
│  │  │ Type: [Z ▼]        │  │    │  │  [10:00:00] Job ID: ...│  │     │
│  │  ├────────────────────┤  │    │  │  [10:00:01] Created    │  │     │
│  │  │ User Requirement   │  │    │  │  [10:00:02] Phase 1:   │  │     │
│  │  │ ScrolledText       │  │    │  │  [10:00:03] LLM chunk..│  │     │
│  │  │                    │  │    │  │  ...                   │  │     │
│  │  └────────────────────┘  │    │  └────────────────────────┘  │     │
│  │                          │    └──────────────────────────────┘     │
│  │  [Open JSON][Run ComfyUI│  │                                    │     │
│  │  [Browse Task] [path    │  │                                    │     │
│  │  ComfyUI: [z-image ▼] │  │  (disabled in Z mode)               │     │
│  └─────────────┬────────────┘    └──────────────────────────────┘     │
│                │                                                        │
│         ┌──────▼──────────────┐                                        │
│         │ new_tab_run() (UI)  │→ spawns daemon thread                  │
│         │ _on_mode_change()   │→ toggles ComfyUI dropdown state        │
│         │ new_tab_stop()      │→ sets stop_event                       │
│         │ new_tab_run_comfyui()│→ mode-aware ComfyUI execution          │
│         └────────┬────────────┘                                        │
└──────────────────┼─────────────────────────────────────────────────────┘
                    │
                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                  new_tab_workflow.py (background thread)               │
│  ┌────────────────┐   ┌──────────────┐   ┌──────────────────────┐    │
│  │ Create task.   │→ │ Phase 1:     │→ │ Phase 2:             │    │
│  │ json (empty)   │   │ Character    │   │ Scene Design (LLM)   │    │
│  │                │   │ Design (LLM) │   │ (mode-aware)         │    │
│  │                │   │ [save+stop]  │   │ [save+stop]          │    │
│  │                │   └──────┬───────┘   └──────────┬───────────┘    │
│  └───────┬────────┘          │                      │                 │
│          │                   │ Tag→location_design   │ Z→scene_design_z│
│          │                   │                      │                 │
│          ▼                   │                      │                 │
│  ┌────────────────┐   ┌──────┴──────────┐   ┌──────┴───────────┐    │
│  │ Phase 3:       │   │ Phase 3:        │   │ Phase 3: SKIPPED │    │
│  │ Image Prompts  │   │ (Tag mode only) │   │ (Z mode)         │    │
│  │ Tag mode only  │   │ CSV-based 3x    │   │ LLM provided     │    │
│  └────────────────┘   └─────────────────┘   └──────────────────┘    │
│                                                                      │
│  Result dict includes "mode": "Tag" or "mode": "Z"                   │
└────────────────────────────────────────────────────────────────────────┘
                    │
                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                  Run ComfyUI (main_ui.py::new_tab_run_comfyui)         │
│  ┌──────────────────────────────────────────────────────────┐         │
│  │ Z mode:                                                  │         │
│  │   • Loads z-image template (fixed)                       │         │
│  │   • Hardcoded defaults: steps=8, cfg=1                   │         │
│  │   • apply_placeholders_unified()                         │         │
│  │                                                            │         │
│  │ Tag mode:                                                │         │
│  │   • wan_image → generate_workflow_for_wan_image()        │         │
│  │   • other → TemplateCatalog.load_template()              │         │
│  │             + apply_placeholders_unified()               │         │
│  │   • Resolve LoRA params via _resolve_lora_params()       │         │
│  │ 4. Save debug JSON to debug_workflows/                   │         │
│  │ 5. POST to ComfyUI API                                   │         │
│  └──────────────────────────────────────────────────────────┘         │
└────────────────────────────────────────────────────────────────────────┘
                    │
                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                  LLM Backend (Ollama)                       │
│                  ComfyUI API                           │
│  http://localhost:8081/v1/chat/completions                  │      │
│  Model: qwen                                                │      │
│  Tools: character_design / location_design / answer(Z-mode) │      │
│  Endpoint: COMFYUI_URL (/prompt)                            │      │
│  Templates: TemplateCatalog (projects/wan/workflow/ root, image/, video/)  │      │
│  Placeholders: apply_placeholders_unified(**XXX**)          │      │
│  Z-mode template: z-image.json (placeholder tokens)         │      │
└─────────────────────────────────────────────────────────────┘
```

---

## Key Dependencies

| Component | Purpose |
|-----------|---------|
| `llm_conversation.LLMUtils` | HTTP client for Ollama API; handles streaming, tool calling, JSON validation |
| `llm_conversation.Conversation` | Manages conversation history, system prompts, tool schemas |
| `llm_utils.render_md_template()` | Jinja2-style rendering of `.md` prompt templates with variables |
| `image_prompt_generator.generate_prompts_for_locations()` | Produces 3 prompts per location using CSV lookup (Tag mode only) |
| `workflow_selector.TemplateCatalog` | Static registry for scanning/loading workflow, prompt, and task templates |
| `workflow_selector.apply_placeholders_unified()` | Placeholder substitution for ComfyUI workflow JSON; handles int/float conversion for numeric placeholders |
| `parameter_extraction.StandardWorkflowParams` | Unified parameter dataclass across all workflow templates |
| `parameter_extraction.extract_params_from_new_tab_task()` | Extracts params from task.json for ComfyUI workflows; detects Z-mode dict prompts |
| `parameter_extraction.extract_params_from_z_mode_task()` | Wrapper for Z-mode task extraction |
| `tasks/<job_id>/` | Directory where each job's `task.json` and intermediate files are stored |
| `projects/wan/workflow/{root,image,video}/*.json` | ComfyUI workflow templates loaded by TemplateCatalog |
| `projects/wan/workflow/image/z-image.json` | Z-mode ComfyUI workflow template with `**XXX**` placeholder tokens |
| `prompts/character_design.md` / `.json` | System prompt and function schema for character design |
| `prompts/location_design.md` / `.json` | System prompt and function schema for scene design (Tag mode) |
| `prompts/scene_design_z.md` / `.json` | System prompt and function schema for scene design (Z mode) |

---

## Error Handling

| Scenario | Behavior |
|----------|----------|
| Empty user input | Status shows `"Please enter requirements"`, nothing runs |
| LLM unreachable | Exception caught in thread, status shows `"Error: <message>"` |
| JSON parse failure | Falls back to empty design objects, status shows `"Warning: Could not parse..."` |
| Button double-click | Guard `new_tab_running` prevents concurrent execution |
| User clicks Stop | `stop_event.set()` triggers abort at next phase boundary; partial `task.json` is saved |
| `image_prompt_generator` import fails | Phase 3 is skipped with a warning; `task.json` still saved |
| No task loaded (Run ComfyUI) | Status shows `"No task loaded"`, button returns immediately |
| Workflow template not found | Raises `FileNotFoundError` from `TemplateCatalog.load_template()` |
| ComfyUI connection fails | Error logged; individual scene failures don't stop processing of remaining scenes |
| Z-mode template not found (z-image) | Error during ComfyUI execution; status shows error message |
| Z-mode LLM returns malformed prompts | `extract_params_from_new_tab_task()` handles gracefully with defaults |

---

## File Locations Reference

```
main_ui.py                          — UI code
  new_tab_run()                      — Entry point (~line 1107)
  new_tab_stop()                     — Stop button handler (~line 802)
  new_tab_run_comfyui()              — Run ComfyUI handler (~line 990)
  new_tab_process_log_queue()        — Log panel queue processor (~line 783)
  _on_mode_change()                  — Type dropdown handler (~line 882)
  comfyui_template_dropdown          — ComfyUI template selector (disabled in Z mode)
  new_tab_mode_dropdown              — Type selector (Tag/Z)
new_tab_workflow.py                 — Workflow logic
  run_new_tab_workflow()             — Main pipeline (~line 35)
  _generate_prompts_for_locations()  — Prompt generation orchestrator (~line 227)
image_prompt_generator.py           — Prompt builder
  generate_prompts_for_locations()   — Generates 3 prompts per location (~line 391)
llm_conversation.py                 — LLM client, Conversation & LLMUtils classes
workflow_selector.py                — TemplateCatalog, apply_placeholders_unified
parameter_extraction.py              — StandardWorkflowParams, extract_params_from_new_tab_task(), extract_params_from_z_mode_task()
projects/wan/workflow/              — ComfyUI workflow templates
  image/  wan_image.json              — SDXL image generation (Tag mode)
          z-image.json                — Z-mode image generation (~line 1045)
  video/  wan_2.1_step*.json          — WAN 2.1 video generation
          wan_2.2_step*.json          — WAN 2.2 video generation
  FlashSVR.json                       — Upscale (shared)
  clean_up.json                       — Cleanup (shared)
  final_upscale.json                  — Upscale (shared)
prompts/character_design.md         — Character design system prompt template
prompts/character_design.json       — Character design tool schema
prompts/location_design.md          — Location design system prompt template (Tag mode)
prompts/location_design.json        — Location design tool schema (Tag mode)
prompts/scene_design_z.md           — Scene design system prompt template (Z mode)
prompts/scene_design_z.json         — Scene design tool schema (Z mode, function: answer)
tasks/<job_id>/task.json            — Output JSON (saves at 4 points during pipeline)
```
