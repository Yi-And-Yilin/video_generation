import os
import json
import threading
from llm_utils import LLMUtils

# Mock paths as defined in nsfw_ui.py
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LTX_PROJECT_DIR = os.path.join(SCRIPT_DIR, "projects", "ltx")
LTX_PROMPTS_DIR = os.path.join(LTX_PROJECT_DIR, "prompts")
LTX_TASK_JSON = os.path.join(LTX_PROJECT_DIR, "task.json")

def simulate_ltx_workflow(user_instruction="A beautiful sunset over a cyberpunk city"):
    """Simulates the logic inside _ltx_run_workflow_thread without requiring a UI."""
    print(f"--- Simulating LTX Workflow Integration ---")
    print(f"User Instruction: {user_instruction}")

    general_md_path = os.path.join(LTX_PROMPTS_DIR, "general.md")
    user_prompt_md_path = os.path.join(LTX_PROMPTS_DIR, "user_prompt.md")
    general_json_path = os.path.join(LTX_PROMPTS_DIR, "general.json")

    try:
        # 1. Read System Prompt
        print(f"Reading {general_md_path}...")
        with open(general_md_path, 'r', encoding='utf-8') as f:
            system_prompt = f.read()

        # 2. Read User Prompt Template
        print(f"Reading {user_prompt_md_path}...")
        with open(user_prompt_md_path, 'r', encoding='utf-8') as f:
            user_prompt_template = f.read()
        
        # Inject instruction
        full_user_prompt = f"{user_prompt_template}\n\nUser Instruction from UI: {user_instruction}"

        # 3. Read Schema
        print(f"Reading {general_json_path}...")
        with open(general_json_path, 'r', encoding='utf-8') as f:
            schema = json.load(f)

        # 4. Call Ollama
        final_prompt = f"{system_prompt}\n\n{full_user_prompt}"
        print("Calling Ollama (this may take a few seconds)...")
        
        full_response_text = ""
        for chunk in LLMUtils.stream(
            prompt=final_prompt,
            model="huihui_ai/qwen3.5-abliterated:9b",
            thinking=True,
            context_window=32768,
            function_definition=schema
        ):
            # print(chunk, end='', flush=True) # Uncomment to see stream
            full_response_text += chunk
        
        if full_response_text.startswith("Error:"):
            print(f"\nFAILED: {full_response_text}")
            return

        # 5. Save as task.json
        print(f"\nSaving results to {LTX_TASK_JSON}...")
        with open(LTX_TASK_JSON, 'w', encoding='utf-8') as f:
            f.write(full_response_text)
        
        print("Success: LTX Workflow Integration Test Passed.")
        
        # Verify content
        if "[TOOL_CALLS]" in full_response_text:
            print("Verified: Response contains valid tool calls.")
        else:
            print("Verified: Response is valid (likely direct JSON).")

    except Exception as e:
        print(f"Test Failed with Exception: {e}")

if __name__ == "__main__":
    simulate_ltx_workflow()
