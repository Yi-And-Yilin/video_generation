"""
End-to-End Pipeline Test: task.json -> batch tasks -> workflows -> (mock ComfyUI)

Tests the full pipeline from user input through task generation,
parameter extraction, batch task conversion, workflow generation,
and mock ComfyUI image/video generation.
"""

import sys
import os
import json
from pathlib import Path

# Add paths
PROJECT_ROOT = r"C:\SimpleAIHelper\video_generation"
LTX_PROJECT = os.path.join(PROJECT_ROOT, "projects", "ltx")
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, LTX_PROJECT)

from PIL import Image
from PIL.PngImagePlugin import PngInfo

from parameter_extraction import (
    extract_params_from_new_tab_task,
    extract_params_for_wan_video,
    new_tab_task_to_ltx_batch_tasks,
)
from workflow_generator import generate_api_workflow

passed = 0
failed = 0
total = 0
results = []


def test(name, condition, detail=""):
    global passed, failed, total
    total += 1
    if condition:
        passed += 1
        results.append(f"  PASS: {name}")
        print(f"  PASS: {name}" + (f"  [{detail}]" if detail else ""))
    else:
        failed += 1
        results.append(f"  FAIL: {name}" + (f"  [{detail}]" if detail else ""))
        print(f"  FAIL: {name}" + (f"  [{detail}]" if detail else ""))


print("=" * 70)
print("STEP 1: Create task.json files for Z mode and Tag mode")
print("=" * 70)

os.makedirs(os.path.join(PROJECT_ROOT, "tasks"), exist_ok=True)
os.makedirs(os.path.join(PROJECT_ROOT, "output_images"), exist_ok=True)
os.makedirs(os.path.join(PROJECT_ROOT, "input"), exist_ok=True)

# --- Z Mode Task ---
z_task = {
    "job_id": "test_e2e",
    "user_requirements": "A romantic couple having dinner in a cozy restaurant, night scene",
    "mode": "Z",
    "character_design": {
        "male": {
            "name": "James",
            "age": "Adult",
            "nationality": "American",
            "height": "175cm",
            "body_shape": "Slim",
            "hair_style": "Short black hair",
            "personality": "Gentle, attentive"
        },
        "female": {
            "name": "Lily",
            "age": "Young",
            "nationality": "French",
            "height": "165cm",
            "body_shape": "Slender",
            "hair_style": "Long wavy brown hair",
            "personality": "Elegant, warm"
        }
    },
    "location_design": {
        "locations": [
            {
                "location": "restaurant",
                "time": "night",
                "lighting": "dim warm candlelight",
                "prompts": [
                    {
                        "image_prompt": "James and Lily sitting across from each other at a cozy restaurant table, candlelight between them, soft bokeh background",
                        "video_prompt": "Lily smiles gently James leans forward slowly soft jazz music soft young female voice"
                    },
                    {
                        "image_prompt": "Close-up of James and Lily's hands touching across the candlelit table, intimate atmosphere",
                        "video_prompt": "Their fingers gently intertwine James whispers softly soft jazz music soft male voice"
                    },
                    {
                        "image_prompt": "James reaches across to brush a strand of hair from Lily's face, warm romantic lighting",
                        "video_prompt": "He gently brushes her hair Lily closes her eyes softly romantic music soft young female voice"
                    }
                ],
                "main_sex_act": ["romantic_intimacy"]
            }
        ]
    }
}
z_path = os.path.join(PROJECT_ROOT, "tasks", "test_e2e.json")
with open(z_path, 'w', encoding='utf-8') as f:
    json.dump(z_task, f, indent=4)
print(f"  Created: {z_path}")

# --- Tag Mode Task ---
tag_task = {
    "job_id": "test_e2e_tag",
    "user_requirements": "A couple walking in park",
    "mode": "Tag",
    "character_design": {
        "male": {"name": "John", "age": "Adult", "nationality": "American"},
        "female": {"name": "Sarah", "age": "Young", "nationality": "British"}
    },
    "location_design": {
        "locations": [{
            "location": "park",
            "prompts": [
                "John and Sarah walking hand in hand at sunset",
                "Sarah laughing as John spins her around",
                "Couple sitting on bench watching the sunset"
            ],
            "main_sex_act": ["walking"]
        }]
    }
}
tag_path = os.path.join(PROJECT_ROOT, "tasks", "test_e2e_tag.json")
with open(tag_path, 'w', encoding='utf-8') as f:
    json.dump(tag_task, f, indent=4)
