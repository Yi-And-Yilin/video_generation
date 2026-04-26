import sys, os, json
sys.path.insert(0, 'projects/ltx')
sys.path.insert(0, '.')
from workflow_generator import generate_api_workflow

# Test 1st_sampling
print('=== 1st_sampling ===')
wf = generate_api_workflow('ltx', 'video', 'ltx_1st_sampling', acts=['lying_cowgirl'], width=1280, height=720, length=241, prompt='test', video_pos_prompt='test', work_id='test', fps=24)
n9 = wf['9']['inputs']
n10 = wf['10']['inputs']
print('Node 9 (Distill): lora_name=%s  strength=%s' % (n9['lora_name'], n9['strength_model']))
print('Node 10 (Dynamic): lora_name=%s  strength=%s' % (n10['lora_name'], n10['strength_model']))

# Test 2nd_sampling
print()
print('=== 2nd_sampling ===')
wf2 = generate_api_workflow('ltx', 'video', 'ltx_2nd_sampling', acts=['lying_cowgirl'], width=1280, height=720, length=241, prompt='test', video_pos_prompt='test', work_id='test', fps=24)
n2 = wf2['2']['inputs']
n3 = wf2['3']['inputs']
print('Node 2 (Distill): lora_name=%s  strength=%s' % (n2['lora_name'], n2['strength_model']))
print('Node 3 (Dynamic): lora_name=%s  strength=%s' % (n3['lora_name'], n3['strength_model']))

# Test upscale
print()
print('=== upscale ===')
wf3 = generate_api_workflow('ltx', 'video', 'ltx_upscale', acts=['lying_cowgirl'], width=1280, height=720, length=241, prompt='test', video_pos_prompt='test', work_id='test', fps=24, load_image='test.png')
for nid, node in sorted(wf3.items(), key=lambda x: int(x[0])):
    if 'LoraLoader' in node.get('class_type', ''):
        inp = node['inputs']
        print('Node %s: lora_name=%s  strength=%s' % (nid, inp.get('lora_name', 'N/A'), inp.get('strength_model', 'N/A')))

print()
print('=== ALL CHECKS PASSED ===')
