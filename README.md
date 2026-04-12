# LLM Utils for Ollama

This utility provides a robust interface for interacting with a local Ollama instance, specifically optimized for the `huihui_ai/qwen3.5-abliterated:9b` model.

## Core Features

- **Streaming Support**: Direct streaming of model responses including "thinking" processes.
- **Automatic Validation**: Validates model output against a provided JSON schema or function definition.
- **Self-Correction Loop**: If the model output fails validation (invalid JSON or schema mismatch), the utility automatically maintains the chat history, adds the error message, and asks the model to correct itself.
- **Retry Logic**: Supports up to 5 retries before returning an error.
- **Context Management**: Default context window of 64k (`65536`).

## Files

- `llm_utils.py`: The core implementation of the `LLMUtils` class.
- `mock_schema.json`: An example function calling schema for image prompt generation.
- `test_validation.py`: A test script to verify the validation and retry logic.

## Usage Example

```python
from llm_utils import LLMUtils
import json

# Load a function definition schema
with open("mock_schema.json", "r") as f:
    schema = json.load(f)

prompt = "Generate a cyberpunk city prompt."

# Use the stream method
# It will automatically handle validation and retries internally
for chunk in LLMUtils.stream(
    prompt=prompt,
    model="huihui_ai/qwen3.5-abliterated:9b",
    thinking=True,
    context_window=65536,
    function_definition=schema
):
    print(chunk, end='', flush=True)
```

## Method Signature

```python
@staticmethod
def stream(
    prompt: str,
    model: str = "huihui_ai/qwen3.5-abliterated:9b",
    thinking: bool = True,
    context_window: int = 65536,
    json_response: bool = False,
    function_definition: Optional[List[Dict[str, Any]]] = None
) -> Generator[str, None, None]:
```

- `prompt`: The user instruction.
- `model`: The Ollama model name.
- `thinking`: If True, yields the `<thought>` process if available.
- `context_window`: Size of the `num_ctx` parameter.
- `json_response`: Forces the model to output valid JSON.
- `function_definition`: A list of tools/functions for the model to follow. Triggers the validation/retry loop.

---

# LTX Project

ComfyUI workflow automation for LTX model.

## Project Structure

```
projects/ltx/
├── workflow_generator.py    # Generate dynamic workflow JSON
├── latent_utils.py          # Latent file management utilities
├── batch_runner.py          # Batch execution engine
├── lora_lookup.csv          # LoRA lookup table by action tags
├── process.json             # Workflow progress tracking
├── ltx.log                  # Log file
├── prompts/                 # Prompt templates
└── workflow/
    ├── clean_up.json        # Cleanup workflow between phases
    ├── image/               # Image workflow templates
    │   └── pornmaster_proSDXLV8.json
    └── video/               # Video workflow templates
        ├── ltx_standard.json
        └── ltx_latent.json
```

## Output Folder Structure

```
ComfyUI/output/
├── {work_id}.png            # Generated images (Phase 1)
├── {work_id}.mp4            # Final videos (Phase 3)
├── latents/
│   └── {work_id}.latent     # Latent files (Phase 2)
└── processed/
    ├── {job_id}-1.txt       # Phase 1 completion indicator
    ├── {job_id}-2.txt       # Phase 2 completion indicator
    └── {job_id}-3.txt       # Phase 3 completion indicator
```

## Modules

### workflow_generator.py

Generate ComfyUI API workflow JSON dynamically.

```python
from workflow_generator import generate_api_workflow, save_workflow

workflow = generate_api_workflow(
    project="ltx",
    type="image",                    # "image" or "video"
    template="pornmaster_proSDXLV8",
    acts=["fingering"],
    width=1280,
    height=720,
    length=241,
    prompt="1girl, beautiful woman",
    negative_prompt="ugly, deformed, bad quality",
    work_id="abc123"                 # Used for output filename
)

save_workflow(workflow, "output.json")
```

#### Template Placeholders

Nodes with `_meta.title` starting with `**` are treated as input nodes:

| Placeholder | Node Title | Field Updated |
|-------------|------------|---------------|
| prompt | `**prompt` | `string` |
| negative_prompt | `**negative_prompt` | `string` |
| width | `**width` | `Number` |
| height | `**height` | `Number` |
| length | `**length` | `Number` |
| work_id | `**work_id` | `string` |

#### LoRA Chain Insertion

Nodes with `_meta.title` starting with `**lora` are anchor points for dynamic LoRA insertion.

- LoRAs are loaded from `lora_lookup.csv` based on action tags
- New LoRA nodes are created starting from ID 200
- LoRAs are chained: `input -> LoRA1 -> LoRA2 -> ... -> downstream`
- Anchor node is removed after insertion

### latent_utils.py

Utilities for managing latent files between ComfyUI output and input folders.

**Filename Patterns:**
| Phase | Output Location | Filename Pattern |
|-------|-----------------|------------------|
| Image | `{output}/` | `{work_id}.png` |
| Video Standard | `{output}/latents/` | `{work_id}.latent` |
| Video Latent | `{output}/` | `{work_id}.mp4` |

#### move_latents_to_input(work_id, ...)

Move latent file matching `work_id` from `output/latents` to `input` folder.