print(f"  Created: {tag_path}")

print()
print("=" * 70)
print("STEP 2: Verify Task Generation Pipeline (Z Mode)")
print("=" * 70)

# 2a: extract_params_from_new_tab_task
print("\n[2a] extract_params_from_new_tab_task — Phase 4+ format")
try:
    params = extract_params_from_new_tab_task(z_path, scene_index=0, resolution="1024*1024", prompt_index=0)
    test("prompt matches image_prompt",
         params.prompt == "James and Lily sitting across from each other at a cozy restaurant table, candlelight between them, soft bokeh background",
         f"got: {params.prompt[:60]}...")
    test("main_sex_act == ['romantic_intimacy']",
         params.main_sex_act == ["romantic_intimacy"],
         f"got: {params.main_sex_act}")
    test("character names set",
         params.character_male_name == "James" and params.character_female_name == "Lily",
         f"male={params.character_male_name}, female={params.character_female_name}")
    test("location set",
         params.location_name == "restaurant",
         f"got: {params.location_name}")
except Exception as e:
    test("extract_params_from_new_tab_task", False, str(e))

# 2b: extract_params_for_wan_video
print("\n[2b] extract_params_for_wan_video — video_prompt extracted")
try:
    video_params = extract_params_for_wan_video(z_path, resolution="1280*720")
    test("video_pos_prompt contains 'Lily smiles'",
         "Lily smiles" in video_params.video_pos_prompt,
         f"got: {video_params.video_pos_prompt[:80]}...")
    test("video_prompt field set",
         video_params.video_prompt == video_params.video_pos_prompt,
         f"video_prompt: {video_params.video_prompt[:60]}...")
    test("load_image set",
         video_params.load_image == "test_e2e.png",
         f"got: {video_params.load_image}")
except Exception as e:
    test("extract_params_for_wan_video", False, str(e))

# 2c: new_tab_task_to_ltx_batch_tasks (bridge function)
print("\n[2c] new_tab_task_to_ltx_batch_tasks — bridge function")
try:
    batch_tasks = new_tab_task_to_ltx_batch_tasks(z_path)
    test("3 batch tasks generated",
         len(batch_tasks) == 3,
         f"got {len(batch_tasks)}")
    test("work_id format: scene0_act0",
         batch_tasks[0]["work_id"] == "test_e2e_scene0_act0",
         f"got: {batch_tasks[0]['work_id']}")
    test("work_id format: scene0_act1",
         batch_tasks[1]["work_id"] == "test_e2e_scene0_act1",
         f"got: {batch_tasks[1]['work_id']}")
    test("work_id format: scene0_act2",
         batch_tasks[2]["work_id"] == "test_e2e_scene0_act2",
         f"got: {batch_tasks[2]['work_id']}")
    test("prompt uses image_prompt",
         batch_tasks[0]["prompt"] == z_task["location_design"]["locations"][0]["prompts"][0]["image_prompt"],
         f"got: {batch_tasks[0]['prompt'][:60]}...")
    test("video_pos_prompt uses video_prompt",
         batch_tasks[0]["video_pos_prompt"] == z_task["location_design"]["locations"][0]["prompts"][0]["video_prompt"],
         f"got: {batch_tasks[0]['video_pos_prompt'][:60]}...")
    test("video_pos_prompt != prompt (different fields)",
         batch_tasks[0]["video_pos_prompt"] != batch_tasks[0]["prompt"],
         "should differ for Phase 4+ format")
except Exception as e:
    test("new_tab_task_to_ltx_batch_tasks", False, str(e))

# 2d: generate_api_workflow — video_prompt in workflow JSON
print("\n[2d] generate_api_workflow — video_prompt in workflow JSON")
try:
    wf = generate_api_workflow(
        project="ltx",
        type="video",
        template="ltx_sampling",
        acts=batch_tasks[0].get("main_sex_act", []),
        width=1280,
        height=720,
        length=241,
        prompt=batch_tasks[0]["prompt"],
        negative_prompt=batch_tasks[0]["negative_prompt"],
        work_id=batch_tasks[0]["work_id"],
        video_pos_prompt=batch_tasks[0]["video_pos_prompt"],
    )
    wf_str = json.dumps(wf)
    test("video_pos_prompt in workflow JSON",
         "Lily smiles gently James leans forward" in wf_str,
         f"workflow has {len(wf_str)} chars")
    test("workflow is dict",
         isinstance(wf, dict),
         f"got {type(wf)}")
    test("workflow has nodes",
         len(wf) > 0,
         f"{len(wf)} nodes")
