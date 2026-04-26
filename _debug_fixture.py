import sys
import time
import tkinter as tk

print("Step 1: Creating tk root...")
tk_root = tk.Tk()
tk_root.withdraw()
print("Step 2: Root created")

print("Step 3: Setting up mock main_ui...")
mock_mu = type('MockMu', (), {
    'COMFYUI_URL': 'http://127.0.0.1:8188/prompt',
    'COMFYUI_ROOT': r'C:\ComfyUI',
    'INPUT_FOLDER': r'C:\ComfyUI\input',
    'OUTPUT_FOLDER': r'C:\ComfyUI\output',
    'WORKFLOW_TEMPLATE_DIR': r'C:\templates',
    'LTX_WORKFLOW_DIR': r'C:\templates\ltx',
    'VIDEO_OUTPUT_FOLDER': r'C:\ComfyUI\output\video',
    'STATE_FILE': r'C:\state.json',
    'TASK_STEPS_CSV': r'C:\task_steps.csv',
    'AUDIO_PROMPT_TSV': r'C:\audio_prompt.tsv',
})

class MockTemplateCatalog:
    @staticmethod
    def get_checkpoint_options():
        return ["cp1", "cp2"]

mock_mu.StreamChunk = type('StreamChunk', (), {})
mock_mu.generate_api_workflow = lambda: None
mock_mu.TemplateCatalog = MockTemplateCatalog

print("Step 4: Patching sys.modules...")
orig_main_ui = sys.modules.get('main_ui')
sys.modules['main_ui'] = mock_mu

print("Step 5: Importing video_tab...")
import video_tab
print("Step 6: video_tab imported")

mock_notebook = type('MockNotebook', (), {'add': lambda self, *a, **k: None})()

print("Step 7: Creating VideoTabUI...")
tab = video_tab.VideoTabUI(mock_notebook, tk_root)
print("Step 8: VideoTabUI created")

print("Done!")
