import requests
import json
import uuid
import random
import os
import sys

# Ensure projects/ltx is in path for workflow_generator
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "projects", "ltx"))
from workflow_generator import generate_api_workflow

def comfyui(prompt: str) -> str:
    # Use the unified WAN-style image generation process
    workflow_dict = generate_api_workflow(
        project="wan",
        type="image",
        template="wan_image",
        prompt=prompt,
        width=1024,
        height=1024
    )
    
    # Generate unique prompt_id
    prompt_id = str(uuid.uuid4())
    
    # Build the payload
    payload = {
        "prompt": workflow_dict,
        "prompt_id": prompt_id
    }
    
    # Send to ComfyUI (Using standard URL from project)
    comfyui_url = "http://192.168.4.22:8188/prompt"
    try:
        response = requests.post(comfyui_url, json=payload, timeout=60)
        if response.ok:
            print("Task queued successfully.")
            return prompt_id
        else:
            print(f"Failed to queue task. Status: {response.status_code}")
    except Exception as e:
        print(f"Error connecting to ComfyUI: {e}")
    return None

if __name__ == "__main__":
    if len(sys.argv) > 1:
        comfyui(" ".join(sys.argv[1:]))
    else:
        comfyui("A beautiful cinematic shot of a sunset over the mountains")
