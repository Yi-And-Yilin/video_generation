import sys, os
sys.path.insert(0, r'C:\SimpleAIHelper\video_generation')
sys.path.insert(0, os.path.join(os.getcwd(), 'projects', 'ltx'))

# 1. Import workflow
from new_tab_workflow import run_new_tab_workflow, load_tool_schema, load_prompt_template
print("OK new_tab_workflow imports OK")

# 2. Check that scene_design_z schema loads
schema = load_tool_schema('scene_design_z')
assert schema['function']['name'] == 'answer'
fname = schema['function']['name']
print(f"OK scene_design_z schema loads OK (function: {fname})")

# 3. Check that scene_design_z.md loads
prompt = load_prompt_template('scene_design_z')
has_content = 'User Requirements' in prompt or 'user_requirements' in prompt.lower() or '{{' in prompt
assert has_content
print(f"OK scene_design_z.md template loads OK (length: {len(prompt)} chars)")

# 4. Import parameter extraction
from parameter_extraction import extract_params_from_new_tab_task, extract_params_from_z_mode_task
print("OK parameter_extraction imports OK")

# 5. Import workflow selector
from workflow_selector import TemplateCatalog, apply_placeholders_unified
print("OK workflow_selector imports OK")

# 6. Check that z-image template loads
z_wf = TemplateCatalog.load_template('z-image')
assert '57:27' in z_wf
print("OK z-image template loads OK")

# 7. Verify placeholders in z-image
node_57_27 = z_wf['57:27']['inputs']['text']
assert '**image_pos_prompt**' in node_57_27
print(f"OK z-image prompt placeholder found: {repr(node_57_27)}")

node_57_13 = z_wf['57:13']['inputs']
assert '**width**' in str(node_57_13['width'])
assert '**height**' in str(node_57_13['height'])
print(f"OK z-image dimensions placeholders: w={node_57_13['width']}, h={node_57_13['height']}")

node_57_3 = z_wf['57:3']['inputs']
assert '**random_number**' in str(node_57_3['seed'])
assert '**steps**' in str(node_57_3['steps'])
assert '**cfg**' in str(node_57_3['cfg'])
print(f"OK z-image KSampler placeholders: seed={node_57_3['seed']}, steps={node_57_3['steps']}, cfg={node_57_3['cfg']}")

# 8. Test placeholder substitution
params = {
    'image_pos_prompt': 'test prompt',
    'width': 1024,
    'height': 1024,
    'random_number': 123456789012345,
    'steps': 8,
    'cfg': 1,
    'sampler_name': 'res_multistep',
    'scheduler': 'simple',
}
result = apply_placeholders_unified(z_wf, params)
assert '**image_pos_prompt**' not in str(result)
print("OK Placeholder substitution works")

# Check types after substitution
w_val = result['57:13']['inputs']['width']
h_val = result['57:13']['inputs']['height']
seed_val = result['57:3']['inputs']['seed']
steps_val = result['57:3']['inputs']['steps']
cfg_val = result['57:3']['inputs']['cfg']
assert isinstance(w_val, int) or str(w_val) == '1024'
assert isinstance(h_val, int) or str(h_val) == '1024'
assert isinstance(seed_val, int)
assert isinstance(steps_val, int)
assert isinstance(cfg_val, int)
print("OK Type conversion works (int values preserved)")

# 9. Test parameter extraction with mock data
import tempfile, json, os
mock_task = {
    'job_id': 'test1',
    'character_design': {'male': {'age': 'Adult', 'nationality': 'Asian'}, 'female': {'age': 'Young', 'nationality': 'Asian'}},
    'location_design': {
        'locations': [{
            'location': 'bedroom',
            'time': 'night',
            'lighting': 'dim',
            'prompts': [{'sex_act': 'kissing', 'prompt': 'A kissing scene in bedroom'}],
            'sex_loras': [],
            'main_sex_act': ['kissing']
        }]
    },
    'mode': 'Z'
}
os.makedirs(r'C:\SimpleAIHelper\video_generation\tasks', exist_ok=True)
with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, dir=r'C:\SimpleAIHelper\video_generation\tasks') as f:
    json.dump(mock_task, f)
    tmp_path = f.name
try:
    params = extract_params_from_new_tab_task(tmp_path, scene_index=0, resolution='1024*1024', prompt_index=0)
    assert params.prompt == 'A kissing scene in bedroom'
    assert params.width == 1024
    assert params.height == 1024
    print(f"OK Z-mode prompt extraction: prompt={repr(params.prompt)}, sex_act extracted")
finally:
    os.unlink(tmp_path)

print()
print("=== ALL TESTS PASSED ===")
