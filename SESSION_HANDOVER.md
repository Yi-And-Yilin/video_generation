# Session Handover - NSFW UI & LLM Utils

## Recent Improvements (March 26, 2026)

### 1. UI Performance & Stability (`nsfw_ui.py`)
- **Buffered Logging:** Refactored log queue processing in both Main and LTX tabs. Chunks are now buffered and flushed every 100ms, with a limit of 1000 items per tick. This prevents Tkinter from freezing during high-frequency updates from the AI's "Thinking" blocks.
- **Log Size Management:** Added a 2000-line cap to UI log windows. Older entries are automatically trimmed to maintain responsiveness over long sessions.
- **Instruction Box Bugfix:** Renamed `user_instruction_box` to `wan_instruction_box` and `ltx_instruction_box` respectively to prevent attribute overwriting when switching tabs.
- **Clean Task Data:** Updated the LTX workflow thread to explicitly extract the "Formal Answer" section from the LLM stream, ensuring that internal reasoning markers no longer pollute the `task.json` file.

### 2. LLM Interaction & Validation (`llm_utils.py`)
- **Visual Delineation:** The `stream` method now yields `Thinking:` and `Formal Answer:` markers, making the real-time output in the UI much easier to follow.
- **Auto-Fixing Validator:** Enhanced `validate_schema` to detect and fix common LLM mistakes where JSON arrays or objects are returned as stringified values (e.g., `'[{"key": "val"}]'`). It now strips surrounding quotes and **removes internal newlines** from these candidate strings, ensuring they parse correctly even if the LLM adds unwanted line breaks.
- **Robust Accumulation:** Separated internal reasoning from the formal content accumulator in the streaming loop. The UI now more reliably extracts only the content after the `Formal Answer:` marker, stripping extra whitespace and marker text.
- **GPU Resource Management:** Added `keep_alive` parameter to `LLMUtils.stream`. In batch jobs (LTX tab), the model now stays loaded (using a 5-minute timeout) between individual steps and **unloads immediately (`keep_alive=0`) only after the final step** or if the process is cancelled/errored. This balances speed for batch processing with VRAM efficiency for ComfyUI.

## Next Steps
- **ComfyUI Integration Testing:** Verify that the "Formal Answer" extraction in `nsfw_ui.py` correctly handles all edge cases (e.g., multiple tool calls or empty formal answers).
- **WAN Instruction Integration:** Currently, the `wan_instruction_box` is defined but not yet used in the WAN workflow thread (unlike the LTX tab). Decide if this feature should be implemented for WAN tasks.
- **Error Handling:** Add more granular error messages for specific validation failures in the UI log.