except Exception as e:
    test("generate_api_workflow", False, str(e))

print()
print("=" * 70)
print("STEP 3: Simulate ComfyUI Image Generation (Mock)")
print("=" * 70)

work_id = "test_e2e_scene0_act0"
output_dir = os.path.join(PROJECT_ROOT, "output_images")
with open(z_path, 'r', encoding='utf-8') as f:
    task_data = json.load(f)
loc = task_data["location_design"]["locations"][0]
prompt_data = loc["prompts"][0]

metadata = {
    "prompt": prompt_data["image_prompt"],
    "video_prompt": prompt_data["video_prompt"],
    "sex_act": loc["main_sex_act"][0] if loc["main_sex_act"] else "",
    "location": loc["location"],
    "job_id": task_data["job_id"],
    "character_male": task_data["character_design"]["male"].get("name", ""),
    "character_female": task_data["character_design"]["female"].get("name", ""),
    "timestamp": "2026-04-24T12:00:00",
}

mock_img = Image.new("RGB", (1024, 1024), color="gray")
output_path = os.path.join(output_dir, f"{work_id}.png")
meta_str = json.dumps(metadata, ensure_ascii=False, indent=2)
pnginfo = PngInfo()
pnginfo.add_text("prompt", meta_str)
mock_img.save(output_path, pnginfo=pnginfo)
print(f"  Created mock image: {output_path}")

with Image.open(output_path) as verify_img:
    png_meta = verify_img.info.get("prompt", "{}")
    meta_loaded = json.loads(png_meta)
    test("Metadata: prompt field matches",
         meta_loaded["prompt"] == prompt_data["image_prompt"])
    test("Metadata: video_prompt field matches",
         meta_loaded["video_prompt"] == prompt_data["video_prompt"])
    test("Metadata: sex_act preserved",
         meta_loaded["sex_act"] == "romantic_intimacy")
    test("Metadata: character names saved",
         meta_loaded["character_male"] == "James" and meta_loaded["character_female"] == "Lily")

print()
print("=" * 70)
print("STEP 4: Simulate BatchRunner Task Processing (Mock)")
print("=" * 70)

from batch_runner import BatchRunner

runner = BatchRunner(
    comfyui_url="http://mock:8188/prompt",
    output_folder=os.path.join(PROJECT_ROOT, "output_images"),
    input_folder=os.path.join(PROJECT_ROOT, "input"),
    processed_folder=os.path.join(PROJECT_ROOT, "output_images", "processed"),
    log_func=print,
)

tasks = new_tab_task_to_ltx_batch_tasks(z_path)

print("\n[4a] BatchRunner task field validation")
for i, task in enumerate(tasks):
    test(f"Task {i} ({task['work_id']}) has work_id", "work_id" in task)
    test(f"Task {i} ({task['work_id']}) has prompt", "prompt" in task)
    test(f"Task {i} ({task['work_id']}) has video_pos_prompt", "video_pos_prompt" in task)
    test(f"Task {i} ({task['work_id']}) has negative_prompt", "negative_prompt" in task)
    test(f"Task {i} ({task['work_id']}) has main_sex_act", "main_sex_act" in task)

print("\n[4b] video_pos_prompt differs from prompt (Phase 4+ format)")
for task in tasks:
    test(f"video_pos_prompt != prompt for {task['work_id']}",
         task["video_pos_prompt"] != task["prompt"])

print("\n[4c] generate_api_workflow for each batch task")
for task in tasks:
    wf = generate_api_workflow(
        project="ltx",
        type="video",
        template="ltx_sampling",
        acts=task.get("main_sex_act", []),
        width=1280,
        height=720,
        length=241,
        prompt=task["prompt"],
        negative_prompt=task["negative_prompt"],
        work_id=task["work_id"],
        video_pos_prompt=task["video_pos_prompt"],
    )
    test(f"Workflow for {task['work_id']} is dict", isinstance(wf, dict))
    test(f"Workflow for {task['work_id']} not empty", len(wf) > 0, f"{len(wf)} nodes")
    wf_str = json.dumps(wf)
    test(f"Workflow {task['work_id']} contains video_prompt text",
         "Lily smiles" in wf_str or "Their fingers" in wf_str or "He gently" in wf_str)

print("\n[4d] BatchRunner initialization")
test("BatchRunner created successfully", runner is not None)
test("BatchRunner.running = False", runner.running == False)
test("BatchRunner.cancel_event not set", not runner.cancel_event.is_set())

