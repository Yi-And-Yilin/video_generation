# ComfyUI API Integration Guide

This document describes how the Video Generation application communicates with ComfyUI servers, including image generation workflows, response handling, and image downloading.

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Core API Endpoints](#core-api-endpoints)
- [Image Downloading via /view Endpoint](#image-downloading-via-view-endpoint)
- [WebSocket Completion Detection](#websocket-completion-detection)
- [Key Components](#key-components)
- [Troubleshooting](#troubleshooting)

---

## Overview

ComfyUI is an asynchronous, node-based image/video generation system. Unlike a standard REST API where you send a request and wait for the result, ComfyUI:

1. **Accepts workflows** and immediately returns a `prompt_id`
2. **Processes asynchronously** on the GPU in the background
3. **Stores results** in its output directory
4. **Sends completion signals** via WebSocket or HTTP polling

This document covers how the application handles this asynchronous architecture.

---

## Architecture

### Two-Layer Communication Model

```
┌─────────────────┐         ┌───────────────────────┐         ┌──────────────┐
│   Application    │         │   ComfyUI Server      │         │  GPU/Storage │
│   (main_ui.py)  │────────>│   (192.168.4.22:8188) │────────>│              │
│                 │<────────│                       │<────────│              │
└─────────────────┘         └───────────────────────┘         └──────────────┘
         │                          │                               │
         │  1. POST /prompt         │                               │
         │     (send workflow)      │                               │
         │─────────────────────────>│                               │
         │                          │  Queue workflow, start GPU   │
         │  2. GET /view?           │                               │
         │     (download image)     │                               │
         │<─────────────────────────│──────────────────────────────>│
         │                          │  Write image to output/      │
         │                          │                               │
         │  3. ws:// (optional)     │                               │
         │     (completion signal)  │                               │
         │<─────────────────────────│                               │
         │                          │  Send 'executing' when done  │
         ───────────────────────────────────────────────────────────
```

### Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| Use `/view` API instead of local filesystem | ComfyUI runs on a remote server (192.168.4.22); local paths don't exist on client machine |
| WebSocket with HTTP polling fallback | WebSocket provides real-time detection; HTTP polling is a reliable fallback if WebSocket fails |
| Download image bytes vs. copy files | Downloading via HTTP works across network boundaries; copying files would require shared filesystem |

---

## Core API Endpoints

### 1. POST `/prompt` — Submit Workflow

```http
POST /prompt HTTP/1.1
Host: 192.168.4.22:8188
Content-Type: application/json

{
  "prompt": { ... },       // Workflow JSON (from workflow templates)
  "prompt_id": "uuid-here",
  "client_id": "optional-uuid"
}
```

**Response** (200 OK):
```json
{
  "prompt_id": "uuid-here",
  "number": 0,
  "node_errors": {}
}
```

**Used in**:
- `main_ui.py::send_workflow_to_comfyui()`
- `projects/ltx/batch_runner.py::send_workflow_to_comfyui()`

---

### 2. GET `/history/{prompt_id}` — Fetch Results

```http
GET /history/{prompt_id} HTTP/1.1
Host: 192.168.4.22:8188
```

**Response** (200 OK):
```json
{
  "{prompt_id}": {
    "status": {
      "status_str": "success",
      "percent": 1,
      "messages": [],
      "current_work": [0, 0],
      "last_work_id": "node123",
      "completed": true,
      "message": "",
      "workers": 0
    },
    "outputs": {
      "10": {
        "images": [
          {
            "filename": "test_output.png",
            "subfolder": "",
            "type": "output"
          }
        ]
      }
    }
  }
}
```

**Used in**:
- `main_ui.py::wait_for_completion()` — polls for completion
- `comfyui_image_utils.py::wait_for_execution()` — fetches final results
- `projects/ltx/batch_runner.py::poll_for_step_completion()`

---

### 3. GET `/view?filename=...&subfolder=...&type=...` — Download Image

```http
GET /view?filename=test_output.png&subfolder=&type=output HTTP/1.1
Host: 192.168.4.22:8188
```

**Response** (200 OK):
```
PNG binary data (or JPEG)
```

**This is the critical endpoint for fixing the "image not appearing locally" issue.**

Previously, the code tried to read the image from a local filesystem path:
```python
# OLD (BROKEN):
image_path = os.path.join(COMFYUI_ROOT, "output", subfolder, filename)
img = PILImage.open(image_path)  # Fails! File doesn't exist locally.
```

Now, the code downloads via HTTP:
```python
# NEW (FIXED):
image_data = download_image_from_comfyui(
    server_address="192.168.4.22:8188",
    filename="test_output.png",
    subfolder="",
    folder_type="output"
)
img = PILImage.open(io.BytesIO(image_data))  # Works! Bytes from HTTP.
```

**Used in**:
- `comfyui_image_utils.py::download_image_from_comfyui()`
- `main_ui.py::new_tab_run_comfyui()` → `_discover_and_save_image_with_metadata()`

---

## Image Downloading via /view Endpoint

### Why Local Filesystem Approach Failed

When ComfyUI runs on a **remote machine** (e.g., 192.168.4.22), images are saved to that machine's disk. The application running on the client machine (192.168.4.x) **cannot access** the remote filesystem directly.

**Old approach** (broken):
```python
# Attempting to read from REMOTE machine's local path:
image_path = os.path.join(COMFYUI_ROOT, "output", subfolder, filename)
# COMFYUI_ROOT = r"D:\ComfyUI_windows_portable\ComfyUI"  ← WRONG! This is the client's path.
```

**New approach** (fixed):
```python
# Download from ComfyUI's /view HTTP endpoint:
server_address = "192.168.4.22:8188"
image_data = download_image_from_comfyui(server_address, filename, subfolder)
```

### How /view Endpoint Works

The `/view` endpoint is ComfyUI's built-in file serving mechanism:
- Accepts `filename`, `subfolder`, and `type` (output/input/queued) parameters
- Streams the raw file bytes back to the client
- Handles MIME type detection automatically

Example URL:
```
http://192.168.4.22:8188/view?filename=somefile.png&subfolder=subdir&type=output
```

### Implementation Details

```python
def download_image_from_comfyui(server_address: str, filename: str,
                                 subfolder: str = "",
                                 folder_type: str = "output",
                                 timeout: int = 60) -> bytes:
    """Download an image file from ComfyUI's /view endpoint."""
    url = get_view_url(server_address, filename, subfolder, folder_type)
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read()
```

---

## WebSocket Completion Detection

### How WebSocket Detection Works

ComfyUI broadcasts events via WebSocket to all connected clients:
```
ws://192.168.4.22:8188/ws?clientId={client_id}
```

**Event types**:
| Event Type | Meaning |
|------------|---------|
| `"status"` | Current queue status |
| `"progress"` | Current progress of active prompt |
| `"executing"` | Node execution started/completed |
| `"executing"` with `node: null` | **All nodes done — workflow complete!** |

### WebSocket Completion Detection Flow

```
1. Application connects to ws://server/ws?clientId={prompt_id}
2. Sends workflow to POST /prompt → gets prompt_id
3. Listens for events:
   - "executing": data.node = node_id  → still working
   - "executing": data.node = null     → ALL DONE!
4. Fetches history via GET /history/{prompt_id}
```

### Fallback to HTTP Polling

If WebSocket is unavailable (e.g., firewall, network issue), fall back to HTTP polling:
```python
while True:
    resp = requests.get(f"http://server/history/{prompt_id}", timeout=10)
    if prompt_id in resp.json():
        return resp.json()[prompt_id]  # Found! Done.
    time.sleep(5)  # Wait before retry
```

### Implementation

```python
def wait_for_execution(comfyui_url: str, prompt_id: str,
                        cancel_event=None, timeout: int = 1800) -> dict:
    """Wait for a ComfyUI workflow to complete using WebSocket + HTTP polling."""
    # Try WebSocket first
    ws_result = try_websocket()
    
    if ws_result is True:
        # WebSocket detected completion, now fetch history via HTTP
        hist_url = f"{base_url}/history/{prompt_id}"
        resp = requests.get(hist_url, timeout=10)
        return resp.json().get(prompt_id)
    
    # Fall back to HTTP polling
    return try_http_polling()
```

---

## Key Components

### `comfyui_image_utils.py` — New Utility Module

**Location**: `C:\SimpleAIHelper\video_generation\comfyui_image_utils.py`

**Exports**:
| Function | Purpose |
|----------|---------|
| `get_view_url()` | Builds `/view` endpoint URL from parameters |
| `download_image_from_comfyui()` | Downloads image bytes from `/view` endpoint |
| `download_image_from_history()` | Downloads all images from a history entry |
| `wait_for_execution()` | Waits for workflow completion via WebSocket+HTTP |

### `main_ui.py` — Modified Methods

| Method | Change |
|--------|--------|
| `_discover_and_save_image_with_metadata()` | Now downloads images via `/view` API instead of reading local filesystem |
| `wait_for_completion()` | Now delegates to `wait_for_execution()` from `comfyui_image_utils` |

### Import Statement

```python
from comfyui_image_utils import download_image_from_comfyui, wait_for_execution
```

---

## Troubleshooting

### Problem: Images not appearing in `output_images` folder

**Cause**: The old code tried to read images from the local filesystem, but ComfyUI generates them on a **remote** server.

**Solution**: The fix uses the `/view` HTTP endpoint to download images over the network.

**Verify**:
```python
# Check if the /view endpoint works manually:
import urllib.request
url = "http://192.168.4.22:8188/view?filename=test.png&type=output"
resp = urllib.request.urlopen(url)
print(resp.read()[:100])  # Should show PNG/JPEG header bytes
```

### Problem: Images taking too long to appear

**Cause**: WebSocket connection might fail, falling back to HTTP polling.

**Solution**: Ensure WebSocket is allowed through firewalls. The `/ws` endpoint uses the same port as HTTP (8188).

**Verify**:
```python
# Test WebSocket connectivity:
import websocket
ws = websocket.WebSocket()
ws.connect("ws://192.168.4.22:8188/ws?clientId=test")
print(ws.recv())  # Should return JSON event data
```

### Problem: `urllib.error.URLError: <urlopen error [Errno 11001]>`

**Cause**: Can't reach the ComfyUI server address.

**Solution**:
1. Verify the ComfyUI server is running: `curl http://192.168.4.22:8188/`
2. Check firewall rules allow port 8188
3. Verify `COMFYUI_URL` environment variable points to the correct address

### Problem: Images saved without metadata

**Cause**: PIL failed to inject metadata, or the image format doesn't support PNG metadata.

**Solution**:
1. Ensure images are PNG (JPG metadata requires PiEXIF or pi-metadata library)
2. Check the `pnginfo` parameter format: `pnginfo=(("prompt", metadata_str),)`

---

## Configuration

### Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `COMFYUI_URL` | `http://192.168.4.22:8188/prompt` | ComfyUI server address |
| `COMFYUI_ROOT` | `D:\ComfyUI_windows_portable\ComfyUI` | ComfyUI installation root (for reference only) |

### ComfyUI Settings

For WebSocket support, ensure ComfyUI has **Dev Mode** enabled:
1. Open ComfyUI web interface
2. Click Settings (gear icon)
3. Enable **Dev Mode**
4. Save settings

This enables the "Save (API Format)" option, which is required for workflow generation.

---

## Testing

### Unit Tests

Run the image download utility tests:
```bash
python -m pytest tests/test_comfyui_image_utils.py -v
```

Tests verify:
- `/view` URL construction
- Image downloading logic
- WebSocket/HTTP polling URL construction
- Metadata extraction from history

### Manual Testing

1. Start ComfyUI on remote server (192.168.4.22)
2. Load a workflow, click "Queue Prompt"
3. In the application, go to New tab → run workflow → Run ComfyUI
4. Check `output_images/` folder for saved images

---

*Document last updated: 2026-04-25*
