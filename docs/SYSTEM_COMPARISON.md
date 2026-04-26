# Video Generation Systems Architecture Comparison

## Overview

This document provides a comprehensive comparison of the three video generation systems available in this project:

1. **gemini** – CLI-based automation framework with CSV template parsing
2. **main_ui (WAN)** – GUI-based system with TSV keyword lookup prompting
3. **main_ui (LTX)** – GUI-based system with LLM-based prompt generation

---

## 1. gemini Folder System

### 1.1 Purpose & Design Philosophy

The `gemini` folder is a **production-grade automation framework** designed for AI assistants (like Gemini CLI) or developers to orchestrate batch image and video generation.

**Core Philosophy:** Structured automation with deterministic outputs through template-based prompt generation.

### 1.2 Architecture Components

| Component | File | Purpose |
|-----------|------|---------|
| **Main Executor** | `comfyui_helper.py` | Runs tasks from JSON files, handles LoRA optimization |
| **Prompt Generator** | `prompt_generator.py` | Parses templates from `prompt_warehouse.csv`, maps placeholders |
| **Batch Generator** | `generate_batch.py` | Generates multiple images from a single character design |
| **Video Generator** | `generate_videos_from_images.py` | Converts PNG images to LTX-2 videos |
| **Task Updater** | `update_task_json.py` | Modifies task JSON files |
| **Cleanup Utility** | `cleanup_images.py` | Removes intermediate files |

### 1.3 Prompt Generation Method

**Template-Based with CSV Parsing**

```
User Input → prompt_generator.py → prompt_warehouse.csv → Placeholder Replacement → Task JSON
```

**Process:**
1. Load character form JSON (e.g., `character_forms/mature_curvy_lady.json`)
2. Load prompt templates from `prompt_warehouse.csv`
3. Replace placeholders: `{breasts}`, `{eyes}`, `{bottom}`, `{top}`, `{hand}`, `{panties_2}`
4. Apply special rules (e.g., `skindentation` for curvy characters)
5. Handle weighted/conditional syntax: `[option1:0.2, option2|option3]`
6. Output: `tasks/image/{job_id}.json` or `tasks/video/{job_id}.json`

### 1.4 LoRA Management

**CSV Lookup System**

- `image_lora_lookup.csv` – Maps tags to LoRA models for image workflows
- `video_lora_lookup.csv` – Maps tags to LoRA models for video workflows
- `action_lora_lookup.csv` – Action-specific LoRA mappings
- `sex_act_lookup.csv` – Sexual act category mappings

**Optimization:** Scenes are **sorted by LoRA tags** to group identical setups, maximizing VRAM cache efficiency.

### 1.5 Video Generation Pipeline (LTX Standard)

**Fixed 5-Step Pipeline:**

| Step | Name | Workflow File | Purpose |
|------|------|---------------|---------|
| 1 | Preparation | `ltx_preparation.json` | Sync images, encode prompts, generate latents |
| 2 | 1st Sampling | `ltx_1st_sampling.json` | Core motion generation |
| 3 | Upscale | `ltx_upscale.json` | Latent-space spatial enhancement |
| 4 | 2nd Sampling | `ltx_2nd_sampling.json` | High-res detail refinement |
| 5 | Decode | `ltx_decode.json` | VAE decoding to MP4 |

**Key Features:**
- Validation phase before execution (checks prompts, image files, LoRA mappings)
- Resume capability via `--step` flag
- Auto-cleanup after each step + delete intermediates after Step 5
- Skip invalid scenes with detailed reports

### 1.6 Command-Line Interface

```powershell
# Image Generation
python comfyui_helper.py --task tasks/image/mytask.json --task_type image --workflow wan_image --width 1024 --height 1024

# Video Generation (full pipeline)
python comfyui_helper.py --task tasks/video/mytask.json --task_type video --workflow ltx_standard --width 1024 --height 1024 --length 251

# Resume from Step 3
python comfyui_helper.py --task tasks/video/mytask.json --task_type video --workflow ltx_standard --step 3

# Process specific scenes
python comfyui_helper.py --task tasks/video/mytask.json --task_type video --workflow ltx_standard --indices 2,5,8
```

