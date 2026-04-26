import sys, os, json
sys.path.insert(0, r'C:\SimpleAIHelper\video_generation')
sys.path.insert(0, os.path.join(os.getcwd(), 'projects', 'ltx'))

from parameter_extraction import extract_params_from_new_tab_task

os.makedirs(r'C:\SimpleAIHelper\video_generation\tasks', exist_ok=True)

# Test 8a: Z-mode old format still works
task_z = {
    'job_id': 'qa_z',
    'character_design': {'male': {'name': 'John'}, 'female': {'name': 'Jane'}},
    'location_design': {
        'locations': [{
            'location': 'bedroom',
            'prompts': [{'sex_act': 'kissing', 'prompt': 'A kissing scene'}],
            'main_sex_act': ['kissing']
        }]
    },
    'mode': 'Z'
}
with open(r'C:\SimpleAIHelper\video_generation\tasks\qa_z.json', 'w', encoding='utf-8') as f:
    json.dump(task_z, f)
params = extract_params_from_new_tab_task(r'C:\SimpleAIHelper\video_generation\tasks\qa_z.json', scene_index=0, resolution='1024*1024', prompt_index=0)
assert params.prompt == 'A kissing scene', f'Got: {params.prompt}'
print('PASS: extract_params_from_new_tab_task - Z-mode old format still works')
os.unlink(r'C:\SimpleAIHelper\video_generation\tasks\qa_z.json')

# Test 8b: Tag-mode string format still works
task_tag = {
    'job_id': 'qa_tag',
    'character_design': {'male': {}, 'female': {}},
    'location_design': {
        'locations': [{
            'location': 'kitchen',
            'prompts': ['A cooking scene'],
            'main_sex_act': ['cooking']
        }]
    },
    'mode': 'Tag'
}
with open(r'C:\SimpleAIHelper\video_generation\tasks\qa_tag.json', 'w', encoding='utf-8') as f:
    json.dump(task_tag, f)
params = extract_params_from_new_tab_task(r'C:\SimpleAIHelper\video_generation\tasks\qa_tag.json', scene_index=0, resolution='1024*1024', prompt_index=0)
assert params.prompt == 'A cooking scene', f'Got: {params.prompt}'
print('PASS: extract_params_from_new_tab_task - Tag-mode string format still works')
os.unlink(r'C:\SimpleAIHelper\video_generation\tasks\qa_tag.json')
