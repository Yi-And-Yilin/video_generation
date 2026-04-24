import os
import random
import string
import json
import logging
from pathlib import Path

from llm_conversation import LLMUtils, Conversation, render_md_template

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROMPTS_DIR = os.path.join(SCRIPT_DIR, "prompts")
TASKS_DIR = os.path.join(SCRIPT_DIR, "tasks")

IMAGE_PROMPT_GENERATOR_PATH = os.path.join(SCRIPT_DIR, "image_prompt_generator.py")


def generate_random_string(length=5):
    return ''.join(random.choice(string.ascii_lowercase + string.digits) for _ in range(length))


def load_prompt_template(template_name, **kwargs):
    md_path = os.path.join(PROMPTS_DIR, f"{template_name}.md")
    return render_md_template(md_path, **kwargs)


def load_tool_schema(schema_name):
    json_path = os.path.join(PROMPTS_DIR, f"{schema_name}.json")
    with open(json_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def run_new_tab_workflow(user_requirements: str, status_callback=None, stop_event=None, mode="Tag") -> dict:
    """
    Runs the full character -> scene -> prompt generation pipeline.

    Parameters
    ----------
    user_requirements : str
        The user's text requirements.
    status_callback : callable or None
        If given, called with status messages after each LLM yield.
    stop_event : threading.Event or None
        If given, the workflow checks ``stop_event.is_set()`` between
        major phases and aborts early when set.
    mode : str
        Either "Tag" (default - generates image prompts via Phase 3) or "Z"
        (LLM already generates full prompts, Phase 3 is skipped).

    Returns
    -------
    dict
        The result dictionary containing job_id, character_design,
        location_design (with prompts embedded per location), mode, etc.
    """
    job_id = generate_random_string(5)
    job_dir = os.path.join(TASKS_DIR, job_id)
    os.makedirs(job_dir, exist_ok=True)

    if status_callback:
        status_callback(f"Job ID: {job_id}")
        status_callback(f"Created folder: {job_dir}")

    result = {
        "job_id": job_id,
        "user_requirements": user_requirements,
        "character_design": {},
        "location_design": {"locations": []},
        "mode": mode
    }

    # --- Create task.json IMMEDIATELY (before any LLM call) ---
    task_path = os.path.join(job_dir, "task.json")
    with open(task_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=4)
    if status_callback:
        status_callback("Created task.json")

    llm = LLMUtils(base_url="http://localhost:8081", model="qwen")

    # ============ Phase 1: Character Design ============
    char_schema = load_tool_schema("character_design")
    char_system_prompt = load_prompt_template("character_design", user_requirements=user_requirements)
    conv = Conversation(system_prompt=char_system_prompt, tool_schema=char_schema)

    if status_callback:
        status_callback("Generating character design...")

    char_response = ""
    for chunk in llm.chat(conv, "Design characters based on the user requirements.", chat_mode="json", max_retries=2):
        char_response += chunk
        if status_callback:
            status_callback(chunk, end="")

    if status_callback:
        status_callback("\n")

    # Check stop after Phase 1
    if stop_event and stop_event.is_set():
        if status_callback:
            status_callback("Stopped by user during character design.")
        # Save partial task.json
        with open(task_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=4)
        return result

    if "[TOOL_CALLS]:" in char_response:
        try:
            tc_start = char_response.rfind("[TOOL_CALLS]:")
            tc_json = char_response[tc_start + 13:].strip()
            char_data = json.loads(tc_json)
            if isinstance(char_data, list) and len(char_data) > 0:
                char_data = char_data[0].get("function", {}).get("arguments", {})
                if isinstance(char_data, str):
                    char_data = json.loads(char_data)
        except:
            char_data = None
    else:
        char_data = None

    if char_data:
        result["character_design"] = char_data
        if status_callback:
            status_callback(f"Character design generated: male={char_data.get('male', {}).get('age')}, female={char_data.get('female', {}).get('age')}")
    else:
        result["character_design"] = {"male": {}, "female": {}}
        if status_callback:
            status_callback("Warning: Could not parse character design")

    # Save after Phase 1
    with open(task_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=4)

    # ============ Phase 2: Scene / Location Design ============
    male_char = result["character_design"].get("male", {})
    female_char = result["character_design"].get("female", {})

    if mode == "Z":
        scene_schema = load_tool_schema("scene_design_z")
        scene_system_prompt = load_prompt_template(
            "scene_design_z",
            user_requirements=user_requirements,
            male_character=json.dumps(male_char),
            female_character=json.dumps(female_char)
        )
    else:
        scene_schema = load_tool_schema("location_design")
        scene_system_prompt = load_prompt_template(
            "location_design",
            user_requirements=user_requirements,
            male_character=json.dumps(male_char),
            female_character=json.dumps(female_char)
        )
    conv2 = Conversation(system_prompt=scene_system_prompt, tool_schema=scene_schema)

    if status_callback:
        status_callback("Generating scene design...")

    scene_response = ""
    for chunk in llm.chat(conv2, "Design the scene based on the characters and requirements.", chat_mode="json", max_retries=2):
        scene_response += chunk
        if status_callback:
            status_callback(chunk, end="")

    if status_callback:
        status_callback("\n")

    # Check stop after Phase 2
    if stop_event and stop_event.is_set():
        if status_callback:
            status_callback("Stopped by user during scene design.")
        with open(task_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=4)
        return result

    if "[TOOL_CALLS]:" in scene_response:
        try:
            tc_start = scene_response.rfind("[TOOL_CALLS]:")
            tc_json = scene_response[tc_start + 13:].strip()
            scene_data = json.loads(tc_json)
            if isinstance(scene_data, list) and len(scene_data) > 0:
                scene_data = scene_data[0].get("function", {}).get("arguments", {})
                if isinstance(scene_data, str):
                    scene_data = json.loads(scene_data)
        except:
            scene_data = None
    else:
        # Fallback: try parsing raw JSON directly (LLM may output without [TOOL_CALLS] wrapper)
        scene_data = None
        stripped = scene_response.strip()
        if stripped.startswith("{"):
            try:
                scene_data = json.loads(stripped)
            except:
                pass

    if scene_data:
        if "scenes" in scene_data and "locations" not in scene_data:
            locations_converted = []
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
                locations_converted.append(loc)
            scene_data["locations"] = locations_converted
            if status_callback:
                status_callback(f"Warning: LLM returned 'scenes' format, auto-converted to 'locations' ({len(locations_converted)} locations)")
        
        result["location_design"] = scene_data
        locations = scene_data.get("locations", [])
        if status_callback:
            loc_names = [loc.get("location", "unknown") for loc in locations]
            status_callback(f"Location design generated: {loc_names}")
    else:
        result["location_design"] = {"locations": []}
        locations = []
        if status_callback:
            status_callback("Warning: Could not parse scene design")

    # Save after Phase 2
    with open(task_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=4)

    # Check stop before entering prompt generation
    if stop_event and stop_event.is_set():
        if status_callback:
            status_callback("Stopped by user before prompt generation.")
        return result

    # ============ Phase 3: Image Prompt Generation ============
    # Z mode: LLM already generates full prompts with sex_act and prompt fields, skip Phase 3
    if mode == "Z":
        if status_callback:
            status_callback("Z mode: Skipping Phase 3 (LLM already generated prompts)")
        with open(task_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=4)
    else:
        if not locations:
            if status_callback:
                status_callback("No locations to generate prompts for.")
                return result

        if status_callback:
            status_callback("Loading image prompt generator...")

        prompts = _generate_prompts_for_locations(
            locations,
            result["character_design"],
            job_id,
            status_callback
        )

        # Embed prompts into each location under a "prompts" key (list of 3 strings)
        for i, loc in enumerate(locations):
            loc_prompts = prompts[i] if i < len(prompts) else []
            loc["prompts"] = loc_prompts

    # Check stop before Phase 4
    if stop_event and stop_event.is_set():
        if status_callback:
            status_callback("Stopped by user before video prompt generation.")
        return result

    # ============ Phase 4: Video Prompt Generation ============
    if status_callback:
        status_callback("Generating video prompts...")
    
    updated_locations = _run_video_prompt_generation(
        locations,
        result["character_design"],
        user_requirements,
        job_id,
        status_callback
    )
    
    if updated_locations is not None:
        result["location_design"]["locations"] = updated_locations
        if status_callback:
            status_callback("Video prompt generation completed successfully.")
    else:
        # Video prompt generation failed, keep original prompts
        if status_callback:
            status_callback("Warning: Video prompt generation failed, keeping original prompts.")

    # Final save
    with open(task_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=4)

    if status_callback:
        status_callback(f"All done. Saved to: {task_path}")

    return result


def _build_first_frame_image_prompts(locations):
    """
    Build the first_frame_image_prompts list from existing prompts.
    
    For each prompt in each location, create an object with:
    - image_prompt: the original image prompt string
    - sex_act: extracted from the location's main_sex_act or prompts metadata
    
    Returns a list of dicts:
    [
        {"image_prompt": "...", "sex_act": "..."},
        ...
    ]
    """
    first_frame_prompts = []
    for loc in locations:
        main_act = loc.get("main_sex_act", [])
        if isinstance(main_act, list) and main_act:
            sex_act = main_act[0] if isinstance(main_act[0], str) else str(main_act[0])
        else:
            sex_act = "unknown"
        
        prompts = loc.get("prompts", [])
        if not prompts:
            # If no prompts, create a placeholder
            first_frame_prompts.append({
                "image_prompt": f"Scene in {loc.get('location', 'unknown')} location",
                "sex_act": sex_act
            })
        else:
            for prompt in prompts:
                if isinstance(prompt, dict):
                    if "image_prompt" in prompt:
                        img_prompt = prompt["image_prompt"]
                        prompt_sex_act = prompt.get("sex_act", sex_act)
                    else:
                        img_prompt = prompt.get("prompt", f"Scene in {loc.get('location', 'unknown')}")
                        prompt_sex_act = prompt.get("sex_act", sex_act)
                    first_frame_prompts.append({
                        "image_prompt": img_prompt,
                        "sex_act": prompt_sex_act
                    })
                else:
                    # Tag mode: prompt is a string
                    first_frame_prompts.append({
                        "image_prompt": prompt,
                        "sex_act": sex_act
                    })
    
    return first_frame_prompts


def _run_video_prompt_generation(locations, character_design, user_requirements, job_id, status_callback=None):
    """
    Phase 4: Generate video prompts using the video_prompting LLM.
    
    For each image prompt, calls the LLM to generate:
    - action (motion description)
    - line (Chinese dialogue)
    - audio (background + movement sounds)
    - female_character_sound (vocal quality)
    
    Then combines them into a video_prompt string.
    Finally transforms each prompt from a string to:
    {"image_prompt": "...", "video_prompt": "..."}
    
    Returns the locations with updated prompts, or None on failure.
    """
    try:
        from llm_conversation import LLMUtils, Conversation
    except ImportError:
        if status_callback:
            status_callback("Warning: Could not import llm_conversation for video prompt generation")
        return None
    
    if status_callback:
        status_callback("Generating video prompts...")
    
    # Build first_frame_image_prompts from existing data
    first_frame_prompts = _build_first_frame_image_prompts(locations)
    if not first_frame_prompts:
        if status_callback:
            status_callback("No prompts available for video generation.")
        return None
    
    if status_callback:
        status_callback(f"Preparing {len(first_frame_prompts)} prompts for video generation...")
    
    try:
        # Load video_prompting schema and template
        video_schema = load_tool_schema("video_prompting")
        video_system_prompt = load_prompt_template(
            "video_prompting",
            user_requirements=user_requirements,
            male_character=json.dumps(character_design.get("male", {})),
            female_character=json.dumps(character_design.get("female", {})),
            first_frame_image_prompts=json.dumps(first_frame_prompts)
        )
    except Exception as e:
        if status_callback:
            status_callback(f"Error loading video_prompting files: {e}")
        return None
    
    # Create conversation
    conv = Conversation(system_prompt=video_system_prompt, tool_schema=video_schema)
    
    # Call LLM
    llm = LLMUtils(base_url="http://localhost:8081", model="qwen")
    response = ""
    try:
        for chunk in llm.chat(conv, "Generate video prompts for each image prompt.", chat_mode="json", max_retries=2):
            response += chunk
            if status_callback:
                status_callback(chunk, end="")
    except Exception as e:
        if status_callback:
            status_callback(f"LLM call failed for video prompting: {e}")
        return None
    
    if status_callback:
        status_callback("\n")
    
    # Parse response
    video_prompts = None
    if "[TOOL_CALLS]:" in response:
        try:
            tc_start = response.rfind("[TOOL_CALLS]:")
            tc_json = response[tc_start + 13:].strip()
            data = json.loads(tc_json)
            if isinstance(data, list) and len(data) > 0:
                video_prompts = data[0].get("function", {}).get("arguments", {})
                if isinstance(video_prompts, str):
                    video_prompts = json.loads(video_prompts)
        except Exception as e:
            if status_callback:
                status_callback(f"Error parsing video prompt response: {e}")
    
    if not video_prompts or "video_prompts" not in video_prompts:
        if status_callback:
            status_callback("Warning: Could not parse video prompts from LLM response")
        return None
    
    vp_list = video_prompts["video_prompts"]
    if len(vp_list) != len(first_frame_prompts):
        if status_callback:
            status_callback(f"Warning: LLM returned {len(vp_list)} video prompts, expected {len(first_frame_prompts)}")
    
    # Transform prompts: each prompt becomes {"image_prompt": "...", "video_prompt": "..."}
    for i, loc in enumerate(locations):
        prompts = loc.get("prompts", [])
        if not prompts:
            continue
        
        # Find corresponding video prompts for this location
        loc_vp_count = len(prompts)
        loc_vps = vp_list[i:i+loc_vp_count] if i < len(vp_list) else []
        
        for j, prompt in enumerate(prompts):
            if j < len(loc_vps):
                vp = loc_vps[j]
                # Combine action + line + audio + female_character_sound into video_prompt
                video_prompt = " ".join([
                    vp.get("action", ""),
                    vp.get("line", ""),
                    vp.get("audio", ""),
                    vp.get("female_character_sound", "")
                ])
                if isinstance(prompt, dict):
                    # Z mode: transform dict
                    prompt["video_prompt"] = video_prompt
                else:
                    # Tag mode: transform to dict
                    prompts[j] = {
                        "image_prompt": prompt,
                        "video_prompt": video_prompt
                    }
            else:
                # No video prompt from LLM, use image prompt as video prompt
                if isinstance(prompt, dict):
                    if "image_prompt" not in prompt:
                        prompt["image_prompt"] = prompt.get("prompt", "")
                    prompt["video_prompt"] = prompt.get("image_prompt", "")
                else:
                    prompts[j] = {
                        "image_prompt": prompt,
                        "video_prompt": prompt
                    }
    
    return locations


def _generate_prompts_for_locations(locations, character_design, job_id, status_callback=None):
    """
    Uses image_prompt_generator.generate_prompts_for_locations() to produce
    3 prompts per location.  Returns a flat list of lists:
        [[loc0_prompt1, loc0_prompt2, loc0_prompt3],
         [loc1_prompt1, ...],
         ...]
    """
    # Import the generator dynamically so we don't break if it's missing
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "image_prompt_generator", IMAGE_PROMPT_GENERATOR_PATH
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        generate_prompts_func = mod.generate_prompts_for_locations
    except Exception as e:
        if status_callback:
            status_callback(f"Failed to load image_prompt_generator: {e}")
        return [[] for _ in locations]

    prompts_list = []
    for idx, location in enumerate(locations):
        if status_callback:
            status_callback(f"Generating 3 prompts for location {idx+1}/{len(locations)}: {location.get('location', 'unknown')}")
        try:
            loc_prompts = generate_prompts_func(location, character_design)
            prompts_list.append(loc_prompts)
        except Exception as e:
            if status_callback:
                status_callback(f"Error generating prompts for '{location.get('location', 'unknown')}': {e}")
            prompts_list.append([])

    return prompts_list


def run_mock_workflow(user_requirements: str, status_callback=None, stop_event=None) -> dict:
    job_id = generate_random_string(5)
    job_dir = os.path.join(TASKS_DIR, job_id)
    os.makedirs(job_dir, exist_ok=True)

    if status_callback:
        status_callback(f"[MOCK] Job ID: {job_id}")
        status_callback(f"[MOCK] Created folder: {job_dir}")
        status_callback("[MOCK] Generating character design...")

    mock_char = {
        "male": {
            "age": "Adult",
            "nationality": "Asian",
            "height": "Tall",
            "body_shape": "Athletic",
            "hair_style": "short",
            "personality": "Confident"
        },
        "female": {
            "age": "Young",
            "nationality": "Asian",
            "height": "Medium",
            "body_shape": "Curvy",
            "hair_style": "long",
            "personality": "Playful"
        }
    }

    if status_callback:
        status_callback(f"[MOCK] Character design: male={mock_char['male']['age']}, female={mock_char['female']['age']}")
        status_callback("[MOCK] Generating scene design...")

    mock_scene = {
        "locations": [
            {
                "location": "swimming pool",
                "location_major_elements": ["pool water", "pool ladder", "deck chairs"],
                "time": "afternoon",
                "lying_surfaces": [
                    {"lying_surface": "pool deck", "objects_on_it": ["towel"]}
                ],
                "sitting_surface": ["pool ladder", "deck chair"],
                "virtical_surface": ["pool wall"],
                "lighting": "natural sunlight",
                "female_character": {
                    "top": "bikini top",
                    "bottom": "bikini bottom",
                    "shoes": "barefoot",
                    "legs": "",
                    "bra": "",
                    "panties": "",
                    "accessories": {"hair": "swimming cap"}
                },
                "male_character": {
                    "top": "swim trunks",
                    "bottom": "swim trunks",
                    "shoes": "barefoot",
                    "legs": "",
                    "accessories": {"hair": ""}
                }
            },
            {
                "location": "bedroom",
                "location_major_elements": ["bed", "window", "nightstand"],
                "time": "evening",
                "lying_surfaces": [
                    {"lying_surface": "bed", "objects_on_it": ["pillow", "blanket"]}
                ],
                "sitting_surface": ["chair", "bed edge"],
                "virtical_surface": ["wall", "window"],
                "lighting": "warm bedroom lamp",
                "female_character": {
                    "top": "silk camisole",
                    "bottom": "shorts",
                    "shoes": "barefoot",
                    "legs": "",
                    "bra": "lace bra",
                    "panties": "matching panties",
                    "accessories": {"hair": "loose hair"}
                },
                "male_character": {
                    "top": "t-shirt",
                    "bottom": "casual pants",
                    "shoes": "barefoot",
                    "legs": "",
                    "accessories": {"hair": "messy hair"}
                }
            },
            {
                "location": "bathroom",
                "location_major_elements": ["bathtub", "mirror", "tiles"],
                "time": "night",
                "lying_surfaces": [
                    {"lying_surface": "bathtub", "objects_on_it": ["sponge", "towels"]}
                ],
                "sitting_surface": ["bathtub edge", "stool"],
                "virtical_surface": ["shower wall", "mirror"],
                "lighting": "dim bathroom light",
                "female_character": {
                    "top": "",
                    "bottom": "",
                    "shoes": "barefoot",
                    "legs": "",
                    "bra": "",
                    "panties": "",
                    "accessories": {"hair": "wet hair bun"}
                },
                "male_character": {
                    "top": "",
                    "bottom": "",
                    "shoes": "barefoot",
                    "legs": "",
                    "accessories": {"hair": "wet combed back"}
                }
            }
        ]
    }

    if status_callback:
        loc_names = [loc.get("location", "unknown") for loc in mock_scene.get("locations", [])]
        status_callback(f"[MOCK] Location design: {loc_names}")

    result = {
        "job_id": job_id,
        "user_requirements": user_requirements,
        "character_design": mock_char,
        "location_design": mock_scene
    }

    task_path = os.path.join(job_dir, "task.json")
    with open(task_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=4)

    if status_callback:
        status_callback(f"[MOCK] Saved to: {task_path}")

    return result


if __name__ == "__main__":
    print("Running mock workflow tests...")

    test_requirements = [
        "An asian couple, design 3 locations for them, romantic atmosphere"
    ]

    for req in test_requirements:
        print(f"\n{'='*50}")
        print(f"Testing: {req}")
        print('='*50)

        def status_callback(msg, end="\n"):
            print(msg, end=end)

        result = run_mock_workflow(req, status_callback)
        print(f"\nResult saved to: tasks/{result['job_id']}/task.json")