```python
from latent_utils import move_latents_to_input

result = move_latents_to_input(
    work_id="abc123",
    log_func=print  # Optional logging function
)

# Returns: {'moved': ['abc123.latent'], 'errors': []}
```

Use this after video standard step to prepare latent files for latent decode step.

#### delete_consumed_latents(work_id, ...)

Delete latent files matching `work_id` from both `output/latents` and `input` folders.

```python
from latent_utils import delete_consumed_latents

result = delete_consumed_latents(
    work_id="abc123",
    log_func=print
)

# Returns: {'deleted': ['abc123.latent'], 'errors': []}
```

Use this after the final latent decode step to clean up consumed latent files.

#### delete_image_files(work_id, ...)

Delete image file from output folder after video generation step.

```python
from latent_utils import delete_image_files

result = delete_image_files(
    work_id="abc123",
    log_func=print
)

# Returns: {'deleted': ['abc123.png'], 'errors': []}
```

Use this after video standard step to clean up the source image.

#### get_latent_files(work_id, ...)

List latent files, optionally filtered by `work_id`.

```python
from latent_utils import get_latent_files

# Get all latent files
all_files = get_latent_files()

# Get files matching work_id
files = get_latent_files("abc123")

# Returns: [{'path': '...', 'filename': '...', 'folder': '...'}, ...]
```

### batch_runner.py

Batch runner for executing the full image -> video -> latent pipeline.

#### ID Hierarchy

- **job_id**: Major ID for the whole job (e.g., `job_20260327_001`)
- **work_id**: Sub-work ID under the job (e.g., `video001`, `video002`)

#### Execution Flow

```
Phase 1: IMAGE GENERATION (step 1)
├── For each task: generate workflow -> send to ComfyUI
├── Run cleanup workflow -> creates {job_id}-1.txt
└── Wait for cleanup completion

Phase 2: VIDEO GENERATION (step 2)
├── For each task: generate workflow -> send to ComfyUI
├── Wait for all latents complete
├── Delete image files from output/
├── move_latents_to_input(work_id) for each task
├── Run cleanup workflow -> creates {job_id}-2.txt
└── Wait for cleanup completion

Phase 3: LATENT DECODE (step 3)
├── For each task: generate workflow -> send to ComfyUI
├── delete_consumed_latents(work_id) for each task
├── Run cleanup workflow -> creates {job_id}-3.txt
└── Wait for cleanup completion
```

#### Completion Indicator Files

Each phase creates an indicator file in `{output}/processed/`:
- `{job_id}-1.txt` - Phase 1 (Image) complete
- `{job_id}-2.txt` - Phase 2 (Video) complete
- `{job_id}-3.txt` - Phase 3 (Latent) complete

#### Usage

```python
from batch_runner import BatchRunner

# Define tasks
tasks = [
    {
        "work_id": "video001",
        "main_sex_act": "fingering",
        "prompt": "1girl, beautiful woman, nude",
        "negative_prompt": "ugly, deformed, bad quality"
    },
    {
        "work_id": "video002",
        "main_sex_act": "kiss",
        "prompt": "1girl, beautiful woman, kissing",
        "negative_prompt": "ugly, deformed, bad quality"
    }
]

# Create runner
runner = BatchRunner()

# Run batch with job_id
result = runner.run_batch(
    job_id="job_20260327_001",  # Major job ID
    tasks=tasks,
    width=1280,
    height=720,
    length=241,
    image_model="pornmaster_proSDXLV8"
)

# result = {
#     'job_id': 'job_20260327_001',
#     'completed': ['video001', 'video002'],
#     'failed': [],
#     'errors': []
# }

# Or run in background thread
import threading

def run():
    result = runner.run_batch(job_id="job_20260327_001", tasks=tasks)
    print("Done:", result)

thread = threading.Thread(target=run, daemon=True)
thread.start()

# Cancel if needed
runner.cancel()

# Check if a step is completed
if runner.check_step_completed("job_20260327_001", step_number=1):
    print("Phase 1 is done, can resume from Phase 2")
```

### clean_up.json

Cleanup workflow that runs between each phase to free GPU memory.

- Cleans file cache, processes, and DLLs
- Cleans VRAM used by models
- Creates completion indicator file: `{output}/processed/{job_id}-{step}.txt`

### lora_lookup.csv

Maps action tags to LoRA configurations.

```csv
tag1,tag2,workflow name,lora1_name,lora1_strength,lora2_name,lora2_strength,...
fingering,,pornmaster_proSDXLV8,xl\fingering_illustrious_V1.0.safetensors,0.8,xl\fingering-kabedon.safetensors,0.6,...
missionary,kiss,pornmaster_proSDXLV8,xl\standing_missionary.safetensors,0.9,xl\frenchkiss.safetensors,0.65,...
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `COMFYUI_ROOT` | `D:\ComfyUI_windows_portable\ComfyUI` | ComfyUI installation path |
| `OUTPUT_FOLDER` | `{COMFYUI_ROOT}/output` | ComfyUI output folder |
| `INPUT_FOLDER` | `{COMFYUI_ROOT}/input` | ComfyUI input folder |
| `COMFYUI_URL` | `http://192.168.4.63:8188/prompt` | ComfyUI API URL |
