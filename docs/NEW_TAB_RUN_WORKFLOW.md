# New Tab Run Button Workflow

## Overview

When the user clicks **"Run"** in the **New** tab, the application initiates an automated pipeline: character design → scene/location design → image prompt generation. All powered by a local LLM (Ollama). The workflow runs in a background thread so the UI remains responsive.

The New tab has a **split layout**: left pane for requirement input, right pane for a live log panel. A **Stop** button is available beside Run to abort the workflow between major phases.

---

## High-Level Flow

```
User enters requirements → Clicks "Run" → Background thread executes pipeline
    → Step 0: Create task.json (before any LLM call)
    → Step 1: Generate Character Design (LLM)
    → Step 2: Generate Scene/Location Design (LLM)
    → Step 3: Generate 3 image prompts per location
    → Save final task.json to disk
    → Update UI log
```

---

## Step-by-Step Breakdown

### 0. Entry Point — `main_ui.py::new_tab_run()`

**File:** `main_ui.py`, line ~831

When the button is clicked:

1. **Guard against double-click** — checks `self.new_tab_running`; if already running, returns immediately.
2. **Read user input** — grabs text from `self.new_requirement_box` (a ScrolledText widget).
3. **Validation** — if the input is empty, sets status to `"Please enter requirements"` and stops.
4. **UI state update** — disables the Run button, enables the Stop button, clears the log panel, sets status to `"Running..."`.
5. **Stop event** — creates `self.new_tab_stop_event = threading.Event()`.
6. **Background thread** — spawns a daemon thread that calls `run_new_tab_workflow(requirements, status_callback, stop_event)`.
7. **Status callback** — pushes messages to `self.new_log_queue` via `root.after()` (thread-safe Tkinter updates). Messages appear in the right-pane log.
8. **Stop handler** — `new_tab_stop()` sets `stop_event`, causing the workflow to abort at the next phase boundary.
9. **Completion** — on success, status shows `"Done: <job_id>"`; on error, shows `"Error: <message>"`. The Run button is re-enabled in a `finally` block.

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
- `prompts/location_design.md` — system prompt template
- `prompts/location_design.json` — tool schema (defines the `location_design` function with a `locations` array; each location has fields for elements, surfaces, lighting, character outfits, etc.)

**Process:**

1. Extract male and female character data from Phase 1.
2. Load the location design tool schema and system prompt template (rendered with `user_requirements`, male character JSON, and female character JSON).
3. Create a new `Conversation` object.
4. Send user message: `"Design the scene based on the characters and requirements."`
5. Stream the LLM response, same as Phase 1.
6. Parse `[TOOL_CALLS]:` marker, extract JSON, retrieve `function.arguments`.
7. Store result as `result["location_design"]`. If parsing fails, defaults to `{locations: []}`.
8. **Save `task.json`** (partial save after Phase 2).
9. **Check stop event** — abort if set.

---

### 4. Phase 3 — Image Prompt Generation

**Files involved:**
- `image_prompt_generator.py` — generates image prompts from location/character data

**Process:**

1. For each location in `location_design["locations"]`, call `generate_prompts_for_locations(location, character_design, count=3)`.
2. Each call produces **3 different prompt strings** by selecting random rows from `image_prompt_main_lookup.csv` and assembling a full prompt using the existing `build_location_prompt()` logic.
3. Embed the prompts into each location dict under a `"prompts"` key: a list of 3 strings.
4. **Save final `task.json`** with embedded prompts.

---

### 5. Persistence — Save to Disk