### 1.7 Strengths & Limitations

**Strengths:**
- ✅ LoRA grouping optimization (VRAM efficiency)
- ✅ Pre-validation of all scenes before execution
- ✅ Resume capability for failed runs
- ✅ Detailed validation reports
- ✅ Metadata extraction from images for video generation

**Limitations:**
- ❌ CLI-only (no visual interface)
- ❌ No WAN model support (only LTX-2)
- ❌ Requires JSON task files (manual or AI-assistant created)
- ❌ Template-based prompts less flexible than LLM

---

## 2. main_ui.py – WAN Tab System

### 2.1 Purpose & Design Philosophy

The WAN tab provides an **interactive GUI** for quick video generation using the WAN2.1/WAN2.2 models with **predefined action categories**.

**Core Philosophy:** Fast, deterministic generation using keyword-based prompt lookup.

### 2.2 Architecture Components

| Component | File/Location | Purpose |
|-----------|---------------|---------|
| **Main UI** | `main_ui.py` (WAN tab) | Visual interface for row-based task management |
| **Task Steps** | `task_steps.csv` | Defines workflow sequence per task type |
| **Video Prompts** | `video_prompt.tsv` | Pre-written prompts categorized by action |
| **Audio Prompts** | `audio_prompt.tsv` | Audio generation prompts by category |
| **Workflow Templates** | `workflows/` | ComfyUI workflow JSON templates |

### 2.3 Prompt Generation Method

**TSV Keyword Lookup System**

```
User Selects Category → Lookup video_prompt.tsv → Random Selection → Workflow
```

**TSV Structure (`video_prompt.tsv`):**
```
category          | video_prompt
------------------|---------------------------------------------------------------------------
sitting_panites   | A Chinese woman is sitting. She spread open her legs...
sitting_panites   | A Chinese woman sits. She parts her legs gradually...
standing_panties  | A Chinese woman stands facing the camera...
oral              | A Chinese woman kneels in front of her partner...
cowgirl           | A Chinese woman straddles her partner...
```

**Available Categories:**
- `Sitting_panites`
- `Standing_panties`
- `Standing_butt`
- `Masturbation`
- `Oral`
- `Cowgirl`
- `Kiss`
- `Doggy`
- `Missionary`
- `NA` (use custom prompt)

**Code Reference (lines 431-432):**
```python
vp = self._get_prompt_from_tsv(VIDEO_PROMPT_TSV, row["category"]) if row["category"] != "NA" else None
```

**Fallback:** If category = "NA", uses user-provided text from the video prompt input box.

### 2.4 Workflow Execution

**Configurable Multi-Step Pipeline**

Defined in `task_steps.csv`:
```
task_name,workflow_name,save_video,category
wan2.2,audio_generation,yes,no
wan2.2,wan_2.2_step0,no,no
wan2.2,wan_2.2_step1,no,no
wan2.2,wan_2.2_step2,no,no
wan2.2,wan_2.2_step3,yes,no
wan2.2,FlashSVR,yes,no
```

**String Placeholder Replacement:**
Workflow templates contain placeholders like:
- `**video_width**` → User's width setting
- `**video_seconds**` → User's duration setting
- `**video_pos_prompt**` → Selected prompt from TSV
- `**load_image**` → Input image filename
- `**job_id**` → Unique job identifier

### 2.5 User Interface Features

- **Visual Row Management:** Add rows via file browser, clipboard paste, or empty template
- **Thumbnail Preview:** See images before processing
- **Category Dropdown:** Select action category for prompt lookup
- **Custom Prompt Input:** Override category prompts with custom text
- **Batch Control:** Specify number of variations per row
- **Upscale Toggle:** Optional FlashSVR upscaling
- **Audio Toggle:** Optional MMAudio generation

