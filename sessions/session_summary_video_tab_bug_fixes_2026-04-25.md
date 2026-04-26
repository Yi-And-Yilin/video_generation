# Session Summary: Video Tab Bug Fixes

**Date:** 2026-04-25
**Session Tasks:** video_tab.py bug fixes and validation

---

## 1. User's Original Request

User said: "carry on" - asking to continue reviewing and fixing the video generation tab implementation.

**Pending/Ongoing Tasks from Previous Session:**
- Video tab Wan/LTX workflow execution needs testing with actual ComfyUI
- Chinese characters display correctly in task.json when viewed in UTF-8 editor (verified)
- Test Video tab with actual LTX and Wan video generation workflows

---

## 2. Background Knowledge

### Project Structure
- **Root:** `C:\SimpleAIHelper\video_generation`
- **Video Tab Module:** `video_tab.py` - New module for video generation from selected images
- **LTX Batch Runner:** `projects/ltx/batch_runner.py` - 4-phase pipeline (Image → Text Encoding → Sampling → Latent Decode)
- **Wan Workflow Templates:** `projects/wan/workflow/` - JSON workflow templates with placeholder replacement
- **Main UI:** `main_ui.py` - Integrates Video tab via `create_video_tab()` factory function

### Key Architecture Decisions
1. **Video prompts are location-based** - organized by scene, each with `image_prompt` + `video_prompt` dict (`action`, `line`, `female_character_sound`)
2. **Chinese characters preserved** via `ensure_ascii=False` on all JSON writes
3. **Lazy imports** - `video_tab.py` uses `_mu()`/`_c()` methods to avoid circular dependency with `main_ui.py`
4. **Two engines supported:**
   - **LTX:** Uses `BatchRunner` from LTX project (4-phase pipeline)
   - **WAN:** Uses workflow template files with `**placeholder**` replacement and ComfyUI API

### ComfyUI API Pattern
```python
# Correct payload format
payload = {"prompt": workflow, "prompt_id": str(uuid.uuid4())}
response = requests.post(COMFYUI_URL, json=payload, timeout=30)
```

---

## 3. Changes Made

### File: `video_tab.py`

#### Fix 1: Grid Layout Overlap (Lines 381-394)
**Problem:** Sec and Width fields both used `row=2` in grid, causing visual overlap.

**Change:**
```python
# Before (broken):
tk.Label(info_frame, text="Sec:").grid(row=2, column=0)
sec_ent.grid(row=2, column=1)
tk.Label(info_frame, text="Width:").grid(row=2, column=2)  # Same row!
width_ent.grid(row=2, column=2)

# After (fixed):
tk.Label(info_frame, text="Sec:").grid(row=2, column=0)
sec_ent.grid(row=2, column=1)
tk.Label(info_frame, text="Width:").grid(row=3, column=0)  # New row
width_ent.grid(row=3, column=1)
tk.Label(info_frame, text="Batch:").grid(row=4, column=0)  # New row
batch_ent.grid(row=4, column=1)
```

#### Fix 2: Video Height Placeholder Bug (Lines 666-671)
**Problem:** `**video_height**` used `row["width"].get()` instead of extracting height from resolution string.

**Change:**
```python
# Before (broken):
"**video_height**": row["width"].get(),  # Wrong - same as width

# After (fixed):
res = self.resolution_var.get()
if '*' in res:
    _, height = res.split('*')
else:
    height = row["width"].get()  # fallback to width
"**video_height**": height,
```

#### Fix 3: Add main_sex_act to LTX Task Dict (Lines 566-578)
**Problem:** LTX task dict missing `main_sex_act` field required by `BatchRunner.run_batch()` for LoRA selection.

**Change:**
```python
# Added before tasks list:
main_action = ""
if video_prompt:
    lines = video_prompt.split('\n')
    main_action = lines[0][:50] if lines else ""

tasks = [{
    "work_id": work_id,
    "prompt": video_prompt or row.get("image_path", ""),
    "video_pos_prompt": video_prompt,
    "negative_prompt": "ugly, deformed, bad quality",
    "main_sex_act": main_action,  # NEW FIELD
    "scene_index": i,
    "prompt_index": 0
}]
```

#### Fix 4: ComfyUI Workflow Sending (Lines 737-751)
**Problem:** `_send_workflow_to_comfyui()` used wrong URL format and payload structure.

