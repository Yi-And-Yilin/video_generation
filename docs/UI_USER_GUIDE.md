# Video Generation UI User Guide

## Overview

Video Generation UI is a Tkinter-based desktop application that provides a unified interface for AI-powered media generation workflows. The application uses a tabbed interface with four main sections, each dedicated to a specific type of generation task.

### Technical Details

- **Framework**: Tkinter with ttk widgets
- **Window Size**: 800x800 pixels
- **Image Handling**: PIL (Pillow) for thumbnails and clipboard operations
- **Logging**: Queue-based system with per-tab log windows
- **State Persistence**: JSON-based state save/load

---

## Tab Overview

The application uses a `ttk.Notebook` with four tabs:

| Tab | Purpose |
|-----|---------|
| **WAN** | Multi-step video generation pipeline with row-based task management |
| **LTX** | Video/image generation with configurable parameters |
| **Prompt** | LLM-powered prompt generation from templates |
| **Image** | Image generation from saved tasks |

---

## WAN Tab

The WAN tab provides a row-based interface for managing video generation tasks.

### Layout

```
+----------------------------------------------------------+
|  [+] [Add Image] [Run] [Cancel] [Clear All] Task:[v]     |  <- Control Bar
+----------------------------------------------------------+
|  User Instruction:                                        |
|  +------------------------------------------------------+|
|  |                                                      ||  <- Text Input (4 lines)
|  |                                                      ||
|  +------------------------------------------------------+|
+----------------------------------------------------------+
|  [Main] [Log]                                            |  <- Sub-notebook
|  +------------------------------------------------------+|
|  | [Row 1] [Row 2] ...                                   ||  <- Scrollable Rows
|  +------------------------------------------------------+|
|  +------------------------------------------------------+|
|  | [Log content...]                                      ||  <- Log Window (10 lines)
|  +------------------------------------------------------+|
+----------------------------------------------------------+
```

### Control Bar Buttons

| Button | Action |
|--------|--------|
| **`+`** | Add an empty row with default values |
| **`Add Image`** | Open file dialog to select image files (supports .png, .jpg, .jpeg, .gif, .bmp) |
| **`Run`** | Start processing all rows with selected task type |
| **`Cancel`** | Cancel ongoing processing (enabled only when running) |
| **`Clear All Rows`** | Remove all rows from the UI |
| **`Task` dropdown** | Select task type (loaded from `task_steps.csv`); default: **wan2.2** |

### Row Structure

Each row contains:

| Column | Content |
|--------|---------|
| **Thumbnail** | 100x100 preview of the source image |
| **File Name** | Readonly entry showing the image filename |
| **Video Prompt** | Editable entry with `...` button for long text editing |
| **Audio Prompt** | Editable entry for audio generation prompt |
| **Sec** | Duration in seconds (default: 6) |
| **Side** | Resolution side length (default: 720) |
| **Cat** | Category dropdown (10 options + NA) |
| **Batch** | Number of outputs to generate (default: 1) |
| **Up** | Upscale checkbox |
| **Aud** | Audio generation checkbox |
| **Del** | Delete this row |

### Category Options

The category dropdown includes:
- NA (Not Applicable)
- Sitting_panites
- Standing_panties
- Standing_butt
- Masturbation
- Oral
- Cowgirl
- Kiss
- Doggy
- Missionary

### User Instructions

- **User Instruction**: Multi-line text input (4 lines height) for describing what you want to generate
- **Paste Support**: Press `Ctrl+V` to paste images directly from clipboard

---

## LTX Tab

The LTX tab provides a streamlined interface for video and image generation.

### Layout

```
+----------------------------------------------------------+
|  [Run] [Pause] [Resume] [Clear Pending]    [Status]      |  <- Action Bar
+----------------------------------------------------------+
|  Res:[v] SEC:[ ] FPS:[ ] Lang:[v] Batch:[v] Img:[v][Up] |  <- Settings Bar
+----------------------------------------------------------+
|  User Instruction:                                        |
|  +------------------------------------------------------+|
|  |                                                      ||  <- Text Input (4 lines)
|  +------------------------------------------------------+|
+----------------------------------------------------------+
|  +------------------------------------------------------+|
|  | [Log content...]                                      ||  <- Log Window (10 lines)
|  +------------------------------------------------------+|
+----------------------------------------------------------+
```

### Action Bar Buttons

| Button | Action |
|--------|--------|
| **`Run`** | Start generation process |
| **`Pause`** | Pause ongoing generation (disabled when not running) |
| **`Resume`** | Resume paused generation (disabled when not paused) |
| **`Clear Pending`** | Clear pending jobs (light red background) |
| **Status** | Right-aligned label showing current status (Ready/Running/Paused) |

### Settings Bar

| Control | Options | Default |
|---------|---------|---------|
| **Res** (Resolution) | 1280*720, 720*1280, 1344*768, 480*854, 854*480, 720*720, 1024*1024 | 1280*720 |
| **SEC** (Duration) | Numeric entry | 10 |
| **FPS** | Numeric entry | 24 |
| **Lang** (Language) | Chinese, English | Chinese |
| **Batch** | Numeric entry | 1 |
| **Img Model** | Image model dropdown (loaded dynamically) | - |
| **Upscale** | Checkbox | Off |

### User Instructions

- **User Instruction**: Multi-line text input (4 lines height) for describing the generation
- **Log Window**: 10-line scrollable text area showing generation progress

