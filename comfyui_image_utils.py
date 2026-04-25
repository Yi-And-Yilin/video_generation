"""
ComfyUI Image Download Utility

Provides functions to download generated images from a remote ComfyUI server
using the /view API endpoint. This is necessary because ComfyUI generates
images on its server machine, and the client needs to download them over HTTP.

Key endpoints used:
- GET /history/{prompt_id} - Get execution results with image metadata
- GET /view?filename=...&subfolder=...&type=... - Download actual image bytes
- ws:///{clientId} - WebSocket for real-time execution completion detection

Author: Video Generation System
"""

import os
import urllib.request
import urllib.parse
import json
import io
import logging

logger = logging.getLogger(__name__)


def get_view_url(server_address: str, filename: str, subfolder: str = "",
                 folder_type: str = "output") -> str:
    """
    Build the full URL for ComfyUI's /view endpoint.

    Parameters
    ----------
    server_address : str
        ComfyUI server address (e.g., "192.168.4.22:8188" or "127.0.0.1:8188")
    filename : str
        The filename returned in ComfyUI history (e.g., "somefile.png")
    subfolder : str
        Optional subfolder within the output directory
    folder_type : str
        Type of folder: "output", "input", "queued", etc.

    Returns
    -------
    str
        Full URL to download the image via /view endpoint
    """
    params = urllib.parse.urlencode({
        "filename": filename,
        "subfolder": subfolder,
        "type": folder_type
    })
    return f"http://{server_address}/view?{params}"


def download_image_from_comfyui(server_address: str, filename: str,
                                 subfolder: str = "",
                                 folder_type: str = "output",
                                 timeout: int = 60) -> bytes:
    """
    Download an image file from ComfyUI's /view endpoint.

    This is the primary function for retrieving generated images from
    a remote ComfyUI server.

    Parameters
    ----------
    server_address : str
        ComfyUI server address (e.g., "192.168.4.22:8188")
    filename : str
        The filename from ComfyUI history output
    subfolder : str
        Optional subfolder within the output directory (may be empty)
    folder_type : str
        Type of folder: "output", "input", "queued" (default "output")
    timeout : int
        Request timeout in seconds

    Returns
    -------
    bytes
        Raw image data (PNG/JPG bytes)

    Raises
    ------
    urllib.error.URLError
        If the image cannot be downloaded from the ComfyUI server
    """
    url = get_view_url(server_address, filename, subfolder, folder_type)
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.read()
    except Exception as e:
        logger.error(f"Failed to download image from ComfyUI: {url} - {e}")
        raise


def download_image_from_history(comfyui_url: str, history_entry: dict,
                                 output_subdir: str = "") -> list:
    """
    Download all images from a ComfyUI history entry and save locally.

    Parameters
    ----------
    comfyui_url : str
        Base ComfyUI URL (e.g., "http://192.168.4.22:8188")
    history_entry : dict
        The history data for a single prompt_id (from /history/{prompt_id})
    output_subdir : str
        Optional subdirectory within the output folder for saving

    Returns
    -------
    list[str]
        List of local file paths where images were saved
    """
    # Extract server address from URL (strip protocol and path)
    # e.g., "http://192.168.4.22:8188/prompt" -> "192.168.4.22:8188"
    server_address = comfyui_url.split("//")[1].split("/")[0]

    output_dir = output_subdir or ""
    saved_paths = []

    try:
        outputs = history_entry.get("outputs", {})
        for node_id, node_output in outputs.items():
            if "images" not in node_output:
                continue

            for img_info in node_output["images"]:
                filename = img_info.get("filename", "")
                subfolder = img_info.get("subfolder", "")
                folder_type = img_info.get("type", "output")

                if not filename:
                    continue

                try:
                    image_data = download_image_from_comfyui(
                        server_address, filename, subfolder, folder_type
                    )

                    if image_data:
                        saved_path = os.path.join(
                            "output_images", output_dir,
                            f"{filename}"
                        )
                        os.makedirs(os.path.dirname(saved_path), exist_ok=True)
                        with open(saved_path, "wb") as f:
                            f.write(image_data)
                        saved_paths.append(saved_path)
                        logger.info(f"Downloaded image: {filename} -> {saved_path}")

                except Exception as e:
                    logger.warning(
                        f"Failed to download image {filename}: {e}"
                    )

    except Exception as e:
        logger.error(f"Error downloading images from history: {e}")

    return saved_paths


