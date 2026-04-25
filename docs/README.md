# Documentation Index

Welcome to the Video Generation project documentation. This folder contains comprehensive guides for using and understanding the system.

---

## 📚 Documentation Files

### [SYSTEM_COMPARISON.md](./SYSTEM_COMPARISON.md)
**Purpose**: Architectural comparison of all three generation systems

**Contents**:
- Overview of gemini, main_ui (WAN), and main_ui (LTX) systems
- Comprehensive feature comparison matrix
- Use case recommendations for each system
- File structure overview
- Integration possibilities between systems
- Technical notes and performance considerations

**Best For**: Understanding which system to use for your specific needs

---

### [UI_USER_GUIDE.md](./UI_USER_GUIDE.md)
**Purpose**: User guide for the main_ui.py GUI application

**Contents**:
- Tab overview (WAN, LTX, Prompt, Image)
- Detailed UI layout and controls for each tab
- Button functions and settings explanations
- Category options and dropdown values
- Global features (state persistence, logging, clipboard)
- Configuration and environment variables
- Usage tips and best practices

**Best For**: Learning how to use the GUI application effectively

---

### [COMFYUI_API_INTEGRATION.md](./COMFYUI_API_INTEGRATION.md)
**Purpose**: Guide for ComfyUI API integration — image downloading, WebSocket completion detection, and API endpoints

**Contents**:
- ComfyUI asynchronous architecture overview
- Core API endpoints: `/prompt`, `/history`, `/view`
- Image downloading via `/view` endpoint (fix for remote ComfyUI servers)
- WebSocket completion detection with HTTP polling fallback
- Key components: `comfyui_image_utils.py`, modified `main_ui.py` methods
- Troubleshooting guide for common issues

**Best For**: Understanding how the application communicates with ComfyUI servers

---

### [WAN_WORKFLOW_TECHNICAL.md](./WAN_WORKFLOW_TECHNICAL.md)
**Purpose**: Technical reference for WAN workflow implementation

**Contents**:
- Flat Jobs architecture explanation
- `**XXX**` placeholder pattern (v2.1)
- LTX naming unification (v2.2)
- Complete placeholder reference (21+ standard placeholders)
- Workflow template placeholder distributions
- File naming conventions and step distinctions
- Discovery and tracking logic
- task_steps.csv workflow definitions
- Workflow template modification guide
- Debugging methods and troubleshooting

**Best For**: Developers modifying or extending WAN workflows

---

## 🗂️ Quick Navigation

| I want to... | Read this document |
|--------------|-------------------|
| Choose between gemini, WAN, or LTX systems | [SYSTEM_COMPARISON.md](./SYSTEM_COMPARISON.md) |
| Learn how to use the GUI interface | [UI_USER_GUIDE.md](./UI_USER_GUIDE.md) |
| Understand how images are downloaded from ComfyUI | [COMFYUI_API_INTEGRATION.md](./COMFYUI_API_INTEGRATION.md) |
| Understand ComfyUI API endpoints and WebSocket | [COMFYUI_API_INTEGRATION.md](./COMFYUI_API_INTEGRATION.md) |
| Understand WAN workflow technical details | [WAN_WORKFLOW_TECHNICAL.md](./WAN_WORKFLOW_TECHNICAL.md) |
| Find placeholder syntax for workflows | [WAN_WORKFLOW_TECHNICAL.md](./WAN_WORKFLOW_TECHNICAL.md) Section 2 |
| Debug workflow generation issues | [WAN_WORKFLOW_TECHNICAL.md](./WAN_WORKFLOW_TECHNICAL.md) Section 9 |
| Understand the three-system architecture | [SYSTEM_COMPARISON.md](./SYSTEM_COMPARISON.md) Section 4 |

---

## 📋 Document Summary

| File | Lines | Last Updated | Focus Area |
|------|-------|--------------|------------|
| SYSTEM_COMPARISON.md | 504 | 2026-04-23 | Architecture & Comparison |
| UI_USER_GUIDE.md | 323 | 2026-04-21 | User Interface Guide |
| WAN_WORKFLOW_TECHNICAL.md | 331 | 2026-04-23 | Technical Implementation |
| projects/ltx/parameter_extraction.py | 550 | 2026-04-23 | StandardWorkflowParams interface & extractors

---

## 🔗 Related Files (Outside docs/)

These files are referenced in the documentation but located elsewhere:

- `task_steps.csv` - WAN task step definitions
- `video_prompt.tsv` - Video prompt templates by category
- `audio_prompt.tsv` - Audio prompt templates by category
- `projects/ltx/parameter_extraction.py` - StandardWorkflowParams dataclass & extraction functions
- `projects/wan/workflow/` - WAN workflow JSON templates
  - `image/wan_image.json` - SDXL image generation
  - `video/wan_2.1_step*.json`, `video/wan_2.2_step*.json` - Video generation steps
  - `FlashSVR.json`, `clean_up.json`, `final_upscale.json` - Shared templates
- `projects/ltx/prompts/` - LTX prompt templates
- `gemini/prompt_warehouse.csv` - Gemini prompt templates
- `gemini/*_lora_lookup.csv` - LoRA mapping files

---

*Documentation last updated: 2026-04-23*