print()
print("=" * 70)
print("STEP 5: Tag Mode Pipeline Tests")
print("=" * 70)

print("\n[5a] extract_params_from_new_tab_task — Tag mode")
try:
    tag_params = extract_params_from_new_tab_task(tag_path, scene_index=0, resolution="1024*1024", prompt_index=0)
    test("Tag mode prompt matches raw string",
         tag_params.prompt == tag_task["location_design"]["locations"][0]["prompts"][0])
    test("Tag mode main_sex_act preserved",
         tag_params.main_sex_act == ["walking"])
    test("Tag mode character names set",
         tag_params.character_male_name == "John" and tag_params.character_female_name == "Sarah")
except Exception as e:
    test("Tag mode extract_params", False, str(e))

print("\n[5b] extract_params_for_wan_video — Tag mode (fallback to prompt)")
try:
    tag_video_params = extract_params_for_wan_video(tag_path, resolution="1280*720")
    test("Tag mode video_pos_prompt falls back to prompt text",
         tag_video_params.video_pos_prompt == tag_task["location_design"]["locations"][0]["prompts"][0])
    test("Tag mode video_prompt == video_pos_prompt",
         tag_video_params.video_prompt == tag_video_params.video_pos_prompt)
except Exception as e:
    test("Tag mode extract_params_for_wan_video", False, str(e))

print("\n[5c] new_tab_task_to_ltx_batch_tasks — Tag mode bridge")
try:
    tag_batch = new_tab_task_to_ltx_batch_tasks(tag_path)
    test("Tag mode: 3 batch tasks", len(tag_batch) == 3, f"got {len(tag_batch)}")
    test("Tag mode: work_id format correct",
         tag_batch[0]["work_id"] == "test_e2e_tag_scene0_act0",
         f"got: {tag_batch[0]['work_id']}")
    test("Tag mode: video_pos_prompt == prompt (same source)",
         tag_batch[0]["video_pos_prompt"] == tag_batch[0]["prompt"])
    test("Tag mode: prompt uses raw string",
         tag_batch[0]["prompt"] == tag_task["location_design"]["locations"][0]["prompts"][0])
except Exception as e:
    test("Tag mode bridge function", False, str(e))

print("\n[5d] generate_api_workflow — Tag mode")
try:
    wf = generate_api_workflow(
        project="ltx",
        type="video",
        template="ltx_sampling",
        acts=tag_batch[0].get("main_sex_act", []),
        width=1280,
        height=720,
        length=241,
        prompt=tag_batch[0]["prompt"],
        negative_prompt=tag_batch[0]["negative_prompt"],
        work_id=tag_batch[0]["work_id"],
        video_pos_prompt=tag_batch[0]["video_pos_prompt"],
    )
    wf_str = json.dumps(wf)
    test("Tag mode workflow contains prompt text",
         "John and Sarah walking hand in hand" in wf_str)
    test("Tag mode workflow is valid dict", isinstance(wf, dict))
except Exception as e:
    test("Tag mode workflow generation", False, str(e))

print()
print("=" * 70)
print("STEP 6: Verify main_ui.py Integration Points")
print("=" * 70)

main_ui_path = os.path.join(PROJECT_ROOT, "main_ui.py")
with open(main_ui_path, 'r', encoding='utf-8') as f:
    source = f.read()

test("main_ui.py has new_tab_last_job_id", "new_tab_last_job_id" in source)
test("main_ui.py has new_tab_run_ltx_video_generation", "def new_tab_run_ltx_video_generation" in source)
test("main_ui.py imports new_tab_task_to_ltx_batch_tasks", "new_tab_task_to_ltx_batch_tasks" in source)
test("main_ui.py imports BatchRunner", "BatchRunner" in source)
test("main_ui.py does NOT import extract_params_for_wan_video (uses new_tab_task_to_ltx_batch_tasks instead)", "extract_params_for_wan_video" not in source)

print()
print("=" * 70)
print("STEP 7: Edge Cases")
print("=" * 70)

# 7a: Empty prompts
empty_task = {
    "job_id": "empty_test",
    "character_design": {"male": {}, "female": {}},
    "location_design": {"locations": [{"location": "empty", "prompts": [], "main_sex_act": []}]},
    "mode": "Z"
}
empty_path = os.path.join(PROJECT_ROOT, "tasks", "empty_test.json")
with open(empty_path, 'w', encoding='utf-8') as f:
    json.dump(empty_task, f)

