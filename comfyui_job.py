import requests
import json
import uuid
import random

def comfyui(prompt: str) -> str:
    workflow = r'''
    {
      "3": {
        "inputs": {
          "seed": {seed},
          "steps": 20,
          "cfg": 6.5,
          "sampler_name": "euler",
          "scheduler": "exponential",
          "denoise": 1,
          "model": [
            "4",
            0
          ],
          "positive": [
            "30",
            0
          ],
          "negative": [
            "33",
            0
          ],
          "latent_image": [
            "5",
            0
          ]
        },
        "class_type": "KSampler",
        "_meta": {
          "title": "KSampler"
        }
      },
      "4": {
        "inputs": {
          "ckpt_name": "xl\\meichiILIghtMIXV1_meichiILUstMIXV1.safetensors"
        },
        "class_type": "CheckpointLoaderSimple",
        "_meta": {
          "title": "Load Checkpoint"
        }
      },
      "5": {
        "inputs": {
          "width": 1024,
          "height": 1024,
          "batch_size": 1
        },
        "class_type": "EmptyLatentImage",
        "_meta": {
          "title": "Empty Latent Image"
        }
      },
      "8": {
        "inputs": {
          "samples": [
            "3",
            0
          ],
          "vae": [
            "4",
            2
          ]
        },
        "class_type": "VAEDecode",
        "_meta": {
          "title": "VAE Decode"
        }
      },
      "28": {
        "inputs": {
          "filename_prefix": "ComfyUI",
          "images": [
            "8",
            0
          ]
        },
        "class_type": "SaveImage",
        "_meta": {
          "title": "Save Image"
        }
      },
      "30": {
        "inputs": {
          "width": 4096,
          "height": 4096,
          "crop_w": 0,
          "crop_h": 0,
          "target_width": 4096,
          "target_height": 4096,
          "text_g": "{pormpt}",
          "text_l": "{pormpt}",
          "speak_and_recognation": {
            "__value__": [
              false,
              true
            ]
          },
          "clip": [
            "4",
            1
          ]
        },
        "class_type": "CLIPTextEncodeSDXL",
        "_meta": {
          "title": "CLIPTextEncodeSDXL"
        }
      },
      "33": {
        "inputs": {
          "width": 4096,
          "height": 4096,
          "crop_w": 0,
          "crop_h": 0,
          "target_width": 4096,
          "target_height": 4096,
          "text_g": "blurry, animation, 3d render, illustration, toy, puppet, claymation, low quality, flag, nasa, mission patch",
          "text_l": "blurry, animation, 3d render, illustration, toy, puppet, claymation, low quality, flag, nasa, mission patch",
          "speak_and_recognation": {
            "__value__": [
              false,
              true
            ]
          },
          "clip": [
            "4",
            1
          ]
        },
        "class_type": "CLIPTextEncodeSDXL",
        "_meta": {
          "title": "CLIPTextEncodeSDXL"
        }
      }
    }
    '''
    
    
    # Replace the placeholder in the JSON string safely
    workflow_filled = workflow.replace('{pormpt}', prompt)
    workflow_filled = workflow_filled.replace('{seed}', str(random.randint(10**15, (10**16) - 1)))
    
    # Load to dict
    workflow_dict = json.loads(workflow_filled)
    
    
    
    # Generate unique prompt_id
    prompt_id = str(uuid.uuid4())
    
    # Build the payload
    payload = {
        "prompt": workflow_dict,
        "prompt_id": prompt_id
    }
    
    # Send to ComfyUI
    response = requests.post(
        "http://192.168.4.63:8188/prompt",
        json=payload
    )
    
    # Check result
    if response.ok:
        print("Task queued successfully.")
        # print("Response:", response.json())
    else:
        print("Failed to queue task.")
        print("Status Code:", response.status_code)
        print("Response:", response.text)