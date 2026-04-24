"""
Parameter Extraction Module for Standard Workflow Interface

This module provides:
1. StandardWorkflowParams - a canonical dataclass covering ALL placeholder names
   from ALL ComfyUI workflow templates (WAN 2.1, WAN 2.2, LTX, SDXL/wan_image)
2. Extraction functions that convert various task.json formats into StandardWorkflowParams
3. Validation helpers

Placeholder Inventory (from all templates):
============================================
WAN 2.2 Step 0:  **video_width**, **video_height**, **video_seconds**, **video_pos_prompt**,
                 **load_image**, **save_pos_conditioning**, **save_neg_conditioning**,
                 **save_latent**
WAN 2.2 Step 1/2: **load_pos_conditioning**, **load_neg_conditioning**, **random_number**,
                  **save_latent**, **load_latent**
WAN 2.2 Step 3:   **save_video**, **load_latent**
WAN Image (SDXL): **checkpoint**, **video_width**, **video_height**, **image_pos_prompt**,
                  **image_neg_prompt**, **random_number**, **save_video**,
                  **lora1..5_name**, **lora1..5_strength**
LTX Sampling:     **prompt**, **width**, **height**, **length**, **work_id**, **image**,
                  **load_pos_conditioning**, **load_neg_conditioning**, **random_number**,
                  **fps**, **lora1..5_name**, **lora1..5_strength**
LTX Text Encoding: **prompt**, **save_pos_conditioning**, **negative_prompt**, **save_neg_conditioning**
LTX Latent:       **video_latent**, **audio_latent**, **save_video**, **fps**
LTX Preparation:  **video_pos_prompt**, **video_width**, **video_height**, **load_pos_conditioning**

Author: Video Generation System
"""

import json
import os
import random
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any
from enum import Enum


# ============================================================================
# Parameter Type Enum
# ============================================================================

class ParamType(str, Enum):
    """Parameter value types matching ComfyUI node input types."""
    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"


# ============================================================================
# Standard Workflow Parameters Dataclass
# ============================================================================