print("\n[7a] Empty prompts list")
try:
    empty_batch = new_tab_task_to_ltx_batch_tasks(empty_path)
    test("Empty prompts returns 0 tasks", len(empty_batch) == 0, f"got {len(empty_batch)}")
except Exception as e:
    test("Empty prompts", False, str(e))

# 7b: Mixed location with different prompt counts
mixed_task = {
    "job_id": "mixed_test",
    "character_design": {"male": {}, "female": {}},
    "location_design": {
        "locations": [
            {
                "location": "loc1",
                "prompts": [
                    {"image_prompt": "Prompt 1A", "video_prompt": "Video 1A"},
                    {"image_prompt": "Prompt 1B", "video_prompt": "Video 1B"}
                ],
                "main_sex_act": ["act1"]
            },
            {
                "location": "loc2",
                "prompts": [
                    {"image_prompt": "Prompt 2", "video_prompt": "Video 2"}
                ],
                "main_sex_act": ["act2"]
            }
        ]
    },
    "mode": "Z"
}
mixed_path = os.path.join(PROJECT_ROOT, "tasks", "mixed_test.json")
with open(mixed_path, 'w', encoding='utf-8') as f:
    json.dump(mixed_task, f)

print("\n[7b] Mixed location prompt counts")
try:
    mixed_batch = new_tab_task_to_ltx_batch_tasks(mixed_path)
    test("Mixed locations: 3 total tasks", len(mixed_batch) == 3, f"got {len(mixed_batch)}")
    test("mixed_batch[0] work_id: mixed_test_scene0_act0",
         mixed_batch[0]["work_id"] == "mixed_test_scene0_act0",
         f"got: {mixed_batch[0]['work_id']}")
    test("mixed_batch[1] work_id: mixed_test_scene0_act1",
         mixed_batch[1]["work_id"] == "mixed_test_scene0_act1",
         f"got: {mixed_batch[1]['work_id']}")
    test("mixed_batch[2] work_id: mixed_test_scene1_act0",
         mixed_batch[2]["work_id"] == "mixed_test_scene1_act0",
         f"got: {mixed_batch[2]['work_id']}")
    test("Scene 0 tasks use act1", mixed_batch[0]["main_sex_act"] == "act1" or mixed_batch[0]["main_sex_act"] == ["act1"])
    test("Scene 1 tasks use act2", mixed_batch[2]["main_sex_act"] == "act2" or mixed_batch[2]["main_sex_act"] == ["act2"])
except Exception as e:
    test("Mixed location counts", False, str(e))

# 7c: Multiple scenes in Z mode
multi_scene_task = {
    "job_id": "multi_scene_test",
    "character_design": {"male": {"name": "A", "age": "", "nationality": ""}, "female": {"name": "B", "age": "", "nationality": ""}},
    "location_design": {
        "locations": [
            {
                "location": "kitchen",
                "prompts": [
                    {"image_prompt": "Kitchen scene A", "video_prompt": "Kitchen video A"},
                    {"image_prompt": "Kitchen scene B", "video_prompt": "Kitchen video B"}
                ],
                "main_sex_act": ["kiss"]
            },
            {
                "location": "garden",
                "prompts": [
                    {"image_prompt": "Garden scene A", "video_prompt": "Garden video A"},
                    {"image_prompt": "Garden scene B", "video_prompt": "Garden video B"},
                    {"image_prompt": "Garden scene C", "video_prompt": "Garden video C"}
                ],
                "main_sex_act": ["intimacy"]
            }
        ]
    },
    "mode": "Z"
}
multi_scene_path = os.path.join(PROJECT_ROOT, "tasks", "multi_scene_test.json")
with open(multi_scene_path, 'w', encoding='utf-8') as f:
    json.dump(multi_scene_task, f)

print("\n[7c] Multiple scenes with different prompt counts")
try:
    multi_batch = new_tab_task_to_ltx_batch_tasks(multi_scene_path)
    test("Multi-scene: 5 total tasks", len(multi_batch) == 5, f"got {len(multi_batch)}")
    test("Scene 0: 2 prompts",
         multi_batch[0]["prompt"] == "Kitchen scene A" and multi_batch[1]["prompt"] == "Kitchen scene B")
    test("Scene 1: 3 prompts",
         multi_batch[2]["prompt"] == "Garden scene A" and
         multi_batch[4]["prompt"] == "Garden scene C")
    test("Scene 1 tasks use act2 (intimacy)",
         multi_batch[2]["main_sex_act"] == "intimacy" or multi_batch[2]["main_sex_act"] == ["intimacy"])
    for task in multi_batch:
        test(f"Multi-scene task {task['work_id']} has video_prompt",
             task["video_pos_prompt"] == "Kitchen video A" or task["video_pos_prompt"] == "Garden video A" or
             task["video_pos_prompt"] == "Kitchen video B" or task["video_pos_prompt"] == "Garden video B" or
             task["video_pos_prompt"] == "Garden video C")
