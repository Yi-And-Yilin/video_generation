
import os
import json
import sys
import csv
from PIL import Image

# Add projects/ltx to sys.path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LTX_DIR = os.path.join(SCRIPT_DIR, "projects", "ltx")
if LTX_DIR not in sys.path:
    sys.path.insert(0, LTX_DIR)

from video_tab import VideoTabUI
from workflow_generator import generate_api_workflow

def test_integration():
    image_path = r"C:\SimpleAIHelper\video_generation\output_images\wg22j_scene0_p0.png"
    if not os.path.exists(image_path):
        print(f"Error: Image not found at {image_path}")
        return

    print(f"--- Processing Image: {os.path.basename(image_path)} ---")
    
    # We can use the methods as they don't depend on self much, 
    # but some call self._c() or other instance methods.
    # Let's create a minimal instance or just replicate the extraction logic.
    
    # Extract metadata using the improved logic
    from PIL import Image as PILImage
    img = PILImage.open(image_path)
    metadata_str = img.info.get("prompt", "")
    metadata = json.loads(metadata_str) if metadata_str else {}
    
    # Format video prompt
    video_prompt_data = metadata.get("video_prompt", {})
    if isinstance(video_prompt_data, dict):
        action = video_prompt_data.get("action", "")
        line = video_prompt_data.get("line", "")
        female_sound = video_prompt_data.get("female_character_sound", "")
        audio = video_prompt_data.get("audio", "")
    else:
        action = video_prompt_data
        line = metadata.get("line", "")
        female_sound = metadata.get("female_character_sound", "")
        audio = metadata.get("audio", "")
    
    video_prompt = action
    if line:
        if video_prompt: video_prompt += "\n"
        video_prompt += "She says: " + line
    if female_sound:
        if video_prompt: video_prompt += "\n"
        video_prompt += "Sound: " + female_sound
    if audio:
        if video_prompt: video_prompt += "\n"
        video_prompt += "Audio: " + audio

    sex_act = metadata.get("sex_act", "")
    
    print(f"Extracted Sex Act: {sex_act}")
    print(f"Extracted Video Prompt:\n{video_prompt}")
    print("-" * 40)
    
    # Check LoRA lookup manually
    sex_acts_in_lookup = set()
    csv_path = "lookup/lora_lookup.csv"
    try:
        from workflow_generator import load_lora_lookup
        debug_lookup = load_lora_lookup(csv_path, filter_type="video", workflow_name="ltx_standard")
        print(f"Debug: load_lora_lookup returned {len(debug_lookup)} keys")
        if sex_act.lower() in debug_lookup:
            print(f"Debug: '{sex_act}' FOUND in debug_lookup")
        else:
            print(f"Debug: '{sex_act}' NOT FOUND in debug_lookup. Available keys: {list(debug_lookup.keys())[:5]}")

        with open(csv_path, mode='r', encoding='utf-8', errors='ignore') as f:
            reader = csv.reader(f)
            header = next(reader, None)
            # Based on file read: tag1(0), tag2(1), type(2)
            for row in reader:
                if len(row) > 2:
                    row_type = row[2].strip().lower()
                    if row_type == 'video':
                        if row[0]: sex_acts_in_lookup.add(row[0].strip())
                        if row[1]: sex_acts_in_lookup.add(row[1].strip())
    except Exception as e:
        print(f"Error reading CSV: {e}")
        
    is_valid = sex_act in sex_acts_in_lookup
    print(f"Is Sex Act in LoRA lookup? {'YES' if is_valid else 'NO'}")
    if not is_valid:
        print(f"Available video acts: {list(sex_acts_in_lookup)[:5]}...")
    
    # Generate all 5 LTX Workflow steps
    steps = ["ltx_preparation", "ltx_1st_sampling", "ltx_upscale", "ltx_2nd_sampling", "ltx_decode"]
    output_dir = "debug_workflows"
    os.makedirs(output_dir, exist_ok=True)
    
    print(f"Generating all 5 LTX workflow steps in {output_dir}/...")
    
    for step in steps:
        try:
            workflow = generate_api_workflow(
                project="ltx",
                type="video",
                template=step,
                acts=[sex_act] if sex_act else [],
                width=1280,
                height=720,
                length=161,
                video_prompt=video_prompt,
                work_id="wg22j_test_integration",
                fps=24
            )
            
            output_file = os.path.join(output_dir, f"{step}.json")
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(workflow, f, indent=2)
                
            print(f" - {step}: Generated and saved to {output_file}")
            
            # Brief check for LoRAs in sampling steps
            if "sampling" in step:
                loras_found = []
                for node_id, node in workflow.items():
                    inputs = node.get("inputs", {})
                    if "lora_name" in inputs:
                        if not inputs["lora_name"].endswith("add-detail.safetensors"):
                            loras_found.append(inputs["lora_name"])
                if loras_found:
                    print(f"   [LoRAs: {', '.join(set(loras_found))}]")

        except Exception as e:
            print(f"Error generating {step}: {e}")

if __name__ == "__main__":
    test_integration()