---

## Prompt Tab

The Prompt tab uses an LLM to generate structured task JSON from natural language instructions.

### Layout

```
+----------------------------------------------------------+
|  [Run] [Open] [Delete] [Clear Log]         [Status]      |  <- Action Bar
+----------------------------------------------------------+
|  Template:[v]                                            |  <- Template Selection
+----------------------------------------------------------+
|  User Instruction:                                        |
|  +------------------------------------------------------+|
|  |                                                      ||  <- Text Input (6 lines)
|  |                                                      ||
|  +------------------------------------------------------+|
+----------------------------------------------------------+
|  +------------------------------------------------------+|
|  | [Log content...]                                      ||  <- Log Window (10 lines)
|  +------------------------------------------------------+|
+----------------------------------------------------------+
```

### Action Bar Buttons

| Button | Action |
|--------|--------|
| **`Run`** | Generate task JSON from instruction using LLM |
| **`Open`** | Open the latest generated task JSON file |
| **`Delete`** | Delete the latest generated task JSON file |
| **`Clear Log`** | Clear the log window |
| **Status** | Right-aligned label showing current status (Ready/Running) |

### Template Selection

- **Template dropdown**: Lists all `.md` files from `projects/ltx/prompts/`
- Templates include: general, plot-based, individual image schemas
- Selecting a template triggers system prompt loading

### User Instructions

- **User Instruction**: Multi-line text input (6 lines height)
- **Minimum length**: 6 lines required before Run is enabled
- **Log Window**: Shows streaming LLM response and generation progress

### Output

- Generated tasks are saved as JSON files to `projects/ltx/tasks/`
- Files are timestamped (format: `YYYYMMDD_HHMMSS.json`)

---

## Image Tab

The Image tab generates images from previously created task JSON files.

### Layout

```
+----------------------------------------------------------+
|  [Run]                                  [Status]          |  <- Action Bar
+----------------------------------------------------------+
|  Task:[v] [Refresh]    Res:[v]                           |  <- Settings
+----------------------------------------------------------+
|  +------------------------------------------------------+|
|  | [Log content...]                                      ||  <- Log Window (10 lines)
|  +------------------------------------------------------+|
+----------------------------------------------------------+
```

### Action Bar

| Button | Action |
|--------|--------|
| **`Run`** | Start image generation for selected task |
| **Status** | Right-aligned label showing current status (Ready/Running) |

### Settings

| Control | Options | Default |
|---------|---------|---------|
| **Task** | Dropdown listing task JSON files | - |
| **Refresh** | Reload task list from disk | - |
| **Res** (Resolution) | 1024*1024, 1280*720, 720*1280, 1344*768, 896*1152, 1152*896 | 1024*1024 |

### Log Window

- Shows generation progress and output paths
- 10-line scrollable text area

---

## Global Features

### State Persistence

- **State File**: `main_ui_state.json`
- **Auto-save**: State is saved 500ms after any row change (debounced)
- **Save on close**: State is saved when closing the application
- **Restored on startup**: Rows and settings are restored from saved state

### Logging System

- **Log File**: `main_ui.log` (main application log)
- **Queue-based**: Thread-safe logging using Python Queue
- **Per-tab logs**: Each tab has its own log window
- **Auto-scroll**: Log windows auto-scroll to latest entry
- **Line limit**: WAN log window maintains max 2000 lines

### Clipboard Integration

- **Ctrl+V**: Paste images from clipboard directly into WAN tab
- **File paths**: Paste image file paths from clipboard
- **Smart detection**: Automatically detects image vs text in clipboard

### Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| **Ctrl+V** | Paste image from clipboard (WAN tab) |

---

## Configuration

### Launch Method

- **Batch file**: `run_video_generation.bat` - Double-click to launch the application. 
- **Silent Launch**: The application now launches without a visible command prompt window using a background VBScript wrapper.
- **Log output**: stdout/stderr redirected to `main_crash_log.txt`.
- **Crash handling**: If the application fails to start, an error message will be displayed.

### UI Behavior

- **Horizontal Expansion**: Rows in the WAN Main tab now automatically expand to fill the full horizontal width of the window.
- **Scrollable Interface**: The WAN Main list is scrollable and supports mouse wheel interaction.

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| **COMFYUI_ROOT** | `D:\ComfyUI_windows_portable\ComfyUI` | ComfyUI installation path |
| **MMAUDIO_ROOT** | `D:\MMAudio` | MMAudio installation path |
| **COMFYUI_URL** | `http://192.168.4.22:8188/prompt` | ComfyUI API endpoint |

### External Files

| File | Purpose |
|------|---------|
| `task_steps.csv` | WAN task step definitions |
| `video_prompt.tsv` | Video prompt templates by category |
| `audio_prompt.tsv` | Audio prompt templates by category |
| `main_ui_state.json` | Saved UI state |
| `main_ui.log` | Application log |

---

## Tips

1. **WAN Tab**: Use the `+` button to quickly add empty rows, then fill in details
2. **LTX Tab**: Adjust resolution before running to avoid regeneration
3. **Prompt Tab**: Write detailed instructions for better LLM output
4. **Image Tab**: Click Refresh if your task doesn't appear in the dropdown
5. **State Save**: Close the application properly to save your work
6. **Clipboard**: Screenshots can be pasted directly into the WAN tab