except Exception as e:
    test("Multi-scene pipeline", False, str(e))

print()
print("=" * 70)
print("STEP 8: Additional Integration Tests")
print("=" * 70)

# Test StandardWorkflowParams roundtrip
print("\n[8a] StandardWorkflowParams roundtrip")
try:
    from parameter_extraction import StandardWorkflowParams
    p = StandardWorkflowParams(job_id="test", work_id="test1", prompt="hello world")
    d = p.to_dict()
    p2 = StandardWorkflowParams.from_dict(d)
    test("to_dict/from_dict roundtrip preserves job_id", p2.job_id == "test")
    test("to_dict/from_dict roundtrip preserves prompt", p2.prompt == "hello world")
    test("merge creates new instance", p.merge(width=1920).width == 1920)
except Exception as e:
    test("StandardWorkflowParams", False, str(e))

# Test extract_params_from_new_tab_task with scene_index
print("\n[8b] extract_params_from_new_tab_task — scene_index=1 on multi-scene")
try:
    scene1_params = extract_params_from_new_tab_task(multi_scene_path, scene_index=1, resolution="1024*1024", prompt_index=0)
    test("Scene index 1 prompt from garden",
         scene1_params.prompt == "Garden scene A",
         f"got: {scene1_params.prompt}")
except Exception as e:
    test("Scene index 1", False, str(e))

# Test with prompt_index
print("\n[8c] extract_params_from_new_tab_task — prompt_index=1")
try:
    params_p1 = extract_params_from_new_tab_task(z_path, scene_index=0, resolution="1024*1024", prompt_index=1)
    test("Prompt index 1: hands touching",
         "hands touching" in params_p1.prompt.lower(),
         f"got: {params_p1.prompt[:60]}...")
    params_p2 = extract_params_from_new_tab_task(z_path, scene_index=0, resolution="1024*1024", prompt_index=2)
    test("Prompt index 2: hair brushing",
         "brush" in params_p2.prompt.lower() or "hair" in params_p2.prompt.lower(),
         f"got: {params_p2.prompt[:60]}...")
except Exception as e:
    test("Prompt index", False, str(e))

# Test generate_api_workflow for image type
print("\n[8d] generate_api_workflow — image type")
try:
    wf_img = generate_api_workflow(
        project="ltx",
        type="image",
        template="wan_image",
        acts=["romantic_intimacy"],
        width=1024,
        height=1024,
        length=241,
        prompt="James and Lily at restaurant",
        negative_prompt="ugly, deformed",
        work_id="test_image",
        video_pos_prompt="Lily smiles gently",
    )
    test("Image workflow is dict", isinstance(wf_img, dict))
    wf_str = json.dumps(wf_img)
    test("Image workflow contains prompt", "James and Lily" in wf_str)
except Exception as e:
    test("Image workflow generation", False, str(e))

# Test with None/empty acts
print("\n[8e] generate_api_workflow — empty acts list")
try:
    wf_empty = generate_api_workflow(
        project="ltx",
        type="video",
        template="ltx_sampling",
        acts=[],
        width=1280,
        height=720,
        length=241,
        prompt="test",
        negative_prompt="bad",
        work_id="test_empty_acts",
    )
    test("Empty acts workflow is valid", isinstance(wf_empty, dict) and len(wf_empty) > 0)
except Exception as e:
    test("Empty acts", False, str(e))


print()
print("=" * 70)
print("FINAL SUMMARY")
print("=" * 70)
print(f"\n  Total tests:  {total}")
print(f"  Passed:       {passed}")
print(f"  Failed:       {failed}")
print(f"  Pass rate:    {passed/total*100:.1f}%")
print()

print("\n--- Detailed Results ---")
for r in results:
    print(r)

print()
if failed == 0:
    print("ALL TESTS PASSED — Pipeline is fully functional!")
else:
    print(f"WARNING: {failed} test(s) failed. Review above for details.")