def wait_for_execution(comfyui_url: str, prompt_id: str, cancel_event=None,
                        timeout: int = 1800) -> dict:
    """
    Wait for a ComfyUI workflow to complete using WebSocket + HTTP polling.

    This function provides the most reliable way to detect when ComfyUI
    has finished executing a prompt. It uses:
    1. WebSocket to listen for the 'executing' message with node=None
    2. HTTP polling as a fallback if WebSocket is unavailable

    Parameters
    ----------
    comfyui_url : str
        Base ComfyUI URL (e.g., "http://192.168.4.22:8188/prompt")
    prompt_id : str
        The prompt_id returned from sending the workflow to /prompt
    cancel_event : threading.Event or None
        If set, this function will return None (indicating cancellation)
    timeout : int
        Maximum wait time in seconds (default 1800 = 30 minutes)

    Returns
    -------
    dict or None
        The history entry for this prompt_id, or None on timeout/cancellation
    """
    import time
    import requests

    # Extract server address and client_id
    base_url = comfyui_url.split("/prompt")[0] if "/prompt" in comfyui_url else comfyui_url
    server_address = base_url.split("//")[1]
    client_id = str(prompt_id)  # Use prompt_id as client identifier

    def try_websocket():
        """Try to use WebSocket for completion detection."""
        try:
            import websocket as ws_module
            ws_url = f"ws://{server_address}/ws?clientId={client_id}"
            ws = ws_module.WebSocket()
            ws.settimeout(10)
            ws.connect(ws_url)

            start_time = time.time()
            while True:
                if cancel_event and cancel_event.is_set():
                    ws.close()
                    return None

                if time.time() - start_time > timeout:
                    ws.close()
                    return None

                try:
                    out = ws.recv()
                except Exception:
                    # Timeout or connection lost, keep trying
                    continue

                if isinstance(out, str):
                    message = json.loads(out)
                    if message.get('type') == 'executing':
                        data = message.get('data', {})
                        if (data.get('node') is None and
                            data.get('prompt_id') == prompt_id):
                            ws.close()
                            return True  # Done
                # Binary data (preview images) or other messages - ignore

        except ImportError:
            return None  # websocket module not available
        except Exception as e:
            return None  # WebSocket failed, fall back to HTTP polling

    def try_http_polling():
        """Fall back to HTTP polling of /history endpoint."""
        hist_url = f"{base_url}/history/{prompt_id}"
        start_time = time.time()

        while True:
            if cancel_event and cancel_event.is_set():
                return None

            if time.time() - start_time > timeout:
                return None

            try:
                resp = requests.get(hist_url, timeout=10)
                if resp.ok:
                    data = resp.json()
                    if prompt_id in data:
                        return data[prompt_id]
            except Exception:
                pass

            time.sleep(5)

    # Try WebSocket first, fall back to HTTP polling
    ws_result = try_websocket()

    if ws_result is True:
        # WebSocket detected completion, now fetch history via HTTP
        base_url = comfyui_url.split("/prompt")[0] if "/prompt" in comfyui_url else comfyui_url
        prompt_id_str = str(prompt_id)
        hist_url = f"{base_url}/history/{prompt_id_str}"
        try:
            resp = requests.get(hist_url, timeout=10)
            if resp.ok:
                return resp.json().get(prompt_id_str)
        except Exception as e:
            logger.error(f"Failed to fetch history after WebSocket completion: {e}")
        # If we got here but no history found, fall through to polling

    # Fall back to HTTP polling
    return try_http_polling()