**File:** `tasks/<job_id>/task.json`

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
  }
}
```

The entire result dict is written as pretty-printed JSON with `indent=4`. Saves occur at **4 points**: immediately after directory creation, after Phase 1, after Phase 2, and after Phase 3.

---

## Architecture Diagram

```
┌────────────────────────────────────────────────────────────────────┐
│                        main_ui.py (New Tab)                        │
│  ┌──────────────────────────┐    ┌──────────────────────────────┐  │
│  │  Left Pane (Input)       │    │  Right Pane (Log)            │  │
│  │  ┌────────────────────┐  │    │  ┌────────────────────────┐  │  │
│  │  │ Run | Stop │ Status│  │    │  │ ScrolledText (disabled)│  │  │
│  │  ├────────────────────┤  │    │  │                        │  │  │
│  │  │ User Requirement   │  │    │  │  [10:00:00] Job ID: ...│  │  │
│  │  │ ScrolledText       │  │    │  │  [10:00:01] Created    │  │  │
│  │  │                    │  │    │  │  [10:00:02] Creating   │  │  │
│  │  │                    │  │    │  │  [10:00:03] LLM chunk..│  │  │
│  │  └────────────────────┘  │    │  │  ...                   │  │  │
│  │                          │    │  └────────────────────────┘  │  │
│  └─────────────┬────────────┘    └──────────────────────────────┘  │
│                │                                                    │
│         ┌──────▼──────────────┐                                    │
│         │ new_tab_run() (UI)  │→ spawns daemon thread              │
│         │ new_tab_stop()      │→ sets stop_event                  │
│         └────────┬────────────┘                                    │
└──────────────────┼────────────────────────────────────────────────┘
                   │
                   ▼
┌────────────────────────────────────────────────────────────────────┐
│                  new_tab_workflow.py (background thread)            │
│  ┌────────────────┐   ┌──────────────┐   ┌──────────────────────┐ │
│  │ Create task.   │→ │ Phase 1:     │→ │ Phase 2:             │ │
│  │ json (empty)   │   │ Character    │   │ Location Design      │ │
│  │                │   │ Design (LLM) │   │ (LLM)                │ │
│  │                │   │ [save+stop]  │   │ [save+stop]          │ │
│  │                │   └──────┬───────┘   └──────────┬───────────┘ │
│  └───────┬────────┘          │                      │              │
│          │                   └──────┬───────────────┘              │
│          │                          │                              │
│          ▼                          ▼                              │
│  ┌──────────────────────────────────────────────┐                  │
│  │ Phase 3: Image Prompt Generation             │                  │
│  │ For each location → generate 3 prompts       │                  │
│  │ Embed prompts into location["prompts"]       │                  │
│  │ [final save]                                 │                  │
│  └──────────────────────────────────────────────┘                  │
└────────────────────────────────────────────────────────────────────┘
                   │
                   ▼
┌────────────────────────────────────────────────────────────────────┐
│                  LLM Backend (Ollama)                       │
│  http://localhost:8081/v1/chat/completions                  │
│  Model: qwen                                                │
│  Stream: True                                               │
│  Tools: character_design / location_design                  │
└─────────────────────────────────────────────────────────────┘
```

---

## Key Dependencies

| Component | Purpose |
|-----------|---------|
| `llm_conversation.LLMUtils` | HTTP client for Ollama API; handles streaming, tool calling, JSON validation |
| `llm_conversation.Conversation` | Manages conversation history, system prompts, tool schemas |
| `llm_utils.render_md_template()` | Jinja2-style rendering of `.md` prompt templates with variables |
| `image_prompt_generator.generate_prompts_for_locations()` | Produces 3 prompts per location using CSV lookup |
| `tasks/<job_id>/` | Directory where each job's `task.json` and intermediate files are stored |
| `prompts/character_design.md` / `.json` | System prompt and function schema for character design |
| `prompts/location_design.md` / `.json` | System prompt and function schema for scene design |

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

---

## File Locations Reference

```
main_ui.py                          — UI code
  new_tab_run()                      — Entry point (~line 831)
  new_tab_stop()                     — Stop button handler (~line 802)
  new_tab_process_log_queue()        — Log panel queue processor (~line 783)
new_tab_workflow.py                 — Workflow logic
  run_new_tab_workflow()             — Main pipeline (~line 35)
  _generate_prompts_for_locations()  — Prompt generation orchestrator (~line 227)
image_prompt_generator.py           — Prompt builder
  generate_prompts_for_locations()   — Generates 3 prompts per location (~line 391)
llm_conversation.py                 — LLM client, Conversation & LLMUtils classes
prompts/character_design.md         — Character design system prompt template
prompts/character_design.json       — Character design tool schema
prompts/location_design.md          — Location design system prompt template
prompts/location_design.json        — Location design tool schema
tasks/<job_id>/task.json            — Output JSON (saves at 4 points during pipeline)
```