**Change:**
```python
# Before (broken):
resp = requests.post(
    c["COMFYUI_URL"].replace("/prompt", ""),  # Strips /prompt - wrong endpoint
    json=workflow,  # Wrong payload format
    timeout=30
)

# After (fixed):
import uuid
prompt_id = str(uuid.uuid4())
payload = {"prompt": workflow, "prompt_id": prompt_id}
resp = requests.post(c["COMFYUI_URL"], json=payload, timeout=30)  # Correct endpoint and format
if resp.ok:
    return prompt_id
```

#### Fix 5: Indentation Correction (Line 660)
**Problem:** Mixed indentation (spaces vs tabs) in `_run_wan_video_generation()` caused syntax error.

**Change:** Normalized all indentation to use consistent 4-space indentation.

---

## 4. Next Steps

### Immediate Testing Required
1. **Test LTX engine** with actual images and video prompts
   - Verify 4-phase pipeline (Image → Text Encoding → Sampling → Latent Decode)
   - Check LoRA selection based on `main_sex_act`
   
2. **Test Wan engine** with workflow templates
   - Verify placeholder replacement (`**prompt**`, `**video_width**`, `**video_height**`, etc.)
   - Confirm ComfyUI workflow submission and completion polling

3. **Test load_from_task_json()** with location-based task.json files
   - Verify image matching by filename pattern: `{location}_scene{idx}_p{p_idx}.png`
   - Check video prompt extraction (action, line, sound)

### Pending Features
- **Wan task type dropdown** currently only visible when WAN engine selected (line 174-176)
- **Image model dropdown** populated from `TemplateCatalog.get_checkpoint_options()`
- **State persistence** via `STATE_FILE` - saves/loads row data across sessions

---

## 5. Tricks/Lessons Learned

### Gotcha #1: Tkinter Grid Row Conflicts
When multiple Entry widgets share the same `row` value in `.grid()`, they overlap visually. Always use unique row numbers or group widgets intentionally.

### Gotcha #2: ComfyUI API Payload Format
The ComfyUI server expects:
```python
{"prompt": <workflow_dict>, "prompt_id": <uuid_string>}
```
NOT:
```python
{"prompt": <workflow_dict>}  # Missing prompt_id - may cause issues
```

### Gotcha #3: Resolution Parsing
Resolution format is `"WIDTH*HEIGHT"` (e.g., "1280*720"). Use `.split('*')` to extract both values. If format doesn't contain `*`, fallback to using width for height.

### Pattern: Lazy Imports to Avoid Circular Dependency
```python
def _mu(self):
    """Lazy import main_ui module to avoid circular import."""
    import main_ui
    return main_ui

def _c(self):
    """Get constants from main_ui lazily."""
    mu = self._mu()
    return {
        "COMFYUI_URL": mu.COMFYUI_URL,
        # ... other constants
    }
```

### Pattern: Placeholder Replacement in JSON Workflows
```python
replacements = {
    "**prompt**": video_prompt or "",
    "**video_width**": width,
    "**video_height**": height,
    # ...
}

for node_id, node in wf_json.items():
    inputs = node.get("inputs", {})
    for k, v in inputs.items():
        if not isinstance(v, str):
            continue
        for placeholder, repl_val in replacements.items():
            if placeholder in v:
                inputs[k] = v.replace(placeholder, str(repl_val))
                break
```

### Pattern: ComfyUI Completion Polling
```python
def _wait_for_completion(self, prompt_id, timeout=3600):
    hist_url = f"{COMFYUI_URL}/history/{prompt_id}"
    while time.time() - start_time < timeout:
        resp = requests.get(hist_url, timeout=10)
        if resp.ok:
            data = resp.json()
            if prompt_id in data:  # Complete!
                return data[prompt_id]
        time.sleep(5)
    return None
```

---

## Summary

This session focused on **bug fixes** rather than feature development. The video tab module was created in the previous session, and this session fixed 4 critical bugs:

| # | Bug | Severity | Status |
|---|-----|----------|--------|
| 1 | Grid layout overlap (Sec/Width fields) | High | Fixed |
| 2 | Video height uses width value | High | Fixed |
| 3 | LTX task missing main_sex_act | Medium | Fixed |
| 4 | Wrong ComfyUI API payload/URL | High | Fixed |

**Overall Status:** Code is syntactically valid and ready for integration testing with ComfyUI server.