@dataclass
class StandardWorkflowParams:
    """
    Canonical parameter interface covering ALL placeholders from ALL
    ComfyUI workflow templates.

    This is the single source of truth for workflow parameter exchange.
    Every downstream workflow generator or template processor consumes
    this interface (or a dict derived from it).

    Categories:
    - Identifiers: job_id, work_id, row_id
    - Dimensions: width, height, video_width, video_height
    - Temporal: length, fps, seconds, video_seconds
    - Prompts: prompt, image_pos_prompt, video_pos_prompt, etc.
    - Conditioning: load/save pos/neg conditioning filenames
    - Latents: load/save latent filenames
    - Images: image, load_image, save_video, save_image
    - Random: random_number (seed)
    - LoRA: lora1..5_name, lora1..5_strength
    - Checkpoint: checkpoint model name
    - Audio: audio_prompt, video_latent, audio_latent
    """

    # === Identifiers ===
    job_id: str = ""
    work_id: str = ""
    row_id: str = ""

    # === Dimensions ===
    width: int = 1024
    height: int = 1024
    video_width: int = 1024
    video_height: int = 1024

    # === Temporal ===
    length: int = 241
    fps: int = 24
    seconds: float = 10.0
    video_seconds: float = 10.0

    # === Prompts ===
    prompt: str = ""
    image_pos_prompt: str = ""
    video_pos_prompt: str = ""
    image_neg_prompt: str = ""
    negative_prompt: str = ""
    audio_prompt: str = ""
    video_prompt: str = ""

    # === Conditioning ===
    save_pos_conditioning: str = ""
    save_neg_conditioning: str = ""
    load_pos_conditioning: str = ""
    load_neg_conditioning: str = ""

    # === Latents ===
    save_latent: str = ""
    load_latent: str = ""
    video_latent: str = ""
    audio_latent: str = ""

    # === Images & Videos ===
    image: str = ""
    load_image: str = ""
    save_video: str = ""
    save_image: str = ""

    # === Random / Seed ===
    random_number: int = field(default_factory=lambda: random.randint(1, 999999999999999))

    # === LoRA (5 slots) ===
    lora1_name: str = "xl\\add-detail.safetensors"
    lora1_strength: float = 0.0
    lora2_name: str = "xl\\add-detail.safetensors"
    lora2_strength: float = 0.0
    lora3_name: str = "xl\\add-detail.safetensors"
    lora3_strength: float = 0.0
    lora4_name: str = "xl\\add-detail.safetensors"
    lora4_strength: float = 0.0
    lora5_name: str = "xl\\add-detail.safetensors"
    lora5_strength: float = 0.0

    # === Checkpoint ===
    checkpoint: str = "meichiILIghtMIXV1_meichiILUstMIXV1.safetensors"

    # === Category / Tags ===
    category: str = ""
    sex_loras: List[str] = field(default_factory=list)
    main_sex_act: List[str] = field(default_factory=list)

    # === Character / Scene metadata (for logging / traceability) ===
    character_male_name: str = ""
    character_female_name: str = ""
    location_name: str = ""
    scene_index: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to a flat dict (for workflow_generator.py compatibility)."""
        result = asdict(self)
        # Remove empty string defaults that shouldn't be passed to workflow
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'StandardWorkflowParams':
        """Create from a dict (partial or full)."""
        known_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in known_fields}
        return cls(**filtered)

    def merge(self, **kwargs) -> 'StandardWorkflowParams':
        """Return a new instance with overridden fields."""
        current = asdict(self)
        current.update(kwargs)
        return StandardWorkflowParams(**current)

    def for_wan_image(self) -> Dict[str, Any]:
        """Return dict subset for wan_image (SDXL) workflow."""
        return {
            "checkpoint": self.checkpoint,
            "video_width": self.video_width,
            "video_height": self.video_height,
            "image_pos_prompt": self.image_pos_prompt or self.prompt,
            "image_neg_prompt": self.image_neg_prompt or self.negative_prompt,
            "random_number": self.random_number,
            "save_video": self.save_video or self.work_id,
            **{f"lora{i}_name": getattr(self, f"lora{i}_name") for i in range(1, 6)},
            **{f"lora{i}_strength": getattr(self, f"lora{i}_strength") for i in range(1, 6)},
        }

    def for_wan_video_step0(self) -> Dict[str, Any]:
        """Return dict subset for WAN 2.2 Step 0 (Image-to-Video prep)."""
        return {
            "video_width": self.video_width,
            "video_height": self.video_height,
            "video_seconds": int(self.video_seconds),
            "video_pos_prompt": self.video_pos_prompt or self.prompt,
            "load_image": self.load_image or self.image or f"{self.work_id}.png",
            "save_pos_conditioning": self.save_pos_conditioning or f"pos_{self.work_id}",
            "save_neg_conditioning": self.save_neg_conditioning or f"neg_{self.work_id}",
            "save_latent": self.save_latent or f"lat_{self.work_id}_s0",
        }

    def for_wan_video_step1(self) -> Dict[str, Any]:
        """Return dict subset for WAN 2.2 Step 1."""
        return {
            "load_pos_conditioning": self.load_pos_conditioning or f"pos_{self.work_id}",
            "load_neg_conditioning": self.load_neg_conditioning or f"neg_{self.work_id}",
            "random_number": self.random_number,
            "save_latent": self.save_latent or f"lat_{self.work_id}_s1",
            "load_latent": self.load_latent or f"lat_{self.work_id}_s0_00001_.latent",
        }

    def for_wan_video_step2(self) -> Dict[str, Any]:
        """Return dict subset for WAN 2.2 Step 2."""
        return {
            "load_pos_conditioning": self.load_pos_conditioning or f"pos_{self.work_id}",
            "load_neg_conditioning": self.load_neg_conditioning or f"neg_{self.work_id}",
            "random_number": self.random_number,
            "save_latent": self.save_latent or f"lat_{self.work_id}_s2",
            "load_latent": self.load_latent or f"lat_{self.work_id}_s1_00001_.latent",
        }

    def for_wan_video_step3(self) -> Dict[str, Any]:
        """Return dict subset for WAN 2.2 Step 3 (Decode + Save)."""
        return {
            "save_video": self.save_video or self.work_id,
            "load_latent": self.load_latent or f"lat_{self.work_id}_s2_00001_.latent",
        }

    def for_ltx_sampling(self) -> Dict[str, Any]:
        """Return dict subset for LTX sampling workflow."""
        return {
            "prompt": self.prompt,
            "width": self.width,
            "height": self.height,
            "length": self.length,
            "work_id": self.work_id,
            "image": self.image or f"{self.work_id}.png",
            "load_pos_conditioning": self.load_pos_conditioning,
            "load_neg_conditioning": self.load_neg_conditioning,
            "random_number": self.random_number,
            "fps": self.fps,
            **{f"lora{i}_name": getattr(self, f"lora{i}_name") for i in range(1, 6)},
            **{f"lora{i}_strength": getattr(self, f"lora{i}_strength") for i in range(1, 6)},
        }

    def for_ltx_text_encoding(self) -> Dict[str, Any]:
        """Return dict subset for LTX text encoding workflow."""
        return {
            "prompt": self.prompt,
            "save_pos_conditioning": self.save_pos_conditioning or f"pos_{self.work_id}",
            "negative_prompt": self.negative_prompt or self.image_neg_prompt,
            "save_neg_conditioning": self.save_neg_conditioning or f"neg_{self.work_id}",
        }

    def for_ltx_latent_decode(self) -> Dict[str, Any]:
        """Return dict subset for LTX latent decode workflow."""
        return {
            "video_latent": self.video_latent,
            "audio_latent": self.audio_latent,
            "save_video": self.save_video or self.work_id,
            "fps": self.fps,
        }


# ============================================================================
# Extraction Functions
# ============================================================================

def extract_params_from_new_tab_task(task_path: str, scene_index: int = 0,
                                     resolution: str = "1024*1024",
                                     prompt_index: int = 0) -> StandardWorkflowParams:
    """
    Extract StandardWorkflowParams from a New-tab task.json file.

    The New tab generates task.json with structure:
    {
        "job_id": "wzk4h",
        "character_design": {"male": {...}, "female": {...}},
        "location_design": {
            "locations": [
                {
                    "location": "...",
                    "prompts": ["prompt1", "prompt2", "prompt3"],
                    "female_character": {...},
                    "male_character": {...},
                    ...
                }
            ]
        }
    }

    Parameters
    ----------
    task_path : str
        Path to the task.json file.
    scene_index : int
        Which location to use (default 0).
    resolution : str
        "WIDTH*HEIGHT" string (e.g., "1280*720").
    prompt_index : int
        Which prompt in the location's prompts list to use (default 0).

    Returns
    -------
    StandardWorkflowParams
        Extracted parameters ready for workflow generation.
    """
    with open(task_path, 'r', encoding='utf-8') as f:
        task = json.load(f)

    # Parse resolution
    res_parts = resolution.split('*')
    width = int(res_parts[0])
    height = int(res_parts[1]) if len(res_parts) > 1 else width

    # Extract character info
    char_design = task.get("character_design", {})
    male = char_design.get("male", {})
    female = char_design.get("female", {})

    # Extract location info
    loc_design = task.get("location_design", {})
    locations = loc_design.get("locations", [])
    location = locations[scene_index] if scene_index < len(locations) else {}

    # Get the prompt for this scene
    # After Phase 4 (Video Prompt Generation): prompts is array of {image_prompt, video_prompt} dicts
    # Before Phase 4 Z mode: prompts is array of {sex_act, prompt} dicts
    # Before Phase 4 Tag mode: prompts is array of strings
    prompts = location.get("prompts", [])
    if prompts:
        first_prompt = prompts[min(prompt_index, len(prompts) - 1)]
        if isinstance(first_prompt, dict):
            # Check if this is the new format (Phase 4+) with image_prompt/video_prompt
            if "image_prompt" in first_prompt:
                # New format: use image_prompt for image generation
                prompt = first_prompt.get("image_prompt", "")
                sex_act = first_prompt.get("sex_act", "")
            elif "prompt" in first_prompt:
                # Old Z-mode format: {sex_act, prompt}
                prompt = first_prompt.get("prompt", "")
                sex_act = first_prompt.get("sex_act", "")
            else:
                prompt = str(first_prompt)
                sex_act = ""
        else:
            # Tag mode: prompts is array of strings
            prompt = first_prompt
            sex_act = ""
    else:
        prompt = ""
        sex_act = ""

    # Build negative prompt (SDXL default)
    default_neg = ("lowres, bad anatomy, bad hands, text, error, missing fingers, "
                   "extra digit, fewer digits, cropped, worst quality, low quality, "
                   "normal quality, jpeg artifacts, signature, watermark, username, blurry")

    # Extract category / sex loras from prompts field if present
    sex_loras = location.get("sex_loras", [])
    main_sex_act = location.get("main_sex_act", sex_loras)

    # In Z mode, use the sex_act from the prompt object if available
    if sex_act and sex_act not in main_sex_act:
        main_sex_act = list(main_sex_act) + [sex_act] if main_sex_act else [sex_act]

    # Build character description for prompt enhancement
    char_desc_parts = []
    if male:
        male_age = male.get("age", "")
        male_nat = male.get("nationality", "")
        char_desc_parts.append(f"{male_age} {male_nat} man")
    if female:
        fem_age = female.get("age", "")
        fem_nat = female.get("nationality", "")
        char_desc_parts.append(f"{fem_age} {fem_nat} woman")

    # Create standard params
    params = StandardWorkflowParams(
        job_id=task.get("job_id", ""),
        work_id=task.get("job_id", ""),
        width=width,
        height=height,
        video_width=width,
        video_height=height,
        prompt=prompt,
        image_pos_prompt=prompt,
        image_neg_prompt=default_neg,
        negative_prompt=default_neg,
        save_video=task.get("job_id", ""),
        category=",".join(main_sex_act) if main_sex_act else "",
        sex_loras=sex_loras,
        main_sex_act=main_sex_act,
        character_male_name=male.get("name", ""),
        character_female_name=female.get("name", ""),
        location_name=location.get("location", ""),
        scene_index=scene_index,
    )

    return params


def extract_z_mode_shot_to_location(scene_data: Dict) -> Optional[Dict]:
    """
    Fallback converter when LLM returned 'scenes' format instead of 'locations'.
    
    Converts:
    {"scenes": [{"location_name": "...", "shots": [{"pose": "...", "prompt": "..."}]}]}
    Into:
    {"location": "...", "time": "...", "lighting": "...", "prompts": [{"sex_act": "...", "prompt": "..."}]}
    
    Parameters
    ----------
    scene_data : dict
        The raw scene design data from LLM response.
    
    Returns
    -------
    dict or None
        The converted locations data, or None if input is invalid.
    """
    if not isinstance(scene_data, dict):
        return None
    
    if "scenes" not in scene_data:
        return None
    
    locations = []
    for sc in scene_data.get("scenes", []):
        loc = {
            "location": sc.get("location_name", sc.get("location", "")),
            "time": sc.get("time", "daytime"),
            "lighting": sc.get("lighting", sc.get("description", "")),
            "prompts": []
        }
        for shot in sc.get("shots", []):
            prompt_obj = {
                "sex_act": shot.get("pose", shot.get("sex_act", "")),
                "prompt": shot.get("prompt", "")
            }
            loc["prompts"].append(prompt_obj)
        locations.append(loc)
    
    return {"locations": locations}


def extract_params_from_z_mode_task(task_path: str, scene_index: int = 0,
                                   resolution: str = "1024*1024",
                                   prompt_index: int = 0) -> StandardWorkflowParams:
    """
    Extract StandardWorkflowParams from a Z-mode task.json file.

    Z-mode task.json structure:
    {
        "job_id": "wzk4h",
        "character_design": {"male": {...}, "female": {...}},
        "location_design": {
            "locations": [{
                "location": "...",
                "time": "...",
                "lighting": "...",
                "prompts": [
                    {"sex_act": "sitting_cowgirl", "prompt": "..."},
                    ...
                ]
            }]
        },
        "mode": "Z"
    }

    This is a convenience wrapper that calls extract_params_from_new_tab_task()
    with the same logic but works specifically with Z-mode format.
    """
    # Attempt fallback conversion if locations is missing
    with open(task_path, 'r', encoding='utf-8') as f:
        task = json.load(f)
    
    loc_design = task.get("location_design", {})
    if "locations" not in loc_design and "scenes" in loc_design:
        converted = extract_z_mode_shot_to_location(loc_design)
        if converted:
            task["location_design"] = converted
            with open(task_path, 'w', encoding='utf-8') as f:
                json.dump(task, f, indent=4)
    
    return extract_params_from_new_tab_task(task_path, scene_index, resolution, prompt_index)


def extract_params_from_scene_task(task_path: str, resolution: str = "1024*1024") -> StandardWorkflowParams:
    """
    Extract StandardWorkflowParams from an LTX scene-style task.json.

    The scene task format (from Prompt tab or Image tab):
    {
        "scenes": [
            {
                "first_frame_image_prompt": "...",
                "main_sex_act": ["doggy_style"],
                ...
            }
        ]
    }

    Parameters
    ----------
    task_path : str
        Path to the task.json file.
    resolution : str
        "WIDTH*HEIGHT" string.

    Returns
    -------
    StandardWorkflowParams
    """
    with open(task_path, 'r', encoding='utf-8') as f:
        task = json.load(f)

    # Parse resolution
    res_parts = resolution.split('*')
    width = int(res_parts[0])
    height = int(res_parts[1]) if len(res_parts) > 1 else width

    # Extract scene info
    scenes = task.get("scenes", [])
    scene = scenes[0] if scenes else {}

    default_neg = ("lowres, bad anatomy, bad hands, text, error, missing fingers, "
                   "extra digit, fewer digits, cropped, worst quality, low quality, "
                   "normal quality, jpeg artifacts, signature, watermark, username, blurry")

    sex_loras = scene.get("sex_loras", [])
    main_sex_act = scene.get("main_sex_act", sex_loras)

    params = StandardWorkflowParams(
        job_id=task.get("job_id", task.get("work_id", "")),
        work_id=task.get("job_id", task.get("work_id", "")),
        width=width,
        height=height,
        video_width=width,
        video_height=height,
        prompt=scene.get("first_frame_image_prompt", ""),
        image_pos_prompt=scene.get("first_frame_image_prompt", ""),
        image_neg_prompt=default_neg,
        negative_prompt=default_neg,
        save_video=task.get("job_id", ""),
        category=",".join(main_sex_act) if main_sex_act else "",
        sex_loras=sex_loras,
        main_sex_act=main_sex_act,
        scene_index=0,
    )

    return params


def extract_params_for_wan_video(task_path: str, work_id: str = "",
                                  resolution: str = "1280*720", seconds: float = 10.0) -> StandardWorkflowParams:
    """
    Extract StandardWorkflowParams for WAN video pipeline from a task.json.

    This is a simplified extractor for the WAN video flow where:
    - The image is provided externally (load_image)
    - The prompts are derived from the task

    Parameters
    ----------
    task_path : str
        Path to the source task.json.
    work_id : str
        Override work_id (if empty, uses job_id from task).
    resolution : str
        "WIDTH*HEIGHT" string.
    seconds : float
        Video duration in seconds.

    Returns
    -------
    StandardWorkflowParams
    """
    with open(task_path, 'r', encoding='utf-8') as f:
        task = json.load(f)

    res_parts = resolution.split('*')
    width = int(res_parts[0])
    height = int(res_parts[1]) if len(res_parts) > 1 else width

    wid = work_id or task.get("job_id", "unknown")

    # Extract first positive prompt from location design
    # After Phase 4: prompts is array of {image_prompt, video_prompt} dicts
    # Before Phase 4: prompts is array of strings or {sex_act, prompt} dicts
    loc_design = task.get("location_design", {})
    locations = loc_design.get("locations", [])
    video_pos = ""
    image_pos = ""
    if locations:
        loc = locations[0]
        prompts = loc.get("prompts", [])
        if prompts:
            first_prompt = prompts[0]
            if isinstance(first_prompt, dict):
                video_pos = first_prompt.get("video_prompt", "")
                image_pos = first_prompt.get("image_prompt", "")
            else:
                video_pos = str(first_prompt)
                image_pos = str(first_prompt)

    return StandardWorkflowParams(
        job_id=task.get("job_id", ""),
        work_id=wid,
        width=width,
        height=height,
        video_width=width,
        video_height=height,
        video_seconds=seconds,
        video_pos_prompt=video_pos or image_pos,
        video_prompt=video_pos,
        load_image=f"{wid}.png",
        save_pos_conditioning=f"pos_{wid}",
        save_neg_conditioning=f"neg_{wid}",
        save_latent=f"lat_{wid}",
        save_video=wid,
        seconds=seconds,
        fps=16,
    )


def create_default_image_params(work_id: str, prompt: str = "",
                                 resolution: str = "1024*1024") -> StandardWorkflowParams:
    """
    Create a default StandardWorkflowParams for image generation.

    Useful for direct ComfyUI API calls without task.json.
    """
    res_parts = resolution.split('*')
    width = int(res_parts[0])
    height = int(res_parts[1]) if len(res_parts) > 1 else width

    default_neg = ("lowres, bad anatomy, bad hands, text, error, missing fingers, "
                   "extra digit, fewer digits, cropped, worst quality, low quality, "
                   "normal quality, jpeg artifacts, signature, watermark, username, blurry")

    return StandardWorkflowParams(
        job_id=work_id,
        work_id=work_id,
        width=width,
        height=height,
        video_width=width,
        video_height=height,
        prompt=prompt,
        image_pos_prompt=prompt,
        image_neg_prompt=default_neg,
        negative_prompt=default_neg,
        save_video=work_id,
    )


def new_tab_task_to_ltx_batch_tasks(task_path: str) -> List[Dict]:
    """
    Convert a New Tab task.json (after Phase 4) to a list of task dicts 
    suitable for BatchRunner.run_batch().
    
    Each prompt in each location becomes a separate task entry.
    The prompt uses the image_prompt field for the image generation prompt
    and the video_prompt field for the video generation prompt.
    
    Returns a list of dicts like:
    [
        {
            "work_id": "<job_id>_scene0_act0",
            "main_sex_act": "kissing",
            "prompt": "A kissing scene in bedroom",
            "video_pos_prompt": "She leans forward slowly こんにちは soft rain sounds soft young female voice",
            "negative_prompt": "...",
        },
        ...
    ]
    """
    with open(task_path, 'r', encoding='utf-8') as f:
        task = json.load(f)
    
    job_id = task.get("job_id", "unknown")
    locations = task.get("location_design", {}).get("locations", [])
    
    default_neg = ("lowres, bad anatomy, bad hands, text, error, missing fingers, "
                   "extra digit, fewer digits, cropped, worst quality, low quality, "
                   "normal quality, jpeg artifacts, signature, watermark, username, blurry")
    
    tasks = []
    for scene_idx, loc in enumerate(locations):
        prompts = loc.get("prompts", [])
        main_sex_act = loc.get("main_sex_act", [])
        sex_act_list = main_sex_act if isinstance(main_sex_act, list) else [main_sex_act]
        sex_act = sex_act_list[0] if sex_act_list else ""
        
        for prompt_idx, prompt_obj in enumerate(prompts):
            if isinstance(prompt_obj, dict):
                image_prompt = prompt_obj.get("image_prompt", prompt_obj.get("prompt", ""))
                video_prompt = prompt_obj.get("video_prompt", prompt_obj.get("prompt", ""))
                prompt_sex_act = prompt_obj.get("sex_act", sex_act)
                if not prompt_sex_act and sex_act_list:
                    prompt_sex_act = sex_act_list[0]
            else:
                image_prompt = prompt_obj
                video_prompt = prompt_obj
                prompt_sex_act = sex_act
            
            work_id = f"{job_id}_scene{scene_idx}_act{prompt_idx}"
            
            tasks.append({
                "work_id": work_id,
                "main_sex_act": prompt_sex_act,
                "prompt": image_prompt,
                "video_pos_prompt": video_prompt,
                "negative_prompt": default_neg,
                "scene_index": scene_idx,
                "prompt_index": prompt_idx,
            })
    
    return tasks


def validate_params(params: StandardWorkflowParams, required_fields: List[str] = None) -> List[str]:
    """
    Validate that required fields are non-empty.

    Parameters
    ----------
    params : StandardWorkflowParams
        The parameters to validate.
    required_fields : List[str], optional
        Field names to check. If None, checks all string fields.

    Returns
    -------
    List[str]
        List of missing/empty field names.
    """
    if required_fields is None:
        required_fields = [f.name for f in params.__dataclass_fields__.values()
                          if f.type == str]

    missing = []
    for field_name in required_fields:
        val = getattr(params, field_name, None)
        if not val:
            missing.append(field_name)
    return missing