### 2.6 Strengths & Limitations

**Strengths:**
- ✅ Visual, user-friendly interface
- ✅ Fast prompt selection (no LLM wait time)
- ✅ Supports WAN2.1, WAN2.2 models
- ✅ Audio generation integration (MMAudio)
- ✅ State persistence (save/load UI state)
- ✅ Clipboard paste support

**Limitations:**
- ❌ Limited to predefined action categories
- ❌ Random prompt selection (non-deterministic)
- ❌ No LoRA grouping optimization (per-scene LoRA lookup only)
- ❌ No pre-validation phase
- ❌ No step-resume capability
- ❌ No LTX model support (separate tab)

---

## 3. main_ui.py – LTX Tab System

### 3.1 Purpose & Design Philosophy

The LTX tab provides **LLM-driven creative generation** for LTX-2 video tasks, allowing users to describe scenes in natural language.

**Core Philosophy:** Maximum flexibility through AI-powered prompt generation.

### 3.2 Architecture Components

| Component | File/Location | Purpose |
|-----------|---------------|---------|
| **Main UI** | `main_ui.py` (LTX tab) | Visual interface for LTX task generation |
| **Prompt Templates** | `projects/ltx/prompts/` | Markdown templates with instructions |
| **JSON Schemas** | `projects/ltx/prompts/*.json` | Output schema definitions for LLM |
| **LLM Utility** | `llm_utils.py` | Streaming LLM inference (Qwen3.5-9B) |
| **Task Output** | `projects/ltx/task.json` | Generated task JSON for execution |
| **Workflow Generator** | `projects/ltx/workflow_generator.py` | Creates ComfyUI workflows from task data |

### 3.3 Prompt Generation Method

**LLM-Based Generation System**

```
User Instruction → Combine with Template → LLM (Qwen3.5) → Structured JSON → Task File
```

**Process:**
1. User writes natural language instruction (e.g., "A seductive scene with a woman in red dress")
2. System loads template: `multiple-scene-videos.md` or selected template
3. System loads schema: `multiple-scene-videos.json`
4. Constructs prompt: `system_prompt + user_prompt + instruction`
5. Streams response from LLM with function calling
6. Extracts JSON from "Formal Answer:" section
7. Saves to `projects/ltx/task.json`

**LLM Configuration:**
- Model: `huihui_ai/qwen3.5-abliterated:9b`
- Streaming: Yes (real-time output display)
- Thinking: Enabled
- Function Definition: JSON schema for structured output

### 3.4 Task Structure (LLM Output)

**Generated `task.json` contains:**
```json
{
  "parameters": {
    "res": "1024*1024",
    "sec": "10"
  },
  "ai_response": {
    "scenes": [
      {
        "scene_number": 1,
        "scene_description": "...",
        "first_frame_image_prompt": "...",
        "video_prompt": "...",
        "duration": 5,
        "camera_movement": "...",
        "motion_intensity": "moderate"
      },
      ...
    ]
  }
}
```

### 3.5 Workflow Execution

**Prompt Tab → Image Tab → Video Generation**

1. **Prompt Tab:** Generate task JSON via LLM
2. **Image Tab:** Select task JSON, execute image generation using `wan_image.json` template with unified `**XXX**` placeholder protocol
3. **Video Generation:** Use generated images as first frames for LTX-2 video generation

**Unified Protocol:** Image Tab now shares the same `_apply_placeholders` engine as WAN Tab. LTX templates (`ltx_preparation.json`, `ltx_1st_sampling.json`, `ltx_upscale.json`, `ltx_2nd_sampling.json`, `ltx_decode.json`) use WAN-style naming (`**placeholder**`) for cross-tab compatibility.

### 3.6 Strengths & Limitations

**Strengths:**
- ✅ Maximum creative flexibility (natural language input)
- ✅ Structured output with JSON schema
- ✅ Streaming LLM response (real-time feedback)
- ✅ Supports multiple prompt templates
- ✅ Generates complete multi-scene storyboards
- ✅ Reusable task JSON files

