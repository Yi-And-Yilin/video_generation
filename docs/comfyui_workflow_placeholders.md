# ComfyUI Workflow Template Placeholders Standard

This document defines the standard placeholder values used across all ComfyUI workflow templates in this project.

## Format Convention

Placeholders use the `**placeholder_name**` format (double asterisks wrapping the placeholder name).

## Standard Placeholders

### Prompt & Conditioning

| Placeholder | Description | Field Type | Example Usage |
|-------------|-------------|------------|---------------|
| `**video_pos_prompt**` | Positive prompt for video generation | String | Main descriptive prompt for video output |
| `**image_pos_prompt**` | Positive prompt for image generation | String | Main descriptive prompt for image output |
| `**video_neg_prompt**` | Negative prompt for video generation | String | Elements to exclude from video |
| `**image_neg_prompt**` | Negative prompt for image generation | String | Elements to exclude from image |
| `**audio_prompt**` | Audio description prompt | String | Audio/voice description for video |
| `**load_pos_conditioning**` | Load positive conditioning from file | String | Path to saved positive conditioning file |
| `**load_neg_conditioning**` | Load negative conditioning from file | String | Path to saved negative conditioning file |
| `**save_pos_conditioning**` | Save positive conditioning to file | String | Output path for positive conditioning |
| `**save_neg_conditioning**` | Save negative conditioning to file | String | Output path for negative conditioning |

### Latent & Image/Video I/O

| Placeholder | Description | Field Type | Example Usage |
|-------------|-------------|------------|---------------|
| `**load_latent**` | Load latent tensor from file | String | Path to saved latent file (.pt or .lat) |
| `**save_latent**` | Save latent tensor to file | String | Output path for latent tensor |
| `**load_image**` | Load input image | String | Path to input image file |
| `**save_image**` | Save generated image | String | Output path for generated image |

### Video Dimensions & Parameters

| Placeholder | Description | Field Type | Example Usage |
|-------------|-------------|------------|---------------|
| `**video_width**` | Video width in pixels | Integer | e.g., 1280, 1920 |
| `**video_height**` | Video height in pixels | Integer | e.g., 720, 1080 |
| `**video_length**` | Video length (frames) | Integer | Total frame count |
| `**video_seconds**` | Video duration in seconds | Integer/Float | e.g., 5, 10, 15 |
| `**fps**` | Frames per second | Integer | e.g., 24, 30, 60 |

## Usage Guidelines

### 1. Node Placement

Placeholders should be placed in the `inputs` section of workflow JSON nodes:

```json
{
  "node_id": {
    "inputs": {
      "prompt": "**video_pos_prompt**",
      "negative": "**video_neg_prompt**"
    },
    "class_type": "CLIPTextEncode"
  }
}
```

### 2. Type Conversion

When replacing placeholders, convert to appropriate types:
- **Integer fields** (e.g., `JWInteger`): Convert string to int
- **String fields**: Use as-is or with string substitution
- **Float fields**: Convert string to float when needed

### 3. File Paths

For file-related placeholders (`load_*`, `save_*`):
- Use relative paths from workflow directory
- Include job ID in paths for multi-job workflows
- Example: `latents/lat_{job_id}_s{step}.lat`

### 4. Naming Convention

- Use lowercase with underscores: `video_pos_prompt` (not `VideoPosPrompt`)
- Be descriptive: `load_pos_conditioning` (not `load_cond`)
- Include context: `video_width` (not just `width`)

## Workflow Integration Example

```python
# Read workflow JSON
with open("workflow.json") as f:
    workflow = json.load(f)

# Define replacement values
replacements = {
    "**video_pos_prompt**": "masterpiece, best quality",
    "**video_neg_prompt**": "blurry, low quality",
    "**video_width**": 1280,
    "**video_height**": 720,
    "**fps**": 24,
    "**video_seconds**": 10
}

# Apply replacements
for node_id, node in workflow.items():
    for key, value in node.get("inputs", {}).items():
        if isinstance(value, str):
            for placeholder, replacement in replacements.items():
                if placeholder in value:
                    # Convert type if needed
                    if node["class_type"] == "JWInteger":
                        node["inputs"][key] = int(replacement)
                    else:
                        node["inputs"][key] = value.replace(placeholder, str(replacement))
```

## Related Documentation

- See `main_workflow.md` for WAN 2.2 workflow details
- See `projects/ltx/README.md` for LTX workflow specifications
