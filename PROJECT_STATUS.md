# Project Status: NSFW UI & LLM Utils Integration

## 1. LLM Utils (`llm_utils.py`)
- **Status:** Fully Functional.
- **Features:** 
    - `LLMUtils.stream(...)` connects to local Ollama (`huihui_ai/qwen3.5-abliterated:9b`).
    - Supports `thinking=True` (handles both `thought` and `thinking` fields from Ollama).
    - **Self-Correction Loop:** 5-retry validation loop. If JSON/Schema validation fails, it appends the error to the chat history and asks the AI to fix it.
    - **Validation:** Basic manual schema validator (handles types and required fields).

## 2. UI Updates (`nsfw_ui.py`)
- **LTX Tab:** Now the default tab.
- **Controls:** Reorganized into two rows for better visibility.
- **New Fields:** 
    - Resolution (Dropdown with 1344*768 added).
    - SEC (default 10) & FPS (default 24).
    - Language (Chinese/English).
    - Img Model (Populated from `projects/ltx/workflow/image/*.json`).
    - Batch Size (default 1).
- **Clear Button:** Resets local `process.json` and `task.json`.
- **User Instruction:** Large text box for custom prompts.
- **Task Generation:** Combines UI parameters and AI response into a structured `task.json`.
- **Incremental Logging:** Added `StreamChunk` and `ltx_stream_log` to allow real-time display of AI thoughts/content without vertical spacing issues.

## 3. Prompts & Data
- `projects/ltx/prompts/general.json`: Updated to a **List** format to satisfy Ollama's Tool API requirements.
- `projects/ltx/prompts/general.md` & `user_prompt.md`: Used as system/user templates.

## 4. Current Bug / Next Steps
- **Issue:** The UI hangs/freezes during generation after the "Thinking" block finishes. 
- **Cause:** Likely Tkinter overloading. The `process_log_queue` loops through chunks too fast, and calling `.see(tk.END)` on every tiny character chunk is expensive.
- **Proposed Fix:** 
    1.  Buffer chunks in the background thread and only send them to the UI queue every 100-200ms.
    2.  Or, in the UI thread, limit the number of updates per `after()` tick.