**Limitations:**
- ❌ Slow (LLM inference time: 10-60 seconds)
- ❌ Non-deterministic (LLM output varies)
- ❌ Requires LLM model availability
- ❌ May need multiple attempts for desired output
- ❌ No direct video execution (separate step required)
- ❌ No WAN model support

---

## 4. Comprehensive Comparison Matrix

| Feature | gemini | main_ui (WAN) | main_ui (LTX) |
|---------|--------|---------------|---------------|
| **Interface** | CLI / API | GUI (Tkinter) | GUI (Tkinter) |
| **Target User** | AI assistants, developers | Human users | Human users |
| **Prompt Source** | CSV templates + placeholders | TSV keyword lookup | LLM generation |
| **Prompt Method** | Placeholder replacement | Random category selection | Natural language → LLM |
| **Flexibility** | Medium (template variables) | Low (fixed categories) | Very High (LLM) |
| **Determinism** | Semi-deterministic | Non-deterministic (random) | Non-deterministic (LLM) |
| **Speed** | Fast (no LLM) | Fastest (lookup) | Slow (LLM inference) |
| **Models Supported** | LTX-2 only | WAN2.1, WAN2.2 | LTX-2 only |
| **Audio Support** | No | Yes (MMAudio) | No |
| **LoRA Support** | ✅ Grouping by tags | ✅ Auto-lookup (5 LoRAs) | ✅ Via workflow_generator.py |
| **Pre-Validation** | ✅ Full validation | ❌ Runtime errors | ❌ Runtime errors |
| **Resume Capability** | ✅ Step-level resume | ❌ Full re-run | ❌ Full re-run |
| **Batch Processing** | ✅ Index/Range selection | ✅ Per-row batch | ✅ Template-based |
| **State Persistence** | Task JSON files | UI state JSON | Task JSON files |
| **Cleanup** | ✅ Auto-cleanup | ✅ Post-task cleanup | ❌ Manual |
| **Placeholder Protocol** | `**XXX**` | `**XXX**` | `**XXX**` (unified) |

---

## 5. Use Case Recommendations

### 5.1 Choose **gemini** When:

- ✅ Generating large batches (50+ images/videos)
- ✅ Need consistent character styles across outputs
- ✅ VRAM optimization is important
- ✅ Want pre-validation before expensive generation
- ✅ Need to resume failed runs
- ✅ Working with AI assistants or scripts
- ✅ LTX-2 is your preferred video model

**Example Scenario:**
> "Generate 100 NSFW images of the same character in different poses, then convert 20 of them to videos."

### 5.2 Choose **main_ui (WAN)** When:

- ✅ Need quick prototyping/experimentation
- ✅ WAN2.1 or WAN2.2 is your preferred model
- ✅ Want visual, drag-and-drop interface
- ✅ Predefined action categories fit your needs
- ✅ Need audio generation (MMAudio)
- ✅ Want instant results (no LLM wait)
- ✅ Clipboard paste workflow preferred

**Example Scenario:**
> "Quickly generate a few cowgirl and oral videos from these images I have, with background audio."

### 5.3 Choose **main_ui (LTX)** When:

- ✅ Need creative, unique scenes
- ✅ Want to describe scenes in natural language
- ✅ Creating multi-scene storylines
- ✅ LTX-2 is your preferred video model
- ✅ Willing to wait for LLM generation
- ✅ Want structured task JSON for later use
- ✅ Exploring new creative directions

**Example Scenario:**
> "Create a 5-scene erotic story about a seductive encounter in a hotel room, with specific camera movements and timing."

---

## 6. File Structure Overview

