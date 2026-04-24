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
            tc_start = char_response.find("[TOOL_CALLS]:")
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
            tc_start = scene_response.find("[TOOL_CALLS]:")
            tc_json = scene_response[tc_start + 13:].strip()
            scene_data = json.loads(tc_json)
            if isinstance(scene_data, list) and len(scene_data) > 0:
                scene_data = scene_data[0].get("function", {}).get("arguments", {})
                if isinstance(scene_data, str):
                    scene_data = json.loads(scene_data)
        except:
            scene_data = None
    else:
        scene_data = None

    if scene_data:
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
        if status_callback:
            status_callback(f"All done (Z mode). Saved to: {task_path}")
        return result

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

    result["location_design"]["locations"] = locations

    # Final save
    with open(task_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=4)

    if status_callback:
        status_callback(f"All done. Saved to: {task_path}")

    return result


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