```
video_generation/
│
├── main_ui.py                          # Main GUI application
│   ├── WAN Tab                         # TSV keyword lookup system
│   ├── LTX Tab                         # LLM-based generation
│   ├── Prompt Tab                      # Template-based LLM prompts
│   └── Image Tab                       # Image generation execution
│
├── gemini/                             # CLI automation framework
│   ├── comfyui_helper.py               # Main executor
│   ├── prompt_generator.py             # Template parser
│   ├── generate_batch.py               # Batch image generator
│   ├── generate_videos_from_images.py  # Image-to-video converter
│   ├── prompt_warehouse.csv            # Prompt templates
│   ├── image_lora_lookup.csv           # Image LoRA mappings
│   ├── video_lora_lookup.csv           # Video LoRA mappings
│   ├── character_forms/                # Character design JSONs
│   ├── comfyui_workflows/              # Workflow templates
│   └── tasks/                          # Generated task JSONs
│
├── projects/
│   ├── wan/
│   │   └── workflow/                   # WAN workflow templates
│   └── ltx/
│       ├── prompts/                    # LLM prompt templates
│       ├── workflow/                   # LTX workflow templates
│       └── workflow_generator.py       # Workflow generator
│
├── docs/                               # Documentation
│   ├── SYSTEM_ARCHITECTURE_COMPARISON.md  # This file
│   ├── UI_GUIDE.md
│   ├── main_workflow.md
│   └── comfyui_workflow_placeholders.md
│
├── video_prompt.tsv                    # WAN video prompts by category
├── audio_prompt.tsv                    # WAN audio prompts by category
└── task_steps.csv                      # WAN task step definitions
```

---

## 7. Integration Possibilities

### 7.1 gemini + main_ui (LTX)

**Workflow:** Use LTX tab to generate creative task JSON, then execute with gemini's optimized runner.

```powershell
# In main_ui LTX Tab: Generate task.json
# Then in gemini folder:
python comfyui_helper.py --task ../projects/ltx/task.json --task_type video --workflow ltx_standard
```

**Benefits:** Creative flexibility + production-grade execution

### 7.2 gemini + main_ui (WAN)

**Workflow:** Use WAN tab for quick prototyping, export results, then use gemini for batch scaling.

**Benefits:** Fast iteration + scalable production

### 7.3 Hybrid Approach

**Recommended Production Flow:**

1. **Ideation:** Use LTX tab to generate creative scene descriptions
2. **Prototyping:** Use WAN tab to quickly test concepts
3. **Production:** Use gemini to generate final batch with optimization
4. **Refinement:** Use any system for targeted fixes

---

## 8. Technical Notes

### 8.1 ComfyUI Server Configuration

All systems require a running ComfyUI server:

```powershell
# WAN / main_ui
COMFYUI_URL="http://192.168.4.22:8188/prompt"

# gemini
server_address="http://192.168.4.22:8188"
```

### 8.2 Model Requirements

| System | Required Models |
|--------|----------------|
| gemini | LTX-2, SDXL checkpoint, LoRAs per workflow |
| main_ui (WAN) | WAN2.1 or WAN2.2, FlashSVR (optional), MMAudio (optional) |
| main_ui (LTX) | LTX-2, SDXL checkpoint, Qwen3.5-9B for LLM |

### 8.3 Performance Considerations

| Metric | gemini | main_ui (WAN) | main_ui (LTX) |
|--------|--------|---------------|---------------|
| Setup Time | Medium (JSON creation) | Low (visual) | High (LLM wait) |
| Generation Speed | Fast (optimized) | Fast | Medium |
| VRAM Efficiency | High (LoRA grouping) | Medium | Medium |
| CPU Usage | Low | Low | High (LLM) |

---

## 9. Conclusion

This project provides **three complementary systems** for video generation, each optimized for different use cases:

- **gemini:** Production automation with optimization
- **main_ui (WAN):** Quick visual prototyping
- **main_ui (LTX):** Creative exploration with AI

Understanding the strengths and limitations of each system allows users to choose the right tool for their specific needs, or combine them for maximum productivity.

---

*Document Version: 1.0*
*Last Updated: 2026-04-21*
*Author: System Analysis*
